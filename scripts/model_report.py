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
from pathlib import Path

import numpy as np
import pandas as pd

from models.metrics import (brier_multiclass_sum, per_class_brier,
                            log_loss_multiclass)

REPO_ROOT = Path(__file__).parent.parent.resolve()

_DEFAULT_MARKET_EVAL = REPO_ROOT / "experiments" / "market_eval.json"


def _load_market_slices(eval_path: str | None = None) -> dict | str:
    """Load market_slices from market_eval.json if it exists.

    Returns the parsed dict when available, otherwise a deferred string
    instructing the user to run scripts/market_eval.py.
    """
    candidates = [eval_path] if eval_path else [str(_DEFAULT_MARKET_EVAL)]
    for path in candidates:
        if path and Path(path).exists():
            try:
                return json.loads(Path(path).read_text())
            except Exception:
                pass
    return "deferred (run: python -m scripts.market_eval to generate)"


def _git_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "-C", str(REPO_ROOT), "rev-parse", "HEAD"], text=True).strip()
    except Exception:
        return "unknown"


def _source_health_snapshot() -> dict:
    """Best-effort per-source coverage gate status (Phase A → promotion gate).

    Returns {source: {parsed, floor, ok, success, error, fetched_at, endpoint}}
    keyed by source name; {} otherwise (no health file → gate skips the check).
    """
    try:
        from data_pipeline.source_health import coverage_gate_status
        return coverage_gate_status()
    except Exception:
        return {}


def _promoted_team_brier_snapshot() -> dict:
    """Best-effort European tier-bridge promoted-team Brier (A3), pooled across
    all supported pairs. MLS has no promotion, so this is an independent
    project-health diagnostic attached to every report — like
    _source_health_snapshot, not scoped to this report's own frame/seasons.
    Returns {} if the tier-bridge data/coefficients aren't available.
    """
    try:
        from scripts.eval.promoted_team_brier import pooled_summary
        summary = pooled_summary()
        summary.pop("by_pair", None)  # per-pair detail stays in the dedicated script's output
        return summary
    except Exception:
        return {}


def _feature_completeness(df: pd.DataFrame, test_seasons: list) -> dict:
    """Per-season null rates for key feature families in the test window.

    Returns {season: {feature: null_fraction}} for the rows the model was
    actually evaluated on, so calibration and Brier are interpretable alongside
    feature coverage. Only columns with at least one null are included to keep
    the report concise when data is clean.
    """
    key_feats = [
        "home_elo", "away_elo",
        "home_form_5", "away_form_5",
        "home_xg_roll_5", "away_xg_roll_5",
        "home_xga_roll_5", "away_xga_roll_5",
        "home_xg_roll_10", "away_xg_roll_10",
        "home_gk_z", "away_gk_z",
        "home_xg_oe_z", "away_xg_oe_z",
        "home_avail_share", "away_avail_share",
        "home_dp_avail", "away_dp_avail",
    ]
    present = [c for c in key_feats if c in df.columns]
    if not present:
        return {}
    test_df = df[df["season"].isin(test_seasons)]
    out: dict = {}
    for s, grp in test_df.groupby("season"):
        n = len(grp)
        if n == 0:
            continue
        season_nulls = {
            c: round(float(grp[c].isna().sum() / n), 4)
            for c in present
            if grp[c].isna().any()
        }
        if season_nulls:
            out[str(s)] = season_nulls
    return out


def _asa_cache_freshness() -> dict:
    """Best-effort freshness summary for ASA parquet cache files."""
    try:
        from data_pipeline.asa_cache import cache_status
        return cache_status()
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


def _binary_side_metrics(rows: pd.DataFrame) -> dict:
    """Metrics for side-level yes/no events such as home/away underdog wins."""
    if rows.empty:
        return {"n": 0}
    p = rows["prob"].astype(float).to_numpy()
    hit = rows["hit"].astype(float).to_numpy()
    p_clip = np.clip(p, 1e-6, 1 - 1e-6)
    return {
        "n": int(len(rows)),
        "mean_prob": round(float(p.mean()), 4),
        "hit_rate": round(float(hit.mean()), 4),
        "binary_brier": round(float(np.mean((p - hit) ** 2)), 4),
        "binary_log_loss": round(float(np.mean(
            -(hit * np.log(p_clip) + (1 - hit) * np.log(1 - p_clip))
        )), 4),
    }


def _side_rows(preds: pd.DataFrame, P: np.ndarray, y: np.ndarray) -> pd.DataFrame:
    """Return one row per non-draw side (home/away) with model and optional market prob."""
    rows = []
    has_market = {"mkt_home", "mkt_away"}.issubset(preds.columns)
    for i, (_, match) in enumerate(preds.iterrows()):
        for side, prob_idx, team_col, mkt_col in [
            ("home", 0, "home_team", "mkt_home"),
            ("away", 2, "away_team", "mkt_away"),
        ]:
            prob = float(P[i, prob_idx])
            row = {
                "match_index": i,
                "side": side,
                "team": match.get(team_col),
                "prob": prob,
                "hit": int(y[i] == prob_idx),
                "opponent_prob": float(P[i, 2 if prob_idx == 0 else 0]),
            }
            if has_market:
                mkt = match.get(mkt_col)
                row["market_prob"] = float(mkt) if pd.notna(mkt) else np.nan
            rows.append(row)
    return pd.DataFrame(rows)


def _underdog_slices(side_df: pd.DataFrame) -> dict:
    """Calibration slices for home/away teams the model prices as underdogs."""
    out = {}
    under = side_df[side_df["prob"] <= 0.40].copy()
    if under.empty:
        return {
            "by_probability": {},
            "significant": {"n": 0},
        }

    buckets = pd.cut(
        under["prob"],
        bins=[0.0, 0.10, 0.20, 0.25, 0.30, 0.40],
        labels=["0-10%", "10-20%", "20-25%", "25-30%", "30-40%"],
        include_lowest=True,
    )
    by_prob = {}
    for bucket, grp in under.groupby(buckets, observed=True):
        if grp.empty:
            continue
        by_prob[str(bucket)] = _binary_side_metrics(grp)

    significant = under[(under["opponent_prob"] - under["prob"]) >= 0.15]
    by_side = {}
    for side, grp in under.groupby("side"):
        by_side[str(side)] = _binary_side_metrics(grp)

    out["by_probability"] = by_prob
    out["by_side"] = by_side
    out["significant"] = _binary_side_metrics(significant)
    return out


def _market_disagreement_slices(side_df: pd.DataFrame) -> dict | None:
    """Side-level model-vs-market disagreement buckets, when market columns exist."""
    if "market_prob" not in side_df.columns:
        return None
    priced = side_df[side_df["market_prob"].notna()].copy()
    if priced.empty:
        return {"status": "no_market", "n": 0, "by_edge": {}, "market_underdogs": {}}

    priced["edge_pp"] = (priced["prob"] - priced["market_prob"]) * 100.0
    edges = pd.cut(
        priced["edge_pp"],
        bins=[-100.0, -8.0, -4.0, 0.0, 4.0, 8.0, 100.0],
        labels=["<=-8pp", "-8 to -4pp", "-4 to 0pp", "0 to 4pp", "4 to 8pp", "8pp+"],
        include_lowest=True,
    )
    by_edge = {}
    for bucket, grp in priced.groupby(edges, observed=True):
        if grp.empty:
            continue
        metrics = _binary_side_metrics(grp)
        metrics["mean_market_prob"] = round(float(grp["market_prob"].mean()), 4)
        metrics["mean_edge_pp"] = round(float(grp["edge_pp"].mean()), 2)
        by_edge[str(bucket)] = metrics

    market_under = priced[priced["market_prob"] <= 0.25]
    disagreement_under = market_under[market_under["edge_pp"] >= 8.0]
    return {
        "status": "ok",
        "n": int(len(priced)),
        "max_abs_edge_pp": round(float(priced["edge_pp"].abs().max()), 2),
        "mean_abs_edge_pp": round(float(priced["edge_pp"].abs().mean()), 2),
        "by_edge": by_edge,
        "market_underdogs": _binary_side_metrics(market_under),
        "disagreement_underdogs": _binary_side_metrics(disagreement_under),
    }


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

    # (i) favorite-probability decile — conditional calibration by confidence
    fav_p = P.max(axis=1)
    fav_cls = P.argmax(axis=1)
    dec = pd.cut(fav_p, bins=np.arange(0.3, 1.0001, 0.07), include_lowest=True)
    by_fav = {}
    for b, idx in pd.Series(range(len(preds))).groupby(dec, observed=True):
        ii = idx.values
        if len(ii) < 25:
            continue
        yoh = np.eye(3)[y[ii]]
        by_fav[str(b)] = {
            "n": int(len(ii)),
            "brier": round(float(np.mean(np.sum((P[ii] - yoh) ** 2, axis=1))), 4),
            "fav_prob_mean": round(float(fav_p[ii].mean()), 4),
            "fav_hit_rate": round(float((fav_cls[ii] == y[ii]).mean()), 4),
        }
    out["by_favorite_prob"] = by_fav

    # (ii) season phase — early-season staleness is a known suspect (§1.3d)
    doy = pd.to_datetime(preds["date"])
    start = doy.groupby(preds["season"]).transform("min")
    days_in = (doy - start).dt.days
    phase = pd.Series(np.select(
        [days_in <= 60, days_in <= 180], ["first_60d", "mid"], default="late"),
        index=preds.index)
    _by(phase, "by_season_phase")

    # club-prior-gap terciles (A7) — fallen giants vs overachievers.
    # Column is attached in main() from the frame's ELO history; rank-based
    # qcut so the many exact-zero gaps (young clubs) can't collapse the bins.
    if "club_prior_gap" in preds.columns:
        ranks = preds["club_prior_gap"].rank(method="first")
        terc = pd.qcut(ranks, 3, labels=["overachiever", "neutral", "fallen"])
        _by(pd.Series(terc, index=preds.index), "by_club_prior_gap")

    # (iii) draw reliability curve — the worst class (max-decile err 0.108)
    curve = []
    for lo in np.arange(0.0, 0.5, 0.05):
        m = (P[:, 1] >= lo) & (P[:, 1] < lo + 0.05)
        if m.sum() < 25:
            continue
        curve.append({"bin": f"{lo:.2f}", "n": int(m.sum()),
                      "p_mean": round(float(P[m, 1].mean()), 4),
                      "freq": round(float((y[m] == 1).mean()), 4)})
    out["draw_reliability"] = curve
    side_df = _side_rows(preds, P, y)
    out["underdog_calibration"] = _underdog_slices(side_df)
    market = _market_disagreement_slices(side_df)
    if market is not None:
        out["market_disagreement"] = market
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--frame", default="data/parity_frame.parquet")
    ap.add_argument("--out", default=None, help="JSON output path")
    ap.add_argument("--label", default="run", help="champion / challenger / run label")
    ap.add_argument("--test-seasons", default=None,
                    help="Comma-separated override; default = meta test_seasons")
    ap.add_argument("--extra-feats", default=None,
                    help="Comma-separated feature columns to append to meta feat_base "
                         "(e.g. ref_hw_rate,ref_draw_rate) — for challenger A/B reports")
    ap.add_argument("--n-bags", type=int, default=5,
                    help="XGB bag size (seed +1000i, raw probs averaged); champion "
                         "config is 5 since 2026-06-10; pass 1 to disable bagging")
    ap.add_argument("--wide-grid", action="store_true",
                    help="Sweep min_child_weight/reg_lambda in the inner XGB grid (48 combos)")
    ap.add_argument("--market-eval", default=None, metavar="PATH",
                    help="Path to market_eval.json; if omitted looks for "
                         "experiments/market_eval.json automatically")
    args = ap.parse_args()

    df, meta, snapshot_hash = _load_frame(args.frame)
    df["date"] = pd.to_datetime(df["date"])
    feat_base = list(meta["feat_base"])
    if args.extra_feats:
        for _c in [c.strip() for c in args.extra_feats.split(",") if c.strip()]:
            if _c not in df.columns:
                raise SystemExit(f"[report] --extra-feats column not in frame: {_c}")
            if _c not in feat_base:
                feat_base.append(_c)
        print(f"[report] feat_base extended with: {args.extra_feats}")
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
        weight_hl=meta.get("weight_hl", 6), dc_decay_hl=meta.get("dc_decay_hl", 120),
        wide_grid=args.wide_grid, n_bags=args.n_bags)
    if preds.empty:
        raise SystemExit("[report] no predictions produced")

    # A7: stamp each match with the larger-|gap| side's club-prior gap so the
    # slice captures every match INVOLVING a fallen giant, home or away.
    if {"home_elo", "away_elo"} <= set(df.columns):
        from scripts.eval.club_prior import (club_prior_gap,
                                             elo_history_from_matches)
        gaps = club_prior_gap(elo_history_from_matches(df))
        def _row_gap(r):
            gh = gaps.get((r["home_team"], int(r["season"])), 0.0)
            ga = gaps.get((r["away_team"], int(r["season"])), 0.0)
            return gh if abs(gh) >= abs(ga) else ga
        preds["club_prior_gap"] = preds.apply(_row_gap, axis=1)

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
        "model_config": {"n_bags": args.n_bags, "wide_grid": args.wide_grid},
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
        # Per-match Brier keyed by match_id — enables the gate's paired
        # bootstrap significance check (champion vs challenger on common matches).
        "per_match": {
            "match_id": preds["match_id"].astype(str).tolist(),
            "brier": np.round(
                np.sum((P - np.eye(3)[y]) ** 2, axis=1), 6).tolist(),
        },
        "source_health": _source_health_snapshot(),
        "feature_completeness": _feature_completeness(df, test_seasons),
        "promoted_team_brier": _promoted_team_brier_snapshot(),
        "asa_cache_freshness": _asa_cache_freshness(),
        "market_slices": _load_market_slices(getattr(args, "market_eval", None)),
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
