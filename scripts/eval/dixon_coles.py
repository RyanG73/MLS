"""
Dixon-Coles Poisson goal model — pure engine extracted from eval_baseline.py (F4).

These functions are purely functional (no module-level state): fit returns
attack/defence/home-advantage/rho parameters; predict turns them into 1X2
probabilities. Time-decay weighting is applied during the NLL fit.

Behavior-preserving extraction — verified by `eval_baseline.py --smoke-test`.
"""

import math

import numpy as np
import pandas as pd
from scipy.stats import poisson
from scipy.special import gammaln
from scipy.optimize import minimize

# Default time-decay half-life (days). Callers in the harness pass this
# explicitly from the validated config; the default mirrors the project value.
DEFAULT_DC_DECAY_HL = 120


def dc_tau(x, y, lam, mu, rho):
    """Dixon-Coles low-score dependency correction factor."""
    if x == 0 and y == 0: return 1 - lam * mu * rho
    if x == 0 and y == 1: return 1 + lam * rho
    if x == 1 and y == 0: return 1 + mu * rho
    if x == 1 and y == 1: return 1 - rho
    return 1.0


def dc_nll(params, teams, arr, decay_hl):
    """Time-decayed negative log-likelihood for the Dixon-Coles model.

    Vectorized over `arr` (numerically identical to the prior per-row loop, to
    ~1e-12): the per-match `scipy.stats.poisson.logpmf` scalar calls — millions
    of them across an L-BFGS fit — were the dominant cost. Here the Poisson term
    is the closed form ``k·ln(λ) − λ − lgamma(k+1)`` (`scipy.special.gammaln`
    vectorizes the log-factorial), and the four Dixon-Coles low-score τ cases are
    applied by boolean masks. ~500× faster per call than the loop.
    """
    n = len(teams)
    p = np.asarray(params, dtype=float)
    atk, dfd = p[:n], p[n:2*n]
    ha, rho = p[2*n], p[2*n + 1]
    lam_d = math.log(2) / decay_hl

    days_ago = arr[:, 0]
    hi = arr[:, 1].astype(int)
    ai = arr[:, 2].astype(int)
    hg = arr[:, 3]
    ag = arr[:, 4]

    w = np.exp(-lam_d * days_ago)
    lam = np.exp(atk[hi] + dfd[ai] + ha)
    mu  = np.exp(atk[ai] + dfd[hi])

    # Dixon-Coles low-score correction (the four special scorelines; 1.0 elsewhere)
    tau = np.ones_like(lam)
    m00 = (hg == 0) & (ag == 0); tau[m00] = 1 - lam[m00] * mu[m00] * rho
    m01 = (hg == 0) & (ag == 1); tau[m01] = 1 + lam[m01] * rho
    m10 = (hg == 1) & (ag == 0); tau[m10] = 1 + mu[m10] * rho
    m11 = (hg == 1) & (ag == 1); tau[m11] = 1 - rho

    # poisson.logpmf(k, m) == k*ln(m) - m - lgamma(k+1)
    log_ph = hg * np.log(lam) - lam - gammaln(hg + 1)
    log_pa = ag * np.log(mu)  - mu  - gammaln(ag + 1)

    # Match the prior loop's `if tau <= 1e-10: continue` (skip degenerate rows)
    valid = tau > 1e-10
    contrib = w * (np.log(np.where(valid, tau, 1.0)) + log_ph + log_pa)
    return -float(contrib[valid].sum())


def fit_dc(matches: pd.DataFrame, decay_hl: int = DEFAULT_DC_DECAY_HL, recent_seasons: int = 4):
    """Fit Dixon-Coles on the most recent `recent_seasons` seasons of `matches`.

    Returns (atk, dfd, home_advantage, rho) where atk/dfd are {team: param} dicts.
    """
    max_s = matches["season"].max()
    recent = matches[matches["season"] >= max_s - recent_seasons + 1].copy()
    teams = sorted(set(recent["home_team"]) | set(recent["away_team"]))
    tidx = {t: i for i, t in enumerate(teams)}
    n = len(teams)
    ref = recent["date"].max()
    arr = np.array([
        [(ref - r["date"]).days, tidx.get(r["home_team"], 0),
         tidx.get(r["away_team"], 0), r["home_goals"], r["away_goals"]]
        for _, r in recent.iterrows()
    ], dtype=float)
    x0 = np.zeros(2 * n + 2)
    x0[2*n], x0[2*n+1] = 0.25, -0.05
    bounds = [(-3, 3)] * (2*n) + [(0.0, 1.0)] + [(-0.5, 0.0)]
    res = minimize(dc_nll, x0, args=(teams, arr, decay_hl),
                   method="L-BFGS-B", bounds=bounds,
                   options={"maxiter": 300, "ftol": 1e-7})
    atk = dict(zip(teams, res.x[:n]))
    dfd = dict(zip(teams, res.x[n:2*n]))
    return atk, dfd, res.x[2*n], res.x[2*n+1]


def dc_predict(ht, at, atk, dfd, ha, rho, max_g=8):
    """Predict (P_home, P_draw, P_away) for a single fixture."""
    lam = math.exp(atk.get(ht, 0) + dfd.get(at, 0) + ha)
    mu  = math.exp(atk.get(at, 0) + dfd.get(ht, 0))
    M = np.zeros((max_g + 1, max_g + 1))
    for i in range(max_g + 1):
        for j in range(max_g + 1):
            tau = dc_tau(i, j, lam, mu, rho)
            M[i, j] = max(tau, 1e-10) * poisson.pmf(i, lam) * poisson.pmf(j, mu)
    M = np.clip(M, 1e-15, None)
    M /= M.sum()
    ph = float(np.tril(M, -1).sum())
    pd_ = float(np.diag(M).sum())
    pa = float(np.triu(M, 1).sum())
    t = ph + pd_ + pa
    return ph / t, pd_ / t, pa / t


def dc_predict_batch(split_df, atk, dfd, ha, rho):
    """Vectorized dc_predict over a fixtures DataFrame → (n, 3) array."""
    return np.array([dc_predict(r.home_team, r.away_team, atk, dfd, ha, rho)
                     for _, r in split_df.iterrows()])


def dc_lam_mu_batch(split_df, atk, dfd, ha):
    """Return (lambda, mu) Poisson means per fixture (DC feature columns)."""
    lams, mus = [], []
    for _, r in split_df.iterrows():
        lam = math.exp(atk.get(r["home_team"], 0) + dfd.get(r["away_team"], 0) + ha)
        mu  = math.exp(atk.get(r["away_team"], 0) + dfd.get(r["home_team"], 0))
        lams.append(lam); mus.append(mu)
    return np.array(lams), np.array(mus)


def dc_draw_prob_batch(split_df, atk, dfd, ha, rho, max_g: int = 8) -> np.ndarray:
    """DC-predicted draw probability for each fixture (unnormalised diagonal sum).

    Computes sum_{k=0}^{max_g} tau(k,k,lam,mu,rho) * P(k|lam) * P(k|mu).
    This is faster than the full dc_predict (O(max_g) per row vs O(max_g²)) and
    returns the draw component before normalisation — suitable as an XGB feature.
    """
    result = []
    for _, r in split_df.iterrows():
        lam = math.exp(atk.get(r["home_team"], 0) + dfd.get(r["away_team"], 0) + ha)
        mu  = math.exp(atk.get(r["away_team"], 0) + dfd.get(r["home_team"], 0))
        p_draw = sum(
            dc_tau(k, k, lam, mu, rho) * poisson.pmf(k, lam) * poisson.pmf(k, mu)
            for k in range(max_g + 1)
        )
        result.append(float(p_draw))
    return np.array(result)
