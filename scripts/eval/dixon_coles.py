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


def fit_dc_dynamic_ha(matches: pd.DataFrame, decay_hl: int = DEFAULT_DC_DECAY_HL,
                      recent_seasons: int = 4, k_grid=(50, 100, 200),
                      cal_matches: pd.DataFrame = None):
    """A4: season-level home-advantage, shrunk toward the pooled estimate.

    Attack/defence/rho are fit once on the pooled recent-seasons window (as
    fit_dc does — static HFA can't track the documented 2024/25 home-win
    collapse). Home advantage is then re-estimated per season with atk/dfd/rho
    held fixed (ha alone makes the NLL a 1-D concave function, cheap to
    optimize), and shrunk toward the pooled ha:
        ha_s = (n_s * ha_hat_s + k * ha_pool) / (n_s + k)
    so a season with few matches leans on the pooled estimate while a
    well-observed season trusts its own data. k is chosen from k_grid by
    DC-only Brier on `cal_matches` (if given), else the grid midpoint.

    Returns (atk, dfd, ha_by_season, ha_pool, rho, k_used). Forward/unseen-
    season prediction should use ha_by_season[max(ha_by_season)] (the latest
    fitted season) — mirrors fit_dc's own single-ha forward convention.
    """
    max_s = matches["season"].max()
    recent = matches[matches["season"] >= max_s - recent_seasons + 1].copy()
    atk, dfd, ha_pool, rho = fit_dc(matches, decay_hl, recent_seasons)
    teams = sorted(set(recent["home_team"]) | set(recent["away_team"]))
    tidx = {t: i for i, t in enumerate(teams)}
    ref = recent["date"].max()
    atk_arr = np.array([atk.get(t, 0.0) for t in teams])
    dfd_arr = np.array([dfd.get(t, 0.0) for t in teams])

    def _season_arr(season_df):
        return np.array([
            [(ref - r["date"]).days, tidx.get(r["home_team"], 0),
             tidx.get(r["away_team"], 0), r["home_goals"], r["away_goals"]]
            for _, r in season_df.iterrows()
        ], dtype=float)

    def _ha_nll(ha_val, arr):
        params = np.concatenate([atk_arr, dfd_arr, [ha_val, rho]])
        return dc_nll(params, teams, arr, decay_hl)

    ha_hat, n_s = {}, {}
    for s, sdf in recent.groupby("season"):
        if len(sdf) < 10:
            continue
        arr = _season_arr(sdf)
        r = minimize(lambda x, _arr=arr: _ha_nll(x[0], _arr), [ha_pool],
                    method="L-BFGS-B", bounds=[(0.0, 1.0)])
        ha_hat[s] = float(r.x[0])
        n_s[s] = len(sdf)

    def _shrink(k):
        return {s: (n_s[s] * ha_hat[s] + k * ha_pool) / (n_s[s] + k) for s in ha_hat}

    if cal_matches is not None and len(cal_matches) > 0 and ha_hat:
        best_k, best_brier = k_grid[len(k_grid) // 2], float("inf")
        for k in k_grid:
            ha_by_season = _shrink(k)
            latest = max(ha_by_season)
            preds, y = [], []
            for _, r in cal_matches.iterrows():
                ha_s = ha_by_season.get(r["season"], ha_by_season[latest])
                preds.append(dc_predict(r["home_team"], r["away_team"], atk, dfd, ha_s, rho))
                y.append(0 if r["home_goals"] > r["away_goals"]
                        else (1 if r["home_goals"] == r["away_goals"] else 2))
            P = np.array(preds)
            yoh = np.eye(3)[y]
            brier = float(np.mean(np.sum((P - yoh) ** 2, axis=1)))
            if brier < best_brier:
                best_brier, best_k = brier, k
    else:
        best_k = k_grid[len(k_grid) // 2]

    ha_by_season = _shrink(best_k) if ha_hat else {}
    return atk, dfd, ha_by_season, ha_pool, rho, best_k


def _ha_for_row(ha_by_season, ha_pool, season):
    """Resolve the shrunk ha for a match's season, falling back to the latest
    fitted season (forward prediction) or the pooled estimate (no fit at all)."""
    if not ha_by_season:
        return ha_pool
    return ha_by_season.get(season, ha_by_season[max(ha_by_season)])


def dc_predict_batch_dynamic_ha(split_df, atk, dfd, ha_by_season, ha_pool, rho):
    """Like dc_predict_batch, but ha varies by each row's season (A4)."""
    return np.array([
        dc_predict(r.home_team, r.away_team, atk, dfd,
                  _ha_for_row(ha_by_season, ha_pool, r.season), rho)
        for _, r in split_df.iterrows()
    ])


def dc_lam_mu_batch_dynamic_ha(split_df, atk, dfd, ha_by_season, ha_pool):
    """Like dc_lam_mu_batch, but ha varies by each row's season (A4)."""
    lams, mus = [], []
    for _, r in split_df.iterrows():
        ha = _ha_for_row(ha_by_season, ha_pool, r["season"])
        lam = math.exp(atk.get(r["home_team"], 0) + dfd.get(r["away_team"], 0) + ha)
        mu = math.exp(atk.get(r["away_team"], 0) + dfd.get(r["home_team"], 0))
        lams.append(lam); mus.append(mu)
    return np.array(lams), np.array(mus)


def dc_draw_prob_batch_dynamic_ha(split_df, atk, dfd, ha_by_season, ha_pool, rho, max_g: int = 8):
    """Like dc_draw_prob_batch, but ha varies by each row's season (A4)."""
    result = []
    for _, r in split_df.iterrows():
        ha = _ha_for_row(ha_by_season, ha_pool, r["season"])
        lam = math.exp(atk.get(r["home_team"], 0) + dfd.get(r["away_team"], 0) + ha)
        mu = math.exp(atk.get(r["away_team"], 0) + dfd.get(r["home_team"], 0))
        p_draw = sum(
            dc_tau(k, k, lam, mu, rho) * poisson.pmf(k, lam) * poisson.pmf(k, mu)
            for k in range(max_g + 1)
        )
        result.append(float(p_draw))
    return np.array(result)


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


def apply_roster_dc_prior(
    atk: dict,
    dfd: dict,
    season: int,
    rd_z: dict,
    hex_to_short: dict,
    alpha: float,
    max_adj: float = 0.25,
) -> tuple:
    """Adjust DC attack/defense parameters using position-split roster value z-scores.

    Called after fit_dc(), before any dc_predict_batch() call:
      atk_adj[team] +=  clip(alpha * new_att_value_z,               -max_adj, +max_adj)
      dfd_adj[team] -=  clip(alpha * (new_def_value_z + new_gk_value_z), -max_adj, +max_adj)

    dfd[team] is defense VULNERABILITY (higher = weaker defense = more goals allowed),
    so a defensive signing DECREASES dfd (fewer goals allowed against the team).

    Returns shallow-copied (atk_adj, dfd_adj). Does not mutate the inputs.
    Lookup falls back to (short, season-1) when current season has no entry.
    """
    atk_adj = dict(atk)
    dfd_adj = dict(dfd)
    for team_id in list(atk.keys()):
        short = hex_to_short.get(team_id, team_id)
        current = rd_z.get((short, season))
        entry = current if current is not None else rd_z.get((short, season - 1))
        if not entry:
            continue
        att_z = entry.get("new_att_value_z", 0.0) or 0.0
        def_z = entry.get("new_def_value_z", 0.0) or 0.0
        gk_z  = entry.get("new_gk_value_z",  0.0) or 0.0
        atk_adj[team_id] += float(np.clip(alpha * att_z,           -max_adj, max_adj))
        dfd_adj[team_id] -= float(np.clip(alpha * (def_z + gk_z),  -max_adj, max_adj))
    return atk_adj, dfd_adj


def fit_dc_dynamic_rho(matches: pd.DataFrame, decay_hl: int = DEFAULT_DC_DECAY_HL,
                       recent_seasons: int = 4, k_grid=(50, 100, 200),
                       cal_matches: pd.DataFrame = None):
    """A11(b): season-level Dixon-Coles low-score correction `rho`, shrunk
    toward the pooled estimate — mirrors A4's `fit_dc_dynamic_ha` shrinkage
    pattern (`rho_s = (n_s*rho_hat_s + k*rho_pool) / (n_s+k)`), but for rho
    instead of home-advantage. rho directly governs the diagonal (draw) mass
    of the score matrix, so a per-season fit lets draw-proneness (e.g. a
    congested-fixture, low-scoring season) move independently of the pooled
    estimate while small seasons still lean on the pool.

    Attack/defence/ha are fit once on the pooled recent-seasons window (as
    fit_dc does); rho alone is then re-estimated per season with atk/dfd/ha
    held fixed (rho makes the NLL a 1-D concave function on its bounded
    interval, cheap to optimize).

    Returns (atk, dfd, ha, rho_by_season, rho_pool, k_used). Forward/unseen-
    season prediction should use rho_by_season[max(rho_by_season)] (the
    latest fitted season) — mirrors fit_dc_dynamic_ha's own forward convention.
    """
    max_s = matches["season"].max()
    recent = matches[matches["season"] >= max_s - recent_seasons + 1].copy()
    atk, dfd, ha, rho_pool = fit_dc(matches, decay_hl, recent_seasons)
    teams = sorted(set(recent["home_team"]) | set(recent["away_team"]))
    tidx = {t: i for i, t in enumerate(teams)}
    ref = recent["date"].max()
    atk_arr = np.array([atk.get(t, 0.0) for t in teams])
    dfd_arr = np.array([dfd.get(t, 0.0) for t in teams])

    def _season_arr(season_df):
        return np.array([
            [(ref - r["date"]).days, tidx.get(r["home_team"], 0),
             tidx.get(r["away_team"], 0), r["home_goals"], r["away_goals"]]
            for _, r in season_df.iterrows()
        ], dtype=float)

    def _rho_nll(rho_val, arr):
        params = np.concatenate([atk_arr, dfd_arr, [ha, rho_val]])
        return dc_nll(params, teams, arr, decay_hl)

    rho_hat, n_s = {}, {}
    for s, sdf in recent.groupby("season"):
        if len(sdf) < 10:
            continue
        arr = _season_arr(sdf)
        r = minimize(lambda x, _arr=arr: _rho_nll(x[0], _arr), [rho_pool],
                    method="L-BFGS-B", bounds=[(-0.5, 0.0)])
        rho_hat[s] = float(r.x[0])
        n_s[s] = len(sdf)

    def _shrink(k):
        return {s: (n_s[s] * rho_hat[s] + k * rho_pool) / (n_s[s] + k) for s in rho_hat}

    if cal_matches is not None and len(cal_matches) > 0 and rho_hat:
        best_k, best_brier = k_grid[len(k_grid) // 2], float("inf")
        for k in k_grid:
            rho_by_season = _shrink(k)
            latest = max(rho_by_season)
            preds, y = [], []
            for _, r in cal_matches.iterrows():
                rho_s = rho_by_season.get(r["season"], rho_by_season[latest])
                preds.append(dc_predict(r["home_team"], r["away_team"], atk, dfd, ha, rho_s))
                y.append(0 if r["home_goals"] > r["away_goals"]
                        else (1 if r["home_goals"] == r["away_goals"] else 2))
            P = np.array(preds)
            yoh = np.eye(3)[y]
            brier = float(np.mean(np.sum((P - yoh) ** 2, axis=1)))
            if brier < best_brier:
                best_brier, best_k = brier, k
    else:
        best_k = k_grid[len(k_grid) // 2]

    rho_by_season = _shrink(best_k) if rho_hat else {}
    return atk, dfd, ha, rho_by_season, rho_pool, best_k


def _rho_for_row(rho_by_season, rho_pool, season):
    """Resolve the shrunk rho for a match's season, falling back to the latest
    fitted season (forward prediction) or the pooled estimate (no fit at all)."""
    if not rho_by_season:
        return rho_pool
    return rho_by_season.get(season, rho_by_season[max(rho_by_season)])


def dc_predict_batch_dynamic_rho(split_df, atk, dfd, ha, rho_by_season, rho_pool):
    """Like dc_predict_batch, but rho varies by each row's season (A11b)."""
    return np.array([
        dc_predict(r.home_team, r.away_team, atk, dfd, ha,
                  _rho_for_row(rho_by_season, rho_pool, r.season))
        for _, r in split_df.iterrows()
    ])


def dc_lam_mu_batch_dynamic_rho(split_df, atk, dfd, ha):
    """lam/mu don't depend on rho, so this is identical to dc_lam_mu_batch —
    provided for call-site symmetry with the dynamic-ha helpers (A11b)."""
    return dc_lam_mu_batch(split_df, atk, dfd, ha)


def dc_draw_prob_batch_dynamic_rho(split_df, atk, dfd, ha, rho_by_season, rho_pool, max_g: int = 8):
    """Like dc_draw_prob_batch, but rho varies by each row's season (A11b)."""
    result = []
    for _, r in split_df.iterrows():
        rho = _rho_for_row(rho_by_season, rho_pool, r["season"])
        lam = math.exp(atk.get(r["home_team"], 0) + dfd.get(r["away_team"], 0) + ha)
        mu = math.exp(atk.get(r["away_team"], 0) + dfd.get(r["home_team"], 0))
        p_draw = sum(
            dc_tau(k, k, lam, mu, rho) * poisson.pmf(k, lam) * poisson.pmf(k, mu)
            for k in range(max_g + 1)
        )
        result.append(float(p_draw))
    return np.array(result)
