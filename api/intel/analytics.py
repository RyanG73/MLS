"""POST /api/intel/analytics with a strict non-sensitive event schema."""
from __future__ import annotations

from server.analytics import record
from server.api_support import ApiError, body_json, guarded, response
from server.kv_client import get_kv
from server.rate_limit import check_rate_limit
from server.api_support import account_user
from server.growth_events import ALLOWED_EVENTS as GROWTH_EVENTS, record_event


def handle(method: str, headers: dict, body: bytes):
    def run():
        if method != "POST":
            raise ApiError(405, "method not allowed")
        payload = body_json(body)
        client = headers.get("X-Client-Id", "anonymous")[:80]
        if not check_rate_limit(get_kv(), f"analytics:{client}", 120, 3600):
            raise ApiError(429, "analytics rate limit exceeded")
        event = payload["event"]
        properties = payload.get("properties") or {}
        count = record(get_kv(), event, properties)
        user_id = None
        if headers.get("Authorization"):
            try:
                user_id = account_user(headers)
            except ApiError:
                user_id = None
        mapped = {
            "why_expanded": "material_change_explanation_viewed",
            "brief_open": "since_last_visit_viewed",
            "scenario_completed": "scenario_run",
            "return_30d": "return_visit",
            "return_90d": "return_visit",
        }.get(event, event)
        if mapped in GROWTH_EVENTS:
            growth_properties = {
                key: value for key, value in {
                    "feature_id": properties.get("feature_id"),
                    "competition_id": properties.get("league_id"),
                    "club_id": properties.get("team_id"),
                    "calendar_mode": properties.get("calendar_mode"),
                    "plan": properties.get("plan"),
                    "surface": properties.get("surface"),
                }.items() if value not in (None, "")
            }
            record_event(
                get_kv(), mapped, user_id=user_id,
                properties=growth_properties)
        return response(202, {"accepted": True, "count": count})
    return guarded(run)
