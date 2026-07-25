"""GET /api/intel/export — CSV/JSON/PNG download of a team's derived record.

Gated at `intel`, not `creator` (launch audit 2026-07-25): "CSV downloads of
every projection" is advertised on the Intel tier on both the account page and
the support page, but the endpoint required `creator` -- a rank an Intel
subscriber never reaches. Every paying launch customer would have been sold a
download that returned 401.

Scope note (docs/data-sources.md, export-scope rule): everything emitted here is
Entenser's own model output plus embedded source/citation/methodology. No raw
supplier rows are ever redistributed through this endpoint.
"""
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
        user_id = bearer_user(headers, "intel")
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
