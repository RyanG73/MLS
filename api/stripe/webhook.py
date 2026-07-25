"""Vercel-style endpoint: POST /api/stripe/webhook -> verify signature,
apply entitlement lifecycle event. See api/auth/request.py's DEPLOYMENT
NOTE for the framework-agnostic handle() signature.
"""
from __future__ import annotations

import json

from server.config import stripe_webhook_secret
from server.kv_client import get_kv
from server.stripe_webhook import InvalidWebhookSignature, handle_event, verify_stripe_signature


def _webhook_secret() -> str:
    return stripe_webhook_secret()


def handle(method: str, headers: dict, body: bytes) -> tuple[int, dict, bytes]:
    if method != "POST":
        return 405, {}, b'{"error":"method not allowed"}'
    secret = _webhook_secret()
    if not secret:
        # Fail CLOSED. HMAC over an empty key still verifies, so an unset
        # secret would let anyone forge checkout.session.completed and grant
        # themselves a paid entitlement. Refuse to process instead.
        return 503, {}, b'{"error":"webhook signing secret is not configured"}'
    sig_header = headers.get("Stripe-Signature", "")
    try:
        verify_stripe_signature(body, sig_header, secret)
    except InvalidWebhookSignature as e:
        return 400, {}, json.dumps({"error": str(e)}).encode()
    event = json.loads(body)
    handle_event(get_kv(), event)
    return 200, {}, b'{"received":true}'
