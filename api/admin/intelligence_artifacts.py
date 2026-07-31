"""Authenticated deployment relay for compiled Club Watch team artifacts.

Vercel sensitive environment variables cannot be exported back to a GitHub
runner.  The deploy job therefore sends small batches of already-compiled,
compressed records to this endpoint; the live function performs the Upstash
writes with credentials that never leave Vercel.
"""
from __future__ import annotations

import hmac
import json
import os
import re

from server.kv_client import get_kv

MAX_RECORDS = 16
MAX_VALUE_BYTES = 1_000_000
TEAM_KEY_PREFIX = "intel:artifact:"
MANIFEST_KEY = "intel:artifact:manifest"
TEAM_KEY_RE = re.compile(r"intel:artifact:[a-z0-9-]+:[A-Za-z0-9:_-]+")


def _json(status: int, payload) -> tuple[int, dict, bytes]:
    return status, {
        "Content-Type": "application/json",
        "Cache-Control": "no-store",
    }, json.dumps(payload, separators=(",", ":")).encode()


def _authorized(headers: dict) -> bool:
    expected = os.environ.get("INTELLIGENCE_PUBLISH_TOKEN", "")
    presented = headers.get("X-Intelligence-Publish-Token", "")
    return bool(expected) and hmac.compare_digest(presented, expected)


def _valid_record(record) -> bool:
    if not isinstance(record, dict) or set(record) != {"key", "value"}:
        return False
    key = record.get("key")
    value = record.get("value")
    if not isinstance(key, str) or not isinstance(value, str):
        return False
    if not key.startswith(TEAM_KEY_PREFIX) or len(key) > 240:
        return False
    if not value or len(value.encode()) > MAX_VALUE_BYTES:
        return False
    if key == MANIFEST_KEY:
        return value.startswith("{")
    return value.startswith("gz:") and TEAM_KEY_RE.fullmatch(key) is not None


def handle(method: str, headers: dict, body: bytes = b"") -> tuple[int, dict, bytes]:
    if not _authorized(headers):
        return _json(401, {"error": "publisher authorization required"})
    if method != "POST":
        return _json(405, {"error": "method not allowed"})
    try:
        payload = json.loads(body or b"{}")
    except json.JSONDecodeError:
        return _json(400, {"error": "invalid JSON"})
    records = payload.get("records") if isinstance(payload, dict) else None
    if not isinstance(records, list) or not 1 <= len(records) <= MAX_RECORDS:
        return _json(400, {"error": f"records must contain 1-{MAX_RECORDS} items"})
    if not all(_valid_record(record) for record in records):
        return _json(400, {"error": "invalid artifact record"})

    kv = get_kv()
    for record in records:
        kv.set(record["key"], record["value"])
    return _json(200, {"published": len(records)})
