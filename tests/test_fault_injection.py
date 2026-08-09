"""The fault-injection drill and the ESPN blackhole it runs on. No network.

Spec: docs/superpowers/specs/2026-08-09-platform-reliability-and-api-opportunity-spec.md
§3.6. The router exists so a dark ESPN degrades instead of failing, and nothing
exercises that path while ESPN is answering — so it rots, and the first anyone
learns of it is the next outage.
"""
from __future__ import annotations

import json

import pytest
import yaml
from pathlib import Path

from data_pipeline import http
from scripts import fault_injection_drill as drill

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def blocked(monkeypatch):
    monkeypatch.setenv(drill.BLOCK_ENV, "1")


# ── the blackhole itself ─────────────────────────────────────────────────────
def test_blackhole_is_off_unless_explicitly_asked_for(monkeypatch):
    """A kill switch that can turn itself on is a production outage waiting to
    happen. Off for unset, empty, "0" and "false"."""
    monkeypatch.delenv(drill.BLOCK_ENV, raising=False)
    assert http.espn_is_blocked() is False
    for value in ("", "0", "false", "False", "  "):
        monkeypatch.setenv(drill.BLOCK_ENV, value)
        assert http.espn_is_blocked() is False, value


def test_blackhole_refuses_before_touching_the_network(monkeypatch, blocked):
    def no_network(*a, **k):
        raise AssertionError("a request was made while blackholed")

    monkeypatch.setattr(http.requests, "get", no_network)
    monkeypatch.setattr(http.time, "sleep", lambda s: None)
    with pytest.raises(http.Blackholed):
        http.espn_get("https://site.api.espn.com/anything")


def test_blackhole_is_a_transport_failure_so_callers_take_their_403_branch():
    """Every adapter already handles requests.RequestException as "the feed did
    not answer". A new exception type would need every caller changed."""
    import requests
    assert issubclass(http.Blackholed, requests.RequestException)


# ── the drill's own smoke test ───────────────────────────────────────────────
def test_drill_fails_when_nothing_is_actually_blocked(monkeypatch):
    """The check that stops this whole drill from passing vacuously."""
    monkeypatch.delenv(drill.BLOCK_ENV, raising=False)
    assert drill.check_blackhole_works()["status"] == "fail"


def test_drill_confirms_the_blackhole_when_it_is_on(monkeypatch, blocked):
    monkeypatch.setattr(http.requests, "get",
                        lambda *a, **k: pytest.fail("network touched"))
    assert drill.check_blackhole_works()["status"] == "pass"


# ── the degradation contract ─────────────────────────────────────────────────
def test_a_routed_league_is_expected_to_have_a_non_espn_primary():
    out = drill.check_routed_league_survives("northern-super-league", live=False)
    assert out["status"] == "skipped"       # structural only without --live
    assert "api_football" in out["detail"]


def test_a_league_that_lost_its_routing_fails_the_drill(monkeypatch):
    from data_pipeline import source_registry
    monkeypatch.setitem(source_registry.REGISTRY, "northern-super-league",
                        {"fixtures": ["espn"]})
    out = drill.check_routed_league_survives("northern-super-league", live=False)
    assert out["status"] == "fail"


def test_an_unrouted_league_must_fail_loudly_naming_its_sources(tmp_path, monkeypatch):
    from data_pipeline import source_health
    monkeypatch.setattr(source_health, "_HEALTH_PATH", tmp_path / "h.parquet")
    out = drill.check_unrouted_league_fails_loudly("epl")
    assert out["status"] == "pass" and "espn" in out["detail"]


def test_mls_fallback_is_checked():
    out = drill.check_mls_schedule_falls_back(live=False)
    assert out["status"] == "skipped" and "api_football" in out["detail"]


def test_a_skipped_check_is_never_reported_as_a_pass(tmp_path, monkeypatch, capsys):
    """A drill that could not reach the spine has not proven the fallback.
    Reporting that as green is worse than reporting nothing."""
    from data_pipeline import source_health
    monkeypatch.setattr(source_health, "_HEALTH_PATH", tmp_path / "h.parquet")
    monkeypatch.setenv(drill.BLOCK_ENV, "1")
    report = tmp_path / "drill.json"
    assert drill.main(["--report", str(report)]) == 0
    results = json.loads(report.read_text())
    assert any(r["status"] == "skipped" for r in results)
    assert "structural only" in capsys.readouterr().out


def test_drill_exits_non_zero_on_a_failed_check(tmp_path, monkeypatch):
    monkeypatch.delenv(drill.BLOCK_ENV, raising=False)
    # main() must not set the block itself: doing so leaked the variable into
    # the test process and turned four unrelated http tests red.
    monkeypatch.setattr(drill, "run", lambda live=False: [
        {"check": "x", "status": "fail", "detail": "broken"}])
    assert drill.main(["--report", str(tmp_path / "d.json")]) == 1
    import os
    assert drill.BLOCK_ENV not in os.environ


# ── it is actually scheduled, and it cannot write data ───────────────────────
def _workflow():
    return yaml.safe_load((ROOT / ".github/workflows/fault-injection.yml").read_text())


def test_the_drill_is_scheduled():
    wf = _workflow()
    on = wf.get("on") or wf.get(True)
    assert on.get("schedule"), "an unscheduled drill only runs after the outage"


def test_the_drill_blackholes_espn_and_cannot_commit():
    wf = _workflow()
    assert wf["env"]["ENTENSER_BLOCK_ESPN"] == "1"
    assert wf["permissions"]["contents"] == "read", (
        "the drill proves behaviour; the refresh jobs own data")
    text = (ROOT / ".github/workflows/fault-injection.yml").read_text()
    assert "git push" not in text and "git commit" not in text


def test_the_drill_has_its_own_api_allowance():
    """R4: a drill must never be able to eat the refresh's budget."""
    wf = _workflow()
    assert int(wf["env"]["API_FOOTBALL_OPS_BUDGET"]) < 2000


def test_the_plan_value_matches_the_refresh_workflows():
    """§8.7: on a downgrade the plan value must change in EVERY workflow, or
    the lapse guard fails builds loudly. Adding a third workflow adds a third
    place to forget."""
    plans = set()
    for name in ("refresh-daily.yml", "refresh-leagues.yml", "fault-injection.yml"):
        wf = yaml.safe_load((ROOT / ".github/workflows" / name).read_text())
        plans.add(wf["env"]["API_FOOTBALL_PLAN"])
    assert len(plans) == 1, f"workflows disagree on the plan: {plans}"
