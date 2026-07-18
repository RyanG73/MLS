#!/usr/bin/env python3
"""Cross-league match calendar → webapp/data/calendar.js (window.CALENDAR_DATA).

Powers the Matches tab's day-by-day browser (2026-07-13 feedback: "a calendar
for matches, so you can scroll across the top by day or ... select a day on
an actual calendar box"). Deliberately separate from build_edge_board.py's
`priced`/`no_line` feed — that one is a narrow 48h betting-edge window by
design; this one is every match, uncapped, across a wide date range, so every
day box on the calendar has something to show.

Read-only over the already-built per-league files. Run after the per-league
builds (append to build_all.sh / daily_build.sh).
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from scripts.payload_utils import write_js_payload

DATA = Path("webapp/data")
DAYS_BACK = 3
DAYS_FWD = 21


def _load(path: Path) -> dict | None:
    try:
        txt = path.read_text()
        return json.loads(txt[txt.index("{"): txt.rindex("}") + 1])
    except Exception:
        return None


def _live_league_files() -> list[tuple[str, dict]]:
    try:
        t = (DATA.parent / "leagues.js").read_text()
        registry = json.loads(t[t.index("["): t.rindex("]") + 1])
    except Exception:
        registry = []
    out = []
    for r in registry:
        if r.get("status") != "live":
            continue
        d = _load(DATA / f"{r['id']}.js")
        if not d or d.get("status") == "placeholder":
            continue
        if (d.get("outlook") or {}).get("mode") == "knockout":
            continue
        out.append((r["id"], d))
    return out


def build_calendar(files: list[tuple[str, dict]]) -> dict:
    lo = (date.today() - timedelta(days=DAYS_BACK)).isoformat()
    hi = (date.today() + timedelta(days=DAYS_FWD)).isoformat()
    by_date: dict[str, list[dict]] = {}
    for lid, d in files:
        name = (d.get("league") or {}).get("name", lid)
        for g in d.get("games", []):
            gd = g.get("date") or ""
            if not (lo <= gd <= hi):
                continue
            by_date.setdefault(gd, []).append({
                "league": lid, "name": name,
                "home": g.get("home"), "away": g.get("away"),
                "hlogo": g.get("hlogo"), "alogo": g.get("alogo"),
                "hg": g.get("hg"), "ag": g.get("ag"), "result": g.get("result"),
                "pH": g.get("pH"), "pD": g.get("pD"), "pA": g.get("pA"),
                # PL-style fixture rows on the redesigned Matches page
                # (2026-07-17): kickoff time as the center axis, team-colored
                # probability bar, likely-scoreline expansion.
                "ko": g.get("ko"),
                "hcolor": g.get("hcolor"), "acolor": g.get("acolor"),
                "lam": g.get("lam"), "mu": g.get("mu"),
            })
    for rows in by_date.values():
        rows.sort(key=lambda g: (g["name"], g["home"]))
    return {"days": by_date, "dates": sorted(by_date.keys()),
            "today": date.today().isoformat()}


def main() -> None:
    files = _live_league_files()
    payload = build_calendar(files)
    payload["generated"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    write_js_payload(DATA / "calendar.js", "CALENDAR_DATA", payload)
    n_matches = sum(len(v) for v in payload["days"].values())
    print(f"[calendar] {len(payload['dates'])} days · {n_matches} matches → webapp/data/calendar.js")


if __name__ == "__main__":
    main()
