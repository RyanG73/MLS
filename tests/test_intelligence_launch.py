import json
from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image

from api.intel import team as team_api
from api.pub import card as public_card_api
from scripts.intelligence.builder import _hydrate_fixture_ids
from scripts.send_intelligence_notifications import render_alert
from server.conversation_card import HEIGHT, WIDTH, render_card_png
from server.intel_auth import issue_access_token
from server.intel_store import (
    delete_creator_workspace,
    export_user_data,
    get_or_create_user,
    save_creator_workspace,
    set_plan,
)
from server.kv_client import get_kv, reset_kv_for_tests
from server.kv_store import InMemoryKVStore
from server.send_ledger import already_sent, record_delivery
from server.stripe_checkout import create_checkout_session
from server.stripe_webhook import handle_event


@pytest.fixture(autouse=True)
def _fresh_kv():
    reset_kv_for_tests()
    yield
    reset_kv_for_tests()


def _authorization(user_id="user-1", plan="trial"):
    kv = get_kv()
    get_or_create_user(kv, user_id, "user@example.com")
    set_plan(kv, user_id, plan)
    token = issue_access_token("dev-only-insecure-secret", user_id, plan)
    return {"Authorization": f"Bearer {token}"}


def test_trial_can_read_team_endpoint(monkeypatch):
    monkeypatch.setattr(
        team_api._service, "get_team",
        lambda league_id, team_id, feature_id=None: {
            "league_id": league_id, "team_id": team_id, "feature_id": feature_id})
    status, _, body = team_api.handle(
        "GET", _authorization(plan="trial"),
        {"league_id": "epl", "team_id": "v1:club"})
    assert status == 200
    assert json.loads(body)["team_id"] == "v1:club"


def test_canceled_plan_cannot_read_team_endpoint(monkeypatch):
    monkeypatch.setattr(team_api._service, "get_team", lambda *_args, **_kwargs: {})
    status, _, body = team_api.handle(
        "GET", _authorization(plan="canceled"),
        {"league_id": "epl", "team_id": "v1:club"})
    assert status == 401
    assert "does not meet" in json.loads(body)["error"]


def test_checkout_uses_server_price_and_subscription_metadata(monkeypatch):
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test")
    monkeypatch.setenv("STRIPE_INTEL_PRICE_ID", "price_intel")
    monkeypatch.setenv("PUBLIC_SITE_URL", "https://entenser.example")

    class Response:
        status_code = 200

        @staticmethod
        def json():
            return {"id": "cs_test", "url": "https://checkout.stripe.com/test"}

    captured = {}

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured.update(kwargs)
        return Response()

    monkeypatch.setattr("server.stripe_checkout.requests.post", fake_post)
    session = create_checkout_session("user-1", "intel")
    assert session["id"] == "cs_test"
    assert captured["data"]["line_items[0][price]"] == "price_intel"
    assert captured["data"]["metadata[user_id]"] == "user-1"
    assert captured["data"]["subscription_data[metadata][plan]"] == "intel"
    assert captured["data"]["success_url"].startswith("https://entenser.example/")


def test_stripe_creator_lifecycle_is_webhook_authoritative():
    kv = InMemoryKVStore()
    get_or_create_user(kv, "user-1", "user@example.com")
    handle_event(kv, {
        "id": "evt_checkout", "type": "checkout.session.completed",
        "data": {"object": {
            "client_reference_id": "user-1",
            "metadata": {"user_id": "user-1", "plan": "creator"},
        }},
    })
    assert export_user_data(kv, "user-1")["plan"] == "creator"
    handle_event(kv, {
        "id": "evt_past_due", "type": "customer.subscription.updated",
        "data": {"object": {
            "status": "past_due",
            "metadata": {"user_id": "user-1", "plan": "creator"},
        }},
    })
    assert export_user_data(kv, "user-1")["plan"] == "canceled"


def test_creator_workspaces_are_bounded_and_deletable():
    kv = InMemoryKVStore()
    get_or_create_user(kv, "user-1", "user@example.com")
    workspace = save_creator_workspace(kv, "user-1", {
        "name": "North London",
        "league_id": "epl",
        "team_id": "v1:arsenal",
        "target_metric": "title",
        "card_template": "race_comparison",
    })
    stored = export_user_data(kv, "user-1")["creator_workspaces"]
    assert stored == [workspace]
    delete_creator_workspace(kv, "user-1", workspace["workspace_id"])
    assert export_user_data(kv, "user-1")["creator_workspaces"] == []


def test_shadow_record_deduplicates_shadow_but_not_first_live_send():
    kv = InMemoryKVStore()
    record_delivery(
        kv, user_id="user-1", team_ids=["v1:club"], event_ids=["event:1"],
        template_version="v1", status="shadow")
    assert already_sent(kv, "user-1", ["event:1"], "v1")
    assert not already_sent(
        kv, "user-1", ["event:1"], "v1", include_shadow=False)
    assert kv.members("send_ledger:index")


def test_material_alert_uses_configured_versioned_api_base(monkeypatch):
    monkeypatch.setenv("PUBLIC_API_URL", "https://api.example.test/v1")
    _, html_body, text_body = render_alert(
        {"user_id": "user-1"},
        [{"record": {"team": "Arsenal", "target_metric": "title"},
          "events": [{"target_metric": "title", "before_pct": 40,
                      "after_pct": 45}]}],
    )
    expected = "https://api.example.test/v1/public/unsubscribe?token="
    assert expected in html_body
    assert expected in text_body
    assert "/v1/v1/" not in html_body


def _card_payload(template):
    fixture = {
        "home": "A Very Long Football Club Name United",
        "away": "Another Exceptionally Long Athletic Association",
        "leverage_pp": 17.4,
    }
    return {
        "schema_version": 1,
        "public_safe": True,
        "template": template,
        "team": "A Very Long Football Club Name United and Athletic Association",
        "league": "International Test Competition",
        "generated": "2026-07-18 12:00 UTC",
        "snapshot_id": "v1:1234567890abcdef",
        "evidence_ids": ["fixture:v1:fixture", "snapshot:v1:snapshot"],
        "insight": {
            "fixtures": [fixture],
            "rivals": [{"team": fixture["away"], "gap_pp": -7.2}],
            "events": [{"target_metric": "title", "delta_pp": 8.1,
                        "cause_class": "result"}],
            "receipts": [{"fixture": "Long Club vs Another Club",
                          "outcome": "Home win"}],
        },
    }


@pytest.mark.parametrize("template", [
    "material_move", "highest_leverage", "turning_point",
    "race_comparison", "receipt",
])
def test_all_card_templates_render_social_dimensions(template):
    png = render_card_png(
        _card_payload(template),
        "https://api.entenser.com/v1/public/card?id=1234567890abcdef1234")
    image = Image.open(BytesIO(png))
    assert image.format == "PNG"
    assert image.size == (WIDTH, HEIGHT)
    assert len(png) < 500_000


def test_public_card_endpoint_never_requires_auth():
    payload = _card_payload("highest_leverage")
    get_kv().set("public_card:1234567890abcdef1234", json.dumps(payload))
    status, headers, body = public_card_api.handle(
        "GET", {}, {"id": "1234567890abcdef1234", "format": "png"})
    assert status == 200
    assert headers["Content-Type"] == "image/png"
    assert Image.open(BytesIO(body)).size == (WIDTH, HEIGHT)


def test_legacy_payload_fixture_ids_are_hydrated_from_snapshot():
    payload = {"games": [{
        "home": "Alpha", "away": "Beta", "date": "2026-08-01",
        "result": None,
    }]}
    snapshot = {"fixtures": [{
        "home": "Alpha", "away": "Beta", "date": "2026-08-01",
        "fixture_id": "v1:fixture", "home_id": "v1:alpha", "away_id": "v1:beta",
    }]}
    _hydrate_fixture_ids(payload, snapshot)
    assert payload["games"][0]["fixture_id"] == "v1:fixture"
    assert payload["games"][0]["home_id"] == "v1:alpha"


def test_workflows_include_launch_gates_and_protected_delivery():
    root = Path(__file__).resolve().parent.parent
    daily = (root / ".github/workflows/refresh-daily.yml").read_text()
    weekly = (root / ".github/workflows/refresh-leagues.yml").read_text()
    delivery = (root / ".github/workflows/intelligence-delivery.yml").read_text()
    api_deploy = (root / ".github/workflows/deploy-api.yml").read_text()
    for workflow in (daily, weekly):
        assert "validate_intelligence_launch.py" in workflow
        assert "publish_intelligence_artifacts.py" in workflow
        assert "report_intelligence_shadow.py" in workflow
    assert "ENABLE LIVE INTELLIGENCE" in delivery
    assert "cron: '30 12 * * *'" in delivery
    assert "vars.INTELLIGENCE_LIVE_SENDS == 'true'" in delivery
    assert "environment: intelligence-production" in delivery
    assert "INTELLIGENCE_SENDS_OWNER_APPROVED: 'true'" in delivery
    assert "UNSUBSCRIBE_SECRET: ${{ secrets.UNSUBSCRIBE_SECRET }}" in delivery
    assert "UNSUBSCRIBE_TOKEN_SECRET" not in delivery
    assert "vercel deploy --prebuilt --prod" in api_deploy


def test_vercel_bundle_excludes_private_artifacts():
    root = Path(__file__).resolve().parent.parent
    config = json.loads((root / "vercel.json").read_text())
    function = config["functions"]["api/index.py"]
    assert "data/**" in function["excludeFiles"]
    assert "webapp/data/**" in function["includeFiles"]
