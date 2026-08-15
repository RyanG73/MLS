"""Owner kill switch and production checkout-readiness gate."""
from __future__ import annotations

import os
import time

from server import open_access
from server.kv_store import KVStore

KEY = "config:checkout"


def _production_missing(kv: KVStore) -> list[str]:
    required = {
        "STRIPE_SECRET_KEY": os.environ.get("STRIPE_SECRET_KEY"),
        "STRIPE_WEBHOOK_SECRET": os.environ.get("STRIPE_WEBHOOK_SECRET"),
        "ACCESS_TOKEN_SECRET": os.environ.get("ACCESS_TOKEN_SECRET"),
        "UPSTASH_REDIS_REST_URL": os.environ.get("UPSTASH_REDIS_REST_URL"),
        "UPSTASH_REDIS_REST_TOKEN": os.environ.get("UPSTASH_REDIS_REST_TOKEN"),
        "CUSTOMER_TERMS_APPROVED_VERSION":
            os.environ.get("CUSTOMER_TERMS_APPROVED_VERSION"),
        "PRIVACY_POLICY_APPROVED_VERSION":
            os.environ.get("PRIVACY_POLICY_APPROVED_VERSION"),
        "REFUND_POLICY_APPROVED_VERSION":
            os.environ.get("REFUND_POLICY_APPROVED_VERSION"),
        "STRIPE_PRICE_INTEL_MONTHLY_LAUNCH":
            os.environ.get("STRIPE_PRICE_INTEL_MONTHLY_LAUNCH"),
        "STRIPE_PRICE_INTEL_ANNUAL_LAUNCH":
            os.environ.get("STRIPE_PRICE_INTEL_ANNUAL_LAUNCH"),
        "STRIPE_PRICE_INTEL_MONTHLY_STANDARD":
            os.environ.get("STRIPE_PRICE_INTEL_MONTHLY_STANDARD"),
        "STRIPE_PRICE_INTEL_ANNUAL_STANDARD":
            os.environ.get("STRIPE_PRICE_INTEL_ANNUAL_STANDARD"),
    }
    missing = [name for name, value in required.items() if not value]
    return missing


def _requested(kv: KVStore) -> tuple[bool, str]:
    override = kv.get(KEY)
    if override == "enabled":
        return True, "owner_enabled"
    if override == "disabled":
        return False, "owner_disabled"
    return os.environ.get("CHECKOUT_ENABLED") == "true", "environment"


def get_state(kv: KVStore) -> dict:
    requested, source = _requested(kv)
    production = os.environ.get("ENTENSER_ENV") == "production"
    missing = _production_missing(kv) if production else []
    # Selling a subscription to something currently being given away is the one
    # combination that produces a refund and a broken promise at the same time.
    # While the paywall is off, checkout stays shut whatever else is configured
    # — including a fully-wired Stripe and an explicit owner_enabled override,
    # because the override predates the free launch and cannot have meant this.
    free_launch = open_access.launch_state() is not None
    enabled = requested and not missing and not free_launch
    reason = "ready" if enabled else (
        "free_launch" if free_launch else
        "configuration_incomplete" if requested and missing else "owner_disabled")
    changed_at = kv.get(f"{KEY}:changed_at")
    return {
        "enabled": enabled,
        "requested": requested,
        "reason": reason,
        "source": source,
        "changed_at": int(changed_at) if changed_at else None,
        "note": kv.get(f"{KEY}:note") or "",
        # Missing variable names are safe operational metadata for the
        # authenticated admin endpoint. The public config removes this field.
        "missing": missing,
    }


def set_enabled(kv: KVStore, enabled: bool, note: str = "") -> dict:
    kv.set(KEY, "enabled" if enabled else "disabled")
    kv.set(f"{KEY}:changed_at", str(int(time.time())))
    if note:
        kv.set(f"{KEY}:note", str(note)[:200])
    return get_state(kv)


def public_state(kv: KVStore) -> dict:
    state = get_state(kv)
    return {
        "enabled": state["enabled"],
        "reason": state["reason"],
        "changed_at": state["changed_at"],
    }
