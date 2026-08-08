"""xG join — backfilled stat sheets onto the canonical frame. No network.

Spec: docs/superpowers/specs/2026-08-08-api-football-migration-execution-spec.md Stage 4.
The store is keyed by API-Football fixture id; canonical frames for
football-data-sourced leagues carry no such id, so the join goes through the
backfill's own fixture inventories: (af_id, season) -> fixtures -> team ids.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest


def _inventory(fixtures):
    return {"response": [
        {"fixture": {"id": fid, "status": {"short": "FT"}},
         "league": {"season": season},
         "teams": {"home": {"id": hid, "name": hname},
                   "away": {"id": aid, "name": aname}}}
        for fid, season, hid, hname, aid, aname in fixtures]}


def _sheet(pairs):
    """pairs: [(team_id, xg_value_or_None), ...]"""
    return {"response": [
        {"team": {"id": tid},
         "statistics": ([{"type": "Total Shots", "value": 10}]
                        + ([{"type": "expected_goals", "value": v}]
                           if v is not None or v is None else []))}
        for tid, v in pairs]}


@pytest.fixture
def store(tmp_path, monkeypatch):
    from data_pipeline import xg_store
    monkeypatch.setattr(xg_store, "STORE", tmp_path / "statistics")
    monkeypatch.setattr(xg_store, "FIXTURES_CACHE", tmp_path / "fixtures")
    monkeypatch.setattr(xg_store, "MAP_PATH", tmp_path / "map.json")
    (tmp_path / "statistics").mkdir()
    (tmp_path / "fixtures").mkdir()
    (tmp_path / "map.json").write_text(json.dumps({"championship": {"af_id": 40}}))
    (tmp_path / "fixtures" / "40_2024.json").write_text(json.dumps(_inventory([
        (101, 2024, 1, "Leeds", 2, "Burnley"),
        (102, 2024, 2, "Burnley", 1, "Leeds"),
        (103, 2024, 3, "Hull City", 1, "Leeds"),
    ])))
    (tmp_path / "statistics" / "101.json").write_text(
        json.dumps(_sheet([(1, "1.85"), (2, "0.42")])))
    (tmp_path / "statistics" / "102.json").write_text(       # null xG both sides
        json.dumps(_sheet([(2, None), (1, None)])))
    # 103 has no sheet at all
    xg_store._team_names.cache_clear()
    yield tmp_path
    xg_store._team_names.cache_clear()


def test_xg_rows_only_returns_matches_with_both_values(store):
    from data_pipeline import xg_store
    rows = xg_store.xg_rows("championship")
    assert len(rows) == 1
    r = rows[0]
    assert (r["season"], r["home_team"], r["away_team"]) == (2024, "Leeds", "Burnley")
    assert r["home_xg"] == pytest.approx(1.85)
    assert r["away_xg"] == pytest.approx(0.42)


def test_xg_is_assigned_by_team_id_not_sheet_order(store):
    """The stat sheet lists teams in its own order; assigning by position
    would silently swap home and away xG."""
    from data_pipeline import xg_store
    (store / "statistics" / "101.json").write_text(
        json.dumps(_sheet([(2, "0.42"), (1, "1.85")])))   # away side listed first
    r = xg_store.xg_rows("championship")[0]
    assert r["home_xg"] == pytest.approx(1.85)   # still Leeds (id 1, the home team)


def test_attach_xg_fills_frame_without_changing_rows(store):
    from data_pipeline import xg_store
    frame = pd.DataFrame({
        "season": [2024, 2024, 2024],
        "home_team": ["Leeds", "Burnley", "Hull City"],
        "away_team": ["Burnley", "Leeds", "Leeds"],
        "home_xg": [np.nan] * 3, "away_xg": [np.nan] * 3,
    })
    out = xg_store.attach_xg(frame, "championship")
    assert len(out) == 3
    assert out.loc[0, "home_xg"] == pytest.approx(1.85)
    assert pd.isna(out.loc[1, "home_xg"])        # null-xG match stays empty
    assert pd.isna(out.loc[2, "home_xg"])        # no sheet stays empty


def test_attach_xg_never_overwrites_existing_values(store):
    """understat/ASA leagues own their xG (Tier C). If a frame already carries
    a value, the spine must not clobber it."""
    from data_pipeline import xg_store
    frame = pd.DataFrame({
        "season": [2024], "home_team": ["Leeds"], "away_team": ["Burnley"],
        "home_xg": [9.99], "away_xg": [8.88]})
    out = xg_store.attach_xg(frame, "championship")
    assert out.loc[0, "home_xg"] == pytest.approx(9.99)


def test_attach_xg_maps_our_names_to_api_football_names(store, monkeypatch):
    """Frames carry OUR spellings; the inventory carries API-Football's, so the
    map runs ours -> theirs (the inverse of the adapter's own name map, which
    converts spine frames into our space)."""
    from data_pipeline import xg_store
    names = store / "names.json"
    names.write_text(json.dumps({"championship": {"Leeds United": "Leeds"}}))
    monkeypatch.setattr(xg_store, "NAMES_PATH", names)
    xg_store._team_names.cache_clear()
    frame = pd.DataFrame({
        "season": [2024], "home_team": ["Leeds United"], "away_team": ["Burnley"],
        "home_xg": [np.nan], "away_xg": [np.nan]})
    out = xg_store.attach_xg(frame, "championship")
    assert out.loc[0, "home_xg"] == pytest.approx(1.85)


def test_coverage_reports_usable_share(store):
    """Usable = both teams non-null. This is the number the feature campaign
    gates on; counting field presence overstated it 2x on 2026-08-08."""
    from data_pipeline import xg_store
    cov = xg_store.coverage("championship")
    assert cov["fixtures"] == 3
    assert cov["usable"] == 1
    assert cov["share"] == pytest.approx(1 / 3)


def test_unmapped_league_returns_nothing_rather_than_raising(store):
    from data_pipeline import xg_store
    assert xg_store.xg_rows("no-such-league") == []
