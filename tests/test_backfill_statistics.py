"""Resumable statistics backfill — plan, store, resume, budget exit. No network.

Spec: docs/superpowers/specs/2026-08-08-api-football-migration-execution-spec.md §6.5 + Stage 4.
"""
from __future__ import annotations

import json

import pytest


MAP = {
    # xG-era statistics (2023+), current source has no xG → target
    "brazil-serie-a": {"af_id": 71, "statistics_since": 2016, "last_season": 2025},
    # statistics flag missing → never a unit
    "australia-aleague": {"af_id": 188, "statistics_since": None, "last_season": 2025},
    # already has real xG → excluded even though statistics exist
    "epl": {"af_id": 39, "statistics_since": 2014, "last_season": 2025},
    # statistics start inside the xG era
    "ireland-premier": {"af_id": 357, "statistics_since": 2023, "last_season": 2025},
    # coverage starts after the xG era begins → clamps to its own start
    "bolivia-profesional": {"af_id": 344, "statistics_since": 2024, "last_season": 2025},
}
EXCLUDE = {"epl"}


def test_plan_targets_xg_era_and_orders_recent_first():
    from data_pipeline.backfill_statistics import plan_backfill
    units = plan_backfill(MAP, exclude=EXCLUDE, xg_since=2023)
    assert ("epl", 39, 2025) not in units          # xG league excluded
    assert all(u[0] != "australia-aleague" for u in units)   # no statistics
    assert ("brazil-serie-a", 71, 2022) not in units         # pre-xG-era
    assert ("bolivia-profesional", 344, 2023) not in units   # before its coverage
    # Recent-first ACROSS leagues: every 2025 unit precedes any 2024 unit.
    seasons = [s for (_, _, s) in units]
    assert seasons == sorted(seasons, reverse=True)
    assert ("brazil-serie-a", 71, 2025) in units
    assert ("ireland-premier", 357, 2023) in units


@pytest.fixture
def env(tmp_path, monkeypatch):
    """Isolated store + health, generous fake plan."""
    from data_pipeline import source_health, backfill_statistics as bf
    monkeypatch.setattr(source_health, "_HEALTH_PATH",
                        tmp_path / "source_health.parquet")
    monkeypatch.setattr(bf, "STORE", tmp_path / "statistics")
    monkeypatch.setattr(bf, "FIXTURES_CACHE", tmp_path / "fixtures")
    monkeypatch.setenv("API_FOOTBALL_PLAN", "mega")
    monkeypatch.setenv("API_FOOTBALL_KEY", "test-key")
    return tmp_path


def _fake_api(calls):
    """Serve fixtures (3 finished, 1 upcoming) and per-fixture statistics."""
    def fake_get(path, params, budget="ops"):
        calls.append((path, dict(params)))
        if path == "fixtures":
            return {"response": [
                {"fixture": {"id": 100 + i, "status": {"short": "FT"}}}
                for i in range(3)
            ] + [{"fixture": {"id": 999, "status": {"short": "NS"}}}]}
        if path == "fixtures/statistics":
            fid = params["fixture"]
            if fid == 102:                       # a fixture with no stat sheet
                return {"response": []}
            return {"response": [{"team": {"id": 1}, "statistics": []},
                                 {"team": {"id": 2}, "statistics": []}]}
        raise AssertionError(f"unexpected path {path}")
    return fake_get


def test_run_stores_per_fixture_and_skips_unplayed(env, monkeypatch):
    from data_pipeline import api_football, backfill_statistics as bf
    calls = []
    monkeypatch.setattr(api_football, "_get", _fake_api(calls))
    done = bf.run_units([("brazil-serie-a", 71, 2024)])
    assert done == 3                                    # finished fixtures only
    assert (bf.STORE / "100.json").exists()
    assert (bf.STORE / "102.json").exists()             # empty sheet cached too
    assert not (bf.STORE / "999.json").exists()         # unplayed: never asked
    stats_calls = [p for p, _ in calls if p == "fixtures/statistics"]
    assert len(stats_calls) == 3


def test_rerun_makes_zero_statistics_requests(env, monkeypatch):
    """Restart re-reads, never re-requests — including empty stat sheets."""
    from data_pipeline import api_football, backfill_statistics as bf
    calls = []
    monkeypatch.setattr(api_football, "_get", _fake_api(calls))
    bf.run_units([("brazil-serie-a", 71, 2024)])
    calls.clear()
    bf.run_units([("brazil-serie-a", 71, 2024)])
    assert [p for p, _ in calls if p == "fixtures/statistics"] == []


def test_budget_exhaustion_exits_cleanly_with_partial_progress(env, monkeypatch):
    from data_pipeline import api_football, api_budget, backfill_statistics as bf
    calls = []
    real = _fake_api(calls)

    def limited(path, params, budget="ops"):
        if path == "fixtures/statistics" and \
                len([p for p, _ in calls if p == "fixtures/statistics"]) >= 2:
            raise api_budget.BudgetExceeded("backfill budget exhausted")
        return real(path, params, budget)

    monkeypatch.setattr(api_football, "_get", limited)
    done = bf.run_units([("brazil-serie-a", 71, 2024)])   # must NOT raise
    assert done == 2                                       # partial, recorded
    resumable = bf.progress([("brazil-serie-a", 71, 2024)])
    assert resumable["fixtures_done"] == 2


def test_progress_counts_from_disk_without_requests(env, monkeypatch):
    from data_pipeline import api_football, backfill_statistics as bf
    calls = []
    monkeypatch.setattr(api_football, "_get", _fake_api(calls))
    bf.run_units([("brazil-serie-a", 71, 2024)])
    calls.clear()
    p = bf.progress([("brazil-serie-a", 71, 2024)])
    assert p["fixtures_done"] == 3 and p["fixtures_total"] == 3
    assert calls == []                       # progress is a disk read, period


def test_plan_mismatch_propagates_loudly(env, monkeypatch):
    """A lapsed plan mid-backfill must stop the job, not be absorbed as a
    per-fixture failure."""
    from data_pipeline import api_football, api_budget, backfill_statistics as bf

    def lapsed(path, params, budget="ops"):
        if path == "fixtures":
            return {"response": [
                {"fixture": {"id": 100, "status": {"short": "FT"}}}]}
        raise api_budget.PlanMismatch("daily quota says free tier")

    monkeypatch.setattr(api_football, "_get", lapsed)
    with pytest.raises(api_budget.PlanMismatch):
        bf.run_units([("brazil-serie-a", 71, 2024)])
