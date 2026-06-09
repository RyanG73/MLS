#!/usr/bin/env python3
"""
Phase 10b parity harness — validate the shared model module (models/research_model.py)
reproduces the research-harness headline (best_brier 0.6363) on a CSV-backed dataset,
with NO database. This is the gate that proves the production-bound model implementation
is faithful before wiring it into the Pi pipeline (where only DB read/write IO differs).

Data: data/parity_frame.parquet + .meta.json, produced by
  python scripts/eval_baseline.py --cache --seed 42 --dump-frame data/parity_frame.parquet

Usage: python scripts/parity_check.py [--frame PATH] [--tol 0.001]
"""

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))

# Parity target = the live champion's avg_brier (experiments/champion.report.json),
# so this check always guards the actual champion rather than a hardcoded snapshot.
# Fallback covers a fresh checkout where the report is absent.
_FALLBACK_TARGET_BRIER = 0.63369  # regress=0.40 champion, promoted 2026-06-07


def _champion_target() -> float:
    report = Path(__file__).parent.parent / "experiments" / "champion.report.json"
    try:
        return float(json.loads(report.read_text())["avg_brier"])
    except Exception:
        return _FALLBACK_TARGET_BRIER


TARGET_BRIER = _champion_target()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--frame", default="data/parity_frame.parquet")
    ap.add_argument("--tol", type=float, default=0.0015,
                    help="Allowed |avg_brier - TARGET_BRIER| for parity PASS")
    args = ap.parse_args()

    frame = Path(args.frame)
    meta_path = frame.with_suffix(".meta.json")
    # Frame may be parquet (if a parquet engine is installed) or pickle (fallback).
    if not frame.exists() and frame.with_suffix(".pkl").exists():
        frame = frame.with_suffix(".pkl")
    if not frame.exists() or not meta_path.exists():
        print(f"[parity] missing {frame} or {meta_path}\n"
              f"  build: python scripts/eval_baseline.py --cache --seed 42 "
              f"--dump-frame {frame}", file=sys.stderr)
        return 1

    try:
        df = pd.read_parquet(frame)
    except Exception:
        df = pd.read_pickle(frame)
    meta = json.loads(meta_path.read_text())
    feat_base = meta["feat_base"]
    test_seasons = meta["test_seasons"]
    weight_hl = meta.get("weight_hl", 6)
    dc_hl = meta.get("dc_decay_hl", 120)
    print(f"[parity] frame {len(df):,} rows | {len(feat_base)} Base features | "
          f"weight_hl={weight_hl} dc_decay_hl={dc_hl} | test={test_seasons}")

    from models.research_model import walk_forward

    res = walk_forward(df, feat_base, test_seasons,
                       weight_hl=weight_hl, dc_decay_hl=dc_hl, seed=42)

    print("\n=== Shared model (models/research_model.py) on CSV frame, no DB ===")
    print(f"  {'Season':>6} {'Brier':>9} {'w_xgb':>7}")
    for yr, b in res["per_season"].items():
        print(f"  {yr:>6} {b:>9.4f} {res['w_xgb'].get(yr, 0):>7.2f}")
    avg = res["avg_brier"]
    print(f"  {'avg':>6} {avg:>9.4f}")

    delta = abs(avg - TARGET_BRIER)
    status = "PASS ✓" if delta <= args.tol else "FAIL ✗"
    print(f"\n[parity] avg_brier={avg:.4f}  target={TARGET_BRIER:.4f}  "
          f"|Δ|={delta:.4f}  (tol {args.tol})  →  {status}")
    print("[parity] Shared model runs DB-free on the CSV frame; production wiring is IO-only.")
    return 0 if delta <= args.tol else 2


if __name__ == "__main__":
    sys.exit(main())
