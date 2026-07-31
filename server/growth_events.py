"""Privacy-limited growth and lifecycle event ledger.

GA4 remains the canonical browser analytics implementation. This ledger covers
authoritative server events that a browser cannot prove: registration,
activation, checkout creation, Stripe lifecycle, delivery status, and current
entitlement. Values never include an email address or private user content.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import uuid

from server.intel_store import export_user_data
from server.kv_store import KVStore

INDEX_KEY = "growth_events:index"
RETENTION_SECONDS = 800 * 24 * 60 * 60

CORE_VALUE_EVENTS = {
    "material_change_explanation_viewed",
    "match_stakes_viewed",
    "since_last_visit_viewed",
}

ALLOWED_EVENTS = {
    "club_page_view", "track_club", "registration_start",
    "registration_complete", "sample_update_view", "activation",
    "upgrade_view", "checkout_start", "purchase", "renewal",
    "cancellation_requested", "expiration", "refund", "failed_payment",
    "payment_recovered", "pause", "reactivation",
    "material_change_explanation_viewed", "match_stakes_viewed",
    "since_last_visit_viewed", "scenario_run", "scenario_saved",
    "return_visit", "notification_setting_change",
    "alert_sent", "alert_delivered", "alert_opened", "alert_clicked",
    "alert_failed", "briefing_sent", "briefing_delivered",
    "briefing_opened", "briefing_clicked", "briefing_failed",
    "delivery_corrected", "delivery_duplicated", "delivery_suppressed",
    "cancellation_reason_submitted", "support_request_categorized",
    "testimonial_consented",
}

ALLOWED_PROPERTIES = {
    "club_id", "club_name", "competition_id", "competition_name", "country",
    "device", "landing_page", "campaign", "source", "medium", "referrer",
    "creator", "experiment_id", "experiment_cell", "club_rate_milestone",
    "plan", "interval", "price_tier", "currency", "value", "status",
    "provider", "template_version", "calendar_mode", "surface", "feature_id",
    "reason", "consent_level",
}


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _key(event_id: str) -> str:
    digest = hashlib.sha256(event_id.encode("utf-8")).hexdigest()
    return f"growth_event:{digest}"


def record_event(
    kv: KVStore,
    event: str,
    *,
    event_id: str | None = None,
    user_id: str | None = None,
    properties: dict | None = None,
    occurred_at: str | None = None,
) -> dict:
    """Write one idempotent lifecycle event and return its stored record."""
    if event not in ALLOWED_EVENTS:
        raise ValueError(f"unsupported growth event: {event}")
    properties = properties or {}
    unknown = set(properties) - ALLOWED_PROPERTIES
    if unknown:
        raise ValueError(f"unsupported growth properties: {sorted(unknown)}")
    stable_id = event_id or f"{event}:{uuid.uuid4()}"
    key = _key(stable_id)
    existing = kv.get(key)
    if existing is not None:
        return json.loads(existing)
    record = {
        "event_id": stable_id,
        "event": event,
        "occurred_at": occurred_at or _now(),
        "user_id": user_id,
        "properties": properties,
    }
    encoded = json.dumps(record, separators=(",", ":"), sort_keys=True)
    kv.set(key, encoded, ex=RETENTION_SECONDS)
    kv.add_to_set(INDEX_KEY, key)
    if user_id:
        kv.set(f"growth_last:{user_id}:{event}", record["occurred_at"],
               ex=RETENTION_SECONDS)
    return record


def read_events(kv: KVStore) -> list[dict]:
    rows = []
    for key in kv.members(INDEX_KEY):
        raw = kv.get(key)
        if raw is None:
            continue
        try:
            rows.append(json.loads(raw))
        except (TypeError, ValueError):
            continue
    return sorted(rows, key=lambda row: row.get("occurred_at") or "")


def scorecard(kv: KVStore, now: dt.datetime | None = None) -> dict:
    """Build the server-verifiable part of the weekly growth scorecard."""
    now = now or dt.datetime.now(dt.timezone.utc)
    events = read_events(kv)
    counts: dict[str, int] = {}
    unique_users: dict[str, set[str]] = {}
    for row in events:
        event = row["event"]
        counts[event] = counts.get(event, 0) + 1
        if row.get("user_id"):
            unique_users.setdefault(event, set()).add(row["user_id"])

    active_ids = set()
    for user_id in kv.members("users:index"):
        record = export_user_data(kv, user_id)
        if not record:
            continue
        lifecycle = record.get("subscription_lifecycle") or {}
        if (record.get("plan") in {"intel", "creator"}
                and lifecycle.get("status") != "refunded"):
            active_ids.add(user_id)

    engaged_ids = set()
    cutoff = now - dt.timedelta(days=30)
    for row in events:
        if row["event"] not in CORE_VALUE_EVENTS or row.get("user_id") not in active_ids:
            continue
        try:
            occurred = dt.datetime.fromisoformat(row["occurred_at"])
        except (TypeError, ValueError):
            continue
        if occurred >= cutoff:
            engaged_ids.add(row["user_id"])

    return {
        "generated_at": now.isoformat(),
        "labels": {
            "server_lifecycle": "known",
            "active_paid": "known",
            "engaged_paid": "known",
            "mau": "missing",
            "qualified_club_intent_visitors": "missing",
            "ga4_conversion_rates": "missing",
        },
        "counts": counts,
        "unique_users": {key: len(value) for key, value in unique_users.items()},
        "active_paid": len(active_ids),
        "engaged_paid": len(engaged_ids),
        "missing_inputs": [
            "GA4 traffic and qualified-visitor export",
            "Google Search Console export",
            "coded support and cancellation export",
        ],
    }
