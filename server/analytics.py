"""Privacy-limited outcome analytics; raw questions and notes are rejected."""
from __future__ import annotations

import datetime as dt

from server.kv_store import KVStore

ALLOWED_EVENTS = {
    "hub_activation", "brief_open", "why_expanded", "scenario_completed",
    "alert_clicked", "receipt_opened", "card_created", "card_shared",
    "thesis_opened", "watchpoint_opened", "analog_opened",
    "journal_checkpoint_created", "creator_exported", "return_30d", "return_90d",
}
ALLOWED_PROPERTIES = {"feature_id", "league_id", "calendar_mode", "plan", "surface"}


def record(kv: KVStore, event: str, properties: dict) -> int:
    if event not in ALLOWED_EVENTS:
        raise ValueError("unsupported analytics event")
    unknown = set(properties) - ALLOWED_PROPERTIES
    if unknown:
        raise ValueError(f"unsupported analytics properties: {sorted(unknown)}")
    day = dt.datetime.now(dt.timezone.utc).date().isoformat()
    return kv.increment(f"analytics:{day}:{event}", ex=400 * 24 * 3600)
