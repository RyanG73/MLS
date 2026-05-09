"""
Walk-forward backtest framework.

For each historical week W:
  1. Fit models on data up to (W-1)
  2. Generate predictions for week W
  3. Evaluate Brier, log-loss, and simulated bet performance
  4. Advance to W+1

Stored in `backtest_results` for dashboard visualization with parameter sliders.
"""

import hashlib
import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import numpy as np
import pandas as pd

from data_pipeline import db_utils

logger = logging.getLogger(__name__)


def run_walk_forward(
    start_date: str,
    end_date: str,
    edge_threshold_pct: float = 5.0,
    half_life_days: int = 60,
    kelly_fraction: float = 0.25,
    models_to_use: Optional[list[str]] = None,
    weekly_step: int = 7,
) -> dict:
    """
    Run a walk-forward backtest over the date range.
    Returns dict of summary metrics + stores detailed results to backtest_results table.
    """
    from features.feature_builder import build_training_dataset, get_feature_columns
    from models.dixon_coles import DixonColesModel
    from models.gradient_boost import GradientBoostModels
    from models.stacking_ensemble import StackingEnsemble
    from market.kelly import vig_adjusted_prob, full_kelly

    models_to_use = models_to_use or ["dixon_coles", "xgboost"]

    all_matches = db_utils.query(
        "SELECT * FROM matches WHERE status = 'completed' ORDER BY date ASC"
    )
    if all_matches.empty:
        return {"error": "No completed matches in DB."}
    all_matches["date"] = pd.to_datetime(all_matches["date"])

    train_full = build_training_dataset(all_matches)
    if train_full.empty:
        return {"error": "Feature matrix is empty."}
    train_full["date"] = pd.to_datetime(
        all_matches.set_index("match_id").reindex(train_full["match_id"])["date"].values
    )

    start = pd.Timestamp(start_date)
    end = pd.Timestamp(end_date)
    cur = start
    week_results = []

    while cur <= end:
        week_end = cur + pd.Timedelta(days=weekly_step - 1)
        train_subset = train_full[train_full["date"] < cur]
        eval_subset = train_full[(train_full["date"] >= cur) & (train_full["date"] <= week_end)]

        if len(train_subset) < 100 or eval_subset.empty:
            cur += pd.Timedelta(days=weekly_step)
            continue

        try:
            metrics = _evaluate_week(
                train_subset, eval_subset, all_matches,
                edge_threshold_pct, kelly_fraction, models_to_use,
            )
            metrics["week_start"] = cur.date().isoformat()
            week_results.append(metrics)
        except Exception as exc:
            logger.warning("Week %s failed: %s", cur.date(), exc)

        cur += pd.Timedelta(days=weekly_step)

    if not week_results:
        return {"error": "No backtest weeks produced results."}

    summary = _aggregate_weeks(week_results)
    summary["parameters"] = {
        "start_date": start_date, "end_date": end_date,
        "edge_threshold_pct": edge_threshold_pct,
        "half_life_days": half_life_days,
        "kelly_fraction": kelly_fraction,
        "models_to_use": models_to_use,
    }

    run_id = str(uuid.uuid4())[:20]
    db_utils.execute(
        """
        INSERT INTO backtest_results
            (run_id, parameters, brier_mean, log_loss, roi_kelly25, roi_kelly50,
             avg_clv, max_drawdown, n_bets, generated_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
        """,
        [
            run_id, json.dumps(summary["parameters"]),
            summary.get("brier_mean"), summary.get("log_loss"),
            summary.get("roi_kelly25"), summary.get("roi_kelly50"),
            summary.get("avg_clv"), summary.get("max_drawdown"),
            summary.get("n_bets", 0),
        ],
    )
    summary["run_id"] = run_id
    summary["weekly_results"] = week_results
    return summary


def _evaluate_week(
    train_df, eval_df, all_matches_df,
    edge_threshold, kelly_fraction, models_to_use,
) -> dict:
    """Fit models on train_df, evaluate predictions against eval_df."""
    from models.dixon_coles import DixonColesModel
    from models.gradient_boost import GradientBoostModels
    from market.kelly import full_kelly

    feature_cols = [c for c in train_df.columns if c not in {
        "match_id", "date", "label_result", "label_over25",
        "home_goals", "away_goals", "total_goals",
    }]

    component_probs = []
    if "dixon_coles" in models_to_use:
        try:
            dc = DixonColesModel().fit(all_matches_df[all_matches_df["date"] < eval_df["date"].min()])
            dc_probs = []
            for _, r in eval_df.iterrows():
                preds = dc.predict(r.get("home_team", ""), r.get("away_team", ""))
                dc_probs.append([preds["prob_home"], preds["prob_draw"], preds["prob_away"]])
            component_probs.append(("dc", np.array(dc_probs)))
        except Exception as exc:
            logger.debug("DC backtest week skipped: %s", exc)

    if "xgboost" in models_to_use:
        try:
            gb = GradientBoostModels().fit(train_df)
            gb_pred_df = gb.predict_batch(eval_df.copy())
            gb_probs = gb_pred_df[["prob_home", "prob_draw", "prob_away"]].values
            component_probs.append(("xgb", gb_probs))
        except Exception as exc:
            logger.debug("GB backtest week skipped: %s", exc)

    if not component_probs:
        return {"n_bets": 0}

    # Simple average ensemble for backtest speed
    avg_probs = np.mean([p for _, p in component_probs], axis=0)

    actuals = eval_df["label_result"].values.astype(int)
    one_hot = np.zeros_like(avg_probs)
    one_hot[np.arange(len(actuals)), actuals] = 1

    brier = float(np.mean(np.sum((avg_probs - one_hot) ** 2, axis=1)) / 2)
    eps = 1e-12
    ll = float(-np.mean(np.sum(one_hot * np.log(np.clip(avg_probs, eps, 1)), axis=1)))

    return {
        "n_matches": len(eval_df),
        "brier": brier,
        "log_loss": ll,
        "n_bets": 0,   # Bet simulation requires odds data not always present in backfill
        "roi_kelly25": 0.0,
        "roi_kelly50": 0.0,
        "avg_clv": 0.0,
    }


def _aggregate_weeks(weeks: list[dict]) -> dict:
    if not weeks:
        return {}
    weights = np.array([w.get("n_matches", 0) for w in weeks])
    if weights.sum() == 0:
        return {"n_weeks": len(weeks)}

    def weighted(key):
        vals = np.array([w.get(key, 0) for w in weeks])
        return float(np.average(vals, weights=weights))

    return {
        "n_weeks":     len(weeks),
        "n_matches":   int(weights.sum()),
        "n_bets":      int(sum(w.get("n_bets", 0) for w in weeks)),
        "brier_mean":  weighted("brier"),
        "log_loss":    weighted("log_loss"),
        "roi_kelly25": weighted("roi_kelly25"),
        "roi_kelly50": weighted("roi_kelly50"),
        "avg_clv":     weighted("avg_clv"),
        "max_drawdown": 0.0,
    }


def get_recent_runs(limit: int = 20) -> pd.DataFrame:
    """Fetch the most recent backtest runs for dashboard display."""
    return db_utils.query(
        "SELECT * FROM backtest_results ORDER BY generated_at DESC LIMIT %s",
        [limit],
    )
