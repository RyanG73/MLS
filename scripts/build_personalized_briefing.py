#!/usr/bin/env python3
"""Assemble deterministic user-specific briefings from team feature records."""
from __future__ import annotations

import argparse
import json

from server.intel_store import export_user_data
from server.intelligence_service import ArtifactNotFound, IntelligenceService
from server.kv_client import get_kv


def build_user_briefing(user_id: str) -> dict:
    user = export_user_data(get_kv(), user_id)
    if user is None:
        raise KeyError(user_id)
    service = IntelligenceService()
    teams = []
    for favorite in user.get("teams", []):
        try:
            record = service.get_team(favorite["league_id"], favorite["team_id"])
        except ArtifactNotFound:
            continue
        section = record["features"]["8"]["data"]
        if not section:
            continue
        teams.append({
            "league_id": record["league_id"], "team_id": record["team_id"],
            "team": record["team"], "calendar_mode": record["calendar_mode"],
            "materiality": max([
                event.get("materiality_score", 0)
                for event in (record["features"]["2"]["data"] or {}).get("events", [])
            ] or [0]),
            "briefing": section,
        })
    teams.sort(key=lambda row: -row["materiality"])
    modes = {row["calendar_mode"]["mode"] for row in teams}
    should_send = any(row["materiality"] > 0 for row in teams) or bool(
        modes & {"scheduled_break", "preseason"})
    return {
        "schema_version": 1, "user_id": user_id, "timezone": user.get("timezone", "UTC"),
        "teams": teams, "should_send": should_send,
        "skip_reason": None if should_send else "no material personalized content or phase report",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--user", required=True)
    args = parser.parse_args()
    print(json.dumps(build_user_briefing(args.user), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
