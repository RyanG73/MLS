"""Email capture (launch plan E2, roadmap 1.4/1.6): KV is the durable record,
Resend Contacts is a best-effort mirror that lights up when E1 provides keys.
E4 standing rule: contacts only — this module never sends email."""
from __future__ import annotations

import json
import os
import re
import time

import requests

from server.api_support import ApiError
from server.kv_store import KVStore

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
TAG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,39}$")
RESEND_CONTACTS_URL = "https://api.resend.com/audiences/{audience}/contacts"


def _push_to_resend(email: str) -> bool:
    """Mirror the contact into the Resend audience. Never raises: capture must
    survive Resend being unconfigured (pre-E1) or down — KV is the backfill source."""
    api_key = os.environ.get("RESEND_API_KEY")
    audience = os.environ.get("RESEND_AUDIENCE_ID")
    if not api_key or not audience:
        return False
    try:
        resp = requests.post(
            RESEND_CONTACTS_URL.format(audience=audience),
            headers={"Authorization": f"Bearer {api_key}",
                     "Content-Type": "application/json"},
            json={"email": email, "unsubscribed": False},
            timeout=8.0,
        )
        resp.raise_for_status()
        return True
    except Exception:
        return False


def subscribe_contact(kv: KVStore, email: str, tags) -> dict:
    email = (email or "").strip().lower()
    if not EMAIL_RE.match(email) or len(email) > 254:
        raise ApiError(400, "invalid email")
    clean = {t for t in (tags or []) if isinstance(t, str) and TAG_RE.match(t)}
    key = f"subscriber:{email}"
    existing = kv.get(key)
    record = json.loads(existing) if existing else {
        "email": email, "tags": [], "created": int(time.time())}
    record["tags"] = sorted(set(record["tags"]) | clean)[:20]
    record["updated"] = int(time.time())
    pushed = _push_to_resend(email)
    record["resend"] = bool(pushed or record.get("resend"))
    kv.set(key, json.dumps(record))
    kv.add_to_set("subscribers", email)
    return {"ok": True, "tags": record["tags"], "resend": record["resend"]}
