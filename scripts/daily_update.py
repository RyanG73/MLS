#!/usr/bin/env python3
"""
Daily update pipeline. Runs every morning via cron.

Orchestration order (mirrors plan):
1.  Fetch yesterday's results + upcoming fixtures (ESPN)
2.  Pull latest xG data (ASA)
3.  Refresh injury/suspension flags (ESPN injuries)
4.  Recalculate ELO ratings
5.  Rebuild feature snapshots for upcoming matches
6.  Refit Dixon-Coles → predict upcoming
7.  Refit gradient boost → predict upcoming
8.  Run R/brms Bayesian model → predict upcoming
9.  Refit stacking ensemble → generate ensemble predictions
10. Fetch latest Pinnacle odds
11. Compute edges + update simulated bet outcomes
12. Write all predictions and odds to PostgreSQL
"""

import json
import logging
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

load_dotenv()

_LOG_DIR = Path(__file__).parent.parent / "logs"
_LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(
            _LOG_DIR / f"daily_{datetime.now().strftime('%Y%m%d')}.log"
        ),
    ],
)
logger = logging.getLogger("daily_update")


def run_step(step_name: str, fn, *args, run_id: str | None = None, stats: dict | None = None, **kwargs):
    """Run a pipeline step with error isolation (failures don't abort the run)."""
    try:
        logger.info("── Starting: %s", step_name)
        result = fn(*args, **kwargs)
        logger.info("── Done: %s", step_name)
        step_status = "skipped" if result is False else "ok"
        message = "returned False" if result is False else "ok"
        if stats is not None:
            stats[step_name] = step_status
        if run_id:
            from data_pipeline import db_utils
            db_utils.update_pipeline_run(run_id, "running", step_name=step_name, message=message)
        return result
    except Exception:
        error = traceback.format_exc()
        logger.error("── FAILED: %s\n%s", step_name, error)
        if stats is not None:
            stats[step_name] = "failed"
        if run_id:
            from data_pipeline import db_utils
            db_utils.update_pipeline_run(run_id, "running", step_name=step_name, message=error[-1000:])
        return None


def main():
    from config import SETTINGS
    from data_pipeline import db_utils
    from data_pipeline.schedule_client import sync_to_db as schedule_sync
    from data_pipeline.asa_client import sync_to_db as asa_sync
    from data_pipeline.injury_scraper import build_availability_snapshot
    from data_pipeline.odds_client import sync_to_db as odds_sync
    from features.elo_ratings import sync_elo_to_db
    from features.feature_builder import build_training_dataset, build_upcoming_features
    from models.dixon_coles import DixonColesModel
    from models.gradient_boost import GradientBoostModels
    from models.r_bridge.run_bayes import prepare_train_data, prepare_predict_data, run_r_model, read_predictions
    from models.stacking_ensemble import StackingEnsemble
    from market.clv_tracker import evaluate_match, store_bets, update_bet_results

    db_utils.initialize_schema()
    run_id = db_utils.start_pipeline_run("daily_update")
    stats: dict[str, str | int] = {}
    logger.info("=== MLS Daily Update — %s ===", datetime.now(timezone.utc).isoformat())

    # ── 1. Match results + fixtures ───────────────────────────────────────────
    run_step("Fetch ESPN results + fixtures", schedule_sync, days_ahead=14, days_back=3, run_id=run_id, stats=stats)

    # ── 2. xG data from ASA ───────────────────────────────────────────────────
    current_season = SETTINGS["data"]["current_season"]
    run_step("Fetch ASA xG data", asa_sync, start_season=current_season - 1, run_id=run_id, stats=stats)

    # ── 3. Injury flags ───────────────────────────────────────────────────────
    injury_df = run_step("Fetch injury/suspension flags", build_availability_snapshot, run_id=run_id, stats=stats)

    # ── 4. ELO recalculation ──────────────────────────────────────────────────
    run_step("Recalculate ELO ratings", sync_elo_to_db, run_id=run_id, stats=stats)

    # ── 5. Feature matrix ─────────────────────────────────────────────────────
    train_df = run_step("Build training feature matrix", build_training_dataset, run_id=run_id, stats=stats)
    upcoming_df = run_step("Build upcoming match features", build_upcoming_features, injury_df, run_id=run_id, stats=stats)

    if train_df is None or train_df.empty:
        logger.error("No training data available. Aborting model refit.")
        db_utils.update_pipeline_run(
            run_id, "failed", step_name="Build training feature matrix",
            message="No training data available.", stats=json.dumps(stats), finished=True
        )
        return

    # ── 6. Dixon-Coles ────────────────────────────────────────────────────────
    matches_completed = db_utils.query("SELECT * FROM matches WHERE status='completed'")
    dc_model = run_step("Fit Dixon-Coles model", _fit_dc, matches_completed, run_id=run_id, stats=stats)
    if dc_model:
        dc_model.save()

    penaltyblog_model = run_step(
        "Fit penaltyblog Dixon-Coles benchmark",
        _fit_penaltyblog_dc,
        matches_completed,
        run_id=run_id,
        stats=stats,
    )
    if penaltyblog_model:
        penaltyblog_model.save()

    # ── 7. Gradient boost ─────────────────────────────────────────────────────
    gb_models = run_step("Fit gradient boost models", _fit_gb, train_df, run_id=run_id, stats=stats)
    if gb_models:
        gb_models.save()

    # ── 8. Bayesian model (R) ─────────────────────────────────────────────────
    if train_df is not None:
        run_step("Prepare Bayesian input data", prepare_train_data, train_df, run_id=run_id, stats=stats)
    if upcoming_df is not None and not upcoming_df.empty:
        run_step("Prepare Bayesian predict data", prepare_predict_data, upcoming_df, run_id=run_id, stats=stats)
    bayes_success = run_step("Run R Bayesian model", run_r_model, run_id=run_id, stats=stats)
    bayes_preds = run_step("Read Bayesian predictions", read_predictions, run_id=run_id, stats=stats) if bayes_success else None

    # ── 9. Pinnacle odds before market comparison ─────────────────────────────
    odds_rows = run_step("Fetch Pinnacle opening odds", odds_sync, snapshot_type="open", run_id=run_id, stats=stats)
    if odds_rows is not None:
        stats["opening_odds_rows"] = int(odds_rows)

    # ── 10. Stacking ensemble + predictions ───────────────────────────────────
    pred_rows = run_step("Generate ensemble predictions",
             _generate_and_store_predictions,
             dc_model, penaltyblog_model, gb_models, bayes_preds, upcoming_df, train_df, run_id=run_id, stats=stats)
    if pred_rows is not None:
        stats["predicted_matches"] = int(pred_rows)

    # ── 11. Update bet outcomes for recently completed matches ─────────────────
    settled = run_step("Update completed bet outcomes", _update_recent_bets, run_id=run_id, stats=stats)
    if settled is not None:
        stats["settled_matches"] = int(settled)

    status = "failed" if any(v == "failed" for v in stats.values()) else "success"
    db_utils.update_pipeline_run(run_id, status, stats=json.dumps(stats), finished=True)
    logger.info("=== Daily update complete ===")


def _fit_dc(matches_df):
    from models.dixon_coles import DixonColesModel
    model = DixonColesModel()
    return model.fit(matches_df)


def _fit_penaltyblog_dc(matches_df):
    from models.penaltyblog_baseline import PenaltyBlogDixonColesModel

    if not PenaltyBlogDixonColesModel.available():
        logger.info("penaltyblog is not installed; skipping optional benchmark.")
        return False
    model = PenaltyBlogDixonColesModel()
    return model.fit(matches_df)


def _fit_gb(train_df):
    from models.gradient_boost import GradientBoostModels
    model = GradientBoostModels()
    return model.fit(train_df)


def _generate_and_store_predictions(dc_model, penaltyblog_model, gb_models, bayes_preds_df, upcoming_df, train_df):
    import hashlib
    from data_pipeline import db_utils
    from models.stacking_ensemble import StackingEnsemble
    from market.clv_tracker import evaluate_match, store_bets
    from data_pipeline.odds_client import get_pinnacle_odds

    if upcoming_df is None or upcoming_df.empty:
        logger.info("No upcoming matches to predict.")
        return

    # Try to load or refit ensemble
    try:
        ensemble = StackingEnsemble.load()
    except FileNotFoundError:
        logger.warning("No saved ensemble found; fitting from scratch on training data.")
        if gb_models and train_df is not None:
            oof_gb = gb_models.oof_predictions(train_df)
            if dc_model is None:
                logger.error("Cannot fit ensemble without Dixon-Coles OOF predictions.")
                return 0
            oof_dc = _generate_dc_oof(dc_model, train_df)
            oof_gb = oof_gb.merge(oof_dc, on="match_id")
            ensemble = StackingEnsemble()
            ensemble.fit(oof_gb)
            ensemble.save()
        else:
            logger.error("Cannot fit ensemble without gradient boost models.")
            return

    all_bets = []
    predicted = 0

    bayes_dict = {}
    if bayes_preds_df is not None:
        for _, row in bayes_preds_df.iterrows():
            bayes_dict[row["match_id"]] = {
                "prob_home": row["prob_home"],
                "prob_draw": row["prob_draw"],
                "prob_away": row["prob_away"],
                "prob_over": row["prob_over"],
                "prob_under": row["prob_under"],
            }

    for _, row in upcoming_df.iterrows():
        match_id = row["match_id"]
        home_team = row.get("home_team", "")
        away_team = row.get("away_team", "")

        # Get overrides for this match
        overrides = db_utils.query(
            "SELECT home_strength_adj, away_strength_adj FROM overrides WHERE match_id = %s",
            [match_id]
        )
        home_adj = float(overrides["home_strength_adj"].sum()) if not overrides.empty else 0.0
        away_adj = float(overrides["away_strength_adj"].sum()) if not overrides.empty else 0.0

        # Component predictions
        try:
            dc_probs = dc_model.predict(home_team, away_team, home_adj, away_adj) if dc_model else None
        except Exception:
            dc_probs = None

        try:
            penaltyblog_probs = penaltyblog_model.predict(home_team, away_team) if penaltyblog_model else None
        except Exception:
            penaltyblog_probs = None

        try:
            gb_probs = gb_models.predict(row.to_dict()) if gb_models else None
        except Exception:
            gb_probs = None

        bayes_probs = bayes_dict.get(match_id)

        dc_probs = dc_probs or penaltyblog_probs

        if dc_probs is None and gb_probs is None:
            continue

        # Fallback chain
        gb_probs = gb_probs or dc_probs
        bayes_probs = bayes_probs or dc_probs

        # Store component predictions
        fh = hashlib.md5(str(row.to_dict()).encode()).hexdigest()[:12]
        for model_name, probs in [
            ("dixon_coles", dc_probs),
            ("penaltyblog_dc", penaltyblog_probs),
            ("xgboost", gb_probs),
            ("bayesian", bayes_probs),
        ]:
            if probs:
                ensemble.store_predictions(match_id, model_name, probs, fh)

        # Ensemble prediction
        try:
            ens_probs = ensemble.predict(dc_probs, gb_probs, bayes_probs, home_adj, away_adj)
            ensemble.store_predictions(match_id, "ensemble", ens_probs, fh)
            predicted += 1
        except Exception as exc:
            logger.warning("Ensemble predict failed for %s: %s", match_id, exc)
            continue

        # Market comparison
        opening_odds = get_pinnacle_odds(match_id, snapshot_type="open")
        if opening_odds:
            bets = evaluate_match(match_id, ens_probs, opening_odds)
            all_bets.extend(bets)

    if all_bets:
        store_bets(all_bets)
    logger.info("Generated predictions for %d upcoming matches.", predicted)
    return predicted


def _generate_dc_oof(dc_model, train_df, n_folds: int = 5):
    import pandas as pd
    from data_pipeline import db_utils
    from models.dixon_coles import DixonColesModel
    from sklearn.model_selection import TimeSeriesSplit

    if not {"match_id", "home_team", "away_team"}.issubset(train_df.columns):
        raise ValueError("Training data must include match_id, home_team, and away_team for DC OOF.")

    rows = []
    tscv = TimeSeriesSplit(n_splits=n_folds)
    for tr_idx, val_idx in tscv.split(train_df.index.values):
        tr_data = train_df.iloc[tr_idx]
        val_data = train_df.iloc[val_idx]
        matches_fold = db_utils.query(
            "SELECT * FROM matches WHERE status='completed'"
        ).merge(tr_data[["match_id"]], on="match_id")

        fold_model = DixonColesModel()
        try:
            fold_model.fit(matches_fold)
        except Exception:
            logger.warning("Dixon-Coles fold fit failed; using fully fitted model for this fold.")
            fold_model = dc_model

        for _, row in val_data.iterrows():
            try:
                preds = fold_model.predict(row["home_team"], row["away_team"])
            except Exception:
                preds = {"prob_home": 0.45, "prob_draw": 0.25, "prob_away": 0.30, "prob_over": 0.50}
            rows.append({
                "match_id": row["match_id"],
                "dc_prob_home": preds["prob_home"],
                "dc_prob_draw": preds["prob_draw"],
                "dc_prob_away": preds["prob_away"],
                "dc_prob_over": preds["prob_over"],
            })
    return pd.DataFrame(rows)


def _update_recent_bets():
    """Update P&L for matches completed in the last 3 days."""
    from data_pipeline import db_utils
    from market.clv_tracker import update_bet_results

    recent = db_utils.query(
        """
        SELECT m.match_id, m.home_goals, m.away_goals
        FROM matches m
        WHERE m.status = 'completed'
          AND m.date >= current_date - INTERVAL '3 days'
          AND EXISTS (
              SELECT 1 FROM simulated_bets sb
              WHERE sb.match_id = m.match_id AND sb.result IS NULL
          )
        """
    )
    for _, row in recent.iterrows():
        hg, ag = int(row["home_goals"]), int(row["away_goals"])
        result = "home" if hg > ag else ("draw" if hg == ag else "away")
        update_bet_results(row["match_id"], result)
    return len(recent)


if __name__ == "__main__":
    main()
