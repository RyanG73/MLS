"""GET /api/intel/team?league_id=...&team_id=...&feature_id=..."""
from __future__ import annotations

from server.api_support import ApiError, bearer_user, guarded, response
from server.intelligence_service import ArtifactNotFound, IntelligenceService

_service = IntelligenceService()


def handle(method: str, headers: dict, query: dict):
    def run():
        if method != "GET":
            raise ApiError(405, "method not allowed")
        bearer_user(headers, "trial")
        try:
            feature_id = int(query["feature_id"]) if query.get("feature_id") else None
            data = _service.get_team(query["league_id"], query["team_id"], feature_id)
        except ArtifactNotFound as exc:
            raise ApiError(404, str(exc)) from exc
        return response(200, data)
    return guarded(run)
