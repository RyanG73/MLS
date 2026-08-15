from __future__ import annotations

import hashlib
import json

import pytest

from api.account import data as account_data
from api.account import feedback as account_feedback
from api.admin import checkout as admin_checkout
from api.admin import delivery as admin_delivery
from api.auth import request as auth_request
from api.intel import sample as sample_api
from api.pub import config as public_config
from server import checkout_control
from server.growth_events import read_events, record_event, scorecard
from server.intel_auth import (
    issue_access_token,
    issue_refresh_token,
    refresh_access_token,
)
from server.intel_store import (
    delete_user_data,
    export_user_data,
    get_or_create_club_watch_sample,
    get_or_create_user,
    get_plan,
    set_plan,
    update_public_preferences,
)
from server.kv_client import get_kv, reset_kv_for_tests
from server.kv_store import InMemoryKVStore


@pytest.fixture(autouse=True)
def _fresh_state(monkeypatch):
    reset_kv_for_tests()
    for name in (
        "ENTENSER_ENV", "CHECKOUT_ENABLED", "ADMIN_TOKEN",
        "STRIPE_SECRET_KEY", "STRIPE_WEBHOOK_SECRET", "ACCESS_TOKEN_SECRET",
        "UPSTASH_REDIS_REST_URL", "UPSTASH_REDIS_REST_TOKEN",
        "CUSTOMER_TERMS_APPROVED_VERSION", "PRIVACY_POLICY_APPROVED_VERSION",
        "REFUND_POLICY_APPROVED_VERSION",
        "STRIPE_PRICE_INTEL_MONTHLY_LAUNCH",
        "STRIPE_PRICE_INTEL_ANNUAL_LAUNCH",
        "STRIPE_PRICE_INTEL_MONTHLY_STANDARD",
        "STRIPE_PRICE_INTEL_ANNUAL_STANDARD",
    ):
        monkeypatch.delenv(name, raising=False)
    auth_request._sender.sent.clear()
    yield
    reset_kv_for_tests()


def _production_checkout_env(monkeypatch):
    values = {
        "ENTENSER_ENV": "production",
        "CHECKOUT_ENABLED": "true",
        "STRIPE_SECRET_KEY": "sk_test",
        "STRIPE_WEBHOOK_SECRET": "whsec_test",
        "ACCESS_TOKEN_SECRET": "secret",
        "UPSTASH_REDIS_REST_URL": "https://redis.example",
        "UPSTASH_REDIS_REST_TOKEN": "redis-token",
        "CUSTOMER_TERMS_APPROVED_VERSION": "2026-08-01",
        "PRIVACY_POLICY_APPROVED_VERSION": "2026-08-01",
        "REFUND_POLICY_APPROVED_VERSION": "2026-08-01",
        "STRIPE_PRICE_INTEL_MONTHLY_LAUNCH": "price_launch_monthly",
        "STRIPE_PRICE_INTEL_ANNUAL_LAUNCH": "price_launch_annual",
        "STRIPE_PRICE_INTEL_MONTHLY_STANDARD": "price_standard_monthly",
        "STRIPE_PRICE_INTEL_ANNUAL_STANDARD": "price_standard_annual",
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)


def test_production_checkout_requires_all_four_immutable_prices(monkeypatch):
    # This asserts the PRODUCTION CONFIG gate. Since 2026-08-15 the free launch
    # shuts checkout ahead of that gate, which would mask it here — pin the
    # paywall on so the four-price requirement is still genuinely exercised.
    from server import open_access
    monkeypatch.setattr(open_access, "LAUNCH_FREE", False)
    _production_checkout_env(monkeypatch)
    monkeypatch.delenv("STRIPE_PRICE_INTEL_ANNUAL_STANDARD")
    state = checkout_control.get_state(InMemoryKVStore())
    assert state["enabled"] is False
    assert state["reason"] == "configuration_incomplete"
    assert state["missing"] == ["STRIPE_PRICE_INTEL_ANNUAL_STANDARD"]


def test_owner_checkout_switch_and_public_state(monkeypatch):
    _production_checkout_env(monkeypatch)
    monkeypatch.setenv("ADMIN_TOKEN", "admin-secret")
    headers = {"X-Admin-Token": "admin-secret"}

    status, _, body = admin_checkout.handle(
        "POST", headers, json.dumps({"enabled": False, "note": "rehearsal"}).encode())
    assert status == 200
    assert json.loads(body)["enabled"] is False

    status, _, body = public_config.handle("GET", {})
    assert status == 200
    checkout = json.loads(body)["checkout"]
    assert checkout["enabled"] is False
    assert "missing" not in checkout


def test_free_account_has_one_club_and_paid_account_has_ten():
    kv = InMemoryKVStore()
    get_or_create_user(kv, "free-user", "free@example.com")
    with pytest.raises(ValueError, match="one synced club"):
        update_public_preferences(kv, "free-user", {"teams": [
            {"league_id": "epl", "team_id": "a"},
            {"league_id": "epl", "team_id": "b"},
        ]})

    set_plan(kv, "free-user", "intel")
    teams = [
        {"league_id": "epl", "team_id": str(index)}
        for index in range(10)
    ]
    record = update_public_preferences(
        kv, "free-user", {"teams": teams}, plan="intel")
    assert len(record["teams"]) == 10


def test_free_sample_is_frozen_and_identity_checked():
    kv = InMemoryKVStore()
    get_or_create_user(kv, "user-1", "a@example.com")
    first = get_or_create_club_watch_sample(
        kv, "user-1", "epl", "arsenal",
        lambda: {
            "league_id": "epl", "team_id": "arsenal",
            "snapshot_id": "snapshot-1",
        })
    second = get_or_create_club_watch_sample(
        kv, "user-1", "epl", "arsenal",
        lambda: {
            "league_id": "epl", "team_id": "arsenal",
            "snapshot_id": "snapshot-2",
        })
    assert first == second
    assert second["snapshot_id"] == "snapshot-1"
    with pytest.raises(ValueError, match="already assigned"):
        get_or_create_club_watch_sample(
            kv, "user-1", "mls", "miami",
            lambda: {
                "league_id": "mls", "team_id": "miami",
                "snapshot_id": "snapshot-3",
            })
    with pytest.raises(ValueError, match="already assigned"):
        update_public_preferences(kv, "user-1", {"teams": [{
            "league_id": "mls", "team_id": "miami", "team": "Inter Miami",
        }]})

    get_or_create_user(kv, "user-2", "b@example.com")
    with pytest.raises(ValueError, match="identity"):
        get_or_create_club_watch_sample(
            kv, "user-2", "epl", "arsenal",
            lambda: {"league_id": "mls", "team_id": "miami"})


def test_sample_endpoint_requires_followed_club_and_reuses_snapshot(monkeypatch):
    kv = get_kv()
    get_or_create_user(kv, "user-1", "a@example.com")
    update_public_preferences(kv, "user-1", {"teams": [{
        "league_id": "epl", "team_id": "arsenal", "team": "Arsenal",
    }]})
    token = issue_access_token(
        "dev-only-insecure-secret", "user-1", "free")
    headers = {"Authorization": f"Bearer {token}"}

    snapshot = {"value": "snapshot-1"}

    def team_record(league_id, team_id):
        return {
            "league_id": league_id, "league_name": "Premier League",
            "team_id": team_id, "team": "Arsenal", "season_id": "2026",
            "snapshot_id": snapshot["value"], "generated": "2026-07-29",
            "calendar_mode": {"mode": "preseason"}, "target_metric": "title",
            "features": {"1": {}, "2": {}, "3": {}, "4": {}},
        }

    monkeypatch.setattr(sample_api._service, "get_team", team_record)
    status, _, body = sample_api.handle(
        "GET", headers, {"league_id": "epl", "team_id": "arsenal"})
    assert status == 200
    assert json.loads(body)["snapshot_id"] == "snapshot-1"

    snapshot["value"] = "snapshot-2"
    status, _, body = sample_api.handle(
        "GET", headers, {"league_id": "epl", "team_id": "arsenal"})
    assert status == 200
    assert json.loads(body)["snapshot_id"] == "snapshot-1"

    status, _, _ = sample_api.handle(
        "GET", headers, {"league_id": "mls", "team_id": "miami"})
    assert status == 403


def test_active_paid_account_cannot_be_deleted_and_refreshes_are_revoked():
    kv = get_kv()
    get_or_create_user(kv, "user-1", "a@example.com")
    set_plan(kv, "user-1", "intel")
    access = issue_access_token(
        "dev-only-insecure-secret", "user-1", "intel")
    headers = {"Authorization": f"Bearer {access}"}

    status, _, body = account_data.handle(
        "DELETE", headers, json.dumps({"confirmation": "DELETE"}).encode())
    assert status == 409
    assert "cancel" in json.loads(body)["error"]

    set_plan(kv, "user-1", "canceled")
    refresh = issue_refresh_token(kv, "user-1")
    refresh_hash = hashlib.sha256(refresh.encode()).hexdigest()
    assert kv.exists(f"refresh:{refresh_hash}")
    status, _, _ = account_data.handle(
        "DELETE", headers, json.dumps({"confirmation": "DELETE"}).encode())
    assert status == 200
    assert export_user_data(kv, "user-1") is None
    assert refresh_access_token(
        kv, "dev-only-insecure-secret", refresh,
        lambda user_id: get_plan(kv, user_id)) is None


def test_growth_scorecard_labels_missing_browser_inputs():
    kv = InMemoryKVStore()
    get_or_create_user(kv, "paid-user", "paid@example.com")
    set_plan(kv, "paid-user", "intel")
    record_event(kv, "purchase", user_id="paid-user")
    record_event(
        kv, "match_stakes_viewed", user_id="paid-user",
        properties={"club_id": "arsenal"})
    card = scorecard(kv)
    assert card["active_paid"] == 1
    assert card["engaged_paid"] == 1
    assert card["counts"]["purchase"] == 1
    assert card["labels"]["mau"] == "missing"


def test_magic_link_preserves_safe_club_intent_and_rejects_external_redirect(
    monkeypatch,
):
    monkeypatch.setenv("PUBLIC_SITE_URL", "https://entenser.com")
    safe = "/?league=intel&intelLeague=epl&team=arsenal&track=1"
    status, _, _ = auth_request.handle(
        "POST", {}, json.dumps({
            "email": "safe@example.com", "return_to": safe,
        }).encode())
    assert status == 200
    assert "intelLeague=epl" in auth_request._sender.sent[-1][1]
    assert "&token=" in auth_request._sender.sent[-1][1]

    status, _, _ = auth_request.handle(
        "POST", {}, json.dumps({
            "email": "unsafe@example.com",
            "return_to": "https://attacker.example/steal",
        }).encode())
    assert status == 200
    assert auth_request._sender.sent[-1][1].startswith(
        "https://entenser.com/?league=intel&token=")


def test_customer_evidence_is_categorized_and_testimonials_require_consent():
    kv = get_kv()
    get_or_create_user(kv, "user-1", "a@example.com")
    token = issue_access_token(
        "dev-only-insecure-secret", "user-1", "free")
    headers = {"Authorization": f"Bearer {token}"}

    status, _, body = account_feedback.handle(
        "POST", headers, json.dumps({
            "kind": "support",
            "category": "data_quality",
            "message": "The displayed timestamp looks stale.",
            "contact_consent": True,
        }).encode())
    assert status == 201
    saved = json.loads(body)
    assert saved["category"] == "data_quality"
    assert saved["contact_consent"] is True

    status, _, body = account_feedback.handle(
        "POST", headers, json.dumps({
            "kind": "testimonial",
            "category": "understood_change",
            "message": "This made the race understandable.",
        }).encode())
    assert status == 400
    assert "publication consent" in json.loads(body)["error"]

    status, _, body = account_feedback.handle(
        "POST", headers, json.dumps({
            "kind": "testimonial",
            "category": "understood_change",
            "message": "This made the race understandable.",
            "publication_consent": True,
        }).encode())
    assert status == 201
    assert json.loads(body)["publication_consent"] is True

    status, _, body = account_feedback.handle("GET", headers)
    assert status == 200
    assert len(json.loads(body)["items"]) == 2
    record = export_user_data(kv, "user-1")
    assert len(record["customer_evidence"]) == 2
    assert {
        row["event"] for row in read_events(kv)
    } >= {"support_request_categorized", "testimonial_consented"}


def test_owner_can_record_delivery_correction(monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", "admin-secret")
    headers = {"X-Admin-Token": "admin-secret"}
    status, _, body = admin_delivery.handle(
        "POST", headers, json.dumps({
            "user_id": "user-1",
            "template_version": "material-alert-v1",
            "delivery_ref": "provider-1",
            "reason": "Incorrect rival attribution replaced before send.",
            "team_ids": ["arsenal"],
            "event_ids": ["event-1"],
        }).encode())
    assert status == 201
    row = json.loads(body)
    assert row["status"] == "corrected"
    assert row["delivery_ref"] == "provider-1"
    assert "delivery_corrected" in {
        event["event"] for event in read_events(get_kv())}


def test_owner_can_review_a_shadow_candidate(monkeypatch):
    from server.send_ledger import record_delivery

    monkeypatch.setenv("ADMIN_TOKEN", "admin-secret")
    record_delivery(
        get_kv(),
        user_id="user-1",
        team_ids=["arsenal"],
        event_ids=["event-1"],
        template_version="material-alert-v1",
        status="shadow",
    )
    status, _, body = admin_delivery.handle(
        "POST", {"X-Admin-Token": "admin-secret"}, json.dumps({
            "action": "review_shadow",
            "user_id": "user-1",
            "template_version": "material-alert-v1",
            "event_ids": ["event-1"],
            "worth_sending": False,
            "defects": ["not_worth_sending"],
            "notes": "Ordinary movement with no supporter consequence.",
        }).encode())
    assert status == 200
    reviewed = json.loads(body)
    assert reviewed["worth_sending"] is False
    assert reviewed["defects"] == ["not_worth_sending"]
