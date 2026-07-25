"""Self-service cancellation via Stripe's hosted Billing Portal.

Added by the 2026-07-25 launch audit: the paid tier previously had no
cancellation path at all, which is a consumer-protection blocker independent of
whether anyone ever asked to cancel.
"""
from __future__ import annotations

import json
import uuid

import pytest

from api.billing import portal as billing_portal
from server.config import access_token_secret
from server.http_headers import Headers
from server.intel_auth import issue_access_token
from server.intel_store import (
    get_or_create_user, get_stripe_customer, set_plan, set_stripe_customer,
)
from server.kv_client import get_kv, reset_kv_for_tests


@pytest.fixture(autouse=True)
def _fresh_kv():
    reset_kv_for_tests()
    yield
    reset_kv_for_tests()


def _user(plan="intel", customer=None):
    user_id = str(uuid.uuid4())
    get_or_create_user(get_kv(), user_id, f"{user_id}@example.test")
    set_plan(get_kv(), user_id, plan)
    if customer:
        set_stripe_customer(get_kv(), user_id, customer)
    token = issue_access_token(access_token_secret(), user_id, plan, ttl_seconds=600)
    return user_id, Headers({"authorization": f"Bearer {token}"})


class TestCustomerLink:
    def test_customer_id_round_trips_and_reverse_indexes(self):
        user_id, _ = _user(customer="cus_test123")
        assert get_stripe_customer(get_kv(), user_id) == "cus_test123"
        # reverse index is what allows rebuilding an entitlement from Stripe
        assert get_kv().get("stripe_customer:cus_test123") == user_id

    def test_webhook_persists_the_customer_id(self):
        from server.stripe_webhook import handle_event
        kv = get_kv()
        user_id = str(uuid.uuid4())
        get_or_create_user(kv, user_id, "a@example.test")
        handle_event(kv, {
            "id": "evt_cus", "type": "checkout.session.completed",
            "data": {"object": {"metadata": {"user_id": user_id}, "customer": "cus_from_hook"}},
        })
        assert get_stripe_customer(kv, user_id) == "cus_from_hook"


class TestPortalEndpoint:
    def test_requires_authentication(self):
        status, _, _ = billing_portal.handle("POST", Headers({}), b"")
        assert status == 401

    def test_rejects_non_post(self):
        _, headers = _user(customer="cus_x")
        status, _, _ = billing_portal.handle("GET", headers, b"")
        assert status == 405

    def test_404_when_the_user_never_bought_anything(self):
        _, headers = _user(plan="free")
        status, _, body = billing_portal.handle("POST", headers, b"")
        assert status == 404
        assert b"no billing account" in body

    def test_a_canceled_user_can_still_reach_their_invoices(self, monkeypatch):
        """Cancellation must not lock someone out of their own billing history."""
        seen = {}

        def fake_create(customer_id):
            seen["customer"] = customer_id
            return {"url": "https://billing.stripe.com/session/test"}

        monkeypatch.setattr(billing_portal, "create_portal_session", fake_create)
        _, headers = _user(plan="canceled", customer="cus_canceled")
        status, _, body = billing_portal.handle("POST", headers, b"")
        assert status == 200
        assert json.loads(body)["url"].startswith("https://billing.stripe.com/")
        assert seen["customer"] == "cus_canceled"

    def test_customer_id_is_never_taken_from_the_client(self, monkeypatch):
        """A forged body must not open somebody else's billing portal."""
        seen = {}

        def fake_create(customer_id):
            seen["customer"] = customer_id
            return {"url": "https://billing.stripe.com/session/test"}

        monkeypatch.setattr(billing_portal, "create_portal_session", fake_create)
        _, headers = _user(customer="cus_mine")
        status, _, _ = billing_portal.handle(
            "POST", headers, json.dumps({"customer": "cus_someone_else"}).encode())
        assert status == 200
        assert seen["customer"] == "cus_mine"

    def test_missing_stripe_key_is_a_503_not_a_crash(self, monkeypatch):
        monkeypatch.delenv("STRIPE_SECRET_KEY", raising=False)
        monkeypatch.delenv("ENTENSER_ENV", raising=False)
        _, headers = _user(customer="cus_x")
        status, _, _ = billing_portal.handle("POST", headers, b"")
        assert status == 503


class TestCanceledUsersKeepTheirOwnRecords:
    """GDPR export/erasure must survive cancellation (launch audit 2026-07-25)."""

    def test_canceled_user_can_export_their_data(self):
        from api.account import data as account_data
        _, headers = _user(plan="canceled")
        status, _, body = account_data.handle("GET", headers, b"{}")
        assert status == 200, body

    def test_canceled_user_can_delete_their_data(self):
        from api.account import data as account_data
        _, headers = _user(plan="canceled")
        status, _, body = account_data.handle(
            "DELETE", headers, json.dumps({"confirmation": "DELETE"}).encode())
        assert status == 200, body

    def test_account_endpoints_still_reject_a_forged_token(self):
        from api.account import data as account_data
        status, _, _ = account_data.handle(
            "GET", Headers({"authorization": "Bearer not.a.real.token"}), b"{}")
        assert status == 401

    def test_canceled_user_still_cannot_reach_paid_features(self):
        """The relaxation is scoped to account management, not entitlements."""
        from api.intel import journal
        _, headers = _user(plan="canceled")
        status, _, _ = journal.handle("GET", headers, {}, b"")
        assert status == 401


class TestOnlyDefinedPlansArePurchasable:
    """A plan nobody has priced or documented must not be buyable."""

    def test_creator_checkout_is_rejected(self):
        from api.billing import checkout
        _, headers = _user(plan="free")
        status, _, body = checkout.handle(
            "POST", headers, json.dumps({"plan": "creator"}).encode())
        assert status == 400
        assert b"not available for purchase" in body

    def test_unknown_plan_is_rejected(self):
        from api.billing import checkout
        _, headers = _user(plan="free")
        status, _, _ = checkout.handle(
            "POST", headers, json.dumps({"plan": "enterprise"}).encode())
        assert status == 400

    def test_intel_is_still_purchasable(self, monkeypatch):
        from api.billing import checkout
        monkeypatch.delenv("STRIPE_SECRET_KEY", raising=False)
        monkeypatch.delenv("ENTENSER_ENV", raising=False)
        _, headers = _user(plan="free")
        status, _, _ = checkout.handle(
            "POST", headers, json.dumps({"plan": "intel"}).encode())
        assert status == 503   # reached Stripe config, i.e. plan was accepted


class TestRefundRevokesAccess:
    """The 30-day guarantee's implementation (launch audit follow-up G9)."""

    def _refund_event(self, customer, refunded=True, event_id="evt_refund"):
        return {"id": event_id, "type": "charge.refunded",
                "data": {"object": {"customer": customer, "refunded": refunded}}}

    def test_full_refund_revokes_the_entitlement(self):
        from server.stripe_webhook import handle_event
        kv = get_kv()
        user_id, _ = _user(plan="intel", customer="cus_refund")
        handle_event(kv, self._refund_event("cus_refund"))
        from server.intel_store import get_plan
        assert get_plan(kv, user_id) == "canceled"
        assert kv.exists(f"refunded:{user_id}")

    def test_partial_refund_does_not_revoke(self):
        """A pro-rata adjustment is not someone taking the guarantee."""
        from server.stripe_webhook import handle_event
        from server.intel_store import get_plan
        kv = get_kv()
        user_id, _ = _user(plan="intel", customer="cus_partial")
        handle_event(kv, self._refund_event("cus_partial", refunded=False))
        assert get_plan(kv, user_id) == "intel"

    def test_refund_for_an_unknown_customer_is_a_safe_no_op(self):
        from server.stripe_webhook import handle_event
        assert handle_event(get_kv(), self._refund_event("cus_never_seen")) is None

    def test_refunded_user_can_still_reach_their_own_records(self):
        from api.account import data as account_data
        from server.stripe_webhook import handle_event
        user_id, headers = _user(plan="intel", customer="cus_r2")
        handle_event(get_kv(), self._refund_event("cus_r2"))
        status, _, _ = account_data.handle("GET", headers, b"{}")
        assert status == 200


class TestCheckoutRateLimit:
    def test_checkout_is_rate_limited(self, monkeypatch):
        from api.billing import checkout
        monkeypatch.delenv("STRIPE_SECRET_KEY", raising=False)
        monkeypatch.delenv("ENTENSER_ENV", raising=False)
        _, headers = _user(plan="free")
        body = json.dumps({"plan": "intel"}).encode()
        for _ in range(checkout.CHECKOUT_RATE_LIMIT_MAX):
            status, _, _ = checkout.handle("POST", headers, body)
            assert status == 503      # reached Stripe config = allowed through
        status, _, out = checkout.handle("POST", headers, body)
        assert status == 429, out
