#!/usr/bin/env python3
"""Cross-league power rankings → webapp/data/power.js.

The platform's unique cross-league capability: put teams from different leagues on
ONE comparable strength scale (domestic ELO + the league's cross-league offset, the
same strength the continental model uses). Rankings are CONFEDERATION-RELATIVE — UEFA
anchors to EPL=0, Concacaf to MLS=0, and the two scales don't connect (the
confederations don't meet in our data), so they're shown as two separate panels.

Aggregates the already-built per-league webapp/data/<id>.js files (each carries team
ELO + crest + colour), so it's cheap and always consistent with the live dashboards.
Run after the league builds.
"""
from __future__ import annotations

import json
from pathlib import Path

from data_pipeline import coefficients as co

_DATA = Path("webapp/data")

# Which leagues form each confederation's comparable scale, with display names.
_GROUPS = {
    "UEFA": [("epl", "EPL"), ("la-liga", "La Liga"), ("serie-a", "Serie A"),
             ("bundesliga", "Bundesliga"), ("ligue-1", "Ligue 1")],
    "Concacaf": [("mls", "MLS"), ("liga-mx", "Liga MX")],
}


def _load_standings(league_id: str):
    """Read a built league's standings rows (team, elo, logo, color)."""
    path = _DATA / f"{league_id}.js"
    if not path.exists():
        return []
    raw = path.read_text().split("=", 1)[1].rstrip(";\n")
    d = json.loads(raw)
    return d.get("standings", [])


def _rank_group(leagues) -> list[dict]:
    """One confederation's teams ranked by cross-league strength (ELO + offset)."""
    rows = []
    for lid, short in leagues:
        offset = co.league_offset(lid)
        for s in _load_standings(lid):
            elo = s.get("elo")
            if elo is None:
                continue
            rows.append({
                "team": s["team"], "league": lid, "league_short": short,
                "elo": int(round(elo)), "strength": round(float(elo) + offset, 1),
                "logo": s.get("logo"), "color": s.get("color"),
            })
    rows.sort(key=lambda r: -r["strength"])
    for i, r in enumerate(rows, 1):
        r["rank"] = i
    return rows


def build():
    data = {"groups": []}
    for conf, leagues in _GROUPS.items():
        ranked = _rank_group(leagues)
        if not ranked:
            continue
        data["groups"].append({
            "confederation": conf,
            "anchor": "EPL = 0" if conf == "UEFA" else "MLS = 0",
            "n_leagues": len({r["league"] for r in ranked}),
            "teams": ranked,
        })
    out = _DATA / "power.js"
    out.write_text("window.POWER_DATA = " + json.dumps(data, separators=(",", ":")) + ";\n")
    for g in data["groups"]:
        top = g["teams"][0]
        print(f"[power] {g['confederation']}: {len(g['teams'])} teams "
              f"({g['n_leagues']} leagues) · #1 {top['team']} (str {top['strength']})")
    print(f"[power] wrote {out} ({out.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    build()
