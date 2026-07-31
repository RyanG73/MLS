"""KV-backed notification deduplication, cap, and provider-status ledger."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import uuid

from server.kv_store import KVStore
from server.growth_events import record_event

DELIVERY_OUTCOMES = {"corrected", "duplicated", "suppressed"}
SHADOW_REVIEW_DEFECTS = {
    "wrong_team", "wrong_outcome", "wrong_price", "duplicate",
    "unsupported_cause", "not_worth_sending", "other",
}


def delivery_key(user_id: str, event_ids: list[str], template_version: str) -> str:
    raw = f"{user_id}|{','.join(sorted(event_ids))}|{template_version}"
    return "send:" + hashlib.sha256(raw.encode()).hexdigest()


def already_sent(kv: KVStore, user_id: str, event_ids: list[str],
                 template_version: str, include_shadow: bool = True) -> bool:
    raw = kv.get(delivery_key(user_id, event_ids, template_version))
    if raw is None:
        return False
    status = json.loads(raw).get("status")
    if status == "shadow" and not include_shadow:
        return False
    return status not in {"failed", "retrying"}


def retry_allowed(kv: KVStore, user_id: str, event_ids: list[str],
                  template_version: str, max_attempts: int = 3) -> bool:
    raw = kv.get(delivery_key(user_id, event_ids, template_version))
    return raw is None or int(json.loads(raw).get("attempts", 0)) < max_attempts


def record_delivery(kv: KVStore, *, user_id: str, team_ids: list[str],
                    event_ids: list[str], template_version: str,
                    status: str, provider_id: str | None = None,
                    error_code: str | None = None) -> dict:
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    key = delivery_key(user_id, event_ids, template_version)
    previous_raw = kv.get(key)
    previous = json.loads(previous_raw) if previous_raw else {}
    record = {
        "user_id": user_id, "team_ids": team_ids, "event_ids": event_ids,
        "template_version": template_version, "status": status,
        "provider_id": provider_id, "error_code": error_code,
        "attempts": int(previous.get("attempts", 0)) + 1,
        "created_at": previous.get("created_at") or now,
        "updated_at": now,
    }
    kv.set(key, json.dumps(record, separators=(",", ":")), ex=180 * 24 * 3600)
    kv.add_to_set("send_ledger:index", key)
    if provider_id:
        kv.set(f"provider_send:{provider_id}", json.dumps(record, separators=(",", ":")),
               ex=180 * 24 * 3600)
    kind = "briefing" if template_version.startswith("personalized-briefing") else "alert"
    if status in {"sent", "failed"}:
        record_event(
            kv, f"{kind}_{status}",
            event_id=f"{key}:{status}",
            user_id=user_id,
            properties={
                "provider": "resend",
                "template_version": template_version,
                "status": status,
            },
            occurred_at=now)
    return record


def update_provider_status(kv: KVStore, provider_id: str, status: str) -> dict | None:
    raw = kv.get(f"provider_send:{provider_id}")
    if raw is None:
        return None
    record = json.loads(raw)
    record["status"] = status
    record["updated_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
    encoded = json.dumps(record, separators=(",", ":"))
    kv.set(f"provider_send:{provider_id}", encoded, ex=180 * 24 * 3600)
    kv.set(delivery_key(record["user_id"], record["event_ids"],
                        record["template_version"]), encoded, ex=180 * 24 * 3600)
    kind = ("briefing" if record["template_version"].startswith(
        "personalized-briefing") else "alert")
    event_status = {
        "delivered": "delivered",
        "opened": "opened",
        "clicked": "clicked",
        "failed": "failed",
        "bounced": "failed",
        "complained": "failed",
    }.get(status)
    if event_status:
        record_event(
            kv, f"{kind}_{event_status}",
            event_id=f"provider:{provider_id}:{status}",
            user_id=record["user_id"],
            properties={
                "provider": "resend",
                "template_version": record["template_version"],
                "status": status,
            })
    return record


def record_delivery_outcome(
    kv: KVStore,
    *,
    user_id: str,
    template_version: str,
    status: str,
    reason: str,
    team_ids: list[str] | None = None,
    event_ids: list[str] | None = None,
    delivery_ref: str | None = None,
) -> dict:
    """Record a non-provider delivery outcome for QA and suppression review."""
    if status not in DELIVERY_OUTCOMES:
        raise ValueError(f"unsupported delivery outcome: {status}")
    clean_reason = str(reason or "").strip()[:160]
    if not clean_reason:
        raise ValueError("delivery outcome reason is required")
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    key = f"send_outcome:{uuid.uuid4()}"
    record = {
        "user_id": user_id,
        "team_ids": list(team_ids or []),
        "event_ids": list(event_ids or []),
        "template_version": template_version,
        "status": status,
        "reason": clean_reason,
        "delivery_ref": str(delivery_ref or "")[:160] or None,
        "attempts": 0,
        "updated_at": now,
    }
    kv.set(key, json.dumps(record, separators=(",", ":")),
           ex=180 * 24 * 3600)
    kv.add_to_set("send_ledger:index", key)
    record_event(
        kv,
        f"delivery_{status}",
        event_id=f"{key}:{status}",
        user_id=user_id,
        properties={
            "template_version": template_version,
            "status": status,
            "reason": clean_reason,
        },
        occurred_at=now,
    )
    return record


def review_shadow_delivery(
    kv: KVStore,
    *,
    user_id: str,
    event_ids: list[str],
    template_version: str,
    worth_sending: bool,
    defects: list[str] | None = None,
    notes: str = "",
) -> dict:
    """Attach a bounded human QA decision to an existing shadow candidate."""
    if not isinstance(worth_sending, bool):
        raise ValueError("worth_sending must be a boolean")
    clean_defects = sorted({
        str(value).strip() for value in (defects or []) if str(value).strip()
    })
    unknown = set(clean_defects) - SHADOW_REVIEW_DEFECTS
    if unknown:
        raise ValueError(f"unsupported shadow review defects: {sorted(unknown)}")
    key = delivery_key(user_id, event_ids, template_version)
    raw = kv.get(key)
    if raw is None:
        raise ValueError("shadow delivery not found")
    record = json.loads(raw)
    if record.get("status") != "shadow":
        raise ValueError("only shadow deliveries can be reviewed")
    record.update({
        "reviewed_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "worth_sending": worth_sending,
        "defects": clean_defects,
        "review_notes": str(notes or "").strip()[:500],
    })
    encoded = json.dumps(record, separators=(",", ":"))
    kv.set(key, encoded, ex=180 * 24 * 3600)
    return record


def within_team_cap(last_sent_at: str | None, hours: int = 24,
                    now: dt.datetime | None = None) -> bool:
    if not last_sent_at:
        return False
    now = now or dt.datetime.now(dt.timezone.utc)
    try:
        previous = dt.datetime.fromisoformat(last_sent_at)
    except ValueError:
        return False
    return now - previous < dt.timedelta(hours=hours)
