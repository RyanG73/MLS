#!/usr/bin/env python3
"""Build the public-safe league/team identity catalog used by account setup."""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from scripts.payload_utils import canonical_team_id, read_js_payload, write_js_payload

OUT = Path("webapp/data/team-catalog.js")
MANIFEST = Path("data/team_intelligence/manifest.json")


def build_catalog(manifest_path: Path = MANIFEST) -> dict:
    manifest = json.loads(manifest_path.read_text())
    supported = {
        league_id for league_id, entry in manifest.get("leagues", {}).items()
        if entry.get("status") == "ok"
    }
    leagues = []
    for path in sorted(Path("webapp/data").glob("*.js")):
        payload = read_js_payload(path)
        if not isinstance(payload, dict) or not payload.get("standings"):
            continue
        league = payload.get("league") or {}
        league_id = league.get("id") or path.stem
        if league_id not in supported:
            continue
        teams = [{
            "team_id": canonical_team_id(row["team"], row.get("team_id")),
            "team": row["team"],
            "logo": row.get("logo"),
        } for row in payload["standings"] if row.get("team")]
        teams.sort(key=lambda row: row["team"])
        leagues.append({
            "league_id": league_id,
            "league": league.get("name", league_id),
            "status": payload.get("status"),
            "data_status": payload.get("data_status"),
            "teams": teams,
        })
    return {
        "schema_version": 1,
        "generated": dt.datetime.now(dt.timezone.utc).isoformat(),
        "leagues": leagues,
    }


def main() -> int:
    catalog = build_catalog()
    write_js_payload(OUT, "TEAM_CATALOG", catalog)
    print(f"[team-catalog] {len(catalog['leagues'])} leagues -> {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
