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
from server.stripe_prices import pricing


def handle(method: str, headers: dict) -> tuple[int, dict, bytes]:
    if method != "GET":
        return 405, {}, b'{"error":"method not allowed"}'
    kv = get_kv()
    # `pricing` is what Stripe will actually charge, read from the Price object
    # itself, so no surface can quote a number we won't bill. Empty when Stripe
    # is unconfigured -- the client shows "see price at checkout" rather than
    # inventing one.
    payload = {"open_access": open_access.get_state(kv), "pricing": pricing(kv)}
    headers_out = {
        "Content-Type": "application/json",
        # short public cache: a promo flip should reach visitors within a
        # minute, but this endpoint must not be hit once per page component
        "Cache-Control": "public, max-age=60",
    }
    return 200, headers_out, json.dumps(payload, separators=(",", ":")).encode()
