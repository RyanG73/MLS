"""Vercel-style endpoint: /api/admin/pricing — owner control of the price tier.

    GET     -> current tier, when it changed, and which tiers are sellable
    POST    -> switch tier   {"tier": "standard", "note": "lifted after launch"}

Same shared-secret auth and fail-closed posture as api/admin/open_access.py:
ADMIN_TOKEN compared with hmac.compare_digest, every request rejected when it
is unset, so a misconfigured deploy cannot leave the price switch exposed.

This exists so lifting $5.99 -> $7.99 is an API call rather than a redeploy.
Existing subscribers are untouched -- Stripe keeps them on the Price they
bought -- so the switch only ever changes what a *new* customer is offered.
"""
from __future__ import annotations

import hmac
import json
import os

from server import pricing_tier
from server.kv_client import get_kv


def _authorized(headers: dict) -> bool:
    expected = os.environ.get("ADMIN_TOKEN", "")
    if not expected:
        return False
    presented = headers.get("X-Admin-Token") or headers.get("x-admin-token") or ""
    return hmac.compare_digest(presented, expected)


def _json(status: int, payload) -> tuple[int, dict, bytes]:
    return status, {"Content-Type": "application/json", "Cache-Control": "no-store"}, \
        json.dumps(payload, separators=(",", ":")).encode()


def handle(method: str, headers: dict, body: bytes = b"") -> tuple[int, dict, bytes]:
    if not _authorized(headers):
        return _json(401, {"error": "admin authorization required"})

    kv = get_kv()

    if method == "GET":
        return _json(200, pricing_tier.get_state(kv))

    if method == "POST":
        try:
            payload = json.loads(body or b"{}")
        except json.JSONDecodeError:
            return _json(400, {"error": "invalid JSON"})
        if not isinstance(payload, dict):
            return _json(400, {"error": "JSON body must be an object"})
        try:
            state = pricing_tier.set_tier(
                kv, str(payload.get("tier", "")), str(payload.get("note", "")))
        except ValueError as exc:
            return _json(400, {"error": str(exc)})
        return _json(200, state)

    return _json(405, {"error": "method not allowed"})
