"""POST /api/intel/analytics with a strict non-sensitive event schema."""
from __future__ import annotations

from server.analytics import record
from server.api_support import ApiError, body_json, guarded, response
from server.kv_client import get_kv
from server.rate_limit import check_rate_limit


def handle(method: str, headers: dict, body: bytes):
    def run():
        if method != "POST":
            raise ApiError(405, "method not allowed")
        payload = body_json(body)
        client = headers.get("X-Client-Id", "anonymous")[:80]
        if not check_rate_limit(get_kv(), f"analytics:{client}", 120, 3600):
            raise ApiError(429, "analytics rate limit exceeded")
        count = record(get_kv(), payload["event"], payload.get("properties") or {})
        return response(202, {"accepted": True, "count": count})
    return guarded(run)
