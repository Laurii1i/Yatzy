"""Scratch verification script: play many full games, once optimally and once
randomly, and check that judge_hold/judge_fill report the expected accuracy.
Not part of the shipped app.
"""
import random
import numpy as np
import game_engine as ge


def play_optimally(seed):
    random.seed(seed)
    idx, u, total = ge.FULL_OPEN_IDX, 0, 0
    moves_total = 0
    moves_optimal = 0
    while True:
        state = ge.solve_state(idx)
        dice = sorted(ge.roll_dice(5))
        for rerolls_remaining in (2, 1):
            d_idx = ge.dice_to_dice_idx(dice)
            H = state.H2 if rerolls_remaining == 2 else state.H1
            legal_mask = ge.POSSIBLE_HOLDS_BOOL[d_idx]
            values = np.where(legal_mask, H[:, u], -np.inf)
            best_hold_idx = int(values.argmax())
            keep_values = ge.hold_state_to_dice(best_hold_idx)
            # translate multiset of kept values into indices into `dice`
            pool = list(dice)
            keep_indices = []
            for v in keep_values:
                pos = next(i for i, x in enumerate(pool) if x == v and i not in keep_indices)
                keep_indices.append(pos)
            result = ge.judge_hold(state, dice, u, rerolls_remaining, keep_indices)
            moves_total += 1
            if result["optimal"]:
                moves_optimal += 1
            else:
                print("  suboptimal hold?!", result)
            kept = [dice[i] for i in keep_indices]
            n_reroll = 5 - len(kept)
            dice = sorted(kept + ge.roll_dice(n_reroll))

        d_idx = ge.dice_to_dice_idx(dice)
        best_col = int(state.optimal_fill_field[d_idx, u])
        result = ge.judge_fill(state, dice, u, best_col)
        moves_total += 1
        if result["optimal"]:
            moves_optimal += 1
        else:
            print("  suboptimal fill?!", result)
        total += result["gain"] + result["bonus"]
        u = result["new_u"]
        idx = result["new_idx"]
        if ge.GAME_STATES[idx].sum() == 0:
            break
    return total, moves_total, moves_optimal


def play_randomly(seed):
    random.seed(seed)
    idx, u, total = ge.FULL_OPEN_IDX, 0, 0
    moves_total = 0
    moves_optimal = 0
    while True:
        state = ge.solve_state(idx)
        dice = sorted(ge.roll_dice(5))
        for rerolls_remaining in (2, 1):
            k = random.randint(0, 5)
            keep_indices = sorted(random.sample(range(5), k))
            result = ge.judge_hold(state, dice, u, rerolls_remaining, keep_indices)
            moves_total += 1
            if result["optimal"]:
                moves_optimal += 1
            kept = [dice[i] for i in keep_indices]
            n_reroll = 5 - len(kept)
            dice = sorted(kept + ge.roll_dice(n_reroll))

        open_cols = list(state.open_cols)
        c = random.choice(open_cols)
        result = ge.judge_fill(state, dice, u, int(c))
        moves_total += 1
        if result["optimal"]:
            moves_optimal += 1
        total += result["gain"] + result["bonus"]
        u = result["new_u"]
        idx = result["new_idx"]
        if ge.GAME_STATES[idx].sum() == 0:
            break
    return total, moves_total, moves_optimal


print(f"OPTIMAL_EXPECTED_SCORE = {ge.OPTIMAL_EXPECTED_SCORE:.4f}")

print("\n--- optimal playthroughs ---")
scores = []
tot_moves = tot_opt = 0
for seed in range(20):
    score, mt, mo = play_optimally(seed)
    scores.append(score)
    tot_moves += mt
    tot_opt += mo
print(f"games=20 mean_score={np.mean(scores):.2f} accuracy={tot_opt/tot_moves:.4%} ({tot_opt}/{tot_moves})")

print("\n--- random playthroughs (sanity: accuracy should be well below 100%) ---")
scores = []
tot_moves = tot_opt = 0
for seed in range(20):
    score, mt, mo = play_randomly(seed)
    scores.append(score)
    tot_moves += mt
    tot_opt += mo
print(f"games=20 mean_score={np.mean(scores):.2f} accuracy={tot_opt/tot_moves:.4%} ({tot_opt}/{tot_moves})")
