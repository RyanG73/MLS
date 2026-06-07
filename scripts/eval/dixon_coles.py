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
    """Time-decayed negative log-likelihood for the Dixon-Coles model."""
    n = len(teams)
    atk, dfd = params[:n], params[n:2*n]
    ha, rho = params[2*n], params[2*n + 1]
    lam_d = math.log(2) / decay_hl
    ll = 0.0
    for row in arr:
        days_ago = int(row[0])
        hi, ai, hg, ag = int(row[1]), int(row[2]), int(row[3]), int(row[4])
        w = math.exp(-lam_d * days_ago)
        lam = math.exp(atk[hi] + dfd[ai] + ha)
        mu  = math.exp(atk[ai] + dfd[hi])
        tau = dc_tau(hg, ag, lam, mu, rho)
        if tau <= 1e-10:
            continue
        ll += w * (math.log(tau) + poisson.logpmf(hg, lam) + poisson.logpmf(ag, mu))
    return -ll


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
