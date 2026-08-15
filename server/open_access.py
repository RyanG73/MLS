#!/usr/bin/env python3
"""Open-access promo switch: temporarily drop the paid-plan requirement on
Intel endpoints for a marketing push, without touching anyone's real plan.

Design notes:

- **Authentication is never bypassed.** A promo waives the *plan rank* check
  only; a valid access token is still required. Intel is per-user (workspaces,
  journal, saved teams, alert state), so an anonymous caller would have nowhere
  to write. Free signup stays the front door.
- **Every promo carries an expiry.** The flag is written with a KV TTL *and* an
  explicit `until` timestamp, and `is_open()` re-checks the timestamp on read.
  Belt and braces: a store whose TTL support is weak still can't leave the site
  free forever, which is the failure mode that actually costs money.
- **`canceled` is not "free".** A canceled account is a deliberate state, so a
  promo must not resurrect it. See PLAN_RANK in server.api_support, where
  canceled ranks -1 and free ranks 0.
"""
from __future__ import annotations

import json
import time

from server.kv_store import KVStore

KEY = "config:open_access"
MAX_PROMO_SECONDS = 90 * 24 * 3600   # a promo longer than a quarter is a typo


# ─────────────────────────────────────────────────────────────────────────────
# FREE LAUNCH — the paywall is off. Owner decision, 2026-08-15.
#
#   To bring the paywall back:  set LAUNCH_FREE = False, and deploy.
#
# That is the whole operation. Nothing else needs undoing — no code was removed
# to get here. Every paid mechanism is still present, still tested, and still
# in the path: the plan ranks, `require_entitlement`, the Stripe webhook that
# writes an entitlement, the client's lock chrome, the checkout gate. This flag
# only makes `is_open()` answer True, which is the single question all of them
# already ask.
#
# Deliberately a committed constant rather than the KV promo below:
#
# - **It ships with the deploy.** The promo lives in KV and is set by an admin
#   call against production, so a KV outage, a restore, or a fresh environment
#   would silently re-lock the site. A launch that costs nothing must not
#   depend on a network write staying put.
# - **It has no expiry, and the promo must keep its own.** MAX_PROMO_SECONDS
#   exists because "a store whose TTL support is weak still can't leave the
#   site free forever, which is the failure mode that actually costs money."
#   That guard is right, and is left exactly as it was. Free launch is not a
#   promo that forgot to end — it is a different, deliberate state, so it gets
#   its own switch instead of weakening the one protecting the other case.
# - **It is greppable.** One constant, one name, one comment. The state of the
#   paywall should never require reading three modules to determine.
#
# What this does NOT change: authentication. Open access has always meant "no
# payment required", never "no account required" — Club Watch state is per-user
# (saved clubs, scenarios, journal, alert state) and needs somewhere to live.
# The public site — tables, forecasts, Next 5 Sim, club and league pages,
# Global ELO — was already free to view with no account at all, and still is.
# ─────────────────────────────────────────────────────────────────────────────
LAUNCH_FREE = True
LAUNCH_FREE_NOTE = "free during launch"


def launch_state() -> dict | None:
    """The free-launch state, or None when the paywall is on.

    Checked before KV on purpose: while the paywall is off, the site must not
    be able to re-lock itself because a key/value store was unreachable.
    """
    if not LAUNCH_FREE:
        return None
    # No `until`. Clients must treat `indefinite` as "open, with no countdown"
    # rather than inventing an expiry — see OpenAccess.state() in the web app.
    return {"active": True, "indefinite": True, "note": LAUNCH_FREE_NOTE}


def get_state(kv: KVStore) -> dict:
    """Current open-access state as a JSON-safe dict. Always has an `active` key."""
    launch = launch_state()
    if launch is not None:
        return launch
    raw = kv.get(KEY)
    if raw is None:
        return {"active": False}
    try:
        record = json.loads(raw)
    except (ValueError, TypeError):
        return {"active": False}
    until = record.get("until", 0)
    if not isinstance(until, (int, float)) or until <= time.time():
        return {"active": False}
    return {"active": True, "until": int(until), "note": record.get("note", "")}


def is_open(kv: KVStore) -> bool:
    return get_state(kv)["active"] is True


def open_promo(kv: KVStore, until: int, note: str = "") -> dict:
    """Open access until the `until` epoch. Raises ValueError for a window
    that is already past or implausibly long."""
    now = time.time()
    if until <= now:
        raise ValueError("promo expiry must be in the future")
    if until - now > MAX_PROMO_SECONDS:
        raise ValueError(f"promo may not run longer than {MAX_PROMO_SECONDS // 86400} days")
    kv.set(KEY, json.dumps({"until": int(until), "note": str(note)[:200]}),
           ex=int(until - now) + 60)
    return get_state(kv)


def close_promo(kv: KVStore) -> dict:
    kv.delete(KEY)
    return get_state(kv)
