from __future__ import annotations

import datetime as dt

import pandas as pd

from api.intel import sample as sample_api
from scripts.intelligence.builder import _trajectory_rows, load_trajectory_frame
from scripts.intelligence.schema import FEATURES
from server.analytics import ALLOWED_EVENTS


def test_club_watch_history_merges_replays_and_exact_archive_with_precedence(tmp_path):
    reconstructed = pd.DataFrame([
        {"league": "mls", "team": "Atlanta United", "snapshot_date": "2026-02-20",
         "season": 2026, "title": 2.0, "kind": "reconstructed",
         "method": "point_in_time_replay", "source_cutoff": "2026-02-20"},
        {"league": "mls", "team": "Atlanta United", "snapshot_date": "2026-04-01",
         "season": 2026, "title": 3.0, "kind": "reconstructed",
         "method": "point_in_time_replay", "source_cutoff": "2026-04-01"},
    ])
    exact = pd.DataFrame([
        {"league": "mls", "team": "Atlanta United", "snapshot_date": "2026-04-01",
         "season": 2026.0, "title": 4.5},
        {"league": "mls", "team": "Atlanta United", "snapshot_date": "2026-04-08",
         "season": 2026.0, "title": 5.5},
    ])
    reconstructed_path = tmp_path / "reconstructed.parquet"
    exact_path = tmp_path / "exact.parquet"
    reconstructed.to_parquet(reconstructed_path, index=False)
    exact.to_parquet(exact_path, index=False)

    merged = load_trajectory_frame(exact_path, reconstructed_path)

    assert list(merged["snapshot_date"]) == [
        "2026-02-20", "2026-04-01", "2026-04-08"]
    same_day = merged[merged["snapshot_date"] == "2026-04-01"].iloc[0]
    assert same_day["kind"] == "archived"
    assert same_day["title"] == 4.5


def test_club_watch_history_is_current_season_and_carries_provenance():
    history = pd.DataFrame([
        {"league": "mls", "team": "Atlanta United", "team_id": None,
         "snapshot_date": "2025-07-01", "season": 2025.0, "title": 9.0,
         "kind": "archived"},
        {"league": "mls", "team": "Atlanta United", "team_id": None,
         "snapshot_date": "2026-02-20", "season": 2026.0, "title": 2.0,
         "kind": "reconstructed", "method": "point_in_time_replay",
         "source_cutoff": "2026-02-20"},
        {"league": "mls", "team": "Atlanta United", "team_id": "v1:atl",
         "snapshot_date": "2026-07-30", "season": None, "title": 6.0,
         "kind": "archived"},
    ])

    points = _trajectory_rows(
        history, "mls", "v1:atl", "Atlanta United", current_season=2026,
        season_window=(dt.date(2026, 1, 1), dt.date(2026, 12, 31)))

    assert [point["snapshot_date"] for point in points] == [
        "2026-02-20", "2026-07-30"]
    assert points[0]["season_id"] == "2026"
    assert points[0]["kind"] == "reconstructed"
    assert points[0]["method"] == "point_in_time_replay"
    assert points[1]["kind"] == "archived"


def test_free_club_watch_sample_includes_frozen_season_history(monkeypatch):
    history = {"feature_id": 11, "name": FEATURES[11], "status": "live",
               "data": {"points": [{"snapshot_date": "2026-02-20"}]}}
    monkeypatch.setattr(sample_api._service, "get_team", lambda *_args: {
        "league_id": "mls", "league_name": "MLS", "team_id": "v1:atl",
        "team": "Atlanta United", "season_id": "2026", "snapshot_id": "v1:snap",
        "generated": "2026-07-31 10:00 UTC", "calendar_mode": {},
        "target_metric": "cup", "features": {
            "1": {}, "2": {}, "3": {}, "4": {}, "11": history,
        },
    })

    sample = sample_api._build_sample("mls", "v1:atl")

    assert FEATURES[11] == "Season Forecast History"
    assert sample["features"]["history"] == history
    assert "season_history_viewed" in ALLOWED_EVENTS
