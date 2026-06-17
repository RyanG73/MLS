"""Cross-league strength + match model for continental competitions.

A team's strength is a single number on a common ELO-point scale:
    modeled:   domestic ELO (compute_elo) + league_offset (coefficients)
    unmodeled: club_strength (coefficients), no ELO term

team_strength() is the seam: Approach C (bridge-regression offsets) replaces only
how the offset is derived, with no change to the match model or simulator.
"""
from __future__ import annotations

import logging
import math

import numpy as np

from data_pipeline import coefficients as co
from scripts.eval.elo import compute_elo

_log = logging.getLogger(__name__)

# Champion ELO config (matches the rest of the platform).
_ELO_K, _ELO_HA, _ELO_REGRESS, _ELO_INIT = 25.0, 80.0, 0.40, 1500.0

# Physically-grounded priors (NOT optimizer-fit). The Task-7 validator is
# coefficient-only: ~48% of UCL matches have both teams at BASELINE_STRENGTH (no
# strength signal), and UCL's low 0.19 draw rate comes from strength mismatches the
# coefficient table can't see — so fitting these constants to that validator's 1X2
# Brier corrupts the goals model (it pushed BASE_GOALS to 10). These values keep
# scorelines realistic; a true edge-vs-naive calibration needs ELO-wired validation
# (a follow-on). The coefficient-only validator below is a sanity FLOOR, not a fit.
BASE_GOALS = 1.35    # expected goals per side at equal strength (UCL avg ~2.7/game)
GOAL_SCALE = 3000.0  # ELO points per 10x goal-rate multiplier; ~400-ELO gap => ~1.35x goal ratio
HOME_ADV_ELO = 80.0  # home advantage in strength points (matches the platform's ELO home_adv)


def team_strength(team: str, league_id: str | None, league_elos: dict[str, float]) -> float:
    """Cross-league strength (ELO points) for a team.

    Args:
        team:        team display key.
        league_id:   modeled-league id (e.g. 'epl') or None for unmodeled.
        league_elos: {team: current_elo} for that league (empty if unmodeled).

    If `league_id` is given but `team` is absent from `league_elos` (e.g. a
    name-map mismatch), this falls back to the coefficient strength and logs a
    WARNING — the fallback is intentional (the build still completes) but must be
    visible so a mis-mapped modeled team is not silently rated at the baseline.
    """
    if league_id and team in league_elos:
        return league_elos[team] + co.league_offset(league_id)
    if league_id and team not in league_elos:
        _log.warning("team_strength: %r mapped to modeled league %r but absent from "
                     "its ELO map; falling back to coefficient strength", team, league_id)
    return co.club_strength(team)


def match_lambdas(strength_home: float, strength_away: float,
                  neutral: bool = False) -> tuple[float, float]:
    """Expected goals (lambda_home, lambda_away) from cross-league strengths."""
    ha = 0.0 if neutral else HOME_ADV_ELO
    diff = strength_home - strength_away
    # Home advantage is modeled as a home-side boost only (added to the home rate,
    # mirroring ELO's home_adv); the away rate intentionally omits it.
    lam_home = BASE_GOALS * 10.0 ** ((diff + ha) / GOAL_SCALE)
    lam_away = BASE_GOALS * 10.0 ** ((-diff) / GOAL_SCALE)
    return lam_home, lam_away


def match_probs(strength_home: float, strength_away: float,
                neutral: bool = False, max_g: int = 10) -> tuple[float, float, float]:
    """(P_home, P_draw, P_away) via independent Poisson score matrix."""
    lam_h, lam_a = match_lambdas(strength_home, strength_away, neutral)
    ph = _poisson_pmf(np.arange(max_g + 1), lam_h)
    pa = _poisson_pmf(np.arange(max_g + 1), lam_a)
    M = np.outer(ph, pa)
    home = float(np.tril(M, -1).sum())
    draw = float(np.diag(M).sum())
    away = float(np.triu(M, 1).sum())
    t = home + draw + away
    return home / t, draw / t, away / t


def _poisson_pmf(ks: np.ndarray, lam: float) -> np.ndarray:
    # exp(-lam) * lam^k / k!  — vectorized, no scipy import needed for this size.
    return np.exp(-lam) * lam ** ks / np.array([math.factorial(int(k)) for k in ks])


def compute_league_elos(frame, K: float = _ELO_K, home_adv: float = _ELO_HA) -> dict[str, float]:
    """Current {team: elo} for a modeled league, champion config."""
    df = frame.sort_values("date")
    _, ratings = compute_elo(df, K=K, home_adv=home_adv,
                             regress=_ELO_REGRESS, initial=_ELO_INIT,
                             return_ratings=True)
    return ratings
