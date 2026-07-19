"""Vercel-style endpoint: GET /api/intel/me -> the caller's current
entitlement state. It uses the same authoritative plan check as every other
authenticated Intel endpoint.
"""
from __future__ import annotations

import json

from server.intel_auth import InvalidToken, require_entitlement
from server.intel_store import get_plan
from server.config import access_token_secret
from server.kv_client import get_kv

_PLAN_RANK = {"free": 0, "trial": 1, "intel": 2, "creator": 3, "canceled": -1}


def handle(method: str, headers: dict) -> tuple[int, dict, bytes]:
    if method != "GET":
        return 405, {}, b'{"error":"method not allowed"}'
    auth_header = headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return 401, {}, b'{"error":"missing bearer token"}'
    token = auth_header[len("Bearer "):]
    try:
        user_id = require_entitlement(access_token_secret(), token, lambda uid: get_plan(get_kv(), uid),
                                       _PLAN_RANK, required_plan="free")
    except InvalidToken as e:
        return 401, {}, json.dumps({"error": str(e)}).encode()
    return 200, {}, json.dumps({"user_id": user_id, "plan": get_plan(get_kv(), user_id)}).encode()
