"""Vercel-style endpoint: GET /api/intel/me -> the caller's current
entitlement state -- the representative "authenticated read" endpoint
docs/intelligence-hub-implementation-instructions.md §4.2 calls for under
api/intel/*.py. See api/auth/request.py's DEPLOYMENT NOTE.
"""
from __future__ import annotations

import json
import os

from server.intel_auth import InvalidToken, require_entitlement
from server.intel_store import get_plan
from server.kv_client import get_kv

_PLAN_RANK = {"free": 0, "trial": 1, "intel": 2, "creator": 3, "canceled": -1}


def _access_token_secret() -> str:
    return os.environ.get("ACCESS_TOKEN_SECRET", "dev-only-insecure-secret")


def handle(method: str, headers: dict) -> tuple[int, dict, bytes]:
    if method != "GET":
        return 405, {}, b'{"error":"method not allowed"}'
    auth_header = headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return 401, {}, b'{"error":"missing bearer token"}'
    token = auth_header[len("Bearer "):]
    try:
        user_id = require_entitlement(_access_token_secret(), token, lambda uid: get_plan(get_kv(), uid),
                                       _PLAN_RANK, required_plan="free")
    except InvalidToken as e:
        return 401, {}, json.dumps({"error": str(e)}).encode()
    return 200, {}, json.dumps({"user_id": user_id, "plan": get_plan(get_kv(), user_id)}).encode()
