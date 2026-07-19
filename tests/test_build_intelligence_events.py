import datetime
import json

import pandas as pd

from scripts.build_intelligence_events import (
    _crossed_thresholds, _resolved_fixture_evidence, append_events,
    build_events, build_latest_index, compute_materiality_score,
)


def _hist_row(league, team, team_id, snapshot_date, season=2026, config_id="cfg-1",
              code_rev="rev1", n_played=5, **metrics):
    row = {"league": league, "team": team, "team_id": team_id, "snapshot_date": snapshot_date,
           "season": season, "config_id": config_id, "code_rev": code_rev, "n_played": n_played,
           "elo": 1500, "proj_pts": 50.0}
    for m in ("title", "playoff", "shield", "cup", "europa", "conf", "releg", "promo"):
        row.setdefault(m, None)
    row.update(metrics)
    return row


def test_crossed_thresholds_detects_upward_crossing():
    assert _crossed_thresholds(20.0, 30.0) == [25.0]


def test_crossed_thresholds_detects_downward_crossing():
    assert _crossed_thresholds(60.0, 40.0) == [50.0]


def test_crossed_thresholds_none_when_no_crossing():
    assert _crossed_thresholds(20.0, 22.0) == []


def test_crossed_thresholds_multiple():
    assert _crossed_thresholds(10.0, 80.0) == [25.0, 50.0, 75.0]


def test_materiality_score_scales_with_movement():
    small = compute_materiality_score(1.0, [], "refresh")
    large = compute_materiality_score(40.0, [], "refresh")
    assert small < large


def test_materiality_score_bonus_for_threshold_crossing():
    no_cross = compute_materiality_score(5.0, [], "refresh")
    with_cross = compute_materiality_score(5.0, [25.0], "refresh")
    assert with_cross > no_cross


def test_materiality_score_bonus_for_result_cause():
    no_result = compute_materiality_score(5.0, [], "model")
    is_result = compute_materiality_score(5.0, [], "result")
    assert is_result > no_result


def test_materiality_score_capped_at_one():
    score = compute_materiality_score(1000.0, [25.0, 50.0, 75.0], "result")
    assert score <= 1.0


def test_resolved_fixture_evidence_finds_disappeared_fixture():
    match_hist = pd.DataFrame([
        {"home_id": "TID_A", "away_id": "TID_B", "fixture_id": "v1:f1", "snapshot_date": "2026-07-17"},
        {"home_id": "TID_A", "away_id": "TID_C", "fixture_id": "v1:f2", "snapshot_date": "2026-07-18"},
    ])
    ev = _resolved_fixture_evidence(match_hist, "TID_A", "2026-07-17", "2026-07-18")
    assert ev == ["fixture:v1:f1"]


def test_resolved_fixture_evidence_empty_when_nothing_resolved():
    match_hist = pd.DataFrame([
        {"home_id": "TID_A", "away_id": "TID_B", "fixture_id": "v1:f1", "snapshot_date": "2026-07-17"},
        {"home_id": "TID_A", "away_id": "TID_B", "fixture_id": "v1:f1", "snapshot_date": "2026-07-18"},
    ])
    ev = _resolved_fixture_evidence(match_hist, "TID_A", "2026-07-17", "2026-07-18")
    assert ev == []


def test_build_events_empty_with_fewer_than_two_snapshots():
    hist = pd.DataFrame([_hist_row("mls", "Alpha", "TID_A", "2026-07-18", playoff=50.0, n_played=5)])
    events = build_events(hist, None, league_id="mls", today=datetime.date(2026, 7, 18))
    assert events == []


def test_build_events_detects_result_with_evidence():
    hist = pd.DataFrame([
        _hist_row("mls", "Alpha", "TID_A", "2026-07-17", playoff=50.0, n_played=5),
        _hist_row("mls", "Alpha", "TID_A", "2026-07-18", playoff=51.0, n_played=6),
    ])
    match_hist = pd.DataFrame([
        {"home_id": "TID_A", "away_id": "TID_B", "fixture_id": "v1:f1", "snapshot_date": "2026-07-17"},
    ])
    events = build_events(hist, match_hist, league_id="mls", today=datetime.date(2026, 7, 18))
    result_events = [e for e in events if e["event_type"] == "result"]
    assert len(result_events) == 1
    assert json.loads(result_events[0]["evidence_ids"]) == ["fixture:v1:f1"]
    assert result_events[0]["attribution_quality"] == "observational"


def test_build_events_result_without_evidence_is_unavailable():
    hist = pd.DataFrame([
        _hist_row("mls", "Alpha", "TID_A", "2026-07-17", playoff=50.0, n_played=5),
        _hist_row("mls", "Alpha", "TID_A", "2026-07-18", playoff=51.0, n_played=6),
    ])
    events = build_events(hist, None, league_id="mls", today=datetime.date(2026, 7, 18))
    result_events = [e for e in events if e["event_type"] == "result"]
    assert len(result_events) == 1
    assert result_events[0]["attribution_quality"] == "unavailable"


def test_build_events_suppresses_refresh_churn():
    hist = pd.DataFrame([
        _hist_row("mls", "Alpha", "TID_A", "2026-07-17", playoff=50.0, n_played=5, config_id="cfg-1"),
        _hist_row("mls", "Alpha", "TID_A", "2026-07-18", playoff=55.0, n_played=5, config_id="cfg-1"),
    ])
    events = build_events(hist, None, league_id="mls", today=datetime.date(2026, 7, 18))
    assert events == []


def test_build_events_detects_threshold_crossing():
    hist = pd.DataFrame([
        _hist_row("mls", "Alpha", "TID_A", "2026-07-17", playoff=20.0, n_played=5),
        _hist_row("mls", "Alpha", "TID_A", "2026-07-18", playoff=30.0, n_played=6),
    ])
    events = build_events(hist, None, league_id="mls", today=datetime.date(2026, 7, 18))
    tc = [e for e in events if e["event_type"] == "threshold_crossing"]
    assert len(tc) == 1 and tc[0]["target_metric"] == "playoff"


def test_build_events_below_noise_floor_without_result_is_suppressed():
    hist = pd.DataFrame([
        _hist_row("mls", "Alpha", "TID_A", "2026-07-17", playoff=50.0, n_played=5,
                   config_id="cfg-1", code_rev="r1"),
        _hist_row("mls", "Alpha", "TID_A", "2026-07-18", playoff=50.1, n_played=5,
                   config_id="cfg-2", code_rev="r1"),
    ])
    events = build_events(hist, None, league_id="mls", today=datetime.date(2026, 7, 18))
    forecast_moves = [e for e in events if e["event_type"] == "forecast_move"]
    assert forecast_moves == []


def test_build_events_detects_model_change():
    hist = pd.DataFrame([
        _hist_row("mls", "Alpha", "TID_A", "2026-07-17", playoff=50.0, n_played=5, config_id="cfg-1"),
        _hist_row("mls", "Alpha", "TID_A", "2026-07-18", playoff=50.0, n_played=5, config_id="cfg-2"),
    ])
    events = build_events(hist, None, league_id="mls", today=datetime.date(2026, 7, 18))
    mc = [e for e in events if e["event_type"] == "model_change"]
    assert len(mc) == 1 and mc[0]["team_id"] is None


def test_build_events_detects_data_health_when_stale():
    hist = pd.DataFrame([
        _hist_row("mls", "Alpha", "TID_A", "2026-07-10", playoff=50.0, n_played=5),
    ])
    events = build_events(hist, None, league_id="mls", today=datetime.date(2026, 7, 18))
    dh = [e for e in events if e["event_type"] == "data_health"]
    assert len(dh) == 1


def test_append_events_dedups_by_event_id(tmp_path):
    hist = pd.DataFrame([
        _hist_row("mls", "Alpha", "TID_A", "2026-07-17", playoff=20.0, n_played=5),
        _hist_row("mls", "Alpha", "TID_A", "2026-07-18", playoff=30.0, n_played=6),
    ])
    events = build_events(hist, None, league_id="mls", today=datetime.date(2026, 7, 18))
    out = tmp_path / "events.parquet"
    added1 = append_events(events, out)
    added2 = append_events(events, out)
    assert added1 == len(events)
    assert added2 == 0
    assert len(pd.read_parquet(out)) == len(events)


def test_build_latest_index_groups_by_team_and_sorts_recent_first():
    events_df = pd.DataFrame([
        {"team_id": "TID_A", "event_id": "e1", "event_type": "result", "target_metric": "playoff",
         "before_pct": 50.0, "after_pct": 51.0, "delta_pp": 1.0, "materiality_score": 0.2,
         "cause_class": "result", "evidence_ids": "[]", "attribution_quality": "unavailable",
         "effective_at": "2026-07-17"},
        {"team_id": "TID_A", "event_id": "e2", "event_type": "threshold_crossing", "target_metric": "playoff",
         "before_pct": 20.0, "after_pct": 30.0, "delta_pp": 10.0, "materiality_score": 0.9,
         "cause_class": "result", "evidence_ids": "[]", "attribution_quality": "unavailable",
         "effective_at": "2026-07-18"},
    ])
    index = build_latest_index(events_df)
    assert index["TID_A"][0]["event_id"] == "e2"  # more recent first
    assert index["TID_A"][1]["event_id"] == "e1"
