"""API-Football budget governor — fail-closed spend control and plan assertion.

Spec: docs/superpowers/specs/2026-08-08-api-football-migration-execution-spec.md
(§4.1 plan economics, §6.4 budget governor). Design constraints, in order:

1. **Fails closed.** If spend cannot be counted, no request is made. A data
   path that silently keeps spending is how you find out from an invoice.
2. **Ops and backfill are separate allowances.** A one-off backfill can never
   eat the daily refresh's capacity: ops draws from a small reserved budget,
   backfill from what the plan leaves above that reserve. On the free plan the
   backfill allowance is 0 by construction — backfill is a paid-plan activity.
3. **A lapse must look like an outage.** There is no auto-renewal; an expired
   subscription silently reverts to Free, whose seasons cap at 2024. Every
   response's rate-limit headers state the plan's daily quota; assert_plan()
   raises the moment they disagree with the configured expectation.
4. **Never look like a spike.** The terms allow blocking accounts for abnormal
   traffic; bulk jobs pace at ≤50% of the plan's per-minute limit.

Spend is counted from data/source_health.parquet (every API-Football call is
already recorded there — spend is a query, not a guess), since 00:00 UTC, the
provider's quota-reset boundary.

Configuration (env): API_FOOTBALL_PLAN = free|pro|ultra|mega (default free);
API_FOOTBALL_OPS_BUDGET = requests/day reserved for operations (default 500).
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Mapping

import pandas as pd

# Verified from the owner's pricing screenshot + pasted terms, 2026-08-08.
PLANS: dict[str, dict[str, int]] = {
    "free":  {"daily": 100,     "rpm": 10},
    "pro":   {"daily": 7_500,   "rpm": 300},
    "ultra": {"daily": 75_000,  "rpm": 450},
    "mega":  {"daily": 150_000, "rpm": 900},
}

_DEFAULT_OPS_BUDGET = 500          # steady state measures ~50–150/day
_THROTTLE_FRACTION = 0.5           # of the plan's per-minute limit
_DAILY_LIMIT_HEADER = "x-ratelimit-requests-limit"


class BudgetError(RuntimeError):
    """Governor cannot make a safe decision (bad config, unreadable spend)."""


class BudgetExceeded(BudgetError):
    """The requested spend kind has no allowance left today."""


class PlanMismatch(BudgetError):
    """Response headers disagree with the configured plan — likely a lapse."""


def expected_plan() -> str:
    """The plan we believe we are on (env API_FOOTBALL_PLAN, default free).

    Consults the repo-root .env first: budget checks run BEFORE the first
    request, so waiting for the request path's dotenv load would leave a
    fresh process on the free-plan default and refuse a paid backfill."""
    from data_pipeline.api_football import _load_dotenv
    _load_dotenv()
    name = os.environ.get("API_FOOTBALL_PLAN", "free").strip().lower()
    if name not in PLANS:
        raise BudgetError(
            f"API_FOOTBALL_PLAN={name!r} is not one of {sorted(PLANS)} — "
            "refusing to guess a budget."
        )
    return name


def _ops_budget(plan: str) -> int:
    env = os.environ.get("API_FOOTBALL_OPS_BUDGET")
    ops = int(env) if env else _DEFAULT_OPS_BUDGET
    return min(ops, PLANS[plan]["daily"])


def spend_today(now: datetime | None = None) -> int:
    """API-Football requests recorded since 00:00 UTC (success and failure —
    both hit the API). Missing health file means zero recorded spend; an
    unreadable one fails closed."""
    from data_pipeline import source_health
    path = source_health._HEALTH_PATH
    if not path.exists():
        return 0
    try:
        df = pd.read_parquet(path, columns=["source_name", "fetched_at"])
    except Exception as exc:
        raise BudgetError(f"cannot count spend from {path}: {exc}") from exc
    now = now or datetime.now(timezone.utc)
    midnight = now.astimezone(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0)
    fetched = pd.to_datetime(df["fetched_at"], utc=True, errors="coerce", format="ISO8601")
    return int(((df["source_name"] == "api_football") & (fetched >= midnight)).sum())


def check_budget(kind: str = "ops", now: datetime | None = None) -> None:
    """Raise BudgetExceeded when `kind` ("ops" | "backfill") has no allowance
    left today. Call before every request; a refusal makes no request and
    records no spend."""
    plan = expected_plan()
    daily = PLANS[plan]["daily"]
    ops = _ops_budget(plan)
    if kind == "ops":
        allowance = ops
    elif kind == "backfill":
        allowance = max(daily - ops, 0)
    else:
        raise BudgetError(f"unknown budget kind {kind!r} (ops|backfill)")
    spent = spend_today(now=now)
    if spent >= allowance:
        raise BudgetExceeded(
            f"{kind} budget exhausted: {spent} spent today >= {allowance} "
            f"allowed (plan={plan}, daily cap={daily})."
        )


def assert_plan(headers: Mapping[str, str]) -> None:
    """Compare the response's daily-quota header against the configured plan.
    Raises PlanMismatch on disagreement — the silent-lapse guard. Missing
    header is a no-op (the provider owns the header contract, not us)."""
    lowered = {str(k).lower(): v for k, v in headers.items()}
    raw = lowered.get(_DAILY_LIMIT_HEADER)
    if raw is None:
        return
    try:
        limit = int(str(raw).strip())
    except ValueError:
        return
    plan = expected_plan()
    if limit != PLANS[plan]["daily"]:
        raise PlanMismatch(
            f"API reports a daily quota of {limit}, but API_FOOTBALL_PLAN="
            f"{plan} expects {PLANS[plan]['daily']}. If {limit} is the free "
            "tier, the subscription has lapsed — renew before refreshing, or "
            "current seasons will silently stop updating."
        )


def throttle_delay() -> float:
    """Seconds to wait between requests: paces at ≤50% of the plan's
    per-minute limit so bulk jobs never resemble a traffic spike."""
    rpm = PLANS[expected_plan()]["rpm"]
    return 60.0 / (rpm * _THROTTLE_FRACTION)
