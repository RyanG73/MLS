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

# Confederation-aware match constants. Sweep-calibrated via validate_continental.py
# (ELO-wired backtest). Hard bounds: base_goals 1.2–1.7, goal_scale 2000–3500,
# home_adv_elo 40–110 (physically-sane per the T7 lesson; insane values auto-rejected).
_CONF_CONST: dict[str, dict[str, float]] = {
    # UEFA: physically-grounded priors (UCL avg ~2.7 goals/game, ~400-ELO gap => ~1.35× rate).
    # Validation: UCL BEATS naive (see validate_continental.py).
    "UEFA": {
        "base_goals": 1.35,
        "goal_scale": 3000.0,
        "home_adv_elo": 80.0,
    },
    # Concacaf: calibrated by grid-sweep on ELO-wired validator (2018-2024).
    # Sweep: base_goals ∈ {1.2–1.7}, goal_scale ∈ {2000–3500}, home_adv_elo ∈ {40–110}.
    # No sane set beats naive for either Concacaf comp (CC n=51 too small; 58.8% home-win
    # rate makes naive baseline very strong; LC also trails at all grid points).
    # Best sane set by combined excess over naive (total_excess=0.0300):
    #   CC:  model=0.5716 vs naive=0.5644 (TRAILS by 0.0072)
    #   LC:  model=0.6698 vs naive=0.6470 (TRAILS by 0.0228)
    # Lower goal_scale (2000) makes ELO gaps matter more (steeper rate multiplier),
    # reducing draw probability; higher home_adv_elo (110) boosts home-win rate
    # to better match Concacaf's empirically strong home advantage.
    "Concacaf": {
        "base_goals": 1.30,
        "goal_scale": 2000.0,
        "home_adv_elo": 110.0,
    },
}

# Module-level aliases — kept for backward compatibility with any direct references.
BASE_GOALS: float    = _CONF_CONST["UEFA"]["base_goals"]
GOAL_SCALE: float    = _CONF_CONST["UEFA"]["goal_scale"]
HOME_ADV_ELO: float  = _CONF_CONST["UEFA"]["home_adv_elo"]


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
                  neutral: bool = False,
                  conf: str = "UEFA") -> tuple[float, float]:
    """Expected goals (lambda_home, lambda_away) from cross-league strengths.

    Args:
        conf: confederation key into _CONF_CONST ("UEFA" or "Concacaf").
              Defaults to "UEFA" so all existing callers are unaffected.
    """
    c = _CONF_CONST.get(conf, _CONF_CONST["UEFA"])
    base_goals   = c["base_goals"]
    goal_scale   = c["goal_scale"]
    home_adv_elo = c["home_adv_elo"]
    ha = 0.0 if neutral else home_adv_elo
    diff = strength_home - strength_away
    # Home advantage is modeled as a home-side boost only (added to the home rate,
    # mirroring ELO's home_adv); the away rate intentionally omits it.
    lam_home = base_goals * 10.0 ** ((diff + ha) / goal_scale)
    lam_away = base_goals * 10.0 ** ((-diff) / goal_scale)
    return lam_home, lam_away


def match_probs(strength_home: float, strength_away: float,
                neutral: bool = False, max_g: int = 10,
                conf: str = "UEFA") -> tuple[float, float, float]:
    """(P_home, P_draw, P_away) via independent Poisson score matrix.

    Args:
        conf: confederation key ("UEFA" or "Concacaf"). Defaults to "UEFA".
    """
    lam_h, lam_a = match_lambdas(strength_home, strength_away, neutral, conf=conf)
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
