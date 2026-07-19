import time

import pytest

from server.intel_auth import (
    InvalidToken, RecordingSender, issue_access_token, issue_refresh_token,
    refresh_access_token, request_magic_link, require_entitlement,
    revoke_refresh_token, verify_access_token, verify_magic_link,
)
from server.kv_store import InMemoryKVStore

SECRET = "test-secret"
PLAN_RANK = {"free": 0, "trial": 1, "intel": 2, "creator": 3, "canceled": -1}


def test_access_token_roundtrip():
    token = issue_access_token(SECRET, "user-1", "intel")
    claims = verify_access_token(SECRET, token)
    assert claims["sub"] == "user-1" and claims["plan"] == "intel"


def test_access_token_rejects_tampered_signature():
    token = issue_access_token(SECRET, "user-1", "intel")
    header, payload, sig = token.split(".")
    tampered = f"{header}.{payload}.{sig[:-1]}x"
    with pytest.raises(InvalidToken):
        verify_access_token(SECRET, tampered)


def test_access_token_rejects_wrong_secret():
    token = issue_access_token(SECRET, "user-1", "intel")
    with pytest.raises(InvalidToken):
        verify_access_token("wrong-secret", token)


def test_access_token_rejects_malformed_token():
    with pytest.raises(InvalidToken):
        verify_access_token(SECRET, "not-a-real-token")


def test_access_token_rejects_expired():
    token = issue_access_token(SECRET, "user-1", "intel", ttl_seconds=-1)
    with pytest.raises(InvalidToken):
        verify_access_token(SECRET, token)


def test_magic_link_request_and_verify_roundtrip():
    kv = InMemoryKVStore()
    sender = RecordingSender()
    request_magic_link(kv, sender, "user@example.com", "https://entenser.com/auth/callback")
    assert len(sender.sent) == 1
    email, url = sender.sent[0]
    assert email == "user@example.com"
    token = url.split("token=")[1]
    assert verify_magic_link(kv, token) == "user@example.com"


def test_magic_link_is_one_time_use():
    kv = InMemoryKVStore()
    sender = RecordingSender()
    request_magic_link(kv, sender, "user@example.com", "https://x/callback")
    token = sender.sent[0][1].split("token=")[1]
    assert verify_magic_link(kv, token) == "user@example.com"
    assert verify_magic_link(kv, token) is None  # second use fails


def test_magic_link_unknown_token_returns_none():
    kv = InMemoryKVStore()
    assert verify_magic_link(kv, "never-issued") is None


def test_refresh_token_issues_new_access_token_with_current_plan():
    kv = InMemoryKVStore()
    refresh = issue_refresh_token(kv, "user-1")
    new_access = refresh_access_token(kv, SECRET, refresh, lambda uid: "intel")
    claims = verify_access_token(SECRET, new_access)
    assert claims["sub"] == "user-1" and claims["plan"] == "intel"


def test_refresh_token_reflects_plan_change_since_issuance():
    """The whole point of re-checking on refresh: a user downgraded after
    their refresh token was issued gets the CURRENT plan, not a stale one."""
    kv = InMemoryKVStore()
    refresh = issue_refresh_token(kv, "user-1")
    new_access = refresh_access_token(kv, SECRET, refresh, lambda uid: "canceled")
    claims = verify_access_token(SECRET, new_access)
    assert claims["plan"] == "canceled"


def test_revoked_refresh_token_cannot_be_used():
    kv = InMemoryKVStore()
    refresh = issue_refresh_token(kv, "user-1")
    revoke_refresh_token(kv, refresh)
    assert refresh_access_token(kv, SECRET, refresh, lambda uid: "intel") is None


def test_unknown_refresh_token_returns_none():
    kv = InMemoryKVStore()
    assert refresh_access_token(kv, SECRET, "never-issued", lambda uid: "intel") is None


def test_require_entitlement_allows_sufficient_plan():
    token = issue_access_token(SECRET, "user-1", "intel")
    user_id = require_entitlement(SECRET, token, lambda uid: "intel", PLAN_RANK, required_plan="intel")
    assert user_id == "user-1"


def test_require_entitlement_rejects_insufficient_plan():
    token = issue_access_token(SECRET, "user-1", "free")
    with pytest.raises(InvalidToken):
        require_entitlement(SECRET, token, lambda uid: "free", PLAN_RANK, required_plan="intel")


def test_require_entitlement_rechecks_current_plan_not_token_claim():
    """The critical security property: a still-valid access token issued
    while the user was 'intel' must be rejected once their CURRENT plan
    (looked up live, not from the token) has been canceled."""
    token = issue_access_token(SECRET, "user-1", "intel")
    with pytest.raises(InvalidToken):
        require_entitlement(SECRET, token, lambda uid: "canceled", PLAN_RANK, required_plan="intel")
