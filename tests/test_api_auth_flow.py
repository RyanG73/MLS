"""End-to-end round-trip tests through the api/*.py handle() adapters --
no real HTTP server, just calling the same framework-agnostic
handle(method, headers, body) functions a real request would reach.
"""
import hashlib
import hmac
import json
import time

import pytest

from server.kv_client import reset_kv_for_tests


@pytest.fixture(autouse=True)
def _fresh_kv():
    reset_kv_for_tests()
    yield
    reset_kv_for_tests()


def test_full_auth_round_trip_then_authenticated_request():
    from api.auth import callback, request as auth_request
    from api.intel import me

    auth_request._sender.sent.clear()
    status, _, body = auth_request.handle("POST", {}, json.dumps({"email": "a@example.com"}).encode())
    assert status == 200
    assert len(auth_request._sender.sent) == 1
    magic_url = auth_request._sender.sent[0][1]
    token = magic_url.split("token=")[1]

    status, _, body = callback.handle("GET", {}, {"token": token})
    assert status == 200
    tokens = json.loads(body)
    access_token = tokens["access_token"]

    status, _, body = me.handle("GET", {"Authorization": f"Bearer {access_token}"})
    assert status == 200
    assert json.loads(body)["plan"] == "free"


def test_me_rejects_missing_authorization_header():
    from api.intel import me
    status, _, _ = me.handle("GET", {})
    assert status == 401


def test_me_rejects_forged_token():
    from api.intel import me
    status, _, _ = me.handle("GET", {"Authorization": "Bearer not.a.real.token"})
    assert status == 401


def test_callback_rejects_unknown_token():
    from api.auth import callback
    status, _, _ = callback.handle("GET", {}, {"token": "never-issued"})
    assert status == 401


def test_auth_request_is_rate_limited():
    from api.auth import request as auth_request
    auth_request._sender.sent.clear()
    for _ in range(auth_request.RATE_LIMIT_MAX):
        status, _, _ = auth_request.handle("POST", {}, json.dumps({"email": "spam@example.com"}).encode())
        assert status == 200
    status, _, _ = auth_request.handle("POST", {}, json.dumps({"email": "spam@example.com"}).encode())
    assert status == 429


def test_refresh_then_me_reflects_current_plan_after_stripe_upgrade():
    from api.auth import callback, refresh as auth_refresh, request as auth_request
    from api.intel import me
    from api.stripe import webhook as stripe_webhook

    auth_request._sender.sent.clear()
    auth_request.handle("POST", {}, json.dumps({"email": "b@example.com"}).encode())
    token = auth_request._sender.sent[0][1].split("token=")[1]
    _, _, body = callback.handle("GET", {}, {"token": token})
    tokens = json.loads(body)
    user_id = None
    # Recover user_id via a fresh /intel/me call using the just-issued access token.
    _, _, me_body = me.handle("GET", {"Authorization": f"Bearer {tokens['access_token']}"})
    user_id = json.loads(me_body)["user_id"]

    payload = json.dumps({
        "id": "evt_test_1", "type": "checkout.session.completed",
        "data": {"object": {"metadata": {"user_id": user_id}}},
    }).encode()
    now = int(time.time())
    sig = hmac.new(stripe_webhook._webhook_secret().encode(),
                    f"{now}.".encode() + payload, hashlib.sha256).hexdigest()
    status, _, _ = stripe_webhook.handle("POST", {"Stripe-Signature": f"t={now},v1={sig}"}, payload)
    assert status == 200

    status, _, new_access = auth_refresh.handle(
        "POST", {}, json.dumps({"refresh_token": tokens["refresh_token"]}).encode())
    assert status == 200
    new_access_token = json.loads(new_access)["access_token"]

    _, _, me_body2 = me.handle("GET", {"Authorization": f"Bearer {new_access_token}"})
    assert json.loads(me_body2)["plan"] == "intel"


def test_stripe_webhook_rejects_bad_signature():
    from api.stripe import webhook as stripe_webhook
    status, _, _ = stripe_webhook.handle("POST", {"Stripe-Signature": "t=1,v1=bad"}, b"{}")
    assert status == 400
