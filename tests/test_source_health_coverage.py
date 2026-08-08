"""Every match-data adapter must report its fetches — successes AND failures.

Phase 1 of the source-resilience scope. record_source_run was called by only 3
of 8 adapters, and always AFTER a successful parse, so a feed going dark left no
trace: on 2026-08-07 ESPN 403'd for hours across three scheduled jobs, the
Leagues Cup lost 9 of 9 seasons, and the only evidence anywhere was warning
lines in workflow logs nobody was reading.

A dark feed has to be visible in data, not prose.
"""
from unittest.mock import patch

import pytest
import requests

from data_pipeline import source_health as sh


@pytest.fixture
def recorded(monkeypatch):
    """Capture record_source_run calls instead of writing the parquet."""
    calls = []
    monkeypatch.setattr(sh, "record_source_run",
                        lambda **kw: calls.append(kw) or "id")
    return calls


# ── the helper itself ────────────────────────────────────────────────────────

def test_failure_is_recorded_with_the_error_attached(recorded):
    sh.record_fetch("espn_continental", "uefa.champions", ok=False, error="403")
    assert len(recorded) == 1
    assert recorded[0]["error_message"] == "403"


def test_success_records_no_error_so_the_success_column_is_true(recorded):
    """source_health derives `success` as `error_message is None`."""
    sh.record_fetch("espn_continental", "uefa.champions", ok=True, raw=12)
    assert recorded[0]["error_message"] is None
    assert recorded[0]["raw_count"] == 12


def test_a_failure_with_no_message_still_records_as_a_failure(recorded):
    sh.record_fetch("x", "y", ok=False)
    assert recorded[0]["error_message"], "ok=False must never write success=True"


def test_recording_never_breaks_a_build(monkeypatch):
    """Health accounting is observability, not a data dependency. If the parquet
    cannot be written, the refresh that was writing it must still finish."""
    def boom(**kw):
        raise OSError("disk full")
    monkeypatch.setattr(sh, "record_source_run", boom)
    sh.record_fetch("espn", "anything", ok=True)      # must not raise


# ── adapter coverage ─────────────────────────────────────────────────────────

def test_continental_fetch_records_both_outcomes(recorded):
    from data_pipeline import espn_continental as ec
    with patch.object(ec, "espn_get", return_value={"events": [1, 2, 3]}):
        ec._fetch("uefa.champions", 2026, 2027)
    with patch.object(ec, "espn_get", side_effect=requests.HTTPError("403")):
        assert ec._fetch("uefa.champions", 2026, 2027) is None
    assert [c["error_message"] is None for c in recorded] == [True, False], recorded
    assert all("uefa.champions" in c["endpoint"] for c in recorded)


def test_fixtures_fetch_records_both_outcomes(recorded):
    from data_pipeline import espn_fixtures as ef
    with patch.object(ef, "espn_get", return_value={"events": [1]}):
        ef._fetch_events("eng.2", 2026)
    with patch.object(ef, "espn_get", side_effect=requests.HTTPError("403")):
        ef._fetch_events("eng.2", 2026)
    assert [c["error_message"] is None for c in recorded] == [True, False]


def test_api_football_quota_error_is_recorded_as_a_failure(recorded):
    """Quota exhaustion arrives as HTTP 200 with an `errors` object, so it looks
    like success at the transport layer and would otherwise never be seen."""
    from data_pipeline import api_football as af

    class R:
        status_code = 200
        def raise_for_status(self): pass
        def json(self): return {"errors": {"plan": "quota exceeded"}}

    with patch.object(af, "_require_key", return_value="k"), \
         patch.object(af.requests, "get", return_value=R()):
        with pytest.raises(RuntimeError):
            af._get("fixtures", {"league": 772})
    assert recorded and recorded[0]["error_message"], "quota error not recorded"


def test_every_match_data_adapter_reports_its_fetches():
    """The list is the contract. A new adapter that fetches match data and does
    not report is the gap this phase closed — adding one here without wiring it
    should fail loudly rather than silently reintroduce a blind feed."""
    import pathlib
    expected = {
        "asa_cache", "espn_soccer", "understat",            # wired before 2026-08-08
        "espn_continental", "espn_fixtures", "football_data",
        "football_data_intl", "api_football",                # wired 2026-08-08
    }
    root = pathlib.Path(__file__).resolve().parent.parent / "data_pipeline"
    missing = {
        name for name in expected
        if "record_fetch" not in (root / f"{name}.py").read_text()
        and "record_source_run" not in (root / f"{name}.py").read_text()
    }
    assert not missing, f"adapters fetch match data but report nothing: {sorted(missing)}"
