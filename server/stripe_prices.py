"""Read the live Stripe Price so the site can never quote a price we won't charge.

The web client previously guessed a price from `navigator.language` -- showing
EUR to EU locales and USD otherwise, with a separate hardcoded number on each
surface. That is a consumer-protection problem rather than a cosmetic one: a
visitor shown a euro amount and billed in dollars has been misled, and any
hardcoded figure silently rots the moment the Stripe Price changes.

Stripe's Price object is the only thing that decides what a card is charged, so
it is what the site quotes. Results are cached in KV because pricing changes
about once a year while `/v1/public/config` is hit on every page load, and a
Stripe outage must never blank the pricing UI.
"""
from __future__ import annotations

import json
import os

import requests

from server.kv_store import KVStore

CACHE_TTL_SECONDS = 3600
_CACHE_KEY = "stripe_price_display"

# Stripe reports minor units for most currencies; these have no minor unit at all.
_ZERO_DECIMAL = {
    "bif", "clp", "djf", "gnf", "jpy", "kmf", "krw", "mga",
    "pyg", "rwf", "ugx", "vnd", "vuv", "xaf", "xof", "xpf",
}


def format_amount(minor_units: int, currency: str) -> str:
    """Render Stripe's integer amount the way a customer expects to read it."""
    currency = (currency or "").lower()
    symbols = {"usd": "$", "eur": "€", "gbp": "£"}
    prefix = symbols.get(currency, "")
    if currency in _ZERO_DECIMAL:
        body = f"{minor_units:,}"
    else:
        body = f"{minor_units / 100:,.2f}"
    return f"{prefix}{body}" if prefix else f"{body} {currency.upper()}"


def _fetch(price_id: str, secret: str) -> dict | None:
    try:
        response = requests.get(
            f"https://api.stripe.com/v1/prices/{price_id}",
            headers={"Authorization": f"Bearer {secret}"},
            timeout=10,
        )
    except requests.RequestException:
        return None
    if response.status_code >= 400:
        return None
    try:
        payload = response.json()
    except ValueError:
        return None
    amount = payload.get("unit_amount")
    currency = payload.get("currency")
    if not isinstance(amount, int) or not currency:
        return None
    recurring = payload.get("recurring") or {}
    return {
        "amount": amount,
        "currency": currency,
        "interval": recurring.get("interval"),
        "interval_count": recurring.get("interval_count", 1),
        "display": format_amount(amount, currency),
    }


def pricing(kv: KVStore) -> dict:
    """Public pricing for every configured plan, keyed by plan name.

    Returns ``{}`` when Stripe is unconfigured or unreachable. The client is
    expected to fall back to "see price at checkout" rather than invent a
    number -- an absent price is honest, a stale one is a refund request.
    """
    cached = kv.get(_CACHE_KEY)
    if cached is not None:
        try:
            return json.loads(cached)
        except (ValueError, TypeError):
            pass

    # Deliberately os.environ, NOT config.required_secret: that raises in
    # production for a missing name, and this runs inside /public/config --
    # the unauthenticated endpoint the site reads on every page load to decide
    # whether to show lock chrome. Env vars are added one at a time, so
    # `ENTENSER_ENV=production` inevitably lands before the Stripe keys do;
    # raising here would 503 the public config for that whole window. A missing
    # price is a display concern with an honest fallback, never an outage.
    secret = os.environ.get("STRIPE_SECRET_KEY", "")
    if not secret:
        return {}
    plans = {}
    for plan, env_name in (("intel", "STRIPE_INTEL_PRICE_ID"),
                           ("creator", "STRIPE_CREATOR_PRICE_ID")):
        price_id = os.environ.get(env_name, "")
        if not price_id:
            continue
        record = _fetch(price_id, secret)
        if record:
            plans[plan] = record
    if plans:
        kv.set(_CACHE_KEY, json.dumps(plans), ex=CACHE_TTL_SECONDS)
    return plans
