"""One durable Club Watch sample for a registered user's followed club."""
from __future__ import annotations

from server.api_support import ApiError, bearer_user, guarded, response
from server.growth_events import record_event
from server.intel_store import (
    export_user_data, get_or_create_club_watch_sample,
)
from server.intelligence_service import ArtifactNotFound, IntelligenceService
from server.kv_client import get_kv

_service = IntelligenceService()


def _build_sample(league_id: str, team_id: str) -> dict:
    record = _service.get_team(league_id, team_id)
    features = record.get("features") or {}
    return {
        "schema_version": 1,
        "league_id": record["league_id"],
        "league_name": record["league_name"],
        "team_id": record["team_id"],
        "team": record["team"],
        "season_id": record.get("season_id"),
        "snapshot_id": record["snapshot_id"],
        "generated": record["generated"],
        "calendar_mode": record.get("calendar_mode"),
        "target_metric": record.get("target_metric"),
        "features": {
            "current": features.get("1"),
            "what_changed": features.get("2"),
            "why": features.get("3"),
            "what_next": features.get("4"),
        },
    }


def handle(method: str, headers: dict, query: dict):
    def run():
        if method != "GET":
            raise ApiError(405, "method not allowed")
        user_id = bearer_user(headers, "free")
        record = export_user_data(get_kv(), user_id)
        if record is None:
            raise ApiError(404, "user not found")
        league_id, team_id = query.get("league_id"), query.get("team_id")
        followed = record.get("teams") or []
        if not any(
            team.get("league_id") == league_id and team.get("team_id") == team_id
            for team in followed
        ):
            raise ApiError(403, "follow this club before opening its sample")
        try:
            sample = get_or_create_club_watch_sample(
                get_kv(), user_id, league_id, team_id,
                lambda: _build_sample(league_id, team_id))
        except ArtifactNotFound as exc:
            raise ApiError(404, str(exc)) from exc
        event_base = f"{user_id}:{sample['snapshot_id']}"
        props = {
            "club_id": team_id,
            "club_name": sample["team"],
            "competition_id": league_id,
            "competition_name": sample["league_name"],
            "surface": "club_watch_sample",
        }
        record_event(get_kv(), "sample_update_view",
                     event_id=f"sample_update_view:{event_base}",
                     user_id=user_id, properties=props)
        record_event(get_kv(), "activation",
                     event_id=f"activation:{user_id}",
                     user_id=user_id, properties=props)
        return response(200, sample)
    return guarded(run)
