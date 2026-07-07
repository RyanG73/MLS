"""Fit 2nd-tier → 1st-tier ELO offsets from promoted-team first-season outcomes.

For each supported league pair, collects all historical teams that promoted from
the 2nd-tier to the 1st-tier, and fits a single ELO offset δ such that

    match_probs(elo_2nd_tier + δ, elo_opponent)

best predicts their first-season top-flight 1X2 outcomes (NLL + ridge penalty,
mirroring scripts/eval/league_bridge.py).

Validation: leave-one-season-out. Accepts the fitted offset if held-out Brier
≤ naive AND |δ - prior| < 200 ELO; otherwise writes the static prior.

Supported pairs (football_data.DIV coverage):
    championship   → epl
    bundesliga-2   → bundesliga
    serie-b        → serie-a

Usage:
    python -m scripts.eval.tier_bridge
    python -m scripts.eval.tier_bridge --dry-run
    python -m scripts.eval.tier_bridge --lam 0.05
"""
from __future__ import annotations

import bisect
import json
import logging
import math
from pathlib import Path
from typing import NamedTuple

import numpy as np
import pandas as pd
from scipy.optimize import minimize

from data_pipeline import coefficients as co
from scripts.eval.cross_league import _ELO_K, _ELO_HA, _ELO_REGRESS, _ELO_INIT, match_probs
from scripts.eval.elo import compute_elo

_log = logging.getLogger(__name__)

# Only fit on seasons within the model training window.
_TRAIN_FROM = 2017

# Sanity bound: reject any fitted offset that deviates more than this from its prior.
_MAX_DELTA_FROM_PRIOR = 200.0

# Minimum match count to attempt a fit (below this, prior is used directly).
_MIN_MATCHES = 20

_OFFSETS_JSON = Path("experiments/tier2_offsets.json")

# Supported (tier2, tier1) league ID pairs.
_TIER2_PAIRS: list[tuple[str, str]] = [
    ("championship", "epl"),
    ("bundesliga-2", "bundesliga"),
    ("serie-b", "serie-a"),
    ("segunda", "la-liga"),
    ("ligue-2", "ligue-1"),
    # English chain extension (2026-07-07): promotees into the Championship /
    # League One had only static ±120 priors; fit them like the other pairs.
    ("league-one", "championship"),
    ("league-two", "league-one"),
]


class _TierMatch(NamedTuple):
    promoted_team: str
    promoted_elo: float   # end-of-tier2-season ELO, BEFORE offset applied
    opponent_elo: float   # tier1 ELO as-of match date (no offset needed)
    is_home: bool         # is the promoted team the home side?
    outcome: int          # 0=home win, 1=draw, 2=away win
    season: int           # tier1 season (used for LOSO grouping)


# Module-level cache so the history is built only once per league per process.
_FD_ELO_HISTORY_CACHE: dict[str, dict[str, tuple[list, list]]] = {}


def _build_fd_elo_history(league_id: str) -> dict[str, tuple[list, list]]:
    """Per-team pre-match ELO history from a football_data source.

    Returns {team: ([dates_ascending], [pre_match_elos])}.
    Mirrors league_bridge._build_elo_history but reads football_data instead of
    Understat/MLS.  The history contains PRE-match ELOs (the rating BEFORE each
    match), which is what elo_asof-style lookups need.
    """
    if league_id in _FD_ELO_HISTORY_CACHE:
        return _FD_ELO_HISTORY_CACHE[league_id]

    from data_pipeline.football_data import match_results
    df = match_results(league_id).sort_values("date").reset_index(drop=True)
    df = df.dropna(subset=["home_goals", "away_goals"])
    if df.empty:
        _FD_ELO_HISTORY_CACHE[league_id] = {}
        return {}

    rated = compute_elo(df, K=_ELO_K, home_adv=_ELO_HA,
                        regress=_ELO_REGRESS, initial=_ELO_INIT)

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

    _FD_ELO_HISTORY_CACHE[league_id] = history
    _log.info("_build_fd_elo_history: %s → %d teams", league_id, len(history))
    return history


def _identify_promotions(tier1_results: pd.DataFrame) -> dict[int, set[str]]:
    """Return {tier1_season: set_of_newly_promoted_teams}.

    A team is considered promoted in season Y if it appears in the tier1 results
    for season Y but did NOT appear in season Y-1.  Seasons before _TRAIN_FROM
    are excluded.
    """
    promotions: dict[int, set[str]] = {}
    seasons = sorted(tier1_results["season"].unique())
    for i, s in enumerate(seasons):
        if i == 0 or s < _TRAIN_FROM:
            continue
        prev = seasons[i - 1]
        teams_now = set(
            tier1_results.loc[tier1_results["season"] == s, "home_team"].tolist() +
            tier1_results.loc[tier1_results["season"] == s, "away_team"].tolist()
        )
        teams_prev = set(
            tier1_results.loc[tier1_results["season"] == prev, "home_team"].tolist() +
            tier1_results.loc[tier1_results["season"] == prev, "away_team"].tolist()
        )
        promoted = teams_now - teams_prev
        if promoted:
            promotions[s] = promoted
    return promotions


def _identify_relegations(tier1_results: pd.DataFrame) -> dict[int, set[str]]:
    """Return {tier1_season: set_of_teams_relegated_into_the_tier2_season Y}.

    The mirror of _identify_promotions: a team is relegated for season Y if it appeared
    in tier1 season Y-1 but NOT in season Y. Keyed by Y — the season it left tier1, which
    is also the tier-2 season it drops into. Seasons before _TRAIN_FROM are excluded.
    """
    relegations: dict[int, set[str]] = {}
    seasons = sorted(tier1_results["season"].unique())
    for i, s in enumerate(seasons):
        if i == 0 or s < _TRAIN_FROM:
            continue
        prev = seasons[i - 1]
        teams_now = set(
            tier1_results.loc[tier1_results["season"] == s, "home_team"].tolist() +
            tier1_results.loc[tier1_results["season"] == s, "away_team"].tolist()
        )
        teams_prev = set(
            tier1_results.loc[tier1_results["season"] == prev, "home_team"].tolist() +
            tier1_results.loc[tier1_results["season"] == prev, "away_team"].tolist()
        )
        relegated = teams_prev - teams_now
        if relegated:
            relegations[s] = relegated
    return relegations


def _collect_tier_matches(
    tier2_lid: str, tier1_lid: str
) -> dict[int, list[_TierMatch]]:
    """Collect first-season tier1 matches for promoted teams, keyed by tier1 season.

    Both leagues use football_data so team names are consistent within
    football-data.co.uk's naming convention.

    Returns {tier1_season: [_TierMatch, ...]}.
    """
    from data_pipeline.football_data import match_results

    tier1_df = match_results(tier1_lid)
    tier2_history = _build_fd_elo_history(tier2_lid)
    tier1_history = _build_fd_elo_history(tier1_lid)

    tier1_df = tier1_df[tier1_df["season"] >= _TRAIN_FROM]
    promotions = _identify_promotions(tier1_df)

    matches_by_season: dict[int, list[_TierMatch]] = {}

    for tier1_season, promoted_teams in sorted(promotions.items()):
        # The cutoff for end-of-tier2-season: June 30 of the season-end year.
        # e.g. for tier1_season=2022 (2022-23), promoted from tier2 2021 (2021-22),
        # end-of-tier2 cutoff = 2022-06-30.
        tier2_cutoff = pd.Timestamp(f"{tier1_season}-06-30")
        season_matches: list[_TierMatch] = []
        tier1_season_df = tier1_df[tier1_df["season"] == tier1_season]

        for _, row in tier1_season_df.iterrows():
            ht, at = row["home_team"], row["away_team"]
            match_date = pd.Timestamp(row["date"]) if pd.notna(row["date"]) else None
            if match_date is None:
                continue
            hg, ag = int(row["home_goals"]), int(row["away_goals"])
            outcome = 0 if hg > ag else (1 if hg == ag else 2)

            for is_home, promoted, opponent in [(True, ht, at), (False, at, ht)]:
                if promoted not in promoted_teams:
                    continue

                # End-of-tier2-season ELO: most recent pre-match ELO on or before cutoff.
                dates_t2, elos_t2 = tier2_history.get(promoted, ([], []))
                idx_t2 = bisect.bisect_right(dates_t2, tier2_cutoff)
                if idx_t2 == 0:
                    _log.debug(
                        "_collect_tier_matches: %s has no tier2 ELO before %s — skipping",
                        promoted, tier2_cutoff,
                    )
                    continue
                promoted_elo = elos_t2[idx_t2 - 1]

                # Opponent's tier1 ELO as-of match date.
                dates_t1, elos_t1 = tier1_history.get(opponent, ([], []))
                idx_t1 = bisect.bisect_left(dates_t1, match_date)
                opp_elo = elos_t1[idx_t1 - 1] if idx_t1 > 0 else _ELO_INIT

                season_matches.append(_TierMatch(
                    promoted_team=promoted,
                    promoted_elo=promoted_elo,
                    opponent_elo=opp_elo,
                    is_home=is_home,
                    outcome=outcome,
                    season=tier1_season,
                ))

        if season_matches:
            matches_by_season[tier1_season] = season_matches
            _log.info(
                "_collect_tier_matches: %s→%s season %d: %d matches, %d promoted teams",
                tier2_lid, tier1_lid, tier1_season,
                len(season_matches), len(promoted_teams),
            )

    return matches_by_season


def _collect_relegated_matches(
    tier2_lid: str, tier1_lid: str
) -> dict[int, list[_TierMatch]]:
    """Collect first tier-2-season matches for teams RELEGATED from tier1, keyed by season.

    The mirror of _collect_tier_matches: a team relegated from tier1 after season Y-1 plays
    its first tier-2 season in Y. We seed it from its END-OF-TIER1 ELO and record its tier-2
    results against tier-2-ELO opponents. The _TierMatch.promoted_* fields carry the relegated
    team and its (tier1) ELO, so _fit_offset / _nll read them unchanged — only the offset's
    sign differs (positive: a dropped side is strong in the second tier).
    """
    from data_pipeline.football_data import match_results

    tier1_df = match_results(tier1_lid)
    tier2_df = match_results(tier2_lid)
    tier1_history = _build_fd_elo_history(tier1_lid)
    tier2_history = _build_fd_elo_history(tier2_lid)

    tier1_df = tier1_df[tier1_df["season"] >= _TRAIN_FROM]
    relegations = _identify_relegations(tier1_df)

    matches_by_season: dict[int, list[_TierMatch]] = {}

    for season, relegated_teams in sorted(relegations.items()):
        # Relegated team's end-of-tier1 ELO: most recent ELO on or before June 30 of `season`
        # (its final tier1 season Y-1 ends in spring of Y).
        tier1_cutoff = pd.Timestamp(f"{season}-06-30")
        season_matches: list[_TierMatch] = []
        tier2_season_df = tier2_df[tier2_df["season"] == season]

        for _, row in tier2_season_df.iterrows():
            ht, at = row["home_team"], row["away_team"]
            match_date = pd.Timestamp(row["date"]) if pd.notna(row["date"]) else None
            if match_date is None:
                continue
            hg, ag = int(row["home_goals"]), int(row["away_goals"])
            outcome = 0 if hg > ag else (1 if hg == ag else 2)

            for is_home, relegated, opponent in [(True, ht, at), (False, at, ht)]:
                if relegated not in relegated_teams:
                    continue

                dates_t1, elos_t1 = tier1_history.get(relegated, ([], []))
                idx_t1 = bisect.bisect_right(dates_t1, tier1_cutoff)
                if idx_t1 == 0:
                    continue
                relegated_elo = elos_t1[idx_t1 - 1]

                dates_t2, elos_t2 = tier2_history.get(opponent, ([], []))
                idx_t2 = bisect.bisect_left(dates_t2, match_date)
                opp_elo = elos_t2[idx_t2 - 1] if idx_t2 > 0 else _ELO_INIT

                season_matches.append(_TierMatch(
                    promoted_team=relegated,
                    promoted_elo=relegated_elo,
                    opponent_elo=opp_elo,
                    is_home=is_home,
                    outcome=outcome,
                    season=season,
                ))

        if season_matches:
            matches_by_season[season] = season_matches
            _log.info(
                "_collect_relegated_matches: %s→%s season %d: %d matches, %d relegated teams",
                tier1_lid, tier2_lid, season, len(season_matches), len(relegated_teams),
            )

    return matches_by_season


# ── objective and scoring ─────────────────────────────────────────────────────

def _nll(delta: float, matches: list[_TierMatch], prior: float, lam: float) -> float:
    """NLL + ridge objective for a single tier ELO offset."""
    nll = 0.0
    for m in matches:
        adj = m.promoted_elo + delta
        if m.is_home:
            ph, pd_, pa = match_probs(adj, m.opponent_elo, conf="UEFA")
        else:
            ph, pd_, pa = match_probs(m.opponent_elo, adj, conf="UEFA")
        p = max((ph, pd_, pa)[m.outcome], 1e-12)
        nll -= math.log(p)
    # Ridge penalty pulls δ toward the static prior.
    nll += lam * len(matches) * (delta - prior) ** 2
    return nll


def _brier(matches: list[_TierMatch], delta: float) -> float:
    """Mean sum-form Brier score on a match list given an ELO offset."""
    if not matches:
        return float("nan")
    total = 0.0
    for m in matches:
        adj = m.promoted_elo + delta
        if m.is_home:
            ph, pd_, pa = match_probs(adj, m.opponent_elo, conf="UEFA")
        else:
            ph, pd_, pa = match_probs(m.opponent_elo, adj, conf="UEFA")
        probs = [ph, pd_, pa]
        actuals = [0.0, 0.0, 0.0]
        actuals[m.outcome] = 1.0
        total += sum((probs[i] - actuals[i]) ** 2 for i in range(3))
    return total / len(matches)


def _fit_offset(matches: list[_TierMatch], prior: float, lam: float) -> float:
    """Fit a single scalar ELO offset on the given matches via NLL+ridge."""
    result = minimize(
        _nll,
        x0=[prior],
        args=(matches, prior, lam),
        method="L-BFGS-B",
        options={"maxiter": 1000, "ftol": 1e-10},
    )
    return float(result.x[0])


def _loso_validate(
    matches_by_season: dict[int, list[_TierMatch]],
    fitted_delta: float,
    prior: float,
    lam: float,
) -> tuple[float, float, float]:
    """Leave-one-season-out validation.

    For each season, fits on all OTHER seasons' matches and evaluates on the
    held-out season.  Returns (mean_brier_fitted, mean_brier_prior, naive_brier).

    naive_brier is always 2/3 (uniform 1/3 per outcome, sum-form).
    """
    seasons = sorted(matches_by_season.keys())
    bf, bp = [], []
    for held_out in seasons:
        train = [m for s, ms in matches_by_season.items()
                 if s != held_out for m in ms]
        test = matches_by_season[held_out]
        if not train or not test:
            continue
        d_cv = _fit_offset(train, prior, lam)
        bf.append(_brier(test, d_cv))
        bp.append(_brier(test, prior))

    if not bf:
        return float("nan"), float("nan"), 2 / 3
    return float(np.mean(bf)), float(np.mean(bp)), 2 / 3


# ── main entry point ──────────────────────────────────────────────────────────

def _fit_and_validate(key: str, matches_by_season: dict[int, list[_TierMatch]] | None,
                      prior: float, lam: float) -> float:
    """Fit + LOSO-validate one direction's offset. Falls back to the static prior on too-few
    matches, over-deviation from the prior, or a worse-than-naive held-out Brier."""
    all_matches = [m for ms in (matches_by_season or {}).values() for m in ms]
    if len(all_matches) < _MIN_MATCHES:
        _log.warning("fit_all: only %d matches for %s (need %d) — using prior",
                     len(all_matches), key, _MIN_MATCHES)
        return prior
    fitted = _fit_offset(all_matches, prior, lam)
    brier_f, brier_p, brier_n = _loso_validate(matches_by_season, fitted, prior, lam)
    _log.info("fit_all: %s fitted=%.1f  LOSO brier: fitted=%.4f prior=%.4f naive=%.4f",
              key, fitted, brier_f, brier_p, brier_n)
    if abs(fitted - prior) > _MAX_DELTA_FROM_PRIOR:
        _log.warning("fit_all: %s offset %.1f deviates >%.0f ELO from prior %.1f — using prior",
                     key, fitted, _MAX_DELTA_FROM_PRIOR, prior)
        return prior
    if not math.isnan(brier_f) and brier_f > brier_n:
        _log.warning("fit_all: %s fitted Brier %.4f > naive %.4f — using prior",
                     key, brier_f, brier_n)
        return prior
    return round(fitted, 2)


def fit_all(lam: float = 0.01, dry_run: bool = False) -> dict[str, float]:
    """Fit bidirectional cross-tier ELO offsets for all supported league pairs.

    Per pair, fits the forward (tier2→tier1, promoted teams) and reverse (tier1→tier2,
    relegated teams) offset, each LOSO-validated. Returns a dict mapping key
    (``championship_to_epl``, ``epl_to_championship``, …) → offset. Writes
    ``experiments/tier2_offsets.json`` unless ``dry_run=True``; falls back to the static
    prior for any direction that fails validation or has too few matches.
    """
    results: dict[str, float] = {}

    for tier2_lid, tier1_lid in _TIER2_PAIRS:
        # forward: tier2 → tier1 (promoted teams)
        fkey = f"{tier2_lid}_to_{tier1_lid}"
        fprior = co._TIER2_PRIORS.get(fkey, -100.0)
        _log.info("fit_all: fitting %s (prior=%.1f ELO)", fkey, fprior)
        try:
            fwd = _collect_tier_matches(tier2_lid, tier1_lid)
        except Exception as e:
            _log.warning("fit_all: failed to collect %s: %s — using prior", fkey, e)
            fwd = None
        results[fkey] = _fit_and_validate(fkey, fwd, fprior, lam)

        # reverse: tier1 → tier2 (relegated teams)
        rkey = f"{tier1_lid}_to_{tier2_lid}"
        rprior = co._TIER1_PRIORS.get(rkey, 100.0)
        _log.info("fit_all: fitting %s (prior=%.1f ELO)", rkey, rprior)
        try:
            rev = _collect_relegated_matches(tier2_lid, tier1_lid)
        except Exception as e:
            _log.warning("fit_all: failed to collect %s: %s — using prior", rkey, e)
            rev = None
        results[rkey] = _fit_and_validate(rkey, rev, rprior, lam)

    if not dry_run:
        _OFFSETS_JSON.parent.mkdir(parents=True, exist_ok=True)
        _OFFSETS_JSON.write_text(json.dumps(results, indent=2))
        _log.info("fit_all: wrote %s", _OFFSETS_JSON)
    else:
        _log.info("fit_all: dry-run, not writing JSON. Results: %s", results)

    return results


if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="Fit 2nd-tier → 1st-tier ELO offsets")
    parser.add_argument("--dry-run", action="store_true",
                        help="Fit and report without writing experiments/tier2_offsets.json")
    parser.add_argument("--lam", type=float, default=0.01,
                        help="Ridge penalty weight (default 0.01)")
    args = parser.parse_args()

    out = fit_all(lam=args.lam, dry_run=args.dry_run)
    print("\nResults:")
    for k, v in out.items():
        print(f"  {k}: {v:.1f}")
