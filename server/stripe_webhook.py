#!/usr/bin/env python3
"""S5: Stripe webhook signature verification + entitlement lifecycle
(docs/intelligence-hub-implementation-instructions.md §4.2, §5 S5, §9
"Stripe webhook signature and replay protection.")

Verifies Stripe's documented Stripe-Signature scheme using stdlib hmac/hashlib,
so the production webhook does not require the Stripe SDK. The secret is loaded
from production configuration by api/stripe/webhook.py.
"""
from __future__ import annotations

import hashlib
import hmac
import time

from server.intel_store import set_plan
from server.kv_store import KVStore

REPLAY_TOLERANCE_SECONDS = 5 * 60   # Stripe's own documented default


class InvalidWebhookSignature(Exception):
    pass


def verify_stripe_signature(payload: bytes, sig_header: str, webhook_secret: str,
                             now: float | None = None) -> None:
    """Raises InvalidWebhookSignature if `sig_header` (the raw
    Stripe-Signature header value, e.g. "t=169...,v1=abc...") doesn't
    match, or its timestamp is outside the replay-tolerance window."""
    now = now if now is not None else time.time()
    parts = dict(p.split("=", 1) for p in sig_header.split(",") if "=" in p)
    if "t" not in parts or "v1" not in parts:
        raise InvalidWebhookSignature("malformed Stripe-Signature header")
    timestamp = parts["t"]
    if abs(now - float(timestamp)) > REPLAY_TOLERANCE_SECONDS:
        raise InvalidWebhookSignature("timestamp outside replay-tolerance window")
    signed_payload = f"{timestamp}.".encode("utf-8") + payload
    expected = hmac.new(webhook_secret.encode("utf-8"), signed_payload, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(parts["v1"], expected):
        raise InvalidWebhookSignature("signature mismatch")


def _plan_for_status(status: str, paid_plan: str = "intel") -> str:
    paid_plan = paid_plan if paid_plan in {"intel", "creator"} else "intel"
    return {
        "active": paid_plan, "trialing": "trial",
        "canceled": "canceled", "unpaid": "canceled", "past_due": "canceled",
    }.get(status, "canceled")


def handle_event(kv: KVStore, event: dict) -> str | None:
    """Apply one already-signature-verified Stripe event to the KV-backed
    user record. Deduplicates by event id (Stripe explicitly documents
    at-least-once, possibly-duplicate delivery) so a redelivered event is
    a safe no-op. Returns the user_id affected, or None if the event type
    isn't handled, has no user_id, or was already processed."""
    event_id = event.get("id")
    if event_id and kv.exists(f"stripe_event:{event_id}"):
        return None
    if event_id:
        kv.set(f"stripe_event:{event_id}", "1", ex=30 * 24 * 60 * 60)

    event_type = event.get("type")
    data = event.get("data", {}).get("object", {})
    user_id = (data.get("metadata") or {}).get("user_id") or data.get("client_reference_id")
    if not user_id:
        return None

    requested_plan = (data.get("metadata") or {}).get("plan", "intel")
    if event_type == "checkout.session.completed":
        set_plan(kv, user_id, requested_plan if requested_plan in {"intel", "creator"} else "intel")
    elif event_type == "customer.subscription.updated":
        set_plan(kv, user_id, _plan_for_status(data.get("status", "canceled"), requested_plan))
    elif event_type == "customer.subscription.deleted":
        set_plan(kv, user_id, "canceled")
    else:
        return None
    return user_id
