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


def get_state(kv: KVStore) -> dict:
    """Current promo state as a JSON-safe dict. Always has an `active` key."""
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
