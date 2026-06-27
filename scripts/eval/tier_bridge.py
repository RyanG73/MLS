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
