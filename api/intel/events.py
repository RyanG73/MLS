"""GET/POST /api/intel/events for per-team cursors."""
from __future__ import annotations

from server.api_support import ApiError, bearer_user, body_json, guarded, response
from server.intel_store import export_user_data, set_seen_cursor
from server.intelligence_service import ArtifactNotFound, IntelligenceService
from server.kv_client import get_kv

_service = IntelligenceService()


def handle(method: str, headers: dict, query: dict, body: bytes = b"{}"):
    def run():
        user_id = bearer_user(headers, "trial")
        if method == "GET":
            try:
                record = _service.get_team(query["league_id"], query["team_id"], 2)
            except ArtifactNotFound as exc:
                raise ApiError(404, str(exc)) from exc
            user = export_user_data(get_kv(), user_id) or {}
            cursor = (user.get("last_seen_event_id_by_team") or {}).get(query["team_id"])
            events = (record["feature"].get("data") or {}).get("events") or []
            if cursor:
                ids = [event["event_id"] for event in events]
                events = events[:ids.index(cursor)] if cursor in ids else events
            return response(200, {**record, "cursor": cursor, "events": events})
        if method == "POST":
            payload = body_json(body)
            set_seen_cursor(get_kv(), user_id, payload["team_id"], payload["event_id"])
            return response(200, {"status": "seen", "team_id": payload["team_id"],
                                  "event_id": payload["event_id"]})
        raise ApiError(405, "method not allowed")
    return guarded(run)
