"""Budget governor — spend counting, fail-closed allowances, plan assertion. No network.

Spec: docs/superpowers/specs/2026-08-08-api-football-migration-execution-spec.md §4.1/§6.4.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest


def _write_health(path: Path, rows: list[dict]) -> None:
    """Minimal source_health.parquet stand-in — spend counting needs only
    source_name + fetched_at."""
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_parquet(path, index=False)


def _row(source: str, when: datetime) -> dict:
    return {"source_name": source, "fetched_at": when.isoformat(), "success": True}


@pytest.fixture
def health_path(tmp_path, monkeypatch) -> Path:
    from data_pipeline import source_health
    p = tmp_path / "source_health.parquet"
    monkeypatch.setattr(source_health, "_HEALTH_PATH", p)
    return p


# ── spend counting ───────────────────────────────────────────────────────────
def test_spend_today_counts_only_api_football_since_utc_midnight(health_path):
    from data_pipeline import api_budget
    now = datetime(2026, 8, 8, 12, 0, tzinfo=timezone.utc)
    _write_health(health_path, [
        _row("api_football", now - timedelta(hours=1)),      # today
        _row("api_football", now - timedelta(hours=11)),     # today, 01:00 UTC
        _row("api_football", now - timedelta(hours=13)),     # yesterday 23:00 UTC
        _row("espn", now - timedelta(hours=1)),              # other source
    ])
    assert api_budget.spend_today(now=now) == 2


def test_spend_today_missing_file_is_zero(health_path):
    from data_pipeline import api_budget
    assert api_budget.spend_today() == 0


def test_spend_today_unreadable_file_fails_closed(health_path):
    from data_pipeline import api_budget
    health_path.write_bytes(b"not a parquet file")
    with pytest.raises(api_budget.BudgetError):
        api_budget.spend_today()


# ── allowances: ops and backfill are separate, both fail closed ──────────────
def test_ops_and_backfill_allowances_are_separate(health_path, monkeypatch):
    """Ops budget 40 on the free plan (100/day): 45 requests spent exhausts ops
    but not the backfill allowance (100 - 40 = 60) — the two must fail
    independently, so a backfill can never eat the daily refresh's capacity
    and vice versa."""
    from data_pipeline import api_budget
    monkeypatch.setenv("API_FOOTBALL_PLAN", "free")
    monkeypatch.setenv("API_FOOTBALL_OPS_BUDGET", "40")
    now = datetime(2026, 8, 8, 12, 0, tzinfo=timezone.utc)
    _write_health(health_path,
                  [_row("api_football", now - timedelta(minutes=i + 1))
                   for i in range(45)])
    with pytest.raises(api_budget.BudgetExceeded):
        api_budget.check_budget("ops", now=now)
    api_budget.check_budget("backfill", now=now)  # 45 < 60 — must not raise


def test_backfill_refused_when_plan_cannot_reserve_ops(health_path, monkeypatch):
    """Free plan daily (100) minus the default ops reserve (500) is negative:
    the backfill allowance floors at 0, so any backfill request is refused
    even with zero spend. Backfill is a paid-plan activity by construction."""
    from data_pipeline import api_budget
    monkeypatch.setenv("API_FOOTBALL_PLAN", "free")
    monkeypatch.delenv("API_FOOTBALL_OPS_BUDGET", raising=False)
    with pytest.raises(api_budget.BudgetExceeded):
        api_budget.check_budget("backfill")


def test_check_budget_under_allowance_passes(health_path, monkeypatch):
    from data_pipeline import api_budget
    monkeypatch.setenv("API_FOOTBALL_PLAN", "free")
    now = datetime(2026, 8, 8, 12, 0, tzinfo=timezone.utc)
    _write_health(health_path, [_row("api_football", now - timedelta(hours=1))])
    api_budget.check_budget("ops", now=now)  # 1 < 100 — must not raise


# ── plan assertion from response headers (silent-lapse guard) ────────────────
def test_assert_plan_raises_on_free_tier_headers(monkeypatch):
    """Expected pro (7,500/day) but the response headers say 100/day: the
    subscription lapsed to Free. This must be loud, never a quiet regression
    to 2024-capped data."""
    from data_pipeline import api_budget
    monkeypatch.setenv("API_FOOTBALL_PLAN", "pro")
    with pytest.raises(api_budget.PlanMismatch):
        api_budget.assert_plan({"x-ratelimit-requests-limit": "100"})


def test_assert_plan_header_lookup_is_case_insensitive(monkeypatch):
    from data_pipeline import api_budget
    monkeypatch.setenv("API_FOOTBALL_PLAN", "pro")
    with pytest.raises(api_budget.PlanMismatch):
        api_budget.assert_plan({"X-RateLimit-Requests-Limit": "100"})


def test_assert_plan_matching_headers_pass(monkeypatch):
    from data_pipeline import api_budget
    monkeypatch.setenv("API_FOOTBALL_PLAN", "free")
    api_budget.assert_plan({"x-ratelimit-requests-limit": "100"})  # no raise


def test_assert_plan_missing_header_is_noop(monkeypatch):
    from data_pipeline import api_budget
    monkeypatch.setenv("API_FOOTBALL_PLAN", "pro")
    api_budget.assert_plan({})  # no raise


def test_unknown_plan_name_fails_closed(monkeypatch):
    from data_pipeline import api_budget
    monkeypatch.setenv("API_FOOTBALL_PLAN", "premium-deluxe")
    with pytest.raises(api_budget.BudgetError):
        api_budget.expected_plan()


# ── throttle: ≤50% of the plan's per-minute limit ────────────────────────────
def test_throttle_delay_is_half_the_plan_rate(monkeypatch):
    from data_pipeline import api_budget
    monkeypatch.setenv("API_FOOTBALL_PLAN", "pro")     # 300 r/m
    assert api_budget.throttle_delay() == pytest.approx(0.4)  # 60 / (300 * 0.5)


def test_throttle_delay_default_plan_is_free(monkeypatch):
    from data_pipeline import api_budget
    monkeypatch.delenv("API_FOOTBALL_PLAN", raising=False)
    assert api_budget.throttle_delay() == pytest.approx(12.0)  # 60 / (10 * 0.5)
