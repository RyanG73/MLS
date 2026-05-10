#!/usr/bin/env python3
"""
Standalone model evaluation — no database required.

Pulls real MLS match data from ASA API, builds minimal features,
trains Dixon-Coles + XGBoost/LightGBM, and evaluates on held-out seasons
using walk-forward (no future leakage).

Metrics:
  - Multi-class Brier score (home/draw/away)
  - Log-loss
  - O/U 2.5 Brier score
  - Calibration (mean predicted vs actual per decile)

Baseline: always predict historical average frequencies.
"""

import sys
import math
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.stats import poisson
from sklearn.metrics import log_loss, brier_score_loss
import xgboost as xgb
import lightgbm as lgb

warnings.filterwarnings("ignore")

# ─── 1. Fetch MLS data ────────────────────────────────────────────────────────

print("=" * 60)
print("MLS Model Baseline Evaluation")
print("=" * 60)
print("\n[1/6] Fetching MLS data from ASA API...")

from itscalledsoccer.client import AmericanSoccerAnalysis
asa = AmericanSoccerAnalysis()

# Game results
games = asa.get_games(leagues="mls")[
    ["game_id", "date_time_utc", "home_team_id", "away_team_id",
     "home_score", "away_score", "season_name", "status"]
].rename(columns={
    "game_id": "match_id", "date_time_utc": "date",
    "home_team_id": "home_team", "away_team_id": "away_team",
    "home_score": "home_goals", "away_score": "away_goals",
    "season_name": "season",
})

# Per-game xG (separate endpoint)
gxg = asa.get_game_xgoals(leagues="mls")[
    ["game_id", "home_team_xgoals", "away_team_xgoals"]
].rename(columns={
    "game_id": "match_id",
    "home_team_xgoals": "home_xg",
    "away_team_xgoals": "away_xg",
})

df = games.merge(gxg, on="match_id", how="left")
df["date"] = pd.to_datetime(df["date"], utc=True).dt.tz_localize(None)
df["season"] = pd.to_numeric(df["season"], errors="coerce").fillna(
    df["date"].dt.year
).astype(int)

# Only completed matches with scores
df = df[df["home_goals"].notna() & df["away_goals"].notna()].copy()
df["home_goals"] = df["home_goals"].astype(int)
df["away_goals"] = df["away_goals"].astype(int)
df = df[df["season"] >= 2013].sort_values("date").reset_index(drop=True)

xg_coverage = df["home_xg"].notna().mean()
print(f"    Loaded {len(df):,} matches  ({df['season'].min()}–{df['season'].max()})")
print(f"    xG coverage: {xg_coverage:.0%}")

# ─── 2. ELO ratings ───────────────────────────────────────────────────────────

print("\n[2/6] Computing ELO ratings...")

K = 20
HOME_ADV = 100
INITIAL = 1500
REGRESS = 0.30

elo: dict[str, float] = {}
home_elo_pre, away_elo_pre = [], []
seen_seasons: set = set()

for _, row in df.iterrows():
    s = row["season"]
    if s not in seen_seasons:
        seen_seasons.add(s)
        elo = {t: INITIAL + (r - INITIAL) * (1 - REGRESS) for t, r in elo.items()}

    ht, at = row["home_team"], row["away_team"]
    rh = elo.get(ht, INITIAL)
    ra = elo.get(at, INITIAL)
    home_elo_pre.append(rh)
    away_elo_pre.append(ra)

    e_h = 1 / (1 + 10 ** ((ra - (rh + HOME_ADV)) / 400))
    hg, ag = row["home_goals"], row["away_goals"]
    s_h = 1.0 if hg > ag else (0.5 if hg == ag else 0.0)
    mov = 1 + math.log(abs(hg - ag) + 1) * 0.1

    elo[ht] = rh + K * mov * (s_h - e_h)
    elo[at] = ra + K * mov * ((1 - s_h) - (1 - e_h))

df["home_elo"] = home_elo_pre
df["away_elo"] = away_elo_pre
df["elo_diff"] = df["home_elo"] - df["away_elo"]

# ─── 3. Rolling features ─────────────────────────────────────────────────────

print("\n[3/6] Computing rolling features...")

def add_rolling_features(df: pd.DataFrame, window: int = 10) -> pd.DataFrame:
    """Add rolling xG and form features without future leakage."""
    team_xg_hist: dict[str, list] = {}
    team_pts_hist: dict[str, list] = {}

    h_xg_r, h_xga_r, a_xg_r, a_xga_r = [], [], [], []
    h_form, a_form = [], []

    for _, row in df.iterrows():
        ht, at = row["home_team"], row["away_team"]
        hg, ag = row["home_goals"], row["away_goals"]
        h_xg_val = row["home_xg"] if pd.notna(row.get("home_xg")) else float(hg)
        a_xg_val = row["away_xg"] if pd.notna(row.get("away_xg")) else float(ag)

        for team, role in [(ht, "home"), (at, "away")]:
            xg_hist = team_xg_hist.get(team, [])[-window:]
            pts_hist = team_pts_hist.get(team, [])[-5:]
            xg_avg  = np.mean([h["xg"]  for h in xg_hist]) if xg_hist else 1.3
            xga_avg = np.mean([h["xga"] for h in xg_hist]) if xg_hist else 1.3
            form    = np.mean(pts_hist) if pts_hist else 1.0

            if role == "home":
                h_xg_r.append(xg_avg); h_xga_r.append(xga_avg); h_form.append(form)
            else:
                a_xg_r.append(xg_avg); a_xga_r.append(xga_avg); a_form.append(form)

        # Update histories (after reading, to avoid leakage)
        team_xg_hist.setdefault(ht, []).append({"xg": h_xg_val, "xga": a_xg_val})
        team_xg_hist.setdefault(at, []).append({"xg": a_xg_val, "xga": h_xg_val})

        h_pts = 3 if hg > ag else (1 if hg == ag else 0)
        a_pts = 3 if ag > hg else (1 if hg == ag else 0)
        team_pts_hist.setdefault(ht, []).append(h_pts)
        team_pts_hist.setdefault(at, []).append(a_pts)

    df = df.copy()
    df["home_xg_roll"] = h_xg_r
    df["home_xga_roll"] = h_xga_r
    df["away_xg_roll"] = a_xg_r
    df["away_xga_roll"] = a_xga_r
    df["home_form"]  = h_form
    df["away_form"]  = a_form
    df["xg_diff"]    = df["home_xg_roll"] - df["away_xg_roll"]
    df["form_diff"]  = df["home_form"] - df["away_form"]
    return df

df = add_rolling_features(df, window=10)

df["label_result"] = np.where(df["home_goals"] > df["away_goals"], 0,
                     np.where(df["home_goals"] == df["away_goals"], 1, 2))
df["label_over25"] = ((df["home_goals"] + df["away_goals"]) > 2.5).astype(int)

FEAT_COLS = ["elo_diff", "home_elo", "away_elo",
             "home_xg_roll", "home_xga_roll",
             "away_xg_roll", "away_xga_roll",
             "xg_diff", "form_diff", "home_form", "away_form"]

# ─── 4. Dixon-Coles ───────────────────────────────────────────────────────────

def dc_tau(x, y, lam, mu, rho):
    if x == 0 and y == 0: return 1 - lam * mu * rho
    if x == 0 and y == 1: return 1 + lam * rho
    if x == 1 and y == 0: return 1 + mu * rho
    if x == 1 and y == 1: return 1 - rho
    return 1.0


def dc_nll(params, teams, matches_arr, decay_hl=180):
    """Negative log-likelihood using logpmf to avoid domain errors.
    matches_arr: numpy array (N, 5) of [days_ago, home_idx, away_idx, hg, ag]
    """
    n = len(teams)
    atk = params[:n]
    dfd = params[n:2*n]
    ha  = params[2*n]
    rho = params[2*n + 1]
    lam_d = math.log(2) / decay_hl
    ll = 0.0
    for row in matches_arr:
        days_ago, hi, ai, hg, ag = int(row[0]), int(row[1]), int(row[2]), int(row[3]), int(row[4])
        w = math.exp(-lam_d * days_ago)
        lam = math.exp(atk[hi] + dfd[ai] + ha)
        mu  = math.exp(atk[ai] + dfd[hi])
        tau = dc_tau(hg, ag, lam, mu, rho)
        if tau <= 1e-10: continue
        ll += w * (math.log(tau) + poisson.logpmf(hg, lam) + poisson.logpmf(ag, mu))
    return -ll


def fit_dc(matches: pd.DataFrame, decay_hl: int = 180, recent_seasons: int = 4):
    """Fit Dixon-Coles. Only uses last `recent_seasons` to keep optimization fast;
    older matches have near-zero weight anyway due to time decay."""
    max_season = matches["season"].max()
    recent = matches[matches["season"] >= max_season - recent_seasons + 1].copy()

    teams = sorted(set(recent["home_team"]) | set(recent["away_team"]))
    tidx = {t: i for i, t in enumerate(teams)}
    n = len(teams)

    ref_date = recent["date"].max()
    arr = np.array([
        [(ref_date - row["date"]).days,
         tidx.get(row["home_team"], 0), tidx.get(row["away_team"], 0),
         row["home_goals"], row["away_goals"]]
        for _, row in recent.iterrows()
    ], dtype=float)

    x0 = np.zeros(2*n + 2)
    x0[2*n], x0[2*n+1] = 0.25, -0.05
    bounds = [(-3, 3)] * (2*n) + [(0.0, 1.0)] + [(-0.5, 0.0)]
    res = minimize(dc_nll, x0, args=(teams, arr, decay_hl),
                   method="L-BFGS-B", bounds=bounds,
                   options={"maxiter": 300, "ftol": 1e-7})

    atk = dict(zip(teams, res.x[:n]))
    dfd = dict(zip(teams, res.x[n:2*n]))
    return atk, dfd, res.x[2*n], res.x[2*n+1]


def dc_predict(ht, at, atk, dfd, ha, rho, max_g=8):
    lam = math.exp(atk.get(ht, 0) + dfd.get(at, 0) + ha)
    mu  = math.exp(atk.get(at, 0) + dfd.get(ht, 0))
    M = np.zeros((max_g+1, max_g+1))
    for i in range(max_g+1):
        for j in range(max_g+1):
            tau = dc_tau(i, j, lam, mu, rho)
            M[i, j] = max(tau, 1e-10) * poisson.pmf(i, lam) * poisson.pmf(j, mu)
    M = np.clip(M, 1e-15, None)
    M /= M.sum()
    ph = float(np.tril(M, -1).sum())
    pd = float(np.diag(M).sum())
    pa = float(np.triu(M, 1).sum())
    po = float(M[np.add.outer(np.arange(max_g+1),
                               np.arange(max_g+1)) > 2.5].sum())
    t = ph + pd + pa
    return ph/t, pd/t, pa/t, po

# ─── 5. Walk-forward ─────────────────────────────────────────────────────────

print("\n[4/6] Walk-forward evaluation (test seasons: 2022, 2023, 2024)...")
print("      DC fit may take ~30–90 sec per season on full history.")

TEST_SEASONS = [2022, 2023, 2024]
results = []

for test_season in TEST_SEASONS:
    train = df[df["season"] < test_season].copy()
    test  = df[df["season"] == test_season].copy()

    if len(train) < 300 or len(test) < 50:
        continue

    print(f"    Season {test_season}: train={len(train)} | test={len(test)}", end="", flush=True)

    # ── Dixon-Coles ──────────────────────────────────────────────────────────
    dc_ok = False
    try:
        atk, dfd, ha, rho = fit_dc(train)
        dc_pred = np.array([dc_predict(r.home_team, r.away_team, atk, dfd, ha, rho)
                            for _, r in test.iterrows()])
        dc_ok = True
        print(" | DC✓", end="", flush=True)
    except Exception as e:
        dc_pred = None
        print(f" | DC✗({e})", end="", flush=True)

    # ── XGBoost (1X2) + LightGBM (O/U) ─────────────────────────────────────
    feat = [c for c in FEAT_COLS if c in train.columns]
    X_tr = train[feat].fillna(0).values
    X_te = test[feat].fillna(0).values
    y_tr_r = train["label_result"].values
    y_tr_o = train["label_over25"].values
    y_te_r = test["label_result"].values
    y_te_o = test["label_over25"].values

    xgb_ok = False
    try:
        clf = xgb.XGBClassifier(
            n_estimators=300, max_depth=4, learning_rate=0.05,
            subsample=0.8, colsample_bytree=0.8,
            objective="multi:softprob", num_class=3,
            eval_metric="mlogloss", verbosity=0, random_state=42
        )
        clf.fit(X_tr, y_tr_r)
        xgb_probs = clf.predict_proba(X_te)

        lgb_clf = lgb.LGBMClassifier(
            n_estimators=300, max_depth=4, learning_rate=0.05,
            subsample=0.8, colsample_bytree=0.8,
            verbose=-1, random_state=42
        )
        lgb_clf.fit(X_tr, y_tr_o)
        lgb_ou = lgb_clf.predict_proba(X_te)[:, 1]
        xgb_ok = True
        print(" | XGB✓", end="", flush=True)
    except Exception as e:
        xgb_probs = lgb_ou = None
        print(f" | XGB✗({e})", end="", flush=True)

    # ── Simple ensemble (average where both available) ───────────────────────
    if dc_ok and xgb_ok:
        ens = (dc_pred[:, :3] + xgb_probs) / 2.0
    elif dc_ok:
        ens = dc_pred[:, :3]
    elif xgb_ok:
        ens = xgb_probs
    else:
        ens = None

    # ── Naive baseline ────────────────────────────────────────────────────────
    freq = train["label_result"].value_counts(normalize=True).sort_index()
    naive_r = np.tile([freq.get(0, 0.33), freq.get(1, 0.33), freq.get(2, 0.33)],
                      (len(test), 1))
    naive_o = np.full(len(test), train["label_over25"].mean())

    # ── Metrics ──────────────────────────────────────────────────────────────
    y_oh = np.zeros((len(test), 3))
    for i, l in enumerate(y_te_r): y_oh[i, l] = 1.0

    def mb(y_oh, yp): return float(np.mean(np.sum((yp - y_oh)**2, axis=1)))
    def ouB(yt, yp): return float(brier_score_loss(yt, yp))

    r = {"season": test_season, "n": len(test),
         "naive_brier": mb(y_oh, naive_r),
         "naive_ll": log_loss(y_te_r, naive_r),
         "naive_ou_brier": ouB(y_te_o, naive_o),
         "home_win_rate": (y_te_r == 0).mean(),
         "draw_rate":     (y_te_r == 1).mean(),
         "away_win_rate": (y_te_r == 2).mean(),
         "over25_rate":   y_te_o.mean(),
         }

    if dc_ok:
        r["dc_brier"]    = mb(y_oh, dc_pred[:, :3])
        r["dc_ll"]       = log_loss(y_te_r, dc_pred[:, :3])
        r["dc_ou_brier"] = ouB(y_te_o, dc_pred[:, 3])

    if xgb_ok:
        r["xgb_brier"]    = mb(y_oh, xgb_probs)
        r["xgb_ll"]       = log_loss(y_te_r, xgb_probs)
        r["xgb_ou_brier"] = ouB(y_te_o, lgb_ou)

    if ens is not None:
        r["ens_brier"] = mb(y_oh, ens)
        r["ens_ll"]    = log_loss(y_te_r, ens)

        # Calibration: home-win deciles
        hp = ens[:, 0]
        ha_ = (y_te_r == 0).astype(float)
        try:
            dec = pd.qcut(hp, 10, duplicates="drop")
            cal = pd.DataFrame({"p": hp, "a": ha_, "d": dec}).groupby("d", observed=True).agg(
                mp=("p","mean"), ma=("a","mean"), n=("p","count"))
            r["cal_max_err"] = float((cal["mp"] - cal["ma"]).abs().max())
            r["cal_mean_err"] = float((cal["mp"] - cal["ma"]).abs().mean())
        except Exception:
            pass

    results.append(r)
    best = r.get("ens_brier", r.get("dc_brier", r.get("xgb_brier", "?")))
    print(f" | Ens={best:.4f} vs Naive={r['naive_brier']:.4f}")

# ─── 6. Report ────────────────────────────────────────────────────────────────

print("\n" + "=" * 60)
print("RESULTS")
print("=" * 60)

rd = pd.DataFrame(results)

def avg(col):
    return rd[col].dropna().mean() if col in rd.columns else float("nan")

def pct(a, b):
    return (b - a) / b * 100 if b and not math.isnan(a) else float("nan")

naive_b = avg("naive_brier")
dc_b    = avg("dc_brier")
xgb_b   = avg("xgb_brier")
ens_b   = avg("ens_brier")
naive_l = avg("naive_ll")
dc_l    = avg("dc_ll")
xgb_l   = avg("xgb_ll")
ens_l   = avg("ens_ll")
naive_ou= avg("naive_ou_brier")
dc_ou   = avg("dc_ou_brier")
xgb_ou  = avg("xgb_ou_brier")
cal_max = avg("cal_max_err")
cal_mean= avg("cal_mean_err")

print(f"\n{'Model':<22} {'Brier':>8} {'vs Naive':>10} {'Log-Loss':>10}")
print("-" * 52)
print(f"{'Naive baseline':<22} {naive_b:8.4f} {'—':>10} {naive_l:10.4f}")
if not math.isnan(dc_b):
    print(f"{'Dixon-Coles':<22} {dc_b:8.4f} {pct(dc_b, naive_b):>+9.1f}% {dc_l:10.4f}")
if not math.isnan(xgb_b):
    print(f"{'XGBoost/LightGBM':<22} {xgb_b:8.4f} {pct(xgb_b, naive_b):>+9.1f}% {xgb_l:10.4f}")
if not math.isnan(ens_b):
    print(f"{'Ensemble (avg)':<22} {ens_b:8.4f} {pct(ens_b, naive_b):>+9.1f}% {ens_l:10.4f}")

print(f"\n{'Model':<22} {'O/U Brier':>10} {'vs Naive':>10}")
print("-" * 44)
print(f"{'Naive baseline':<22} {naive_ou:10.4f} {'—':>10}")
if not math.isnan(dc_ou):
    print(f"{'Dixon-Coles':<22} {dc_ou:10.4f} {pct(dc_ou, naive_ou):>+9.1f}%")
if not math.isnan(xgb_ou):
    print(f"{'XGBoost O/U':<22} {xgb_ou:10.4f} {pct(xgb_ou, naive_ou):>+9.1f}%")

if not math.isnan(cal_max):
    print(f"\nCalibration (home-win deciles):")
    print(f"  Max decile error : {cal_max:.4f}  (target < 0.05)")
    print(f"  Mean decile error: {cal_mean:.4f}")

print(f"\nMatch outcome rates (test period avg):")
for col, label in [("home_win_rate","Home wins"), ("draw_rate","Draws"), ("away_win_rate","Away wins"), ("over25_rate","Over 2.5")]:
    if col in rd.columns:
        print(f"  {label}: {rd[col].mean():.1%}")

print("\nPer-season detail:")
cols = ["season","n","naive_brier"]
for c in ["dc_brier","xgb_brier","ens_brier"]:
    if c in rd.columns: cols.append(c)
print(rd[cols].to_string(index=False, float_format="{:.4f}".format))

# ─── 7. Recommendations ──────────────────────────────────────────────────────

print("\n" + "=" * 60)
print("RECOMMENDATIONS")
print("=" * 60)

best_b = min(v for v in [dc_b, xgb_b, ens_b] if not math.isnan(v)) if results else float("nan")
improvement_pct = pct(best_b, naive_b) if not math.isnan(best_b) else 0

print()
# Overall signal strength
if math.isnan(best_b):
    print("  [!] No model produced valid predictions. Check data quality.")
elif improvement_pct > -8:
    print("  [!] WEAK: Best model is <8% better than naive baseline.")
    print("      Soccer is inherently low-information, but this suggests")
    print("      insufficient training data or feature issues. Expected")
    print("      range with full backfill and features is 5–12%.")
elif improvement_pct > -12:
    print("  [~] MODERATE: Model shows real but modest improvement.")
    print("      This is typical at this feature-set stage. Full backfill")
    print("      and Phase 2 features should push improvement to 8–12%.")
else:
    print("  [+] GOOD: Model meaningfully beats naive baseline.")

# DC vs XGB
if not math.isnan(dc_b) and not math.isnan(xgb_b):
    if dc_b < xgb_b - 0.002:
        print()
        print("  [DC wins] Dixon-Coles outperforms XGBoost significantly.")
        print("      With only ELO + basic xG features, the Poisson structure")
        print("      of DC provides a better inductive bias than gradient boosting.")
        print("      Add more features before XGBoost adds value to the ensemble.")
    elif xgb_b < dc_b - 0.002:
        print()
        print("  [XGB wins] XGBoost outperforms Dixon-Coles.")
        print("      The tabular features are capturing signal DC misses.")
        print("      Upweight XGBoost in the ensemble blend.")
    else:
        print()
        print("  [DC ≈ XGB] Models are close — averaging them makes sense.")
        print("      The full stacking ensemble (logistic meta-learner) should")
        print("      find better weights than a 50/50 average.")

# O/U specific
if not math.isnan(xgb_ou) and xgb_ou > naive_ou:
    print()
    print("  [O/U concern] XGBoost O/U is WORSE than naive baseline.")
    print("      Without good xG features, LightGBM is fitting noise.")
    print("      O/U predictions will only be reliable once per-game xG")
    print("      features are properly computed from historical data.")
elif not math.isnan(dc_ou) and dc_ou < naive_ou - 0.005:
    print()
    print("  [O/U: DC good] Dixon-Coles O/U beats naive — the goal rate")
    print("      parameters (λ, μ) contain real scoring-rate signal.")

# Calibration
if not math.isnan(cal_max):
    if cal_max > 0.10:
        print()
        print("  [Calibration] Max decile error is high (>10%).")
        print("      The isotonic recalibration in the stacking ensemble is")
        print("      CRITICAL before using these probabilities for bet sizing.")
        print("      Raw probabilities will systematically over/under-bet.")
    elif cal_max > 0.05:
        print()
        print("  [Calibration] Moderate calibration error (5–10%).")
        print("      Isotonic recalibration will help but isn't urgent.")

# Feature priorities
print()
print("  Feature priority for improving Brier score:")
print("  1. More history — backfill to 2013 (already loading).")
print("     Each extra season is worth ~0.002–0.005 Brier improvement.")
print("  2. ELO + xG are by far the most predictive features for MLS.")
print("     If SHAP analysis shows other features near zero, drop them.")
print("  3. Draw prediction is the hardest class (~25% MLS draw rate).")
print("     Draws are essentially random at team level — DC handles them")
print("     better than XGBoost because it uses the full score distribution.")
print("  4. Once live, prioritize CLV over Brier score.")
print("     A model with 3% Brier improvement but positive CLV is more")
print("     valuable than a 6% Brier improvement with negative CLV.")

print()
print("Evaluation complete.")
