import numpy as np
import pandas as pd

from scripts.eval.season_format import format_classification, regular_phase_mask


def _mini_season(results):
    """results: list of (home, away, hg, ag) in chronological order."""
    return pd.DataFrame([
        {"date": pd.Timestamp("2025-08-01") + pd.Timedelta(days=i),
         "home_team": h, "away_team": a, "home_goals": hg, "away_goals": ag}
        for i, (h, a, hg, ag) in enumerate(results)
    ])


def test_regular_phase_mask_splits_on_per_team_game_count():
    # 3 teams, single round-robin (rr=1 → 2 games each), then 1 extra game.
    df = _mini_season([
        ("A", "B", 1, 0), ("B", "C", 1, 0), ("C", "A", 1, 0),  # regular
        ("A", "B", 0, 0),                                      # post-season
    ])
    mask = regular_phase_mask(df, regular_games=2)
    assert mask.tolist() == [True, True, True, False]


def test_belgian_halving_rounds_up_and_groups_dominate():
    # 4 teams, top-2 championship group with halved carry-in.
    # Regular (rr=1, 3 games each): A 9pts, B 6, C 3, D 0.
    df = _mini_season([
        ("A", "B", 1, 0), ("C", "D", 1, 0),
        ("A", "C", 1, 0), ("B", "D", 1, 0),
        ("A", "D", 1, 0), ("B", "C", 1, 0),
        # playoff (top 2 = A, B): A enters ceil(9/2)=5, B enters 3.
        # B beats A twice → B 3+6=9 > A 5.
        ("A", "B", 0, 1), ("B", "A", 1, 0),
    ])
    fmt = {"rr": 1, "groups": [2], "carry": "half"}
    cls = format_classification(df, fmt, teams=["A", "B", "C", "D"])
    assert cls["B"]["group"] == 0 and cls["A"]["group"] == 0
    assert cls["B"]["pts"] == 9 and cls["A"]["pts"] == 5
    assert cls["C"]["group"] == 1 and cls["D"]["group"] == 1
    # official order: playoff group first (B, A), then the rest (C, D)
    order = sorted(cls, key=lambda t: (cls[t]["group"], -cls[t]["pts"]))
    assert order == ["B", "A", "C", "D"]


def test_scottish_split_constrains_bottom_team_below_line():
    # 4 teams, top-2 split, FULL carry. Regular: A 9, B 6, C 3, D 0.
    # Post-split C wins big but must stay in the bottom group (rank ≥ 3).
    df = _mini_season([
        ("A", "B", 1, 0), ("C", "D", 1, 0),
        ("A", "C", 1, 0), ("B", "D", 1, 0),
        ("A", "D", 1, 0), ("B", "C", 1, 0),
        # split round: within-half pairings only
        ("B", "A", 1, 0),      # B 9, A 9
        ("C", "D", 5, 0),      # C 6
    ])
    fmt = {"rr": 1, "groups": [2], "carry": "full"}
    cls = format_classification(df, fmt, teams=["A", "B", "C", "D"])
    assert cls["C"]["pts"] == 6
    assert cls["C"]["group"] == 1          # more pts than nobody in top half, but even
    assert cls["A"]["group"] == 0 and cls["B"]["group"] == 0


def test_pools_inferred_from_post_phase_pairings():
    # 6 teams, regular single RR; post phase = two pools of 2 that DON'T match
    # the naive table cut (C and D swapped by an unmodelled tie-break). The
    # pairing graph is ground truth: whoever actually played in the top pool
    # classifies there.
    regular = []
    teams = ["A", "B", "C", "D", "E", "F"]
    for i, h in enumerate(teams):
        for a in teams[i + 1:]:
            regular.append((h, a, 1, 0))   # earlier alphabet always wins
    df = _mini_season(regular + [
        ("A", "D", 1, 0), ("D", "A", 1, 0),    # top pool: A + D (not C!)
        ("B", "C", 1, 0), ("C", "B", 1, 0),
        ("E", "F", 1, 0), ("F", "E", 1, 0),
    ])
    fmt = {"rr": 1, "groups": [2, 2], "carry": "full"}
    cls = format_classification(df, fmt, teams=teams)
    assert cls["A"]["group"] == 0 and cls["D"]["group"] == 0
    assert cls["B"]["group"] == 1 and cls["C"]["group"] == 1
    assert cls["E"]["group"] == 2 and cls["F"]["group"] == 2


def test_no_post_season_rows_keeps_regular_table():
    df = _mini_season([
        ("A", "B", 2, 0), ("B", "A", 0, 0),
    ])
    fmt = {"rr": 1, "groups": [1], "carry": "full"}
    cls = format_classification(df, fmt, teams=["A", "B"])
    assert cls["A"]["pts"] == 4 and cls["B"]["pts"] == 1
    assert cls["A"]["group"] == 0 and cls["B"]["group"] == 1
