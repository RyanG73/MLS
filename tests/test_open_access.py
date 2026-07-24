"""Open-access promo switch: a KV-backed flag that lets any signed-in user
reach Intel endpoints without a paid plan, for marketing pushes.

The promo never removes authentication -- a valid access token is still
required, so per-user Intel features (workspaces, journal, saved teams) keep
having somewhere to write. It only bypasses the *plan rank* check.
"""
import json
import time

import pytest

from server.kv_client import get_kv, reset_kv_for_tests
from server import open_access


@pytest.fixture(autouse=True)
def _fresh_kv():
    reset_kv_for_tests()
    yield
    reset_kv_for_tests()


@pytest.fixture(autouse=True)
def _admin_token(monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", "test-admin-token")
    yield


# ── the store ────────────────────────────────────────────────────────────────

def test_closed_by_default():
    assert open_access.is_open(get_kv()) is False
    assert open_access.get_state(get_kv()) == {"active": False}


def test_open_then_close():
    kv = get_kv()
    until = int(time.time()) + 3600
    open_access.open_promo(kv, until=until, note="launch week")
    assert open_access.is_open(kv) is True
    state = open_access.get_state(kv)
    assert state["active"] is True
    assert state["until"] == until
    assert state["note"] == "launch week"

    open_access.close_promo(kv)
    assert open_access.is_open(kv) is False


def test_expired_promo_reads_as_closed():
    """The whole point of an expiry: a promo left open must close itself.

    Written straight to KV — open_promo() refuses a past date, so this
    simulates a live promo whose window has since elapsed (and a store whose
    TTL eviction hasn't fired yet, which is the case that matters).
    """
    kv = get_kv()
    kv.set(open_access.KEY, json.dumps({"until": int(time.time()) - 1, "note": "yesterday"}))
    assert open_access.is_open(kv) is False
    assert open_access.get_state(kv)["active"] is False


def test_corrupt_promo_record_reads_as_closed():
    """Fail closed on garbage rather than throwing inside every request."""
    kv = get_kv()
    kv.set(open_access.KEY, "not json at all")
    assert open_access.is_open(kv) is False
    kv.set(open_access.KEY, json.dumps({"note": "no until field"}))
    assert open_access.is_open(kv) is False


def test_open_promo_rejects_a_past_expiry():
    with pytest.raises(ValueError):
        open_access.open_promo(get_kv(), until=int(time.time()) - 60, note="nope")


def test_open_promo_rejects_an_absurd_expiry():
    """Guards against a typo in the epoch putting the site free for years."""
    with pytest.raises(ValueError):
        open_access.open_promo(
            get_kv(), until=int(time.time()) + open_access.MAX_PROMO_SECONDS + 60,
            note="too long")


# ── entitlement bypass ───────────────────────────────────────────────────────

def _signed_in_free_user():
    """Round-trips a real magic-link signup and returns a free-plan token."""
    from api.auth import callback, request as auth_request
    auth_request._sender.sent.clear()
    auth_request.handle("POST", {}, json.dumps({"email": "promo@example.com"}).encode())
    magic_url = auth_request._sender.sent[0][1]
    _, _, body = callback.handle("GET", {}, {"token": magic_url.split("token=")[1]})
    return json.loads(body)["access_token"]


def test_free_user_is_blocked_when_promo_is_closed():
    from server.api_support import ApiError, bearer_user
    token = _signed_in_free_user()
    with pytest.raises(ApiError) as exc:
        bearer_user({"Authorization": f"Bearer {token}"}, required_plan="intel")
    assert exc.value.status == 401


def test_free_user_is_admitted_while_promo_is_open():
    from server.api_support import bearer_user
    token = _signed_in_free_user()
    open_access.open_promo(get_kv(), until=int(time.time()) + 3600, note="launch")
    user_id = bearer_user({"Authorization": f"Bearer {token}"}, required_plan="intel")
    assert user_id


def test_promo_still_requires_a_valid_token():
    """Open access is not anonymous access -- signup is still the front door."""
    from server.api_support import ApiError, bearer_user
    open_access.open_promo(get_kv(), until=int(time.time()) + 3600, note="launch")

    with pytest.raises(ApiError) as exc:
        bearer_user({}, required_plan="intel")
    assert exc.value.status == 401

    with pytest.raises(ApiError) as exc:
        bearer_user({"Authorization": "Bearer forged.token.here"}, required_plan="intel")
    assert exc.value.status == 401


def test_promo_does_not_resurrect_a_canceled_user():
    """A canceled account is a deliberate state, not a missing entitlement."""
    from server.api_support import ApiError, bearer_user
    from server.intel_store import set_plan
    token = _signed_in_free_user()
    from server.intel_auth import verify_access_token
    from server.config import access_token_secret
    user_id = verify_access_token(access_token_secret(), token)["sub"]
    set_plan(get_kv(), user_id, "canceled")
    open_access.open_promo(get_kv(), until=int(time.time()) + 3600, note="launch")
    with pytest.raises(ApiError) as exc:
        bearer_user({"Authorization": f"Bearer {token}"}, required_plan="intel")
    assert exc.value.status == 401


# ── admin endpoint ───────────────────────────────────────────────────────────

def test_admin_endpoint_requires_the_admin_token():
    from api.admin import open_access as endpoint
    status, _, _ = endpoint.handle("GET", {}, b"")
    assert status == 401
    status, _, _ = endpoint.handle("GET", {"X-Admin-Token": "wrong"}, b"")
    assert status == 401


def test_admin_endpoint_opens_reads_and_closes():
    from api.admin import open_access as endpoint
    hdrs = {"X-Admin-Token": "test-admin-token"}
    until = int(time.time()) + 3600

    status, _, body = endpoint.handle(
        "POST", hdrs, json.dumps({"until": until, "note": "launch week"}).encode())
    assert status == 200
    assert json.loads(body)["active"] is True

    status, _, body = endpoint.handle("GET", hdrs, b"")
    assert json.loads(body)["note"] == "launch week"

    status, _, body = endpoint.handle("DELETE", hdrs, b"")
    assert status == 200
    assert json.loads(body)["active"] is False


def test_admin_endpoint_accepts_days_instead_of_epoch():
    """`days` is the ergonomic form -- nobody wants to compute an epoch."""
    from api.admin import open_access as endpoint
    hdrs = {"X-Admin-Token": "test-admin-token"}
    status, _, body = endpoint.handle("POST", hdrs, json.dumps({"days": 7, "note": "week"}).encode())
    assert status == 200
    state = json.loads(body)
    assert state["active"] is True
    assert 6 * 86400 < state["until"] - time.time() < 8 * 86400


def test_admin_endpoint_rejects_a_bad_window():
    from api.admin import open_access as endpoint
    hdrs = {"X-Admin-Token": "test-admin-token"}
    status, _, _ = endpoint.handle("POST", hdrs, json.dumps({"days": -1}).encode())
    assert status == 400


def test_admin_endpoint_refuses_a_blank_admin_token(monkeypatch):
    """An unset ADMIN_TOKEN must fail closed, not admit everyone."""
    from api.admin import open_access as endpoint
    monkeypatch.delenv("ADMIN_TOKEN", raising=False)
    status, _, _ = endpoint.handle("GET", {"X-Admin-Token": ""}, b"")
    assert status == 401


# ── public config ────────────────────────────────────────────────────────────

def test_public_config_advertises_the_promo():
    """The client needs this to drop lock chrome; it must leak nothing else."""
    from api.public import config
    status, _, body = config.handle("GET", {})
    assert status == 200
    assert json.loads(body)["open_access"]["active"] is False

    until = int(time.time()) + 3600
    open_access.open_promo(get_kv(), until=until, note="launch week")
    status, _, body = config.handle("GET", {})
    payload = json.loads(body)["open_access"]
    assert payload["active"] is True
    assert payload["until"] == until
    assert payload["note"] == "launch week"
