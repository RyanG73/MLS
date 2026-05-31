#!/usr/bin/env python3
"""
Phase 10b parity harness — validate PRODUCTION model classes on a CSV-backed dataset,
no database. Confirms the production code reproduces the research-harness result before
porting to the Pi (where only the DB read/write IO differs).

Data: data/parity_frame.parquet (produced by
      `python scripts/eval_baseline.py --cache --seed 42 --dump-frame data/parity_frame.parquet`)

This first increment validates the production DixonColesModel (DataFrame-in, DB-agnostic).
The XGB + capped-DC-blend ensemble parity is the next increment (needs the structural
production port: drop O/U, grid instead of Optuna, capped-DC blend, temperature cal).

Usage: python scripts/parity_check.py [--frame PATH] [--test-seasons 2022 2023 2024]
"""

import argparse
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))


def multiclass_brier(y_true: np.ndarray, probs: np.ndarray) -> float:
    """y_true in {0,1,2} (home/draw/away); probs Nx3."""
    oh = np.eye(3)[y_true]
    return float(np.mean(np.sum((probs - oh) ** 2, axis=1)))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--frame", default="data/parity_frame.parquet")
    ap.add_argument("--test-seasons", nargs="+", type=int, default=[2022, 2023, 2024])
    args = ap.parse_args()

    if not Path(args.frame).exists():
        print(f"[parity] frame not found: {args.frame}\n"
              f"  Build it: python scripts/eval_baseline.py --cache --seed 42 "
              f"--dump-frame {args.frame}", file=sys.stderr)
        return 1

    df = pd.read_parquet(args.frame)
    df["date"] = pd.to_datetime(df["date"])
    print(f"[parity] frame: {len(df):,} rows, seasons "
          f"{int(df['season'].min())}–{int(df['season'].max())}")

    from models.dixon_coles import DixonColesModel

    print("\n=== Production DixonColesModel — walk-forward parity ===")
    print(f"  {'Season':>6} {'n_test':>7} {'DC Brier':>10} {'naive':>8}")
    print("  " + "-" * 36)

    rows = []
    for ts in args.test_seasons:
        train = df[df["season"] < ts].dropna(subset=["home_goals", "away_goals"])
        test = df[df["season"] == ts].dropna(subset=["home_goals", "away_goals"])
        if len(train) < 200 or len(test) < 50:
            print(f"  {ts:>6}  insufficient data, skip")
            continue

        dc = DixonColesModel().fit(train)
        probs, y = [], []
        for _, r in test.iterrows():
            try:
                p = dc.predict(r["home_team"], r["away_team"])
                probs.append([p["prob_home"], p["prob_draw"], p["prob_away"]])
                # label_result: 0=home,1=draw,2=away
                y.append(int(r["label_result"]))
            except Exception:
                continue
        probs = np.array(probs)
        y = np.array(y)
        # normalize any rows that don't sum to 1
        probs = probs / probs.sum(axis=1, keepdims=True).clip(1e-9, None)
        dc_brier = multiclass_brier(y, probs)

        # naive baseline = train-set outcome base rates
        base = np.bincount(train["label_result"].astype(int).values, minlength=3) / len(train)
        naive = multiclass_brier(y, np.tile(base, (len(y), 1)))

        print(f"  {ts:>6} {len(y):>7} {dc_brier:>10.4f} {naive:>8.4f}")
        rows.append((ts, dc_brier, naive))

    if rows:
        avg_dc = np.mean([r[1] for r in rows])
        avg_nv = np.mean([r[2] for r in rows])
        print("  " + "-" * 36)
        print(f"  {'avg':>6} {'':>7} {avg_dc:>10.4f} {avg_nv:>8.4f}")
        print(f"\n[parity] Production DixonColesModel runs DB-free on the CSV frame ✓")
        print(f"  DC-alone avg Brier {avg_dc:.4f} (research DC-alone calibrated ≈ 0.648;")
        print(f"  the 0.6363 headline is the capped-DC BLEND with XGB — next increment).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
