"""POST /v1/billing/portal opens the caller's own Stripe Billing Portal.

This is the self-service cancellation path. It is deliberately reachable by any
authenticated account ("free" rank) rather than paid-only: a customer who has
already been downgraded to `canceled` still needs to reach their invoices and
payment history, and someone mid-dunning must be able to fix their card.
"""
from __future__ import annotations

from server.api_support import ApiError, account_user, guarded, response
from server.intel_store import get_stripe_customer
from server.kv_client import get_kv
from server.stripe_portal import (
    PortalConfigurationError,
    PortalProviderError,
    create_portal_session,
)


def handle(method: str, headers: dict, body: bytes = b""):
    def run():
        if method != "POST":
            raise ApiError(405, "method not allowed")
        user_id = account_user(headers)
        customer_id = get_stripe_customer(get_kv(), user_id)
        if not customer_id:
            raise ApiError(404, "no billing account for this user")
        try:
            session = create_portal_session(customer_id)
        except PortalConfigurationError as exc:
            raise ApiError(503, str(exc)) from exc
        except PortalProviderError as exc:
            raise ApiError(502, str(exc)) from exc
        return response(200, session)
    return guarded(run)
