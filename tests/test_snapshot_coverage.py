"""Per-snapshot coverage manifest (launch audit follow-up, Track 5).

Row counts alone cannot distinguish "this league had no upcoming fixtures" from
"this league was never built today" -- they move with league count AND with
fixtures remaining. Under a paid tier a partial day is a hole in something a
customer bought, so the archive records what it captured, at the time.
"""
from __future__ import annotations

import json

from scripts.archive_odds_snapshot import record_coverage


def test_complete_day_is_marked_complete(tmp_path):
    out = tmp_path / "coverage.json"
    rec = record_coverage("2026-07-25", ["epl", "mls"], ["epl", "mls"], out)
    assert rec["complete"] is True
    assert rec["missing"] == []
    assert rec["n_archived"] == 2


def test_partial_day_names_the_missing_leagues(tmp_path):
    out = tmp_path / "coverage.json"
    rec = record_coverage("2026-07-24", ["epl"], ["epl", "mls", "nwsl"], out)
    assert rec["complete"] is False
    assert rec["missing"] == ["mls", "nwsl"]


def test_a_later_run_can_only_improve_a_day(tmp_path):
    """An ad-hoc local build after the nightly run must not erase its coverage."""
    out = tmp_path / "coverage.json"
    record_coverage("2026-07-24", ["epl"], ["epl", "mls"], out)
    rec = record_coverage("2026-07-24", ["mls"], ["epl", "mls"], out)
    assert rec["leagues_archived"] == ["epl", "mls"]
    assert rec["complete"] is True


def test_history_accumulates_and_stays_sorted(tmp_path):
    out = tmp_path / "coverage.json"
    record_coverage("2026-07-25", ["epl"], ["epl"], out)
    record_coverage("2026-07-23", ["epl"], ["epl"], out)
    history = json.loads(out.read_text())
    assert list(history) == ["2026-07-23", "2026-07-25"]


def test_corrupt_history_does_not_lose_the_current_day(tmp_path):
    out = tmp_path / "coverage.json"
    out.write_text("{not json")
    rec = record_coverage("2026-07-25", ["epl"], ["epl"], out)
    assert rec["complete"] is True
    assert "2026-07-25" in json.loads(out.read_text())


def test_complete_is_not_a_count_comparison(tmp_path):
    """More leagues archive than are flagged live (preseason leagues publish
    fixtures too), so a raw count check would call a day with a missing live
    league 'complete' -- the exact ambiguity this manifest removes."""
    out = tmp_path / "coverage.json"
    rec = record_coverage(
        "2026-07-25",
        ["epl", "mls", "nwsl", "brazil-serie-a"],   # 4 archived
        ["epl", "romania-liga1"],                   # 2 live, one absent
        out,
    )
    assert rec["n_archived"] > rec["n_live"]
    assert rec["missing"] == ["romania-liga1"]
    assert rec["complete"] is False


def test_merge_does_not_resurrect_completeness(tmp_path):
    out = tmp_path / "coverage.json"
    record_coverage("2026-07-24", ["epl"], ["epl", "mls"], out)
    rec = record_coverage("2026-07-24", ["nwsl"], ["epl", "mls"], out)
    assert rec["missing"] == ["mls"]
    assert rec["complete"] is False
