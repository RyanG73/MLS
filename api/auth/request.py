"""Vercel-style endpoint: POST /api/auth/request {"email": "..."} -> issues
a magic link via server.intel_auth.request_magic_link.

The framework-independent handle() contract is routed by api/index.py in the
Vercel Python function and remains directly unit-testable.
"""
from __future__ import annotations

import json
import os
from urllib.parse import urlsplit

from server.email_client import get_magic_link_sender
from server.intel_auth import request_magic_link
from server.kv_client import get_kv
from server.rate_limit import check_rate_limit
from server.growth_events import record_event

_sender = get_magic_link_sender()

RATE_LIMIT_MAX = 5
RATE_LIMIT_WINDOW_SECONDS = 60 * 60


def _safe_return_to(value: str) -> str | None:
    """Allow a same-site path/query, never an absolute or protocol-relative URL."""
    value = str(value or "").strip()
    if not value or not value.startswith("/") or value.startswith("//"):
        return None
    parsed = urlsplit(value)
    if parsed.scheme or parsed.netloc or parsed.fragment:
        return None
    return value[:1000]


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
    public_site = os.environ.get("PUBLIC_SITE_URL", "https://entenser.com").rstrip("/")
    return_to = _safe_return_to(payload.get("return_to", ""))
    base_url = (
        public_site + return_to if return_to
        else os.environ.get("MAGIC_LINK_BASE_URL", f"{public_site}/?league=intel")
    )
    record_event(
        get_kv(), "registration_start",
        properties={"source": "magic_link", "surface": "club_watch"})
    request_magic_link(get_kv(), _sender, email, base_url)
    return 200, {}, b'{"status":"sent"}'
