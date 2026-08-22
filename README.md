# Yatzy Trainer

Play Scandinavian Yatzy and get feedback, after every hold and every
category-fill, on whether your move matched optimal play under the
precomputed value function (`GAME_STATE_V`, solved via DP, loaded from
`game_values.csv`). Nickname-gated, with a Postgres-backed hiscores board
(ranked by accuracy, tiebroken by completion time; also sortable by score).

## What's in here

- `game_engine.py` — loads `GAME_STATE_V` and the precomputes tables once,
  and extends the existing `solve_optimal_play` logic (from `solver.py`) so
  it also exposes the underlying **value arrays** (not just argmaxes). This
  is what lets the app judge a move by EV gap against the best legal move,
  rather than by argmax match (so ties are scored as optimal, correctly).
  Also owns the `Session` dataclass (in-memory, per-game state).
- `server.py` — FastAPI app: endpoints (`new_game`, `roll`, `hold`, `fill`,
  `hiscores`) backed by in-memory game sessions, plus static file serving
  for the frontend.
- `db.py` — Postgres access for the hiscores table (`psycopg2`, a small
  threaded connection pool, plain SQL — no ORM). `init_db()` creates the
  table/indexes if missing; runs once at FastAPI startup.
- `static/` — plain HTML/CSS/JS frontend. No build step.
- `verify_engine.py` — a standalone correctness check: confirms
  `GAME_STATE_V[full_open, 0] ≈ 248.44`, and that a scripted playthrough
  which always takes the engine's own optimal move reports 100% accuracy
  (with a random-play run alongside it as a sanity check that accuracy is
  *not* trivially 100%).

## Setup

```
pip install -r requirements.txt
```

You'll also need a Postgres instance for local development. The easiest way
is a throwaway Docker container (the app itself is *not* containerized —
this is just for a local database to develop against):

```
docker run --rm -p 5433:5432 -e POSTGRES_PASSWORD=devpass -e POSTGRES_DB=yatzy postgres:16
```

## Run

```
export DATABASE_URL=postgresql://postgres:devpass@localhost:5433/yatzy
uvicorn server:app --port 8000
```

(On Windows PowerShell: `$env:DATABASE_URL = "postgresql://postgres:devpass@localhost:5433/yatzy"`.)

Then open **http://127.0.0.1:8000/** in a browser. `DATABASE_URL` is
required — the app fails fast at startup if it's not set.

Startup loads `game_values.csv` (~39MB), builds the precomputes tables, and
creates the `games` table if it doesn't exist yet; this takes about a
second.

## Deploying (Railway)

The app deploys via Railway's Nixpacks builder (see `Procfile`) — no
Dockerfile needed, `psycopg2-binary` ships prebuilt wheels just like `numpy`
does. One-time setup in the Railway project:

1. **New → Database → PostgreSQL** to provision a Postgres plugin.
2. On the web service, add an env var `DATABASE_URL` =
   `${{Postgres.DATABASE_PRIVATE_URL}}` — the internal
   (`postgres.railway.internal`) variant, not the public proxy URL, since
   both services live in the same Railway project.
3. Redeploy (Railway triggers this automatically when the env var changes).

## Verify correctness (optional, before/instead of playing)

```
python verify_engine.py
```

Expected output: `OPTIMAL_EXPECTED_SCORE ≈ 248.44`, optimal playthroughs at
100.0000% accuracy, random playthroughs well below that (confirms the
judging logic isn't vacuously always reporting "optimal").

## How judging works

For every hold and every fill, the server compares the EV of your chosen
move against the EV of the best *legal* move in that same spot:

- **Fill**: for the dice you rolled and your current upper-progress `u`,
  compute the candidate value of every open category
  (`SCORE_ARRAY[dice, cat] + BONUS + GAME_STATE_V[next_scorecard, U_NEXT]`
  for upper categories, `SCORE_ARRAY[dice, cat] + GAME_STATE_V[next_scorecard, u]`
  otherwise) and compare your chosen category's value to the max.
- **Hold**: compute, for every legal hold given your current dice, the
  expected value over `HOLD_TRANSITIONS` against the appropriate next-stage
  value layer (the "must fill" value layer when 1 reroll remains, or the
  "1 reroll left" value layer when 2 rerolls remain), and compare your
  chosen hold's value to the max over legal holds.

A move is "optimal" if its EV is within `1e-6` of the best achievable EV —
so ties (which are common, e.g. several categories worth the same amount
with no upper-section interaction) are correctly scored as optimal rather
than flagged just because they don't match a single argmax.

The EV cost (`best_ev - chosen_ev`, floored at 0) is returned on every
suboptimal move, along with what the optimal move was.

## Gameplay notes

- Each turn is the standard 3-throw structure, and every throw is an
  explicit click of the **Roll** button — nothing auto-rolls. At the start
  of a turn, click Roll to get your first throw; click dice to toggle
  keeping them, then click Roll again to reroll the rest (up to twice);
  once you're out of rerolls, pick a category to fill.
- Dice you keep stay visually selected across a reroll (same values, just
  possibly reshuffled among the five slots) so you can see at a glance what
  you're holding going into the next decision — click a die again to
  release it before rerolling.
- To "stop rerolling early" simply hold all 5 dice — the value tables
  already account for this (holding everything is a legal, deterministic
  no-op reroll), so its EV is judged exactly like the DP intends.
- The scorecard shows a live preview of what each open category would score
  with your current dice once you're out of rerolls and must fill.
- Running score and accuracy (`optimal moves / total moves`) are tracked
  and shown throughout the game.

## Hiscores & nicknames

- On first load, you're asked for a nickname (remembered in `localStorage`
  after that, so you're not re-prompted every visit). It's sent with
  `POST /api/new_game` and attached to the game session.
- Completion time starts on your **first roll** of turn 1 (not when the page
  loads), so idle time before you start doesn't count against you.
- When a game ends, a row is written to the `games` table: nickname, total
  score, accuracy, completion time, and timestamp. A DB write failure never
  breaks your game-over screen — it's logged and swallowed
  (`server.py`'s `/api/fill` handler).
- The **Hiscores** button opens a leaderboard, `GET /api/hiscores?sort=...`:
  - `sort=accuracy` (default) — ranked by accuracy, ties broken by faster
    completion time.
  - `sort=score` — ranked by total score.
- Nicknames aren't authenticated — no accounts, no uniqueness — this is a
  casual leaderboard, not a login system.
