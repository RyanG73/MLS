#!/usr/bin/env python3
"""
Probe: does a shorter Dixon-Coles recent-seasons window help 2024?

The 2024 diagnosis (docs/2024-diagnosis.md) found DC's home_adv is stale — it is fit
on `recent_seasons=4` of history, which through 2024 is dominated by the high-HFA
2017-2021 era. Hypothesis: a shorter window leans on the low-HFA 2022-2023 seasons and
reduces DC's home over-prediction in 2024.

Tests recent_seasons in {2, 3, 4, 5} for the DC component inside the full blend
pipeline. XGB is fit ONCE per test season and reused across windows (XGB is independent
of the DC window), so the cost is dominated by 4 windows × 3 seasons DC fits.

Research probe only; does not modify production. Promote a winner through the gate.

Usage: python scripts/probe_dc_window.py [--frame data/parity_frame.parquet]
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))

from models.metrics import brier_multiclass_sum


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


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--frame", default="data/parity_frame.parquet")
    ap.add_argument("--test-seasons", default="2022,2023,2024")
    ap.add_argument("--windows", default="2,3,4,5")
    args = ap.parse_args()

    df, meta = _load_frame(args.frame)
    df["date"] = pd.to_datetime(df["date"])
    feat = [c for c in meta["feat_base"] if c in df.columns]
    test_seasons = [int(s) for s in args.test_seasons.split(",")]
    windows = [int(w) for w in args.windows.split(",")]
    dc_hl = meta.get("dc_decay_hl", 120)

    from models.research_model import (fit_dc, dc_predict_batch, fit_xgb, bag_proba,
                                       calibrate_temperature, fit_capped_blend, blend)

    print("# Probe: Dixon-Coles recent-seasons window sweep\n")
    print(f"Frame {len(df):,} rows · test {test_seasons} · windows {windows}\n")

    # results[window][season] = brier
    results = {w: {} for w in windows}
    for ts in test_seasons:
        cal_s = ts - 1
        train = df[df["season"] < cal_s].dropna(subset=["home_goals", "away_goals"])
        cal = df[df["season"] == cal_s].dropna(subset=["home_goals", "away_goals"])
        test = df[df["season"] == ts].dropna(subset=["home_goals", "away_goals"])
        if len(train) < 200 or len(cal) < 50 or len(test) < 50:
            continue
        y_cal = cal["label_result"].values.astype(int)
        y_te = test["label_result"].values.astype(int)
        y_cal_oh, y_te_oh = np.eye(3)[y_cal], np.eye(3)[y_te]

        # XGB fit once, reused for all windows
        clfs, _ = fit_xgb(train, feat, weight_hl=meta.get("weight_hl", 6))
        xc = bag_proba(clfs, cal[feat].fillna(0).values)
        xt = bag_proba(clfs, test[feat].fillna(0).values)
        xgb_cal = calibrate_temperature(xc, y_cal, xc)
        xgb_te = calibrate_temperature(xc, y_cal, xt)

        for w_yr in windows:
            atk, dfd, ha, rho = fit_dc(train, decay_hl=dc_hl, recent_seasons=w_yr)
            dc_cal = calibrate_temperature(dc_predict_batch(cal, atk, dfd, ha, rho), y_cal,
                                           dc_predict_batch(cal, atk, dfd, ha, rho))
            dc_te = calibrate_temperature(dc_predict_batch(cal, atk, dfd, ha, rho), y_cal,
                                          dc_predict_batch(test, atk, dfd, ha, rho))
            wb = fit_capped_blend(xgb_cal, dc_cal, y_cal_oh)
            cal_blend = blend(xgb_cal, dc_cal, wb)
            te_blend = blend(xgb_te, dc_te, wb)
            ens = calibrate_temperature(cal_blend, y_cal, te_blend)
            b = brier_multiclass_sum(ens, y_te_oh)
            results[w_yr][ts] = b
            print(f"  ts={ts} window={w_yr}: Brier={b:.4f} (w_xgb={wb:.2f}, dc_home_adv={ha:.3f})")
        print()

    print("## Summary (avg sum-form Brier by DC window)\n")
    print(f"  {'window':>7} {'2022':>8} {'2023':>8} {'2024':>8} {'avg':>8}")
    base_avg = None
    for w_yr in windows:
        per = results[w_yr]
        avg = float(np.mean(list(per.values()))) if per else float("nan")
        if w_yr == 4:
            base_avg = avg
        print(f"  {w_yr:>7} " + " ".join(f"{per.get(ts, float('nan')):>8.4f}" for ts in test_seasons)
              + f" {avg:>8.4f}")
    print()
    if base_avg is not None:
        best_w = min(windows, key=lambda w: np.mean(list(results[w].values())) if results[w] else 9)
        best_avg = float(np.mean(list(results[best_w].values())))
        print(f"  Current default window=4 → avg {base_avg:.4f}")
        print(f"  Best window={best_w} → avg {best_avg:.4f}  (Δ {base_avg-best_avg:+.4f})")
        verdict = ("PROMOTE" if best_w != 4 and base_avg - best_avg > 0.0005
                   and results[best_w].get(2024, 9) <= results[4].get(2024, 0) + 1e-9
                   else "KEEP window=4")
        print(f"  Verdict: {verdict} (KEEP bar >0.0005 AND no 2024 regression)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
