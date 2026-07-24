"""POST /api/public/subscribe {email, tags} -> KV + Resend Contacts (launch plan E2).
CORS is enforced centrally in api/index.py via ALLOWED_ORIGINS; per-IP rate
limiting here keeps the open endpoint from being a write amplifier."""
from __future__ import annotations

from server.api_support import ApiError, body_json, guarded, response
from server.kv_client import get_kv
from server.rate_limit import check_rate_limit
from server.subscribe import subscribe_contact

MAX_PER_HOUR = 10


def _client_ip(headers: dict) -> str:
    for key, value in headers.items():
        if key.lower() == "x-forwarded-for":
            return value.split(",")[0].strip() or "unknown"
    return "unknown"


def handle(method: str, headers: dict, body: bytes):
    def run():
        if method != "POST":
            raise ApiError(405, "method not allowed")
        data = body_json(body)
        kv = get_kv()
        if not check_rate_limit(kv, f"subscribe:{_client_ip(headers)}",
                                MAX_PER_HOUR, 3600):
            raise ApiError(429, "rate limited")
        return response(200, subscribe_contact(kv, data.get("email"), data.get("tags")))
    return guarded(run)
