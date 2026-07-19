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
    ELO (1500.0).  Champion ELO config: K=25, home_adv=80, regress=0.40.

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
from scripts.eval.elo import compute_elo

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

_COMPS_BY_CONF = {
    "UEFA": ["ucl", "europa", "conference"],
    "Concacaf": ["concacaf-champions", "leagues-cup"],
}

# Experiments output
_OFFSETS_JSON = Path("experiments/league_offsets.json")

# Sanity bound: reject fit if any offset deviates more than this from its prior
_MAX_DELTA_FROM_PRIOR = 150.0

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
    rated = compute_elo(df, K=_K, home_adv=_HA, regress=_REGRESS, initial=_INIT)

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
        else:
            matches.extend(_collect_concacaf(df, comp))

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


def _resolve_uefa_team(espn_name: str) -> tuple[str, str] | None:
    """(league_id, frame_key) for an ESPN continental team name, or None.

    Three tiers, cheapest/safest first: (1) the hand-curated big-5 map, (2)
    exact normalized-name match against each extended league's own domestic
    frame, (3) a close-but-not-exact fallback (difflib) for name variants the
    normalizer alone doesn't catch — e.g. ESPN's "Ajax Amsterdam" vs the
    domestic frame's "Ajax", or "Olympiacos" vs "Olympiakos" spelling drift.
    Tier 3 requires a high similarity cutoff so it can't cross-match two
    different clubs; worst case on a miss is just one dropped match, not a
    wrong one.
    """
    hit = _ESPN_TO_MODELED.get(espn_name)
    if hit:
        return hit
    key = _norm_team(espn_name)
    if not key:
        return None
    for lid in _EXTENDED_UEFA:
        idx = _team_name_index(lid)
        if key in idx:
            return (lid, idx[key])
    # substring tier — city-suffix variants ("Ajax Amsterdam" ⊇ "Ajax")
    for lid in _EXTENDED_UEFA:
        idx = _team_name_index(lid)
        for nk, actual in idx.items():
            if len(nk) >= 4 and (nk in key or key in nk):
                return (lid, actual)
    # fuzzy tier — spelling drift (e.g. Olympiacos/Olympiakos)
    import difflib
    for lid in _EXTENDED_UEFA:
        idx = _team_name_index(lid)
        close = difflib.get_close_matches(key, idx.keys(), n=1, cutoff=0.85)
        if close:
            return (lid, idx[close[0]])
    return None


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

def _nll_with_ridge(
    free_offsets: np.ndarray,
    matches: list[_Match],
    anchor_league: str,
    free_leagues: list[str],
    priors: dict[str, float],
    lam: float,
    league_counts: dict[str, int] | None = None,
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
    offsets = {anchor_league: 0.0}
    for i, lid in enumerate(free_leagues):
        offsets[lid] = float(free_offsets[i])

    nll = 0.0
    for m in matches:
        delta_h = offsets.get(m.home_league, 0.0)
        delta_a = offsets.get(m.away_league, 0.0)
        ph, pd_, pa = match_probs(
            m.home_elo + delta_h,
            m.away_elo + delta_a,
            neutral=m.neutral,
        )
        probs = (ph, pd_, pa)
        p = max(probs[m.outcome], 1e-12)
        nll -= math.log(p)

    # Ridge: penalise deviation from priors, weighted by each league's OWN
    # match count (falls back to the global total if counts weren't supplied,
    # matching the old behaviour for any other caller).
    n = len(matches) if matches else 1
    for i, lid in enumerate(free_leagues):
        weight = league_counts.get(lid, n) if league_counts else n
        nll += lam * max(weight, 1) * (free_offsets[i] - priors[lid]) ** 2

    return nll


def _brier_score(matches: list[_Match], offsets: dict[str, float]) -> float:
    """1X2 Brier score on a set of matches given offset dict."""
    if not matches:
        return float("nan")
    total = 0.0
    for m in matches:
        delta_h = offsets.get(m.home_league, 0.0)
        delta_a = offsets.get(m.away_league, 0.0)
        ph, pd_, pa = match_probs(
            m.home_elo + delta_h,
            m.away_elo + delta_a,
            neutral=m.neutral,
        )
        probs = [ph, pd_, pa]
        actuals = [0.0, 0.0, 0.0]
        actuals[m.outcome] = 1.0
        bs = sum((probs[i] - actuals[i]) ** 2 for i in range(3))
        total += bs
    return total / len(matches)


def _fit_group(
    matches: list[_Match],
    all_leagues: list[str],
    anchor: str,
    lam: float,
    seed: int = 42,
) -> tuple[dict[str, float], dict[str, float], float, float]:
    """Fit offsets for one confederation group.

    Returns (fitted_offsets, prior_offsets, held_out_brier_prior, held_out_brier_fitted).
    """
    free_leagues = [l for l in all_leagues if l != anchor]
    priors = {lid: co.league_offset(lid) for lid in all_leagues}

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
        args=(train, anchor, free_leagues, priors, lam, league_counts),
        method="L-BFGS-B",
        options={"maxiter": 1000, "ftol": 1e-10},
    )

    fitted = {anchor: 0.0}
    for i, lid in enumerate(free_leagues):
        fitted[lid] = float(result.x[i])

    # Evaluate held-out Brier
    brier_prior = _brier_score(test, priors)
    brier_fitted = _brier_score(test, fitted)

    return fitted, priors, brier_prior, brier_fitted


# ── main entry point ──────────────────────────────────────────────────────────

def fit_offsets(lam: float = 0.00002, seed: int = 42) -> dict[str, float]:
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

    for confederation, all_leagues, anchor in [
        ("UEFA", _UEFA_LEAGUES, _UEFA_ANCHOR),
        ("Concacaf", _CONCACAF_LEAGUES, _CONCACAF_ANCHOR),
    ]:
        print(f"\n{'='*60}")
        print(f"Confederation: {confederation}  (anchor={anchor})")
        print(f"{'='*60}")

        matches = _collect_matches(confederation)
        print(f"Cross-league matches: {len(matches)}")

        if not matches:
            print("  NO MATCHES — using priors")
            priors = {lid: co.league_offset(lid) for lid in all_leagues}
            for lid, v in priors.items():
                adopted[lid] = v
            decisions[confederation] = "NO_DATA — priors adopted"
            continue

        # Run the primary seed fit
        fitted, priors, brier_prior, brier_fitted = _fit_group(
            matches, all_leagues, anchor, lam=lam, seed=seed,
        )

        # Robustness check: run 9 more seeds and count how often fitted beats prior.
        # For a small dataset (< 200 matches), a fit that wins < 70% of seeds is
        # considered noisy and is REJECTED in favour of the prior.
        _ROBUSTNESS_SEEDS = 9
        _ROBUSTNESS_MIN_WIN_RATE = 0.70  # must beat prior in >= 70% of seeds
        wins = 1 if brier_fitted < brier_prior else 0
        for s in range(1, _ROBUSTNESS_SEEDS + 1):
            _, _, bp, bf = _fit_group(matches, all_leagues, anchor, lam=lam, seed=seed + s * 100)
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
        is_stable = max_deviation <= _MAX_DELTA_FROM_PRIOR
        is_better = (
            (not math.isnan(brier_fitted)) and brier_fitted < brier_prior
            and win_rate >= _ROBUSTNESS_MIN_WIN_RATE
        )

        print(f"\nMax deviation from prior: {max_deviation:.1f} ELO"
              f"  ({'within' if is_stable else 'EXCEEDS'} ±{_MAX_DELTA_FROM_PRIOR} bound)")

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
            if not is_stable:
                reasons.append(f"max deviation {max_deviation:.1f} > {_MAX_DELTA_FROM_PRIOR} ELO")
            reason_str = "; ".join(reasons)
            print(f"\nDECISION: REJECT fitted offsets for {confederation} ({reason_str})")
            print(f"  Falling back to prior offsets.")
            decision = f"REJECTED ({reason_str})"
            use = priors

        for lid, v in use.items():
            adopted[lid] = v
        decisions[confederation] = decision

    # Write results
    _OFFSETS_JSON.parent.mkdir(parents=True, exist_ok=True)
    _OFFSETS_JSON.write_text(json.dumps(adopted, indent=2, sort_keys=True))
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
    a = ap.parse_args()
    fit_offsets(lam=a.lam, seed=a.seed)
