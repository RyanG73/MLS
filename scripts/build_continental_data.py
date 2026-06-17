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

from data_pipeline.espn_continental import (
    continental_results, continental_fixtures, latest_season)
from data_pipeline.understat import canonical_frame
from scripts.eval import bracket_sim as bs
from scripts.eval import cross_league as cl

logger = logging.getLogger(__name__)

_LEAGUE_PHASE_ROUND = "league-phase"  # ESPN season.slug for the UCL/Europa group/league phase

# ESPN round slug → (display-round name, ordinal). Higher ordinal = further in the
# competition. Used to resolve a finished edition's actual bracket from results.
_ESPN_ROUND = {
    "league-phase": ("league", 0), "group-stage": ("league", 0),
    "knockout-round-playoffs": ("Playoff", 1),
    "round-one": ("RoundOne", 1),
    "round-of-16": ("R16", 2),
    "quarterfinals": ("QF", 3),
    "semifinals": ("SF", 4),
    "final": ("Final", 5),
}

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


def _season_label(comp_id: str, played) -> str:
    """Human edition label, derived from the final's date (reliable across seasons)."""
    fin = played[played["round"] == "final"]
    src = fin if not fin.empty else played
    yr = int(src["date"].max().year)
    if META[comp_id]["confederation"] == "UEFA":
        return f"{yr - 1}-{str(yr)[2:]}"   # Sep–May, spans two calendar years
    return str(yr)                          # single calendar-year comps


def _is_concluded(comp_id: str, season: int, played) -> bool:
    """True if this edition has a played final and no upcoming fixtures."""
    if played.empty or played[played["round"] == "final"].empty:
        return False
    try:
        return continental_fixtures(comp_id, season).empty
    except Exception:
        return True   # no fixtures reachable → treat the played edition as final


def _actual_standings(comp_id, played):
    """Real final table from league/group-phase results, with resolved 0/1 buckets."""
    import collections
    phase_type = bs.FORMATS[comp_id]["phase"]["type"]
    if phase_type == "bracket":
        return []                                   # pure knockout — no table
    lp = played[played["round"].isin(["league-phase", "group-stage"])]
    if lp.empty:
        return []
    teams = set(lp["home_team"]) | set(lp["away_team"])
    pts = collections.Counter(); gd = collections.Counter()
    for _, r in lp.iterrows():
        h, a, hg, ag = r["home_team"], r["away_team"], r["home_goals"], r["away_goals"]
        gd[h] += hg - ag; gd[a] += ag - hg
        if hg > ag: pts[h] += 3
        elif ag > hg: pts[a] += 3
        else: pts[h] += 1; pts[a] += 1
    if phase_type == "two_table":
        caches = {"mls": _league_elos("mls"), "liga-mx": _league_elos("liga-mx")}
        rows = [{"team": t, "table": _resolve_one(t, comp_id, caches)["league"] or "other",
                 "pts": pts[t], "gd": gd[t]} for t in teams]
        for r in rows:
            r["league"] = r["table"]
        adv = bs.FORMATS[comp_id]["phase"]["advance_per_table"]
        for tk in set(r["table"] for r in rows):
            grp = sorted([r for r in rows if r["table"] == tk], key=lambda r: (-r["pts"], -r["gd"]))
            for i, r in enumerate(grp):
                r["advance"] = 1.0 if i < adv else 0.0
        return rows
    # UEFA single league phase
    auto = bs.FORMATS[comp_id]["phase"]["auto_advance"]
    _, phi = bs.FORMATS[comp_id]["phase"]["playoff"]
    order = sorted(teams, key=lambda t: (-pts[t], -gd[t]))
    return [{"team": t, "pts": pts[t], "gd": gd[t],
             "auto_advance": 1.0 if i < auto else 0.0,
             "playoff": 1.0 if auto <= i < phi else 0.0,
             "eliminated": 1.0 if i >= phi else 0.0}
            for i, t in enumerate(order)]


def _resolve_actual(comp_id: str, played):
    """Resolved payload for a FINISHED edition — actual champion + each team's furthest
    round reached (no projection). Returns {standings, field, champion}."""
    fmt = bs.FORMATS[comp_id]
    ko_rounds = [r["round"] for r in fmt["ko"]]
    ord_of = {name: o for (name, o) in _ESPN_ROUND.values()}
    teams = sorted(set(played["home_team"]) | set(played["away_team"]))
    far = {t: 0 for t in teams}
    for _, r in played.iterrows():
        _, o = _ESPN_ROUND.get(r["round"], ("?", 0))
        for t in (r["home_team"], r["away_team"]):
            if o > far[t]:
                far[t] = o
    fin = played[played["round"] == "final"].sort_values("date")
    champion = fin.iloc[-1]["winner"] if not fin.empty else None
    field = []
    for t in teams:
        odds = {rd: (1.0 if far[t] >= ord_of.get(rd, 99) else 0.0) for rd in ko_rounds}
        odds["win"] = 1.0 if t == champion else 0.0
        field.append({"team": t, "odds": odds, "is_champion": t == champion})
    return {"standings": _actual_standings(comp_id, played),
            "field": field, "champion": champion}


def build(comp_id: str, season: int | None, sims: int):
    if season is None:
        season = latest_season(comp_id)
        if season is None:
            raise SystemExit(f"[{comp_id}] no cached results — run the ESPN adapter first.")
    played = continental_results(comp_id, range(season, season + 1))

    # Finished edition → show the actual result, not a projection.
    if _is_concluded(comp_id, season, played):
        res = _resolve_actual(comp_id, played)
        label = _season_label(comp_id, played)
        champ_sorted = sorted(res["field"], key=lambda t: -t["odds"]["win"])
        data = {
            "league": {"name": META[comp_id]["name"],
                       "confederation": META[comp_id]["confederation"]},
            "outlook": {
                "mode": "knockout",
                "confederation": META[comp_id]["confederation"],
                "format_label": META[comp_id]["format_label"],
                "phases": META[comp_id]["phases"],
                "rounds": [r["round"] for r in bs.FORMATS[comp_id]["ko"]],
                "concluded": True, "champion": res["champion"], "season_label": label,
            },
            "standings": res["standings"],
            "field": res["field"],
            "champion_odds": [{"team": t["team"], "win_pct": round(t["odds"]["win"] * 100, 1)}
                              for t in champ_sorted],
            "games": [],
        }
        out = Path(f"webapp/data/{comp_id}.js")
        out.write_text("window.LEAGUE_DATA = " + json.dumps(data, separators=(",", ":")) + ";\n")
        print(f"[{comp_id}] wrote {out} ({out.stat().st_size // 1024} KB) · "
              f"CONCLUDED {label} · champion {res['champion']} · {len(res['field'])} teams")
        return

    # In-progress / drawn edition → Monte-Carlo projection (original path).
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
    ap.add_argument("--season", type=int, default=None,
                    help="edition start year; default = latest cached season")
    ap.add_argument("--sims", type=int, default=20000)
    a = ap.parse_args()
    build(a.comp, a.season, a.sims)
