"""Build webapp/data/<comp>.js for a continental competition.

Resolves the field's cross-league strengths, runs the bracket Monte-Carlo, and
emits the knockout payload (outlook.mode='knockout', standings, field, champion
odds). Mirrors scripts/build_league_data.py for the table leagues.
"""
from __future__ import annotations

import argparse
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from data_pipeline.espn_continental import (
    continental_results, continental_fixtures, latest_season)
from data_pipeline.understat import canonical_frame
from scripts.eval import bracket_sim as bs
from scripts.eval import cross_league as cl
from scripts.eval.season_state import season_state, CONCLUDED
from scripts.payload_utils import write_js_payload

logger = logging.getLogger(__name__)

_LEAGUE_PHASE_ROUND = "league-phase"  # ESPN season.slug for the UCL/Europa group/league phase

# ESPN round slug → (display-round name, ordinal). Higher ordinal = further in the
# competition. Used to resolve a finished edition's actual bracket from results.
_ESPN_ROUND = {
    "league-phase": ("league", 0), "group-stage": ("league", 0),
    # CONMEBOL qualifying rounds, played BEFORE the group stage (2026-07-24).
    # They must be listed with ordinal 0 like the group stage: left unmapped they
    # fall through to `(raw_slug, 0)` and would render as a raw "second-stage"
    # label, and worse, _resolve_actual's furthest-round logic would read an
    # unknown ordinal as no progress at all.
    "first-stage": ("Qualifying", 0),
    "second-stage": ("Qualifying", 0),
    "third-stage": ("Qualifying", 0),
    "knockout-round-playoffs": ("Playoff", 1),
    "round-one": ("RoundOne", 1),
    "round-of-16": ("R16", 2),
    "quarterfinals": ("QF", 3),
    "semifinals": ("SF", 4),
    "final": ("Final", 5),
}

# Comp metadata for the payload header.
META = {
    # `rules` (2026-07-14 feedback: "cover all of these phases comprehensively"):
    # qualifying rounds and the pot/draw mechanics aren't modeled — ESPN's
    # continental feed only carries league-phase-onward fixtures (earliest date
    # in `data/espn_continental` for ucl is a September league-phase kickoff,
    # confirmed by direct inspection; no qualifying-round data exists in any
    # source this repo already has), and a real Swiss-model draw needs UEFA's
    # actual club coefficients for pot seeding, which this repo doesn't carry
    # either. Rather than silently omit those phases, `rules` explains the full
    # structure in plain language so a reader understands where the modeled
    # league-phase/knockout section sits within the real competition, even
    # though only that section carries live probabilities. Verified against
    # UEFA.com and the 2025-26 qualifying Wikipedia pages, 2026-07-14.
    "ucl": {
        "name": "UEFA Champions League",
        "confederation": "UEFA",
        "format_label": "League phase (36) → knockout",
        "phases": ["league", "knockout"],
        "rules": "Champions Path (domestic champions from lower-ranked leagues) and League Path "
                 "(non-champions from the top leagues) run separate qualifying rounds each summer; "
                 "Champions League qualifying losers drop into Europa League qualifying, whose losers "
                 "in turn drop into Conference League qualifying · qualifying winners plus the "
                 "highest-coefficient automatic entrants form the 36-team league phase modeled below: "
                 "a single seeded table where each club is drawn into 4 pots of 9 and plays 8 opponents "
                 "(2 from each pot, split home/away) · top 8 advance straight to the Round of 16, "
                 "9th-24th enter a two-legged knockout play-off for the remaining 8 spots, bottom 12 are "
                 "eliminated · Round of 16 onward is single-elimination, two legs until a one-off final.",
    },
    "europa": {
        "name": "UEFA Europa League",
        "confederation": "UEFA",
        "format_label": "League phase (36) → knockout",
        "phases": ["league", "knockout"],
        "rules": "Champions Path (teams eliminated from Champions League qualifying, plus domestic "
                 "champions from lower-ranked leagues) and Main Path (domestic non-champions and cup "
                 "winners, plus Champions League qualifying losers) run separate qualifying rounds; "
                 "Europa League qualifying losers drop into Conference League qualifying · qualifying "
                 "winners plus automatic entrants form the 36-team league phase modeled below — the "
                 "same seeded single-table format as the Champions League (4 pots of 9, 8 games each) "
                 "· top 8 advance to the Round of 16, 9th-24th enter a knockout play-off, bottom 12 are "
                 "out · single-elimination two-legged knockout from there to a one-off final.",
    },
    "conference": {
        "name": "UEFA Conference League",
        "confederation": "UEFA",
        "format_label": "League phase (36) → knockout",
        "phases": ["league", "knockout"],
        "rules": "Champions Path (teams eliminated from Champions League and Europa League qualifying, "
                 "plus domestic champions from lower-ranked leagues) and Main Path (domestic cup winners "
                 "and lower-ranked-league entrants, plus Europa League qualifying losers) run separate "
                 "qualifying rounds into a play-off round · winners form the 36-team league phase "
                 "modeled below — the same seeded single-table format as the other two competitions "
                 "(4 pots of 9, 8 games each) · top 8 advance to the Round of 16, 9th-24th enter a "
                 "knockout play-off, bottom 12 are out · single-elimination two-legged knockout from "
                 "there to a one-off final.",
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
    # CONMEBOL (2026-07-24). Shipped once scripts/eval/continental_calibrate.py
    # produced a validated CONMEBOL league-offset scale — before that every South
    # American league sat at offset 0.0 and a Bolivian club would have been rated
    # level with a Brazilian one. 100% of both fields resolves to a modeled league.
    "libertadores": {
        "name": "CONMEBOL Libertadores",
        "confederation": "CONMEBOL",
        "format_label": "8 groups of 4 → knockout",
        "phases": ["group", "knockout"],
        "rules": "Three qualifying stages each February decide the last six group-stage places; "
                 "those rounds are not modeled below (the projection starts at the group stage) "
                 "· 32 clubs are drawn into 8 groups of 4 and play everyone in their group home "
                 "and away · the top 2 of each group reach the round of 16, while the eight "
                 "third-placed clubs transfer into the Copa Sudamericana's knockout play-off "
                 "round · from the round of 16 the competition is two-legged single elimination "
                 "until a one-off final at a pre-selected neutral venue · projections-only: "
                 "there is no continental odds source, so no edge figures are shown.",
    },
    "sudamericana": {
        "name": "CONMEBOL Sudamericana",
        "confederation": "CONMEBOL",
        "format_label": "8 groups of 4 → knockout",
        "phases": ["group", "knockout"],
        "rules": "A first qualifying stage each March decides part of the group-stage field and "
                 "is not modeled below · 32 clubs are drawn into 8 groups of 4 and play everyone "
                 "in their group home and away · the 8 group winners go straight to the round of "
                 "16; in the real competition the 8 runners-up first play a knockout play-off "
                 "against the third-placed clubs dropping out of the Copa Libertadores — that "
                 "cross-competition inflow cannot be represented inside this competition's field, "
                 "so runners-up are advanced directly and their odds are correspondingly "
                 "optimistic · two-legged single elimination from the round of 16 to a one-off "
                 "neutral final · projections-only: no continental odds source.",
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
    # Bundesliga
    "Bayer Leverkusen": ("bundesliga", "Bayer Leverkusen"),
    "Bayern Munich": ("bundesliga", "Bayern Munich"),
    "Borussia Dortmund": ("bundesliga", "Borussia Dortmund"),
    "RB Leipzig": ("bundesliga", "RB Leipzig"),
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
        # Big-5 Understat leagues keep the direct canonical_frame call; every
        # other league routes through build_league_data's own source registry
        # (2026-07-24). Before this, ANY non-big-5 league reaching here raised
        # "Unknown Understat league" — which is why the CONMEBOL comps could not
        # be built even after their offsets were calibrated: Libertadores needs
        # ELO maps for a dozen leagues, none of them Understat-sourced.
        from data_pipeline.understat import BIG5
        if league_id in BIG5:
            frame = canonical_frame(league_id)
        else:
            from scripts.build_league_data import OUTLOOK, _load_frame
            cfg = OUTLOOK.get(league_id, {})
            frame = _load_frame(league_id, cfg.get("source", "espn"), cfg.get("asa_key"))
            if "is_result" in frame.columns:
                frame = frame[frame["is_result"]]
        frame = frame.dropna(subset=["home_goals", "away_goals"])
        result = cl.compute_league_elos(frame)

    _ELO_CACHE[league_id] = result
    return result


def _mls_elos() -> dict[str, float]:
    """Compute MLS ELOs from parity_frame and remap opaque ASA hash IDs to team names."""
    import pandas as pd
    from data_pipeline.asa_cache import get_teams

    df = pd.read_parquet("data/parity_frame.parquet")
    elos_by_hash = cl.compute_league_elos(df)

    id2name = {r.team_id: r.team_name for r in get_teams("mls").itertuples()}
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

    elif confederation == "CONMEBOL":
        # Resolution is by ESPN team id, not name — see league_bridge._resolve_by_id
        # for why (River Plate exists in both Argentina and Uruguay, and both play
        # this competition). `elos_caches` carries the prebuilt {league: {team: elo}}
        # maps plus the id→(league, frame_key) index built once per build.
        idx = (elos_caches or {}).get("_conmebol_index") or {}
        hit = idx.get(team)
        if hit:
            lid, frame_key = hit
            strength = cl.team_strength(frame_key, lid, (elos_caches or {}).get(lid, {}))
            return {"team": team, "league": lid, "strength": strength, "modeled": True}
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


def _build_games(comp_id: str, played, caches: dict | None = None) -> list[dict]:
    """Build per-match game-card dicts for the Match Projections tab.

    For each played match resolves both teams' cross-league strengths via
    _resolve_one, runs match_probs (confederation-aware), and attaches
    actual result. Market fields (mkt_*, edge_*) are always None — there is
    no continental odds source (football-data.co.uk is domestic-only).

    Args:
        comp_id: competition id (e.g. 'ucl').
        played:  DataFrame from continental_results — all played rows for the
                 season.  Rows with NaN goals (postponed/incomplete) are skipped.
        caches:  Concacaf ELO caches {'mls': ..., 'liga-mx': ...} or None for UEFA.

    Returns list of game-card dicts sorted by date ascending.
    """
    conf = META[comp_id]["confederation"]
    games: list[dict] = []

    # Drop rows where goals are unavailable (shouldn't occur in completed_only
    # results, but guard defensively).
    df = played.dropna(subset=["home_goals", "away_goals"]).copy()
    # Ensure date is a plain Python string.
    df["date_str"] = df["date"].apply(
        lambda d: d.strftime("%Y-%m-%d") if hasattr(d, "strftime") else str(d)[:10]
    )

    for _, row in df.iterrows():
        home_name = row["home_team"]
        away_name = row["away_team"]

        h_info = _resolve_one(home_name, comp_id, caches)
        a_info = _resolve_one(away_name, comp_id, caches)

        sh = h_info["strength"]
        sa = a_info["strength"]
        neutral = bool(row.get("neutral", False))

        ph, pd_, pa = cl.match_probs(sh, sa, neutral=neutral, conf=conf)

        hg = int(row["home_goals"])
        ag = int(row["away_goals"])
        if hg > ag:
            result = "H"
        elif hg < ag:
            result = "A"
        else:
            result = "D"

        display_round, _ = _ESPN_ROUND.get(row["round"], (row["round"], 0))

        games.append({
            "date": row["date_str"],
            "round": display_round,
            "home": home_name,
            "away": away_name,
            "pH": round(ph, 4),
            "pD": round(pd_, 4),
            "pA": round(pa, 4),
            "hg": hg,
            "ag": ag,
            "result": result,
            "modeled": h_info["modeled"] and a_info["modeled"],
            "mkt_home": None,
            "mkt_draw": None,
            "mkt_away": None,
            "edge_home": None,
            "edge_draw": None,
            "edge_away": None,
        })

    games.sort(key=lambda g: g["date"])
    return games


def _value_layer_scaffold() -> dict:
    """Empty value-layer scaffold — no continental odds source exists.

    football-data.co.uk is domestic-only; a continental odds feed would be
    required to compute model-minus-market edge.
    """
    return {
        "backtest": None,
        "value_bets": [],
        "note": (
            "No continental odds source — model−market edge unavailable "
            "(domestic-only football-data); requires a continental odds feed."
        ),
    }


_CONMEBOL_LEAGUES = [
    "brazil-serie-a", "argentina-primera", "chile-primera", "colombia-primera-a",
    "uruguay-primera", "peru-liga1", "ecuador-ligapro", "paraguay-primera",
    "bolivia-profesional", "venezuela-primera",
    "brazil-serie-b", "argentina-nacional",
]


def _conmebol_caches(comp_id: str, season: int) -> dict:
    """ELO maps for every CONMEBOL league + an ESPN-name → (league, key) index.

    The index is keyed by DISPLAY NAME but built by resolving ESPN team IDs, so
    it inherits id-level correctness while giving `_resolve_one` (which only
    receives a name) something it can look up. Safe because a club appears at
    most once in a single season's field, so names are unique within it.
    """
    from scripts.eval.continental_resolve import resolve as _resolve
    df = continental_results(comp_id, range(season, season + 1))
    pairs: dict[str, str] = {}
    for _, r in df.iterrows():
        for side in ("home", "away"):
            nm = r.get(f"{side}_team")
            if nm:
                pairs[nm] = r.get(f"{side}_id")
    try:
        up = continental_fixtures(comp_id, season)
        for _, r in up.iterrows():
            for side in ("home", "away"):
                nm = r.get(f"{side}_team")
                if nm and nm not in pairs:
                    pairs[nm] = r.get(f"{side}_id")
    except Exception:  # noqa: BLE001
        pass

    index: dict[str, tuple[str, str]] = {}
    for name, tid in pairs.items():
        hit = _resolve(tid, name, _CONMEBOL_LEAGUES)
        if hit:
            index[name] = hit
    caches: dict = {"_conmebol_index": index}
    for lid in {lid for lid, _ in index.values()}:
        caches[lid] = _league_elos(lid)
    unresolved = [n for n in pairs if n not in index]
    if unresolved:
        logger.warning("_conmebol_caches: %d/%d unresolved: %s",
                       len(unresolved), len(pairs), sorted(unresolved)[:8])
    return caches


def _infer_groups(comp_id: str, season: int, field) -> tuple[list[list[int]], list[int] | None]:
    """(groups, qualifiers) as FIELD INDICES, inferred from played group matches.

    Two clubs share a group exactly when they played each other in the group
    stage, so the real draw is recoverable from results — no need to invent one.
    When every group has played its full double round-robin the group stage is
    OVER, and the teams that actually advanced are returned as `qualifiers` so
    the simulator does not re-roll a settled phase (which would print
    elimination odds for clubs that have demonstrably already qualified).
    """
    df = continental_results(comp_id, range(season, season + 1))
    gs = df[(df["season"] == season) & (df["round"] == "group-stage")] if not df.empty else df
    pos = {t["team"]: i for i, t in enumerate(field)}
    if gs.empty:
        return [], None

    # Connected components over "played each other in the group stage".
    adj: dict[str, set] = {}
    for _, r in gs.iterrows():
        h, a = r["home_team"], r["away_team"]
        if h in pos and a in pos:
            adj.setdefault(h, set()).add(a)
            adj.setdefault(a, set()).add(h)
    seen, groups = set(), []
    for t in adj:
        if t in seen:
            continue
        comp, stack = [], [t]
        while stack:
            cur = stack.pop()
            if cur in seen:
                continue
            seen.add(cur)
            comp.append(cur)
            stack.extend(adj.get(cur, ()) - seen)
        groups.append(sorted(comp))

    fmt = bs.FORMATS[comp_id]["phase"]
    size = fmt["teams"] // fmt["groups"]
    if len(groups) != fmt["groups"] or any(len(g) != size for g in groups):
        logger.warning("_infer_groups: %s %s got %d groups %s — falling back to a random draw",
                       comp_id, season, len(groups), [len(g) for g in groups])
        return [], None

    # Complete when every group has played its full double round-robin.
    per_group_expected = size * (size - 1)
    complete = all(
        len(gs[(gs["home_team"].isin(g)) & (gs["away_team"].isin(g))]) >= per_group_expected
        for g in groups)

    qualifiers = None
    if complete:
        adv = fmt["advance_per_group"]
        qualifiers = []
        for g in groups:
            pts = dict.fromkeys(g, 0)
            gd = dict.fromkeys(g, 0)
            sub = gs[(gs["home_team"].isin(g)) & (gs["away_team"].isin(g))]
            for _, r in sub.iterrows():
                h, a = r["home_team"], r["away_team"]
                hg, ag = r.get("home_goals"), r.get("away_goals")
                if hg is None or ag is None or hg != hg or ag != ag:
                    continue
                gd[h] += hg - ag
                gd[a] += ag - hg
                if hg > ag:
                    pts[h] += 3
                elif ag > hg:
                    pts[a] += 3
                else:
                    pts[h] += 1
                    pts[a] += 1
            ranked = sorted(g, key=lambda t: (-pts[t], -gd[t], t))
            qualifiers.extend(pos[t] for t in ranked[:adv])

    return [[pos[t] for t in g] for g in groups], qualifiers


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
    if lp.empty and bs.FORMATS[comp_id]["phase"]["type"] == "groups":
        # CONMEBOL: the season's rows also carry the pre-group qualifying stages,
        # whose losers never reach the competition proper. Restrict the field to
        # the group stage or the 32-team format check below would truncate an
        # arbitrary alphabetical slice of a ~60-team set.
        lp = df[(df["season"] == season) & (df["round"] == "group-stage")]
    if not lp.empty:
        teams = sorted(set(lp["home_team"]) | set(lp["away_team"]))
    else:
        season_df = df[df["season"] == season]
        teams = sorted(set(season_df["home_team"]) | set(season_df["away_team"]))

    # Pre-load Concacaf caches once (amortised across all teams in the field).
    confederation = META[comp_id]["confederation"]
    elos_caches: dict | None = None
    if confederation == "Concacaf":
        elos_caches = {
            "mls": _league_elos("mls"),
            "liga-mx": _league_elos("liga-mx"),
        }
    elif confederation == "CONMEBOL":
        elos_caches = _conmebol_caches(comp_id, season)

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
    """True if this edition has a played final and no upcoming fixtures.

    Delegates to the shared season_state() detector.
    """
    played_count = int(played["is_result"].sum()) if not played.empty else 0
    final_played = not played[played["round"] == "final"].empty if not played.empty else False
    try:
        upcoming_count = len(continental_fixtures(comp_id, season))
    except Exception:
        upcoming_count = 0   # no fixtures reachable → treat the played edition as final
    return season_state(played_count, upcoming_count, final_played=final_played) == CONCLUDED


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
        # Build Concacaf caches if needed for _build_games.
        confederation = META[comp_id]["confederation"]
        caches_for_games: dict | None = None
        if confederation == "Concacaf":
            caches_for_games = {
                "mls": _league_elos("mls"),
                "liga-mx": _league_elos("liga-mx"),
            }
        games = _build_games(comp_id, played, caches_for_games)
        data = {
            # Top-level route state (see docs/CURRENT_STATE.md § Route State Taxonomy).
            # "completed" = final results, render with result framing, no projection affordances.
            "status": "completed",
            "data_status": "full_forecast",  # launch-plan B1 data contract
            "league": {"name": META[comp_id]["name"],
                       "confederation": META[comp_id]["confederation"]},
            "outlook": {
                "mode": "knockout",
                "confederation": META[comp_id]["confederation"],
                "format_label": META[comp_id]["format_label"],
                "rules": META[comp_id].get("rules"),
                "phases": META[comp_id]["phases"],
                "rounds": [r["round"] for r in bs.FORMATS[comp_id]["ko"]],
                # How many per group/table advance. The webapp hardcoded 4 (the
                # Leagues Cup value) until CONMEBOL's 8-groups-of-4-top-2 shape
                # arrived; it now reads this instead.
                "advance_per_table": (bs.FORMATS[comp_id]["phase"].get("advance_per_group")
                                      or bs.FORMATS[comp_id]["phase"].get("advance_per_table")),
                "concluded": True, "champion": res["champion"], "season_label": label,
            },
            "standings": res["standings"],
            "field": res["field"],
            "champion_odds": [{"team": t["team"], "win_pct": round(t["odds"]["win"] * 100, 1)}
                              for t in champ_sorted],
            "games": games,
            "value_layer": _value_layer_scaffold(),
            "generated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        }
        out = Path(f"webapp/data/{comp_id}.js")
        write_js_payload(out, "LEAGUE_DATA", data)
        print(f"[{comp_id}] wrote {out} ({out.stat().st_size // 1024} KB) · "
              f"CONCLUDED {label} · champion {res['champion']} · {len(res['field'])} teams · "
              f"{len(games)} games")
        return

    # In-progress / drawn edition → Monte-Carlo projection (original path).
    field = _resolve_field(comp_id, season)
    if len(field) < bs.FORMATS[comp_id]["phase"]["teams"]:
        print(f"[{comp_id}] only {len(field)} teams resolved — field not yet drawn; "
              f"emitting completed-bracket placeholder.")
    sim_groups, sim_quals = ([], None)
    if bs.FORMATS[comp_id]["phase"]["type"] == "groups":
        sim_groups, sim_quals = _infer_groups(comp_id, season, field)
        if sim_quals:
            print(f"[{comp_id}] group stage complete — seeding the bracket from the "
                  f"{len(sim_quals)} teams that actually qualified")
    result = bs.simulate(comp_id, field, N=sims,
                         groups=sim_groups or None, qualifiers=sim_quals)
    champ = sorted(
        ({"team": t["team"], "win_pct": round(t["odds"]["win"] * 100, 1)}
         for t in result["field"]),
        key=lambda x: -x["win_pct"],
    )
    # Build game cards for played matches (results) + upcoming (result=None, probs only).
    confederation = META[comp_id]["confederation"]
    caches_for_games: dict | None = None
    if confederation == "Concacaf":
        caches_for_games = {
            "mls": _league_elos("mls"),
            "liga-mx": _league_elos("liga-mx"),
        }
    elif confederation == "CONMEBOL":
        caches_for_games = _conmebol_caches(comp_id, season)
    games = _build_games(comp_id, played, caches_for_games)
    # Append upcoming fixtures (result=None, probs only).
    try:
        upcoming = continental_fixtures(comp_id, season)
        if not upcoming.empty:
            for _, row in upcoming.iterrows():
                home_name = row["home_team"]
                away_name = row["away_team"]
                h_info = _resolve_one(home_name, comp_id, caches_for_games)
                a_info = _resolve_one(away_name, comp_id, caches_for_games)
                ph, pd_, pa = cl.match_probs(
                    h_info["strength"], a_info["strength"],
                    neutral=bool(row.get("neutral", False)),
                    conf=confederation,
                )
                date_str = (row["date"].strftime("%Y-%m-%d")
                            if hasattr(row["date"], "strftime") else str(row["date"])[:10])
                display_round, _ = _ESPN_ROUND.get(row["round"], (row["round"], 0))
                games.append({
                    "date": date_str,
                    "round": display_round,
                    "home": home_name,
                    "away": away_name,
                    "pH": round(ph, 4),
                    "pD": round(pd_, 4),
                    "pA": round(pa, 4),
                    "hg": None,
                    "ag": None,
                    "result": None,
                    "modeled": h_info["modeled"] and a_info["modeled"],
                    "mkt_home": None,
                    "mkt_draw": None,
                    "mkt_away": None,
                    "edge_home": None,
                    "edge_draw": None,
                    "edge_away": None,
                })
            games.sort(key=lambda g: g["date"])
    except Exception:
        pass  # fixtures not reachable — played-only games are fine
    data = {
        # Top-level route state (see docs/CURRENT_STATE.md § Route State Taxonomy).
        # "knockout_live" = bracket/league phase active, render projection + current path.
        "status": "knockout_live",
        "data_status": "full_forecast",  # launch-plan B1 data contract
        "league": {"name": META[comp_id]["name"],
                   "confederation": META[comp_id]["confederation"]},
        "outlook": {
            "mode": "knockout",
            "confederation": META[comp_id]["confederation"],
            "format_label": META[comp_id]["format_label"],
            # `rules` was present on the CONCLUDED path only — an in-progress
            # edition silently dropped its format caveats (fixed 2026-07-24).
            # That matters most exactly while a competition is live: Sudamericana's
            # note that the runners-up play-off against the Libertadores drop-downs
            # is NOT modeled is only meaningful before the bracket resolves.
            "rules": META[comp_id].get("rules"),
            "phases": META[comp_id]["phases"],
            "rounds": [r["round"] for r in bs.FORMATS[comp_id]["ko"]],
            "advance_per_table": (bs.FORMATS[comp_id]["phase"].get("advance_per_group")
                                  or bs.FORMATS[comp_id]["phase"].get("advance_per_table")),
        },
        "standings": result["standings"],
        "field": result["field"],
        "champion_odds": champ,
        "games": games,
        "value_layer": _value_layer_scaffold(),
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    }
    out = Path(f"webapp/data/{comp_id}.js")
    write_js_payload(out, "LEAGUE_DATA", data)
    modeled = sum(1 for e in field if e["modeled"])
    total = len(field)
    print(
        f"[{comp_id}] wrote {out} ({out.stat().st_size // 1024} KB) · "
        f"{total} teams · modeled {modeled}/{total} · "
        f"champion favorite {champ[0]['team']} {champ[0]['win_pct']}% · "
        f"{len(games)} games"
    )


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--comp", default="ucl")
    ap.add_argument("--season", type=int, default=None,
                    help="edition start year; default = latest cached season")
    ap.add_argument("--sims", type=int, default=20000)
    a = ap.parse_args()
    build(a.comp, a.season, a.sims)
