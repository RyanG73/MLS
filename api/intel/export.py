"""GET /api/intel/export requires Creator entitlement."""
from __future__ import annotations

from server.api_support import ApiError, bearer_user, guarded, response
from server.intelligence_service import ArtifactNotFound, IntelligenceService
from server.kv_client import get_kv
from server.rate_limit import check_rate_limit

_service = IntelligenceService()


def handle(method: str, headers: dict, query: dict):
    def run():
        if method != "GET":
            raise ApiError(405, "method not allowed")
        user_id = bearer_user(headers, "creator")
        if not check_rate_limit(get_kv(), f"export:{user_id}", 20, 3600):
            raise ApiError(429, "export rate limit exceeded")
        try:
            content_type, payload = _service.creator_export(
                query["league_id"], query["team_id"], query.get("format", "csv"),
                query.get("template", "highest_leverage"))
        except ArtifactNotFound as exc:
            raise ApiError(404, str(exc)) from exc
        return 200, {"Content-Type": content_type, "Cache-Control": "private, no-store"}, payload
    return guarded(run)
