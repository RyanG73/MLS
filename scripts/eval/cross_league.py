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
# (ELO-wired backtest).
#
# Hard bounds: base_goals 1.2–1.7, home_adv_elo 40–130, goal_scale 800–3500.
# The goal_scale floor was 2000 until 2026-08-06 and it was never justified —
# every confederation calibrated against it sat at or near the floor, which is
# what a binding constraint looks like. UEFA's own fit wanted ~1000 and beat the
# floor value by 0.03 held-out Brier. What actually needs bounding is the
# SCORELINE, since bracket_sim samples goals from these lambdas, so the real
# constraint is on lambdas for an even tie (home 1.35–1.70, total 2.60–2.95) and
# it is asserted directly in tests/test_bracket_sim.py.
_CONF_CONST: dict[str, dict[str, float]] = {
    # UEFA: CALIBRATED 2026-08-06 on the 743 cross-league continental matches,
    # offsets refit at every grid point, scored on mean held-out 1X2 Brier over
    # the same 10 seeds the bridge's robustness gate uses.
    #
    #   was 1.35 / 3000 / 80   Brier 0.6006   home .395 draw .247 away .358
    #   now 1.25 / 1000 / 110  Brier 0.5708   home .478 draw .209 away .313
    #   actual over 743                       home .503 draw .182 away .315
    #
    # These were the only confederation constants never fitted — the note they
    # replace called them "physically-grounded priors", and Concacaf/CONMEBOL/AFC
    # were all grid-swept while UEFA kept its typed guess. The guess was wrong in
    # a way that mattered: at goal_scale 3000 a 300-ELO gap is only a 1.26x goal
    # rate, so the model could not express dominance and predicted 39.5% home
    # wins against an actual 50.3%. On 743 matches that is a ~6-sigma miss, not
    # noise.
    #
    # It also explains the ladder complaint that started this. A model that
    # under-predicts strong clubs has to put the missing strength SOMEWHERE, and
    # the only free parameters are the league offsets — so leagues whose European
    # entrants win a lot got inflated. Ligue 1 sat at -18 against a -81 prior,
    # which put Lens 10th in the world. The EPL, being the anchor at 0, could not
    # inflate and simply kept the largest residual of any league (+0.43 points
    # per appearance), which is the same miss with nowhere to go. Recalibrated,
    # Ligue 1 lands at -64 without anyone touching it.
    #
    # Constrained, not just optimised: bracket_sim draws real scorelines from
    # these lambdas, so the grid was restricted to points where an even, non-
    # neutral tie yields home 1.35-1.70 and 2.60-2.95 total goals. 1.25/1000/110
    # gives 1.61 + 1.25 = 2.86. Unconstrained the Brier optimum keeps going to
    # goal_scale ~900 for another 0.002, which is inside the noise on 743 matches
    # and not worth an unphysical scoreline model.
    "UEFA": {
        "base_goals": 1.25,
        "goal_scale": 1000.0,
        "home_adv_elo": 110.0,
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
    # CONMEBOL (2026-07-24). Calibrated by scripts/eval/continental_calibrate.py
    # over 2922 cross-league Libertadores+Sudamericana matches (2015-2026):
    # ridge sweep → constants grid (48 points, offsets refit at each) → scored on
    # a 584-match holdout that neither stage saw. Result there: 0.5834 fitted vs
    # 0.6264 prior vs 0.6102 naive base-rate — it beats BOTH, which neither
    # Concacaf comp manages (see the note above). goal_scale lands at 2000 rather
    # than UEFA's 3000: CONMEBOL's continental record is lower-scoring (2.43 g/g
    # vs UCL's 3.18) and drawier, and the tighter scale makes ELO gaps bite
    # harder, which is what fits a confederation with a genuinely wide spread
    # between its strongest and weakest leagues.
    "CONMEBOL": {
        "base_goals": 1.25,
        "goal_scale": 2000.0,
        "home_adv_elo": 100.0,
    },
    # AFC (2026-07-24) — PRESENT BUT NOT SHIPPED. Same calibration procedure;
    # the AFC Champions League is NOT built (see build_continental_data.META).
    # Two independent reasons, either fatal on its own:
    #   1. On the untouched 76-match holdout the fit beats the prior (-0.0311)
    #      but LOSES to a naive base-rate predictor (+0.0020). CONMEBOL clears
    #      the same bar comfortably; this does not.
    #   2. Only 54% of the AFC Champions League Elite field resolves to a modeled
    #      league. The competition splits into West and East regions, and every
    #      West Asian league (Qatar, UAE, Iran, Uzbekistan, Iraq) is absent from
    #      ESPN's catalog entirely, so half the field would sit on a flat
    #      baseline. saudi-pro's own offset rests on just 13 inter-regional
    #      matches — West and East only meet in the final.
    # Kept here so the numbers are recorded rather than lost, and so re-running
    # the calibrator after a paid West-Asian source lands is a one-line change.
    "AFC": {
        "base_goals": 1.35,
        "goal_scale": 3500.0,
        "home_adv_elo": 100.0,
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
