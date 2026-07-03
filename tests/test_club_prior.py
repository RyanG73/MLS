import pandas as pd

from scripts.eval.club_prior import club_prior_gap, elo_history_from_matches


def _history():
    """Tidy per-team-season ELO history.

    Team X: averaged 1600 over the 3 prior seasons, seeds 2026 at 1440 → gap 160.
    Team Y: only 1 prior season → gap 0 (promoted teams stay with the tier bridge).
    Team Z: overachiever — prior mean 1450, seeds at 1520 → gap −70.
    """
    return pd.DataFrame([
        {"team": "X", "season": 2023, "seed_elo": 1590, "end_elo": 1610},
        {"team": "X", "season": 2024, "seed_elo": 1595, "end_elo": 1600},
        {"team": "X", "season": 2025, "seed_elo": 1580, "end_elo": 1590},
        {"team": "X", "season": 2026, "seed_elo": 1440, "end_elo": 1445},
        {"team": "Y", "season": 2025, "seed_elo": 1500, "end_elo": 1530},
        {"team": "Y", "season": 2026, "seed_elo": 1512, "end_elo": 1520},
        {"team": "Z", "season": 2024, "seed_elo": 1440, "end_elo": 1445},
        {"team": "Z", "season": 2025, "seed_elo": 1448, "end_elo": 1455},
        {"team": "Z", "season": 2026, "seed_elo": 1520, "end_elo": 1525},
    ])


def test_fallen_giant_gap():
    gaps = club_prior_gap(_history())
    assert gaps[("X", 2026)] == 160.0


def test_fewer_than_two_prior_seasons_gap_zero():
    gaps = club_prior_gap(_history())
    assert gaps[("Y", 2026)] == 0.0
    # first-ever season for every team is also 0
    assert gaps[("X", 2023)] == 0.0


def test_overachiever_negative_gap():
    gaps = club_prior_gap(_history())
    assert gaps[("Z", 2026)] == -70.0


def test_elo_history_from_matches():
    df = pd.DataFrame({
        "date": pd.to_datetime([
            "2025-03-01", "2025-10-01", "2026-03-01", "2026-10-01"]),
        "season": [2025, 2025, 2026, 2026],
        "home_team": ["A", "B", "A", "B"],
        "away_team": ["B", "A", "B", "A"],
        "home_elo": [1500.0, 1495.0, 1512.0, 1490.0],
        "away_elo": [1500.0, 1510.0, 1488.0, 1515.0],
    })
    hist = elo_history_from_matches(df)
    a = hist[(hist["team"] == "A") & (hist["season"] == 2025)].iloc[0]
    assert a["seed_elo"] == 1500.0    # first pre-match value of the season
    assert a["end_elo"] == 1510.0     # last pre-match value of the season
    b = hist[(hist["team"] == "B") & (hist["season"] == 2026)].iloc[0]
    assert b["seed_elo"] == 1488.0
    assert b["end_elo"] == 1490.0
