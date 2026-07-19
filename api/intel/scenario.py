"""POST /api/intel/scenario."""
from __future__ import annotations

from server.api_support import ApiError, bearer_user, body_json, guarded, response
from server.intel_store import save_scenario
from server.intelligence_service import (
    ArtifactNotFound, IntelligenceService, StaleScenario,
)
from server.kv_client import get_kv
from server.rate_limit import check_rate_limit

_service = IntelligenceService()


def handle(method: str, headers: dict, body: bytes):
    def run():
        if method != "POST":
            raise ApiError(405, "method not allowed")
        user_id = bearer_user(headers, "trial")
        if not check_rate_limit(get_kv(), f"scenario:{user_id}", 30, 3600):
            raise ApiError(429, "scenario rate limit exceeded")
        payload = body_json(body)
        try:
            result = _service.run_scenario(payload["league_id"], payload["team_id"], payload)
        except ArtifactNotFound as exc:
            raise ApiError(404, str(exc)) from exc
        except StaleScenario as exc:
            raise ApiError(409, str(exc)) from exc
        if payload.get("save"):
            result["saved"] = save_scenario(get_kv(), user_id, {
                "league_id": payload["league_id"], "team_id": payload["team_id"],
                "snapshot_id": result["snapshot_id"],
                "simulation_version": result["simulation_version"],
                "seed": result["seed"], "assumptions": result["assumptions"],
                "target_metric": result["target_metric"],
            })
        return response(200, result)
    return guarded(run)
