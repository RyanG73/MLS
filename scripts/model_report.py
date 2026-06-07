#!/usr/bin/env python3
"""
Standardized model-run report (Phase 4a/4b).

Runs the canonical model (models/research_model.walk_forward_predictions) on a data
snapshot, then emits a full review report: run provenance, overall metrics
(standardized sum-form Brier), calibration summary, and a SLICE table —
season · month · predicted-class · confidence bucket · per-class calibration · team.

The JSON output is the machine-readable artifact consumed by scripts/promotion_gate.py.
The markdown is the human-readable record for the experiment log.

This runs against the canonical model + parity frame, NOT the eval_baseline monolith,
so it produces per-match predictions that can be sliced. Market/edge slices require
the odds DB and are reported as "deferred (no odds in frame)".

Usage:
  python scripts/model_report.py [--frame data/parity_frame.parquet] \
      [--out experiments/report_<id>.json] [--label champion]
"""

import argparse
import datetime
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))

from models.metrics import (brier_multiclass_sum, per_class_brier,
                            log_loss_multiclass)

REPO_ROOT = Path(__file__).parent.parent.resolve()


def _git_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "-C", str(REPO_ROOT), "rev-parse", "HEAD"], text=True).strip()
    except Exception:
        return "unknown"


def _source_health_snapshot() -> dict:
    """Best-effort per-source coverage gate status (Phase A → promotion gate).

    Returns {source: {parsed, floor, ok, success, error}} when the source_runs
    table is reachable; {} otherwise (no DB at report time → gate skips the check).
    """
    try:
        from data_pipeline.source_health import coverage_gate_status
        return coverage_gate_status()
    except Exception:
        return {}


def _load_frame(frame_arg: str):
    frame = Path(frame_arg)
    meta_path = frame.with_suffix(".meta.json")
    if not frame.exists() and frame.with_suffix(".pkl").exists():
        frame = frame.with_suffix(".pkl")
    if not frame.exists() or not meta_path.exists():
        raise SystemExit(f"[report] missing {frame} or {meta_path}")
    try:
        df = pd.read_parquet(frame)
    except Exception:
        df = pd.read_pickle(frame)
    snapshot_hash = hashlib.md5(frame.read_bytes()).hexdigest()[:16]
    return df, json.loads(meta_path.read_text()), snapshot_hash


def _metrics(probs: np.ndarray, y: np.ndarray) -> dict:
    """Standard metric block for a set of predictions."""
    if len(y) == 0:
        return {"n": 0}
    y_oh = np.eye(3)[y.astype(int)]
    pc = per_class_brier(probs, y_oh)
    return {
        "n": int(len(y)),
        "brier_sum": round(brier_multiclass_sum(probs, y_oh), 6),
        "log_loss": round(log_loss_multiclass(probs, y), 6),
        "accuracy": round(float(np.mean(np.argmax(probs, axis=1) == y)), 6),
        "brier_home": round(pc[0], 6),
        "brier_draw": round(pc[1], 6),
        "brier_away": round(pc[2], 6),
    }


def _max_decile_cal_error(probs: np.ndarray, y: np.ndarray, bins: int = 10) -> float:
    """Max |mean_pred - mean_actual| over deciles, pooled across the 3 class probs."""
    y_oh = np.eye(3)[y.astype(int)]
    p = probs.flatten()
    a = y_oh.flatten()
    edges = np.linspace(0, 1, bins + 1)
    idx = np.clip(np.digitize(p, edges[1:-1]), 0, bins - 1)
    max_err = 0.0
    for b in range(bins):
        m = idx == b
        if m.sum() >= 20:
            max_err = max(max_err, abs(p[m].mean() - a[m].mean()))
    return round(float(max_err), 6)


def _slice_table(preds: pd.DataFrame) -> dict:
    """Compute the slice metrics block."""
    P = preds[["prob_home", "prob_draw", "prob_away"]].values
    y = preds["label_result"].values.astype(int)
    out = {}

    def _by(key_series, name):
        rows = {}
        for k, idx in preds.groupby(key_series).groups.items():
            ii = preds.index.get_indexer(idx)
            rows[str(k)] = _metrics(P[ii], y[ii])
        out[name] = rows

    # season
    _by(preds["season"], "by_season")
    # month
    _by(pd.to_datetime(preds["date"]).dt.month, "by_month")
    # predicted class (home/draw/away favorite)
    pred_cls = pd.Series(np.argmax(P, axis=1), index=preds.index).map(
        {0: "pred_home", 1: "pred_draw", 2: "pred_away"})
    _by(pred_cls, "by_predicted_class")
    # confidence bucket (max prob)
    conf = pd.Series(P.max(axis=1), index=preds.index)
    conf_bucket = pd.cut(conf, bins=[0, 0.4, 0.5, 0.6, 1.0],
                         labels=["<40%", "40-50%", "50-60%", ">60%"])
    _by(conf_bucket, "by_confidence")
    # favorite vs underdog correctness already in predicted_class; add home/away venue
    # (every row is a home/away pairing; report home-fav vs away-fav split)
    # team-level (home team) — top regressions surfaced by the gate
    _by(preds["home_team"], "by_home_team")

    # per-class calibration (reliability) — home/draw/away separately
    cal = {}
    for ci, cname in [(0, "home"), (1, "draw"), (2, "away")]:
        pc = P[:, ci]
        ac = (y == ci).astype(float)
        edges = np.linspace(0, 1, 11)
        idx = np.clip(np.digitize(pc, edges[1:-1]), 0, 9)
        max_err = 0.0
        for b in range(10):
            m = idx == b
            if m.sum() >= 20:
                max_err = max(max_err, abs(pc[m].mean() - ac[m].mean()))
        cal[cname] = round(float(max_err), 6)
    out["per_class_calibration_error"] = cal
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--frame", default="data/parity_frame.parquet")
    ap.add_argument("--out", default=None, help="JSON output path")
    ap.add_argument("--label", default="run", help="champion / challenger / run label")
    ap.add_argument("--test-seasons", default=None,
                    help="Comma-separated override; default = meta test_seasons")
    args = ap.parse_args()

    df, meta, snapshot_hash = _load_frame(args.frame)
    df["date"] = pd.to_datetime(df["date"])
    feat_base = meta["feat_base"]
    if args.test_seasons:
        test_seasons = [int(s) for s in args.test_seasons.split(",")]
    else:
        # default to seasons that actually evaluate (skip 2021 COVID cal fold)
        test_seasons = [s for s in meta["test_seasons"] if s >= 2022]

    from models.research_model import walk_forward_predictions

    print(f"[report] frame {len(df):,} rows · snapshot {snapshot_hash} · "
          f"test {test_seasons}")
    preds, w_used = walk_forward_predictions(
        df, feat_base, test_seasons,
        weight_hl=meta.get("weight_hl", 6), dc_decay_hl=meta.get("dc_decay_hl", 120))
    if preds.empty:
        raise SystemExit("[report] no predictions produced")

    P = preds[["prob_home", "prob_draw", "prob_away"]].values
    y = preds["label_result"].values.astype(int)

    overall = _metrics(P, y)
    cal_err = _max_decile_cal_error(P, y)
    slices = _slice_table(preds)
    per_season = {s: m["brier_sum"] for s, m in slices["by_season"].items()}
    coverage = {s: m["n"] for s, m in slices["by_season"].items()}

    run_id = f"{args.label}-{_git_sha()[:8]}-" \
             f"{datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S')}"

    report = {
        "run_id": run_id,
        "label": args.label,
        "git_sha": _git_sha(),
        "timestamp": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "model": "models/research_model.py (DC + XGB + temp + capped blend + 2nd-pass)",
        "metric_convention": "brier_sum_form",
        "data_snapshot_hash": snapshot_hash,
        "frame": str(Path(args.frame).name),
        "test_seasons": test_seasons,
        "w_xgb": w_used,
        "overall": overall,
        "avg_brier": round(float(np.mean(list(per_season.values()))), 6),
        "max_decile_cal_error": cal_err,
        "per_season": per_season,
        "coverage_by_season": coverage,
        "slices": slices,
        "source_health": _source_health_snapshot(),
        "market_slices": "deferred (no odds in frame; run against odds DB for edge/CLV slices)",
    }

    out_path = (Path(args.out) if args.out else
                REPO_ROOT / "experiments" / f"{run_id}.report.json").resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2))

    # ── Markdown to stdout ───────────────────────────────────────────────────
    print(f"\n# Model Report — {run_id}\n")
    print(f"- model: {report['model']}")
    print(f"- git: {report['git_sha'][:8]} · snapshot: {snapshot_hash} · "
          f"metric: sum-form Brier")
    print(f"- avg Brier: **{report['avg_brier']:.4f}** · cal_err: "
          f"{cal_err:.4f} · acc: {overall['accuracy']:.3f} · n={overall['n']}")
    print(f"- per-season: " + " · ".join(f"{s}={b:.4f}" for s, b in per_season.items()))
    print(f"- per-class Brier: H={overall['brier_home']:.4f} "
          f"D={overall['brier_draw']:.4f} A={overall['brier_away']:.4f}")
    print(f"- per-class cal_err: " +
          " ".join(f"{k}={v:.3f}" for k, v in slices['per_class_calibration_error'].items()))
    print(f"\n## Confidence buckets")
    for k, m in slices["by_confidence"].items():
        if m.get("n", 0):
            print(f"  {k:>7}: n={m['n']:>4}  brier={m['brier_sum']:.4f}  acc={m['accuracy']:.3f}")
    print(f"\n## Worst 5 home-team slices (by Brier)")
    teams = [(k, m) for k, m in slices["by_home_team"].items() if m.get("n", 0) >= 10]
    for k, m in sorted(teams, key=lambda kv: -kv[1]["brier_sum"])[:5]:
        print(f"  {k:<24} n={m['n']:>3}  brier={m['brier_sum']:.4f}")
    try:
        shown = out_path.relative_to(REPO_ROOT)
    except ValueError:
        shown = out_path
    print(f"\nReport written → {shown}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
