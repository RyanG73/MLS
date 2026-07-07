"""
Contract tests for data_pipeline/espn_fixtures.py.

Network-free: all tests use synthetic event dicts or pure unit functions.
Live-fetch coverage is provided by the CLI smoke run, not here.
"""
import numpy as np
import pandas as pd
import pytest

from data_pipeline.espn_fixtures import (
    ESPN_TO_UNDERSTAT,
    SLUGS,
    _parse_events,
    _to_understat,
    european_fixtures,
)
from data_pipeline.understat import _COLS


# ── _to_understat ─────────────────────────────────────────────────────────────

def test_to_understat_known_mismatch_epl():
    """ESPN 'AFC Bournemouth' → Understat 'Bournemouth'."""
    assert _to_understat("epl", "AFC Bournemouth") == "Bournemouth"


def test_to_understat_known_mismatch_serie_a():
    """ESPN 'Internazionale' → Understat 'Inter'."""
    assert _to_understat("serie-a", "Internazionale") == "Inter"


def test_to_understat_known_mismatch_ligue1():
    """ESPN 'Paris Saint-Germain' → Understat 'Paris Saint Germain'."""
    assert _to_understat("ligue-1", "Paris Saint-Germain") == "Paris Saint Germain"


def test_to_understat_passthrough_unmapped():
    """Names that already match Understat pass through unchanged."""
    assert _to_understat("epl", "Arsenal") == "Arsenal"
    assert _to_understat("epl", "Liverpool") == "Liverpool"


def test_to_understat_promoted_team_passthrough():
    """Promoted teams not in the map return their ESPN name unchanged."""
    assert _to_understat("epl", "Coventry City") == "Coventry City"


def test_to_understat_unknown_league():
    """Unknown league id returns the name unchanged (no KeyError)."""
    assert _to_understat("unknown-league", "Some Team FC") == "Some Team FC"


# ── _parse_events ──────────────────────────────────────────────────────────────

def _make_event(home: str, away: str, completed: bool,
                home_score: str = "2", away_score: str = "1") -> dict:
    """Build a minimal ESPN event dict matching the API shape."""
    return {
        "date": "2026-08-16T15:00:00Z",
        "competitions": [{
            "status": {"type": {"completed": completed}},
            "competitors": [
                {"homeAway": "home", "team": {"displayName": home},
                 "score": home_score if completed else None},
                {"homeAway": "away", "team": {"displayName": away},
                 "score": away_score if completed else None},
            ],
        }],
    }


def test_parse_events_completed_sets_is_result_and_goals():
    events = [_make_event("Arsenal", "Chelsea", completed=True,
                          home_score="3", away_score="1")]
    rows = _parse_events(events, "epl", 2026)
    assert len(rows) == 1
    r = rows[0]
    assert r["is_result"] is True
    assert r["home_goals"] == 3.0
    assert r["away_goals"] == 1.0
    assert r["label_result"] == 0.0   # home win


def test_parse_events_scheduled_sets_nan_goals():
    events = [_make_event("Liverpool", "Manchester City", completed=False)]
    rows = _parse_events(events, "epl", 2026)
    assert len(rows) == 1
    r = rows[0]
    assert r["is_result"] is False
    assert np.isnan(r["home_goals"])
    assert np.isnan(r["away_goals"])
    assert np.isnan(r["label_result"])


def test_parse_events_label_result_draw():
    events = [_make_event("Everton", "Fulham", completed=True,
                          home_score="1", away_score="1")]
    rows = _parse_events(events, "epl", 2026)
    assert rows[0]["label_result"] == 1.0   # draw


def test_parse_events_label_result_away_win():
    events = [_make_event("Everton", "Arsenal", completed=True,
                          home_score="0", away_score="2")]
    rows = _parse_events(events, "epl", 2026)
    assert rows[0]["label_result"] == 2.0   # away win


def test_parse_events_applies_name_mapping():
    """ESPN 'AFC Bournemouth' is mapped to Understat 'Bournemouth'."""
    events = [_make_event("AFC Bournemouth", "Brentford", completed=False)]
    rows = _parse_events(events, "epl", 2026)
    assert rows[0]["home_team"] == "Bournemouth"
    assert rows[0]["away_team"] == "Brentford"


def test_parse_events_xg_always_nan():
    """The ESPN adapter never populates xG — it is always NaN."""
    events = [_make_event("Arsenal", "Chelsea", completed=True)]
    rows = _parse_events(events, "epl", 2026)
    assert np.isnan(rows[0]["home_xg"])
    assert np.isnan(rows[0]["away_xg"])


def test_parse_events_is_playoff_zero():
    events = [_make_event("Arsenal", "Chelsea", completed=False)]
    rows = _parse_events(events, "epl", 2026)
    assert rows[0]["is_playoff"] == 0


def test_parse_events_skips_missing_competitors():
    bad = {"date": "2026-08-16T15:00:00Z",
           "competitions": [{"status": {"type": {"completed": False}},
                              "competitors": []}]}
    rows = _parse_events([bad], "epl", 2026)
    assert rows == []


# ── european_fixtures schema ───────────────────────────────────────────────────

def test_european_fixtures_schema(tmp_path, monkeypatch):
    """european_fixtures() returns all canonical columns (network-free via monkeypatch)."""
    import data_pipeline.espn_fixtures as mod

    # Monkeypatch _fetch_events to return two synthetic events.
    def fake_fetch(slug, season, calendar_year=False):
        return [
            _make_event("Arsenal", "Chelsea", completed=False),
            _make_event("Liverpool", "Everton", completed=True,
                        home_score="2", away_score="0"),
        ]

    monkeypatch.setattr(mod, "_fetch_events", fake_fetch)
    # Redirect cache to tmp_path so we don't pollute the real cache.
    monkeypatch.setattr(mod, "_CACHE_DIR", tmp_path)

    df = european_fixtures("epl", 2026, use_cache=False)

    assert list(df.columns) == _COLS, f"Column mismatch: {list(df.columns)}"
    assert len(df) == 2
    # Scheduled row
    scheduled = df[~df["is_result"]]
    assert len(scheduled) == 1
    assert np.isnan(scheduled.iloc[0]["home_goals"])
    assert np.isnan(scheduled.iloc[0]["label_result"])
    # Played row
    played = df[df["is_result"]]
    assert len(played) == 1
    assert played.iloc[0]["home_goals"] == 2.0
    assert played.iloc[0]["label_result"] == 0.0   # home win


def test_european_fixtures_cache_roundtrip(tmp_path, monkeypatch):
    """Parquet cache is written on first call and read back correctly."""
    import data_pipeline.espn_fixtures as mod

    call_count = {"n": 0}

    def fake_fetch(slug, season, calendar_year=False):
        call_count["n"] += 1
        return [_make_event("Arsenal", "Chelsea", completed=False)]

    monkeypatch.setattr(mod, "_fetch_events", fake_fetch)
    monkeypatch.setattr(mod, "_CACHE_DIR", tmp_path)

    # First call — fetches and caches.
    df1 = european_fixtures("epl", 2026, use_cache=False)
    # Second call — reads from cache (fetch should NOT be called again).
    df2 = european_fixtures("epl", 2026, use_cache=True)

    assert call_count["n"] == 1, "Expected exactly one live fetch; cache was bypassed."
    pd.testing.assert_frame_equal(df1.reset_index(drop=True),
                                  df2.reset_index(drop=True))


def test_european_fixtures_unknown_league():
    with pytest.raises(ValueError, match="Unknown league"):
        european_fixtures("mls", 2026)


# ── SLUGS and ESPN_TO_UNDERSTAT sanity ────────────────────────────────────────

def test_slugs_covers_all_big5():
    # big-5 preseason fixtures + the C2 ASA leagues (mid-season remainder)
    assert set(SLUGS) == {"epl", "la-liga", "serie-a", "bundesliga", "ligue-1",
                          "nwsl", "usl-championship"}


def test_espn_to_understat_no_identity_entries():
    """Map entries where ESPN name == Understat name are redundant noise."""
    for league, mapping in ESPN_TO_UNDERSTAT.items():
        for espn, us in mapping.items():
            assert espn != us, (
                f"{league}: identity entry '{espn}' → '{us}' is redundant "
                f"and should be removed from ESPN_TO_UNDERSTAT."
            )
