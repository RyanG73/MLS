"""Owner-operated checkout kill switch and readiness report."""
from __future__ import annotations

import hmac
import json
import os

from server import checkout_control
from server.kv_client import get_kv


def _authorized(headers: dict) -> bool:
    expected = os.environ.get("ADMIN_TOKEN", "")
    presented = headers.get("X-Admin-Token") or headers.get("x-admin-token") or ""
    return bool(expected) and hmac.compare_digest(presented, expected)


def _json(status: int, payload):
    return status, {
        "Content-Type": "application/json",
        "Cache-Control": "no-store",
    }, json.dumps(payload, separators=(",", ":")).encode()


def handle(method: str, headers: dict, body: bytes = b""):
    if not _authorized(headers):
        return _json(401, {"error": "admin authorization required"})
    if method == "GET":
        return _json(200, checkout_control.get_state(get_kv()))
    if method == "POST":
        try:
            payload = json.loads(body or b"{}")
        except json.JSONDecodeError:
            return _json(400, {"error": "invalid JSON"})
        if not isinstance(payload, dict) or not isinstance(payload.get("enabled"), bool):
            return _json(400, {"error": "enabled must be a boolean"})
        return _json(200, checkout_control.set_enabled(
            get_kv(), payload["enabled"], str(payload.get("note", ""))))
    return _json(405, {"error": "method not allowed"})
