"""A10(b): per-sim team-strength perturbations for the season Monte-Carlo.

The season simulator samples outcomes from FIXED per-fixture DC probabilities —
the only stochasticity is the categorical draw and the tie jitter, so preseason
odds are point estimates with no strength uncertainty. This module introduces
per-sim perturbations on a common ELO-point scale:

    δ_t ~ N(0, σ_t)  per team, drawn once per simulated season
    σ_t = σ_base · min(1 + γ·|club_prior_gap_t|/200, 1.5)

Each fixture's home/away log-probs tilt by ±k·(δ_h − δ_a) with
k = ln(10)/800 per side, so a δ-point differential moves the home-vs-away
log-odds by δ·ln(10)/400 — exactly the ELO expectation curve's scale. The
draw logit is left untouched (renormalisation shrinks it slightly as one
side strengthens, which is the right direction for mismatches).

High-gap teams ("fallen giants" whose seed rating disagrees with their own
recent history — A7's `club_prior_gap`) get wider σ: the model is *less sure*
about them, so their finish distribution widens instead of collapsing to a
confident point estimate (the Spurs-42%-relegation failure mode).
"""

from __future__ import annotations

import math

import numpy as np

# Per-side logit tilt per ELO point: home gets +k·d, away −k·d, so the
# home-vs-away log-odds shift is d·ln(10)/400 (the ELO curve's scale).
ELO_LOGIT_K: float = math.log(10.0) / 800.0

SIGMA_CAP: float = 1.5  # max widening multiplier (plan-specified)

# Production preseason σ (A10(b) verdict 2026-07-06): uniform widening only,
# γ=0 — the gap-scaled component was judged on the big-5 FD cohort replay and
# DROPPED (no pooled gain over uniform σ; hurts the high-gap cohort it
# targets). σ=60 ≈ the observed sd of seed→end-of-season ELO drift (62) and
# was the only grid point improving relegation AND top-4 Brier with title
# flat.
#
# Per-family σ (season-outcome sweep 2026-07-07, two-seed confirmed): the
# goals-only/football-data family wants MORE widening — σ=90 improves BOTH
# bottom-table (releg+promo −0.0024) and top-table Brier there, unlike big-5
# where σ>60 trades top for bottom. σ decays with season progress,
# σ_eff = σ·(1−f) (decay confirmed at both seeds: −0.0015 releg at the 25%
# checkpoint, no regression anywhere); preseason-only was the f=0 special case.
PRESEASON_SIGMA: float = 60.0

_SIGMA_BY_SOURCE: dict[str, float] = {
    "understat": 60.0,      # big-5 (A10(b) grid)
    "footballdata": 90.0,   # goals-only tiers + C1 flights (2026-07-07 sweep)
}


def preseason_sigma_for_source(source: str) -> float:
    """Family preseason σ by data source; untested families take the default."""
    return _SIGMA_BY_SOURCE.get(source, PRESEASON_SIGMA)


def gap_sigma_multiplier(gap: float, gamma: float, cap: float = SIGMA_CAP) -> float:
    """Widening multiplier for one team: min(1 + γ·|gap|/200, cap)."""
    return min(cap, 1.0 + gamma * abs(gap) / 200.0)


def team_sigmas(tids: list[str], gaps: dict[str, float], sigma_base: float,
                gamma: float, cap: float = SIGMA_CAP) -> np.ndarray:
    """Per-team perturbation σ aligned with `tids`; missing teams get gap 0."""
    return np.array([sigma_base * gap_sigma_multiplier(gaps.get(t, 0.0), gamma, cap)
                     for t in tids])


def perturb_probs(LP: np.ndarray, RH: np.ndarray, RA: np.ndarray,
                  delta: np.ndarray, k: float = ELO_LOGIT_K) -> np.ndarray:
    """Tilt fixture outcome probs by per-team strength perturbations.

    Args:
        LP:    (F, 3) log of baseline [home, draw, away] probabilities.
        RH/RA: (F,) team indices (into `delta`) for each fixture's sides.
        delta: (T,) per-team perturbations in ELO points.

    Returns:
        (F, 3) renormalised probabilities.
    """
    d = delta[RH] - delta[RA]
    lp = LP.copy()
    lp[:, 0] += k * d
    lp[:, 2] -= k * d
    lp -= lp.max(axis=1, keepdims=True)
    p = np.exp(lp)
    return p / p.sum(axis=1, keepdims=True)
