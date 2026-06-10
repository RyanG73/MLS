#!/usr/bin/env python3
"""
Shared, validated 1X2 model — faithful port of the research-harness pipeline that
produced best_brier 0.6363 (Dixon-Coles + season-weighted XGBoost grid + temperature
calibration + capped-DC convex blend). DataFrame-in, no database, no O/U.

This is the single validated implementation intended for BOTH local validation
(scripts/parity_check.py) and the production pipeline (replacing the divergent
GradientBoostModels/StackingEnsemble model logic). The Pi sees only DB read/write IO.

Validated config (CLAUDE.md / Phase 8-10): DC decay 120d, XGB season weight_hl 6,
temperature calibration, capped-DC blend with DC contribution <= 30% (w_xgb in [0.7,1.0]).
"""

import itertools
import logging
import math

import numpy as np
import pandas as pd
from scipy.optimize import minimize, minimize_scalar
from scipy.stats import poisson
from sklearn.metrics import log_loss
from models.metrics import brier_multiclass_sum, per_class_brier, log_loss_multiclass
import xgboost as xgb

_logger = logging.getLogger(__name__)

DEFAULT_DC_DECAY_HL = 120
DEFAULT_WEIGHT_HL = 6
DEFAULT_XGB_NJOBS = 2
# Champion config since the 2026-06-10 promotion (challenger-bag5, user override):
# 5-member XGB seed bag, narrow grid. wide_grid stays opt-in (gate-rejected on
# calibration). Set n_bags=1 to reproduce the pre-bagging champion exactly.
DEFAULT_N_BAGS = 5


# ─── Dixon-Coles ──────────────────────────────────────────────────────────────

def _dc_tau(x, y, lam, mu, rho):
    if x == 0 and y == 0: return 1 - lam * mu * rho
    if x == 0 and y == 1: return 1 + lam * rho
    if x == 1 and y == 0: return 1 + mu * rho
    if x == 1 and y == 1: return 1 - rho
    return 1.0


def _dc_nll(params, teams, arr, decay_hl):
    n = len(teams)
    atk, dfd = params[:n], params[n:2 * n]
    ha, rho = params[2 * n], params[2 * n + 1]
    lam_d = math.log(2) / decay_hl
    ll = 0.0
    for row in arr:
        days_ago = int(row[0]); hi, ai = int(row[1]), int(row[2])
        hg, ag = int(row[3]), int(row[4])
        w = math.exp(-lam_d * days_ago)
        lam = math.exp(atk[hi] + dfd[ai] + ha)
        mu = math.exp(atk[ai] + dfd[hi])
        tau = _dc_tau(hg, ag, lam, mu, rho)
        if tau <= 1e-10:
            continue
        ll += w * (math.log(tau) + poisson.logpmf(hg, lam) + poisson.logpmf(ag, mu))
    return -ll


def fit_dc(matches, decay_hl=DEFAULT_DC_DECAY_HL, recent_seasons=4):
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
    x0[2 * n], x0[2 * n + 1] = 0.25, -0.05
    bounds = [(-3, 3)] * (2 * n) + [(0.0, 1.0)] + [(-0.5, 0.0)]
    res = minimize(_dc_nll, x0, args=(teams, arr, decay_hl),
                   method="L-BFGS-B", bounds=bounds,
                   options={"maxiter": 300, "ftol": 1e-7})
    atk = dict(zip(teams, res.x[:n]))
    dfd = dict(zip(teams, res.x[n:2 * n]))
    return atk, dfd, res.x[2 * n], res.x[2 * n + 1]


def _dc_predict(ht, at, atk, dfd, ha, rho, max_g=8):
    lam = math.exp(atk.get(ht, 0) + dfd.get(at, 0) + ha)
    mu = math.exp(atk.get(at, 0) + dfd.get(ht, 0))
    M = np.zeros((max_g + 1, max_g + 1))
    for i in range(max_g + 1):
        for j in range(max_g + 1):
            M[i, j] = max(_dc_tau(i, j, lam, mu, rho), 1e-10) * \
                poisson.pmf(i, lam) * poisson.pmf(j, mu)
    M = np.clip(M, 1e-15, None)
    M /= M.sum()
    ph = float(np.tril(M, -1).sum())
    pdr = float(np.diag(M).sum())
    pa = float(np.triu(M, 1).sum())
    t = ph + pdr + pa
    return ph / t, pdr / t, pa / t


def dc_predict_batch(split_df, atk, dfd, ha, rho):
    return np.array([_dc_predict(r.home_team, r.away_team, atk, dfd, ha, rho)
                     for _, r in split_df.iterrows()])


# ─── Temperature calibration ──────────────────────────────────────────────────

def calibrate_temperature(raw_cal, y_cal, raw_test):
    def _nll(T):
        log_p = np.log(np.clip(raw_cal, 1e-9, 1.0)) / max(T, 0.1)
        log_p -= log_p.max(axis=1, keepdims=True)
        ep = np.exp(log_p)
        return float(log_loss(y_cal, ep / ep.sum(axis=1, keepdims=True)))
    T = minimize_scalar(_nll, bounds=(0.3, 5.0), method="bounded").x
    log_p = np.log(np.clip(raw_test, 1e-9, 1.0)) / T
    log_p -= log_p.max(axis=1, keepdims=True)
    ep = np.exp(log_p)
    return ep / ep.sum(axis=1, keepdims=True)


def multiclass_brier(y_oh, probs):
    """Alias for brier_multiclass_sum (sum-form, canonical for this project)."""
    return brier_multiclass_sum(probs, y_oh)


# ─── XGBoost (season-weighted, inner grid) ────────────────────────────────────

def _season_weights(seasons, ref_s, weight_hl):
    return seasons.apply(lambda s: math.exp(-math.log(2) / weight_hl * (ref_s - s))).values


def fit_xgb(train, feat, weight_hl=DEFAULT_WEIGHT_HL, n_jobs=DEFAULT_XGB_NJOBS, seed=42,
            wide_grid=False, n_bags=1):
    """Inner-grid-tuned, season-weighted XGB multiclass on `feat`.

    wide_grid: sweep min_child_weight {1,5} × reg_lambda {1,5} in the inner grid
               (12 → 48 combos; single values below are XGBoost defaults so
               wide_grid=False behaves exactly as before).
    n_bags:    fit N models at seeds (seed + 1000·i) and average raw probabilities
               downstream (variance reduction; harness-validated 2026-06-09).
    Returns (clfs, best_p) where clfs is a LIST of fitted classifiers — use
    bag_proba(clfs, X) for predictions.
    """
    ref_s = train["season"].max()
    sw = _season_weights(train["season"], ref_s, weight_hl)
    inner_s = sorted(train["season"].unique())[-2:]
    itr, ival = train[~train["season"].isin(inner_s)], train[train["season"].isin(inner_s)]
    sw_i = _season_weights(itr["season"], ref_s, weight_hl)
    best_b = float("inf")
    best_p = {"max_depth": 4, "n_estimators": 300, "learning_rate": 0.05,
              "min_child_weight": 1, "reg_lambda": 1.0}
    mcw_axis = [1, 5] if wide_grid else [1]
    rl_axis = [1.0, 5.0] if wide_grid else [1.0]
    if len(ival) >= 30:
        for md, ne, lr, mcw, rl in itertools.product(
                [3, 4, 5], [200, 400], [0.05, 0.10], mcw_axis, rl_axis):
            try:
                c = xgb.XGBClassifier(n_estimators=ne, max_depth=md, learning_rate=lr,
                                      min_child_weight=mcw, reg_lambda=rl,
                                      subsample=0.8, colsample_bytree=0.8,
                                      objective="multi:softprob", num_class=3,
                                      eval_metric="mlogloss", verbosity=0,
                                      random_state=seed, n_jobs=n_jobs)
                c.fit(itr[feat].fillna(0).values, itr["label_result"].values, sample_weight=sw_i)
                ip = c.predict_proba(ival[feat].fillna(0).values)
                b = multiclass_brier(np.eye(3)[ival["label_result"].values], ip)
                if b < best_b:
                    best_b = b
                    best_p = {"max_depth": md, "n_estimators": ne, "learning_rate": lr,
                              "min_child_weight": mcw, "reg_lambda": rl}
            except Exception:
                pass
    clfs = []
    for bi in range(max(1, int(n_bags))):
        clf = xgb.XGBClassifier(objective="multi:softprob", num_class=3,
                                eval_metric="mlogloss", verbosity=0,
                                random_state=seed + 1000 * bi,
                                subsample=0.8, colsample_bytree=0.8, n_jobs=n_jobs,
                                **best_p)
        clf.fit(train[feat].fillna(0).values, train["label_result"].values, sample_weight=sw)
        clfs.append(clf)
    return clfs, best_p


def bag_proba(clfs, X):
    """Average raw predict_proba over bag members (len-1 bags are a no-op)."""
    return np.mean([c.predict_proba(X) for c in clfs], axis=0)


# ─── Capped-DC convex blend ───────────────────────────────────────────────────

def fit_capped_blend(xgb_cal3, dc_cal3, y_cal_oh, w_min=0.7, w_max=1.0):
    """Scalar w (XGB weight, DC <= 1-w_min) fit on the cal fold by Brier minimisation."""
    def _bl(w_arr):
        w = w_arr[0]
        b = w * xgb_cal3 + (1.0 - w) * dc_cal3
        b = b / b.sum(axis=1, keepdims=True).clip(1e-9, None)
        return multiclass_brier(y_cal_oh, b)
    res = minimize(_bl, x0=[0.85], bounds=[(w_min, w_max)], method="L-BFGS-B")
    return float(np.clip(res.x[0], w_min, w_max))


def blend(xg, dc, w):
    b = w * xg + (1.0 - w) * dc
    return b / b.sum(axis=1, keepdims=True).clip(1e-9, None)


# ─── End-to-end walk-forward (the validated 0.6363 pipeline) ──────────────────

def walk_forward_predictions(df, feat_base, test_seasons, weight_hl=DEFAULT_WEIGHT_HL,
                             dc_decay_hl=DEFAULT_DC_DECAY_HL, n_jobs=DEFAULT_XGB_NJOBS,
                             seed=42, wide_grid=False, n_bags=DEFAULT_N_BAGS):
    """
    Run the validated walk-forward pipeline and return PER-MATCH predictions for the
    test seasons (for slicing / reporting). Same computation as walk_forward — the
    latter aggregates this. Returns (preds_df, w_used) where preds_df has columns:
    match_id, season, date, home_team, away_team, label_result,
    prob_home, prob_draw, prob_away, w_xgb.
    """
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"])
    feat = [c for c in feat_base if c in df.columns]
    chunks, w_used = [], {}
    for ts in test_seasons:
        cal_s = ts - 1
        train = df[df["season"] < cal_s].dropna(subset=["home_goals", "away_goals"])
        cal = df[df["season"] == cal_s].dropna(subset=["home_goals", "away_goals"])
        test = df[df["season"] == ts].dropna(subset=["home_goals", "away_goals"])
        if len(train) < 200 or len(cal) < 50 or len(test) < 50:
            continue
        y_cal = cal["label_result"].values.astype(int)
        y_cal_oh = np.eye(3)[y_cal]

        atk, dfd, ha, rho = fit_dc(train, decay_hl=dc_decay_hl)
        dc_cal = calibrate_temperature(dc_predict_batch(cal, atk, dfd, ha, rho), y_cal,
                                       dc_predict_batch(cal, atk, dfd, ha, rho))
        dc_te = calibrate_temperature(dc_predict_batch(cal, atk, dfd, ha, rho), y_cal,
                                      dc_predict_batch(test, atk, dfd, ha, rho))

        clfs, _ = fit_xgb(train, feat, weight_hl=weight_hl, n_jobs=n_jobs, seed=seed,
                          wide_grid=wide_grid, n_bags=n_bags)
        xgb_cal_raw = bag_proba(clfs, cal[feat].fillna(0).values)
        xgb_te_raw = bag_proba(clfs, test[feat].fillna(0).values)
        xgb_cal = calibrate_temperature(xgb_cal_raw, y_cal, xgb_cal_raw)
        xgb_te = calibrate_temperature(xgb_cal_raw, y_cal, xgb_te_raw)

        w = fit_capped_blend(xgb_cal, dc_cal, y_cal_oh)
        # Second-pass temperature calibration on the BLEND output. The per-component
        # temperature scaling above leaves the convex blend itself uncalibrated
        # (root cause of cal_err 0.1326); calibrating the blend recovers it.
        cal_blend = blend(xgb_cal, dc_cal, w)
        te_blend = blend(xgb_te, dc_te, w)
        ens_te = calibrate_temperature(cal_blend, y_cal, te_blend)

        chunk = test[["match_id", "season", "date", "home_team", "away_team",
                      "label_result"]].copy().reset_index(drop=True)
        chunk["prob_home"] = ens_te[:, 0]
        chunk["prob_draw"] = ens_te[:, 1]
        chunk["prob_away"] = ens_te[:, 2]
        chunk["w_xgb"] = round(w, 3)
        chunks.append(chunk)
        w_used[str(ts)] = round(w, 3)

    preds = pd.concat(chunks, ignore_index=True) if chunks else pd.DataFrame()
    return preds, w_used


def walk_forward(df, feat_base, test_seasons, weight_hl=DEFAULT_WEIGHT_HL,
                 dc_decay_hl=DEFAULT_DC_DECAY_HL, n_jobs=DEFAULT_XGB_NJOBS, seed=42,
                 wide_grid=False, n_bags=DEFAULT_N_BAGS):
    """Returns {'per_season': {yr: brier}, 'avg_brier': float, 'w_xgb': {yr: w}}."""
    preds, w_used = walk_forward_predictions(
        df, feat_base, test_seasons, weight_hl=weight_hl,
        dc_decay_hl=dc_decay_hl, n_jobs=n_jobs, seed=seed,
        wide_grid=wide_grid, n_bags=n_bags)
    per_season = {}
    if not preds.empty:
        for ts, g in preds.groupby("season"):
            y_oh = np.eye(3)[g["label_result"].values.astype(int)]
            p = g[["prob_home", "prob_draw", "prob_away"]].values
            per_season[str(int(ts))] = round(multiclass_brier(y_oh, p), 6)
    avg = round(float(np.mean(list(per_season.values()))), 6) if per_season else float("nan")
    return {"per_season": per_season, "avg_brier": avg, "w_xgb": w_used}


# ─── Production inference ─────────────────────────────────────────────────────

# Feature columns to exclude when selecting numeric predictors
_FEAT_EXCLUDE = frozenset({
    "match_id", "date", "home_team", "away_team", "home_goals", "away_goals",
    "total_goals", "label_result", "label_over25", "season",
    "conference_h", "conference_a", "ref_is_known",
})


def predict_upcoming(
    train_df: pd.DataFrame,
    upcoming_df: pd.DataFrame,
    current_season: int,
    weight_hl: int = DEFAULT_WEIGHT_HL,
    dc_decay_hl: int = DEFAULT_DC_DECAY_HL,
    n_jobs: int = DEFAULT_XGB_NJOBS,
    seed: int = 42,
    wide_grid: bool = False,
    n_bags: int = DEFAULT_N_BAGS,
) -> pd.DataFrame:
    """
    Fit the validated research pipeline on train_df and predict upcoming matches.

    Pipeline mirrors the walk-forward logic validated at Brier 0.6347:
    train < cal_season < current_season; DC decay 120d; XGB season-weighted;
    temperature calibration on blend output; capped-DC blend (w_xgb in [0.7,1.0]).

    Args:
        train_df:       Historical feature matrix (build_training_dataset output).
                        Must have season, date, home_team, away_team, home_goals,
                        away_goals, label_result.
        upcoming_df:    Feature rows for upcoming matches (build_upcoming_features
                        output). Must have match_id, home_team, away_team and the
                        same feature columns as train_df.
        current_season: The in-progress season. Cal fold = current_season - 1.

    Returns:
        DataFrame with columns: match_id, prob_home, prob_draw, prob_away, w_xgb.
        Returns empty DataFrame if upcoming_df is None or empty.
    """
    _empty = pd.DataFrame(columns=["match_id", "prob_home", "prob_draw", "prob_away", "w_xgb"])

    if upcoming_df is None or upcoming_df.empty:
        return _empty

    train_df = train_df.copy()
    train_df["date"] = pd.to_datetime(train_df["date"])
    upcoming_df = upcoming_df.reset_index(drop=True)

    cal_season = current_season - 1
    hist = train_df[train_df["season"] < current_season].dropna(
        subset=["home_goals", "away_goals"]
    )
    train = hist[hist["season"] < cal_season]
    cal = hist[hist["season"] == cal_season]

    # DC-only fallback when there is not enough data for the full pipeline
    if len(train) < 200 or len(cal) < 50:
        _logger.warning(
            "predict_upcoming: insufficient train (%d) or cal (%d) rows; using DC-only.",
            len(train), len(cal),
        )
        fit_data = hist if len(hist) >= 100 else train_df.dropna(subset=["home_goals", "away_goals"])
        atk, dfd, ha, rho = fit_dc(fit_data, decay_hl=dc_decay_hl)
        rows = []
        for _, r in upcoming_df.iterrows():
            ph, pd_, pa = _dc_predict(r["home_team"], r["away_team"], atk, dfd, ha, rho)
            rows.append({"match_id": r["match_id"], "prob_home": ph, "prob_draw": pd_,
                         "prob_away": pa, "w_xgb": 1.0})
        return pd.DataFrame(rows)

    # Feature columns: intersection of train and upcoming, excluding metadata
    feat = [
        c for c in train.columns
        if c not in _FEAT_EXCLUDE and not c.startswith("_") and c in upcoming_df.columns
    ]

    y_cal = cal["label_result"].values.astype(int)
    y_cal_oh = np.eye(3)[y_cal]

    # Dixon-Coles on pre-cal training data
    atk, dfd, ha, rho = fit_dc(train, decay_hl=dc_decay_hl)
    dc_cal_raw = dc_predict_batch(cal, atk, dfd, ha, rho)
    dc_up_raw = dc_predict_batch(upcoming_df, atk, dfd, ha, rho)
    dc_cal_t = calibrate_temperature(dc_cal_raw, y_cal, dc_cal_raw)
    dc_up_t = calibrate_temperature(dc_cal_raw, y_cal, dc_up_raw)

    # XGBoost on pre-cal training data
    clfs, _ = fit_xgb(train, feat, weight_hl=weight_hl, n_jobs=n_jobs, seed=seed,
                      wide_grid=wide_grid, n_bags=n_bags)
    xgb_cal_raw = bag_proba(clfs, cal[feat].fillna(0).values)
    xgb_up_raw = bag_proba(clfs, upcoming_df[feat].fillna(0).values)
    xgb_cal_t = calibrate_temperature(xgb_cal_raw, y_cal, xgb_cal_raw)
    xgb_up_t = calibrate_temperature(xgb_cal_raw, y_cal, xgb_up_raw)

    # Capped-DC blend weight (fitted on cal fold)
    w = fit_capped_blend(xgb_cal_t, dc_cal_t, y_cal_oh)

    # Second-pass temperature calibration on the BLEND output (matches walk_forward).
    cal_blend = blend(xgb_cal_t, dc_cal_t, w)
    up_blend = blend(xgb_up_t, dc_up_t, w)
    ens_final = calibrate_temperature(cal_blend, y_cal, up_blend)

    results = []
    for i, row in upcoming_df.iterrows():
        results.append({
            "match_id": row["match_id"],
            "prob_home": float(ens_final[i, 0]),
            "prob_draw": float(ens_final[i, 1]),
            "prob_away": float(ens_final[i, 2]),
            "w_xgb": round(float(w), 3),
        })
    return pd.DataFrame(results)
