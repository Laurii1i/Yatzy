import numpy as np
from math import factorial, prod
from itertools import combinations_with_replacement
from itertools import product
from collections import defaultdict

def _upper(d, face):      return d[face-1] * face
def _two_of_a_kind(d):    return max([2*v for v,c in enumerate(d,1) if c>=2], default=0)
def _three_of_a_kind(d):  return max([3*v for v,c in enumerate(d,1) if c>=3], default=0)
def _four_of_a_kind(d):   return max([4*v for v,c in enumerate(d,1) if c>=4], default=0)
def _two_pairs(d):
    pairs = [v for v,c in enumerate(d,1) if c>=2]
    return sum(2*p for p in pairs) if len(pairs) >= 2 else 0
def _lower_straight(d):   return 15 if tuple(d)==(1,1,1,1,1,0) else 0
def _upper_straight(d):   return 20 if tuple(d)==(0,1,1,1,1,1) else 0
def _full_house(d):
    dd = tuple(d)
    return 2*(dd.index(2)+1) + 3*(dd.index(3)+1) if (2 in dd and 3 in dd) else 0
def _chance(d):           return sum((i+1)*c for i,c in enumerate(d))
def _yatzee(d):           return 50 if 5 in d else 0

CATEGORY_SCORERS = [
    lambda d: _upper(d,1), lambda d: _upper(d,2), lambda d: _upper(d,3),
    lambda d: _upper(d,4), lambda d: _upper(d,5), lambda d: _upper(d,6),
    _two_of_a_kind, _three_of_a_kind, _four_of_a_kind, _two_pairs,
    _lower_straight, _upper_straight, _full_house, _chance, _yatzee,
]

def build_score_array(five_dice_states):
    """(252, 15): row i = points state i scores in each of the 15 categories."""
    return np.array([[scorer(row) for scorer in CATEGORY_SCORERS]
                     for row in five_dice_states], dtype=np.int64)
def get_five_dice_states():
    """(252, 6): every result of 5 dice, as face-count vectors."""
    states = [[combo.count(f) for f in range(1, 7)]
              for combo in combinations_with_replacement(range(1, 7), 5)]
    return np.array(states, dtype=np.int64)

def get_hold_states():
    """(462, 6): every sub-multiset you can keep — 0 through 5 dice."""
    states = []
    for k in range(6):
        for combo in combinations_with_replacement(range(1, 7), k):
            states.append([combo.count(f) for f in range(1, 7)])
    return np.array(states, dtype=np.int64)

def build_hold_transitions(hold_states, five_dice_states):
    """(462, 252): [i,j] = P(reach five-dice state j | keep hold i, reroll the rest)."""
    five_idx = {tuple(row): j for j, row in enumerate(five_dice_states)}
    T = np.zeros((len(hold_states), 252), dtype=np.float64)
    for i, hold in enumerate(hold_states):
        m = 5 - int(hold.sum())
        total = 6 ** m
        for combo in combinations_with_replacement(range(1, 7), m):
            counts = np.array([combo.count(f) for f in range(1, 7)], dtype=np.int64)
            arrangements = factorial(m) // prod(factorial(int(c)) for c in counts)
            T[i, five_idx[tuple(hold + counts)]] = arrangements / total
    return T

def build_possible_holds(five_dice_states, hold_states):
    """(252, 462): [i,j] = 1 if hold j is keepable from five-dice state i, else 0."""
    le = five_dice_states[:, None, :] >= hold_states[None, :, :]   # (252,462,6) elementwise
    return le.all(axis=2).astype(np.int64)

def build_ini_roll_probas(five_dice_states):
    """(252,): element i = P(rolling five-dice state i) with 5 fair dice."""
    probs = np.array([factorial(5) // prod(factorial(int(c)) for c in row)
                      for row in five_dice_states], dtype=np.float64)
    return probs / 6**5


def build_game_states(n_categories=15):
    """(2**n, n): row i is a scorecard; a_ij = 1 if field j is open in state i, else 0.
       Sorted by turns_left ascending, so DP order = row order."""
    states = list(product((1, 0), repeat=n_categories))
    states.sort(key=sum)
    return np.array(states, dtype=np.int8)



def build_game_state_transitions(game_states):
    """{i: (rows reachable from state i by clearing exactly one open field)}."""
    row_of = {tuple(row): i for i, row in enumerate(GAME_STATES)}   # state vector -> row index
    transitions = {}
    for i, row in enumerate(game_states):
        succ = []
        for c in np.where(row == 1)[0]:        # each still-open field
            nxt = row.copy(); nxt[c] = 0       # fill category c
            succ.append(row_of[tuple(nxt)])
        transitions[i] = tuple(succ)
    return transitions

def build_turns_left_map(game_states):
    """{turns_left: (row indices whose scorecard has that many open fields)}."""
    buckets = defaultdict(list)
    for i, row in enumerate(game_states):
        buckets[int(row.sum())].append(i)
    return {t: tuple(rows) for t, rows in buckets.items()}

FIVE_DICE_STATES = get_five_dice_states()
HOLD_STATES = get_hold_states()
HOLD_TRANSITIONS = build_hold_transitions(HOLD_STATES, FIVE_DICE_STATES)
SCORE_ARRAY = build_score_array(FIVE_DICE_STATES)
POSSIBLE_HOLDS = build_possible_holds(FIVE_DICE_STATES, HOLD_STATES)
INI_ROLLS_PROBAS = build_ini_roll_probas(FIVE_DICE_STATES)
GAME_STATES = build_game_states(15)
GAME_STATE_TURNS_LEFT = build_turns_left_map(GAME_STATES)
GAME_STATE_TRANSITIONS = build_game_state_transitions(GAME_STATES)
GAME_STATE_V = np.zeros((len(GAME_STATES), 64), dtype=np.float64)

UPPER_GAIN = SCORE_ARRAY[:, np.array([0, 1, 2, 3, 4, 5])]                  # (252, 6): upper score per dice state per face

u = np.arange(64)
U_NEXT = np.empty((6, 252, 64), dtype=np.int64)          # allocate first
BONUS  = np.empty((6, 252, 64), dtype=np.float64)        # allocate first
for f in range(6):
    gain = UPPER_GAIN[:, f][:, None]                     # (252, 1)
    nxt  = np.minimum(u[None, :] + gain, 63)             # (252, 64)
    U_NEXT[f] = nxt
    BONUS[f]  = 50.0 * ((u[None, :] < 63) & (nxt >= 63))

CATEGORY_NAMES = [
    "ones", "twos", "threes", "fours", "fives", "sixes",
    "two_of_a_kind", "three_of_a_kind", "four_of_a_kind", "two_pairs",
    "lower_straight", "upper_straight", "full_house", "chance", "yatzee",
]

DICE_STATE_TO_IDX = {tuple(row): i for i, row in enumerate(FIVE_DICE_STATES)}

