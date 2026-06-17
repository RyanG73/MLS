"""Build webapp/data/<comp>.js for a continental competition.

Resolves the field's cross-league strengths, runs the bracket Monte-Carlo, and
emits the knockout payload (outlook.mode='knockout', standings, field, champion
odds). Mirrors scripts/build_league_data.py for the table leagues.
"""
from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

from data_pipeline.espn_continental import continental_results
from data_pipeline.understat import canonical_frame
from scripts.eval import bracket_sim as bs
from scripts.eval import cross_league as cl

logger = logging.getLogger(__name__)

_LEAGUE_PHASE_ROUND = "league-phase"  # ESPN season.slug for the UCL/Europa group/league phase

# Comp metadata for the payload header.
META = {
    "ucl": {
        "name": "UEFA Champions League",
        "confederation": "UEFA",
        "format_label": "League phase (36) → knockout",
        "phases": ["league", "knockout"],
    },
    "europa": {
        "name": "UEFA Europa League",
        "confederation": "UEFA",
        "format_label": "League phase (36) → knockout",
        "phases": ["league", "knockout"],
    },
    "conference": {
        "name": "UEFA Conference League",
        "confederation": "UEFA",
        "format_label": "League phase (36) → knockout",
        "phases": ["league", "knockout"],
    },
    "concacaf-champions": {
        "name": "Concacaf Champions Cup",
        "confederation": "Concacaf",
        "format_label": "27-team knockout",
        "phases": ["knockout"],
    },
    "leagues-cup": {
        "name": "Leagues Cup",
        "confederation": "Concacaf",
        "format_label": "Two-table group → knockout",
        "phases": ["group", "knockout"],
    },
}

# ESPN displayName -> (modeled league id, domestic-league team key as it appears in
# that league's Understat frame).
# Keys are EXACT ESPN displayNames from the field ESPN returns.
# Values use EXACT Understat team keys verified against canonical_frame() outputs.
_ESPN_TO_MODELED: dict[str, tuple[str, str]] = {
    # ── UCL entries ──────────────────────────────────────────────────────────
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

    # ── Europa League entries (2024-25 field) ───────────────────────────────
    # EPL
    "Manchester United": ("epl", "Manchester United"),
    "Tottenham Hotspur": ("epl", "Tottenham"),
    # La Liga
    "Athletic Club": ("la-liga", "Athletic Club"),
    "Real Sociedad": ("la-liga", "Real Sociedad"),
    # Serie A — ESPN: "AS Roma"; Understat: "Roma"
    "AS Roma": ("serie-a", "Roma"),
    "Lazio": ("serie-a", "Lazio"),
    # Bundesliga — ESPN: "TSG Hoffenheim"; Understat: "Hoffenheim"
    "Eintracht Frankfurt": ("bundesliga", "Eintracht Frankfurt"),
    "TSG Hoffenheim": ("bundesliga", "Hoffenheim"),
    # Ligue-1
    "Lyon": ("ligue-1", "Lyon"),
    "Nice": ("ligue-1", "Nice"),

    # ── Conference League entries (2024-25 field) ────────────────────────────
    # EPL
    "Chelsea": ("epl", "Chelsea"),
    # La Liga
    "Real Betis": ("la-liga", "Real Betis"),
    # Serie A
    "Fiorentina": ("serie-a", "Fiorentina"),
    # Bundesliga — ESPN: "1. FC Heidenheim 1846"; Understat: "FC Heidenheim"
    "1. FC Heidenheim 1846": ("bundesliga", "FC Heidenheim"),
    # ESPN variant without "1. FC" prefix
    "FC Heidenheim 1846": ("bundesliga", "FC Heidenheim"),
}

# Aliases for Concacaf comps where the ESPN name doesn't exactly match the MLS
# or Liga MX ELO key.  Values are (league_id, frame_key).
_CONCACAF_ALIAS: dict[str, tuple[str, str]] = {
    # MLS — ESPN short name vs. ASA full name
    "LAFC": ("mls", "Los Angeles FC"),
    "Portland Timbers": ("mls", "Portland Timbers FC"),
    "Red Bull New York": ("mls", "New York Red Bulls"),
    "Vancouver Whitecaps": ("mls", "Vancouver Whitecaps FC"),
}

# Cache of {league_id: {team: current_elo}} so each league's frame loads once.
_ELO_CACHE: dict[str, dict[str, float]] = {}


def _league_elos(league_id: str) -> dict[str, float]:
    """Return {team_name: elo} for the given league, routing by source.

    - big-5 (epl/la-liga/serie-a/bundesliga/ligue-1): Understat canonical frame.
    - liga-mx: ESPN Soccer Liga MX frame (displayNames are already frame keys).
    - mls: ASA parity_frame.parquet with hash→name remapping via AmericanSoccerAnalysis.
    """
    if league_id in _ELO_CACHE:
        return _ELO_CACHE[league_id]

    if league_id == "mls":
        result = _mls_elos()
    elif league_id == "liga-mx":
        from data_pipeline.espn_soccer import liga_mx_frame
        df = liga_mx_frame()
        df = df.dropna(subset=["home_goals", "away_goals"])
        result = cl.compute_league_elos(df)
    else:
        # Big-5 Understat leagues
        frame = canonical_frame(league_id)
        frame = frame.dropna(subset=["home_goals", "away_goals"])
        result = cl.compute_league_elos(frame)

    _ELO_CACHE[league_id] = result
    return result


def _mls_elos() -> dict[str, float]:
    """Compute MLS ELOs from parity_frame and remap opaque ASA hash IDs to team names."""
    import pandas as pd
    from itscalledsoccer.client import AmericanSoccerAnalysis

    df = pd.read_parquet("data/parity_frame.parquet")
    elos_by_hash = cl.compute_league_elos(df)

    asa = AmericanSoccerAnalysis()
    try:
        asa.session.verify = False
    except Exception:
        pass
    id2name = {r.team_id: r.team_name for r in asa.get_teams(leagues="mls").itertuples()}
    return {id2name.get(h, h): e for h, e in elos_by_hash.items()}  # {ASA name: elo}


def _resolve_one(
    team: str,
    comp_id: str,
    elos_caches: dict[str, dict[str, float]] | None = None,
) -> dict:
    """Resolve a single ESPN team name to a field entry dict.

    UEFA comps: use _ESPN_TO_MODELED hand-map; fall back to coefficient strength.
    Concacaf comps: auto-resolve via MLS/Liga MX ELO caches, then _CONCACAF_ALIAS,
                    then coefficient fallback.
    """
    confederation = META[comp_id]["confederation"]

    if confederation == "UEFA":
        mapped = _ESPN_TO_MODELED.get(team)
        if mapped:
            lid, dom_key = mapped
            strength = cl.team_strength(dom_key, lid, _league_elos(lid))
            return {"team": team, "league": lid, "strength": strength, "modeled": True}
        else:
            strength = cl.team_strength(team, None, {})
            return {"team": team, "league": None, "strength": strength, "modeled": False}

    else:  # Concacaf
        mls_elos = elos_caches["mls"]
        mx_elos = elos_caches["liga-mx"]

        if team in mls_elos:
            strength = cl.team_strength(team, "mls", mls_elos)
            return {"team": team, "league": "mls", "strength": strength, "modeled": True}
        elif team in mx_elos:
            strength = cl.team_strength(team, "liga-mx", mx_elos)
            return {"team": team, "league": "liga-mx", "strength": strength, "modeled": True}
        elif team in _CONCACAF_ALIAS:
            lid, frame_key = _CONCACAF_ALIAS[team]
            cache = mls_elos if lid == "mls" else mx_elos
            strength = cl.team_strength(frame_key, lid, cache)
            return {"team": team, "league": lid, "strength": strength, "modeled": True}
        else:
            strength = cl.team_strength(team, None, {})
            return {"team": team, "league": None, "strength": strength, "modeled": False}


def _resolve_field(comp_id: str, season: int):
    """Latest field for the comp -> [{team, league, strength, modeled, ...}].

    Modeled big-5 entrants get domestic ELO + league offset; everyone else gets
    the coefficient-based club strength fallback.

    For UEFA comps (UCL/Europa/Conference): the new 36-team league-phase format
    started in 2024-25.  The ESPN parquet cache merges all seasons, so we filter
    to the 'league-phase' round to isolate the correct 36-team field.
    Pre-2024 seasons used 'group-stage' (32 teams); if no league-phase rows are
    found for the requested season we fall back to all teams in that season.

    For Concacaf comps: MLS and Liga MX ELO caches are built once and passed
    through to _resolve_one for auto-resolution.
    """
    # NOTE: continental_results returns ALL cached seasons on a cache hit (ignores the range);
    # the season + round filter below is REQUIRED to isolate this season's field.
    df = continental_results(comp_id, range(season, season + 1))
    if df.empty:
        return []

    # Prefer the league-phase round (new 36-team UEFA format) if present.
    lp = df[(df["season"] == season) & (df["round"] == _LEAGUE_PHASE_ROUND)]
    if not lp.empty:
        teams = sorted(set(lp["home_team"]) | set(lp["away_team"]))
    else:
        season_df = df[df["season"] == season]
        teams = sorted(set(season_df["home_team"]) | set(season_df["away_team"]))

    # Pre-load Concacaf caches once (amortised across all teams in the field).
    confederation = META[comp_id]["confederation"]
    elos_caches: dict[str, dict[str, float]] | None = None
    if confederation == "Concacaf":
        elos_caches = {
            "mls": _league_elos("mls"),
            "liga-mx": _league_elos("liga-mx"),
        }

    field = [_resolve_one(t, comp_id, elos_caches) for t in teams]

    expected = bs.FORMATS[comp_id]["phase"]["teams"]
    if len(field) > expected:
        logger.warning(
            "_resolve_field: %d teams resolved for %s but format expects %d; "
            "truncating (check for duplicate/variant team names)", len(field), comp_id, expected,
        )
    return field[:expected]


def build(comp_id: str, season: int, sims: int):
    field = _resolve_field(comp_id, season)
    if len(field) < bs.FORMATS[comp_id]["phase"]["teams"]:
        print(f"[{comp_id}] only {len(field)} teams resolved — field not yet drawn; "
              f"emitting completed-bracket placeholder.")
    result = bs.simulate(comp_id, field, N=sims)
    champ = sorted(
        ({"team": t["team"], "win_pct": round(t["odds"]["win"] * 100, 1)}
         for t in result["field"]),
        key=lambda x: -x["win_pct"],
    )
    data = {
        "league": {"name": META[comp_id]["name"],
                   "confederation": META[comp_id]["confederation"]},
        "outlook": {
            "mode": "knockout",
            "confederation": META[comp_id]["confederation"],
            "format_label": META[comp_id]["format_label"],
            "phases": META[comp_id]["phases"],
            "rounds": [r["round"] for r in bs.FORMATS[comp_id]["ko"]],
        },
        "standings": result["standings"],
        "field": result["field"],
        "champion_odds": champ,
        "games": [],
    }
    out = Path(f"webapp/data/{comp_id}.js")
    out.write_text("window.LEAGUE_DATA = " + json.dumps(data, separators=(",", ":")) + ";\n")
    modeled = sum(1 for e in field if e["modeled"])
    total = len(field)
    print(
        f"[{comp_id}] wrote {out} ({out.stat().st_size // 1024} KB) · "
        f"{total} teams · modeled {modeled}/{total} · "
        f"champion favorite {champ[0]['team']} {champ[0]['win_pct']}%"
    )


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--comp", default="ucl")
    ap.add_argument("--season", type=int, default=2024)
    ap.add_argument("--sims", type=int, default=20000)
    a = ap.parse_args()
    build(a.comp, a.season, a.sims)
