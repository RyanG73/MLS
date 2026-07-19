#!/usr/bin/env python3
"""Compile public-safe intelligence events into per-league browser payloads."""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.payload_utils import read_js_payload, write_js_payload  # noqa: E402

EVENTS_LATEST = Path("data/intelligence_events_latest.json")
PAYLOAD_DIR = Path("webapp/data")
OUT_DIR = PAYLOAD_DIR / "intel-events"
EXCLUDED = {
    "logos", "ledger", "power", "edge-board", "movers", "drift",
    "model-slices", "coefficients", "weekly", "race-deltas",
    "team-catalog", "search-index",
}


def build_payload(events_by_team_id: dict, standings: list[dict]) -> dict:
    """Return a display-name-keyed event payload for one competition."""
    teams: dict[str, list[dict]] = {}
    for standing in standings:
        team_id, name = standing.get("team_id"), standing.get("team")
        if not team_id or not name:
            continue
        teams[name] = events_by_team_id.get(team_id, [])
    return {
        "status": "ok" if teams else "empty",
        "generated": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "teams": teams,
    }


def _league_events(raw: dict) -> dict[str, dict]:
    if raw.get("schema_version") == 2 and isinstance(raw.get("leagues"), dict):
        return raw["leagues"]
    return {"mls": raw}


def main() -> int:
    raw = json.loads(EVENTS_LATEST.read_text()) if EVENTS_LATEST.exists() else {}
    by_league = _league_events(raw if isinstance(raw, dict) else {})
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    written = 0
    for path in sorted(PAYLOAD_DIR.glob("*.js")):
        if path.stem in EXCLUDED:
            continue
        league = read_js_payload(path)
        if not isinstance(league, dict) or not league.get("standings"):
            continue
        league_id = (league.get("league") or {}).get("id") or path.stem
        events = by_league.get(league_id) or {}
        if isinstance(events, dict) and "teams" in events:
            events = events["teams"]
        payload = build_payload(events, league["standings"])
        write_js_payload(OUT_DIR / f"{league_id}.js", "INTEL_EVENTS", payload)
        written += 1
    print(f"[intel-events-payload] wrote {written} league payloads to {OUT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
