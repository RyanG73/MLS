"""POST /v1/billing/checkout creates a server-priced hosted Checkout Session."""
from __future__ import annotations

from server.api_support import ApiError, bearer_user, body_json, guarded, response
from server.stripe_checkout import (
    CheckoutConfigurationError,
    CheckoutProviderError,
    create_checkout_session,
)


def handle(method: str, headers: dict, body: bytes):
    def run():
        if method != "POST":
            raise ApiError(405, "method not allowed")
        user_id = bearer_user(headers, "free")
        plan = body_json(body).get("plan", "intel")
        if plan not in {"intel", "creator"}:
            raise ApiError(400, "plan must be intel or creator")
        try:
            session = create_checkout_session(user_id, plan)
        except CheckoutConfigurationError as exc:
            raise ApiError(503, str(exc)) from exc
        except CheckoutProviderError as exc:
            raise ApiError(502, str(exc)) from exc
        return response(201, session)
    return guarded(run)
