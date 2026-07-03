import pandas as pd
import pytest
from scripts.eval.upcoming_features import latest_team_features, build_upcoming_row

FEAT = ["h_elo", "a_elo", "h_xg_form_5", "a_xg_form_5"]

def _frame():
    return pd.DataFrame({
        "date": pd.to_datetime(["2026-03-01", "2026-03-08", "2026-03-15"]),
        "season": 2026,
        "home_team": ["A", "B", "A"], "away_team": ["B", "C", "C"],
        "home_goals": [1, 0, 2], "away_goals": [0, 0, 1],
        "h_elo": [1500.0, 1480.0, 1512.0], "a_elo": [1490.0, 1505.0, 1470.0],
        "h_xg_form_5": [1.1, 0.9, 1.3], "a_xg_form_5": [1.0, 1.2, 0.8],
    })

def test_latest_values_prefer_most_recent_match_and_side():
    tf = latest_team_features(_frame(), FEAT)
    # A last appeared 03-15 as HOME → take h_* values
    assert tf["A"]["elo"] == 1512.0 and tf["A"]["xg_form_5"] == 1.3
    # B last appeared 03-08 as HOME
    assert tf["B"]["elo"] == 1480.0
    # C last appeared 03-15 as AWAY → take a_* values
    assert tf["C"]["elo"] == 1470.0 and tf["C"]["xg_form_5"] == 0.8

def test_build_upcoming_row_maps_sides():
    tf = latest_team_features(_frame(), FEAT)
    row = build_upcoming_row("B", "C", tf, FEAT)
    assert row["h_elo"] == 1480.0 and row["a_elo"] == 1470.0

def test_unseen_team_returns_none_values():
    tf = latest_team_features(_frame(), FEAT)
    row = build_upcoming_row("B", "ZZZ", tf, FEAT)
    assert row["a_elo"] is None   # caller decides DC-fallback


def test_champion_prefixes_and_derived_columns():
    """The real frame uses home_/away_ prefixes + derived diff columns."""
    frame = pd.DataFrame({
        "date": pd.to_datetime(["2026-03-01", "2026-03-08"]),
        "season": 2026,
        "home_team": ["A", "B"], "away_team": ["B", "A"],
        "home_goals": [1, 0], "away_goals": [0, 2],
        "home_elo": [1500.0, 1480.0], "away_elo": [1490.0, 1512.0],
        "home_xg_roll_3": [1.2, 0.9], "away_xg_roll_3": [1.0, 1.4],
    })
    feat = ["home_elo", "away_elo", "elo_diff",
            "home_xg_roll_3", "away_xg_roll_3", "xg_diff", "home_xg_sum",
            "is_playoff"]
    from scripts.eval.upcoming_features import build_upcoming_features
    up = build_upcoming_features(frame, [("A", "B")], feat, 2026)
    r = up.iloc[0]
    # A last seen 03-08 AWAY (elo 1512, xg 1.4); B last seen 03-08 HOME (1480, 0.9)
    assert r["home_elo"] == 1512.0 and r["away_elo"] == 1480.0
    assert r["elo_diff"] == 32.0                       # recomputed, not None
    assert r["xg_diff"] == pytest.approx(0.5)
    assert r["home_xg_sum"] == pytest.approx(2.3)
    assert r["is_playoff"] == 0.0
    assert r["match_id"] == "up_0" and r["season"] == 2026
