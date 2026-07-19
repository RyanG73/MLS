#!/usr/bin/env python3
"""S6: expose S4's committed, public intelligence events to the webapp as a
lazy-loaded file (docs/intelligence-hub-implementation-instructions.md §5 S6:
"Replace panels one at a time and display a sample, live, thin history, or
unavailable state.")

Reads data/intelligence_events_latest.json (S4 — team_id-keyed) and
webapp/data/mls.js (for the team_id -> display-name mapping) and writes
webapp/data/intel-events/mls.js, keyed by team NAME for direct lookup
against FavStore's pinned-team display name — the Intel page doesn't load
the full per-league payload for the pinned team's league, so resolving
identity client-side would otherwise need a second fetch.

MLS pilot only, matching the established pattern — data/intelligence_events_latest.json
currently only has MLS rows (S4 is MLS-only).

Usage:
    python scripts/build_intel_events_payload.py
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.payload_utils import read_js_payload, write_js_payload  # noqa: E402

EVENTS_LATEST = Path("data/intelligence_events_latest.json")
MLS_PAYLOAD = Path("webapp/data/mls.js")
OUT = Path("webapp/data/intel-events/mls.js")


def build_payload(events_by_team_id: dict, standings: list[dict]) -> dict:
    """{status, generated, teams: {team_name: [events...]}} — events carried
    through unchanged except re-keyed by display name instead of team_id."""
    id_to_name = {s["team_id"]: s["team"] for s in standings if s.get("team_id")}
    teams: dict[str, list[dict]] = {}
    for team_id, events in events_by_team_id.items():
        name = id_to_name.get(team_id)
        if name is None:
            continue  # no live standings row for this team_id anymore
        teams[name] = events
    return {
        "status": "ok" if teams else "empty",
        "generated": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "teams": teams,
    }


def main() -> int:
    events_by_team_id = json.loads(EVENTS_LATEST.read_text()) if EVENTS_LATEST.exists() else {}
    mls = read_js_payload(MLS_PAYLOAD)
    standings = (mls or {}).get("standings") or []
    payload = build_payload(events_by_team_id, standings)
    write_js_payload(OUT, "INTEL_EVENTS", payload)
    print(f"[intel-events-payload] {payload['status']} · {len(payload['teams'])} teams → {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
