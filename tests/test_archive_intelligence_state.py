import gzip
import json

import pytest

from scripts.archive_intelligence_state import (
    MissingRequiredInput, build_snapshot, write_snapshot,
)


def _payload(**overrides):
    base = {
        "league": {"id": "mls"}, "season": 2026, "generated": "2026-07-18 12:00 UTC",
        "provenance": {"champion_run": "run-123", "git_commit": "abcd123"},
        "n_sims": 20000, "playoff_slots": 9, "hfa_slots": 4,
        "standings": [
            {"team": "Alpha", "team_id": "TID_A", "conf": "East", "pts": 30, "gd": 10,
             "proj_pts": 55.0, "playoff": 80.0, "hfa": 40.0, "shield": 5.0, "spoon": 0.0,
             "conf_win": 10.0, "cup": 2.0},
            {"team": "Beta", "team_id": "TID_B", "conf": "West", "pts": 20, "gd": -5,
             "proj_pts": 40.0, "playoff": 20.0, "hfa": 5.0, "shield": 0.5, "spoon": 3.0,
             "conf_win": 1.0, "cup": 0.2},
        ],
        "games": [
            {"home": "Alpha", "away": "Beta", "home_id": "TID_A", "away_id": "TID_B",
             "fixture_id": "v1:fixture1", "date": "2026-07-20", "pH": 0.5, "pD": 0.2, "pA": 0.3,
             "result": None},
            {"home": "Beta", "away": "Alpha", "home_id": "TID_B", "away_id": "TID_A",
             "fixture_id": "v1:fixture0", "date": "2026-06-01", "pH": 0.3, "pD": 0.3, "pA": 0.4,
             "result": "H"},
        ],
        "sim": {"teams": ["Alpha", "Beta"],
                "pmatrix": [[None, [500, 200, 300]], [[300, 200, 500], None]]},
    }
    base.update(overrides)
    return base


def test_build_snapshot_shape():
    snap = build_snapshot(_payload())
    assert snap["league_id"] == "mls" and snap["season"] == 2026
    assert snap["config_id"] == "run-123"
    assert len(snap["teams"]) == 2
    assert snap["teams"][0]["team"] == "Alpha" and snap["teams"][0]["team_id"] == "TID_A"
    assert snap["teams"][0]["published"]["playoff"] == 80.0


def test_build_snapshot_only_includes_upcoming_fixtures():
    snap = build_snapshot(_payload())
    assert len(snap["fixtures"]) == 1
    assert snap["fixtures"][0]["fixture_id"] == "v1:fixture1"


def test_build_snapshot_fails_closed_on_missing_standings():
    payload = _payload(standings=[])
    with pytest.raises(MissingRequiredInput):
        build_snapshot(payload)


def test_build_snapshot_fails_closed_on_missing_config_id():
    payload = _payload()
    del payload["provenance"]["champion_run"]
    with pytest.raises(MissingRequiredInput):
        build_snapshot(payload)


def test_build_snapshot_fails_closed_on_missing_pmatrix():
    payload = _payload()
    payload["sim"]["pmatrix"] = []
    with pytest.raises(MissingRequiredInput):
        build_snapshot(payload)


def test_snapshot_id_is_deterministic_for_identical_inputs():
    snap1 = build_snapshot(_payload())
    snap2 = build_snapshot(_payload())
    assert snap1["snapshot_id"] == snap2["snapshot_id"]
    assert snap1["replay_seed"] == snap2["replay_seed"]


def test_snapshot_id_differs_when_generated_timestamp_differs():
    snap1 = build_snapshot(_payload())
    snap2 = build_snapshot(_payload(generated="2026-07-19 12:00 UTC"))
    assert snap1["snapshot_id"] != snap2["snapshot_id"]


def test_write_snapshot_writes_gzip_json(tmp_path):
    snap = build_snapshot(_payload())
    path, deduped = write_snapshot(snap, snapshot_dir=tmp_path)
    assert path.exists() and not deduped
    with gzip.open(path, "rt", encoding="utf-8") as f:
        loaded = json.load(f)
    assert loaded["snapshot_id"] == snap["snapshot_id"]
    assert isinstance(loaded["pmatrix"], list)


def test_write_snapshot_dedups_unchanged_pmatrix(tmp_path):
    snap1 = build_snapshot(_payload())
    write_snapshot(snap1, snapshot_dir=tmp_path)
    snap2 = build_snapshot(_payload(generated="2026-07-19 12:00 UTC"))  # new id, same pmatrix
    path2, deduped2 = write_snapshot(snap2, snapshot_dir=tmp_path)
    assert deduped2 is True
    with gzip.open(path2, "rt", encoding="utf-8") as f:
        loaded = json.load(f)
    assert loaded["pmatrix"] == {"$ref": snap1["snapshot_id"]}


def test_write_snapshot_does_not_dedup_when_pmatrix_changes(tmp_path):
    snap1 = build_snapshot(_payload())
    write_snapshot(snap1, snapshot_dir=tmp_path)
    changed_payload = _payload(generated="2026-07-19 12:00 UTC")
    changed_payload["sim"]["pmatrix"][0][1] = [510, 190, 300]
    snap2 = build_snapshot(changed_payload)
    _, deduped2 = write_snapshot(snap2, snapshot_dir=tmp_path)
    assert deduped2 is False
