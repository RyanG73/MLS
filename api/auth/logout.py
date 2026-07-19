"""POST /api/auth/logout revokes the opaque refresh token."""
from __future__ import annotations

from server.api_support import ApiError, body_json, guarded, response
from server.intel_auth import revoke_refresh_token
from server.kv_client import get_kv


def handle(method: str, headers: dict, body: bytes):
    def run():
        if method != "POST":
            raise ApiError(405, "method not allowed")
        token = body_json(body).get("refresh_token")
        if not token:
            raise ApiError(400, "refresh_token required")
        revoke_refresh_token(get_kv(), token)
        return response(200, {"status": "logged_out"})
    return guarded(run)
