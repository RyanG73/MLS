"""Production delivers header names lowercased; handlers must still see them.

Regression cover for the 2026-07-25 launch audit's top finding: Vercel's edge
normalises header field names to lowercase (HTTP/2 requires it), but
``api/index.py`` handed handlers a plain dict built from the raw items, so
``headers.get("Authorization")`` and ``headers.get("Stripe-Signature")`` missed
in production while every exact-case test fixture passed. The effect was a
total outage of the money path: all authenticated requests 401'd and every
Stripe webhook 400'd, with no local or CI signal.

These tests exercise the lowercase spelling that production actually sends.
"""
from __future__ import annotations

import json
import time
import uuid

import pytest

from api.intel import me as intel_me
from api.stripe import webhook as stripe_webhook_endpoint
from server.config import access_token_secret
from server.http_headers import Headers
from server.intel_auth import issue_access_token
from server.intel_store import get_or_create_user, set_plan
from server.kv_client import get_kv, reset_kv_for_tests
from server.stripe_webhook import verify_stripe_signature


@pytest.fixture(autouse=True)
def _fresh_kv():
    reset_kv_for_tests()
    yield
    reset_kv_for_tests()


def _seeded_token(plan: str = "intel") -> str:
    user_id = str(uuid.uuid4())
    get_or_create_user(get_kv(), user_id, f"{user_id}@example.test")
    set_plan(get_kv(), user_id, plan)
    return issue_access_token(access_token_secret(), user_id, plan, ttl_seconds=600)


class TestHeadersMapping:
    def test_lookup_folds_case_in_both_directions(self):
        assert Headers({"authorization": "Bearer x"}).get("Authorization") == "Bearer x"
        assert Headers({"Authorization": "Bearer x"}).get("authorization") == "Bearer x"

    def test_exact_match_still_wins_and_default_is_honoured(self):
        assert Headers({"X-Client-Id": "abc"}).get("X-Client-Id") == "abc"
        assert Headers({}).get("Authorization", "") == ""

    def test_membership_and_indexing_fold_case(self):
        headers = Headers({"stripe-signature": "t=1,v1=2"})
        assert "Stripe-Signature" in headers
        assert headers["Stripe-Signature"] == "t=1,v1=2"
        with pytest.raises(KeyError):
            headers["X-Absent"]

    def test_it_is_still_a_dict(self):
        headers = Headers({"authorization": "Bearer x"})
        assert isinstance(headers, dict)
        assert dict(headers.items()) == {"authorization": "Bearer x"}


class TestAuthenticatedRequests:
    def test_lowercase_authorization_reaches_the_handler(self):
        token = _seeded_token()
        status, _, body = intel_me.handle("GET", Headers({"authorization": f"Bearer {token}"}))
        assert status == 200, body
        assert json.loads(body)["plan"] == "intel"

    def test_capitalised_authorization_still_works(self):
        token = _seeded_token()
        status, _, _ = intel_me.handle("GET", Headers({"Authorization": f"Bearer {token}"}))
        assert status == 200

    def test_a_plain_lowercase_dict_is_what_regressed(self):
        """The pre-fix production shape: a plain dict with lowercase keys."""
        token = _seeded_token()
        status, _, body = intel_me.handle("GET", {"authorization": f"Bearer {token}"})
        assert status == 401
        assert b"missing bearer token" in body


class TestStripeWebhookSignature:
    def _signed(self, secret: str, payload: bytes) -> str:
        import hashlib
        import hmac

        timestamp = str(int(time.time()))
        signature = hmac.new(
            secret.encode(), f"{timestamp}.".encode() + payload, hashlib.sha256
        ).hexdigest()
        return f"t={timestamp},v1={signature}"

    def test_lowercase_stripe_signature_verifies(self, monkeypatch):
        secret = "whsec_test_launch_audit"
        monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", secret)
        payload = json.dumps({"id": "evt_case_test", "type": "ping"}).encode()
        headers = Headers({"stripe-signature": self._signed(secret, payload)})

        status, _, body = stripe_webhook_endpoint.handle("POST", headers, payload)

        assert status == 200, body

    def test_signature_helper_rejects_a_forged_value(self):
        from server.stripe_webhook import InvalidWebhookSignature

        payload = b'{"id":"evt_x"}'
        with pytest.raises(InvalidWebhookSignature):
            verify_stripe_signature(payload, "t=1785007000,v1=deadbeef", "whsec_test")
