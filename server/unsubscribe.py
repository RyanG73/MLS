"""Signed one-click unsubscribe tokens without exposing user emails."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time

from server.config import required_secret
from server.intel_store import export_user_data, update_preferences
from server.kv_store import KVStore


def _secret() -> str:
    return required_secret("UNSUBSCRIBE_SECRET", "dev-unsubscribe-secret")


def issue_unsubscribe_token(user_id: str, category: str, ttl: int = 180 * 24 * 3600) -> str:
    payload = base64.urlsafe_b64encode(json.dumps({
        "sub": user_id, "category": category, "exp": int(time.time()) + ttl,
    }, separators=(",", ":")).encode()).rstrip(b"=").decode()
    signature = hmac.new(_secret().encode(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}.{signature}"


def apply_unsubscribe(kv: KVStore, token: str) -> dict:
    try:
        payload, signature = token.rsplit(".", 1)
        expected = hmac.new(_secret().encode(), payload.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            raise ValueError("invalid unsubscribe token")
        decoded = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    except Exception as exc:
        raise ValueError("invalid unsubscribe token") from exc
    if decoded.get("exp", 0) < time.time():
        raise ValueError("expired unsubscribe token")
    record = export_user_data(kv, decoded["sub"])
    if record is None:
        raise ValueError("unknown unsubscribe token")
    state = dict(record.get("unsubscribe_state") or {})
    state[decoded["category"]] = True
    update_preferences(kv, decoded["sub"], unsubscribe_state=state)
    return {"status": "unsubscribed", "category": decoded["category"]}
