"""Vercel-style endpoint: GET /api/auth/callback?token=... -> verifies the
magic-link token, issues an access + refresh token pair. See
api/auth/request.py's DEPLOYMENT NOTE for the framework-agnostic handle()
signature this scaffolding stage uses.
"""
from __future__ import annotations

import json
import os
import uuid

from server.intel_auth import issue_access_token, issue_refresh_token, verify_magic_link
from server.intel_store import get_or_create_user
from server.kv_client import get_kv


def _access_token_secret() -> str:
    return os.environ.get("ACCESS_TOKEN_SECRET", "dev-only-insecure-secret")


def handle(method: str, headers: dict, query: dict) -> tuple[int, dict, bytes]:
    if method != "GET":
        return 405, {}, b'{"error":"method not allowed"}'
    token = query.get("token")
    if not token:
        return 400, {}, b'{"error":"token required"}'
    email = verify_magic_link(get_kv(), token)
    if email is None:
        return 401, {}, b'{"error":"invalid or expired token"}'
    user_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"mailto:{email}"))
    user = get_or_create_user(get_kv(), user_id, email)
    access_token = issue_access_token(_access_token_secret(), user_id, user["plan"])
    refresh_token = issue_refresh_token(get_kv(), user_id)
    return 200, {}, json.dumps({"access_token": access_token, "refresh_token": refresh_token}).encode()
