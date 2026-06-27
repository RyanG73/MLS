#!/usr/bin/env python3
"""
Scrape ESPN per-match matchday rosters (who was AVAILABLE/active each game) for MLS,
2022-2024. Free hidden API, no key. Caches to data/espn_rosters.csv (resumable).

Powers the Phase 9 availability-weighted g+ feature: a player `active` in a match's
ESPN roster was available; ASA holds the season g+/xG quality, joined by player name.

Endpoints:
  scoreboard?dates=YYYYMMDD-YYYYMMDD  -> all event ids for a season (one call)
  summary?event={id}                 -> per-team rosters (active/starter/sub flags)

Usage:  python data_pipeline/espn_rosters.py [--seasons 2022 2023 2024]
Resumable: re-running skips event_ids already in the CSV.
"""

import argparse
import csv
import os
import time
import sys

from data_pipeline.http import espn_get

_BASE = "https://site.api.espn.com/apis/site/v2/sports/soccer/usa.1"
_OUT = os.path.join(os.path.dirname(__file__), "..", "data", "espn_rosters.csv")
_OUT = os.path.abspath(_OUT)
_FIELDS = [
    "season", "event_id", "date", "team_abbr", "team_name", "is_home",
    "player_name", "active", "starter", "subbed_in", "subbed_out",
]
# MLS season windows (regular season + playoffs). 2020 excluded (COVID; model drops it).
_WINDOWS = {
    2017: ("20170301", "20171215"),
    2018: ("20180301", "20181215"),
    2019: ("20190301", "20191115"),
    2021: ("20210401", "20211215"),
    2022: ("20220225", "20221105"),
    2023: ("20230225", "20231210"),
    2024: ("20240221", "20241210"),
}


def _get(path, params, tries=3):
    for i in range(tries):
        try:
            return espn_get(f"{_BASE}/{path}", params, timeout=25)
        except Exception as e:
            if i == tries - 1:
                print(f"  [warn] {path} {params} failed: {e}", file=sys.stderr)
        time.sleep(0.6 * (i + 1))
    return {}


def event_ids_for_season(season: int) -> list[tuple[str, str]]:
    """Return [(event_id, iso_date), ...] for a season via one scoreboard range call."""
    start, end = _WINDOWS[season]
    sb = _get("scoreboard", {"dates": f"{start}-{end}", "limit": 1000})
    out = []
    for e in sb.get("events", []):
        out.append((str(e["id"]), e.get("date", "")[:10]))
    return out


def rosters_for_event(event_id: str) -> list[dict]:
    """Extract per-active-player rows from a match summary. [] if unavailable."""
    sm = _get("summary", {"event": event_id})
    rosters = sm.get("rosters") or []
    rows = []
    for tm in rosters:
        team = tm.get("team", {})
        is_home = 1 if tm.get("homeAway") == "home" else 0
        for p in tm.get("roster", []):
            if not p.get("active"):
                continue
            ath = p.get("athlete", {})
            rows.append({
                "team_abbr": team.get("abbreviation", ""),
                "team_name": team.get("displayName", ""),
                "is_home": is_home,
                "player_name": ath.get("displayName", ""),
                "active": 1,
                "starter": 1 if p.get("starter") else 0,
                "subbed_in": 1 if p.get("subbedIn") else 0,
                "subbed_out": 1 if p.get("subbedOut") else 0,
            })
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seasons", nargs="+", type=int, default=[2022, 2023, 2024])
    args = ap.parse_args()

    os.makedirs(os.path.dirname(_OUT), exist_ok=True)
    done = set()
    if os.path.exists(_OUT):
        with open(_OUT) as f:
            for row in csv.DictReader(f):
                done.add(row["event_id"])
        print(f"Resuming: {len(done)} events already cached.")

    new_file = not os.path.exists(_OUT)
    fh = open(_OUT, "a", newline="")
    w = csv.DictWriter(fh, fieldnames=_FIELDS)
    if new_file:
        w.writeheader()

    total_events = total_rows = 0
    for season in args.seasons:
        events = event_ids_for_season(season)
        print(f"{season}: {len(events)} events from scoreboard")
        for eid, date in events:
            if eid in done:
                continue
            rows = rosters_for_event(eid)
            for r in rows:
                r.update({"season": season, "event_id": eid, "date": date})
                w.writerow(r)
            total_events += 1
            total_rows += len(rows)
            if total_events % 50 == 0:
                fh.flush()
                print(f"  ...{total_events} events, {total_rows} player-rows")
            time.sleep(0.2)
    fh.close()
    print(f"Done. {total_events} new events, {total_rows} player-rows -> {_OUT}")


if __name__ == "__main__":
    main()
