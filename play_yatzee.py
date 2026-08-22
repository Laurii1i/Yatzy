import numpy as np, random
from precomputes3 import *          # ...CATEGORY_NAMES, DICE_STATE_TO_IDX, HOLD_STATES, GAME_STATES,
                                    #    GAME_STATE_TRANSITIONS, SCORE_ARRAY, GAME_STATE_V, ...
from solver import solve_optimal_play, GAME_STATE_V   # wherever solve_optimal_play lives

HOLD_TO_IDX = {tuple(h): i for i, h in enumerate(HOLD_STATES)}

def dice_to_idx(dice):   return DICE_STATE_TO_IDX[tuple(dice.count(f) for f in range(1, 7))]
def keep_to_hold_idx(k): return HOLD_TO_IDX[tuple(k.count(f) for f in range(1, 7))]
def hold_to_dice(h):     return " ".join(str(f) for f in range(1, 7) for _ in range(HOLD_STATES[h][f-1])) or "nothing"

def ask_keep(dice):
    while True:
        raw = input(f"  dice {sorted(dice)} — keep which values? (space-sep, 'all', 'none'): ").strip().lower()
        if raw in ("none", ""): return []
        if raw == "all":        return list(dice)
        try: kept = [int(x) for x in raw.split()]
        except ValueError: print("  ! e.g.  3 3 6"); continue
        pool = list(dice); ok = all((v in pool and not pool.remove(v)) or v in dice for v in [])  # placeholder
        pool = list(dice); ok = True
        for v in kept:
            if v in pool: pool.remove(v)
            else: ok = False; break
        if ok: return kept
        print(f"  ! keep only dice you have ({sorted(dice)})")

def ask_category(open_cols):
    while True:
        print("  open:", ", ".join(f"{c}={CATEGORY_NAMES[c]}" for c in open_cols))
        raw = input("  fill which category? (number or name): ").strip().lower()
        for c in open_cols:
            if raw == str(int(c)) or raw == CATEGORY_NAMES[c]: return int(c)
        print("  ! pick an open category")

def play_turn(idx, u, total):
    optimal_fill_field, optimal_holds = solve_optimal_play(idx)      # (252,64) , (252,64,3)
    open_cols   = np.flatnonzero(GAME_STATES[idx])
    transitions = np.asarray(GAME_STATE_TRANSITIONS[idx], dtype=int)
    dice = [random.randint(1, 6) for _ in range(5)]

    for rolls_left in (2, 1):
        d = dice_to_idx(dice)
        print(f"\n  roll (rerolls left: {rolls_left}):")
        kept = ask_keep(dice)
        player_h = keep_to_hold_idx(kept)
        opt_h    = int(optimal_holds[d, u, rolls_left])
        if player_h == opt_h:
            print("    ✓ optimal hold")
        else:
            print(f"    ✗ optimal was to keep [{hold_to_dice(opt_h)}]")
        dice = kept + [random.randint(1, 6) for _ in range(5 - len(kept))]

    d = dice_to_idx(dice)
    print(f"\n  final dice {sorted(dice)}:")
    c = ask_category(open_cols)
    opt_c = int(optimal_fill_field[d, u])
    if c == opt_c:
        print("    ✓ optimal fill")
    else:
        print(f"    ✗ optimal was {CATEGORY_NAMES[opt_c]}")

    gain = int(SCORE_ARRAY[d, c]); bonus = 0
    if c < 6:
        new_u = min(u + gain, 63)
        if u < 63 and new_u >= 63: bonus = 50; print("    ★ upper bonus +50!")
    else:
        new_u = u
    new_idx = int(transitions[int(np.flatnonzero(open_cols == c)[0])])
    total  += gain + bonus
    print(f"  scored {gain} in {CATEGORY_NAMES[c]}"
          + (f" (+{bonus})" if bonus else "") + f".  total {total}")
    return new_idx, new_u, total

def play_yatzy():
    idx, u, total = len(GAME_STATES) - 1, 0, 0
    print(f"New game.  optimal expected score: {GAME_STATE_V[idx, 0]:.2f}\n")
    t = 1
    while GAME_STATES[idx].sum() > 0:
        print(f"===== turn {t} — {int(GAME_STATES[idx].sum())} left, u={u} =====")
        idx, u, total = play_turn(idx, u, total); t += 1
    print(f"\n===== final score {total} (optimal EV {GAME_STATE_V[len(GAME_STATES)-1, 0]:.2f}) =====")

if __name__ == "__main__":
    play_yatzy()