"""
Core game logic for the Yatzy trainer: loads the precomputed value table and
precomputes module once, and exposes session-based gameplay with optimal-move
judging. No recomputation of the DP happens here -- GAME_STATE_V is loaded
from disk and everything else is derived from it plus the precomputes tables.
"""
import random
import uuid
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Optional

import numpy as np

from precomputes3 import (
    FIVE_DICE_STATES, DICE_STATE_TO_IDX,
    HOLD_STATES, HOLD_TRANSITIONS, POSSIBLE_HOLDS,
    SCORE_ARRAY, BONUS, U_NEXT,
    GAME_STATES, GAME_STATE_TRANSITIONS, CATEGORY_NAMES,
)
from csv_writer import load_game_state_V

# ---------------------------------------------------------------------------
# Load once at import time (server startup).
# ---------------------------------------------------------------------------
GAME_STATE_V = load_game_state_V()

N_CATEGORIES = len(CATEGORY_NAMES)
FULL_OPEN_IDX = len(GAME_STATES) - 1          # all 15 categories open
EMPTY_IDX = 0                                  # all categories closed
OPTIMAL_EXPECTED_SCORE = float(GAME_STATE_V[FULL_OPEN_IDX, 0])

HOLD_TO_IDX = {tuple(h): i for i, h in enumerate(HOLD_STATES)}
POSSIBLE_HOLDS_BOOL = POSSIBLE_HOLDS.astype(bool)

EV_TOLERANCE = 1e-6


def _dice_counts(dice):
    counts = [0] * 6
    for f in dice:
        counts[f - 1] += 1
    return tuple(counts)


def dice_to_dice_idx(dice):
    return DICE_STATE_TO_IDX[_dice_counts(dice)]


def hold_state_to_dice(hold_idx):
    """462-row hold state -> sorted list of face values, e.g. [3,3,5]."""
    counts = HOLD_STATES[hold_idx]
    return [f for f in range(1, 7) for _ in range(int(counts[f - 1]))]


def roll_dice(n):
    return [random.randint(1, 6) for _ in range(n)]


# ---------------------------------------------------------------------------
# Per-scorecard solve, extended to expose value arrays (not just argmaxes).
# Mirrors solver.solve_optimal_play's math exactly (verified against it),
# but also returns the candidate/value arrays needed to score arbitrary
# (possibly suboptimal) player choices, not only the best one.
# ---------------------------------------------------------------------------
@dataclass
class StateSolve:
    idx: int
    open_cols: np.ndarray          # (n_open,) category column ids, open in this scorecard
    transitions: np.ndarray        # (n_open,) successor scorecard idx, aligned to open_cols
    cand: np.ndarray               # (252, 64, n_open) fill candidate value per dice-state/u/open-cat
    final_Vs: np.ndarray           # (252, 64) = cand.max(axis=2): value with 0 rerolls left, must fill
    optimal_fill_field: np.ndarray  # (252, 64) category column of the best fill choice
    H1: np.ndarray                 # (462, 64) value of each hold when 1 reroll remains
    H2: np.ndarray                 # (462, 64) value of each hold when 2 rerolls remain


@lru_cache(maxsize=1024)
def solve_state(idx: int) -> StateSolve:
    transitions = np.array(GAME_STATE_TRANSITIONS[idx], dtype=int)
    open_cols = np.flatnonzero(GAME_STATES[idx])
    n_open = len(open_cols)

    cand = np.empty((252, 64, n_open), dtype=np.float64)
    for i, (open_col, new_state) in enumerate(zip(open_cols, transitions)):
        dv = GAME_STATE_V[new_state]
        if open_col < 6:
            cand[:, :, i] = SCORE_ARRAY[:, open_col][:, None] + BONUS[open_col] + dv[U_NEXT[open_col]]
        else:
            cand[:, :, i] = SCORE_ARRAY[:, open_col][:, None] + dv[None, :]

    final_Vs = cand.max(axis=2)
    optimal_fill_field = open_cols[cand.argmax(axis=2)]

    H1 = HOLD_TRANSITIONS @ final_Vs                                   # (462, 64)
    masked1 = np.where(POSSIBLE_HOLDS_BOOL[:, :, None], H1[None, :, :], -np.inf)
    Vs1 = masked1.max(axis=1)                                          # (252, 64)

    H2 = HOLD_TRANSITIONS @ Vs1                                        # (462, 64)

    return StateSolve(
        idx=idx, open_cols=open_cols, transitions=transitions, cand=cand,
        final_Vs=final_Vs, optimal_fill_field=optimal_fill_field, H1=H1, H2=H2,
    )


def judge_hold(state: StateSolve, dice, u: int, rerolls_remaining: int, keep_indices):
    """rerolls_remaining is the count BEFORE this hold decision (2 or 1)."""
    d_idx = dice_to_dice_idx(dice)
    H = state.H2 if rerolls_remaining == 2 else state.H1

    legal_mask = POSSIBLE_HOLDS_BOOL[d_idx]
    values = np.where(legal_mask, H[:, u], -np.inf)
    best_val = float(values.max())
    best_hold_idx = int(values.argmax())

    kept = [dice[i] for i in keep_indices]
    chosen_hold_idx = HOLD_TO_IDX[_dice_counts_partial(kept)]
    chosen_val = float(H[chosen_hold_idx, u])

    ev_cost = max(0.0, best_val - chosen_val)
    optimal = ev_cost <= EV_TOLERANCE

    return {
        "chosen_ev": chosen_val,
        "optimal_ev": best_val,
        "ev_cost": ev_cost,
        "optimal": optimal,
        "optimal_hold_dice": hold_state_to_dice(best_hold_idx),
        "chosen_hold_dice": sorted(kept),
    }


def _dice_counts_partial(dice_subset):
    counts = [0] * 6
    for f in dice_subset:
        counts[f - 1] += 1
    return tuple(counts)


def judge_fill(state: StateSolve, dice, u: int, category_col: int):
    d_idx = dice_to_dice_idx(dice)
    matches = np.flatnonzero(state.open_cols == category_col)
    if len(matches) == 0:
        raise ValueError(f"category {category_col} is not open in this scorecard")
    i = int(matches[0])

    chosen_val = float(state.cand[d_idx, u, i])
    best_val = float(state.final_Vs[d_idx, u])
    best_col = int(state.optimal_fill_field[d_idx, u])

    ev_cost = max(0.0, best_val - chosen_val)
    optimal = ev_cost <= EV_TOLERANCE

    gain = int(SCORE_ARRAY[d_idx, category_col])
    bonus = 0
    if category_col < 6:
        new_u = min(u + gain, 63)
        if u < 63 and new_u >= 63:
            bonus = 50
    else:
        new_u = u

    new_idx = int(state.transitions[i])

    return {
        "chosen_ev": chosen_val,
        "optimal_ev": best_val,
        "ev_cost": ev_cost,
        "optimal": optimal,
        "optimal_category": CATEGORY_NAMES[best_col],
        "gain": gain,
        "bonus": bonus,
        "new_u": new_u,
        "new_idx": new_idx,
    }


# ---------------------------------------------------------------------------
# Session: one running game.
# ---------------------------------------------------------------------------
@dataclass
class Session:
    session_id: str
    idx: int = FULL_OPEN_IDX
    u: int = 0
    total: int = 0
    turn: int = 1
    dice: list = field(default_factory=list)
    rerolls_remaining: int = 2
    game_over: bool = False
    moves_total: int = 0
    moves_optimal: int = 0
    ev_lost_total: float = 0.0
    filled: dict = field(default_factory=dict)  # category name -> points scored there

    def start_turn(self):
        """Reset for a new turn, awaiting an explicit first roll (dice stays
        empty until the player clicks Roll -- no auto-roll)."""
        self.dice = []
        self.rerolls_remaining = 2

    def apply_first_roll(self):
        self.dice = sorted(roll_dice(5))

    def record_move(self, ev_cost: float, optimal: bool):
        self.moves_total += 1
        self.ev_lost_total += ev_cost
        if optimal:
            self.moves_optimal += 1

    def open_categories(self):
        return [CATEGORY_NAMES[c] for c in np.flatnonzero(GAME_STATES[self.idx])]

    def accuracy(self):
        if self.moves_total == 0:
            return 1.0
        return self.moves_optimal / self.moves_total

    def dice_category_preview(self):
        """What each still-open category would score with the current dice."""
        if not self.dice:
            return {}
        d_idx = dice_to_dice_idx(self.dice)
        return {
            CATEGORY_NAMES[c]: int(SCORE_ARRAY[d_idx, c])
            for c in np.flatnonzero(GAME_STATES[self.idx])
        }

    def public_state(self):
        return {
            "session_id": self.session_id,
            "turn": self.turn,
            "turns_left": int(GAME_STATES[self.idx].sum()),
            "u": self.u,
            "total": self.total,
            "dice": self.dice,
            "rerolls_remaining": self.rerolls_remaining,
            "open_categories": self.open_categories(),
            "filled": self.filled,
            "dice_category_preview": self.dice_category_preview(),
            "game_over": self.game_over,
            "moves_total": self.moves_total,
            "moves_optimal": self.moves_optimal,
            "accuracy": self.accuracy(),
            "ev_lost_total": self.ev_lost_total,
            "optimal_expected_score": OPTIMAL_EXPECTED_SCORE,
        }


SESSIONS: dict[str, Session] = {}


def new_session() -> Session:
    sid = uuid.uuid4().hex
    s = Session(session_id=sid)
    s.start_turn()
    SESSIONS[sid] = s
    return s


def get_session(session_id: str) -> Session:
    if session_id not in SESSIONS:
        raise KeyError(session_id)
    return SESSIONS[session_id]
