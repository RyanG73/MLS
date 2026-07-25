"""Runtime price switch: launch $5.99 with the option to lift to $7.99.

A Stripe Price is immutable, so a price change is never an edit -- it points new
Checkout Sessions at a different, pre-created Price while Stripe keeps existing
subscribers on the one they bought. These tests pin the safety properties that
make that switch trustworthy: it fails LOW rather than high, a client cannot
choose its own tier, and a tier with no configured Price cannot be selected.
"""
from __future__ import annotations

import json
import uuid

import pytest

from api.admin import pricing as admin_pricing
from server import pricing_tier
from server.config import access_token_secret
from server.http_headers import Headers
from server.intel_auth import issue_access_token
from server.intel_store import get_or_create_user, set_plan
from server.kv_client import get_kv, reset_kv_for_tests

LAUNCH_M = "price_launch_monthly"
LAUNCH_A = "price_launch_annual"
STANDARD_M = "price_standard_monthly"
STANDARD_A = "price_standard_annual"


@pytest.fixture(autouse=True)
def _fresh(monkeypatch):
    reset_kv_for_tests()
    for name in ("STRIPE_INTEL_PRICE_ID", "ENTENSER_ENV"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("STRIPE_PRICE_INTEL_MONTHLY_LAUNCH", LAUNCH_M)
    monkeypatch.setenv("STRIPE_PRICE_INTEL_ANNUAL_LAUNCH", LAUNCH_A)
    yield
    reset_kv_for_tests()


class TestResolution:
    def test_defaults_to_launch(self):
        assert pricing_tier.get_tier(get_kv()) == "launch"
        assert pricing_tier.price_id_for("launch", "monthly") == LAUNCH_M

    def test_interval_aliases_normalise(self):
        for alias in ("annual", "year", "yearly", "ANNUAL"):
            assert pricing_tier.normalise_interval(alias) == "annual"
        for alias in ("monthly", "month", "", None, "nonsense"):
            assert pricing_tier.normalise_interval(alias) == "monthly"

    def test_legacy_single_price_env_still_works(self, monkeypatch):
        """An environment configured before the switch existed must keep working."""
        monkeypatch.delenv("STRIPE_PRICE_INTEL_MONTHLY_LAUNCH", raising=False)
        monkeypatch.setenv("STRIPE_INTEL_PRICE_ID", "price_legacy")
        assert pricing_tier.price_id_for("launch", "monthly") == "price_legacy"


class TestFailsLowNeverHigh:
    def test_unknown_stored_tier_falls_back_to_launch(self, monkeypatch):
        monkeypatch.setenv("STRIPE_PRICE_INTEL_MONTHLY_STANDARD", STANDARD_M)
        get_kv().set(pricing_tier.KEY, "premium_deluxe")
        assert pricing_tier.get_tier(get_kv()) == "launch"

    def test_tier_whose_price_vanished_falls_back_to_launch(self, monkeypatch):
        """Config drift must undercharge, never overcharge."""
        monkeypatch.setenv("STRIPE_PRICE_INTEL_MONTHLY_STANDARD", STANDARD_M)
        pricing_tier.set_tier(get_kv(), "standard")
        assert pricing_tier.get_tier(get_kv()) == "standard"
        monkeypatch.delenv("STRIPE_PRICE_INTEL_MONTHLY_STANDARD")
        assert pricing_tier.get_tier(get_kv()) == "launch"

    def test_cannot_select_a_tier_with_no_price(self):
        with pytest.raises(ValueError, match="no Stripe Price configured"):
            pricing_tier.set_tier(get_kv(), "standard")

    def test_cannot_select_a_nonsense_tier(self):
        with pytest.raises(ValueError, match="tier must be one of"):
            pricing_tier.set_tier(get_kv(), "free_forever")


class TestSwitching:
    def test_lift_and_revert(self, monkeypatch):
        monkeypatch.setenv("STRIPE_PRICE_INTEL_MONTHLY_STANDARD", STANDARD_M)
        monkeypatch.setenv("STRIPE_PRICE_INTEL_ANNUAL_STANDARD", STANDARD_A)
        state = pricing_tier.set_tier(get_kv(), "standard", "lifted after launch week")
        assert state["tier"] == "standard"
        assert state["note"] == "lifted after launch week"
        assert state["changed_at"] is not None
        assert pricing_tier.price_id_for("standard", "annual") == STANDARD_A
        # reversible in seconds if conversion falls off a cliff
        assert pricing_tier.set_tier(get_kv(), "launch")["tier"] == "launch"

    def test_state_reports_what_is_sellable(self, monkeypatch):
        monkeypatch.setenv("STRIPE_PRICE_INTEL_MONTHLY_STANDARD", STANDARD_M)
        available = pricing_tier.get_state(get_kv())["available"]
        assert available["launch"] == ["monthly", "annual"]
        assert available["standard"] == ["monthly"]   # annual not created yet


class TestCheckoutUsesTheSwitch:
    def _headers(self):
        user_id = str(uuid.uuid4())
        get_or_create_user(get_kv(), user_id, f"{user_id}@example.test")
        set_plan(get_kv(), user_id, "free")
        token = issue_access_token(access_token_secret(), user_id, "free", ttl_seconds=600)
        return Headers({"authorization": f"Bearer {token}"})

    def _capture(self, monkeypatch):
        seen = {}

        def fake_post(url, data=None, headers=None, timeout=None):
            seen["price"] = data["line_items[0][price]"]
            seen["meta_interval"] = data["metadata[interval]"]
            seen["meta_tier"] = data["metadata[price_tier]"]

            class R:
                status_code = 200

                @staticmethod
                def json():
                    return {"id": "cs_test", "url": "https://checkout.stripe.com/x"}
            return R()

        monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_x")
        monkeypatch.setattr("server.stripe_checkout.requests.post", fake_post)
        return seen

    def test_monthly_launch_is_the_default(self, monkeypatch):
        seen = self._capture(monkeypatch)
        from api.billing import checkout
        status, _, body = checkout.handle("POST", self._headers(), b'{"plan":"intel"}')
        assert status == 201, body
        assert seen["price"] == LAUNCH_M
        assert json.loads(body)["tier"] == "launch"

    def test_annual_selects_the_annual_price(self, monkeypatch):
        seen = self._capture(monkeypatch)
        from api.billing import checkout
        status, _, body = checkout.handle(
            "POST", self._headers(), b'{"plan":"intel","interval":"annual"}')
        assert status == 201, body
        assert seen["price"] == LAUNCH_A
        assert seen["meta_interval"] == "annual"

    def test_a_lift_changes_what_new_customers_are_charged(self, monkeypatch):
        monkeypatch.setenv("STRIPE_PRICE_INTEL_MONTHLY_STANDARD", STANDARD_M)
        pricing_tier.set_tier(get_kv(), "standard")
        seen = self._capture(monkeypatch)
        from api.billing import checkout
        status, _, _ = checkout.handle("POST", self._headers(), b'{"plan":"intel"}')
        assert status == 201
        assert seen["price"] == STANDARD_M
        assert seen["meta_tier"] == "standard"

    def test_client_cannot_choose_its_own_tier(self, monkeypatch):
        """A body naming a tier must be ignored, or anyone picks the cheap one."""
        monkeypatch.setenv("STRIPE_PRICE_INTEL_MONTHLY_STANDARD", STANDARD_M)
        pricing_tier.set_tier(get_kv(), "standard")
        seen = self._capture(monkeypatch)
        from api.billing import checkout
        checkout.handle("POST", self._headers(),
                        b'{"plan":"intel","tier":"launch","price_tier":"launch"}')
        assert seen["price"] == STANDARD_M


class TestAdminEndpoint:
    def test_fails_closed_without_admin_token(self, monkeypatch):
        monkeypatch.delenv("ADMIN_TOKEN", raising=False)
        status, _, _ = admin_pricing.handle("GET", Headers({"x-admin-token": "anything"}))
        assert status == 401

    def test_rejects_a_wrong_token(self, monkeypatch):
        monkeypatch.setenv("ADMIN_TOKEN", "correct")
        status, _, _ = admin_pricing.handle("GET", Headers({"x-admin-token": "wrong"}))
        assert status == 401

    def test_get_then_switch(self, monkeypatch):
        monkeypatch.setenv("ADMIN_TOKEN", "correct")
        monkeypatch.setenv("STRIPE_PRICE_INTEL_MONTHLY_STANDARD", STANDARD_M)
        headers = Headers({"x-admin-token": "correct"})   # lowercase, as prod sends
        status, _, body = admin_pricing.handle("GET", headers)
        assert status == 200
        assert json.loads(body)["tier"] == "launch"
        status, _, body = admin_pricing.handle(
            "POST", headers, json.dumps({"tier": "standard", "note": "lift"}).encode())
        assert status == 200
        assert json.loads(body)["tier"] == "standard"

    def test_switching_to_an_unconfigured_tier_is_a_400(self, monkeypatch):
        monkeypatch.setenv("ADMIN_TOKEN", "correct")
        status, _, body = admin_pricing.handle(
            "POST", Headers({"x-admin-token": "correct"}),
            json.dumps({"tier": "standard"}).encode())
        assert status == 400
        assert b"no Stripe Price configured" in body
