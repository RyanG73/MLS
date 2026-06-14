"""
Contract tests for the Understat adapter (data_pipeline/understat.py).

Network-free: they exercise the pure parse/coerce/name-mapping functions with
synthetic match dicts shaped like understatapi output, locking the canonical
schema the league-agnostic model depends on (the same schema the MLS ASA path
produces). The live fetch path is covered by the CLI smoke run, not here.
"""

import numpy as np
import pandas as pd

from data_pipeline.understat import (
    _COLS, _coerce, _default_seasons, _parse_season, espn_name,
)


def _match(mid, h, a, hg, ag, hxg, axg, played=True):
    """A raw Understat-shaped match dict."""
    return {
        "id": mid, "isResult": played,
        "h": {"id": "1", "title": h}, "a": {"id": "2", "title": a},
        "goals": {"h": str(hg), "a": str(ag)} if played else {"h": None, "a": None},
        "xG": {"h": str(hxg), "a": str(axg)},
        "datetime": "2023-08-11 19:00:00",
    }


def test_parse_season_schema_and_labels():
    rows = [
        _match("1", "Burnley", "Man City", 0, 3, 0.31, 2.40),   # away win → 2
        _match("2", "Arsenal", "Chelsea", 2, 0, 1.8, 0.6),      # home win → 0
        _match("3", "Everton", "Fulham", 1, 1, 1.1, 1.0),       # draw     → 1
    ]
    df = _parse_season(rows, 2023)
    assert list(df.columns) == _COLS
    assert df["label_result"].tolist() == [2.0, 0.0, 1.0]
    assert (df["season"] == 2023).all()
    assert (df["is_playoff"] == 0).all()
    assert df["is_result"].all()
    # xG parsed from strings to float
    assert abs(df.loc[0, "away_xg"] - 2.40) < 1e-9


def test_parse_season_unplayed_is_nan():
    df = _parse_season([_match("9", "A", "B", 0, 0, 1.0, 0.5, played=False)], 2025)
    assert df["is_result"].iloc[0] == False  # noqa: E712 (numpy bool)
    assert np.isnan(df["home_goals"].iloc[0])
    assert np.isnan(df["label_result"].iloc[0])
    # xG can still be present for an unplayed fixture (Understat forecasts it)
    assert df["home_xg"].iloc[0] == 1.0


def test_coerce_pins_dtypes():
    raw = pd.DataFrame([{
        "match_id": 5, "date": "2023-08-11 19:00:00", "season": "2023",
        "home_team": "A", "away_team": "B", "home_goals": "1", "away_goals": "0",
        "home_xg": "1.2", "away_xg": "0.4", "label_result": "0",
        "is_result": 1, "is_playoff": "0",
    }])
    df = _coerce(raw)
    assert df["is_result"].dtype == bool
    assert df["is_result"].iloc[0] is np.True_ or bool(df["is_result"].iloc[0])
    # The int-poisoning bug: ~is_result must flip a bool, not compute ~1 == -2.
    assert int((~df["is_result"]).sum()) == 0
    assert str(df["season"].dtype) == "int64"
    assert df["match_id"].iloc[0] == "5"


def test_coerce_empty_returns_canonical_columns():
    df = _coerce(pd.DataFrame())
    assert list(df.columns) == _COLS
    assert df.empty


def test_espn_name_overrides_and_passthrough():
    assert espn_name("epl", "Tottenham") == "Tottenham Hotspur"
    assert espn_name("serie-a", "Inter") == "Internazionale"
    assert espn_name("bundesliga", "Wolfsburg") == "VfL Wolfsburg"
    assert espn_name("la-liga", "Atletico Madrid") == "Atlético Madrid"
    # An already-matching title passes through unchanged
    assert espn_name("epl", "Arsenal") == "Arsenal"
    # Unknown league → identity
    assert espn_name("unknown", "Whoever") == "Whoever"


def test_default_seasons_starts_2014_and_is_sorted():
    s = _default_seasons()
    assert s[0] == 2014
    assert s == sorted(s)
    assert all(isinstance(y, int) for y in s)
