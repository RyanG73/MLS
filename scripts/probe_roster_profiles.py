#!/usr/bin/env python3
"""
B5 probe — MLS roster-construction features (DP / U22 / TAM / GAM) from the
American-Soccer-Analysis/mls-roster-profiles repo.

The repo only covers 2024+, so a standard walk-forward can't test it (training
predates the data). This runs the only valid probe: a SINGLE split, train=2024
→ test=2025, with the roster snapshot of each season (leakage-safe, near-kickoff)
joined by team_id. Compares Base vs Base+roster bagged-XGB Brier on 2025.

Low statistical power (one ~540-match fold); a probe, not a gate experiment.

Usage: python scripts/probe_roster_profiles.py
Requires data/roster_profiles/{2024,2025}.json (downloaded from the repo).
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from models.research_model import fit_xgb, bag_proba, calibrate_temperature  # noqa: E402
from models.metrics import brier_multiclass_sum  # noqa: E402

_DP = {"Designated Player", "Young Designated Player"}


def _roster_feats(path: Path) -> dict:
    """team_id -> {dp_count, u22_count, tam_count, gam_available, intl_slots}."""
    d = json.loads(path.read_text())
    out = {}
    for t in d["teams"]:
        desigs = [p.get("roster_designation") for p in t["players"]]
        out[t["id"]] = {
            "dp_count": sum(x in _DP for x in desigs),
            "u22_count": sum(x == "U22 Initiative" for x in desigs),
            "tam_count": sum(x == "TAM Player" for x in desigs),
            "gam_available": float(t.get("gam_available") or 0),
            "intl_slots": float(t.get("international_slots") or 0),
        }
    return out


def _attach(df: pd.DataFrame, feats_by_season: dict) -> pd.DataFrame:
    df = df.copy()
    cols = ["dp_count", "u22_count", "tam_count", "gam_available", "intl_slots"]
    for side in ("home", "away"):
        for c in cols:
            df[f"{side}_{c}"] = [
                feats_by_season.get(s, {}).get(t, {}).get(c, 0.0)
                for s, t in zip(df["season"], df[f"{side}_team"])]
    for c in cols:
        df[f"{c}_diff"] = df[f"home_{c}"] - df[f"away_{c}"]
    roster_cols = ([f"home_{c}" for c in cols] + [f"away_{c}" for c in cols]
                   + [f"{c}_diff" for c in cols])
    return df, roster_cols


def _fit_eval(train, test, feat, y_test_oh, seed=42):
    clfs, _ = fit_xgb(train, feat, n_bags=5, seed=seed)
    raw_tr = bag_proba(clfs, train[feat].fillna(0).values)
    raw_te = bag_proba(clfs, test[feat].fillna(0).values)
    y_tr = train["label_result"].values.astype(int)
    cal_te = calibrate_temperature(raw_tr, y_tr, raw_te)
    return brier_multiclass_sum(cal_te, y_test_oh)


def main() -> int:
    frame = Path("data/parity_frame.parquet")
    df = pd.read_parquet(frame)
    meta = json.loads(frame.with_suffix(".meta.json").read_text())
    base = [c for c in meta["feat_base"] if c in df.columns]

    rp_dir = Path("data/roster_profiles")
    feats = {2024: _roster_feats(rp_dir / "2024.json"),
             2025: _roster_feats(rp_dir / "2025.json")}
    df, roster_cols = _attach(df, feats)

    train = df[df["season"] == 2024].dropna(subset=["label_result"])
    test = df[df["season"] == 2025].dropna(subset=["label_result"])
    y_te_oh = np.eye(3)[test["label_result"].values.astype(int)]
    print(f"[B5] single fold: train=2024 (n={len(train)}) → test=2025 (n={len(test)})")

    b_base = np.mean([_fit_eval(train, test, base, y_te_oh, s) for s in (42, 1, 2)])
    b_rost = np.mean([_fit_eval(train, test, base + roster_cols, y_te_oh, s)
                      for s in (42, 1, 2)])
    print(f"[B5] Base            2025 Brier: {b_base:.5f}")
    print(f"[B5] Base + roster   2025 Brier: {b_rost:.5f}")
    print(f"[B5] Δ (roster − base): {b_rost - b_base:+.5f}  "
          f"({'helps' if b_rost < b_base - 0.001 else 'marginal/neutral' if b_rost < b_base else 'hurts'})")
    print("[B5] NOTE: single fold, train-on-2024-only — low power; not gate-promotable.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
