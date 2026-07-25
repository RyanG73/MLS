import hashlib
import hmac
import time

import pytest

from server.intel_store import get_or_create_user, get_plan
from server.kv_store import InMemoryKVStore
from server.stripe_webhook import (
    InvalidWebhookSignature, handle_event, verify_stripe_signature,
)

SECRET = "whsec_test"


def _sign(payload: bytes, timestamp: int, secret: str = SECRET) -> str:
    signed_payload = f"{timestamp}.".encode("utf-8") + payload
    sig = hmac.new(secret.encode("utf-8"), signed_payload, hashlib.sha256).hexdigest()
    return f"t={timestamp},v1={sig}"


def test_valid_signature_is_accepted():
    payload = b'{"id":"evt_1"}'
    now = time.time()
    header = _sign(payload, int(now))
    verify_stripe_signature(payload, header, SECRET, now=now)  # must not raise


def test_tampered_payload_is_rejected():
    payload = b'{"id":"evt_1"}'
    now = time.time()
    header = _sign(payload, int(now))
    with pytest.raises(InvalidWebhookSignature):
        verify_stripe_signature(b'{"id":"evt_2"}', header, SECRET, now=now)


def test_wrong_secret_is_rejected():
    payload = b'{"id":"evt_1"}'
    now = time.time()
    header = _sign(payload, int(now))
    with pytest.raises(InvalidWebhookSignature):
        verify_stripe_signature(payload, header, "wrong-secret", now=now)


def test_stale_timestamp_is_rejected():
    payload = b'{"id":"evt_1"}'
    now = time.time()
    header = _sign(payload, int(now) - 3600)  # 1 hour old
    with pytest.raises(InvalidWebhookSignature):
        verify_stripe_signature(payload, header, SECRET, now=now)


def test_malformed_header_is_rejected():
    with pytest.raises(InvalidWebhookSignature):
        verify_stripe_signature(b"{}", "not-a-real-header", SECRET)


def test_checkout_completed_activates_intel_plan():
    kv = InMemoryKVStore()
    get_or_create_user(kv, "user-1", "a@example.com")
    event = {"id": "evt_1", "type": "checkout.session.completed",
             "data": {"object": {"metadata": {"user_id": "user-1"}}}}
    handle_event(kv, event)
    assert get_plan(kv, "user-1") == "intel"


def test_subscription_deleted_downgrades_to_canceled():
    kv = InMemoryKVStore()
    get_or_create_user(kv, "user-1", "a@example.com")
    handle_event(kv, {"id": "evt_1", "type": "checkout.session.completed",
                       "data": {"object": {"metadata": {"user_id": "user-1"}}}})
    handle_event(kv, {"id": "evt_2", "type": "customer.subscription.deleted",
                       "data": {"object": {"metadata": {"user_id": "user-1"}}}})
    assert get_plan(kv, "user-1") == "canceled"


def test_subscription_updated_maps_status_to_plan():
    kv = InMemoryKVStore()
    get_or_create_user(kv, "user-1", "a@example.com")
    handle_event(kv, {"id": "evt_1", "type": "customer.subscription.updated",
                       "data": {"object": {"metadata": {"user_id": "user-1"}, "status": "trialing"}}})
    assert get_plan(kv, "user-1") == "trial"


def test_duplicate_event_id_is_a_no_op():
    kv = InMemoryKVStore()
    get_or_create_user(kv, "user-1", "a@example.com")
    event = {"id": "evt_1", "type": "checkout.session.completed",
              "data": {"object": {"metadata": {"user_id": "user-1"}}}}
    handle_event(kv, event)
    handle_event(kv, {**event, "data": {"object": {"metadata": {"user_id": "user-1"},
                                                     "status": "should_be_ignored"}}})
    assert get_plan(kv, "user-1") == "intel"  # second (duplicate) delivery had no effect


def test_unknown_event_type_is_a_safe_no_op():
    kv = InMemoryKVStore()
    get_or_create_user(kv, "user-1", "a@example.com")
    result = handle_event(kv, {"id": "evt_1", "type": "some.other.event",
                                 "data": {"object": {"metadata": {"user_id": "user-1"}}}})
    assert result is None
    assert get_plan(kv, "user-1") == "free"


def test_event_without_user_id_is_a_safe_no_op():
    kv = InMemoryKVStore()
    result = handle_event(kv, {"id": "evt_1", "type": "checkout.session.completed",
                                 "data": {"object": {}}})
    assert result is None


# ── Launch-audit additions (2026-07-25) ──────────────────────────────────────

def test_past_due_keeps_access_during_stripe_dunning():
    """Stripe retries a declined renewal for ~3 weeks before giving up. Cutting
    access on the first decline punishes a customer whose card merely expired."""
    kv = InMemoryKVStore()
    get_or_create_user(kv, "user-1", "a@example.com")
    handle_event(kv, {"id": "evt_1", "type": "checkout.session.completed",
                      "data": {"object": {"metadata": {"user_id": "user-1"}}}})
    handle_event(kv, {"id": "evt_2", "type": "customer.subscription.updated",
                      "data": {"object": {"metadata": {"user_id": "user-1"},
                                          "status": "past_due"}}})
    assert get_plan(kv, "user-1") == "intel"


def test_unpaid_is_where_access_actually_ends():
    kv = InMemoryKVStore()
    get_or_create_user(kv, "user-1", "a@example.com")
    handle_event(kv, {"id": "evt_1", "type": "checkout.session.completed",
                      "data": {"object": {"metadata": {"user_id": "user-1"}}}})
    handle_event(kv, {"id": "evt_2", "type": "customer.subscription.updated",
                      "data": {"object": {"metadata": {"user_id": "user-1"},
                                          "status": "unpaid"}}})
    assert get_plan(kv, "user-1") == "canceled"


def test_payment_failed_flags_dunning_without_revoking():
    kv = InMemoryKVStore()
    get_or_create_user(kv, "user-1", "a@example.com")
    handle_event(kv, {"id": "evt_1", "type": "checkout.session.completed",
                      "data": {"object": {"metadata": {"user_id": "user-1"}}}})
    result = handle_event(kv, {"id": "evt_2", "type": "invoice.payment_failed",
                               "data": {"object": {"subscription_details":
                                                   {"metadata": {"user_id": "user-1"}}}}})
    assert result == "user-1"
    assert kv.exists("dunning:user-1")
    assert get_plan(kv, "user-1") == "intel"


def test_a_failed_apply_leaves_the_event_retryable():
    """The dedup key must be written only after the event is applied, or a KV
    failure mid-apply turns Stripe's retry into a silent no-op and the paying
    customer never gets an entitlement."""
    class FailingOnce(InMemoryKVStore):
        fail = False

        def set(self, key, value, ex=None):
            if self.fail and key.startswith("user:"):
                self.fail = False
                raise RuntimeError("KV write failed")
            return super().set(key, value, ex=ex)

    kv = FailingOnce()
    get_or_create_user(kv, "user-1", "a@example.com")
    kv.fail = True   # arm only for the entitlement write under test
    event = {"id": "evt_1", "type": "checkout.session.completed",
             "data": {"object": {"metadata": {"user_id": "user-1"}}}}
    with pytest.raises(RuntimeError):
        handle_event(kv, event)
    assert not kv.exists("stripe_event:evt_1")   # retryable, not swallowed
    handle_event(kv, event)                      # Stripe's redelivery
    assert get_plan(kv, "user-1") == "intel"
