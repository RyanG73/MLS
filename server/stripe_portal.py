"""Create hosted Stripe Billing Portal sessions.

Self-service cancellation is not optional for a consumer subscription: US
negative-option rules and EU/UK distance-selling rules both require a
cancellation path no harder than signup, and Stripe's own merchant terms
require published terms. Hosting it at Stripe means the cancel, plan-change,
payment-method and invoice-history surfaces are Stripe's problem, not ours --
we only mint a session for an authenticated user's own customer id.
"""
from __future__ import annotations

import os

import requests

from server.config import required_secret


class PortalConfigurationError(RuntimeError):
    pass


class PortalProviderError(RuntimeError):
    pass


def create_portal_session(customer_id: str) -> dict:
    """Return Stripe's hosted Billing Portal URL for `customer_id`.

    The customer id is always resolved server-side from the caller's own
    authenticated record -- never accepted from the client, which would let
    anyone open anyone else's billing page.
    """
    secret = required_secret("STRIPE_SECRET_KEY", "")
    if not secret:
        raise PortalConfigurationError("STRIPE_SECRET_KEY is not configured")
    site = os.environ.get("PUBLIC_SITE_URL", "https://entenser.com").rstrip("/")
    try:
        response = requests.post(
            "https://api.stripe.com/v1/billing_portal/sessions",
            data={"customer": customer_id, "return_url": f"{site}/?league=account"},
            headers={"Authorization": f"Bearer {secret}"},
            timeout=15,
        )
    except requests.RequestException as exc:
        raise PortalProviderError("Stripe billing portal is temporarily unavailable") from exc
    if response.status_code >= 400:
        raise PortalProviderError("Stripe rejected the billing portal session")
    try:
        payload = response.json()
        return {"url": payload["url"]}
    except (ValueError, KeyError, TypeError) as exc:
        raise PortalProviderError("Stripe returned an invalid billing portal session") from exc
