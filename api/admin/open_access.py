"""Vercel-style endpoint: /api/admin/open-access — owner control for the
open-access promo switch (server/open_access.py).

    GET     -> current state
    POST    -> open a promo   {"days": 7, "note": "launch week"}
                              or {"until": <epoch>, "note": "..."}
    DELETE  -> close it now

Auth is a single shared secret in the ADMIN_TOKEN environment variable,
compared with hmac.compare_digest. It fails closed: if ADMIN_TOKEN is unset or
blank, every request is rejected, so a misconfigured deploy cannot leave the
switch exposed. This is deliberately not the magic-link/JWT path — it is an
owner-operated lever, not a user-facing feature, and it must keep working even
if the auth system itself is what's broken.
"""
from __future__ import annotations

import hmac
import json
import os
import time

from server.kv_client import get_kv
from server import open_access

MAX_PROMO_DAYS = open_access.MAX_PROMO_SECONDS // 86400


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
        return _json(200, open_access.get_state(kv))

    if method == "DELETE":
        return _json(200, open_access.close_promo(kv))

    if method == "POST":
        try:
            payload = json.loads(body or b"{}")
        except json.JSONDecodeError:
            return _json(400, {"error": "invalid JSON"})
        if not isinstance(payload, dict):
            return _json(400, {"error": "JSON body must be an object"})

        until = payload.get("until")
        if until is None:
            days = payload.get("days", 7)
            if not isinstance(days, (int, float)) or isinstance(days, bool):
                return _json(400, {"error": "days must be a number"})
            until = time.time() + days * 86400
        if not isinstance(until, (int, float)) or isinstance(until, bool):
            return _json(400, {"error": "until must be an epoch timestamp"})

        try:
            state = open_access.open_promo(kv, int(until), str(payload.get("note", "")))
        except ValueError as exc:
            return _json(400, {"error": str(exc)})
        return _json(200, state)

    return _json(405, {"error": "method not allowed"})
