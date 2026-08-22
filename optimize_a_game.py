import random
import numpy as np
from math import factorial, prod
from fractions import Fraction
from itertools import combinations, product, combinations_with_replacement
from collections import Counter
from scoring import *
from precomputes3 import *
from csv_writer import load_game_state_V

GAME_STATE_V = load_game_state_V()

def solve_optimal_play(idx):

    transitions = np.array(GAME_STATE_TRANSITIONS[idx]).astype(int)
    open_cols = np.flatnonzero(GAME_STATES[idx]) 
    GAME_TRANSITION_V = np.zeros((len(transitions), 64))

    for i, transition_state in enumerate(transitions):

        V = GAME_STATE_V[transition_state, :]
        GAME_TRANSITION_V[i, :] = V


    for rolls_left in [0,1,2,3]:

        if rolls_left == 0:

            optimal_pick = np.zeros((252,64, len(transitions)))
            for i, (open_col, new_state) in enumerate(zip(open_cols, transitions)):

                dv = GAME_STATE_V[new_state]
                if open_col < 6:
                    cand = SCORE_ARRAY[:, open_col][:, None] + BONUS[open_col] + dv[U_NEXT[open_col]]
                else:
                    cand = SCORE_ARRAY[:, open_col][:, None] + dv[None, :]

                optimal_pick[:,:,i] = cand

            final_Vs = np.max(optimal_pick, axis = 2)
            optimal_fill_field = open_cols[np.argmax(optimal_pick, axis=2)]

        elif rolls_left == 1:

            hold_expected_values = HOLD_TRANSITIONS @ final_Vs
            state_hold_values = np.where(POSSIBLE_HOLDS[:, :, None],                     # (252, 462, 1)
                  hold_expected_values[None, :, :],               # (1, 462, 64)
                  -np.inf) 
            
            Vs = np.max(state_hold_values, axis = 1)
if __name__ == '__main__':

    optimal_play = solve_optimal_play(32767)