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
