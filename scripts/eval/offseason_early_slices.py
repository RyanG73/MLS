#!/usr/bin/env python3
"""Research-only opening-window diagnostics for the canonical MLS model.

The script replays ``models.research_model`` on explicit held-out seasons and
reports metrics for each club's first five and first ten matches.  Match number
is derived chronologically within club-season, so the analysis does not depend
on a provider-specific "matchweek" field in an unbalanced MLS schedule.

This is an audit tool only.  It neither changes nor promotes model settings.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from models.research_model import walk_forward_predictions


REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_frame(path: Path) -> tuple[pd.DataFrame, dict, str]:
    meta_path = path.with_suffix(".meta.json")
    if not path.exists() and path.with_suffix(".pkl").exists():
        path = path.with_suffix(".pkl")
    if not path.exists() or not meta_path.exists():
        raise SystemExit(f"missing frame or metadata: {path}, {meta_path}")
    try:
        frame = pd.read_parquet(path)
    except Exception:
        frame = pd.read_pickle(path)
    snapshot = hashlib.md5(path.read_bytes()).hexdigest()[:16]
    return frame, json.loads(meta_path.read_text()), snapshot


def _add_club_match_numbers(frame: pd.DataFrame) -> pd.DataFrame:
    """Number each side's matches within a season using only chronology."""
    ordered = frame.sort_values(
        ["season", "date", "match_id"], kind="mergesort"
    ).copy()
    counts: dict[tuple[int, str], int] = {}
    home_numbers: list[int] = []
    away_numbers: list[int] = []
    for row in ordered.itertuples(index=False):
        season = int(row.season)
        home_key = (season, str(row.home_team))
        away_key = (season, str(row.away_team))
        home_no = counts.get(home_key, 0) + 1
        away_no = counts.get(away_key, 0) + 1
        home_numbers.append(home_no)
        away_numbers.append(away_no)
        counts[home_key] = home_no
        counts[away_key] = away_no
    ordered["home_match_number"] = home_numbers
    ordered["away_match_number"] = away_numbers
    ordered["window_match_number"] = ordered[
        ["home_match_number", "away_match_number"]
    ].max(axis=1)
    return ordered


def _calibration(probs: np.ndarray, y: np.ndarray, bins: int = 10) -> dict:
    """Return pooled one-vs-rest ECE and the largest populated-bin error."""
    y_one_hot = np.eye(3)[y]
    total_weight = 0
    weighted_error = 0.0
    max_error = 0.0
    by_class: dict[str, float] = {}
    for class_idx, class_name in enumerate(("home", "draw", "away")):
        class_weight = 0
        class_error = 0.0
        p = probs[:, class_idx]
        actual = y_one_hot[:, class_idx]
        bin_ids = np.minimum((p * bins).astype(int), bins - 1)
        for bin_idx in range(bins):
            mask = bin_ids == bin_idx
            n = int(mask.sum())
            if n < 10:
                continue
            error = abs(float(p[mask].mean() - actual[mask].mean()))
            class_error += n * error
            class_weight += n
            weighted_error += n * error
            total_weight += n
            max_error = max(max_error, error)
        by_class[class_name] = (
            round(class_error / class_weight, 6) if class_weight else float("nan")
        )
    return {
        "ece": round(weighted_error / total_weight, 6)
        if total_weight
        else float("nan"),
        "max_bin_error": round(max_error, 6),
        "ece_by_class": by_class,
        "bins": bins,
        "minimum_bin_n": 10,
    }


def _metrics(rows: pd.DataFrame) -> dict:
    if rows.empty:
        return {"n": 0}
    probs = rows[["prob_home", "prob_draw", "prob_away"]].to_numpy(float)
    y = rows["label_result"].to_numpy(int)
    y_one_hot = np.eye(3)[y]
    brier_rows = np.sum((probs - y_one_hot) ** 2, axis=1)
    # Ranked probability score for ordered H/D/A, normalized to [0, 1].
    rps_rows = 0.5 * np.sum(
        (np.cumsum(probs, axis=1)[:, :2]
         - np.cumsum(y_one_hot, axis=1)[:, :2]) ** 2,
        axis=1,
    )
    clipped = np.clip(probs[np.arange(len(y)), y], 1e-15, 1.0)
    per_class = np.mean((probs - y_one_hot) ** 2, axis=0)
    return {
        "n": int(len(rows)),
        "brier_sum": round(float(brier_rows.mean()), 6),
        "log_loss": round(float(-np.log(clipped).mean()), 6),
        "rps": round(float(rps_rows.mean()), 6),
        "accuracy": round(float((np.argmax(probs, axis=1) == y).mean()), 6),
        "brier_home": round(float(per_class[0]), 6),
        "brier_draw": round(float(per_class[1]), 6),
        "brier_away": round(float(per_class[2]), 6),
        "calibration": _calibration(probs, y),
    }


def _season_block_ci(
    rows: pd.DataFrame, rng: np.random.Generator, draws: int
) -> dict:
    """Bootstrap whole seasons; intentionally conservative with four folds."""
    if rows.empty:
        return {}
    seasons = sorted(rows["season"].astype(int).unique())
    if len(seasons) < 2:
        return {"method": "unavailable (fewer than two seasons)"}
    values = []
    for _ in range(draws):
        chosen = rng.choice(seasons, size=len(seasons), replace=True)
        sampled = pd.concat(
            [rows[rows["season"] == season] for season in chosen],
            ignore_index=True,
        )
        values.append(_metrics(sampled)["brier_sum"])
    lo, hi = np.quantile(values, [0.025, 0.975])
    return {
        "method": "whole-season cluster bootstrap",
        "draws": draws,
        "brier_sum_95pct": [round(float(lo), 6), round(float(hi), 6)],
        "note": "Only four held-out seasons; interval is descriptive, not a promotion test.",
    }


def _slice(
    rows: pd.DataFrame, mask: pd.Series, rng: np.random.Generator, draws: int
) -> dict:
    selected = rows.loc[mask].copy()
    result = _metrics(selected)
    result["uncertainty"] = _season_block_ci(selected, rng, draws)
    result["by_season"] = {
        str(int(season)): _metrics(group)
        for season, group in selected.groupby("season")
    }
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frame", default="data/parity_frame.parquet")
    parser.add_argument("--test-seasons", default="2022,2023,2024,2025")
    parser.add_argument("--n-bags", type=int, default=5)
    parser.add_argument(
        "--drop-feats",
        default="",
        help="Comma-separated baseline features to omit for an isolated audit ablation.",
    )
    parser.add_argument("--bootstrap-draws", type=int, default=5000)
    parser.add_argument("--model-seed", type=int, default=42)
    parser.add_argument("--bootstrap-seed", type=int, default=20260730)
    parser.add_argument(
        "--out",
        default="experiments/offseason-audit-early-slices-2026-07-30.json",
    )
    args = parser.parse_args()

    frame_path = (REPO_ROOT / args.frame).resolve()
    frame, meta, snapshot = _load_frame(frame_path)
    frame["date"] = pd.to_datetime(frame["date"])
    seasons = [int(value) for value in args.test_seasons.split(",")]
    dropped = [value.strip() for value in args.drop_feats.split(",") if value.strip()]
    unknown = sorted(set(dropped) - set(meta["feat_base"]))
    if unknown:
        raise SystemExit(f"cannot drop features absent from baseline metadata: {unknown}")
    features = [value for value in meta["feat_base"] if value not in dropped]
    preds, weights = walk_forward_predictions(
        frame,
        features,
        seasons,
        weight_hl=meta.get("weight_hl", 6),
        dc_decay_hl=meta.get("dc_decay_hl", 120),
        seed=args.model_seed,
        n_bags=args.n_bags,
    )
    if preds.empty:
        raise SystemExit("no predictions produced")

    numbered = _add_club_match_numbers(frame)
    audit_columns = [
        "match_id",
        "home_match_number",
        "away_match_number",
        "window_match_number",
    ]
    for optional in ("home_mgr_new", "away_mgr_new"):
        if optional in numbered.columns:
            audit_columns.append(optional)
    rows = preds.merge(
        numbered[audit_columns], on="match_id", how="left", validate="one_to_one"
    )
    if {"home_mgr_new", "away_mgr_new"} <= set(rows.columns):
        rows["involves_new_manager"] = (
            rows[["home_mgr_new", "away_mgr_new"]].fillna(0).max(axis=1) > 0
        )
    else:
        rows["involves_new_manager"] = False

    rng = np.random.default_rng(args.bootstrap_seed)
    all_rows = pd.Series(True, index=rows.index)
    first_five = rows["window_match_number"] <= 5
    first_ten = rows["window_match_number"] <= 10
    output = {
        "purpose": "research-only early-season baseline diagnostics",
        "frame": frame_path.name,
        "data_snapshot_hash": snapshot,
        "test_seasons": seasons,
        "n_bags": args.n_bags,
        "model_seed": args.model_seed,
        "bootstrap_seed": args.bootstrap_seed,
        "dropped_features": dropped,
        "w_xgb": weights,
        "window_definition": (
            "A match is in first N when both clubs are playing match N or earlier; "
            "club match number is derived chronologically within club-season."
        ),
        "metric_convention": {
            "brier": "multiclass sum-form (lower is better)",
            "rps": "ordered H/D/A, divided by K-1 (lower is better)",
            "calibration": "one-vs-rest equal-width-bin ECE",
        },
        "slices": {
            "all": _slice(rows, all_rows, rng, args.bootstrap_draws),
            "club_matches_1_5": _slice(
                rows, first_five, rng, args.bootstrap_draws
            ),
            "club_matches_1_10": _slice(
                rows, first_ten, rng, args.bootstrap_draws
            ),
            "after_club_match_10": _slice(
                rows, ~first_ten, rng, args.bootstrap_draws
            ),
            "involves_new_manager": _slice(
                rows, rows["involves_new_manager"], rng, args.bootstrap_draws
            ),
            "no_new_manager_flag": _slice(
                rows, ~rows["involves_new_manager"], rng, args.bootstrap_draws
            ),
        },
        "limitations": [
            "Only four held-out seasons are available.",
            "MLS schedules are unbalanced; chronological club-match number is not an official round.",
            "Manager flags are diagnostic cohort labels, not features in this replay.",
        ],
    }
    out_path = (REPO_ROOT / args.out).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(output, indent=2))
    print(json.dumps(output["slices"], indent=2))
    print(f"wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
