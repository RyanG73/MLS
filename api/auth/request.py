"""Vercel-style endpoint: POST /api/auth/request {"email": "..."} -> issues
a magic link via server.intel_auth.request_magic_link.

DEPLOYMENT NOTE: this file uses a minimal, framework-agnostic
`handle(method, headers, body) -> (status, headers, body)` signature
rather than committing to Vercel's exact Python runtime convention, since
no Vercel project is linked to this repo yet (this S5 plan's confirmed
scope: code + mocked tests only). Wiring this to a real
`BaseHTTPRequestHandler` or WSGI app is a small adapter, not a rewrite,
once a project exists.
"""
from __future__ import annotations

import json
import os

from server.intel_auth import RecordingSender, request_magic_link
from server.kv_client import get_kv
from server.rate_limit import check_rate_limit

# A real deployment swaps this for a Resend-backed sender; this scaffolding
# stage never contacts a real email provider.
_sender = RecordingSender()

RATE_LIMIT_MAX = 5
RATE_LIMIT_WINDOW_SECONDS = 60 * 60


def handle(method: str, headers: dict, body: bytes) -> tuple[int, dict, bytes]:
    if method != "POST":
        return 405, {}, b'{"error":"method not allowed"}'
    try:
        payload = json.loads(body)
        email = payload["email"]
    except (json.JSONDecodeError, KeyError):
        return 400, {}, b'{"error":"email required"}'
    if not check_rate_limit(get_kv(), f"auth_request:{email}", RATE_LIMIT_MAX, RATE_LIMIT_WINDOW_SECONDS):
        return 429, {}, b'{"error":"too many requests"}'
    base_url = os.environ.get("MAGIC_LINK_BASE_URL", "https://entenser.com/auth/callback")
    request_magic_link(get_kv(), _sender, email, base_url)
    return 200, {}, b'{"status":"sent"}'
