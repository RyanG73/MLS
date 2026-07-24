"""Vercel-style endpoint: GET /api/public/config — unauthenticated client
configuration.

Right now this carries exactly one thing: whether an open-access promo is
running, so the web client can drop its lock chrome and show a promo banner
instead of "Sign in to unlock". Keep it that way — this response is public and
cacheable, so nothing user-specific or secret belongs here.
"""
from __future__ import annotations

import json

from server.kv_client import get_kv
from server import open_access


def handle(method: str, headers: dict) -> tuple[int, dict, bytes]:
    if method != "GET":
        return 405, {}, b'{"error":"method not allowed"}'
    payload = {"open_access": open_access.get_state(get_kv())}
    headers_out = {
        "Content-Type": "application/json",
        # short public cache: a promo flip should reach visitors within a
        # minute, but this endpoint must not be hit once per page component
        "Cache-Control": "public, max-age=60",
    }
    return 200, headers_out, json.dumps(payload, separators=(",", ":")).encode()
