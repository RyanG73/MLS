"""GET /api/public/unsubscribe?token=..."""
from __future__ import annotations

from server.api_support import ApiError, guarded, response
from server.kv_client import get_kv
from server.unsubscribe import apply_unsubscribe


def handle(method: str, headers: dict, query: dict):
    def run():
        if method != "GET":
            raise ApiError(405, "method not allowed")
        return response(200, apply_unsubscribe(get_kv(), query.get("token", "")))
    return guarded(run)
