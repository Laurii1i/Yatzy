"""
FastAPI backend for the Yatzy trainer. Loads the precomputed value table and
precomputes tables once at startup (via game_engine), keeps games in an
in-memory session dict (no database), and serves the static frontend.

Run:  uvicorn server:app --reload --port 8000
Then open http://127.0.0.1:8000/
"""
import logging
from typing import List

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import db
import game_engine as ge

logger = logging.getLogger("yatzy")

app = FastAPI(title="Yatzy Trainer")

CATEGORY_NAME_TO_COL = {name: i for i, name in enumerate(ge.CATEGORY_NAMES)}

MAX_NICKNAME_LEN = 32
HISCORES_SORTS = {"accuracy", "score"}


@app.on_event("startup")
def on_startup():
    db.init_db()


class SessionRequest(BaseModel):
    session_id: str


class NewGameRequest(BaseModel):
    nickname: str


class HoldRequest(BaseModel):
    session_id: str
    keep_indices: List[int]


class FillRequest(BaseModel):
    session_id: str
    category: str


def _session_or_404(session_id: str) -> ge.Session:
    try:
        return ge.get_session(session_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="unknown session_id")


@app.post("/api/new_game")
def new_game(req: NewGameRequest):
    nickname = req.nickname.strip()
    if not nickname:
        raise HTTPException(status_code=400, detail="nickname is required")
    if len(nickname) > MAX_NICKNAME_LEN:
        raise HTTPException(status_code=400, detail=f"nickname must be at most {MAX_NICKNAME_LEN} characters")

    s = ge.new_session(nickname)
    return s.public_state()


@app.get("/api/hiscores")
def hiscores(sort: str = "accuracy", limit: int = 20):
    if sort not in HISCORES_SORTS:
        raise HTTPException(status_code=400, detail=f"sort must be one of {sorted(HISCORES_SORTS)}")
    limit = max(1, min(limit, 100))
    return {"rows": db.fetch_hiscores(sort, limit)}


@app.get("/api/state/{session_id}")
def get_state(session_id: str):
    s = _session_or_404(session_id)
    return s.public_state()


@app.post("/api/roll")
def roll(req: SessionRequest):
    s = _session_or_404(req.session_id)
    if s.game_over:
        raise HTTPException(status_code=400, detail="game is over")
    if s.dice:
        raise HTTPException(status_code=400, detail="dice already rolled this turn")

    s.apply_first_roll()
    return {"state": s.public_state()}


@app.post("/api/hold")
def hold(req: HoldRequest):
    s = _session_or_404(req.session_id)
    if s.game_over:
        raise HTTPException(status_code=400, detail="game is over")
    if not s.dice:
        raise HTTPException(status_code=400, detail="roll first")
    if s.rerolls_remaining not in (2, 1):
        raise HTTPException(status_code=400, detail="no reroll decision available right now")

    n = len(s.dice)
    if len(set(req.keep_indices)) != len(req.keep_indices) or any(
        i < 0 or i >= n for i in req.keep_indices
    ):
        raise HTTPException(status_code=400, detail=f"keep_indices must be distinct values in [0,{n})")

    state = ge.solve_state(s.idx)
    result = ge.judge_hold(state, s.dice, s.u, s.rerolls_remaining, req.keep_indices)
    s.record_move(result["ev_cost"], result["optimal"])

    slot = "hold1" if s.rerolls_remaining == 2 else "hold2"
    s.current_turn_record()[slot] = {
        "optimal": result["optimal"],
        "chosen_dice": result["chosen_hold_dice"],
        "top_holds": result["top_holds"],
    }

    kept = [s.dice[i] for i in req.keep_indices]
    n_reroll = 5 - len(kept)
    s.dice = sorted(kept + ge.roll_dice(n_reroll))
    s.rerolls_remaining -= 1

    return {"judgment": result, "state": s.public_state()}


@app.post("/api/fill")
def fill(req: FillRequest):
    s = _session_or_404(req.session_id)
    if s.game_over:
        raise HTTPException(status_code=400, detail="game is over")
    if s.rerolls_remaining != 0:
        raise HTTPException(status_code=400, detail="rerolls remain -- hold/reroll before filling")

    category_col = CATEGORY_NAME_TO_COL.get(req.category)
    if category_col is None:
        raise HTTPException(status_code=400, detail=f"unknown category '{req.category}'")
    if category_col not in ge.GAME_STATES[s.idx].nonzero()[0]:
        raise HTTPException(status_code=400, detail=f"category '{req.category}' is not open")

    state = ge.solve_state(s.idx)
    result = ge.judge_fill(state, s.dice, s.u, category_col)
    s.record_move(result["ev_cost"], result["optimal"])

    s.current_turn_record()["fill"] = {
        "optimal": result["optimal"],
        "chosen_category": req.category,
        "top_fills": result["top_fills"],
    }

    s.total += result["gain"] + result["bonus"]
    s.u = result["new_u"]
    s.idx = result["new_idx"]
    s.turn += 1
    s.filled[req.category] = result["gain"]

    response = {"judgment": result}
    if ge.GAME_STATES[s.idx].sum() == 0:
        s.game_over = True
        response["final"] = {
            "score": s.total,
            "optimal_expected_score": ge.OPTIMAL_EXPECTED_SCORE,
            "history": s.history,
        }
        # A hiscores write failing must never break the player's game-over
        # response -- log and move on. If it succeeds, attach this game's
        # rank so the frontend can show it immediately.
        try:
            ranks = db.insert_game(
                s.nickname, s.total, s.accuracy(), s.moves_optimal, s.moves_total, s.elapsed_seconds()
            )
            response["final"]["ranks"] = ranks
        except Exception:
            logger.exception("failed to record hiscore for session %s", s.session_id)
    else:
        s.start_turn()

    response["state"] = s.public_state()
    return response


app.mount("/", StaticFiles(directory="static", html=True), name="static")
