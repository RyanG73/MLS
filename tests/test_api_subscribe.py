"""Round-trip tests through api/pub/subscribe.handle (pattern: test_api_auth_flow)."""
import json

import pytest

from server.kv_client import reset_kv_for_tests


@pytest.fixture(autouse=True)
def _fresh_kv():
    reset_kv_for_tests()
    yield
    reset_kv_for_tests()


def _post(payload, ip="1.2.3.4"):
    from api.pub import subscribe
    return subscribe.handle(
        "POST", {"X-Forwarded-For": ip}, json.dumps(payload).encode())


def test_post_valid_email_returns_ok():
    status, _, body = _post({"email": "a@example.com", "tags": ["supporter-waitlist"]})
    assert status == 200
    out = json.loads(body)
    assert out["ok"] is True and out["tags"] == ["supporter-waitlist"]


def test_get_is_rejected():
    from api.pub import subscribe
    status, _, _ = subscribe.handle("GET", {}, b"")
    assert status == 405


def test_invalid_email_is_400():
    status, _, _ = _post({"email": "nope"})
    assert status == 400


def test_rate_limit_kicks_in_per_ip():
    for _ in range(10):
        status, _, _ = _post({"email": "a@example.com"})
        assert status == 200
    status, _, _ = _post({"email": "a@example.com"})
    assert status == 429
    status, _, _ = _post({"email": "b@example.com"}, ip="5.6.7.8")
    assert status == 200


def test_router_dispatches_public_subscribe():
    from api.index import _dispatch
    status, _, body = _dispatch(
        "POST", "/v1/public/subscribe", {"X-Forwarded-For": "9.9.9.9"},
        json.dumps({"email": "c@example.com"}).encode())
    assert status == 200
    assert json.loads(body)["ok"] is True
