"""GET/DELETE /api/account/data for complete user lifecycle."""
from __future__ import annotations

from server.api_support import ApiError, bearer_user, body_json, guarded, response
from server.intel_store import delete_user_data, export_user_data
from server.kv_client import get_kv


def handle(method: str, headers: dict, body: bytes = b"{}"):
    def run():
        user_id = bearer_user(headers, "free")
        if method == "GET":
            record = export_user_data(get_kv(), user_id)
            if record is None:
                raise ApiError(404, "user not found")
            return response(200, record)
        if method == "DELETE":
            payload = body_json(body)
            if payload.get("confirmation") != "DELETE":
                raise ApiError(400, "confirmation must be DELETE")
            delete_user_data(get_kv(), user_id)
            return response(200, {"status": "deleted"})
        raise ApiError(405, "method not allowed")
    return guarded(run)
