"""Owner-only server lifecycle scorecard."""
from __future__ import annotations

import hmac
import json
import os

from server.growth_events import scorecard
from server.kv_client import get_kv


def handle(method: str, headers: dict):
    expected = os.environ.get("ADMIN_TOKEN", "")
    presented = headers.get("X-Admin-Token") or headers.get("x-admin-token") or ""
    if not expected or not hmac.compare_digest(presented, expected):
        status, payload = 401, {"error": "admin authorization required"}
    elif method != "GET":
        status, payload = 405, {"error": "method not allowed"}
    else:
        status, payload = 200, scorecard(get_kv())
    return status, {
        "Content-Type": "application/json",
        "Cache-Control": "no-store",
    }, json.dumps(payload, separators=(",", ":")).encode()
