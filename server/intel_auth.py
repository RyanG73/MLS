#!/usr/bin/env python3
"""S5: magic-link auth + signed access/refresh tokens + entitlement
middleware (docs/intelligence-hub-implementation-instructions.md §4.8, §5 S5).

Token format is a minimal HS256 JWT (header.payload.signature, base64url,
HMAC-SHA256) using only the standard library — no PyJWT dependency, same
"no new tooling unless it earns its keep" pattern as webapp/sim-engine.js.

MagicLinkSender remains injectable for tests. Production selects the Resend
adapter in server.email_client and persistent Upstash storage in
server.kv_client; both fail closed when production credentials are absent.

The server is always authoritative for entitlement state
(docs/intelligence-hub-implementation-instructions.md §2 rule 7: "No
localStorage security theater"): access tokens carry a plan claim for fast
client display, but require_entitlement() always re-checks the CURRENT
plan in the KV-backed user record, never trusting a stale claim from an
old token.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from typing import Protocol

from server.kv_store import KVStore

MAGIC_LINK_TTL_SECONDS = 15 * 60                # 15 minutes
ACCESS_TOKEN_TTL_SECONDS = 60 * 60              # 1 hour
REFRESH_TOKEN_TTL_SECONDS = 30 * 24 * 60 * 60   # 30 days


class MagicLinkSender(Protocol):
    def send(self, email: str, magic_link_url: str) -> None: ...


class RecordingSender:
    """Development/test double that records sends without contacting Resend."""

    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []

    def send(self, email: str, magic_link_url: str) -> None:
        self.sent.append((email, magic_link_url))


class InvalidToken(Exception):
    """Raised by verify_access_token / require_entitlement for a missing,
    forged, expired, or insufficiently-entitled token."""


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(s: str) -> bytes:
    padding = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + padding)


def _sign(secret: str, message: str) -> str:
    return _b64url_encode(hmac.new(secret.encode("utf-8"), message.encode("utf-8"), hashlib.sha256).digest())


def issue_access_token(secret: str, user_id: str, plan: str, ttl_seconds: int = ACCESS_TOKEN_TTL_SECONDS) -> str:
    """A minimal HS256 JWT: header.payload.signature, base64url, HMAC-SHA256.
    `plan` is a claim for fast client-side display only — require_entitlement
    always re-checks the authoritative KV record, never this claim alone."""
    header = _b64url_encode(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode())
    payload = _b64url_encode(json.dumps({
        "sub": user_id, "plan": plan,
        "iat": int(time.time()), "exp": int(time.time()) + ttl_seconds,
    }, separators=(",", ":")).encode())
    signature = _sign(secret, f"{header}.{payload}")
    return f"{header}.{payload}.{signature}"


def verify_access_token(secret: str, token: str) -> dict:
    """Verify signature and expiry; return the decoded claims. Raises
    InvalidToken for anything malformed, forged, or expired."""
    try:
        header, payload, signature = token.split(".")
    except ValueError:
        raise InvalidToken("malformed token")
    expected_sig = _sign(secret, f"{header}.{payload}")
    if not hmac.compare_digest(signature, expected_sig):
        raise InvalidToken("bad signature")
    try:
        claims = json.loads(_b64url_decode(payload))
    except (ValueError, json.JSONDecodeError):
        raise InvalidToken("malformed payload")
    if claims.get("exp", 0) < time.time():
        raise InvalidToken("expired")
    return claims


def request_magic_link(kv: KVStore, sender: MagicLinkSender, email: str, base_url: str) -> None:
    """Issue a one-time magic-link token for `email`, store its hash (never
    the raw token) in the KV store with a short TTL, and hand the sender a
    URL containing the raw token."""
    raw_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    kv.set(f"magic_link:{token_hash}", email, ex=MAGIC_LINK_TTL_SECONDS)
    separator = "&" if "?" in base_url else "?"
    sender.send(email, f"{base_url}{separator}token={raw_token}")


def verify_magic_link(kv: KVStore, raw_token: str) -> str | None:
    """Consume a one-time magic-link token. Returns the associated email, or
    None if the token is missing/expired/already used. Always deletes the
    token first (one-time use, even on a race)."""
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    key = f"magic_link:{token_hash}"
    email = kv.get(key)
    kv.delete(key)
    return email


def issue_refresh_token(kv: KVStore, user_id: str) -> str:
    """Opaque, server-tracked refresh token (looked up by hash in the KV
    store, unlike the access token, which is stateless) — so a refresh
    token can be revoked (logout, plan cancellation) without waiting for
    natural expiry."""
    raw_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    kv.set(f"refresh:{token_hash}", user_id, ex=REFRESH_TOKEN_TTL_SECONDS)
    return raw_token


def revoke_refresh_token(kv: KVStore, raw_token: str) -> None:
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    kv.delete(f"refresh:{token_hash}")


def refresh_access_token(kv: KVStore, secret: str, raw_refresh_token: str,
                          current_plan_lookup) -> str | None:
    """Exchange a valid refresh token for a new access token.
    `current_plan_lookup` is a callable(user_id) -> plan, so the new
    token's plan claim reflects the CURRENT entitlement state, not
    whatever it was when the refresh token was issued. Returns None if the
    refresh token is missing/expired/revoked."""
    token_hash = hashlib.sha256(raw_refresh_token.encode("utf-8")).hexdigest()
    user_id = kv.get(f"refresh:{token_hash}")
    if user_id is None:
        return None
    plan = current_plan_lookup(user_id)
    return issue_access_token(secret, user_id, plan)


def require_entitlement(secret: str, token: str, current_plan_lookup, min_plan_rank: dict[str, int],
                         required_plan: str) -> str:
    """Verify `token`, then re-check the CURRENT plan from
    `current_plan_lookup(user_id)` against `required_plan` using
    `min_plan_rank` (e.g. {"free": 0, "trial": 1, "intel": 2, "creator": 3}).
    Returns the user_id on success. Raises InvalidToken on any failure —
    expired token, or a plan that no longer meets the requirement (covers
    canceled/downgraded users transparently, since the check is always
    against live state, never the token's own plan claim)."""
    claims = verify_access_token(secret, token)
    user_id = claims["sub"]
    current_plan = current_plan_lookup(user_id)
    if min_plan_rank.get(current_plan, -1) < min_plan_rank.get(required_plan, 0):
        raise InvalidToken(f"plan {current_plan!r} does not meet required {required_plan!r}")
    return user_id
