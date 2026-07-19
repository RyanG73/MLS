#!/usr/bin/env python3
"""Run the Intelligence API locally with an optional in-memory test account."""
from __future__ import annotations

import argparse
import json
import uuid
from http.server import ThreadingHTTPServer
from urllib.parse import quote

from api.index import handler
from server.config import access_token_secret
from server.intel_auth import (
    RecordingSender, issue_access_token, issue_refresh_token, request_magic_link,
)
from server.intel_store import get_or_create_user, set_plan
from server.kv_client import get_kv


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--site-url", default="http://127.0.0.1:8000")
    parser.add_argument("--preview-league", default="epl")
    parser.add_argument("--preview-team", default="v1:1c90591709108353")
    parser.add_argument("--seed-email", default="creator@example.test")
    parser.add_argument(
        "--seed-plan", choices=["free", "trial", "intel", "creator"],
        default="creator")
    args = parser.parse_args()

    kv = get_kv()
    user_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"mailto:{args.seed_email}"))
    get_or_create_user(kv, user_id, args.seed_email)
    set_plan(kv, user_id, args.seed_plan)
    access = issue_access_token(
        access_token_secret(), user_id, args.seed_plan, ttl_seconds=24 * 3600)
    refresh = issue_refresh_token(kv, user_id)
    sender = RecordingSender()
    api_url = f"http://{args.host}:{args.port}/v1"
    preview_base = (
        f"{args.site_url.rstrip('/')}/?league=intel&api={quote(api_url, safe='')}"
        f"&intelLeague={quote(args.preview_league, safe='')}"
        f"&team={quote(args.preview_team, safe='')}")
    request_magic_link(kv, sender, args.seed_email, preview_base)
    print(json.dumps({
        "url": f"http://{args.host}:{args.port}",
        "user_id": user_id,
        "plan": args.seed_plan,
        "preview_url": sender.sent[0][1],
        "access_token": access,
        "refresh_token": refresh,
    }), flush=True)
    ThreadingHTTPServer((args.host, args.port), handler).serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
