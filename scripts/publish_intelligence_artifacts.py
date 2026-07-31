#!/usr/bin/env python3
"""Publish compiled private intelligence artifacts to authenticated Upstash KV."""
from __future__ import annotations

import argparse
import base64
import gzip
import json
import os
import sys
import time
from pathlib import Path

import requests

from server.upstash_kv import UpstashKVStore

DEFAULT_BATCH_SIZE = 12


def _publish_via_api(endpoint: str, token: str, records: list[dict]) -> None:
    for start in range(0, len(records), DEFAULT_BATCH_SIZE):
        batch = records[start:start + DEFAULT_BATCH_SIZE]
        last_error = None
        for attempt in range(3):
            try:
                response = requests.post(
                    endpoint,
                    headers={
                        "Content-Type": "application/json",
                        "X-Intelligence-Publish-Token": token,
                    },
                    json={"records": batch},
                    timeout=30,
                )
                response.raise_for_status()
                result = response.json()
                if result.get("published") != len(batch):
                    raise RuntimeError("artifact relay returned an incomplete batch count")
                break
            except (requests.RequestException, RuntimeError) as exc:
                last_error = exc
                if attempt < 2:
                    time.sleep(2 ** attempt)
        else:
            raise RuntimeError("artifact relay failed after three attempts") from last_error


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("data/team_intelligence"))
    parser.add_argument("--allow-missing-config", action="store_true")
    parser.add_argument("--endpoint", help="authenticated API relay URL")
    args = parser.parse_args()
    url = os.environ.get("UPSTASH_REDIS_REST_URL")
    token = os.environ.get("UPSTASH_REDIS_REST_TOKEN")
    relay_token = os.environ.get("INTELLIGENCE_PUBLISH_TOKEN")
    if args.endpoint and not relay_token:
        message = "[publish-intelligence] relay token unavailable"
        if args.allow_missing_config:
            print(message + "; skipped")
            return 0
        print(message, file=sys.stderr)
        return 2
    if not args.endpoint and (not url or not token):
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
    manifest = json.loads(manifest_path.read_text())
    records = []
    for league_id, league in manifest["leagues"].items():
        if league.get("status") != "ok":
            continue
        for filename in league.get("files", []):
            path = args.root / league_id / filename
            raw = path.read_bytes()
            record = json.loads(raw)
            encoded = "gz:" + base64.b64encode(gzip.compress(raw, compresslevel=9)).decode()
            records.append({
                "key": f"intel:artifact:{league_id}:{record['team_id']}",
                "value": encoded,
            })
    manifest_record = {
        "key": "intel:artifact:manifest",
        "value": json.dumps(manifest, separators=(",", ":")),
    }
    if args.endpoint:
        # Publish the manifest last so readers never see a new manifest before
        # every team record it describes is available.
        _publish_via_api(args.endpoint, relay_token, records)
        _publish_via_api(args.endpoint, relay_token, [manifest_record])
    else:
        kv = UpstashKVStore(url, token, timeout=15)
        for record in records:
            kv.set(record["key"], record["value"])
        kv.set(manifest_record["key"], manifest_record["value"])
    published = len(records)
    print(f"[publish-intelligence] published {published} compressed team artifacts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
