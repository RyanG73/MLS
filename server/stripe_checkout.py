"""Create hosted Stripe Checkout sessions without trusting client pricing."""
from __future__ import annotations

import os
import uuid

import requests

from server.config import required_secret
from server.pricing_tier import normalise_interval, price_id_for


class CheckoutConfigurationError(RuntimeError):
    pass


class CheckoutProviderError(RuntimeError):
    pass


def _price_id(plan: str, interval: str = "monthly", tier: str = "launch") -> str:
    """Resolve the Stripe Price for a (plan, interval) at the active tier.

    `intel` prices come from the pricing-tier matrix so the launch rate can be
    lifted at runtime without a redeploy, and so the annual option the site has
    always rendered is actually sellable -- previously every checkout billed the
    single monthly Price regardless of which cadence the customer picked, which
    is a chargeback waiting to happen.
    """
    if plan == "creator":
        value = required_secret("STRIPE_CREATOR_PRICE_ID", "")
        if not value:
            raise CheckoutConfigurationError("STRIPE_CREATOR_PRICE_ID is not configured")
        return value
    if plan != "intel":
        raise ValueError("plan must be intel or creator")
    interval = normalise_interval(interval)
    value = price_id_for(tier, interval)
    if not value:
        raise CheckoutConfigurationError(
            f"no Stripe Price configured for intel/{interval} at the {tier} tier")
    return value


def create_checkout_session(user_id: str, plan: str, interval: str = "monthly",
                            tier: str = "launch") -> dict:
    """Return Stripe's hosted Checkout Session ID and URL.

    Price IDs are selected server-side. User and plan metadata are copied to
    both the Session and resulting Subscription so later lifecycle webhooks can
    reconcile the entitlement without trusting a browser redirect.
    """
    secret = required_secret("STRIPE_SECRET_KEY", "")
    if not secret:
        raise CheckoutConfigurationError("STRIPE_SECRET_KEY is not configured")
    price_id = _price_id(plan, interval, tier)
    site = os.environ.get("PUBLIC_SITE_URL", "https://entenser.com").rstrip("/")
    data = {
        "mode": "subscription",
        "line_items[0][price]": price_id,
        "line_items[0][quantity]": "1",
        "client_reference_id": user_id,
        "metadata[user_id]": user_id,
        "metadata[plan]": plan,
        "metadata[interval]": normalise_interval(interval),
        "metadata[price_tier]": tier,
        "subscription_data[metadata][user_id]": user_id,
        "subscription_data[metadata][plan]": plan,
        "subscription_data[metadata][interval]": normalise_interval(interval),
        "subscription_data[metadata][price_tier]": tier,
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
