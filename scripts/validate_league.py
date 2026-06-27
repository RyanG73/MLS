#!/usr/bin/env python3
"""
Per-league model validation (WS2) — does the MLS champion pipeline transfer?

Loads a league's canonical match frame from the Understat adapter, builds the
league-agnostic feature set (ELO + rolling xG/form), and runs the validated
walk-forward pipeline (research_model.walk_forward) with the MLS champion config
unchanged. Reports per-season + average sum-form Brier against a base-rate naive
baseline, so each European league gets a number directly comparable to MLS's
champion 0.6330 (4-fold 2022-2025).

No conferences, no playoffs (is_playoff is 0 for every European top flight). No
COVID-season exclusion: unlike MLS's 2020 bubble, the European 2019-20/2020-21
seasons were completed (behind closed doors), so they stay in training. Ligue 1
is the lone exception — its 2019-20 was cancelled, so ~100 matches are simply
absent from the frame (the adapter marks them unplayed).

Usage:
    python scripts/validate_league.py --all
    python scripts/validate_league.py --league epl --quick   # n_bags=1, fast
    python scripts/validate_league.py --league epl --seasons 2023,2024,2025
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import numpy as np

from data_pipeline.understat import BIG5, canonical_frame
from models.research_model import DEFAULT_N_BAGS, walk_forward
from scripts.eval.league_features import LEAGUE_FEAT_BASE, build_league_features

DEFAULT_TEST_SEASONS = [2022, 2023, 2024, 2025]


def _played_frame(league_id: str):
    """Canonical frame restricted to completed matches, model-ready dtypes."""
    df = canonical_frame(league_id)
    df = df[df["is_result"]].copy()
    df["home_goals"] = df["home_goals"].astype(int)
    df["away_goals"] = df["away_goals"].astype(int)
    df["label_result"] = df["label_result"].astype(int)
    return df


def _naive_brier(df, test_seasons) -> float:
    """Sum-form Brier of the base-rate prediction (train base rates per fold)."""
    briers = []
    for ts in test_seasons:
        train = df[df["season"] < ts - 1]
        test = df[df["season"] == ts]
        if len(train) < 200 or len(test) < 50:
            continue
        freq = np.bincount(train["label_result"].values, minlength=3) / len(train)
        y_oh = np.eye(3)[test["label_result"].values]
        briers.append(float(np.mean(np.sum(
            (np.tile(freq, (len(test), 1)) - y_oh) ** 2, axis=1))))
    return round(float(np.mean(briers)), 4) if briers else float("nan")


def validate(league_id: str, test_seasons, n_bags: int) -> dict:
    t0 = time.time()
    df = _played_frame(league_id)
    df = build_league_features(df)
    res = walk_forward(df, LEAGUE_FEAT_BASE, test_seasons, n_bags=n_bags)
    naive = _naive_brier(df, test_seasons)
    model = res["avg_brier"]
    res.update({
        "league": league_id, "n_matches": int(len(df)),
        "naive_brier": naive,
        "improve_pct": round((naive - model) / naive * 100, 2)
        if naive and not np.isnan(naive) and not np.isnan(model) else None,
        "secs": round(time.time() - t0, 1),
    })
    return res


def _print(r: dict) -> None:
    ps = " ".join(f"{k}:{v:.4f}" for k, v in sorted(r["per_season"].items()))
    print(f"\n  {r['league']:11s} {r['n_matches']:5d} matches · "
          f"avg Brier {r['avg_brier']:.4f}  vs naive {r['naive_brier']:.4f}  "
          f"({r['improve_pct']:+.1f}%)  [{r['secs']}s]")
    print(f"    per-season: {ps}")
    print(f"    w_xgb: {r['w_xgb']}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--league", choices=BIG5, help="single league id")
    ap.add_argument("--all", action="store_true", help="all big-5 leagues")
    ap.add_argument("--seasons", help="comma-separated test seasons "
                    "(default 2022,2023,2024,2025)")
    ap.add_argument("--bags", type=int, default=DEFAULT_N_BAGS,
                    help=f"XGB seed bag size (default {DEFAULT_N_BAGS}, champion)")
    ap.add_argument("--quick", action="store_true",
                    help="n_bags=1 fast single-fit signal (σ≈0.001)")
    a = ap.parse_args()

    targets = BIG5 if a.all else ([a.league] if a.league else [])
    if not targets:
        ap.error("pass --league <id> or --all")
    seasons = ([int(s) for s in a.seasons.split(",")] if a.seasons
               else DEFAULT_TEST_SEASONS)
    n_bags = 1 if a.quick else a.bags

    print(f"Validating {len(targets)} league(s) · seasons {seasons} · "
          f"n_bags={n_bags} · champion config (ELO 25/80/0.40, DC 120d, whl 6)")
    rows = []
    for lid in targets:
        r = validate(lid, seasons, n_bags)
        rows.append(r)
        _print(r)

    if len(rows) > 1:
        print("\n" + "=" * 64)
        print(f"  {'league':11s} {'avg':>8s} {'naive':>8s} {'impr%':>7s}")
        for r in rows:
            print(f"  {r['league']:11s} {r['avg_brier']:8.4f} "
                  f"{r['naive_brier']:8.4f} {r['improve_pct']:+7.1f}")
        print(f"\n  MLS champion reference: 0.6330 (4-fold 2022-2025)")
