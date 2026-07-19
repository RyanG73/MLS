#!/usr/bin/env python3
"""Publish compiled private intelligence artifacts to authenticated Upstash KV."""
from __future__ import annotations

import argparse
import base64
import gzip
import json
import os
import sys
from pathlib import Path

from server.upstash_kv import UpstashKVStore


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("data/team_intelligence"))
    parser.add_argument("--allow-missing-config", action="store_true")
    args = parser.parse_args()
    url = os.environ.get("UPSTASH_REDIS_REST_URL")
    token = os.environ.get("UPSTASH_REDIS_REST_TOKEN")
    if not url or not token:
        message = "[publish-intelligence] Upstash configuration unavailable"
        if args.allow_missing_config:
            print(message + "; skipped")
            return 0
        print(message, file=sys.stderr)
        return 2
    manifest_path = args.root / "manifest.json"
    if not manifest_path.exists():
        print("[publish-intelligence] build_team_intelligence.py must run first", file=sys.stderr)
        return 2
    kv = UpstashKVStore(url, token, timeout=15)
    manifest = json.loads(manifest_path.read_text())
    published = 0
    for league_id, league in manifest["leagues"].items():
        if league.get("status") != "ok":
            continue
        for filename in league.get("files", []):
            path = args.root / league_id / filename
            raw = path.read_bytes()
            record = json.loads(raw)
            encoded = "gz:" + base64.b64encode(gzip.compress(raw, compresslevel=9)).decode()
            kv.set(f"intel:artifact:{league_id}:{record['team_id']}", encoded)
            published += 1
    kv.set("intel:artifact:manifest", json.dumps(manifest, separators=(",", ":")))
    print(f"[publish-intelligence] published {published} compressed team artifacts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
