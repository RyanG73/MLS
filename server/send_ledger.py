"""KV-backed notification deduplication, cap, and provider-status ledger."""
from __future__ import annotations

import datetime as dt
import hashlib
import json

from server.kv_store import KVStore


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
        "updated_at": now,
    }
    kv.set(key, json.dumps(record, separators=(",", ":")), ex=180 * 24 * 3600)
    kv.add_to_set("send_ledger:index", key)
    if provider_id:
        kv.set(f"provider_send:{provider_id}", json.dumps(record, separators=(",", ":")),
               ex=180 * 24 * 3600)
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
