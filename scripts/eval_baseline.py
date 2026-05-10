#!/usr/bin/env python3
"""
Standalone model evaluation — no database required.

Pulls real MLS match data from ASA API, builds minimal features,
trains Dixon-Coles + XGBoost/LightGBM, and evaluates on held-out seasons
using walk-forward (no future leakage).

Evaluation structure (3-way split):
  train   → seasons < cal_season       (model fitting)
  cal     → cal_season = test_season-1 (Platt calibration + meta-learner)
  test    → test_season                (final held-out evaluation)

Changes vs v1:
  - Data: 2017+ only, COVID seasons (2020/2021) excluded, 2025 in training
  - ELO: grid search K∈[20,25,30] × HOME_ADV∈[80,100,120], REGRESS 30%→40%
  - Rolling: two xG windows (5,15), rolling draw rate (10), home_xg_sum
  - DC: time-decay half-life 180→120 days; λ/μ exported as XGB features
  - Calibration: isotonic → Platt scaling (LogisticRegression per class)
  - XGBoost: hyperparameter grid search, exponential season sample weights
  - A/B test: per-feature Brier delta for draw_rate and DC params
"""

import math
import itertools
import warnings

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.stats import poisson
from sklearn.metrics import log_loss, brier_score_loss
from sklearn.linear_model import LogisticRegression
import xgboost as xgb
import lightgbm as lgb

warnings.filterwarnings("ignore")

# ─── Constants ────────────────────────────────────────────────────────────────

XG_WINDOWS    = (5, 15)
FORM_WINDOW   = 5
DRAW_WINDOW   = 10
REGRESS       = 0.40
INITIAL_ELO   = 1500.0
DC_DECAY_HL   = 120
TEST_SEASONS  = [2022, 2023, 2024]
_COVID        = {2020, 2021}
WEIGHT_HL     = 4       # exponential season decay half-life in seasons

# ─── 1. Fetch data ────────────────────────────────────────────────────────────

print("=" * 65)
print("MLS Model Evaluation  (3-way split + Platt calibration)")
print("=" * 65)
print("\n[1/8] Fetching MLS data from ASA API...")

from itscalledsoccer.client import AmericanSoccerAnalysis
asa = AmericanSoccerAnalysis()

games_raw = asa.get_games(leagues="mls")
_avail = set(games_raw.columns)

_stage_col = next(
    (c for c in ["stage_name", "competition_round", "round_name",
                 "competition_stage", "game_type"] if c in _avail),
    None,
)
_sel = ["game_id", "date_time_utc", "home_team_id", "away_team_id",
        "home_score", "away_score", "season_name", "status"]
if _stage_col:
    _sel.append(_stage_col)

games = games_raw[[c for c in _sel if c in _avail]].rename(columns={
    "game_id": "match_id", "date_time_utc": "date",
    "home_team_id": "home_team", "away_team_id": "away_team",
    "home_score": "home_goals", "away_score": "away_goals",
    "season_name": "season",
})

if _stage_col and _stage_col in games.columns:
    games["is_playoff"] = games[_stage_col].str.lower().str.contains(
        r"playoff|cup final|semifinal|final|knockout|conference", na=False
    ).astype(int)
    games.drop(columns=[_stage_col], inplace=True)
else:
    games["is_playoff"] = 0

gxg = asa.get_game_xgoals(leagues="mls")[
    ["game_id", "home_team_xgoals", "away_team_xgoals"]
].rename(columns={
    "game_id": "match_id",
    "home_team_xgoals": "home_xg",
    "away_team_xgoals": "away_xg",
})

df = games.merge(gxg, on="match_id", how="left")
df["date"] = pd.to_datetime(df["date"], utc=True).dt.tz_localize(None)
df["season"] = (
    pd.to_numeric(df["season"], errors="coerce")
    .fillna(df["date"].dt.year)
    .astype(int)
)
df = df[df["home_goals"].notna() & df["away_goals"].notna()].copy()
df["home_goals"] = df["home_goals"].astype(int)
df["away_goals"] = df["away_goals"].astype(int)

_n_raw = len(df)
df = df[(df["season"] >= 2017) & (~df["season"].isin(_COVID))].copy()
df = df.sort_values("date").reset_index(drop=True)

print(f"    {len(df):,} matches ({df['season'].min()}–{df['season'].max()})  |  "
      f"{_n_raw - len(df):,} pre-2017/COVID excluded")
print(f"    xG coverage: {df['home_xg'].notna().mean():.0%}  |  "
      f"Playoff: {df['is_playoff'].sum()} ({df['is_playoff'].mean():.1%})")

# Labels needed early for ELO grid search
df["label_result"] = np.where(
    df["home_goals"] > df["away_goals"], 0,
    np.where(df["home_goals"] == df["away_goals"], 1, 2),
)
df["label_over25"] = ((df["home_goals"] + df["away_goals"]) > 2.5).astype(int)

# ─── 2. ELO grid search ───────────────────────────────────────────────────────

print("\n[2/8] ELO hyperparameter grid search (val: 2019)...")


def compute_elo(
    df: pd.DataFrame,
    K: float,
    HOME_ADV: float,
    regress: float = 0.40,
    initial: float = 1500.0,
    return_expected: bool = False,
) -> pd.DataFrame:
    elo: dict[str, float] = {}
    h_elo, a_elo, h_exp = [], [], []
    seen: set = set()
    for _, row in df.iterrows():
        s = row["season"]
        if s not in seen:
            seen.add(s)
            elo = {t: initial + (r - initial) * (1 - regress) for t, r in elo.items()}
        ht, at = row["home_team"], row["away_team"]
        rh = elo.get(ht, initial)
        ra = elo.get(at, initial)
        e_h = 1 / (1 + 10 ** ((ra - (rh + HOME_ADV)) / 400))
        hg, ag = row["home_goals"], row["away_goals"]
        s_h = 1.0 if hg > ag else (0.5 if hg == ag else 0.0)
        mov = 1 + math.log(abs(hg - ag) + 1) * 0.1
        h_elo.append(rh)
        a_elo.append(ra)
        h_exp.append(e_h)
        elo[ht] = rh + K * mov * (s_h - e_h)
        elo[at] = ra + K * mov * ((1 - s_h) - (1 - e_h))
    out = df.copy()
    out["home_elo"] = h_elo
    out["away_elo"] = a_elo
    out["elo_diff"] = np.array(h_elo) - np.array(a_elo)
    if return_expected:
        out["elo_p_home"] = h_exp
    return out


_VAL_S = {2019}
_val_draw_rate = df[df["season"] < min(_VAL_S)]["label_result"].eq(1).mean()
_ELO_GRID = list(itertools.product([20, 25, 30], [80, 100, 120]))
_best_elo_b, _best_K, _best_HA = float("inf"), 20, 100

for _K, _HA in _ELO_GRID:
    _tmp = compute_elo(df, _K, _HA, REGRESS, INITIAL_ELO, return_expected=True)
    _v = _tmp[_tmp["season"].isin(_VAL_S)]
    if len(_v) < 30:
        continue
    _ph = _v["elo_p_home"].values
    _pd = np.full(len(_v), _val_draw_rate)
    _pa = np.clip(1 - _ph - _pd, 0.01, None)
    _s = _ph + _pd + _pa
    _p3 = np.column_stack([_ph / _s, _pd / _s, _pa / _s])
    _yoh = np.eye(3)[_v["label_result"].values]
    _b = float(np.mean(np.sum((_p3 - _yoh) ** 2, axis=1)))
    if _b < _best_elo_b:
        _best_elo_b, _best_K, _best_HA = _b, _K, _HA

K, HOME_ADV = _best_K, _best_HA
print(f"    Best: K={K}, HOME_ADV={HOME_ADV}  (val Brier={_best_elo_b:.4f})")
print(f"    REGRESS: 0.30 → {REGRESS:.0%}  (MLS parity increasing)")

df = compute_elo(df, K, HOME_ADV, REGRESS, INITIAL_ELO)

# ─── 3. Rolling features ─────────────────────────────────────────────────────

print(f"\n[3/8] Rolling features (xG windows={XG_WINDOWS}, draw window={DRAW_WINDOW})...")


def add_rolling_features(
    df: pd.DataFrame,
    xg_windows: tuple = (5, 15),
    form_window: int = 5,
    draw_window: int = 10,
) -> pd.DataFrame:
    team_xg: dict[str, list] = {}
    team_pts: dict[str, list] = {}
    team_draw: dict[str, list] = {}

    res: dict[str, list] = {
        **{f"home_xg_roll_{w}": [] for w in xg_windows},
        **{f"home_xga_roll_{w}": [] for w in xg_windows},
        **{f"away_xg_roll_{w}": [] for w in xg_windows},
        **{f"away_xga_roll_{w}": [] for w in xg_windows},
        "home_form": [],
        "away_form": [],
        f"home_draw_rate_{draw_window}": [],
        f"away_draw_rate_{draw_window}": [],
    }

    for _, row in df.iterrows():
        ht, at = row["home_team"], row["away_team"]
        hg, ag = row["home_goals"], row["away_goals"]
        h_xg = row["home_xg"] if pd.notna(row.get("home_xg")) else float(hg)
        a_xg = row["away_xg"] if pd.notna(row.get("away_xg")) else float(ag)

        for team, role, xg_val, xga_val in [
            (ht, "home", h_xg, a_xg),
            (at, "away", a_xg, h_xg),
        ]:
            hist = team_xg.get(team, [])
            pts_h = team_pts.get(team, [])[-form_window:]
            draw_h = team_draw.get(team, [])[-draw_window:]

            for w in xg_windows:
                xg_w = hist[-w:]
                res[f"{role}_xg_roll_{w}"].append(
                    np.mean([x["xg"] for x in xg_w]) if xg_w else 1.3
                )
                res[f"{role}_xga_roll_{w}"].append(
                    np.mean([x["xga"] for x in xg_w]) if xg_w else 1.3
                )

            res[f"{role}_form"].append(np.mean(pts_h) if pts_h else 1.0)
            res[f"{role}_draw_rate_{draw_window}"].append(
                np.mean(draw_h) if draw_h else 0.25
            )

        # Update histories after reading (avoid leakage)
        team_xg.setdefault(ht, []).append({"xg": h_xg, "xga": a_xg})
        team_xg.setdefault(at, []).append({"xg": a_xg, "xga": h_xg})
        h_pts = 3 if hg > ag else (1 if hg == ag else 0)
        a_pts = 3 if ag > hg else (1 if hg == ag else 0)
        team_pts.setdefault(ht, []).append(h_pts)
        team_pts.setdefault(at, []).append(a_pts)
        is_draw = int(hg == ag)
        team_draw.setdefault(ht, []).append(is_draw)
        team_draw.setdefault(at, []).append(is_draw)

    out = df.copy()
    for col, vals in res.items():
        out[col] = vals

    w0 = xg_windows[0]
    out["xg_diff"] = out[f"home_xg_roll_{w0}"] - out[f"away_xg_roll_{w0}"]
    out["form_diff"] = out["home_form"] - out["away_form"]
    out["home_xg_sum"] = out[f"home_xg_roll_{w0}"] + out[f"away_xg_roll_{w0}"]
    return out


df = add_rolling_features(df, XG_WINDOWS, FORM_WINDOW, DRAW_WINDOW)

# ─── Feature sets for A/B testing ────────────────────────────────────────────

_FEAT_BASE = (
    ["elo_diff", "home_elo", "away_elo"]
    + [f"{r}_xg_roll_{w}" for r in ("home", "away") for w in XG_WINDOWS]
    + [f"{r}_xga_roll_{w}" for r in ("home", "away") for w in XG_WINDOWS]
    + ["xg_diff", "form_diff", "home_form", "away_form", "is_playoff"]
)
_FEAT_DRAW = _FEAT_BASE + [
    f"home_draw_rate_{DRAW_WINDOW}",
    f"away_draw_rate_{DRAW_WINDOW}",
]
_FEAT_DC  = _FEAT_BASE + ["dc_lam", "dc_mu"]
_FEAT_ALL = _FEAT_BASE + [
    f"home_draw_rate_{DRAW_WINDOW}",
    f"away_draw_rate_{DRAW_WINDOW}",
    "dc_lam", "dc_mu",
    "home_xg_sum",
]

AB_SETS = {
    "Base":      _FEAT_BASE,
    "+DrawRate": _FEAT_DRAW,
    "+DCParams": _FEAT_DC,
    "+All":      _FEAT_ALL,
}

# ─── 4. Dixon-Coles ───────────────────────────────────────────────────────────

def dc_tau(x, y, lam, mu, rho):
    if x == 0 and y == 0: return 1 - lam * mu * rho
    if x == 0 and y == 1: return 1 + lam * rho
    if x == 1 and y == 0: return 1 + mu * rho
    if x == 1 and y == 1: return 1 - rho
    return 1.0


def dc_nll(params, teams, arr, decay_hl):
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
        mu = math.exp(atk[ai] + dfd[hi])
        tau = dc_tau(hg, ag, lam, mu, rho)
        if tau <= 1e-10:
            continue
        ll += w * (math.log(tau) + poisson.logpmf(hg, lam) + poisson.logpmf(ag, mu))
    return -ll


def fit_dc(matches: pd.DataFrame, decay_hl: int = DC_DECAY_HL, recent_seasons: int = 4):
    max_s = matches["season"].max()
    recent = matches[matches["season"] >= max_s - recent_seasons + 1].copy()
    teams = sorted(set(recent["home_team"]) | set(recent["away_team"]))
    tidx = {t: i for i, t in enumerate(teams)}
    n = len(teams)
    ref = recent["date"].max()
    arr = np.array(
        [
            [
                (ref - r["date"]).days,
                tidx.get(r["home_team"], 0),
                tidx.get(r["away_team"], 0),
                r["home_goals"],
                r["away_goals"],
            ]
            for _, r in recent.iterrows()
        ],
        dtype=float,
    )
    x0 = np.zeros(2 * n + 2)
    x0[2 * n], x0[2 * n + 1] = 0.25, -0.05
    bounds = [(-3, 3)] * (2 * n) + [(0.0, 1.0)] + [(-0.5, 0.0)]
    res = minimize(
        dc_nll, x0, args=(teams, arr, decay_hl),
        method="L-BFGS-B", bounds=bounds,
        options={"maxiter": 300, "ftol": 1e-7},
    )
    atk = dict(zip(teams, res.x[:n]))
    dfd = dict(zip(teams, res.x[n:2*n]))
    return atk, dfd, res.x[2*n], res.x[2*n + 1]


def dc_predict(ht, at, atk, dfd, ha, rho, max_g=8):
    lam = math.exp(atk.get(ht, 0) + dfd.get(at, 0) + ha)
    mu = math.exp(atk.get(at, 0) + dfd.get(ht, 0))
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
    po = float(M[np.add.outer(np.arange(max_g + 1), np.arange(max_g + 1)) > 2.5].sum())
    t = ph + pd_ + pa
    return ph / t, pd_ / t, pa / t, po


def dc_predict_batch(split_df, atk, dfd, ha, rho):
    return np.array(
        [dc_predict(r.home_team, r.away_team, atk, dfd, ha, rho)
         for _, r in split_df.iterrows()]
    )


def dc_lam_mu_batch(split_df, atk, dfd, ha):
    lams, mus = [], []
    for _, r in split_df.iterrows():
        lam = math.exp(atk.get(r["home_team"], 0) + dfd.get(r["away_team"], 0) + ha)
        mu = math.exp(atk.get(r["away_team"], 0) + dfd.get(r["home_team"], 0))
        lams.append(lam)
        mus.append(mu)
    return np.array(lams), np.array(mus)


# ─── 5. Calibration — Platt scaling ──────────────────────────────────────────

def calibrate_multiclass(
    raw_cal: np.ndarray, y_cal: np.ndarray, raw_test: np.ndarray
) -> np.ndarray:
    cal_out = np.zeros_like(raw_test, dtype=float)
    for c in range(3):
        platt = LogisticRegression(max_iter=300, C=1.0, random_state=42)
        platt.fit(raw_cal[:, c].reshape(-1, 1), (y_cal == c).astype(int))
        cal_out[:, c] = platt.predict_proba(raw_test[:, c].reshape(-1, 1))[:, 1]
    row_sums = cal_out.sum(axis=1, keepdims=True).clip(1e-9, None)
    return cal_out / row_sums


def calibrate_binary(
    raw_cal: np.ndarray, y_cal: np.ndarray, raw_test: np.ndarray
) -> np.ndarray:
    platt = LogisticRegression(max_iter=300, C=1.0, random_state=42)
    platt.fit(raw_cal.reshape(-1, 1), y_cal.astype(int))
    return platt.predict_proba(raw_test.reshape(-1, 1))[:, 1]


def decile_cal_error(probs: np.ndarray, actuals: np.ndarray) -> tuple[float, float]:
    try:
        dec = pd.qcut(probs, 10, duplicates="drop")
        cal = (
            pd.DataFrame({"p": probs, "a": actuals.astype(float), "d": dec})
            .groupby("d", observed=True)
            .agg(mp=("p", "mean"), ma=("a", "mean"))
        )
        errs = (cal["mp"] - cal["ma"]).abs()
        return float(errs.max()), float(errs.mean())
    except Exception:
        return float("nan"), float("nan")


def multiclass_brier(y_oh: np.ndarray, probs: np.ndarray) -> float:
    return float(np.mean(np.sum((probs - y_oh) ** 2, axis=1)))


def per_class_brier(y_oh: np.ndarray, probs: np.ndarray) -> tuple:
    return tuple(float(np.mean((probs[:, c] - y_oh[:, c]) ** 2)) for c in range(3))


# ─── 6. Walk-forward evaluation ───────────────────────────────────────────────

print(
    f"\n[4/8] Walk-forward evaluation "
    f"(test={TEST_SEASONS}, DC decay={DC_DECAY_HL}d, Platt cal)..."
)
print("      DC fit ~30–90 sec per season.")

results: list[dict] = []
ab_records: list[dict] = []
all_imp: list[dict] = []

for test_season in TEST_SEASONS:
    cal_season = test_season - 1

    train_raw = df[df["season"] < cal_season].copy()
    cal_raw = df[df["season"] == cal_season].copy()
    test_raw = df[df["season"] == test_season].copy()

    if len(train_raw) < 200 or len(cal_raw) < 50 or len(test_raw) < 50:
        print(f"    Season {test_season}: insufficient data, skipping.")
        continue

    print(
        f"    {test_season}: train={len(train_raw)} cal={len(cal_raw)} test={len(test_raw)}",
        end="",
        flush=True,
    )

    y_cal_r = cal_raw["label_result"].values
    y_cal_o = cal_raw["label_over25"].values
    y_te_r = test_raw["label_result"].values
    y_te_o = test_raw["label_over25"].values
    y_te_oh = np.eye(3)[y_te_r]
    y_cal_oh = np.eye(3)[y_cal_r]

    # ── Dixon-Coles ──────────────────────────────────────────────────────────
    dc_ok = False
    try:
        atk, dfd, ha, rho = fit_dc(train_raw, decay_hl=DC_DECAY_HL)
        dc_pred_cal = dc_predict_batch(cal_raw, atk, dfd, ha, rho)
        dc_pred_te = dc_predict_batch(test_raw, atk, dfd, ha, rho)
        dc_cal_cal3 = calibrate_multiclass(dc_pred_cal[:, :3], y_cal_r, dc_pred_cal[:, :3])
        dc_cal_te3 = calibrate_multiclass(dc_pred_cal[:, :3], y_cal_r, dc_pred_te[:, :3])
        dc_cal_ou = calibrate_binary(dc_pred_cal[:, 3], y_cal_o, dc_pred_te[:, 3])
        dc_ok = True
        print(" | DC✓", end="", flush=True)
    except Exception as e:
        dc_pred_cal = dc_pred_te = dc_cal_cal3 = dc_cal_te3 = dc_cal_ou = None
        print(f" | DC✗({e})", end="", flush=True)

    # ── Add DC λ/μ features to splits ────────────────────────────────────────
    if dc_ok:
        train = train_raw.copy()
        cal = cal_raw.copy()
        test = test_raw.copy()
        train["dc_lam"], train["dc_mu"] = dc_lam_mu_batch(train, atk, dfd, ha)
        cal["dc_lam"], cal["dc_mu"] = dc_lam_mu_batch(cal, atk, dfd, ha)
        test["dc_lam"], test["dc_mu"] = dc_lam_mu_batch(test, atk, dfd, ha)
    else:
        train, cal, test = train_raw, cal_raw, test_raw

    # ── Exponential season weights ────────────────────────────────────────────
    ref_s = train["season"].max()
    sw = train["season"].apply(
        lambda s: math.exp(-math.log(2) / WEIGHT_HL * (ref_s - s))
    ).values

    # ── XGBoost hyperparameter search (inner val = last 2 seasons of train) ──
    _inner_s = sorted(train["season"].unique())[-2:]
    _itr = train[~train["season"].isin(_inner_s)]
    _ival = train[train["season"].isin(_inner_s)]
    _sw_i = _itr["season"].apply(
        lambda s: math.exp(-math.log(2) / WEIGHT_HL * (ref_s - s))
    ).values

    _gs_feat = [c for c in _FEAT_ALL if c in _itr.columns]
    _xgb_grid = list(itertools.product([3, 4, 5], [200, 400], [0.05, 0.10]))
    _best_xgb_b = float("inf")
    _best_p = {"max_depth": 4, "n_estimators": 300, "learning_rate": 0.05}

    for _md, _ne, _lr in _xgb_grid:
        try:
            _c = xgb.XGBClassifier(
                n_estimators=_ne, max_depth=_md, learning_rate=_lr,
                subsample=0.8, colsample_bytree=0.8,
                objective="multi:softprob", num_class=3,
                eval_metric="mlogloss", verbosity=0, random_state=42,
            )
            _c.fit(_itr[_gs_feat].fillna(0).values, _itr["label_result"].values,
                   sample_weight=_sw_i)
            _ip = _c.predict_proba(_ival[_gs_feat].fillna(0).values)
            _yoh_i = np.eye(3)[_ival["label_result"].values]
            _b = float(np.mean(np.sum((_ip - _yoh_i) ** 2, axis=1)))
            if _b < _best_xgb_b:
                _best_xgb_b = _b
                _best_p = {"max_depth": _md, "n_estimators": _ne, "learning_rate": _lr}
        except Exception:
            pass

    print(
        f" | XGB-grid(d={_best_p['max_depth']},n={_best_p['n_estimators']},"
        f"lr={_best_p['learning_rate']})",
        end="",
        flush=True,
    )

    # ── A/B test: run each feature set ───────────────────────────────────────
    xgb_ok = False
    xgb_cal_probs_best = xgb_te_probs_best = xgb_cal_te3 = None
    ab_brier: dict[str, float] = {}

    for ab_name, ab_feat in AB_SETS.items():
        feat = [c for c in ab_feat if c in train.columns]
        X_tr = train[feat].fillna(0).values
        X_cal = cal[feat].fillna(0).values
        X_te = test[feat].fillna(0).values
        try:
            clf = xgb.XGBClassifier(
                objective="multi:softprob", num_class=3,
                eval_metric="mlogloss", verbosity=0, random_state=42,
                subsample=0.8, colsample_bytree=0.8,
                **_best_p,
            )
            clf.fit(X_tr, train["label_result"].values, sample_weight=sw)
            cal_p = clf.predict_proba(X_cal)
            te_p = clf.predict_proba(X_te)
            cal_te = calibrate_multiclass(cal_p, y_cal_r, te_p)
            ab_brier[ab_name] = multiclass_brier(y_te_oh, cal_te)

            if ab_name == "+All":
                xgb_cal_probs_best = cal_p
                xgb_te_probs_best = te_p
                xgb_cal_te3 = cal_te
                imp = clf.get_booster().get_score(importance_type="gain")
                all_imp.append({f: imp.get(f"f{i}", 0.0) for i, f in enumerate(feat)})
                xgb_ok = True
        except Exception as e:
            ab_brier[ab_name] = float("nan")
            if ab_name == "+All":
                print(f" | XGB✗({e})", end="", flush=True)

    ab_records.append({"season": test_season, **ab_brier})

    # ── LightGBM O/U ─────────────────────────────────────────────────────────
    ou_feat = [c for c in _FEAT_ALL if c in train.columns]
    lgb_cal_ou_cal = lgb_te_ou_raw = None
    try:
        lgb_clf = lgb.LGBMClassifier(
            n_estimators=_best_p["n_estimators"],
            max_depth=_best_p["max_depth"],
            learning_rate=_best_p["learning_rate"],
            subsample=0.8, colsample_bytree=0.8,
            verbose=-1, random_state=42,
        )
        lgb_clf.fit(train[ou_feat].fillna(0).values, train["label_over25"].values,
                    sample_weight=sw)
        lgb_cal_ou_raw_probs = lgb_clf.predict_proba(cal[ou_feat].fillna(0).values)[:, 1]
        lgb_te_ou_raw = lgb_clf.predict_proba(test[ou_feat].fillna(0).values)[:, 1]
        lgb_cal_ou_cal = calibrate_binary(lgb_cal_ou_raw_probs, y_cal_o, lgb_te_ou_raw)
    except Exception as e:
        print(f" | LGB✗({e})", end="", flush=True)

    # ── Stacking meta-learner ─────────────────────────────────────────────────
    meta_ok = False
    ens_stacked = ens_ou_stacked = None
    if dc_ok and xgb_ok:
        try:
            xgb_cal_cal3 = calibrate_multiclass(xgb_cal_probs_best, y_cal_r, xgb_cal_probs_best)
            meta_X_cal = np.hstack([dc_cal_cal3, xgb_cal_cal3])
            meta_X_te = np.hstack([dc_cal_te3, xgb_cal_te3])
            meta = LogisticRegression(max_iter=300, C=1.0, random_state=42)
            meta.fit(meta_X_cal, y_cal_r)
            ens_stacked = meta.predict_proba(meta_X_te)
            if dc_cal_ou is not None and lgb_cal_ou_cal is not None:
                ens_ou_stacked = (dc_cal_ou + lgb_cal_ou_cal) / 2.0
            else:
                ens_ou_stacked = dc_cal_ou if dc_cal_ou is not None else lgb_cal_ou_cal
            meta_ok = True
            print(" | Meta✓", end="", flush=True)
        except Exception as e:
            print(f" | Meta✗({e})", end="", flush=True)

    # ── Simple average ensemble ───────────────────────────────────────────────
    if dc_ok and xgb_ok:
        ens_avg = (dc_pred_te[:, :3] + xgb_te_probs_best) / 2.0
    elif dc_ok:
        ens_avg = dc_pred_te[:, :3]
    elif xgb_ok:
        ens_avg = xgb_te_probs_best
    else:
        ens_avg = None

    # ── Naive baseline ────────────────────────────────────────────────────────
    freq = train_raw["label_result"].value_counts(normalize=True).sort_index()
    naive_r = np.tile(
        [freq.get(0, 0.33), freq.get(1, 0.33), freq.get(2, 0.33)], (len(test), 1)
    )
    naive_o = float(train_raw["label_over25"].mean())

    # ── Collect results ───────────────────────────────────────────────────────
    r: dict = {
        "season": test_season,
        "n": len(test),
        "naive_brier": multiclass_brier(y_te_oh, naive_r),
        "naive_ll": log_loss(y_te_r, naive_r),
        "naive_ou_brier": brier_score_loss(y_te_o, np.full(len(test), naive_o)),
        "home_win_rate": (y_te_r == 0).mean(),
        "draw_rate": (y_te_r == 1).mean(),
        "away_win_rate": (y_te_r == 2).mean(),
        "over25_rate": y_te_o.mean(),
    }

    if dc_ok:
        r["dc_brier_raw"] = multiclass_brier(y_te_oh, dc_pred_te[:, :3])
        r["dc_brier_cal"] = multiclass_brier(y_te_oh, dc_cal_te3)
        r["dc_ll_raw"] = log_loss(y_te_r, dc_pred_te[:, :3])
        r["dc_ll_cal"] = log_loss(y_te_r, dc_cal_te3)
        r["dc_ou_raw"] = brier_score_loss(y_te_o, dc_pred_te[:, 3])
        r["dc_ou_cal"] = brier_score_loss(y_te_o, dc_cal_ou)
        h, d, a = per_class_brier(y_te_oh, dc_cal_te3)
        r["dc_cal_h"], r["dc_cal_d"], r["dc_cal_a"] = h, d, a
        r["dc_cal_err_max"], _ = decile_cal_error(dc_cal_te3[:, 0], (y_te_r == 0))

    if xgb_ok:
        r["xgb_brier_raw"] = multiclass_brier(y_te_oh, xgb_te_probs_best)
        r["xgb_brier_cal"] = multiclass_brier(y_te_oh, xgb_cal_te3)
        r["xgb_ll_raw"] = log_loss(y_te_r, xgb_te_probs_best)
        r["xgb_ll_cal"] = log_loss(y_te_r, xgb_cal_te3)
        h, d, a = per_class_brier(y_te_oh, xgb_cal_te3)
        r["xgb_cal_h"], r["xgb_cal_d"], r["xgb_cal_a"] = h, d, a
        r["xgb_cal_err_max"], _ = decile_cal_error(xgb_cal_te3[:, 0], (y_te_r == 0))

    if lgb_te_ou_raw is not None:
        r["xgb_ou_raw"] = brier_score_loss(y_te_o, lgb_te_ou_raw)
    if lgb_cal_ou_cal is not None:
        r["xgb_ou_cal"] = brier_score_loss(y_te_o, lgb_cal_ou_cal)

    if ens_avg is not None:
        r["ens_avg_brier"] = multiclass_brier(y_te_oh, ens_avg)
        r["ens_avg_ll"] = log_loss(y_te_r, ens_avg)

    if meta_ok:
        r["ens_stacked_brier"] = multiclass_brier(y_te_oh, ens_stacked)
        r["ens_stacked_ll"] = log_loss(y_te_r, ens_stacked)
        if ens_ou_stacked is not None:
            r["ens_stacked_ou"] = brier_score_loss(y_te_o, ens_ou_stacked)
        h, d, a = per_class_brier(y_te_oh, ens_stacked)
        r["ens_stacked_h"], r["ens_stacked_d"], r["ens_stacked_a"] = h, d, a
        r["ens_cal_err_max"], _ = decile_cal_error(ens_stacked[:, 0], (y_te_r == 0))
        raw_ce, _ = decile_cal_error(ens_avg[:, 0], (y_te_r == 0))
        stk_ce, _ = decile_cal_error(ens_stacked[:, 0], (y_te_r == 0))
        r["cal_stage_raw_avg"] = raw_ce
        r["cal_stage_stacked"] = stk_ce

    results.append(r)
    best_key = next(
        (k for k in ["ens_stacked_brier", "ens_avg_brier", "xgb_brier_cal", "dc_brier_cal"]
         if k in r),
        None,
    )
    best = f"{r[best_key]:.4f}" if best_key else "?"
    print(f" | Best={best} vs Naive={r['naive_brier']:.4f}")


# ─── 7. Report ────────────────────────────────────────────────────────────────

print("\n" + "=" * 65)
print("RESULTS — averaged over test seasons 2022–2024")
print("=" * 65)

rd = pd.DataFrame(results)


def avg(col: str) -> float:
    return rd[col].dropna().mean() if col in rd.columns else float("nan")


def pct(a: float, b: float) -> float:
    return (b - a) / b * 100 if b and not (math.isnan(a) or math.isnan(b)) else float("nan")


naive_b = avg("naive_brier")
naive_l = avg("naive_ll")
naive_ou = avg("naive_ou_brier")

print(f"\n{'Model':<28} {'Brier':>8} {'vs Naive':>10} {'Log-Loss':>10}")
print("-" * 58)
print(f"{'Naive baseline':<28} {naive_b:8.4f} {'—':>10} {naive_l:10.4f}")

for label, bk, lk in [
    ("DC (raw)",             "dc_brier_raw",       "dc_ll_raw"),
    ("DC (calibrated)",      "dc_brier_cal",        "dc_ll_cal"),
    ("XGBoost (raw)",        "xgb_brier_raw",       "xgb_ll_raw"),
    ("XGBoost (cal, +All)",  "xgb_brier_cal",       "xgb_ll_cal"),
    ("Ensemble avg",         "ens_avg_brier",        "ens_avg_ll"),
    ("Ensemble stacked",     "ens_stacked_brier",    "ens_stacked_ll"),
]:
    b = avg(bk)
    l = avg(lk)
    if not math.isnan(b):
        print(f"  {label:<26} {b:8.4f} {pct(b, naive_b):>+9.1f}% {l:10.4f}")

print(f"\n{'Model':<28} {'O/U Brier':>10} {'vs Naive':>10}")
print("-" * 50)
print(f"{'Naive baseline':<28} {naive_ou:10.4f} {'—':>10}")
for label, k in [
    ("DC (raw)",         "dc_ou_raw"),
    ("DC (calibrated)",  "dc_ou_cal"),
    ("LightGBM (raw)",   "xgb_ou_raw"),
    ("LightGBM (cal)",   "xgb_ou_cal"),
    ("Stacked avg",      "ens_stacked_ou"),
]:
    v = avg(k)
    if not math.isnan(v):
        print(f"  {label:<26} {v:10.4f} {pct(v, naive_ou):>+9.1f}%")

# A/B feature test
if ab_records:
    n_folds = len(ab_records)
    print(f"\nA/B feature test (XGBoost Brier, avg over {n_folds} seasons):")
    print(f"  {'Feature set':<16} {'Brier':>8}  {'Δ vs Base':>10}  {'Keep?':>6}")
    print("  " + "-" * 44)
    ab_df = pd.DataFrame(ab_records).drop(columns=["season"], errors="ignore")
    ab_avg = ab_df.mean()
    base_b = ab_avg.get("Base", float("nan"))
    for fs in ["Base", "+DrawRate", "+DCParams", "+All"]:
        v = ab_avg.get(fs, float("nan"))
        if math.isnan(v):
            continue
        if fs == "Base":
            print(f"  {fs:<16} {v:8.4f}  {'—':>10}  {'—':>6}")
        else:
            delta = base_b - v  # positive = improvement
            keep = "YES" if delta > 0.001 else ("~" if delta > 0 else "NO")
            print(f"  {fs:<16} {v:8.4f}  {delta:>+10.4f}  {keep:>6}")

# Per-class Brier
print(f"\nPer-class Brier (calibrated):")
print(f"  {'Model':<24} {'Home':>8} {'Draw':>8} {'Away':>8}")
print("  " + "-" * 48)
for label, hk, dk, ak in [
    ("DC (calibrated)",      "dc_cal_h",       "dc_cal_d",       "dc_cal_a"),
    ("XGBoost (cal, +All)",  "xgb_cal_h",      "xgb_cal_d",      "xgb_cal_a"),
    ("Ensemble stacked",     "ens_stacked_h",  "ens_stacked_d",  "ens_stacked_a"),
]:
    h, d, a = avg(hk), avg(dk), avg(ak)
    if not (math.isnan(h) and math.isnan(d)):
        print(f"  {label:<24} {h:8.4f} {d:8.4f} {a:8.4f}")

# Calibration error
print(f"\nCalibration error (Platt, home-win deciles, max):")
print(f"  {'Stage':<28} {'Max err':>8}")
print("  " + "-" * 38)
for label, k in [
    ("Raw average ensemble",   "cal_stage_raw_avg"),
    ("Stacked (meta-learner)", "cal_stage_stacked"),
]:
    v = avg(k)
    if not math.isnan(v):
        flag = "✓" if v < 0.05 else ("~" if v < 0.10 else "!")
        print(f"  {label:<28} {v:8.4f}  [{flag}]")

# Feature importances
if all_imp:
    print(f"\nXGBoost feature importances (+All, gain, avg across folds):")
    agg: dict[str, float] = {}
    for fi in all_imp:
        for f, v in fi.items():
            agg[f] = agg.get(f, 0.0) + v / len(all_imp)
    total = sum(agg.values()) or 1.0
    print(f"  {'Feature':<28} {'Gain':>10} {'Share':>8}")
    print("  " + "-" * 48)
    for fn, fv in sorted(agg.items(), key=lambda x: x[1], reverse=True):
        print(f"  {fn:<28} {fv:10.1f} {fv / total:8.1%}")

# Match rates
print(f"\nMatch outcome rates (test avg):")
for col, label in [
    ("home_win_rate", "Home wins"),
    ("draw_rate", "Draws"),
    ("away_win_rate", "Away wins"),
    ("over25_rate", "Over 2.5"),
]:
    if col in rd.columns:
        print(f"  {label}: {rd[col].mean():.1%}")

# Per-season detail
print(f"\nPer-season Brier:")
dcols = ["season", "n", "naive_brier"]
for c in ["dc_brier_cal", "xgb_brier_cal", "ens_stacked_brier"]:
    if c in rd.columns:
        dcols.append(c)
print(rd[dcols].to_string(index=False, float_format="{:.4f}".format))

# ─── 8. Recommendations ──────────────────────────────────────────────────────

print("\n" + "=" * 65)
print("RECOMMENDATIONS")
print("=" * 65)
print()
print(f"  ELO: K={K}, HOME_ADV={HOME_ADV}, REGRESS={REGRESS:.0%}")

best_key = next(
    (k for k in ["ens_stacked_brier", "ens_avg_brier", "xgb_brier_cal", "dc_brier_cal"]
     if k in rd.columns and not math.isnan(avg(k))),
    None,
)
best_b = avg(best_key) if best_key else float("nan")
imp_pct = pct(best_b, naive_b)

if not math.isnan(imp_pct):
    if imp_pct > -5:
        print(f"  [!] WEAK:     Best model {imp_pct:+.1f}% vs naive. Calibration + features needed.")
    elif imp_pct > -10:
        print(f"  [~] MODERATE: Best model {imp_pct:+.1f}% vs naive.")
    else:
        print(f"  [+] GOOD:     Best model {imp_pct:+.1f}% vs naive.")

xgb_d = avg("xgb_cal_d")
if not math.isnan(xgb_d) and xgb_d > 0.18:
    print(f"\n  [Draw] Brier={xgb_d:.4f} — draws remain the hardest class (~25% MLS rate).")

xgb_ou = avg("xgb_ou_cal")
dc_ou_cal = avg("dc_ou_cal")
if not math.isnan(xgb_ou):
    if xgb_ou >= naive_ou:
        print(f"\n  [O/U] LightGBM ({xgb_ou:.4f}) ≥ naive. Use DC O/U ({dc_ou_cal:.4f}) directly.")
    else:
        print(f"\n  [O/U] LightGBM improved to {xgb_ou:.4f} (naive: {naive_ou:.4f}).")

if ab_records:
    ab_df2 = pd.DataFrame(ab_records)
    ab_avg2 = ab_df2.drop(columns=["season"]).mean()
    base_b2 = ab_avg2.get("Base", float("nan"))
    for fs in ["+DrawRate", "+DCParams"]:
        v = ab_avg2.get(fs, float("nan"))
        if not math.isnan(v) and not math.isnan(base_b2):
            delta = base_b2 - v
            verdict = "KEEP" if delta > 0.001 else ("marginal" if delta > 0 else "DROP")
            print(f"\n  [A/B] {fs}: Δ={delta:+.4f} → {verdict}")

print()
print("Evaluation complete.")
