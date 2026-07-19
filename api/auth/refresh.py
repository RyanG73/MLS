"""Vercel-style endpoint: POST /api/auth/refresh {"refresh_token": "..."}
-> a new access token, with the plan claim re-checked against current
entitlement state. See api/auth/request.py's DEPLOYMENT NOTE.
"""
from __future__ import annotations

import json
import os

from server.intel_auth import refresh_access_token
from server.intel_store import get_plan
from server.kv_client import get_kv


def _access_token_secret() -> str:
    return os.environ.get("ACCESS_TOKEN_SECRET", "dev-only-insecure-secret")


def handle(method: str, headers: dict, body: bytes) -> tuple[int, dict, bytes]:
    if method != "POST":
        return 405, {}, b'{"error":"method not allowed"}'
    try:
        refresh_token = json.loads(body)["refresh_token"]
    except (json.JSONDecodeError, KeyError):
        return 400, {}, b'{"error":"refresh_token required"}'
    new_token = refresh_access_token(get_kv(), _access_token_secret(), refresh_token,
                                      lambda uid: get_plan(get_kv(), uid))
    if new_token is None:
        return 401, {}, b'{"error":"invalid or expired refresh token"}'
    return 200, {}, json.dumps({"access_token": new_token}).encode()
