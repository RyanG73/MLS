"""Verify and process Resend/Svix delivery webhooks."""
from __future__ import annotations

import base64
import datetime as dt
import hashlib
import hmac
import json
import time

from server.config import required_secret
from server.intel_store import export_user_data, update_preferences
from server.kv_store import KVStore
from server.send_ledger import update_provider_status


class InvalidResendWebhook(Exception):
    pass


def verify(payload: bytes, headers: dict, now: float | None = None) -> str:
    message_id = headers.get("svix-id") or headers.get("Svix-Id")
    timestamp = headers.get("svix-timestamp") or headers.get("Svix-Timestamp")
    signatures = headers.get("svix-signature") or headers.get("Svix-Signature")
    if not message_id or not timestamp or not signatures:
        raise InvalidResendWebhook("missing Svix signature headers")
    now = now or time.time()
    if abs(now - int(timestamp)) > 300:
        raise InvalidResendWebhook("webhook timestamp outside tolerance")
    secret = required_secret("RESEND_WEBHOOK_SECRET", "whsec_ZGV2LXNlY3JldA==")
    encoded_secret = secret[6:] if secret.startswith("whsec_") else secret
    try:
        key = base64.b64decode(encoded_secret)
    except ValueError as exc:
        raise InvalidResendWebhook("invalid webhook secret") from exc
    signed = f"{message_id}.{timestamp}.".encode() + payload
    expected = base64.b64encode(hmac.new(key, signed, hashlib.sha256).digest()).decode()
    candidates = [part.split(",", 1)[1] for part in signatures.split()
                  if part.startswith("v1,")]
    if not any(hmac.compare_digest(candidate, expected) for candidate in candidates):
        raise InvalidResendWebhook("webhook signature mismatch")
    return message_id


def process(kv: KVStore, message_id: str, event: dict) -> dict | None:
    dedup = f"resend_webhook:{message_id}"
    if kv.exists(dedup):
        return None
    kv.set(dedup, "1", ex=30 * 24 * 3600)
    event_type = event.get("type", "")
    provider_id = (event.get("data") or {}).get("email_id")
    if not provider_id:
        return None
    status = event_type.removeprefix("email.")
    record = update_provider_status(kv, provider_id, status)
    if record and event_type == "email.bounced":
        user = export_user_data(kv, record["user_id"])
        if user:
            state = dict(user.get("alert_state") or {})
            state["bounced"] = True
            state["bounced_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
            update_preferences(kv, record["user_id"], alert_state=state)
    return record
