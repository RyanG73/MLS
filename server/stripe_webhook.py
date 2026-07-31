#!/usr/bin/env python3
"""S5: Stripe webhook signature verification + entitlement lifecycle
(docs/intelligence-hub-implementation-instructions.md §4.2, §5 S5, §9
"Stripe webhook signature and replay protection.")

Verifies Stripe's documented Stripe-Signature scheme using stdlib hmac/hashlib,
so the production webhook does not require the Stripe SDK. The secret is loaded
from production configuration by api/stripe/webhook.py.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import time

from server.growth_events import record_event
from server.intel_store import (
    set_plan, set_stripe_customer, update_subscription_lifecycle,
    user_for_stripe_customer,
)
from server.kv_store import KVStore

REPLAY_TOLERANCE_SECONDS = 5 * 60   # Stripe's own documented default

# The 30-day money-back guarantee replaces the trial as the risk-reversal
# mechanism, so refunds must be honoured automatically and access must end when
# the money goes back. Flip to False if the published policy is ever changed to
# "access continues to period end" (draft decision L4 in
# docs/legal-copy-draft-2026-07-25.md) -- the published wording and this
# constant must always agree.
REVOKE_ACCESS_ON_REFUND = True


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
    """Map a Stripe subscription status to our stored plan.

    `past_due` deliberately KEEPS paid access. Stripe retries a failed renewal
    on its dunning schedule for roughly three weeks before giving up, and only
    then moves the subscription to `unpaid`. Revoking on the first decline
    would cut off a customer whose card merely expired -- someone who is still
    paying us and whose payment will most likely succeed on retry. `unpaid` is
    the point Stripe itself has given up, so that is where access ends.
    """
    paid_plan = paid_plan if paid_plan in {"intel", "creator"} else "intel"
    return {
        "active": paid_plan, "trialing": "trial",
        "past_due": paid_plan,          # grace: Stripe is still retrying
        "canceled": "canceled", "unpaid": "canceled",
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

    event_type = event.get("type")
    data = event.get("data", {}).get("object", {})
    metadata = data.get("metadata") or {}
    if not metadata:
        # invoice.* objects carry the subscription's metadata one level down
        metadata = (data.get("subscription_details") or {}).get("metadata") or {}
    user_id = metadata.get("user_id") or data.get("client_reference_id")
    if not user_id:
        # charge.* and some invoice.* objects carry no metadata at all -- the
        # customer id plus the reverse index is the only way back to a user.
        user_id = user_for_stripe_customer(kv, data.get("customer") or "")
    if not user_id:
        return None

    # Persist the Stripe customer id the first time we see it. Without this
    # link there is no self-service billing portal, no way to reconcile a
    # refund back to a user, and no way to rebuild entitlements from Stripe if
    # the KV store is ever lost -- Stripe is the source of truth, KV the cache.
    customer_id = data.get("customer")
    if isinstance(customer_id, str) and customer_id:
        set_stripe_customer(kv, user_id, customer_id)

    requested_plan = metadata.get("plan", "intel")
    occurred_at = dt.datetime.fromtimestamp(
        int(event.get("created") or time.time()), tz=dt.timezone.utc).isoformat()
    growth_properties = {
        key: value for key, value in {
            "plan": requested_plan,
            "interval": metadata.get("interval"),
            "price_tier": metadata.get("price_tier"),
            "currency": str(data.get("currency") or "").upper() or None,
            "value": (
                float(data["amount_total"]) / 100
                if isinstance(data.get("amount_total"), (int, float))
                else None
            ),
            "provider": "stripe",
            "status": data.get("status"),
        }.items() if value is not None
    }
    cancellation_details = data.get("cancellation_details") or {}
    cancellation_reason = str(
        cancellation_details.get("feedback")
        or cancellation_details.get("reason")
        or ""
    ).strip()[:80]
    cancellation_comment = str(
        cancellation_details.get("comment") or ""
    ).strip()[:1000]
    if event_type == "checkout.session.completed":
        set_plan(kv, user_id, requested_plan if requested_plan in {"intel", "creator"} else "intel")
        update_subscription_lifecycle(
            kv, user_id, status="active", paid_started_at=occurred_at,
            last_paid_at=occurred_at, interval=metadata.get("interval"),
            price_tier=metadata.get("price_tier"))
        record_event(
            kv, "purchase", event_id=f"stripe:{event_id}:purchase",
            user_id=user_id, properties=growth_properties,
            occurred_at=occurred_at)
    elif event_type == "customer.subscription.updated":
        status = data.get("status", "canceled")
        previous = (event.get("data") or {}).get("previous_attributes") or {}
        set_plan(kv, user_id, _plan_for_status(status, requested_plan))
        update_subscription_lifecycle(
            kv, user_id, status=status,
            current_period_end=data.get("current_period_end"),
            cancel_at_period_end=bool(data.get("cancel_at_period_end")),
            paused=bool(data.get("pause_collection")),
            cancellation_reason=cancellation_reason or None,
            cancellation_comment=cancellation_comment or None)
        if data.get("cancel_at_period_end") and not previous.get("cancel_at_period_end"):
            cancellation_properties = dict(growth_properties)
            if cancellation_reason:
                cancellation_properties["reason"] = cancellation_reason
            record_event(
                kv, "cancellation_requested",
                event_id=f"stripe:{event_id}:cancellation_requested",
                user_id=user_id, properties=cancellation_properties,
                occurred_at=occurred_at)
        if data.get("pause_collection") and not previous.get("pause_collection"):
            record_event(
                kv, "pause", event_id=f"stripe:{event_id}:pause",
                user_id=user_id, properties=growth_properties,
                occurred_at=occurred_at)
        if (status in {"active", "trialing"}
                and previous.get("status") in {"canceled", "unpaid", "paused"}):
            record_event(
                kv, "reactivation", event_id=f"stripe:{event_id}:reactivation",
                user_id=user_id, properties=growth_properties,
                occurred_at=occurred_at)
    elif event_type == "customer.subscription.deleted":
        set_plan(kv, user_id, "canceled")
        update_subscription_lifecycle(
            kv, user_id, status="expired", expired_at=occurred_at,
            cancel_at_period_end=False,
            cancellation_reason=cancellation_reason or None,
            cancellation_comment=cancellation_comment or None)
        record_event(
            kv, "expiration", event_id=f"stripe:{event_id}:expiration",
            user_id=user_id, properties=growth_properties,
            occurred_at=occurred_at)
    elif event_type == "charge.refunded":
        # A refund under the 30-day guarantee. Stripe cancels no subscription
        # of its own accord when a charge is refunded, so without this the
        # customer keeps paid access after getting their money back -- and the
        # runbook carries a manual KV write somebody has to remember at 2am.
        # Partial refunds (a pro-rata adjustment, say) must NOT revoke.
        if REVOKE_ACCESS_ON_REFUND and data.get("refunded") is True:
            set_plan(kv, user_id, "canceled")
            kv.set(f"refunded:{user_id}", "1", ex=400 * 24 * 60 * 60)
            update_subscription_lifecycle(
                kv, user_id, status="refunded", refunded_at=occurred_at)
            record_event(
                kv, "refund", event_id=f"stripe:{event_id}:refund",
                user_id=user_id, properties=growth_properties,
                occurred_at=occurred_at)
    elif event_type == "invoice.payment_failed":
        # Dunning has started but Stripe is still retrying. Access is governed
        # by the subscription status (see _plan_for_status), so deliberately do
        # not downgrade here -- record it so support and the ops digest can see
        # who is at risk before Stripe gives up and sends `unpaid`.
        kv.set(f"dunning:{user_id}", "1", ex=45 * 24 * 60 * 60)
        update_subscription_lifecycle(
            kv, user_id, payment_status="failed",
            payment_failed_at=occurred_at)
        record_event(
            kv, "failed_payment",
            event_id=f"stripe:{event_id}:failed_payment",
            user_id=user_id, properties=growth_properties,
            occurred_at=occurred_at)
    elif event_type in {"invoice.paid", "invoice.payment_succeeded"}:
        recovered = kv.exists(f"dunning:{user_id}")
        kv.delete(f"dunning:{user_id}")
        update_subscription_lifecycle(
            kv, user_id, payment_status="paid", last_paid_at=occurred_at)
        lifecycle_event = "payment_recovered" if recovered else "renewal"
        # The first invoice is paired with checkout.session.completed and is not
        # renewal evidence.
        if recovered or data.get("billing_reason") == "subscription_cycle":
            record_event(
                kv, lifecycle_event,
                event_id=f"stripe:{event_id}:{lifecycle_event}",
                user_id=user_id, properties=growth_properties,
                occurred_at=occurred_at)
    else:
        return None

    # Record the event as processed only AFTER it has been applied. Writing the
    # dedup key first meant a KV failure mid-apply turned Stripe's retry into a
    # silent no-op -- a paid customer with no entitlement and no second chance.
    if event_id:
        kv.set(f"stripe_event:{event_id}", "1", ex=30 * 24 * 60 * 60)
    return user_id
