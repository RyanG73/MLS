"""POST /api/resend/webhook."""
from __future__ import annotations

import json

from server.api_support import response
from server.kv_client import get_kv
from server.resend_webhook import InvalidResendWebhook, process, verify


def handle(method: str, headers: dict, body: bytes):
    if method != "POST":
        return response(405, {"error": "method not allowed"})
    try:
        message_id = verify(body, headers)
        event = json.loads(body)
    except (InvalidResendWebhook, json.JSONDecodeError) as exc:
        return response(400, {"error": str(exc)})
    process(get_kv(), message_id, event)
    return response(200, {"received": True})
