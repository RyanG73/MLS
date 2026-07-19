"""GET/POST/DELETE /v1/intel/workspaces for Creator presets."""
from __future__ import annotations

from server.api_support import ApiError, bearer_user, body_json, guarded, response
from server.intel_store import (
    delete_creator_workspace,
    export_user_data,
    save_creator_workspace,
)
from server.kv_client import get_kv


def handle(method: str, headers: dict, query: dict, body: bytes = b"{}"):
    def run():
        user_id = bearer_user(headers, "creator")
        if method == "GET":
            record = export_user_data(get_kv(), user_id) or {}
            return response(200, {"workspaces": record.get("creator_workspaces", [])})
        if method == "POST":
            workspace = save_creator_workspace(get_kv(), user_id, body_json(body))
            return response(201, workspace)
        if method == "DELETE":
            delete_creator_workspace(get_kv(), user_id, query["workspace_id"])
            return response(200, {"status": "deleted"})
        raise ApiError(405, "method not allowed")
    return guarded(run)
