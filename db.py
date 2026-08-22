"""
Hiscores persistence. One table (`games`), one row per completed game.
Uses a small threaded connection pool since FastAPI's sync `def` endpoints
already run in a bounded threadpool (same as the numpy DP-solve work in
server.py), so concurrent pool checkout/return needs to be thread-safe.
"""
import os

import psycopg2
from psycopg2.pool import ThreadedConnectionPool

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set -- required to start the app")

_pool = ThreadedConnectionPool(minconn=1, maxconn=5, dsn=DATABASE_URL)

VALID_SORTS = {
    "accuracy": "accuracy DESC, completion_seconds ASC",
    "score": "total_score DESC",
}


def init_db():
    conn = _pool.getconn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS games (
                    id BIGSERIAL PRIMARY KEY,
                    nickname TEXT NOT NULL,
                    total_score INTEGER NOT NULL,
                    accuracy DOUBLE PRECISION NOT NULL,
                    moves_optimal INTEGER NOT NULL,
                    moves_total INTEGER NOT NULL,
                    completion_seconds DOUBLE PRECISION NOT NULL,
                    played_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
                """
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_games_accuracy "
                "ON games (accuracy DESC, completion_seconds ASC)"
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_games_score ON games (total_score DESC)"
            )
    finally:
        _pool.putconn(conn)


def insert_game(nickname, total_score, accuracy, moves_optimal, moves_total, completion_seconds):
    """Inserts the row and returns this game's rank on both leaderboards,
    computed in the same round-trip so the numbers are self-consistent."""
    conn = _pool.getconn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO games
                    (nickname, total_score, accuracy, moves_optimal, moves_total, completion_seconds)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (nickname, total_score, accuracy, moves_optimal, moves_total, completion_seconds),
            )
            cur.execute(
                """
                SELECT
                    (SELECT COUNT(*) FROM games
                     WHERE accuracy > %s OR (accuracy = %s AND completion_seconds < %s)) + 1,
                    (SELECT COUNT(*) FROM games WHERE total_score > %s) + 1,
                    (SELECT COUNT(*) FROM games)
                """,
                (accuracy, accuracy, completion_seconds, total_score),
            )
            accuracy_rank, score_rank, total_games = cur.fetchone()
    finally:
        _pool.putconn(conn)

    return {
        "accuracy_rank": accuracy_rank,
        "score_rank": score_rank,
        "total_games": total_games,
    }


def fetch_hiscores(sort: str, limit: int):
    order_by = VALID_SORTS[sort]  # caller (server.py) validates sort is a known key
    conn = _pool.getconn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT nickname, total_score, accuracy, moves_optimal, moves_total,
                       completion_seconds, played_at
                FROM games
                ORDER BY {order_by}
                LIMIT %s
                """,
                (limit,),
            )
            rows = cur.fetchall()
    finally:
        _pool.putconn(conn)

    return [
        {
            "nickname": r[0],
            "total_score": r[1],
            "accuracy": r[2],
            "moves_optimal": r[3],
            "moves_total": r[4],
            "completion_seconds": r[5],
            "played_at": r[6].isoformat(),
        }
        for r in rows
    ]
