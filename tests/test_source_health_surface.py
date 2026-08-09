"""The published source-health surface and its alerting. No network.

Spec: docs/superpowers/specs/2026-08-09-platform-reliability-and-api-opportunity-spec.md
§3.4. `source_health.parquet` is gitignored, read by no workflow, and thrown
away every CI run — so the division-mismatch guard, every router fallback and
the plan-lapse assertion all log into nothing.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from scripts import build_source_health as bsh

NOW = datetime(2026, 8, 9, 12, 0, tzinfo=timezone.utc)


def _health_parquet(path, rows):
    frame = pd.DataFrame([{
        "source_run_id": f"r{i}", "source_name": r[0], "endpoint": r[1],
        "fetched_at": r[2], "raw_count": r[3], "parsed_count": r[3],
        "matched_count": 0, "unmatched_count": 0, "schema_hash": "x",
        "null_rate_json": "{}", "success": r[4], "error_message": r[5],
    } for i, r in enumerate(rows)])
    frame.to_parquet(path, index=False)
    return path


def test_run_counters_are_a_full_pass_and_count_successful_rows_only(tmp_path):
    """R3: a coverage claim is a full pass asserting the consumer's condition.
    A stale-cache read records rows AND a failure — those rows are not evidence
    the feed answered."""
    p = _health_parquet(tmp_path / "h.parquet", [
        ("espn", "usa.1/scoreboard", "2026-08-09T11:00:00+00:00", 480, True, None),
        ("espn", "eng.1/scoreboard", "2026-08-09T11:01:00+00:00", 0, False, "403 Forbidden"),
        ("football_data_intl", "argentina.csv", "2026-08-09T11:02:00+00:00", 900,
         False, "served from cache: timeout"),
    ])
    feeds = bsh.read_run(p)
    assert feeds["espn"]["attempts"] == 2 and feeds["espn"]["failures"] == 1
    assert feeds["espn"]["rows"] == 480
    assert feeds["football_data_intl"]["rows"] == 0     # cache read is not coverage
    assert feeds["espn"]["last_success"].startswith("2026-08-09T11:00")


def test_missing_parquet_is_empty_not_an_error(tmp_path):
    assert bsh.read_run(tmp_path / "absent.parquet") == {}


# ── the counter that decides whether a run fails ─────────────────────────────
def test_a_feed_that_answers_resets_the_dark_counter():
    prior = {"feeds": {"espn": {"consecutive_dark_runs": 4}}}
    out = bsh.merge(prior, {"espn": _run(attempts=3, failures=1)}, now=NOW)
    assert out["feeds"]["espn"]["consecutive_dark_runs"] == 0


def test_a_feed_that_answers_nothing_advances_the_dark_counter():
    prior = {"feeds": {"espn": {"consecutive_dark_runs": 1}}}
    out = bsh.merge(prior, {"espn": _run(attempts=3, failures=3)}, now=NOW)
    assert out["feeds"]["espn"]["consecutive_dark_runs"] == 2


def test_an_unexercised_feed_is_not_dark():
    """§8.14: ~40% of the catalogue is between seasons at any moment. A feed
    nobody called is unexercised, not dark — counting it would make the alert
    fire every off-season and teach everyone to ignore it."""
    prior = {"feeds": {"understat": {"consecutive_dark_runs": 1}}}
    out = bsh.merge(prior, {"understat": _run(attempts=0, failures=0)}, now=NOW)
    assert out["feeds"]["understat"]["consecutive_dark_runs"] == 1


def test_a_success_with_zero_rows_is_a_success():
    """A dormant league's 200 carrying no fixtures is the normal off-season
    answer, not an outage."""
    out = bsh.merge({}, {"espn": _run(attempts=1, failures=0, rows=0)}, now=NOW)
    assert out["feeds"]["espn"]["consecutive_dark_runs"] == 0


# ── the published figures state their own condition ──────────────────────────
def test_failure_rate_names_the_window_and_the_n_it_is_over():
    prior = {"feeds": {"espn": {"recent": [
        {"at": (NOW - timedelta(hours=30)).isoformat(), "attempts": 10, "failures": 10},
        {"at": (NOW - timedelta(hours=2)).isoformat(), "attempts": 10, "failures": 2},
    ]}}}
    out = bsh.merge(prior, {"espn": _run(attempts=10, failures=0)}, now=NOW)
    info = out["feeds"]["espn"]
    # The 30h-old run is outside the window; 2/20 across the two inside it.
    assert info["failure_rate_24h"] == pytest.approx(0.1)
    assert "2 recorded runs" in info["failure_rate_24h_condition"]
    assert "2/20" in info["failure_rate_24h_condition"]


def test_recent_history_is_bounded():
    prior = {"feeds": {"espn": {"recent": [
        {"at": NOW.isoformat(), "attempts": 1, "failures": 0}
    ] * (bsh.RECENT_RUNS_KEPT + 20)}}}
    out = bsh.merge(prior, {"espn": _run(attempts=1, failures=0)}, now=NOW)
    assert len(out["feeds"]["espn"]["recent"]) == bsh.RECENT_RUNS_KEPT


# ── the failures that must not be as quiet as a routine 404 ──────────────────
@pytest.mark.parametrize("error,kind", [
    ("served SC2 content, expected SP2 (via 301)", "division_mismatch"),
    ("API-Football /fixtures identity mismatch: league id ['140'] != 141",
     "identity_mismatch"),
    ("served from cache: read timeout", "stale_cache"),
])
def test_notable_failures_are_classified(error, kind):
    feeds = {"football_data": _run(attempts=1, failures=1, errors=[error])}
    kinds = [n["kind"] for n in bsh.classify_notable(feeds)]
    assert kind in kinds


def test_a_plain_404_is_not_notable():
    feeds = {"espn": _run(attempts=1, failures=1, errors=["404 Not Found"])}
    assert bsh.classify_notable(feeds) == []


# ── alerting: within one cycle, failing after N ──────────────────────────────
def test_one_dark_run_already_annotates_as_an_error(capsys):
    summary = bsh.merge({}, {"espn": _run(attempts=2, failures=2)}, now=NOW)
    bsh.annotate(summary)
    out = capsys.readouterr().out
    assert "::error::" in out and "espn" in out


def test_check_exits_non_zero_only_after_the_threshold(tmp_path, capsys):
    path = tmp_path / "summary.json"
    path.write_text(json.dumps({"feeds": {
        "espn": {"consecutive_dark_runs": bsh.DARK_RUNS_ALERT},
        "asa": {"consecutive_dark_runs": 1},
    }}))
    assert bsh.main(["--check", "--summary-path", str(path)]) == 1
    assert "espn" in capsys.readouterr().out

    path.write_text(json.dumps({"feeds": {"asa": {"consecutive_dark_runs": 1}}}))
    assert bsh.main(["--check", "--summary-path", str(path)]) == 0


def test_write_never_fails_the_build(tmp_path):
    """Observability must not discard a run's good payloads — the 2026-07-19
    bug threw away five nights of correct data exactly this way."""
    p = _health_parquet(tmp_path / "h.parquet", [
        ("espn", "usa.1/scoreboard", "2026-08-09T11:00:00+00:00", 0, False, "403"),
    ])
    summary = tmp_path / "summary.json"
    summary.write_text(json.dumps({"feeds": {"espn": {"consecutive_dark_runs": 9}}}))
    assert bsh.main(["--write", "--health-path", str(p),
                     "--summary-path", str(summary)]) == 0
    assert json.loads(summary.read_text())["feeds"]["espn"]["consecutive_dark_runs"] == 10


def test_summary_survives_a_run_that_wrote_no_parquet(tmp_path):
    summary = tmp_path / "summary.json"
    summary.write_text(json.dumps({"feeds": {"espn": {
        "consecutive_dark_runs": 2, "last_success": "2026-08-01T00:00:00+00:00"}}}))
    bsh.main(["--write", "--health-path", str(tmp_path / "absent.parquet"),
              "--summary-path", str(summary)])
    kept = json.loads(summary.read_text())["feeds"]["espn"]
    assert kept["consecutive_dark_runs"] == 2
    assert kept["last_success"] == "2026-08-01T00:00:00+00:00"


# ── the workflows actually run it ────────────────────────────────────────────
@pytest.mark.parametrize("workflow", ["refresh-daily.yml", "refresh-leagues.yml"])
def test_scheduled_refreshes_publish_and_check_the_surface(workflow):
    from pathlib import Path
    text = (Path(__file__).resolve().parent.parent /
            ".github/workflows" / workflow).read_text()
    assert "build_source_health.py --write" in text
    assert "build_source_health.py --check" in text
    assert "data/source_health_summary.json" in text, (
        "the summary must be committed, or the consecutive-dark counter resets "
        "every run and can never reach its threshold")
    # The check runs AFTER the commit, so a failing verdict cannot discard the
    # payloads the run just built correctly.
    assert text.index("git add") < text.index("build_source_health.py --check")


def _run(attempts, failures, rows=1, errors=None):
    return {"attempts": attempts, "failures": failures, "rows": rows,
            "last_success": "2026-08-09T11:00:00+00:00" if attempts > failures else None,
            "last_failure": "2026-08-09T11:05:00+00:00" if failures else None,
            "errors": errors or [], "endpoints_failed": []}
