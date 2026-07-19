"""POST /api/intel/ask using a finite, deterministic intent catalog."""
from __future__ import annotations

from server.api_support import ApiError, bearer_user, body_json, guarded, response
from server.intelligence_service import ArtifactNotFound, IntelligenceService
from server.kv_client import get_kv
from server.rate_limit import check_rate_limit

_service = IntelligenceService()


def handle(method: str, headers: dict, body: bytes):
    def run():
        if method != "POST":
            raise ApiError(405, "method not allowed")
        user_id = bearer_user(headers, "trial")
        if not check_rate_limit(get_kv(), f"ask:{user_id}", 60, 3600):
            raise ApiError(429, "Ask Entenser rate limit exceeded")
        payload = body_json(body)
        try:
            result = _service.ask(payload["league_id"], payload["team_id"], payload)
        except ArtifactNotFound as exc:
            raise ApiError(404, str(exc)) from exc
        return response(200, result)
    return guarded(run)
