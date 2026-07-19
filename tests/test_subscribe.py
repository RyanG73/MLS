"""Email-capture core (launch plan E2, roadmap 1.4/1.6): KV-durable, Resend-optional."""
import json

import pytest

from server.kv_store import InMemoryKVStore
from server.api_support import ApiError
from server.subscribe import subscribe_contact


def _kv():
    return InMemoryKVStore()


def test_valid_email_recorded_in_kv():
    kv = _kv()
    out = subscribe_contact(kv, "A@Example.com", ["supporter-waitlist"])
    assert out["ok"] is True
    rec = json.loads(kv.get("subscriber:a@example.com"))
    assert rec["email"] == "a@example.com"
    assert rec["tags"] == ["supporter-waitlist"]
    assert "a@example.com" in kv.members("subscribers")


def test_tags_merge_across_calls_and_are_sanitised():
    kv = _kv()
    subscribe_contact(kv, "a@example.com", ["weekly-digest", "lg-mls"])
    out = subscribe_contact(kv, "a@example.com", ["supporter-waitlist", "BAD TAG!", "x" * 50])
    assert out["tags"] == ["lg-mls", "supporter-waitlist", "weekly-digest"]


def test_invalid_email_raises_400():
    with pytest.raises(ApiError) as e:
        subscribe_contact(_kv(), "not-an-email", [])
    assert e.value.status == 400


def test_resend_not_configured_records_kv_only(monkeypatch):
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    monkeypatch.delenv("RESEND_AUDIENCE_ID", raising=False)
    out = subscribe_contact(_kv(), "a@example.com", [])
    assert out["resend"] is False


def test_resend_configured_pushes_contact(monkeypatch):
    monkeypatch.setenv("RESEND_API_KEY", "re_test")
    monkeypatch.setenv("RESEND_AUDIENCE_ID", "aud_1")
    calls = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        calls["url"], calls["json"] = url, json

        class R:
            status_code = 201

            def raise_for_status(self):
                pass

        return R()

    monkeypatch.setattr("server.subscribe.requests.post", fake_post)
    out = subscribe_contact(_kv(), "a@example.com", ["intel-waitlist"])
    assert out["resend"] is True
    assert calls["url"] == "https://api.resend.com/audiences/aud_1/contacts"
    assert calls["json"]["email"] == "a@example.com"


def test_resend_failure_still_records_kv(monkeypatch):
    monkeypatch.setenv("RESEND_API_KEY", "re_test")
    monkeypatch.setenv("RESEND_AUDIENCE_ID", "aud_1")

    def boom(*a, **k):
        raise OSError("network down")

    monkeypatch.setattr("server.subscribe.requests.post", boom)
    kv = _kv()
    out = subscribe_contact(kv, "a@example.com", [])
    assert out["ok"] is True and out["resend"] is False
    assert kv.get("subscriber:a@example.com") is not None
