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
12. Write all predictions and odds to DuckDB
"""

import logging
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(
            Path(__file__).parent.parent / "logs" / f"daily_{datetime.now().strftime('%Y%m%d')}.log"
        ),
    ],
)
logger = logging.getLogger("daily_update")


def run_step(step_name: str, fn, *args, **kwargs):
    """Run a pipeline step with error isolation (failures don't abort the run)."""
    try:
        logger.info("── Starting: %s", step_name)
        result = fn(*args, **kwargs)
        logger.info("── Done: %s", step_name)
        return result
    except Exception:
        logger.error("── FAILED: %s\n%s", step_name, traceback.format_exc())
        return None


def main():
    from config import SETTINGS
    from data_pipeline import db_utils
    from data_pipeline.schedule_client import sync_to_db as schedule_sync
    from data_pipeline.asa_client import sync_to_db as asa_sync
    from data_pipeline.injury_scraper import build_availability_snapshot
    from data_pipeline.odds_client import sync_to_db as odds_sync, get_pinnacle_implied_prob
    from features.elo_ratings import sync_elo_to_db
    from features.feature_builder import build_training_dataset, build_upcoming_features
    from models.dixon_coles import DixonColesModel
    from models.gradient_boost import GradientBoostModels
    from models.r_bridge.run_bayes import prepare_train_data, prepare_predict_data, run_r_model, read_predictions
    from models.stacking_ensemble import StackingEnsemble
    from market.clv_tracker import evaluate_match, store_bets, update_bet_results

    db_utils.initialize_schema()
    logger.info("=== MLS Daily Update — %s ===", datetime.now(timezone.utc).isoformat())

    # ── 1. Match results + fixtures ───────────────────────────────────────────
    run_step("Fetch ESPN results + fixtures", schedule_sync, days_ahead=14, days_back=3)

    # ── 2. xG data from ASA ───────────────────────────────────────────────────
    current_season = SETTINGS["data"]["current_season"]
    run_step("Fetch ASA xG data", asa_sync, start_season=current_season - 1)

    # ── 3. Injury flags ───────────────────────────────────────────────────────
    injury_df = run_step("Fetch injury/suspension flags", build_availability_snapshot)

    # ── 4. ELO recalculation ──────────────────────────────────────────────────
    run_step("Recalculate ELO ratings", sync_elo_to_db)

    # ── 5. Feature matrix ─────────────────────────────────────────────────────
    train_df = run_step("Build training feature matrix", build_training_dataset)
    upcoming_df = run_step("Build upcoming match features", build_upcoming_features, injury_df)

    if train_df is None or train_df.empty:
        logger.error("No training data available. Aborting model refit.")
        return

    # ── 6. Dixon-Coles ────────────────────────────────────────────────────────
    matches_completed = db_utils.query("SELECT * FROM matches WHERE status='completed'")
    dc_model = run_step("Fit Dixon-Coles model", _fit_dc, matches_completed)
    if dc_model:
        dc_model.save()

    # ── 7. Gradient boost ─────────────────────────────────────────────────────
    gb_models = run_step("Fit gradient boost models", _fit_gb, train_df)
    if gb_models:
        gb_models.save()

    # ── 8. Bayesian model (R) ─────────────────────────────────────────────────
    if train_df is not None:
        run_step("Prepare Bayesian input data", prepare_train_data, train_df)
    if upcoming_df is not None and not upcoming_df.empty:
        run_step("Prepare Bayesian predict data", prepare_predict_data, upcoming_df)
    bayes_success = run_step("Run R Bayesian model", run_r_model)
    bayes_preds = run_step("Read Bayesian predictions", read_predictions) if bayes_success else None

    # ── 9. Stacking ensemble + predictions ────────────────────────────────────
    run_step("Generate ensemble predictions",
             _generate_and_store_predictions,
             dc_model, gb_models, bayes_preds, upcoming_df, train_df)

    # ── 10. Pinnacle odds ─────────────────────────────────────────────────────
    run_step("Fetch Pinnacle odds", odds_sync)

    # ── 11. Update bet outcomes for recently completed matches ─────────────────
    run_step("Update completed bet outcomes", _update_recent_bets)

    logger.info("=== Daily update complete ===")


def _fit_dc(matches_df):
    from models.dixon_coles import DixonColesModel
    model = DixonColesModel()
    return model.fit(matches_df)


def _fit_gb(train_df):
    from models.gradient_boost import GradientBoostModels
    model = GradientBoostModels()
    return model.fit(train_df)


def _generate_and_store_predictions(dc_model, gb_models, bayes_preds_df, upcoming_df, train_df):
    import hashlib
    import uuid
    from datetime import datetime, timezone
    from data_pipeline import db_utils
    from models.stacking_ensemble import StackingEnsemble
    from market.clv_tracker import evaluate_match, store_bets
    from data_pipeline.odds_client import get_pinnacle_implied_prob

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
            # Add placeholder DC OOF columns
            oof_gb["dc_prob_home"] = 0.45
            oof_gb["dc_prob_draw"] = 0.25
            oof_gb["dc_prob_away"] = 0.30
            oof_gb["dc_prob_over"] = 0.50
            ensemble = StackingEnsemble()
            ensemble.fit(oof_gb)
            ensemble.save()
        else:
            logger.error("Cannot fit ensemble without gradient boost models.")
            return

    now = datetime.now(timezone.utc).isoformat()
    all_bets = []

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
            gb_probs = gb_models.predict(row.to_dict()) if gb_models else None
        except Exception:
            gb_probs = None

        bayes_probs = bayes_dict.get(match_id)

        if dc_probs is None and gb_probs is None:
            continue

        # Fallback chain
        dc_probs = dc_probs or gb_probs
        gb_probs = gb_probs or dc_probs
        bayes_probs = bayes_probs or dc_probs

        # Store component predictions
        fh = hashlib.md5(str(row.to_dict()).encode()).hexdigest()[:12]
        for model_name, probs in [("dixon_coles", dc_probs), ("xgboost", gb_probs), ("bayesian", bayes_probs)]:
            if probs:
                ensemble.store_predictions(match_id, model_name, probs, fh)

        # Ensemble prediction
        try:
            ens_probs = ensemble.predict(dc_probs, gb_probs, bayes_probs, home_adj, away_adj)
            ensemble.store_predictions(match_id, "ensemble", ens_probs, fh)
        except Exception as exc:
            logger.warning("Ensemble predict failed for %s: %s", match_id, exc)
            continue

        # Market comparison
        market_implied = get_pinnacle_implied_prob(match_id)
        if market_implied:
            opening_odds = {
                k: 1.0 / v if v > 0 else 0 for k, v in market_implied.items()
            }
            bets = evaluate_match(match_id, ens_probs, opening_odds)
            all_bets.extend(bets)

    if all_bets:
        store_bets(all_bets)
    logger.info("Generated predictions for %d upcoming matches.", len(upcoming_df))


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
        update_bet_results(row["match_id"], result, 0, 0, 0)


if __name__ == "__main__":
    main()
