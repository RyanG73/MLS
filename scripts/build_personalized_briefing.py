#!/usr/bin/env python3
"""Assemble deterministic user-specific briefings from team feature records."""
from __future__ import annotations

import argparse
import datetime as dt
import json
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from server.intel_store import export_user_data
from server.intelligence_service import ArtifactNotFound, IntelligenceService
from server.kv_client import get_kv


def _local_now(timezone_name: str, now: dt.datetime | None = None) -> dt.datetime:
    current = now or dt.datetime.now(dt.timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=dt.timezone.utc)
    try:
        zone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        zone = dt.timezone.utc
    return current.astimezone(zone)


def _local_fixture_date(stake: dict, local_now: dt.datetime) -> str | None:
    """Return the fixture's calendar date in the subscriber's timezone."""
    kickoff = stake.get("ko")
    if kickoff:
        try:
            parsed = dt.datetime.fromisoformat(
                str(kickoff).replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=dt.timezone.utc)
            return parsed.astimezone(local_now.tzinfo).date().isoformat()
        except (TypeError, ValueError):
            pass
    return stake.get("delivery_date") or stake.get("date")


def build_user_briefing(user_id: str, now: dt.datetime | None = None) -> dict:
    user = export_user_data(get_kv(), user_id)
    if user is None:
        raise KeyError(user_id)
    timezone_name = user.get("timezone", "UTC")
    local_now = _local_now(timezone_name, now)
    local_date = local_now.date().isoformat()
    local_morning = 6 <= local_now.hour < 11
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
    for row in teams:
        stake = row["briefing"]["sections"].get("prematch_stakes")
        if stake:
            stake["delivery_date"] = _local_fixture_date(stake, local_now)
    modes = {row["calendar_mode"]["mode"] for row in teams}
    due_stakes = [
        row["briefing"]["sections"]["prematch_stakes"]
        for row in teams
        if (row["briefing"]["sections"].get("prematch_stakes") or {}).get(
            "delivery_date") == local_date
    ]
    has_content = (
        any(row["materiality"] > 0 for row in teams)
        or bool(modes & {"scheduled_break", "preseason"})
        or bool(due_stakes)
    )
    should_send = local_morning and has_content
    if not local_morning:
        skip_reason = "outside local morning delivery window"
    elif not has_content:
        skip_reason = "no material personalized content, phase report, or matchday stake"
    else:
        skip_reason = None
    return {
        "schema_version": 2, "user_id": user_id, "timezone": timezone_name,
        "local_date": local_date, "local_hour": local_now.hour,
        "prematch_due": bool(due_stakes),
        "due_fixture_ids": sorted({
            stake["fixture_id"] for stake in due_stakes if stake.get("fixture_id")
        }),
        "teams": teams, "should_send": should_send,
        "skip_reason": skip_reason,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--user", required=True)
    args = parser.parse_args()
    print(json.dumps(build_user_briefing(args.user), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
