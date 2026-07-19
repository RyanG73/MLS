"""GET/POST/DELETE /api/intel/journal; entries are immutable versions."""
from __future__ import annotations

from server.api_support import ApiError, bearer_user, body_json, guarded, response
from server.intel_store import (
    append_journal_entry, delete_journal_entry, export_user_data,
)
from server.kv_client import get_kv


def handle(method: str, headers: dict, query: dict, body: bytes = b"{}"):
    def run():
        user_id = bearer_user(headers, "trial")
        if method == "GET":
            record = export_user_data(get_kv(), user_id) or {}
            return response(200, {"entries": record.get("journal_entries", [])})
        if method == "POST":
            entry = append_journal_entry(get_kv(), user_id, body_json(body))
            return response(201, entry)
        if method == "DELETE":
            delete_journal_entry(get_kv(), user_id, query["journal_entry_id"])
            return response(200, {"status": "deleted"})
        raise ApiError(405, "method not allowed")
    return guarded(run)
