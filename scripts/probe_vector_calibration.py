#!/usr/bin/env python3
"""
Probe: per-class (vector) calibration vs scalar temperature on the blend output.

The 2024 diagnosis (docs/2024-diagnosis.md) showed a directional home->away mass
shift that a single scalar temperature cannot correct. This probe compares, on the
SAME walk-forward folds the production model uses:

  A. scalar temperature on the blend output           (current canonical pipeline)
  B. vector scaling on the blend output: z'_c = w_c*log(p_c) + b_c, softmax,
     6 params fit on the cal fold by NLL                (candidate)

Reports per-season + average sum-form Brier and per-class Brier for each, so we can
see whether vector calibration helps overall, helps draws, and — critically —
whether it helps 2024 (it may not: the cal fold predates the shift).

This is a research probe; it does NOT modify the production model. If B wins through
the promotion gate, port it into models/research_model.py.

Usage:
  python scripts/probe_vector_calibration.py [--frame data/parity_frame.parquet]
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from sklearn.metrics import log_loss

sys.path.insert(0, str(Path(__file__).parent.parent))

from models.metrics import brier_multiclass_sum, per_class_brier


def _load_frame(frame_arg: str):
    frame = Path(frame_arg)
    meta_path = frame.with_suffix(".meta.json")
    if not frame.exists() and frame.with_suffix(".pkl").exists():
        frame = frame.with_suffix(".pkl")
    if not frame.exists() or not meta_path.exists():
        raise SystemExit(f"[probe] missing {frame} or {meta_path}")
    try:
        df = pd.read_parquet(frame)
    except Exception:
        df = pd.read_pickle(frame)
    return df, json.loads(meta_path.read_text())


def _vector_calibrate(blend_cal, y_cal, blend_te):
    """Vector scaling z'_c = w_c*log(p_c) + b_c, softmax. 6 params fit on cal NLL."""
    log_cal = np.log(np.clip(blend_cal, 1e-9, 1.0))
    log_te = np.log(np.clip(blend_te, 1e-9, 1.0))

    def _apply(params, logp):
        w = params[:3]
        b = params[3:]
        z = logp * w + b
        z -= z.max(axis=1, keepdims=True)
        e = np.exp(z)
        return e / e.sum(axis=1, keepdims=True)

    def _nll(params):
        return float(log_loss(y_cal, _apply(params, log_cal), labels=[0, 1, 2]))

    x0 = np.array([1.0, 1.0, 1.0, 0.0, 0.0, 0.0])
    res = minimize(_nll, x0, method="Nelder-Mead",
                   options={"maxiter": 2000, "xatol": 1e-4, "fatol": 1e-7})
    return _apply(res.x, log_te), res.x


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--frame", default="data/parity_frame.parquet")
    ap.add_argument("--test-seasons", default="2022,2023,2024")
    args = ap.parse_args()

    df, meta = _load_frame(args.frame)
    df["date"] = pd.to_datetime(df["date"])
    feat = [c for c in meta["feat_base"] if c in df.columns]
    test_seasons = [int(s) for s in args.test_seasons.split(",")]

    from models.research_model import (fit_dc, dc_predict_batch, fit_xgb, bag_proba,
                                       calibrate_temperature, fit_capped_blend, blend)

    print("# Probe: vector vs scalar calibration on the blend output\n")
    print(f"Frame {len(df):,} rows · {len(feat)} features · test {test_seasons}\n")

    rows = []
    for ts in test_seasons:
        cal_s = ts - 1
        train = df[df["season"] < cal_s].dropna(subset=["home_goals", "away_goals"])
        cal = df[df["season"] == cal_s].dropna(subset=["home_goals", "away_goals"])
        test = df[df["season"] == ts].dropna(subset=["home_goals", "away_goals"])
        if len(train) < 200 or len(cal) < 50 or len(test) < 50:
            print(f"  {ts}: skipped (insufficient data)")
            continue
        y_cal = cal["label_result"].values.astype(int)
        y_te = test["label_result"].values.astype(int)
        y_cal_oh, y_te_oh = np.eye(3)[y_cal], np.eye(3)[y_te]

        atk, dfd, ha, rho = fit_dc(train, decay_hl=meta.get("dc_decay_hl", 120))
        dc_cal = calibrate_temperature(dc_predict_batch(cal, atk, dfd, ha, rho), y_cal,
                                       dc_predict_batch(cal, atk, dfd, ha, rho))
        dc_te = calibrate_temperature(dc_predict_batch(cal, atk, dfd, ha, rho), y_cal,
                                      dc_predict_batch(test, atk, dfd, ha, rho))
        clfs, _ = fit_xgb(train, feat, weight_hl=meta.get("weight_hl", 6))
        xc = bag_proba(clfs, cal[feat].fillna(0).values)
        xt = bag_proba(clfs, test[feat].fillna(0).values)
        xgb_cal = calibrate_temperature(xc, y_cal, xc)
        xgb_te = calibrate_temperature(xc, y_cal, xt)
        w = fit_capped_blend(xgb_cal, dc_cal, y_cal_oh)
        cal_blend = blend(xgb_cal, dc_cal, w)
        te_blend = blend(xgb_te, dc_te, w)

        # A. scalar temperature (current)
        a_te = calibrate_temperature(cal_blend, y_cal, te_blend)
        # B. vector scaling (candidate)
        b_te, vparams = _vector_calibrate(cal_blend, y_cal, te_blend)

        a_b = brier_multiclass_sum(a_te, y_te_oh)
        b_b = brier_multiclass_sum(b_te, y_te_oh)
        a_pc = per_class_brier(a_te, y_te_oh)
        b_pc = per_class_brier(b_te, y_te_oh)
        rows.append((ts, a_b, b_b, a_pc, b_pc, vparams))
        print(f"  {ts}: scalar={a_b:.4f}  vector={b_b:.4f}  Δ={a_b-b_b:+.4f}  "
              f"(vector better if Δ>0)")
        print(f"        per-class scalar  H={a_pc[0]:.4f} D={a_pc[1]:.4f} A={a_pc[2]:.4f}")
        print(f"        per-class vector  H={b_pc[0]:.4f} D={b_pc[1]:.4f} A={b_pc[2]:.4f}")
        print(f"        vector w={np.round(vparams[:3],3)} b={np.round(vparams[3:],3)}")

    if rows:
        a_avg = np.mean([r[1] for r in rows])
        b_avg = np.mean([r[2] for r in rows])
        print(f"\n  AVG: scalar={a_avg:.4f}  vector={b_avg:.4f}  Δ={a_avg-b_avg:+.4f}")
        print(f"\n  Verdict: {'VECTOR WINS' if b_avg < a_avg - 0.0005 else 'KEEP SCALAR'} "
              f"(KEEP bar: vector must beat scalar by >0.0005)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
