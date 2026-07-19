"""Verify a one-time magic link and issue an access/refresh token pair."""
from __future__ import annotations

import json
import uuid

from server.intel_auth import issue_access_token, issue_refresh_token, verify_magic_link
from server.intel_store import get_or_create_user
from server.config import access_token_secret
from server.kv_client import get_kv


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
    access_token = issue_access_token(access_token_secret(), user_id, user["plan"])
    refresh_token = issue_refresh_token(get_kv(), user_id)
    return 200, {}, json.dumps({"access_token": access_token, "refresh_token": refresh_token}).encode()
