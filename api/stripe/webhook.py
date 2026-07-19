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
    sig_header = headers.get("Stripe-Signature", "")
    try:
        verify_stripe_signature(body, sig_header, _webhook_secret())
    except InvalidWebhookSignature as e:
        return 400, {}, json.dumps({"error": str(e)}).encode()
    event = json.loads(body)
    handle_event(get_kv(), event)
    return 200, {}, b'{"received":true}'
