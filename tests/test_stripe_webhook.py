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
