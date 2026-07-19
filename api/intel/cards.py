"""POST /v1/intel/cards creates a public-safe verification record."""
from __future__ import annotations

import hashlib
import json
import os

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
        if not check_rate_limit(get_kv(), f"card:{user_id}", 20, 3600):
            raise ApiError(429, "card rate limit exceeded")
        payload = body_json(body)
        try:
            public = _service.public_card_payload(
                payload["league_id"], payload["team_id"], payload["template"])
        except ArtifactNotFound as exc:
            raise ApiError(404, str(exc)) from exc
        canonical = json.dumps(public, sort_keys=True, separators=(",", ":"))
        card_id = hashlib.sha256(canonical.encode()).hexdigest()[:20]
        get_kv().set(f"public_card:{card_id}", canonical)
        api_base = os.environ.get(
            "PUBLIC_API_URL", "https://api.entenser.com/v1").rstrip("/")
        verification_url = f"{api_base}/public/card?id={card_id}"
        return response(201, {
            "card_id": card_id,
            "verification_url": verification_url,
            "image_url": verification_url + "&format=png",
            "payload": public,
        })
    return guarded(run)
