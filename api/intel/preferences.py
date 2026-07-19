"""GET/PATCH /api/intel/preferences."""
from __future__ import annotations

from server.api_support import ApiError, bearer_user, body_json, guarded, response
from server.intel_store import export_user_data, update_public_preferences
from server.kv_client import get_kv


def handle(method: str, headers: dict, body: bytes = b"{}"):
    def run():
        user_id = bearer_user(headers, "free")
        if method == "GET":
            record = export_user_data(get_kv(), user_id)
            if record is None:
                raise ApiError(404, "user not found")
            safe = {key: value for key, value in record.items()
                    if key not in {"email", "journal_entries", "saved_scenarios",
                                   "creator_workspaces", "alert_state"}}
            return response(200, safe)
        if method == "PATCH":
            record = update_public_preferences(get_kv(), user_id, body_json(body))
            return response(200, {key: value for key, value in record.items()
                                  if key not in {"email", "journal_entries"}})
        raise ApiError(405, "method not allowed")
    return guarded(run)
