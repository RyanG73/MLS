"""POST /v1/billing/checkout creates a server-priced hosted Checkout Session."""
from __future__ import annotations

# `creator` ranks above `intel` in PLAN_RANK and the UI had an "Upgrade to
# Creator" button, but the tier has no published price, no entitlement list and
# no marketing copy anywhere -- it was purchasable and undefined at the same
# time. Launch sells exactly one plan. The rank and the webhook mapping stay
# intact so an existing creator entitlement keeps working and the tier can be
# re-enabled by adding it back here once it is actually specified.
PURCHASABLE_PLANS = {"intel"}

from server.api_support import ApiError, bearer_user, body_json, guarded, response
from server.kv_client import get_kv
from server.rate_limit import check_rate_limit
from server.stripe_checkout import (
    CheckoutConfigurationError,
    CheckoutProviderError,
    create_checkout_session,
)

# Every call mints a Stripe Checkout Session. Unlimited, an authenticated
# account can spray sessions at Stripe's API and pollute the funnel metrics the
# Sept 30 conversion gate is read from. Generous enough that a genuine customer
# retrying a failed card never notices.
CHECKOUT_RATE_LIMIT_MAX = 10
CHECKOUT_RATE_LIMIT_WINDOW_SECONDS = 60 * 60


def handle(method: str, headers: dict, body: bytes):
    def run():
        if method != "POST":
            raise ApiError(405, "method not allowed")
        user_id = bearer_user(headers, "free")
        plan = body_json(body).get("plan", "intel")
        if plan not in PURCHASABLE_PLANS:
            raise ApiError(400, "plan is not available for purchase")
        if not check_rate_limit(get_kv(), f"checkout:{user_id}",
                                CHECKOUT_RATE_LIMIT_MAX,
                                CHECKOUT_RATE_LIMIT_WINDOW_SECONDS):
            raise ApiError(429, "too many checkout attempts, try again later")
        try:
            session = create_checkout_session(user_id, plan)
        except CheckoutConfigurationError as exc:
            raise ApiError(503, str(exc)) from exc
        except CheckoutProviderError as exc:
            raise ApiError(502, str(exc)) from exc
        return response(201, session)
    return guarded(run)
