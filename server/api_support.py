"""Common authentication, JSON, and validation helpers for Intel endpoints."""
from __future__ import annotations

import json

from server.config import access_token_secret
from server.intel_auth import InvalidToken, require_entitlement, verify_access_token
from server.intel_store import get_plan
from server.kv_client import get_kv
from server.open_access import is_open

PLAN_RANK = {"free": 0, "trial": 1, "intel": 2, "creator": 3, "canceled": -1}


class ApiError(Exception):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


def response(status: int, payload, headers: dict | None = None):
    base = {"Content-Type": "application/json", "Cache-Control": "private, no-store"}
    base.update(headers or {})
    return status, base, json.dumps(payload, separators=(",", ":"), allow_nan=False).encode()


def body_json(body: bytes) -> dict:
    try:
        payload = json.loads(body or b"{}")
    except json.JSONDecodeError as exc:
        raise ApiError(400, "invalid JSON") from exc
    if not isinstance(payload, dict):
        raise ApiError(400, "JSON body must be an object")
    return payload


def bearer_user(headers: dict, required_plan: str = "intel") -> str:
    """Resolve the caller's user_id, enforcing `required_plan`.

    While an open-access promo is running (server.open_access) the plan-rank
    check is waived, but the token check is not: the caller must still present
    a valid, unexpired, correctly-signed access token, and a `canceled` account
    stays out. Open access means "no payment required", never "no account
    required" — Intel state is per-user and needs somewhere to live.
    """
    authorization = headers.get("Authorization", "")
    if not authorization.startswith("Bearer "):
        raise ApiError(401, "missing bearer token")
    token = authorization[7:]
    try:
        if is_open(get_kv()):
            user_id = verify_access_token(access_token_secret(), token)["sub"]
            if PLAN_RANK.get(get_plan(get_kv(), user_id), -1) < PLAN_RANK["free"]:
                raise InvalidToken("account is canceled")
            return user_id
        return require_entitlement(
            access_token_secret(), token,
            lambda user_id: get_plan(get_kv(), user_id),
            PLAN_RANK, required_plan,
        )
    except (InvalidToken, KeyError) as exc:
        raise ApiError(401, str(exc)) from exc


def guarded(call):
    try:
        return call()
    except ApiError as exc:
        return response(exc.status, {"error": exc.message})
    except (KeyError, ValueError) as exc:
        return response(400, {"error": str(exc)})
