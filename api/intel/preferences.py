"""GET/PATCH /api/intel/preferences."""
from __future__ import annotations

from server.api_support import ApiError, bearer_user, body_json, guarded, response
from server.intel_store import export_user_data, update_public_preferences
from server.growth_events import record_event
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
                                   "creator_workspaces", "alert_state",
                                   "customer_evidence"}}
            return response(200, safe)
        if method == "PATCH":
            updates = body_json(body)
            prior = export_user_data(get_kv(), user_id) or {}
            record = update_public_preferences(
                get_kv(), user_id, updates, plan=prior.get("plan", "free"))
            if "teams" in updates and record.get("teams") != prior.get("teams"):
                for team in record.get("teams") or []:
                    record_event(
                        get_kv(), "track_club",
                        event_id=(f"track_club:{user_id}:{team['league_id']}:"
                                  f"{team['team_id']}"),
                        user_id=user_id,
                        properties={
                            "club_id": team["team_id"],
                            "club_name": team.get("team", ""),
                            "competition_id": team["league_id"],
                            "surface": "account",
                        })
            if ("notifications" in updates
                    and record.get("notifications") != prior.get("notifications")):
                record_event(
                    get_kv(), "notification_setting_change",
                    user_id=user_id, properties={"surface": "club_watch"})
            return response(200, {key: value for key, value in record.items()
                                  if key not in {"email", "journal_entries"}})
        raise ApiError(405, "method not allowed")
    return guarded(run)
