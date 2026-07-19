"""Create hosted Stripe Checkout sessions without trusting client pricing."""
from __future__ import annotations

import os
import uuid

import requests

from server.config import required_secret


class CheckoutConfigurationError(RuntimeError):
    pass


class CheckoutProviderError(RuntimeError):
    pass


def _price_id(plan: str) -> str:
    names = {
        "intel": "STRIPE_INTEL_PRICE_ID",
        "creator": "STRIPE_CREATOR_PRICE_ID",
    }
    if plan not in names:
        raise ValueError("plan must be intel or creator")
    value = required_secret(names[plan], "")
    if not value:
        raise CheckoutConfigurationError(f"{names[plan]} is not configured")
    return value


def create_checkout_session(user_id: str, plan: str) -> dict:
    """Return Stripe's hosted Checkout Session ID and URL.

    Price IDs are selected server-side. User and plan metadata are copied to
    both the Session and resulting Subscription so later lifecycle webhooks can
    reconcile the entitlement without trusting a browser redirect.
    """
    secret = required_secret("STRIPE_SECRET_KEY", "")
    if not secret:
        raise CheckoutConfigurationError("STRIPE_SECRET_KEY is not configured")
    price_id = _price_id(plan)
    site = os.environ.get("PUBLIC_SITE_URL", "https://entenser.com").rstrip("/")
    data = {
        "mode": "subscription",
        "line_items[0][price]": price_id,
        "line_items[0][quantity]": "1",
        "client_reference_id": user_id,
        "metadata[user_id]": user_id,
        "metadata[plan]": plan,
        "subscription_data[metadata][user_id]": user_id,
        "subscription_data[metadata][plan]": plan,
        "success_url": f"{site}/?league=intel&checkout=success",
        "cancel_url": f"{site}/?league=intel&checkout=canceled",
        "allow_promotion_codes": "true",
    }
    try:
        response = requests.post(
            "https://api.stripe.com/v1/checkout/sessions",
            data=data,
            headers={
                "Authorization": f"Bearer {secret}",
                "Idempotency-Key": str(uuid.uuid4()),
            },
            timeout=15,
        )
    except requests.RequestException as exc:
        raise CheckoutProviderError("Stripe Checkout is temporarily unavailable") from exc
    if response.status_code >= 400:
        raise CheckoutProviderError("Stripe rejected the Checkout Session")
    try:
        payload = response.json()
        return {"id": payload["id"], "url": payload["url"]}
    except (ValueError, KeyError, TypeError) as exc:
        raise CheckoutProviderError("Stripe returned an invalid Checkout Session") from exc
