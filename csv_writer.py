import csv
import numpy as np
def write_game_registry_csv(game_registry, path="game_values.csv"):
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["game_state", "expected_value_remaining"])
        for (game_state, turns_left), ev in game_registry.items():
            writer.writerow([game_state, repr(float(ev))])
    return path
def save_game_values(game_states, game_state_v, path="game_values.csv"):
    n_cat = game_states.shape[1]        # 15
    n_u   = game_state_v.shape[1]       # 64
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow([f"cat_{j}" for j in range(n_cat)] + [f"u_{u}" for u in range(n_u)])
        for state, vrow in zip(game_states, game_state_v):
            w.writerow([*state.tolist()] + [repr(float(x)) for x in vrow])
    return path

def load_game_values(path="game_values.csv"):
    values = {}
    with open(path, newline="") as f:
        r = csv.reader(f); header = next(r)
        n_cat = sum(1 for h in header if h.startswith("cat_"))
        for row in r:
            state = tuple(int(x) for x in row[:n_cat])
            values[state] = np.array([float(x) for x in row[n_cat:]], dtype=np.float64)
    return values

def load_game_state_V(path="game_values.csv"):
    """Reconstruct the (n_scorecards, n_u) value matrix, row-aligned to GAME_STATES."""
    rows = []
    with open(path, newline="") as f:
        r = csv.reader(f); header = next(r)
        n_cat = sum(1 for h in header if h.startswith("cat_"))
        for line in r:
            rows.append([float(x) for x in line[n_cat:]])   # value columns only
    return np.array(rows, dtype=np.float64)