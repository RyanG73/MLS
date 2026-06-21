#!/usr/bin/env python3
"""
Multi-league scaffolding fetch — pulls teams + crest logos (teams endpoint) and
the league logo (scoreboard endpoint) from ESPN's public soccer API for every
league on the platform, then writes:

  webapp/leagues.js          — the league registry (window.LEAGUES = [...])
  webapp/data/<id>.js        — a "coming soon" stub (window.LEAGUE_DATA = {...})
                                for every non-live league (teams + logos only)

MLS is `live`: its full data file (webapp/data/mls.js) is produced by
build_dashboard_data.py, so this script only records MLS's registry entry +
league logo and does NOT overwrite mls.js.

Run once to scaffold, re-run to refresh team lists (they change rarely).
Usage: python scripts/fetch_league_teams.py
"""
import json
from datetime import datetime, timezone
from pathlib import Path

import requests
import urllib3

urllib3.disable_warnings()

_ESPN = "https://site.api.espn.com/apis/site/v2/sports/soccer"
_HDR = {"User-Agent": "Mozilla/5.0"}

# (id, display name, ESPN slug | None, confederation, status)
# espn_code None → menu entry only (no ESPN team data available under a clean code yet).
REGISTRY = [
    # Concacaf
    ("mls",                 "Major League Soccer",      "usa.1",            "Concacaf", "live"),
    ("liga-mx",             "Liga MX",                  "mex.1",            "Concacaf", "live"),
    ("canadian-pl",         "Canadian Premier League",  None,               "Concacaf", "soon"),
    ("leagues-cup",         "Leagues Cup",              "concacaf.leagues.cup","Concacaf", "live"),
    ("concacaf-champions",  "Concacaf Champions Cup",   "concacaf.champions","Concacaf", "live"),
    # Concacaf League removed 2026-06-17 — discontinued after 2023 (absorbed into the Champions Cup).
    # UEFA
    ("epl",                 "English Premier League",   "eng.1",            "UEFA", "live"),
    ("championship",        "EFL Championship",         "eng.2",            "UEFA", "live"),
    ("league-one",          "EFL League One",           "eng.3",            "UEFA", "live"),
    ("league-two",          "EFL League Two",           "eng.4",            "UEFA", "live"),
    ("bundesliga",          "Bundesliga",               "ger.1",            "UEFA", "live"),
    ("bundesliga-2",        "2. Bundesliga",            "ger.2",            "UEFA", "live"),
    ("ligue-1",             "Ligue 1",                  "fra.1",            "UEFA", "live"),
    ("la-liga",             "La Liga",                  "esp.1",            "UEFA", "live"),
    ("serie-a",             "Serie A",                  "ita.1",            "UEFA", "live"),
    ("serie-b",             "Serie B",                  "ita.2",            "UEFA", "live"),
    ("ucl",                 "UEFA Champions League",    "uefa.champions",   "UEFA", "live"),
    ("europa",              "UEFA Europa League",       "uefa.europa",      "UEFA", "live"),
    ("conference",          "UEFA Conference League",   "uefa.europa.conf", "UEFA", "live"),
]


def _get(url):
    return requests.get(url, headers=_HDR, verify=False, timeout=25).json()


def _league_logo(code):
    try:
        L = _get(f"{_ESPN}/{code}/scoreboard").get("leagues", [{}])[0]
        return (L.get("logos") or [{}])[0].get("href")
    except Exception:
        return None


def _teams(code):
    try:
        ts = _get(f"{_ESPN}/{code}/teams")["sports"][0]["leagues"][0]["teams"]
        out = []
        for it in ts:
            t = it["team"]
            out.append({"name": t.get("displayName"),
                        "logo": (t.get("logos") or [{}])[0].get("href"),
                        "color": "#" + (t.get("color") or "8a93a6")})
        return sorted(out, key=lambda x: x["name"] or "")
    except Exception as e:
        print(f"    [warn] teams fetch failed for {code}: {e}")
        return []


def main():
    out_dir = Path("webapp/data")
    out_dir.mkdir(parents=True, exist_ok=True)
    registry = []
    for lid, name, code, conf, status in REGISTRY:
        logo = _league_logo(code) if code else None
        registry.append({"id": lid, "name": name, "confederation": conf,
                         "status": status, "logo": logo, "espn_code": code})
        if status == "live":
            print(f"  {lid:18s} live   · logo {'ok' if logo else 'none'} (data built separately: MLS→build_dashboard_data, others→build_league_data)")
            continue
        teams = _teams(code) if code else []
        stub = {
            "status": "placeholder",
            "generated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
            "league": {"id": lid, "name": name, "logo": logo,
                       "confederation": conf, "status": "soon"},
            "teams": teams,
        }
        (out_dir / f"{lid}.js").write_text(
            "window.LEAGUE_DATA = " + json.dumps(stub, separators=(",", ":")) + ";\n")
        print(f"  {lid:18s} soon   · {len(teams):3d} teams · logo {'ok' if logo else 'none'}")

    Path("webapp/leagues.js").write_text(
        "window.LEAGUES = " + json.dumps(registry, separators=(",", ":")) + ";\n")
    print(f"\nWrote webapp/leagues.js ({len(registry)} leagues) + "
          f"{sum(1 for r in registry if r['status']=='soon')} coming-soon stubs.")


if __name__ == "__main__":
    main()
