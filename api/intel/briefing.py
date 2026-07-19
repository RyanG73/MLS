"""GET /api/intel/briefing returns the shared structured briefing."""
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
            record = _service.get_team(query["league_id"], query["team_id"], 8)
        except ArtifactNotFound as exc:
            raise ApiError(404, str(exc)) from exc
        return response(200, record)
    return guarded(run)
