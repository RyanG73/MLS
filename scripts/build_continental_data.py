"""Build webapp/data/<comp>.js for a continental competition.

Resolves the field's cross-league strengths, runs the bracket Monte-Carlo, and
emits the knockout payload (outlook.mode='knockout', standings, field, champion
odds). Mirrors scripts/build_league_data.py for the table leagues.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from data_pipeline.espn_continental import continental_results
from data_pipeline.understat import canonical_frame
from scripts.eval import bracket_sim as bs
from scripts.eval import cross_league as cl

_LEAGUE_PHASE_ROUND = "league-phase"  # ESPN season.slug for the UCL/Europa group/league phase

# Comp metadata for the payload header.
META = {
    "ucl": {"name": "UEFA Champions League", "confederation": "UEFA",
            "format_label": "League phase (36) → knockout", "phases": ["league", "knockout"]},
}

# ESPN displayName -> (modeled league id, domestic-league team key as it appears in
# that league's Understat frame).
# Keys are EXACT ESPN displayNames from the 2024-25 UCL league-phase field (36 teams).
# Values use EXACT Understat team keys verified against canonical_frame() outputs.
# To extend for other comps (Europa, Conference, Concacaf): add entries mapping each ESPN displayName -> (modeled league_id, that league's exact Understat team key).
_ESPN_TO_MODELED: dict[str, tuple[str, str]] = {
    # EPL
    "Arsenal": ("epl", "Arsenal"),
    "Aston Villa": ("epl", "Aston Villa"),
    "Liverpool": ("epl", "Liverpool"),
    "Manchester City": ("epl", "Manchester City"),
    # La Liga — ESPN uses UTF-8 accent: "Atlético Madrid"
    "Atlético Madrid": ("la-liga", "Atletico Madrid"),
    "Barcelona": ("la-liga", "Barcelona"),
    "Girona": ("la-liga", "Girona"),
    "Real Madrid": ("la-liga", "Real Madrid"),
    # Serie A — ESPN: "Internazionale"; Understat: "Inter"
    "AC Milan": ("serie-a", "AC Milan"),
    "Atalanta": ("serie-a", "Atalanta"),
    "Bologna": ("serie-a", "Bologna"),
    "Internazionale": ("serie-a", "Inter"),
    "Juventus": ("serie-a", "Juventus"),
    # Bundesliga — ESPN: "RB Leipzig"; Understat: "RasenBallsport Leipzig"
    "Bayer Leverkusen": ("bundesliga", "Bayer Leverkusen"),
    "Bayern Munich": ("bundesliga", "Bayern Munich"),
    "Borussia Dortmund": ("bundesliga", "Borussia Dortmund"),
    "RB Leipzig": ("bundesliga", "RasenBallsport Leipzig"),
    "VfB Stuttgart": ("bundesliga", "VfB Stuttgart"),
    # Ligue-1 — ESPN: "AS Monaco"; Understat: "Monaco"; ESPN: "Paris Saint-Germain"; Understat: "Paris Saint Germain"
    "AS Monaco": ("ligue-1", "Monaco"),
    "Brest": ("ligue-1", "Brest"),
    "Lille": ("ligue-1", "Lille"),
    "Paris Saint-Germain": ("ligue-1", "Paris Saint Germain"),
}

# Cache of {league_id: {team: current_elo}} so each league's frame loads once.
_ELO_CACHE: dict[str, dict[str, float]] = {}


def _league_elos(league_id: str) -> dict[str, float]:
    if league_id not in _ELO_CACHE:
        frame = canonical_frame(league_id)
        # Drop rows with missing goals/xg — ELO propagates NaN through the MoV
        # multiplier (math.log) if either score is NaN, poisoning all teams that
        # share a match with an incomplete row. ~100 rows in ligue-1.
        frame = frame.dropna(subset=["home_goals", "away_goals"])
        _ELO_CACHE[league_id] = cl.compute_league_elos(frame)
    return _ELO_CACHE[league_id]


def _resolve_field(comp_id: str, season: int):
    """Latest field for the comp -> [{team, league, strength, modeled, ...}].

    Modeled big-5 entrants get domestic ELO + league offset; everyone else gets
    the coefficient-based club strength fallback.

    For UCL: the new 36-team league-phase format started in 2024-25.  The ESPN
    parquet cache merges all seasons, so we filter to the 'league-phase' round
    to isolate the correct 36-team field.  Pre-2024 seasons used 'group-stage'
    (32 teams); if no league-phase rows are found for the requested season we
    fall back to all teams in that season.
    """
    # NOTE: continental_results returns ALL cached seasons on a cache hit (ignores the range); the season + round filter below is REQUIRED to isolate this season's field.
    df = continental_results(comp_id, range(season, season + 1))
    if df.empty:
        return []
    # Prefer the league-phase round (new 36-team UCL format) if present in this season.
    lp = df[(df["season"] == season) & (df["round"] == _LEAGUE_PHASE_ROUND)]
    if not lp.empty:
        teams = sorted(set(lp["home_team"]) | set(lp["away_team"]))
    else:
        season_df = df[df["season"] == season]
        teams = sorted(set(season_df["home_team"]) | set(season_df["away_team"]))
    field = []
    for t in teams:
        mapped = _ESPN_TO_MODELED.get(t)
        if mapped:
            lid, dom_key = mapped
            strength = cl.team_strength(dom_key, lid, _league_elos(lid))
            field.append({"team": t, "league": lid, "strength": strength, "modeled": True})
        else:
            strength = cl.team_strength(t, None, {})
            field.append({"team": t, "league": None, "strength": strength, "modeled": False})
    expected = bs.FORMATS[comp_id]["phase"]["teams"]
    if len(field) > expected:
        import logging
        logging.getLogger(__name__).warning(
            "_resolve_field: %d teams resolved for %s but format expects %d; "
            "truncating (check for duplicate/variant team names)", len(field), comp_id, expected)
    return field[:expected]


def build(comp_id: str, season: int, sims: int):
    field = _resolve_field(comp_id, season)
    if len(field) < bs.FORMATS[comp_id]["phase"]["teams"]:
        print(f"[{comp_id}] only {len(field)} teams resolved — field not yet drawn; "
              f"emitting completed-bracket placeholder.")
    result = bs.simulate(comp_id, field, N=sims)
    champ = sorted(({"team": t["team"], "win_pct": round(t["odds"]["win"] * 100, 1)}  # per-team rounding; the underlying odds["win"] sum to exactly 1.0
                    for t in result["field"]), key=lambda x: -x["win_pct"])
    data = {
        "league": {"name": META[comp_id]["name"],
                   "confederation": META[comp_id]["confederation"]},
        "outlook": {"mode": "knockout", "confederation": META[comp_id]["confederation"],
                    "format_label": META[comp_id]["format_label"],
                    "phases": META[comp_id]["phases"],
                    "rounds": [r["round"] for r in bs.FORMATS[comp_id]["ko"]]},
        "standings": result["standings"],
        "field": result["field"],
        "champion_odds": champ,
        "games": [],
    }
    out = Path(f"webapp/data/{comp_id}.js")
    out.write_text("window.LEAGUE_DATA = " + json.dumps(data, separators=(",", ":")) + ";\n")
    print(f"[{comp_id}] wrote {out} ({out.stat().st_size // 1024} KB) · "
          f"{len(field)} teams · champion favorite {champ[0]['team']} {champ[0]['win_pct']}%")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--comp", default="ucl")
    ap.add_argument("--season", type=int, default=2024)
    ap.add_argument("--sims", type=int, default=20000)
    a = ap.parse_args()
    build(a.comp, a.season, a.sims)
