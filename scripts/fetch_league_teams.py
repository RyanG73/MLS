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

# (id, display name, ESPN slug | None, confederation, status, group)
# espn_code None → menu entry only (no ESPN team data available under a clean code yet).
# `group` drives the sidebar's collapsible country/region sections (B13); confederation
# stays for the Power Rankings cross-league grouping, which is coarser by design.
# Presentation metadata for the masthead dropdowns / leagues index (2026-07-11
# feedback: "clear what country the league plays in and what division level").
# tier=None → cup / continental competition. Keyed by REGISTRY league id.
LEAGUE_INFO = {
    "mls": ("United States", 1), "liga-mx": ("Mexico", 1), "canadian-pl": ("Canada", 1),
    "nwsl": ("United States", 1), "usl-championship": ("United States", 2),
    "leagues-cup": ("North America", None), "concacaf-champions": ("North America", None),
    "epl": ("England", 1), "championship": ("England", 2), "league-one": ("England", 3),
    "league-two": ("England", 4), "national-league": ("England", 5),
    "bundesliga": ("Germany", 1), "bundesliga-2": ("Germany", 2),
    "ligue-1": ("France", 1), "ligue-2": ("France", 2),
    "la-liga": ("Spain", 1), "segunda": ("Spain", 2),
    "serie-a": ("Italy", 1), "serie-b": ("Italy", 2),
    "eredivisie": ("Netherlands", 1), "primeira": ("Portugal", 1), "super-lig": ("Turkey", 1),
    "scottish-prem": ("Scotland", 1), "scottish-champ": ("Scotland", 2),
    "scottish-league-one": ("Scotland", 3), "scottish-league-two": ("Scotland", 4),
    "austria-bundesliga": ("Austria", 1), "swiss-super-league": ("Switzerland", 1),
    "romania-liga1": ("Romania", 1), "ireland-premier": ("Ireland", 1),
    "russia-premier": ("Russia", 1), "china-super": ("China", 1),
    "saudi-pro": ("Saudi Arabia", 1), "australia-aleague": ("Australia", 1),
    "wsl": ("England", 1), "belgian-pro": ("Belgium", 1), "greek-super": ("Greece", 1),
    "sweden-allsvenskan": ("Sweden", 1), "norway-eliteserien": ("Norway", 1),
    "denmark-superliga": ("Denmark", 1), "poland-ekstraklasa": ("Poland", 1),
    "finland-veikkausliiga": ("Finland", 1),
    "brazil-serie-a": ("Brazil", 1), "argentina-primera": ("Argentina", 1),
    "japan-j1": ("Japan", 1),
    # Round 5 (2026-07-14)
    "chile-primera": ("Chile", 1), "colombia-primera-a": ("Colombia", 1),
    "uruguay-primera": ("Uruguay", 1), "peru-liga1": ("Peru", 1),
    "thai-league-1": ("Thailand", 1), "k-league-1": ("South Korea", 1),
    "eerste-divisie": ("Netherlands", 2),
    "ucl": ("Europe", None), "europa": ("Europe", None), "conference": ("Europe", None),
}

REGISTRY = [
    # Concacaf / Americas
    ("mls",                 "MLS",                      "usa.1",            "Concacaf", "live", "Americas"),
    ("liga-mx",             "Liga MX",                  "mex.1",            "Concacaf", "live", "Americas"),
    ("canadian-pl",         "Canadian Premier League",  None,               "Concacaf", "live", "Americas"),
    # C2 (ASA track): flip to "live" when their dashboard builders ship;
    # eval gating is per-family (experiments/champion_nwsl.json / champion_usl.json).
    ("nwsl",                "NWSL",                     "usa.nwsl",         "Concacaf", "live", "Americas"),
    ("usl-championship",    "USL Championship",         "usa.usl.1",        "Concacaf", "live", "Americas"),
    ("leagues-cup",         "Leagues Cup",              "concacaf.leagues.cup","Concacaf", "live", "Cups"),
    ("concacaf-champions",  "Concacaf Champions Cup",   "concacaf.champions","Concacaf", "live", "Cups"),
    # Concacaf League removed 2026-06-17 — discontinued after 2023 (absorbed into the Champions Cup).
    # UEFA — England
    ("epl",                 "Premier League",           "eng.1",            "UEFA", "live", "England"),
    ("championship",        "EFL Championship",         "eng.2",            "UEFA", "live", "England"),
    ("league-one",          "EFL League One",           "eng.3",            "UEFA", "live", "England"),
    ("league-two",          "EFL League Two",           "eng.4",            "UEFA", "live", "England"),
    ("national-league",     "National League",          "eng.5",            "UEFA", "live", "England"),
    # UEFA — Germany
    ("bundesliga",          "Bundesliga",               "ger.1",            "UEFA", "live", "Germany"),
    ("bundesliga-2",        "2. Bundesliga",            "ger.2",            "UEFA", "live", "Germany"),
    # UEFA — France
    ("ligue-1",             "Ligue 1",                  "fra.1",            "UEFA", "live", "France"),
    ("ligue-2",             "Ligue 2",                  "fra.2",            "UEFA", "live", "France"),
    # UEFA — Spain
    ("la-liga",             "La Liga",                  "esp.1",            "UEFA", "live", "Spain"),
    ("segunda",             "LaLiga 2",                 "esp.2",            "UEFA", "live", "Spain"),
    # UEFA — Italy
    ("serie-a",             "Serie A",                  "ita.1",            "UEFA", "live", "Italy"),
    ("serie-b",             "Serie B",                  "ita.2",            "UEFA", "live", "Italy"),
    # UEFA — Other Europe (C1 batch; flip each to "live" as its build ships)
    ("eredivisie",          "Eredivisie",               "ned.1",            "UEFA", "live", "Other Europe"),
    ("primeira",            "Primeira Liga",            "por.1",            "UEFA", "live", "Other Europe"),
    ("super-lig",           "Süper Lig",                "tur.1",            "UEFA", "live", "Other Europe"),
    ("scottish-prem",       "Scottish Premiership",     "sco.1",            "UEFA", "live", "Other Europe"),
    ("scottish-champ",      "Scottish Championship",    "sco.2",            "UEFA", "live", "Other Europe"),
    ("scottish-league-one", "Scottish League One",      "sco.3",            "UEFA", "live", "Other Europe"),
    ("scottish-league-two", "Scottish League Two",      "sco.4",            "UEFA", "live", "Other Europe"),
    ("austria-bundesliga",  "Austrian Bundesliga",      "aut.1",            "UEFA", "live", "Other Europe"),
    ("swiss-super-league",  "Swiss Super League",       "sui.1",            "UEFA", "live", "Other Europe"),
    ("romania-liga1",       "Liga I (Romania)",         "rou.1",            "UEFA", "live", "Other Europe"),
    ("ireland-premier",     "League of Ireland Premier","irl.1",            "UEFA", "live", "Other Europe"),
    # Round-4 projection-only (footballdata_intl odds backbone + ESPN fixtures)
    ("russia-premier",      "Russian Premier League",   "rus.1",            "UEFA", "live", "Other Europe"),
    ("china-super",         "Chinese Super League",     "chn.1",            "AFC",  "live", "Asia"),
    ("saudi-pro",           "Saudi Pro League",         "ksa.1",            "AFC",  "live", "Asia"),
    ("australia-aleague",   "A-League Men",             "aus.1",            "AFC",  "live", "Asia"),
    ("wsl",                 "Women's Super League",     "eng.w.1",          "UEFA", "live", "England"),
    ("belgian-pro",         "Belgian Pro League",       "bel.1",            "UEFA", "live", "Other Europe"),
    ("greek-super",         "Greek Super League",       "gre.1",            "UEFA", "live", "Other Europe"),
    # UEFA — Nordics + Poland (Tier-1 expansion, 2026-07-10)
    ("sweden-allsvenskan",  "Allsvenskan",               "swe.1",            "UEFA", "live", "Other Europe"),
    ("norway-eliteserien",  "Eliteserien",               "nor.1",            "UEFA", "live", "Other Europe"),
    ("denmark-superliga",   "Superliga",                 "den.1",            "UEFA", "live", "Other Europe"),
    # No confirmed ESPN slug (results-only league — see football_data_intl.NO_ESPN_SCHEDULE)
    ("poland-ekstraklasa",  "Ekstraklasa",               None,               "UEFA", "live", "Other Europe"),
    # No ESPN slug → results-only (like Poland). football-data results+odds are
    # current; API-Football free plan can't serve 2026 fixtures (round-4 Phase 3).
    ("finland-veikkausliiga","Veikkausliiga",            None,               "UEFA", "live", "Other Europe"),
    # CONMEBOL — South America (Tier-1 expansion, 2026-07-10)
    ("brazil-serie-a",      "Brasileirão Série A",       "bra.1",            "CONMEBOL", "live", "South America"),
    ("argentina-primera",   "Liga Profesional Argentina", "arg.1",           "CONMEBOL", "live", "South America"),
    # AFC — Asia (Tier-1 expansion, 2026-07-10)
    ("japan-j1",            "J1 League",                 "jpn.1",            "AFC", "live", "Asia"),
    # Round 5 (2026-07-14): South America + more Asia + Eerste Divisie
    # (docs/league-expansion-report.md). ESPN slugs verified live.
    ("chile-primera",       "Liga de Primera",           "chi.1",            "CONMEBOL", "live", "South America"),
    ("colombia-primera-a",  "Categoría Primera A",       "col.1",            "CONMEBOL", "live", "South America"),
    ("uruguay-primera",     "Primera División",          "uru.1",            "CONMEBOL", "live", "South America"),
    ("peru-liga1",          "Liga 1",                    "per.1",            "CONMEBOL", "live", "South America"),
    ("thai-league-1",       "Thai League 1",             "tha.1",            "AFC", "live", "Asia"),
    ("eerste-divisie",      "Eerste Divisie",            "ned.2",            "UEFA", "live", "Other Europe"),
    # No confirmed ESPN slug (kor.1/kor.k1/k.league.1 all return 0 teams) —
    # results-only via API-Football, same as canadian-pl above.
    ("k-league-1",          "K League 1",                None,               "AFC", "live", "Asia"),
    # UEFA — continental cups
    ("ucl",                 "UEFA Champions League",    "uefa.champions",   "UEFA", "live", "Cups"),
    ("europa",              "UEFA Europa League",       "uefa.europa",      "UEFA", "live", "Cups"),
    ("conference",          "UEFA Conference League",   "uefa.europa.conf", "UEFA", "live", "Cups"),
]


# Data-status contract (launch plan 2026-08-17 B1): what each league's data can
# honestly support. Everything defaults to "full_forecast"; list only the
# exceptions. Keep in sync with the payload-side derivation in
# build_league_data.py — validate_payloads.py fails when a payload and this
# registry disagree.
#   results_only — current-season results but no forward-fixture feed
#   historical   — newest available season is in the past (stale source)
DATA_STATUS = {
    "canadian-pl": "historical",             # API-Football free plan: newest season 2024
    "k-league-1": "historical",              # API-Football free plan: 2022–2024 only
    "poland-ekstraklasa": "results_only",    # no ESPN slug — no forward fixtures
    "finland-veikkausliiga": "results_only",  # no ESPN slug — no forward fixtures
}


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
    for lid, name, code, conf, status, group in REGISTRY:
        logo = _league_logo(code) if code else None
        country, tier = LEAGUE_INFO.get(lid, (None, None))
        registry.append({"id": lid, "name": name, "confederation": conf, "group": group,
                         "status": status, "logo": logo, "espn_code": code,
                         "country": country, "tier": tier,
                         "data_status": DATA_STATUS.get(lid, "full_forecast")})
        if status == "live":
            print(f"  {lid:18s} live   · logo {'ok' if logo else 'none'} (data built separately: MLS→build_dashboard_data, others→build_league_data)")
            continue
        teams = _teams(code) if code else []
        # Explicit placeholder reason (see docs/CURRENT_STATE.md § Route State Taxonomy
        # and codex suggestions Net-New #11): say *why* there are no projections so the
        # webapp can render a real empty state instead of implying a broken model.
        reason = ("Projection model not built for this league yet — team list shown for reference."
                  if teams else
                  "Projection model and fixture source not yet wired for this league.")
        stub = {
            "status": "placeholder",
            "reason": reason,
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
