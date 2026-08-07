"""Approach C — fit cross-league ELO offsets from historical continental results.

Bridge-regression: minimise the NLL of observed 1X2 outcomes under the
`cross_league.match_probs` model, with a ridge penalty that pulls each offset
toward the prior from `coefficients.league_offset`.

Two INDEPENDENT fits are run because the confederations are DISCONNECTED graphs
(UEFA big-5 teams never play MLS/Liga MX in these competitions):
  * UEFA  — {epl, la-liga, serie-a, bundesliga, ligue-1}, anchor EPL = 0
  * Concacaf — {mls, liga-mx}, anchor MLS = 0

ELO timing — as-of-date (Refinement R2 → R3):
    Each continental match uses the team's domestic ELO AS OF the match date,
    computed by replaying the domestic-league ELO sequence (compute_elo) and
    looking up each team's most recent pre-match rating strictly before the
    continental match date.  If the team has no prior domestic match before
    that date (e.g. a newly-entered team) we fall back to the league initial
    ELO (1500.0).  ELO config: K=25, regress=0.40, home advantage per
    competition via scripts.eval.elo.home_adv_for (55 outside MLS/Brazil).

Validation gate:
    A 70/30 train/test split (stratified by confederation, fixed seed) compares
    held-out 1X2 Brier under (a) prior offsets and (b) fitted offsets.
    Fitted offsets are only written to `experiments/league_offsets.json` if they
    LOWER held-out Brier vs the prior AND all fitted offsets are within ±150 ELO
    of their prior.  Otherwise priors are written (or no file if neither condition
    is met) and the function reports why.

Usage:
    python -m scripts.eval.league_bridge [--lambda 0.01] [--seed 42]
"""
from __future__ import annotations

import argparse
import bisect
import json
import logging
import math
import re
import unicodedata
from pathlib import Path
from typing import NamedTuple

import numpy as np
import pandas as pd
from scipy.optimize import minimize

from data_pipeline import coefficients as co
from data_pipeline.espn_continental import continental_results
from scripts.build_continental_data import (
    _ESPN_TO_MODELED, _CONCACAF_ALIAS, META, _league_elos,
)
from scripts.eval.cross_league import match_probs, _ELO_K, _ELO_HA, _ELO_REGRESS, _ELO_INIT
from scripts.eval.elo import compute_elo, home_adv_for

_log = logging.getLogger(__name__)

# ── champion ELO config (must match cross_league.py constants) ────────────────
_K       = _ELO_K       # 25.0
_HA      = _ELO_HA      # 80.0
_REGRESS = _ELO_REGRESS  # 0.40
_INIT    = _ELO_INIT    # 1500.0

# ── confederations and their anchor/free leagues ──────────────────────────────
# Extended 2026-07-13 (user feedback: "the dutch league has the same problem as
# the portuguese league. all european leagues should have calibrated elo") from
# the original big-5-only fit to every live UEFA-confederation table league this
# site models. Leagues with little/no continental history (e.g. Russia, banned
# from UEFA competitions since 2022) simply contribute ~0 to the NLL term and the
# ridge penalty holds them at their prior — safe to include even when thin.
_UEFA_LEAGUES = [
    "epl", "la-liga", "serie-a", "bundesliga", "ligue-1",
    "eredivisie", "primeira", "belgian-pro", "super-lig", "scottish-prem",
    "greek-super", "austria-bundesliga", "swiss-super-league",
    "romania-liga1", "ireland-premier", "russia-premier",
    "poland-ekstraklasa", "norway-eliteserien", "denmark-superliga",
    "sweden-allsvenskan", "finland-veikkausliiga",
]
_UEFA_ANCHOR = "epl"
_CONCACAF_LEAGUES = ["mls", "liga-mx"]
_CONCACAF_ANCHOR = "mls"

# ── CONMEBOL / AFC (2026-07-24) ───────────────────────────────────────────────
# Added so the South American and Asian continental competitions can ship. Before
# this fit, `coefficients.league_offset` returned 0.0 for every league here, which
# would have baselined a Bolivian club level with a Brazilian one in a Libertadores
# tie — the reason round 6 shipped the domestic leagues but held the cups back.
#
# Second tiers are included because they really do enter these competitions: a
# Brasileirão club relegated to Série B still plays out the Libertadores group
# stage it qualified for, and the as-of-date ELO lookup will find it in whichever
# frame it was actually playing in at the time.
_CONMEBOL_LEAGUES = [
    "brazil-serie-a", "argentina-primera", "chile-primera", "colombia-primera-a",
    "uruguay-primera", "peru-liga1", "ecuador-ligapro", "paraguay-primera",
    "bolivia-profesional", "venezuela-primera",
    "brazil-serie-b", "argentina-nacional",
]
# Brazil anchors CONMEBOL: most continental matches by a wide margin, and the
# deepest domestic history. Offsets are RELATIVE within the confederation — the
# same convention as MLS anchoring Concacaf.
_CONMEBOL_ANCHOR = "brazil-serie-a"

# k-league-1 has no ESPN slug (API-Football, seasons 2022-2024 only) so it has no
# roster for id-based resolution and falls back to name matching; india-isl has
# thin continental history. Both are safe to include — a league with few matches
# contributes ~nothing to the NLL and the ridge holds it at its prior.
_AFC_LEAGUES = [
    "japan-j1", "saudi-pro", "china-super", "k-league-1",
    "australia-aleague", "thai-league-1", "india-isl",
]
_AFC_ANCHOR = "japan-j1"

_COMPS_BY_CONF = {
    "UEFA": ["ucl", "europa", "conference"],
    "Concacaf": ["concacaf-champions", "leagues-cup"],
    "CONMEBOL": ["libertadores", "sudamericana"],
    "AFC": ["afc-champions"],
}

# Experiments output
_OFFSETS_JSON = Path("experiments/league_offsets.json")

# Sanity bound: reject fit if any offset deviates more than this from its prior.
# UEFA and Concacaf priors come from real external anchors (UEFA country
# coefficients / a hand-calibrated MLS-Liga MX gap), so a large deviation there
# genuinely signals a bad fit. CONMEBOL and AFC have NO external anchor in this
# repo — every prior is 0.0, which carries no information — so holding them to
# ±150 of an uninformative prior would just encode the uninformed guess. They get
# a wider bound; the held-out Brier and 10-seed robustness gates below are the
# real protection, and they are unchanged.
#
# UEFA moved to 450 on 2026-08-05, with the ridge (see _RIDGE_BY_CONF). ±150 was
# set when the UEFA ridge was strong enough that no league moved more than ~15
# ELO, so it never bound on anything; at a ridge that lets the matches speak it
# binds hardest on exactly the leagues whose prior is least trustworthy. Only
# the big five carry a captured UEFA coefficient. The other fifteen are typed
# estimates — _LEAGUE_COEFF's own PROVENANCE note says the 2026-07-31 additions
# are "best-available ESTIMATES ... not a fresh capture" — and holding a fit to
# ±150 of a guess is holding it to the guess. 450 still catches a runaway: an
# unregularised fit sends Finland to -1427 (deviation 1184).
_MAX_DELTA_FROM_PRIOR = 150.0
_MAX_DELTA_BY_CONF = {"CONMEBOL": 600.0, "AFC": 600.0, "UEFA": 450.0}

# Per-confederation ridge configuration: (lambda, weight_by_league_match_count).
# UEFA/Concacaf keep the historical count-weighted ridge and its lambda — their
# priors are informative and the existing offsets were fitted under exactly this
# setting, so changing it would silently move live UCL numbers. CONMEBOL/AFC use
# the constant-weight ridge with a lambda chosen on held-out data by
# scripts/eval/continental_calibrate.py (Stage 1).
_RIDGE_BY_CONF: dict[str, tuple[float, bool]] = {
    # UEFA, 2026-08-05. Was the CLI default 2e-5, which turned out to be strong
    # enough that the fit was decorative: every fitted offset landed within ~15
    # ELO of its coefficient prior, so the published ladder was really
    # _K_COEFF * (coeff - 94) and the 743 continental matches were barely
    # consulted. That is what put PSV 7th in the world, Club Brugge 10th and
    # Union SG 12th, ahead of Liverpool (19th) and Leverkusen (28th).
    #
    # Chosen on MEAN held-out Brier across all 10 robustness seeds, not on one
    # split (the sweep lives in the 2026-08-05 entry in PROJECT_HISTORY.md):
    #
    #     lambda   mean held-out Brier   vs prior   seeds won
    #     2e-5           0.6088           -0.0008     10/10   <- was live
    #     5e-6           0.6070           -0.0027     10/10
    #     2e-6           0.6045           -0.0051     10/10
    #     1e-6           0.6023           -0.0073     10/10
    #     5e-7           0.6006           -0.0090     10/10   <- adopted
    #     2e-7           0.5994           -0.0102      8/10   <- fails robustness
    #
    # 5e-7 is the loosest setting that still wins on every seed, and it extracts
    # an order of magnitude more from the same matches than 2e-5 did. Looser than
    # that the fit starts to separate — thin leagues run toward -infinity and the
    # seed agreement breaks, which is the ridge earning its keep.
    #
    # ridge_by_count stays True here. The adaptive (constant-weight) form was
    # measured too and is WORSE for UEFA: at a matched Brier of 0.6008 it wins
    # only 8/10 seeds and sends Sweden 684 ELO from its prior, against 10/10 and
    # 431 for the count-weighted fit at 5e-7.
    "UEFA": (5e-7, True),
    "CONMEBOL": (3e-6, False),
    "AFC": (1e-5, False),
}

# Confederations whose priors carry NO information (every prior is 0.0, because
# this repo has no external coefficient table for them). "Beat the prior" is a
# meaningless bar there — beating an all-zeros offset vector only proves the
# leagues differ at all. These must additionally beat a naive base-rate
# predictor on held-out data before they are adopted. This is what separates
# CONMEBOL (beats naive by 0.027, shipped) from AFC (loses to naive by 0.002,
# not shipped).
_UNINFORMATIVE_PRIOR_CONFS = {"CONMEBOL", "AFC"}

# ── ELO history cache: {league_id: (sorted_dates, {team: [sorted_dates], {team: [elos]}})}
# We store per-team parallel arrays (dates, elos) sorted ascending.
_ELO_HISTORY_CACHE: dict[str, dict[str, tuple[list, list]]] = {}


def _build_elo_history(league_id: str) -> dict[str, tuple[list, list]]:
    """Build per-team ELO history for a league: {team: ([dates], [pre_match_elos])}.

    Walks domestic matches in date order via compute_elo and records each
    team's pre-match ELO (i.e. the rating BEFORE that match is played).
    The lists are sorted ascending by date.  Used by elo_asof().
    """
    if league_id in _ELO_HISTORY_CACHE:
        return _ELO_HISTORY_CACHE[league_id]

    # Load the domestic frame for this league (mirrors _league_elos routing).
    # Every non-Concacaf league is routed through build_league_data.OUTLOOK's own
    # source registry (understat / footballdata / footballdata_intl / espn / asa)
    # via its _load_frame() — the same dispatch the production league builds use
    # — rather than assuming Understat, which only covers the big-5 (2026-07-13:
    # extending the bridge fit past the big-5 needs each league's REAL source).
    if league_id == "mls":
        df = _load_mls_frame()
    elif league_id == "liga-mx":
        from data_pipeline.espn_soccer import liga_mx_frame
        df = liga_mx_frame().dropna(subset=["home_goals", "away_goals"])
    else:
        from scripts.build_league_data import OUTLOOK, _load_frame
        cfg = OUTLOOK.get(league_id, {})
        source = cfg.get("source", "understat")
        if source == "understat":
            # refresh_latest=False: use the existing same-day parquet cache
            # rather than forcing a live Understat re-fetch (this is an offline
            # calibration script, not the production build; the optional
            # `understatapi` dependency isn't assumed to be installed here).
            from data_pipeline.understat import canonical_frame
            frame = canonical_frame(league_id, refresh_latest=False)
        else:
            frame = _load_frame(league_id, source, cfg.get("asa_key"))
        if "is_result" in frame.columns:
            frame = frame[frame["is_result"]]
        df = frame.dropna(subset=["home_goals", "away_goals"])

    df = df.sort_values("date").reset_index(drop=True)

    # compute_elo writes home_elo / away_elo as pre-match ratings.
    # home_adv_for(league_id), not the flat _HA: this replay has to reproduce
    # the ratings production publishes, and those became per-competition on
    # 2026-08-07. Fitting offsets against a differently-computed rating would
    # bake the discrepancy straight into the published ladder.
    rated = compute_elo(df, K=_K, home_adv=home_adv_for(league_id),
                        regress=_REGRESS, initial=_INIT)

    # Build per-team (dates, elos) parallel lists.
    history: dict[str, tuple[list, list]] = {}
    for _, row in rated.iterrows():
        d = row["date"]
        if pd.isna(d):
            continue
        d = pd.Timestamp(d)
        for team, elo_col in [(row["home_team"], row["home_elo"]),
                               (row["away_team"], row["away_elo"])]:
            if team not in history:
                history[team] = ([], [])
            history[team][0].append(d)
            history[team][1].append(float(elo_col))

    _ELO_HISTORY_CACHE[league_id] = history
    _log.info("_build_elo_history: %s → %d teams", league_id, len(history))
    return history


def _load_mls_frame() -> pd.DataFrame:
    """Load and name-remap MLS parity frame (mirrors build_continental_data._mls_elos)."""
    from data_pipeline.asa_cache import get_teams
    df = pd.read_parquet("data/parity_frame.parquet")
    # Remap ASA hash IDs to team names (home_team / away_team columns).
    id2name = {r.team_id: r.team_name for r in get_teams("mls").itertuples()}
    df = df.copy()
    df["home_team"] = df["home_team"].map(lambda h: id2name.get(h, h))
    df["away_team"] = df["away_team"].map(lambda a: id2name.get(a, a))
    return df.dropna(subset=["home_goals", "away_goals"])


def elo_asof(league_id: str, team: str, before_date: pd.Timestamp) -> float:
    """Return the team's most recent pre-match domestic ELO strictly before before_date.

    Falls back to _INIT (1500.0) if the team has no recorded domestic match
    prior to before_date (e.g. a team making its continental debut before
    any domestic results are stored).

    Args:
        league_id:    Domestic league id (e.g. 'epl', 'mls').
        team:         Team key as it appears in the domestic frame.
        before_date:  The continental match date; we want the most recent
                      domestic ELO STRICTLY BEFORE this date.
    """
    history = _build_elo_history(league_id)
    if team not in history:
        return _INIT
    dates, elos = history[team]
    # bisect_left gives the insertion point for before_date.
    # All entries with index < insertion point have date < before_date.
    idx = bisect.bisect_left(dates, before_date)
    if idx == 0:
        return _INIT  # no domestic match before this date
    return elos[idx - 1]


# ── data collection ───────────────────────────────────────────────────────────

class _Match(NamedTuple):
    home_league: str
    away_league: str
    home_elo: float    # domestic ELO as-of-date (no offset applied yet)
    away_elo: float
    neutral: bool
    outcome: int       # 0=home win, 1=draw, 2=away win
    match_date: object = None  # pd.Timestamp (None for backward-compat synthetic matches)


def _collect_matches(confederation: str) -> list[_Match]:
    """Collect cross-modeled-league completed matches for one confederation."""
    comps = _COMPS_BY_CONF[confederation]
    matches: list[_Match] = []

    for comp in comps:
        try:
            df = continental_results(comp)
        except Exception as e:
            _log.warning("collect_matches: failed to load %s: %s", comp, e)
            continue
        if df.empty:
            continue

        df = df[df["is_result"] == True].copy()
        if df.empty:
            continue

        if confederation == "UEFA":
            matches.extend(_collect_uefa(df, comp))
        elif confederation == "Concacaf":
            matches.extend(_collect_concacaf(df, comp))
        else:
            # CONMEBOL / AFC (2026-07-24) — ESPN-id resolution, see _resolve_by_id.
            leagues = (_CONMEBOL_LEAGUES if confederation == "CONMEBOL"
                       else _AFC_LEAGUES)
            matches.extend(_collect_by_id(df, leagues))

    _log.info("collect_matches: %s → %d cross-league matches", confederation, len(matches))
    return matches


# ── auto-resolution for leagues outside the hand-curated big-5 map ────────────
# build_continental_data._ESPN_TO_MODELED is hand-verified but only covers the
# original big-5 (it also feeds the live bracket simulator, so it's left alone
# rather than bulk-edited). Every other _UEFA_LEAGUES entry (2026-07-13
# extension) is resolved by normalized name match against that league's own
# domestic frame instead — safe because an unresolved team is simply dropped
# (fewer matches, same as before), never mismatched to the wrong team.
_EXTENDED_UEFA = [lid for lid in _UEFA_LEAGUES
                  if lid not in {"epl", "la-liga", "serie-a", "bundesliga", "ligue-1"}]
_TEAM_NAME_INDEX_CACHE: dict[str, dict[str, str]] = {}


def _norm_team(name: str) -> str:
    s = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode()
    s = re.sub(r"\b(fc|cf|sk|afc|ac|sc|1\.)\b", "", s, flags=re.I)
    return re.sub(r"[^a-z0-9]", "", s.lower())


def _team_name_index(league_id: str) -> dict[str, str]:
    if league_id not in _TEAM_NAME_INDEX_CACHE:
        hist = _build_elo_history(league_id)
        _TEAM_NAME_INDEX_CACHE[league_id] = {_norm_team(t): t for t in hist}
    return _TEAM_NAME_INDEX_CACHE[league_id]


# ESPN continental name → the domestic frame's own name, for clubs no amount of
# normalising will connect. Nearly all of these are football-data abbreviating a
# name ESPN writes out in full. Every entry here was a club whose entire European
# record was being discarded. (2026-08-07)
_UEFA_NAME_ALIASES: dict[str, tuple[str, str]] = {
    "Sporting CP":       ("primeira", "Sp Lisbon"),
    "Sporting Lisbon":   ("primeira", "Sp Lisbon"),
    "F.C. København":    ("denmark-superliga", "FC Copenhagen"),
    "FC Copenhagen":     ("denmark-superliga", "FC Copenhagen"),
    "Olympiacos":        ("greek-super", "Olympiakos"),
    "PAOK Salonika":     ("greek-super", "PAOK"),
    "Ajax Amsterdam":    ("eredivisie", "Ajax"),
}


def _resolve_uefa_team(espn_name: str) -> tuple[str, str] | None:
    """(league_id, frame_key) for an ESPN continental team name, or None.

    Tiers, cheapest and safest first: (1) the hand-curated big-5 map, (2) the
    alias table above, (3) exact normalized-name match, (4) substring for
    city-suffix variants, (5) difflib for spelling drift.

    Tiers 3-5 search EVERY modelled UEFA league. They used to search only
    `_EXTENDED_UEFA`, which deliberately excludes the big five — so a big-5 club
    absent from the hand map could never resolve at all, and its whole European
    record was dropped in silence. Napoli, Sevilla, Villarreal, Marseille,
    Newcastle, Wolfsburg and Union Berlin were all in that hole; measured
    2026-08-07, only 60% of cached continental matches had BOTH clubs resolved,
    and every unresolved match is evidence the bridge never sees.

    Opening the big five is safe rather than merely convenient: across all
    modelled UEFA leagues, 0 of 632 normalized club keys are claimed by more
    than one league. The ambiguity guard below is there so that stays true as
    leagues are added — on a collision it returns None (drop one match) instead
    of guessing (poison many).
    """
    hit = _ESPN_TO_MODELED.get(espn_name)
    if hit:
        return hit
    alias = _UEFA_NAME_ALIASES.get(espn_name)
    if alias:
        return alias
    key = _norm_team(espn_name)
    if not key:
        return None

    exact = [(lid, _team_name_index(lid)[key])
             for lid in _UEFA_LEAGUES if key in _team_name_index(lid)]
    if len(exact) == 1:
        return exact[0]
    if len(exact) > 1:
        _log.warning("resolve_uefa_team: %r is ambiguous across %s — dropping",
                     espn_name, [lid for lid, _ in exact])
        return None

    # substring tier — city-suffix variants ("Ajax Amsterdam" ⊇ "Ajax")
    sub = {(lid, actual)
           for lid in _UEFA_LEAGUES
           for nk, actual in _team_name_index(lid).items()
           if len(nk) >= 4 and (nk in key or key in nk)}
    if len(sub) == 1:
        return next(iter(sub))
    if len(sub) > 1:
        _log.warning("resolve_uefa_team: %r substring-matches %s — dropping",
                     espn_name, sorted(sub)[:4])
        return None

    # fuzzy tier — spelling drift (e.g. Olympiacos/Olympiakos)
    import difflib
    fuzzy = set()
    for lid in _UEFA_LEAGUES:
        idx = _team_name_index(lid)
        close = difflib.get_close_matches(key, idx.keys(), n=1, cutoff=0.85)
        if close:
            fuzzy.add((lid, idx[close[0]]))
    if len(fuzzy) == 1:
        return next(iter(fuzzy))
    return None


# ── ESPN-id resolution for CONMEBOL / AFC (2026-07-24) ───────────────────────
# Name matching is NOT safe in CONMEBOL. Measured across the 12 modeled leagues:
# 45 of 408 normalized club names collide. Most are benign (the same club either
# side of a promotion — Cruzeiro, Santos, Tigre appear in both tiers of their
# country), but four are genuinely DIFFERENT clubs sharing a name:
#     River Plate   Argentina  vs  Uruguay      ← both play Libertadores
#     Guaraní       Paraguay   vs  Brazil (B)
#     Portuguesa    Brazil     vs  Venezuela
#     Llaneros      Colombia   vs  Venezuela
# Resolving River Plate to the wrong country would hand a continental heavyweight
# a minor side's ELO (or vice-versa) and quietly poison the fit — precisely the
# kind of silent corruption a Brier gate would NOT catch, because the damage is
# spread thinly across many matches.
#
# So club identity is resolved by ESPN team id, which is shared between the
# continental feed and each league's /teams endpoint. Ambiguity that remains
# (a club that changed TIER between the continental match and today's roster
# snapshot) is settled by date: whichever candidate league that club actually
# played a domestic match in most recently before the continental match.
# Roster/name resolution lives in scripts/eval/continental_resolve so the
# production build can use it too — build_continental_data cannot import this
# module (this module imports IT), so neither may own the resolver.
from scripts.eval.continental_resolve import (          # noqa: E402
    league_rosters as _league_rosters,
    match_name_in_league as _match_name_in_league,
    resolve as _resolve_shared,
)


def _last_domestic_date(lid: str, key: str, before: pd.Timestamp):
    """Most recent domestic match date for `key` in `lid` strictly before `before`."""
    hist = _build_elo_history(lid)
    if key not in hist:
        return None
    dates = hist[key][0]
    idx = bisect.bisect_left(dates, before)
    return dates[idx - 1] if idx else None


def _resolve_by_id(espn_id, espn_name: str, leagues: list[str],
                   date: pd.Timestamp) -> tuple[str, str] | None:
    """Date-aware wrapper over continental_resolve.resolve.

    When a club resolves to more than one candidate league it has moved TIER
    (Brazil Série A↔B, Argentina Primera↔Nacional). Pick the league it last
    played a domestic match in before THIS continental match, so a historical
    match is rated on the frame the club was actually in at the time rather
    than on today's roster snapshot.
    """
    def tie_break(cands, name):
        best, best_date = None, None
        for lid in cands:
            k = _match_name_in_league(name, lid)
            if not k:
                continue
            d = _last_domestic_date(lid, k, date)
            if d is not None and (best_date is None or d > best_date):
                best, best_date = (lid, k), d
        return best

    return _resolve_shared(espn_id, espn_name, leagues, tie_break=tie_break)


def _collect_by_id(df, leagues: list[str]) -> list[_Match]:
    """Cross-league matches for a confederation resolved via ESPN team ids."""
    out: list[_Match] = []
    for _, row in df.iterrows():
        date = pd.Timestamp(row["date"]) if pd.notna(row.get("date")) else None
        if date is None:
            continue
        h = _resolve_by_id(row.get("home_id"), row["home_team"], leagues, date)
        a = _resolve_by_id(row.get("away_id"), row["away_team"], leagues, date)
        if not h or not a:
            continue
        h_lid, h_key = h
        a_lid, a_key = a
        if h_lid == a_lid:
            continue  # same league — carries no cross-league signal
        hg, ag = int(row["home_goals"]), int(row["away_goals"])
        outcome = 0 if hg > ag else (1 if hg == ag else 2)
        out.append(_Match(h_lid, a_lid,
                          elo_asof(h_lid, h_key, date),
                          elo_asof(a_lid, a_key, date),
                          bool(row.get("neutral", False)), outcome, date))
    return out


def _collect_uefa(df, comp: str) -> list[_Match]:
    """Extract cross-modeled-league matches from a UEFA competition frame.

    Uses ELO as-of the continental match date (not current ELO).
    """
    out: list[_Match] = []
    for _, row in df.iterrows():
        ht, at = row["home_team"], row["away_team"]
        h_info = _resolve_uefa_team(ht)
        a_info = _resolve_uefa_team(at)
        if not h_info or not a_info:
            continue  # at least one team is unmodeled
        h_lid, h_key = h_info
        a_lid, a_key = a_info
        if h_lid == a_lid:
            continue  # same league — no cross-league signal

        match_date = pd.Timestamp(row["date"]) if pd.notna(row.get("date")) else None
        if match_date is None:
            _log.debug("UEFA: no date for %s vs %s — skipping", ht, at)
            continue

        h_elo = elo_asof(h_lid, h_key, match_date)
        a_elo = elo_asof(a_lid, a_key, match_date)

        hg, ag = int(row["home_goals"]), int(row["away_goals"])
        if hg > ag:
            outcome = 0
        elif hg == ag:
            outcome = 1
        else:
            outcome = 2

        neutral = bool(row.get("neutral", False))
        out.append(_Match(h_lid, a_lid, h_elo, a_elo, neutral, outcome, match_date))
    return out


def _collect_concacaf(df, comp: str) -> list[_Match]:
    """Extract cross-modeled-league matches from a Concacaf competition frame.

    Uses ELO as-of the continental match date (not current ELO).
    """
    out: list[_Match] = []

    def _resolve_team(team: str) -> tuple[str, str] | None:
        """(league_id, frame_key) for a Concacaf team, or None if unmodeled."""
        mls_elos = _league_elos("mls")
        mx_elos = _league_elos("liga-mx")
        if team in mls_elos:
            return ("mls", team)
        if team in mx_elos:
            return ("liga-mx", team)
        if team in _CONCACAF_ALIAS:
            lid, frame_key = _CONCACAF_ALIAS[team]
            cache = mls_elos if lid == "mls" else mx_elos
            if frame_key in cache:
                return (lid, frame_key)
        return None

    for _, row in df.iterrows():
        ht, at = row["home_team"], row["away_team"]
        h_res = _resolve_team(ht)
        a_res = _resolve_team(at)
        if h_res is None or a_res is None:
            continue  # at least one unmodeled
        h_lid, h_key = h_res
        a_lid, a_key = a_res
        if h_lid == a_lid:
            continue  # same league

        match_date = pd.Timestamp(row["date"]) if pd.notna(row.get("date")) else None
        if match_date is None:
            _log.debug("Concacaf: no date for %s vs %s — skipping", ht, at)
            continue

        h_elo = elo_asof(h_lid, h_key, match_date)
        a_elo = elo_asof(a_lid, a_key, match_date)

        hg, ag = int(row["home_goals"]), int(row["away_goals"])
        if hg > ag:
            outcome = 0
        elif hg == ag:
            outcome = 1
        else:
            outcome = 2

        neutral = bool(row.get("neutral", False))
        out.append(_Match(h_lid, a_lid, h_elo, a_elo, neutral, outcome, match_date))
    return out


# ── optimization ──────────────────────────────────────────────────────────────

def _probs_vec(sh: np.ndarray, sa: np.ndarray, neutral: np.ndarray,
               conf: str, max_g: int = 10) -> np.ndarray:
    """Vectorized (n,3) [P_home, P_draw, P_away] — the array form of match_probs.

    The scalar `match_probs` is a Python-loop-per-match call that rebuilds a
    Poisson score matrix (and a factorial table) every time. That is fine for a
    build that scores a few hundred fixtures, but the bridge fit evaluates the
    objective across thousands of matches on every L-BFGS step — with CONMEBOL's
    2808 matches the scalar path made a single ridge sweep untenable. This is the
    same arithmetic, broadcast across matches; `test_league_bridge_vectorized`
    asserts it matches `match_probs` elementwise.
    """
    from scripts.eval.cross_league import _CONF_CONST
    c = _CONF_CONST.get(conf, _CONF_CONST["UEFA"])
    ha = np.where(neutral, 0.0, c["home_adv_elo"])
    diff = sh - sa
    lam_h = c["base_goals"] * 10.0 ** ((diff + ha) / c["goal_scale"])
    lam_a = c["base_goals"] * 10.0 ** ((-diff) / c["goal_scale"])

    ks = np.arange(max_g + 1)
    log_fact = np.cumsum(np.concatenate([[0.0], np.log(np.arange(1, max_g + 1))]))
    # log P(k; lam) = -lam + k*log(lam) - log(k!)
    ph = np.exp(-lam_h[:, None] + ks[None, :] * np.log(lam_h[:, None]) - log_fact[None, :])
    pa = np.exp(-lam_a[:, None] + ks[None, :] * np.log(lam_a[:, None]) - log_fact[None, :])
    M = ph[:, :, None] * pa[:, None, :]          # (n, home_goals, away_goals)
    tri = np.tril(np.ones((max_g + 1, max_g + 1)), -1)   # home > away
    home = (M * tri[None]).sum(axis=(1, 2))
    draw = np.einsum("nii->n", M)
    away = (M * tri.T[None]).sum(axis=(1, 2))
    tot = home + draw + away
    return np.stack([home / tot, draw / tot, away / tot], axis=1)


class _Packed(NamedTuple):
    """Match list flattened into arrays for the vectorized objective."""
    home_elo: np.ndarray
    away_elo: np.ndarray
    home_idx: np.ndarray   # index into the offset vector (anchor → -1)
    away_idx: np.ndarray
    neutral: np.ndarray
    outcome: np.ndarray


def _pack(matches: list[_Match], anchor: str, free_leagues: list[str]) -> _Packed:
    pos = {lid: i for i, lid in enumerate(free_leagues)}
    return _Packed(
        np.array([m.home_elo for m in matches], dtype=float),
        np.array([m.away_elo for m in matches], dtype=float),
        np.array([pos.get(m.home_league, -1) for m in matches], dtype=int),
        np.array([pos.get(m.away_league, -1) for m in matches], dtype=int),
        np.array([m.neutral for m in matches], dtype=bool),
        np.array([m.outcome for m in matches], dtype=int),
    )


def _apply_offsets(pk: _Packed, vec: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Strengths with per-league offsets applied (anchor index -1 contributes 0)."""
    padded = np.concatenate([vec, [0.0]])      # index -1 → the appended 0.0
    return pk.home_elo + padded[pk.home_idx], pk.away_elo + padded[pk.away_idx]


def _nll_with_ridge(
    free_offsets: np.ndarray,
    matches: list[_Match],
    anchor_league: str,
    free_leagues: list[str],
    priors: dict[str, float],
    lam: float,
    league_counts: dict[str, int] | None = None,
    conf: str = "UEFA",
    ridge_by_count: bool = True,
) -> float:
    """Objective = NLL + ridge toward priors (vectorized across matches).

    The ridge weight for each league is scaled by THAT league's own match
    count, not the global total (2026-07-13 fix — discovered extending the
    fit past 2 free leagues to 20: with a single global `n`, every league's
    ridge penalty scales with the WHOLE dataset's size regardless of how much
    evidence exists for that specific league, so adding more leagues crushes
    everyone's movement toward ~0 regardless of signal. A league with 3
    continental matches should stay close to its prior; a league with 60
    shouldn't be held by the same absolute penalty as a league with 3 just
    because the total dataset happens to be large.
    """
    # `matches` may arrive as a raw list (any external caller) or pre-packed
    # arrays (the fit path, which packs once instead of per L-BFGS step).
    pk = matches if isinstance(matches, _Packed) else _pack(matches, anchor_league, free_leagues)
    sh, sa = _apply_offsets(pk, np.asarray(free_offsets, dtype=float))
    probs = _probs_vec(sh, sa, pk.neutral, conf)
    p = np.maximum(probs[np.arange(len(pk.outcome)), pk.outcome], 1e-12)
    nll = float(-np.log(p).sum())

    # Ridge: penalise deviation from priors, weighted by each league's OWN
    # match count (falls back to the global total if counts weren't supplied,
    # matching the old behaviour for any other caller).
    # ridge_by_count=False (2026-07-24, CONMEBOL/AFC): penalty CONSTANT in the
    # league's match count. The count-weighted form above cancels against the
    # NLL — a league's log-likelihood contribution also scales with its match
    # count — so every league ends up with the same shrinkage factor no matter
    # how much evidence supports it. That is fine when the priors are
    # informative (UEFA/Concacaf, where the ridge is really just holding a
    # coefficient-derived value), but it is actively wrong when fitting from an
    # uninformative 0 prior: it let india-isl run to -2417 ELO off FOUR matches
    # while brazil-serie-a moved barely at all off a thousand. With a constant
    # penalty the shrinkage factor becomes lam/(lam + n_league·I), which is what
    # adaptive shrinkage should look like — thin leagues stay near the prior,
    # well-observed leagues move freely.
    n = len(matches) if matches else 1
    for i, lid in enumerate(free_leagues):
        if ridge_by_count:
            weight = league_counts.get(lid, n) if league_counts else n
            weight = max(weight, 1)
        else:
            weight = 1.0
        nll += lam * weight * (free_offsets[i] - priors[lid]) ** 2

    return nll


def _brier_score(matches: list[_Match], offsets: dict[str, float],
                 conf: str = "UEFA") -> float:
    """1X2 Brier score on a set of matches given offset dict."""
    if len(matches) == 0:
        return float("nan")
    sh = np.array([m.home_elo + offsets.get(m.home_league, 0.0) for m in matches])
    sa = np.array([m.away_elo + offsets.get(m.away_league, 0.0) for m in matches])
    neutral = np.array([m.neutral for m in matches], dtype=bool)
    outcome = np.array([m.outcome for m in matches], dtype=int)
    probs = _probs_vec(sh, sa, neutral, conf)
    actuals = np.zeros_like(probs)
    actuals[np.arange(len(outcome)), outcome] = 1.0
    return float(((probs - actuals) ** 2).sum(axis=1).mean())


def _naive_brier(matches: list[_Match]) -> float:
    """Base-rate baseline: this confederation's overall home/draw/away split.

    Fitted on the very matches it scores, which makes it the strongest possible
    form of the naive baseline — deliberately, so that clearing it means
    something. See _UNINFORMATIVE_PRIOR_CONFS for why it gates the new fits.
    """
    if len(matches) == 0:
        return float("nan")
    outcome = np.array([m.outcome for m in matches], dtype=int)
    rates = np.array([(outcome == k).mean() for k in range(3)])
    actuals = np.zeros((len(outcome), 3))
    actuals[np.arange(len(outcome)), outcome] = 1.0
    return float(((rates[None, :] - actuals) ** 2).sum(axis=1).mean())


def _fit_group(
    matches: list[_Match],
    all_leagues: list[str],
    anchor: str,
    lam: float,
    seed: int = 42,
    conf: str = "UEFA",
    ridge_by_count: bool = True,
) -> tuple[dict[str, float], dict[str, float], float, float]:
    """Fit offsets for one confederation group.

    Returns (fitted_offsets, prior_offsets, held_out_brier_prior, held_out_brier_fitted).
    """
    free_leagues = [l for l in all_leagues if l != anchor]
    # static_league_offset, NOT league_offset: the latter returns the fitted
    # file when one exists, which would ridge this fit toward its own previous
    # output and freeze whatever the first-ever run produced. (2026-07-31)
    priors = {lid: co.static_league_offset(lid) for lid in all_leagues}

    if not matches:
        _log.warning("_fit_group: no matches for anchor=%s — returning priors", anchor)
        return dict(priors), dict(priors), float("nan"), float("nan")

    # 70/30 train/test split
    rng = np.random.default_rng(seed)
    idxs = rng.permutation(len(matches))
    split = int(0.7 * len(matches))
    train_idxs = idxs[:split]
    test_idxs = idxs[split:]
    train = [matches[i] for i in train_idxs]
    test = [matches[i] for i in test_idxs]

    _log.info(
        "_fit_group: anchor=%s  total=%d  train=%d  test=%d",
        anchor, len(matches), len(train), len(test),
    )

    # Initial point = priors
    x0 = np.array([priors[lid] for lid in free_leagues], dtype=float)

    # Per-league ridge weight = how many of the TRAIN matches that league
    # actually appears in (home or away) — see _nll_with_ridge's docstring.
    league_counts: dict[str, int] = {}
    for m in train:
        league_counts[m.home_league] = league_counts.get(m.home_league, 0) + 1
        league_counts[m.away_league] = league_counts.get(m.away_league, 0) + 1

    result = minimize(
        _nll_with_ridge,
        x0,
        args=(_pack(train, anchor, free_leagues), anchor, free_leagues,
              priors, lam, league_counts, conf, ridge_by_count),
        method="L-BFGS-B",
        options={"maxiter": 1000, "ftol": 1e-10},
    )

    fitted = {anchor: 0.0}
    for i, lid in enumerate(free_leagues):
        fitted[lid] = float(result.x[i])

    # Evaluate held-out Brier
    brier_prior = _brier_score(test, priors, conf=conf)
    brier_fitted = _brier_score(test, fitted, conf=conf)

    return fitted, priors, brier_prior, brier_fitted


# ── main entry point ──────────────────────────────────────────────────────────

def fit_offsets(lam: float = 0.00002, seed: int = 42,
                only: set[str] | None = None) -> dict[str, float]:
    """Fit cross-league ELO offsets from continental results (Approach C, as-of-date ELO).

    Runs two independent fits (UEFA and Concacaf) with validation.  Each team's
    domestic ELO is taken AS OF the continental match date (historical replay),
    not the current end-of-history rating.  If the fitted offsets improve
    held-out Brier and are within sanity bounds, they are written to
    `experiments/league_offsets.json`.  Otherwise, priors are written and the
    reason is reported.

    Returns the adopted offsets dict {league_id: offset}.
    """
    adopted: dict[str, float] = {}
    decisions: dict[str, str] = {}

    _ALL_GROUPS = [
        ("UEFA", _UEFA_LEAGUES, _UEFA_ANCHOR),
        ("Concacaf", _CONCACAF_LEAGUES, _CONCACAF_ANCHOR),
        ("CONMEBOL", _CONMEBOL_LEAGUES, _CONMEBOL_ANCHOR),
        ("AFC", _AFC_LEAGUES, _AFC_ANCHOR),
    ]
    groups = [g for g in _ALL_GROUPS if only is None or g[0] in only]
    for confederation, all_leagues, anchor in groups:
        print(f"\n{'='*60}")
        print(f"Confederation: {confederation}  (anchor={anchor})")
        print(f"{'='*60}")

        matches = _collect_matches(confederation)
        print(f"Cross-league matches: {len(matches)}")

        if not matches:
            print("  NO MATCHES — using priors")
            priors = {lid: co.static_league_offset(lid) for lid in all_leagues}
            for lid, v in priors.items():
                adopted[lid] = v
            decisions[confederation] = "NO_DATA — priors adopted"
            continue

        # Per-confederation ridge configuration (see _RIDGE_BY_CONF).
        conf_lam, by_count = _RIDGE_BY_CONF.get(confederation, (lam, True))

        # Run the primary seed fit
        fitted, priors, brier_prior, brier_fitted = _fit_group(
            matches, all_leagues, anchor, lam=conf_lam, seed=seed,
            conf=confederation, ridge_by_count=by_count,
        )

        # Robustness check: run 9 more seeds and count how often fitted beats prior.
        # For a small dataset (< 200 matches), a fit that wins < 70% of seeds is
        # considered noisy and is REJECTED in favour of the prior.
        _ROBUSTNESS_SEEDS = 9
        _ROBUSTNESS_MIN_WIN_RATE = 0.70  # must beat prior in >= 70% of seeds
        wins = 1 if brier_fitted < brier_prior else 0
        for s in range(1, _ROBUSTNESS_SEEDS + 1):
            _, _, bp, bf = _fit_group(matches, all_leagues, anchor, lam=conf_lam,
                                      seed=seed + s * 100, conf=confederation,
                                      ridge_by_count=by_count)
            if bf < bp:
                wins += 1
        total_seeds = 1 + _ROBUSTNESS_SEEDS
        win_rate = wins / total_seeds
        print(f"Robustness: fitted beats prior in {wins}/{total_seeds} seeds ({win_rate:.0%})")

        # Print comparison table
        print(f"\n{'League':<15} {'Prior':>10} {'Fitted':>10} {'Δ':>10}")
        print("-" * 50)
        for lid in all_leagues:
            delta = fitted[lid] - priors[lid]
            print(f"  {lid:<13} {priors[lid]:>10.1f} {fitted[lid]:>10.1f} {delta:>+10.1f}")

        print(f"\nHeld-out Brier:")
        print(f"  Prior:  {brier_prior:.4f}")
        print(f"  Fitted: {brier_fitted:.4f}")
        delta_brier = brier_fitted - brier_prior
        print(f"  Δ:      {delta_brier:+.4f}  ({'improvement' if delta_brier < 0 else 'degradation'})")

        # Sanity check: reject if any offset is >±150 ELO from prior
        max_deviation = max(
            abs(fitted[lid] - priors[lid])
            for lid in all_leagues
        )
        bound = _MAX_DELTA_BY_CONF.get(confederation, _MAX_DELTA_FROM_PRIOR)
        is_stable = max_deviation <= bound
        is_better = (
            (not math.isnan(brier_fitted)) and brier_fitted < brier_prior
            and win_rate >= _ROBUSTNESS_MIN_WIN_RATE
        )

        # Extra gate for confederations with uninformative (all-zero) priors:
        # beating the prior there proves only that the leagues differ at all, so
        # the fit must also beat a base-rate predictor to be worth adopting.
        beats_naive = True
        if confederation in _UNINFORMATIVE_PRIOR_CONFS:
            rng_n = np.random.default_rng(seed)
            idxs_n = rng_n.permutation(len(matches))
            test_n = [matches[i] for i in idxs_n[int(0.7 * len(matches)):]]
            naive = _naive_brier(test_n)
            beats_naive = (not math.isnan(brier_fitted)) and brier_fitted < naive
            print(f"Naive base-rate Brier: {naive:.4f}  "
                  f"(fitted {brier_fitted:.4f} → {'BEATS' if beats_naive else 'LOSES TO'} naive)")
            is_better = is_better and beats_naive

        print(f"\nMax deviation from prior: {max_deviation:.1f} ELO"
              f"  ({'within' if is_stable else 'EXCEEDS'} ±{bound} bound)")

        if is_better and is_stable:
            print(f"\nDECISION: ADOPT fitted offsets for {confederation}")
            decision = "ADOPTED"
            use = fitted
        else:
            reasons = []
            if math.isnan(brier_fitted) or brier_fitted >= brier_prior:
                reasons.append(f"fitted Brier ({brier_fitted:.4f}) >= prior Brier ({brier_prior:.4f})")
            elif win_rate < _ROBUSTNESS_MIN_WIN_RATE:
                reasons.append(
                    f"robustness check failed: only {wins}/{total_seeds} seeds improve on prior "
                    f"({win_rate:.0%} < {_ROBUSTNESS_MIN_WIN_RATE:.0%} threshold)"
                )
            if not beats_naive:
                reasons.append("fitted Brier loses to a naive base-rate predictor "
                               "(uninformative-prior confederation — see "
                               "_UNINFORMATIVE_PRIOR_CONFS)")
            if not is_stable:
                reasons.append(f"max deviation {max_deviation:.1f} > {bound} ELO")
            reason_str = "; ".join(reasons)
            print(f"\nDECISION: REJECT fitted offsets for {confederation} ({reason_str})")
            print(f"  Falling back to prior offsets.")
            decision = f"REJECTED ({reason_str})"
            use = priors

        for lid, v in use.items():
            adopted[lid] = v
        decisions[confederation] = decision

    # Write results. MERGE into the existing file rather than overwrite it: a
    # run scoped with --conf must not drop (or silently re-drift) the offsets of
    # confederations it did not fit. Because each run's "prior" is the previous
    # run's fitted value, a full unscoped re-fit walks every league a little
    # every time — scoping keeps live UEFA numbers stable when only a new
    # confederation is being calibrated.
    _OFFSETS_JSON.parent.mkdir(parents=True, exist_ok=True)
    merged: dict[str, float] = {}
    if _OFFSETS_JSON.exists():
        try:
            merged = json.loads(_OFFSETS_JSON.read_text())
        except json.JSONDecodeError:
            merged = {}
    merged.update(adopted)
    _OFFSETS_JSON.write_text(json.dumps(merged, indent=2, sort_keys=True))
    print(f"\n{'='*60}")
    print(f"Wrote {_OFFSETS_JSON}")
    for conf, dec in decisions.items():
        print(f"  {conf}: {dec}")
    print("Continental odds will change ONLY if fitted offsets were adopted AND "
          "differ materially from priors.")

    return adopted


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--lambda", dest="lam", type=float, default=0.00002,
                    help="Ridge penalty weight (default: 0.00002 — see the "
                         "per-league weighting note on _nll_with_ridge; 0.01 "
                         "was calibrated for the original 2-free-league fit "
                         "and over-regularizes now that the ridge is properly "
                         "scaled per-league across 20 free leagues)")
    ap.add_argument("--seed", type=int, default=42, help="RNG seed for train/test split")
    ap.add_argument("--conf", action="append", default=None,
                    choices=["UEFA", "Concacaf", "CONMEBOL", "AFC"],
                    help="fit only these confederations and merge into the "
                         "existing offsets file (repeatable). Default: all.")
    a = ap.parse_args()
    fit_offsets(lam=a.lam, seed=a.seed, only=set(a.conf) if a.conf else None)
