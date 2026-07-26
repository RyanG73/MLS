#!/usr/bin/env python3
"""Cross-league power rankings → webapp/data/power.js.

The platform's unique cross-league capability: put teams from different leagues on
ONE comparable strength scale (domestic ELO + the league's cross-league offset, the
same strength the continental model uses).

Panels are still grouped by confederation for READABILITY, but as of 2026-07-26 the
scales do connect: coefficients.league_offset adds a whole-scale confederation shift
fitted on the FIFA Club World Cup — the only competition where confederations
actually meet — so a Liga MX side can now be read against a European one. See
scripts/eval/interconf_calibrate.py. The link rests on 60 matches, so cross-
confederation gaps are the least certain numbers on the page; within a confederation
nothing changed, because a constant added to every league in a group cancels in the
strength difference the match model consumes.

Aggregates the already-built per-league webapp/data/<id>.js files (each carries team
ELO + crest + colour), so it's cheap and always consistent with the live dashboards.
Run after the league builds.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from data_pipeline import coefficients as co
from scripts.payload_utils import write_js_payload

_DATA = Path("webapp/data")

# Which leagues form each confederation's comparable scale, with display names.
_GROUPS = {
    "UEFA": [("epl", "EPL"), ("la-liga", "La Liga"), ("serie-a", "Serie A"),
             ("bundesliga", "Bundesliga"), ("ligue-1", "Ligue 1"),
             # C1 leagues join as their payloads ship (missing payloads no-op).
             ("eredivisie", "Eredivisie"), ("primeira", "Primeira"),
             ("super-lig", "Süper Lig"), ("scottish-prem", "SPFL"),
             ("belgian-pro", "Pro League"), ("greek-super", "Super League GR")],
    "Concacaf": [("mls", "MLS"), ("liga-mx", "Liga MX")],
    # CONMEBOL, AFC and CAF join 2026-07-26. They were absent while their scales
    # had no link to UEFA's — a Brazilian club's number would have been an
    # uninterpretable 0.0-anchored figure sitting next to a European one. The
    # Club World Cup fit supplies that link, so they can be shown.
    "CONMEBOL": [("brazil-serie-a", "Brasileirão"), ("argentina-primera", "Liga Argentina"),
                 ("colombia-primera-a", "Primera A"), ("chile-primera", "Liga de Primera"),
                 ("uruguay-primera", "Primera Uruguay"), ("peru-liga1", "Liga 1"),
                 ("ecuador-ligapro", "LigaPro"), ("paraguay-primera", "División de Honor"),
                 ("bolivia-profesional", "División Profesional")],
    "AFC": [("japan-j1", "J1 League"), ("saudi-pro", "Saudi Pro League"),
            ("k-league-1", "K League 1"), ("china-super", "Chinese Super League"),
            ("australia-aleague", "A-League"), ("thai-league-1", "Thai League 1"),
            ("india-isl", "Indian Super League")],
    "CAF": [("south-africa-psl", "Betway Premiership")],
}

# Tier-2 European leagues (Championship, 2.Bundesliga, Serie B).
_TIER2_LEAGUES = [
    ("championship", "Championship"),
    ("bundesliga-2", "2. Bundesliga"),
    ("serie-b", "Serie B"),
]


def _load_standings(league_id: str):
    """Read a built league's standings rows (team, elo, logo, color)."""
    path = _DATA / f"{league_id}.js"
    if not path.exists():
        return []
    raw = path.read_text().split("=", 1)[1].rstrip(";\n")
    d = json.loads(raw)
    return d.get("standings", [])


def _rank_group(leagues, tier: int = 1) -> list[dict]:
    """One confederation's teams ranked by cross-league strength (ELO + offset)."""
    rows = []
    for lid, short in leagues:
        offset = co.tier2_offset(lid) if tier == 2 else co.league_offset(lid)
        for s in _load_standings(lid):
            elo = s.get("elo")
            if elo is None:
                continue
            rows.append({
                "team": s["team"], "league": lid, "league_short": short,
                "elo": int(round(elo)), "strength": round(float(elo) + offset, 1),
                "logo": s.get("logo"), "color": s.get("color"),
                "tier": tier,
            })
    rows.sort(key=lambda r: -r["strength"])
    for i, r in enumerate(rows, 1):
        r["rank"] = i
    return rows


def build():
    data = {"status": "live",  # rankings page is always-on (route state taxonomy)
            "groups": [],
            "generated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")}
    for conf, leagues in _GROUPS.items():
        ranked = _rank_group(leagues)
        if not ranked:
            continue
        data["groups"].append({
            "confederation": conf,
            # One global anchor now that the confederation shift links the
            # scales; the old per-confederation label ("MLS = 0") was already
            # wrong for CONMEBOL/AFC/CAF the moment they were added.
            "anchor": "EPL = 0",
            "n_leagues": len({r["league"] for r in ranked}),
            "teams": ranked,
        })
    # Tier-2 UEFA group (Championship, 2.Bundesliga, Serie B) — on the EPL=0 scale.
    ranked_t2 = _rank_group(_TIER2_LEAGUES, tier=2)
    if ranked_t2:
        data["groups"].append({
            "confederation": "UEFA Tier 2",
            "anchor": "EPL = 0",
            "n_leagues": len({r["league"] for r in ranked_t2}),
            "teams": ranked_t2,
        })
    out = _DATA / "power.js"
    write_js_payload(out, "POWER_DATA", data)
    for g in data["groups"]:
        top = g["teams"][0]
        print(f"[power] {g['confederation']}: {len(g['teams'])} teams "
              f"({g['n_leagues']} leagues) · #1 {top['team']} (str {top['strength']})")
    print(f"[power] wrote {out} ({out.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    build()
