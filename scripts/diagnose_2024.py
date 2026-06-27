#!/usr/bin/env python3
"""
Diagnose the 2024 distribution shift.

The Dixon-Coles component is catastrophically bad in 2024 (raw Brier ~0.649) while
strong in 2022-2023. The capped-DC blend is a workaround; this script diagnoses the
root cause so it can be addressed directly rather than patched.

Three diagnostics, per the plan (Phase 4d):
  1. Per-season feature mean / std — surface features whose distribution moved.
  2. Jensen-Shannon divergence (train-pool vs each test season) per feature —
     ranks which features shifted most going into 2024.
  3. Outcome-rate drift — home-win / draw / away-win base rates per season, plus
     DC-fit attack/defence/home-advantage params per season.

DataFrame-in, no database. Reads the parity frame (same data the model trains on).

Usage:
  python scripts/diagnose_2024.py [--frame data/parity_frame.parquet] [--top 15]
"""

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

_LABEL_NAMES = {0: "home", 1: "draw", 2: "away"}


def _load_frame(frame_arg: str) -> tuple[pd.DataFrame, dict]:
    frame = Path(frame_arg)
    meta_path = frame.with_suffix(".meta.json")
    if not frame.exists() and frame.with_suffix(".pkl").exists():
        frame = frame.with_suffix(".pkl")
    if not frame.exists() or not meta_path.exists():
        raise SystemExit(
            f"[diagnose] missing {frame} or {meta_path}\n"
            f"  build: python scripts/eval_baseline.py --cache --seed 42 "
            f"--dump-frame data/parity_frame.parquet"
        )
    try:
        df = pd.read_parquet(frame)
    except Exception:
        df = pd.read_pickle(frame)
    meta = json.loads(meta_path.read_text())
    return df, meta


def _js_divergence(p: np.ndarray, q: np.ndarray) -> float:
    """Jensen-Shannon divergence (base-2, in [0,1]) between two histograms."""
    p = np.asarray(p, dtype=float) + 1e-12
    q = np.asarray(q, dtype=float) + 1e-12
    p /= p.sum()
    q /= q.sum()
    m = 0.5 * (p + q)
    kl = lambda a, b: np.sum(a * np.log2(a / b))
    return float(0.5 * kl(p, m) + 0.5 * kl(q, m))


def _feature_js(train: pd.DataFrame, test: pd.DataFrame, feat: list[str],
                bins: int = 20) -> pd.DataFrame:
    """Per-feature JS divergence between train pool and a test season."""
    rows = []
    for c in feat:
        a = train[c].dropna().values
        b = test[c].dropna().values
        if len(a) < 20 or len(b) < 20:
            continue
        lo = min(a.min(), b.min())
        hi = max(a.max(), b.max())
        if hi <= lo:
            continue
        edges = np.linspace(lo, hi, bins + 1)
        ph, _ = np.histogram(a, bins=edges)
        qh, _ = np.histogram(b, bins=edges)
        rows.append({
            "feature": c,
            "js_div": _js_divergence(ph, qh),
            "train_mean": float(np.mean(a)),
            "test_mean": float(np.mean(b)),
            "mean_shift": float(np.mean(b) - np.mean(a)),
            "train_std": float(np.std(a)),
            "test_std": float(np.std(b)),
        })
    return pd.DataFrame(rows).sort_values("js_div", ascending=False).reset_index(drop=True)


def _outcome_rates(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for s, g in df.groupby("season"):
        g = g.dropna(subset=["label_result"])
        if g.empty:
            continue
        vc = g["label_result"].value_counts(normalize=True)
        rows.append({
            "season": int(s),
            "n": len(g),
            "home_rate": round(float(vc.get(0, 0.0)), 4),
            "draw_rate": round(float(vc.get(1, 0.0)), 4),
            "away_rate": round(float(vc.get(2, 0.0)), 4),
            "avg_total_goals": round(float((g["home_goals"] + g["away_goals"]).mean()), 3),
        })
    return pd.DataFrame(rows).sort_values("season").reset_index(drop=True)


def _dc_params_per_season(df: pd.DataFrame, seasons: list[int],
                          dc_decay_hl: int) -> pd.DataFrame:
    """Fit DC on data BEFORE each season; report home-adv, rho, and attack/def spread."""
    from models.research_model import fit_dc
    rows = []
    for s in seasons:
        train = df[df["season"] < s].dropna(subset=["home_goals", "away_goals"])
        if len(train) < 200:
            continue
        atk, dfd, ha, rho = fit_dc(train, decay_hl=dc_decay_hl)
        atk_v = np.array(list(atk.values()))
        dfd_v = np.array(list(dfd.values()))
        rows.append({
            "fit_for_season": int(s),
            "train_n": len(train),
            "home_adv": round(float(ha), 4),
            "rho": round(float(rho), 4),
            "atk_std": round(float(atk_v.std()), 4),
            "def_std": round(float(dfd_v.std()), 4),
            "atk_range": round(float(atk_v.max() - atk_v.min()), 4),
        })
    return pd.DataFrame(rows)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--frame", default="data/parity_frame.parquet")
    ap.add_argument("--target-season", type=int, default=2024)
    ap.add_argument("--top", type=int, default=15, help="Top-N shifted features to show")
    args = ap.parse_args()

    df, meta = _load_frame(args.frame)
    df["date"] = pd.to_datetime(df["date"])
    feat = [c for c in meta["feat_base"] if c in df.columns]
    ts = args.target_season

    print(f"# 2024 Distribution-Shift Diagnosis\n")
    print(f"Frame: {len(df):,} rows · {len(feat)} Base features · "
          f"seasons {int(df['season'].min())}–{int(df['season'].max())}\n")

    # ── 1. Outcome-rate drift ────────────────────────────────────────────────
    print("## Outcome base rates per season\n")
    rates = _outcome_rates(df)
    print(rates.to_string(index=False))
    print()
    if ts in rates["season"].values:
        pre = rates[rates["season"] < ts]
        cur = rates[rates["season"] == ts].iloc[0]
        if not pre.empty:
            print(f"2024 vs pre-2024 mean: "
                  f"home {cur['home_rate'] - pre['home_rate'].mean():+.4f}, "
                  f"draw {cur['draw_rate'] - pre['draw_rate'].mean():+.4f}, "
                  f"away {cur['away_rate'] - pre['away_rate'].mean():+.4f}, "
                  f"goals {cur['avg_total_goals'] - pre['avg_total_goals'].mean():+.3f}")
    print()

    # ── 2. Per-feature JS divergence (pre-target train pool vs target season) ─
    train_pool = df[df["season"] < ts].dropna(subset=["home_goals", "away_goals"])
    target = df[df["season"] == ts].dropna(subset=["home_goals", "away_goals"])
    print(f"## Top {args.top} shifted features — train(<{ts}) vs {ts} (JS divergence)\n")
    js = _feature_js(train_pool, target, feat)
    print(js.head(args.top).to_string(index=False))
    print()

    # ── 2b. For comparison: JS for a stable season (2023) ────────────────────
    if ts - 1 in df["season"].values:
        prev = df[df["season"] == ts - 1].dropna(subset=["home_goals", "away_goals"])
        prev_train = df[df["season"] < ts - 1].dropna(subset=["home_goals", "away_goals"])
        js_prev = _feature_js(prev_train, prev, feat)
        print(f"## Comparison — mean JS divergence\n")
        print(f"  train(<{ts-1}) vs {ts-1}: {js_prev['js_div'].mean():.4f}")
        print(f"  train(<{ts})   vs {ts}:   {js['js_div'].mean():.4f}")
        print()

    # ── 3. DC param drift across walk-forward fits ───────────────────────────
    print("## Dixon-Coles params (fit on data before each season)\n")
    seasons = [s for s in sorted(df["season"].unique()) if s >= ts - 2]
    dc_params = _dc_params_per_season(df, seasons, meta.get("dc_decay_hl", 120))
    print(dc_params.to_string(index=False))
    print()

    print("## Interpretation hints\n")
    print("- A large draw_rate or goals shift in 2024 vs prior seasons points at an")
    print("  outcome-distribution change DC's Poisson assumption cannot track.")
    print("- High-JS features that the model leans on (elo_diff, xg_diff, form_diff)")
    print("  mean the learned mapping is being applied off-distribution in 2024.")
    print("- DC home_adv / rho drift shows whether the DC fit itself moved.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
