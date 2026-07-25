#!/usr/bin/env python3
"""Which price new customers are offered — a runtime switch, not a redeploy.

Launch is $5.99/mo with the option to lift to $7.99 later (owner decision
2026-07-25). A Stripe Price object is **immutable** in amount, currency and
interval, so "changing the price" is never an edit -- it is pointing new
Checkout Sessions at a different, pre-created Price. Everyone already
subscribed stays on the Price they bought, which Stripe handles on its own:
that is what makes a price lift safe, and what makes the founding rate a
promise you can actually keep.

Design notes, mirroring server.open_access (the other owner-operated lever):

- **The switch is KV state, not an env var.** Flipping a price must not require
  a redeploy: the lift may well land during the Aug 15 code freeze, and it must
  be reversible in seconds if conversion falls off a cliff.
- **Display and charge resolve from the same place.** `/v1/public/config` quotes
  the active tier's Price and checkout charges the active tier's Price, so the
  two cannot drift. Quoting one number and billing another is the failure mode
  this whole mechanism exists to prevent.
- **Fail low, never high.** An unset, unknown or unconfigured tier resolves to
  `launch`. If a config mistake must charge the wrong amount, it charges the
  lower one -- undercharging is a business problem, overcharging is a refund,
  a chargeback and a trust story.
- **A tier with no configured Price cannot be selected.** `set_tier` refuses it,
  so the switch can never point at nothing and 503 the checkout button.
"""
from __future__ import annotations

import os
import time

from server.kv_store import KVStore

KEY = "config:pricing_tier"
DEFAULT_TIER = "launch"
TIERS = ("launch", "standard")
INTERVALS = ("monthly", "annual")

# (tier, interval) -> env var holding the Stripe Price id.
# STRIPE_INTEL_PRICE_ID is the pre-existing single-price name, kept as the
# launch-monthly fallback so an environment configured before this switch
# existed keeps working unchanged.
_ENV_MATRIX = {
    ("launch", "monthly"): ("STRIPE_PRICE_INTEL_MONTHLY_LAUNCH", "STRIPE_INTEL_PRICE_ID"),
    ("launch", "annual"): ("STRIPE_PRICE_INTEL_ANNUAL_LAUNCH",),
    ("standard", "monthly"): ("STRIPE_PRICE_INTEL_MONTHLY_STANDARD",),
    ("standard", "annual"): ("STRIPE_PRICE_INTEL_ANNUAL_STANDARD",),
}


def normalise_interval(interval: str | None) -> str:
    return "annual" if str(interval or "").lower() in ("annual", "year", "yearly") else "monthly"


def price_id_for(tier: str, interval: str) -> str:
    """The configured Stripe Price id, or "" when that combination is unset."""
    for name in _ENV_MATRIX.get((tier, normalise_interval(interval)), ()):
        value = os.environ.get(name, "")
        if value:
            return value
    return ""


def configured_tiers() -> dict[str, list[str]]:
    """Which (tier, interval) combinations actually have a Price id set."""
    out: dict[str, list[str]] = {}
    for tier in TIERS:
        available = [i for i in INTERVALS if price_id_for(tier, i)]
        if available:
            out[tier] = available
    return out


def get_tier(kv: KVStore) -> str:
    """The tier new checkouts are currently priced at.

    Resolves to `launch` for anything unexpected -- unset, an unknown value, or
    a tier whose Price ids have since been removed from the environment.
    """
    raw = kv.get(KEY)
    tier = raw.strip() if isinstance(raw, str) else ""
    if tier not in TIERS or not price_id_for(tier, "monthly"):
        return DEFAULT_TIER
    return tier


def set_tier(kv: KVStore, tier: str, note: str = "") -> dict:
    """Point new checkouts at `tier`. Raises ValueError if it isn't sellable."""
    if tier not in TIERS:
        raise ValueError(f"tier must be one of {', '.join(TIERS)}")
    if not price_id_for(tier, "monthly"):
        raise ValueError(
            f"tier {tier!r} has no Stripe Price configured; create the Price and set "
            f"{_ENV_MATRIX[(tier, 'monthly')][0]} before switching to it")
    kv.set(KEY, tier)
    kv.set(f"{KEY}:changed_at", str(int(time.time())))
    if note:
        kv.set(f"{KEY}:note", str(note)[:200])
    return get_state(kv)


def get_state(kv: KVStore) -> dict:
    changed_at = kv.get(f"{KEY}:changed_at")
    try:
        changed = int(changed_at) if changed_at else None
    except (TypeError, ValueError):
        changed = None
    tier = get_tier(kv)
    return {
        "tier": tier,
        "intervals": configured_tiers().get(tier, []),
        "changed_at": changed,
        "note": kv.get(f"{KEY}:note") or "",
        "available": configured_tiers(),
    }
