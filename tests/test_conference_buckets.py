import numpy as np

from scripts.build_league_data import _per_conf_members


def test_third_overall_but_first_in_conference_qualifies():
    # 4 teams, 2 conferences, top-1 per conference qualifies.
    # key (higher = better): A=40, B=30, C=20, D=10
    # conferences: {A, B} east · {C, D} west
    # C is 3rd overall but 1st in west → qualifies; B (2nd overall) does not.
    key = np.array([40.0, 30.0, 20.0, 10.0])
    conf_arrays = [np.array([0, 1]), np.array([2, 3])]
    got = set(_per_conf_members(key, conf_arrays, 1))
    assert got == {0, 2}


def test_top_two_per_conference():
    key = np.array([40.0, 30.0, 20.0, 10.0, 5.0, 50.0])
    conf_arrays = [np.array([0, 1, 2]), np.array([3, 4, 5])]
    got = set(_per_conf_members(key, conf_arrays, 2))
    assert got == {0, 1, 5, 3}
