#!/usr/bin/env python3
"""
Probe: find a calibration method that absorbs the +Referee (ref_draw_rate)
draw-distribution shift WITHOUT the vector-calibration 2024 penalty.

Background
----------
Base + ref_hw_rate + ref_draw_rate improves production-model Brier
(0.63465 -> 0.63397) but regresses calibration (max_decile_cal_err
0.0306 -> 0.0394, > the gate's 0.005 tol) -> REJECTED. Full per-class
("vector") temperature fixes calibration on the cal fold but overfits the
2023 class priors and blows up 2024 (the HFA regime shift).

Approach
--------
Run the validated research_model walk-forward ONCE per test season to obtain the
pre-final-calibration blend probabilities (cal fold + test fold). Cache them.
Then sweep calibration families on those cached arrays instantly:

  scalar        z/T                      (current production; the 0.0394 baseline)
  vector        z_c / T_c                (the known-bad over-flexible method)
  tempbias(λ)   z_c / T + b_c, L2 λ||b|| (temperature + REGULARISED per-class bias)
  vshrink(λ)    z_c / T_c, L2 toward     (regularised vector: shrink T_c to common)

`tempbias` / `vshrink` interpolate scalar (λ→∞) ↔ vector (λ→0). We look for a λ
that recovers calibration (cal_err <= champion + 0.005 = 0.0356) while keeping
the Brier gain (avg <= 0.63397, 2024 <= 0.635364 + 0.0005 = 0.635864).

Metrics match scripts/model_report.py exactly (sum-form Brier; pooled-decile cal
error across all 3 class probs over the full test set).

Usage:
  python scripts/probe_referee_calibration.py [--frame data/parity_frame.parquet]
                                              [--rebuild]   # ignore cached blends
"""

import argparse
import pickle
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import minimize, minimize_scalar
from sklearn.metrics import log_loss

REPO_ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(REPO_ROOT))

from models.metrics import brier_multiclass_sum
from models.research_model import (
    fit_dc, dc_predict_batch, fit_xgb, calibrate_temperature,
    fit_capped_blend, blend,
)

CACHE = REPO_ROOT / "experiments" / "_referee_blends.pkl"
TEST_SEASONS = [2022, 2023, 2024]
EXTRA_FEATS = ["ref_hw_rate", "ref_draw_rate"]

# Reference points (production research_model, from Phase F gate)
CHAMP_AVG, CHAMP_2024, CHAMP_CAL = 0.63465, 0.635364, 0.030601
CAL_TOL, TOL_2024, MIN_GAIN = 0.005, 0.0005, 0.0005


# ── metrics (must match model_report.py) ──────────────────────────────────────
def max_decile_cal_error(probs: np.ndarray, y: np.ndarray, bins: int = 10) -> float:
    y_oh = np.eye(3)[y.astype(int)]
    p, a = probs.flatten(), y_oh.flatten()
    edges = np.linspace(0, 1, bins + 1)
    idx = np.clip(np.digitize(p, edges[1:-1]), 0, bins - 1)
    return round(float(max(
        (abs(p[idx == b].mean() - a[idx == b].mean()) for b in range(bins)
         if (idx == b).sum() >= 20), default=0.0)), 6)


def season_brier(probs, y):
    return brier_multiclass_sum(probs, np.eye(3)[y.astype(int)])


# ── build (expensive: once) → cache cal/test blends per season ────────────────
def build_blends(frame_path: str) -> list:
    frame = Path(frame_path)
    if not frame.exists() and frame.with_suffix(".pkl").exists():
        frame = frame.with_suffix(".pkl")
    meta = pd.read_json(frame.with_suffix(".meta.json"), typ="series")
    feat_base = list(meta["feat_base"])
    try:
        df = pd.read_parquet(frame)
    except Exception:
        df = pd.read_pickle(frame)
    df["date"] = pd.to_datetime(df["date"])
    feat = [c for c in feat_base if c in df.columns] + \
           [c for c in EXTRA_FEATS if c in df.columns]
    print(f"[build] feats={len(feat)} (incl {EXTRA_FEATS}); seasons {TEST_SEASONS}")

    out = []
    for ts in TEST_SEASONS:
        cal_s = ts - 1
        train = df[df["season"] < cal_s].dropna(subset=["home_goals", "away_goals"])
        cal = df[df["season"] == cal_s].dropna(subset=["home_goals", "away_goals"])
        test = df[df["season"] == ts].dropna(subset=["home_goals", "away_goals"])
        if len(train) < 200 or len(cal) < 50 or len(test) < 50:
            print(f"[build] {ts}: insufficient, skip"); continue
        y_cal = cal["label_result"].values.astype(int)
        y_test = test["label_result"].values.astype(int)
        y_cal_oh = np.eye(3)[y_cal]

        atk, dfd, ha, rho = fit_dc(train)
        dc_cal = calibrate_temperature(dc_predict_batch(cal, atk, dfd, ha, rho), y_cal,
                                       dc_predict_batch(cal, atk, dfd, ha, rho))
        dc_te = calibrate_temperature(dc_predict_batch(cal, atk, dfd, ha, rho), y_cal,
                                      dc_predict_batch(test, atk, dfd, ha, rho))
        clf, _ = fit_xgb(train, feat)
        xc_raw = clf.predict_proba(cal[feat].fillna(0).values)
        xgb_cal = calibrate_temperature(xc_raw, y_cal, xc_raw)
        xgb_te = calibrate_temperature(xc_raw, y_cal, clf.predict_proba(test[feat].fillna(0).values))
        w = fit_capped_blend(xgb_cal, dc_cal, y_cal_oh)
        out.append({
            "season": ts,
            "cal_blend": blend(xgb_cal, dc_cal, w),
            "te_blend":  blend(xgb_te, dc_te, w),
            "y_cal": y_cal, "y_test": y_test, "w": round(w, 3),
        })
        print(f"[build] {ts}: cal={len(y_cal)} test={len(y_test)} w_xgb={w:.2f}")
    return out


# ── calibration families (operate on blend probs) ─────────────────────────────
def _softmax(z):
    z = z - z.max(axis=1, keepdims=True)
    e = np.exp(z)
    return e / e.sum(axis=1, keepdims=True)


def cal_scalar(cal_p, y_cal, te_p):
    return calibrate_temperature(cal_p, y_cal, te_p)


def cal_vector(cal_p, y_cal, te_p):
    zc, zt = np.log(np.clip(cal_p, 1e-9, 1)), np.log(np.clip(te_p, 1e-9, 1))

    def nll(T):
        return float(log_loss(y_cal, _softmax(zc / np.clip(T, 0.1, None)), labels=[0, 1, 2]))
    res = minimize(nll, x0=[1, 1, 1], bounds=[(0.3, 5)] * 3, method="L-BFGS-B")
    return _softmax(zt / np.clip(res.x, 0.1, None))


def cal_tempbias(cal_p, y_cal, te_p, lam):
    """z_c / T + b_c, with L2 penalty lam*||b||^2 (b identified by the penalty)."""
    zc, zt = np.log(np.clip(cal_p, 1e-9, 1)), np.log(np.clip(te_p, 1e-9, 1))

    def obj(p):
        T, b = p[0], p[1:]
        probs = _softmax(zc / max(T, 0.1) + b)
        return float(log_loss(y_cal, probs, labels=[0, 1, 2])) + lam * float(b @ b)
    res = minimize(obj, x0=[1.0, 0, 0, 0], method="Nelder-Mead",
                   options={"xatol": 1e-4, "fatol": 1e-7, "maxiter": 2000})
    T, b = res.x[0], res.x[1:]
    return _softmax(zt / max(T, 0.1) + b), (T, b)


def cal_vshrink(cal_p, y_cal, te_p, lam):
    """z_c / T_c with L2 penalty lam*Σ(1/T_c - mean(1/T))^2 (shrink to common temp)."""
    zc, zt = np.log(np.clip(cal_p, 1e-9, 1)), np.log(np.clip(te_p, 1e-9, 1))

    def obj(invT):
        probs = _softmax(zc * invT)            # invT = 1/T per class
        pen = lam * float(((invT - invT.mean()) ** 2).sum())
        return float(log_loss(y_cal, probs, labels=[0, 1, 2])) + pen
    res = minimize(obj, x0=[1, 1, 1], bounds=[(0.2, 3)] * 3, method="L-BFGS-B")
    return _softmax(zt * res.x), res.x


# ── evaluate a calibrated method across seasons ───────────────────────────────
def evaluate(blends, method_fn):
    per_season, pooled_p, pooled_y, extra = {}, [], [], {}
    for bl in blends:
        r = method_fn(bl["cal_blend"], bl["y_cal"], bl["te_blend"])
        te_cal = r[0] if isinstance(r, tuple) else r
        if isinstance(r, tuple):
            extra[bl["season"]] = r[1]
        per_season[str(bl["season"])] = round(season_brier(te_cal, bl["y_test"]), 6)
        pooled_p.append(te_cal); pooled_y.append(bl["y_test"])
    P = np.vstack(pooled_p); Y = np.concatenate(pooled_y)
    avg = round(float(np.mean(list(per_season.values()))), 6)
    cal = max_decile_cal_error(P, Y)
    return avg, per_season, cal, extra


def verdict(avg, per_season, cal):
    s2024 = per_season.get("2024", 9)
    gain = CHAMP_AVG - avg
    ok_core = gain >= MIN_GAIN
    ok_2024 = s2024 <= CHAMP_2024 + TOL_2024
    ok_cal = cal <= CHAMP_CAL + CAL_TOL
    tag = "PROMOTE" if (ok_core and ok_2024 and ok_cal) else "reject"
    flags = []
    if not ok_core: flags.append(f"core(gain {gain:+.4f})")
    if not ok_2024: flags.append(f"2024({s2024:.4f})")
    if not ok_cal:  flags.append(f"cal({cal:.4f})")
    return tag, (", ".join(flags) if flags else "all gates pass")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--frame", default="data/parity_frame.parquet")
    ap.add_argument("--rebuild", action="store_true")
    args = ap.parse_args()

    if CACHE.exists() and not args.rebuild:
        blends = pickle.loads(CACHE.read_bytes())
        print(f"[cache] loaded blends for seasons {[b['season'] for b in blends]}")
    else:
        blends = build_blends(args.frame)
        CACHE.write_bytes(pickle.dumps(blends))
        print(f"[cache] wrote {CACHE}")

    print(f"\nReference — champion: avg {CHAMP_AVG} · 2024 {CHAMP_2024} · cal {CHAMP_CAL}")
    print(f"Gate: gain>={MIN_GAIN}, 2024<={CHAMP_2024+TOL_2024:.4f}, cal<={CHAMP_CAL+CAL_TOL:.4f}\n")
    print(f"{'method':<22}{'avg':>9}{'2024':>9}{'cal_err':>9}  verdict")
    print("-" * 70)

    methods = [("scalar (current)", cal_scalar), ("vector", cal_vector)]
    for lam in (5.0, 2.0, 1.0, 0.5, 0.2, 0.1, 0.05):
        methods.append((f"tempbias λ={lam}", lambda c, y, t, L=lam: cal_tempbias(c, y, t, L)))
    for lam in (2.0, 1.0, 0.5, 0.2, 0.1):
        methods.append((f"vshrink λ={lam}", lambda c, y, t, L=lam: cal_vshrink(c, y, t, L)))

    results = []
    for name, fn in methods:
        avg, ps, cal, extra = evaluate(blends, fn)
        tag, detail = verdict(avg, ps, cal)
        mark = "✓" if tag == "PROMOTE" else " "
        print(f"{name:<22}{avg:>9.5f}{ps.get('2024',0):>9.5f}{cal:>9.5f}  [{mark}] {detail}")
        results.append((name, avg, ps, cal, tag, detail))

    winners = [r for r in results if r[4] == "PROMOTE"]
    print("\n" + "=" * 70)
    if winners:
        best = min(winners, key=lambda r: r[1])
        print(f"BEST PROMOTABLE: {best[0]} — avg {best[1]:.5f}, 2024 {best[2]['2024']:.5f}, "
              f"cal {best[3]:.5f}\n  per-season {best[2]}")
    else:
        print("No calibration method clears all three gates on the referee model.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
