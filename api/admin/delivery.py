"""Owner-only correction logging for notification QA."""
from __future__ import annotations

import hmac
import json
import os

from server.kv_client import get_kv
from server.send_ledger import record_delivery_outcome, review_shadow_delivery


def _json(status: int, payload):
    return status, {
        "Content-Type": "application/json",
        "Cache-Control": "no-store",
    }, json.dumps(payload, separators=(",", ":")).encode()


def handle(method: str, headers: dict, body: bytes = b""):
    expected = os.environ.get("ADMIN_TOKEN", "")
    presented = headers.get("X-Admin-Token") or headers.get(
        "x-admin-token") or ""
    if not expected or not hmac.compare_digest(presented, expected):
        return _json(401, {"error": "admin authorization required"})
    if method != "POST":
        return _json(405, {"error": "method not allowed"})
    try:
        payload = json.loads(body or b"{}")
    except json.JSONDecodeError:
        return _json(400, {"error": "invalid JSON"})
    if not isinstance(payload, dict):
        return _json(400, {"error": "JSON body must be an object"})
    if payload.get("action") == "review_shadow":
        required = ("user_id", "template_version")
        if any(not str(payload.get(key) or "").strip() for key in required):
            return _json(
                400, {"error": "user_id and template_version are required"})
        if not isinstance(payload.get("event_ids"), list):
            return _json(400, {"error": "event_ids must be a list"})
        try:
            row = review_shadow_delivery(
                get_kv(),
                user_id=str(payload["user_id"]),
                event_ids=[str(value) for value in payload["event_ids"]],
                template_version=str(payload["template_version"]),
                worth_sending=payload.get("worth_sending"),
                defects=[str(value) for value in payload.get("defects") or []],
                notes=str(payload.get("notes") or ""),
            )
        except ValueError as exc:
            return _json(400, {"error": str(exc)})
        return _json(200, row)

    required = ("user_id", "template_version", "reason")
    if any(not str(payload.get(key) or "").strip() for key in required):
        return _json(
            400, {"error": "user_id, template_version, and reason are required"})
    try:
        row = record_delivery_outcome(
            get_kv(),
            user_id=str(payload["user_id"]),
            template_version=str(payload["template_version"]),
            status="corrected",
            reason=str(payload["reason"]),
            team_ids=[str(value) for value in payload.get("team_ids") or []],
            event_ids=[str(value) for value in payload.get("event_ids") or []],
            delivery_ref=str(payload.get("delivery_ref") or "") or None,
        )
    except ValueError as exc:
        return _json(400, {"error": str(exc)})
    return _json(201, row)
