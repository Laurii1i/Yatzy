def scores_three_of_a_kind(dices):

    highest_points = 0

    for value, count in enumerate(dices, start=1):
        if count >= 3:
            highest_points = 3 * value

    return highest_points

def scores_four_of_a_kind(dices):

    highest_points = 0

    for value, count in enumerate(dices, start=1):
        if count >= 4:
            highest_points = 4 * value

    return highest_points

def scores_yatzee(dices):

    for count in dices:
        if count == 5:
            return   50

    return   0

def scores_lower_straight(dices):
    if tuple(dices) == (1, 1, 1, 1, 1, 0):
        return   15
    return   0

def scores_upper_straight(dices):
    if tuple(dices) == (0, 1, 1, 1, 1, 1):
        return   20
    return   0

def scores_full_house(dices):
    if 2 in dices and 3 in dices:

        return   2 * (dices.index(2) + 1) + 3 * (dices.index(3) + 1)
    return   0

def scores_two_of_a_kind(dices):

    highest_points = 0

    for value, count in enumerate(dices, start=1):
        if count >= 2:
            highest_points = 2 * value

    return highest_points

def scores_two_pairs(dices):

    pairs = [value for value, count in enumerate(dices, start=1) if count >= 2]

    if len(pairs) >= 2:
        return   sum([2 * pair for pair in pairs])

    return 0

def scores_upper(dices, face):

    return face * dices[face - 1] 

def scores_chance(dices):

    return sum((i + 1) * c for i, c in enumerate(dices))