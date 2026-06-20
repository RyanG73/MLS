"""Approach C — fit cross-league ELO offsets from historical continental results.

Bridge-regression: minimise the NLL of observed 1X2 outcomes under the
`cross_league.match_probs` model, with a ridge penalty that pulls each offset
toward the prior from `coefficients.league_offset`.

Two INDEPENDENT fits are run because the confederations are DISCONNECTED graphs
(UEFA big-5 teams never play MLS/Liga MX in these competitions):
  * UEFA  — {epl, la-liga, serie-a, bundesliga, ligue-1}, anchor EPL = 0
  * Concacaf — {mls, liga-mx}, anchor MLS = 0

IMPORTANT NOTE — ELO timing:
    This implementation uses each team's CURRENT domestic ELO as the strength
    proxy. Historical ELO-as-of-match-date is a future refinement: it would
    require replaying the ELO sequence to a point-in-time rating, which the
    `_league_elos` cache does not currently support.  Current ELO is a reasonable
    proxy for completed continental competitions because the field changes slowly
    relative to seasonal ELO drift.

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
import json
import logging
import math
from pathlib import Path
from typing import NamedTuple

import numpy as np
from scipy.optimize import minimize

from data_pipeline import coefficients as co
from data_pipeline.espn_continental import continental_results
from scripts.build_continental_data import (
    _ESPN_TO_MODELED, _CONCACAF_ALIAS, META, _league_elos,
)
from scripts.eval.cross_league import match_probs

_log = logging.getLogger(__name__)

# ── confederations and their anchor/free leagues ──────────────────────────────
_UEFA_LEAGUES = ["epl", "la-liga", "serie-a", "bundesliga", "ligue-1"]
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

# ── data collection ───────────────────────────────────────────────────────────

class _Match(NamedTuple):
    home_league: str
    away_league: str
    home_elo: float    # domestic ELO (no offset applied yet)
    away_elo: float
    neutral: bool
    outcome: int       # 0=home win, 1=draw, 2=away win


def _resolve_elo(team: str, league_id: str) -> float | None:
    """Return domestic ELO for a modeled team, or None on miss."""
    cache = _league_elos(league_id)
    return cache.get(team)


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


def _collect_uefa(df, comp: str) -> list[_Match]:
    """Extract cross-modeled-league matches from a UEFA competition frame."""
    out: list[_Match] = []
    for _, row in df.iterrows():
        ht, at = row["home_team"], row["away_team"]
        h_info = _ESPN_TO_MODELED.get(ht)
        a_info = _ESPN_TO_MODELED.get(at)
        if not h_info or not a_info:
            continue  # at least one team is unmodeled
        h_lid, h_key = h_info
        a_lid, a_key = a_info
        if h_lid == a_lid:
            continue  # same league — no cross-league signal

        h_elo = _resolve_elo(h_key, h_lid)
        a_elo = _resolve_elo(a_key, a_lid)
        if h_elo is None or a_elo is None:
            _log.debug("UEFA ELO miss: %s/%s or %s/%s", ht, h_lid, at, a_lid)
            continue

        hg, ag = int(row["home_goals"]), int(row["away_goals"])
        if hg > ag:
            outcome = 0
        elif hg == ag:
            outcome = 1
        else:
            outcome = 2

        neutral = bool(row.get("neutral", False))
        out.append(_Match(h_lid, a_lid, h_elo, a_elo, neutral, outcome))
    return out


def _collect_concacaf(df, comp: str) -> list[_Match]:
    """Extract cross-modeled-league matches from a Concacaf competition frame."""
    out: list[_Match] = []
    mls_elos = _league_elos("mls")
    mx_elos = _league_elos("liga-mx")

    def _get(team: str) -> tuple[str, float] | None:
        """(league_id, elo) for a team, or None if unmodeled."""
        if team in mls_elos:
            return ("mls", mls_elos[team])
        if team in mx_elos:
            return ("liga-mx", mx_elos[team])
        if team in _CONCACAF_ALIAS:
            lid, frame_key = _CONCACAF_ALIAS[team]
            cache = mls_elos if lid == "mls" else mx_elos
            elo = cache.get(frame_key)
            return (lid, elo) if elo is not None else None
        return None

    for _, row in df.iterrows():
        ht, at = row["home_team"], row["away_team"]
        h_res = _get(ht)
        a_res = _get(at)
        if h_res is None or a_res is None:
            continue  # at least one unmodeled
        h_lid, h_elo = h_res
        a_lid, a_elo = a_res
        if h_lid == a_lid:
            continue  # same league

        hg, ag = int(row["home_goals"]), int(row["away_goals"])
        if hg > ag:
            outcome = 0
        elif hg == ag:
            outcome = 1
        else:
            outcome = 2

        neutral = bool(row.get("neutral", False))
        out.append(_Match(h_lid, a_lid, h_elo, a_elo, neutral, outcome))
    return out


# ── optimization ──────────────────────────────────────────────────────────────

def _nll_with_ridge(
    free_offsets: np.ndarray,
    matches: list[_Match],
    anchor_league: str,
    free_leagues: list[str],
    priors: dict[str, float],
    lam: float,
) -> float:
    """Objective = NLL + ridge toward priors (vectorized across matches)."""
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

    # Ridge: penalise deviation from priors for ALL free leagues
    n = len(matches) if matches else 1
    for i, lid in enumerate(free_leagues):
        nll += lam * n * (free_offsets[i] - priors[lid]) ** 2

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

    result = minimize(
        _nll_with_ridge,
        x0,
        args=(train, anchor, free_leagues, priors, lam),
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

def fit_offsets(lam: float = 0.01, seed: int = 42) -> dict[str, float]:
    """Fit cross-league ELO offsets from continental results (Approach C).

    Runs two independent fits (UEFA and Concacaf) with validation.  If the
    fitted offsets improve held-out Brier and are within sanity bounds, they
    are written to `experiments/league_offsets.json`.  Otherwise, the priors
    are written (or the file is left unchanged) and a report is printed.

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
    ap.add_argument("--lambda", dest="lam", type=float, default=0.01,
                    help="Ridge penalty weight (default: 0.01)")
    ap.add_argument("--seed", type=int, default=42, help="RNG seed for train/test split")
    a = ap.parse_args()
    fit_offsets(lam=a.lam, seed=a.seed)
