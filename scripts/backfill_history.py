#!/usr/bin/env python3
"""
One-time historical backfill script.
Run this on first setup to populate PostgreSQL with full MLS history.

Steps:
1. Initialize PostgreSQL schema
2. Seed team registry
3. Pull all MLS matches from ASA API (2011–present)
4. Compute full ELO history
5. Build training feature matrix
6. Fit all three component models
7. Generate OOF predictions for stacking
8. Fit stacking ensemble

Expected runtime: 20–60 minutes depending on hardware.
"""

import logging
import sys
from pathlib import Path

# Ensure repo root is on path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger("backfill")


def main():
    from config import SETTINGS
    from data_pipeline import db_utils
    from data_pipeline.asa_client import sync_to_db as asa_sync, _TEAM_NAME_MAP, get_conference
    from data_pipeline.schedule_client import sync_to_db as schedule_sync
    from features.elo_ratings import sync_elo_to_db
    from features.feature_builder import build_training_dataset, build_upcoming_features
    from models.dixon_coles import DixonColesModel
    from models.gradient_boost import GradientBoostModels
    from models.penaltyblog_baseline import PenaltyBlogDixonColesModel
    from models.r_bridge.run_bayes import prepare_train_data, prepare_predict_data
    from models.stacking_ensemble import StackingEnsemble

    # ── Step 1: Schema ────────────────────────────────────────────────────────
    logger.info("=== Step 1: Initializing PostgreSQL schema ===")
    db_utils.initialize_schema()

    # ── Step 2: Team registry ─────────────────────────────────────────────────
    logger.info("=== Step 2: Seeding team registry ===")
    _seed_team_registry(db_utils)

    # ── Step 3: Pull match history ────────────────────────────────────────────
    logger.info("=== Step 3: Pulling MLS match history from ASA ===")
    start_season = SETTINGS["data"]["backfill_start_season"]
    asa_sync(start_season=start_season)

    logger.info("=== Step 3b: Syncing upcoming fixtures from ESPN ===")
    try:
        schedule_sync(days_ahead=14, days_back=3)
    except Exception as exc:
        logger.warning("ESPN sync failed (non-fatal): %s", exc)

    # ── Step 4: ELO history ───────────────────────────────────────────────────
    logger.info("=== Step 4: Computing ELO rating history ===")
    sync_elo_to_db()

    # ── Step 5: Feature matrix ────────────────────────────────────────────────
    logger.info("=== Step 5: Building training feature matrix ===")
    train_df = build_training_dataset()
    logger.info("Feature matrix: %d rows, %d cols", len(train_df), len(train_df.columns))

    if train_df.empty:
        logger.error("No training data — check ASA API connectivity.")
        sys.exit(1)

    # ── Step 6: Fit Dixon-Coles ───────────────────────────────────────────────
    logger.info("=== Step 6a: Fitting Dixon-Coles model ===")
    matches_df = db_utils.query("SELECT * FROM matches WHERE status = 'completed'")
    dc_model = DixonColesModel()
    dc_model.fit(matches_df)
    dc_model.save()

    logger.info("=== Step 6a.1: Fitting optional penaltyblog Dixon-Coles benchmark ===")
    if PenaltyBlogDixonColesModel.available():
        try:
            penaltyblog_model = PenaltyBlogDixonColesModel()
            penaltyblog_model.fit(matches_df)
            penaltyblog_model.save()
        except Exception as exc:
            logger.warning("penaltyblog benchmark fit failed (non-fatal): %s", exc)
    else:
        logger.info("penaltyblog is not installed; skipping optional benchmark.")

    # ── Step 6b: Fit gradient boost ───────────────────────────────────────────
    logger.info("=== Step 6b: Fitting gradient boost models ===")
    gb_models = GradientBoostModels()
    gb_models.fit(train_df)
    gb_models.save()

    # ── Step 6c: Prepare Bayesian model data ──────────────────────────────────
    logger.info("=== Step 6c: Preparing Bayesian model input data ===")
    bayes_train = train_df[train_df["label_result"].notna()].copy()
    prepare_train_data(bayes_train)
    upcoming_df = build_upcoming_features()
    if not upcoming_df.empty:
        prepare_predict_data(upcoming_df)

    logger.info(
        "Bayesian model data written. Run R script manually if brms is installed:\n"
        "  Rscript models/r_bridge/bayesian_elo.R ."
    )

    # ── Step 7: OOF predictions for stacking ─────────────────────────────────
    logger.info("=== Step 7: Generating OOF predictions for stacking ===")
    oof_gb = gb_models.oof_predictions(train_df)

    # Generate OOF Dixon-Coles predictions
    oof_dc = _generate_dc_oof(dc_model, train_df, n_folds=5)

    oof_combined = oof_gb.merge(oof_dc, on="match_id", suffixes=("", "_dc"))
    oof_combined = oof_combined.rename(columns={
        "xgb_prob_home": "xgb_prob_home",
        "xgb_prob_draw": "xgb_prob_draw",
        "xgb_prob_away": "xgb_prob_away",
    })
    # Map DC columns
    for col in ["dc_prob_home", "dc_prob_draw", "dc_prob_away", "dc_prob_over"]:
        if col not in oof_combined.columns and col + "_dc" in oof_combined.columns:
            oof_combined[col] = oof_combined[col + "_dc"]

    # ── Step 8: Fit stacking ensemble ─────────────────────────────────────────
    logger.info("=== Step 8: Fitting stacking ensemble ===")
    ensemble = StackingEnsemble()
    ensemble.fit(oof_combined)
    ensemble.save()

    logger.info("=== Backfill complete! ===")
    db_cfg = SETTINGS["database"]
    logger.info("Database: %s:%s/%s", db_cfg["host"], db_cfg["port"], db_cfg["name"])
    n_matches = db_utils.query("SELECT COUNT(*) AS n FROM matches").iloc[0]["n"]
    n_completed = db_utils.query("SELECT COUNT(*) AS n FROM matches WHERE status='completed'").iloc[0]["n"]
    logger.info("Total matches in DB: %d (%d completed)", n_matches, n_completed)


def _seed_team_registry(db_utils) -> None:
    """Insert all known MLS teams into the team_registry table."""
    from features.travel_features import _STADIUMS
    from data_pipeline.asa_client import get_conference, _FIRST_SEASON

    teams = [
        ("ATL", "Atlanta United FC", "ATL", 2017),
        ("ATX", "Austin FC", "ATX", 2021),
        ("CLT", "Charlotte FC", "CLT", 2022),
        ("CHI", "Chicago Fire FC", "CHI", 1998),
        ("CIN", "FC Cincinnati", "CIN", 2019),
        ("COL", "Colorado Rapids", "COL", 1996),
        ("CLB", "Columbus Crew", "CLB", 1996),
        ("DC", "D.C. United", "DC", 1996),
        ("DAL", "FC Dallas", "DAL", 1996),
        ("HOU", "Houston Dynamo FC", "HOU", 2006),
        ("MIA", "Inter Miami CF", "MIA", 2020),
        ("LAG", "LA Galaxy", "LAG", 1996),
        ("LAFC", "Los Angeles FC", "LAFC", 2018),
        ("MIN", "Minnesota United FC", "MIN", 2017),
        ("MTL", "CF Montréal", "MTL", 2012),
        ("NSH", "Nashville SC", "NSH", 2020),
        ("NE", "New England Revolution", "NE", 1996),
        ("NYC", "New York City FC", "NYC", 2015),
        ("NYRB", "New York Red Bulls", "NYRB", 1996),
        ("ORL", "Orlando City SC", "ORL", 2015),
        ("PHI", "Philadelphia Union", "PHI", 2010),
        ("POR", "Portland Timbers", "POR", 2011),
        ("RSL", "Real Salt Lake", "RSL", 2005),
        ("SJ", "San Jose Earthquakes", "SJ", 1996),
        ("SEA", "Seattle Sounders FC", "SEA", 2009),
        ("SKC", "Sporting Kansas City", "SKC", 1996),
        ("STL", "St. Louis City SC", "STL", 2023),
        ("TOR", "Toronto FC", "TOR", 2007),
        ("VAN", "Vancouver Whitecaps FC", "VAN", 2011),
        ("SD", "San Diego FC", "SD", 2025),
    ]

    rows = []
    for team_id, name, short, first_season in teams:
        lat, lon = _STADIUMS.get(team_id, (0.0, 0.0))
        rows.append({
            "team_id": team_id,
            "name": name,
            "short_name": short,
            "conference": get_conference(team_id),
            "first_season": first_season,
            "stadium_lat": lat,
            "stadium_lon": lon,
            "stadium_name": "",
            "active": True,
        })

    df = pd.DataFrame(rows)
    db_utils.upsert_dataframe(df, "team_registry", ["team_id"])
    logger.info("Seeded %d teams to registry.", len(rows))


def _generate_dc_oof(dc_model, train_df: pd.DataFrame, n_folds: int = 5) -> pd.DataFrame:
    """Generate out-of-fold Dixon-Coles predictions via time-series splits."""
    from sklearn.model_selection import TimeSeriesSplit

    dc_oof = []
    tscv = TimeSeriesSplit(n_splits=n_folds)
    idx_array = train_df.index.values

    for tr_idx, val_idx in tscv.split(idx_array):
        tr_data = train_df.iloc[tr_idx]
        val_data = train_df.iloc[val_idx]

        dc_fold = DixonColesModel()
        matches_fold = db_utils.query(  # Use full match table for DC fitting
            "SELECT * FROM matches WHERE status='completed'"
        ).merge(tr_data[["match_id"]], on="match_id")

        try:
            dc_fold.fit(matches_fold)
        except Exception:
            dc_fold = dc_model  # fallback to fully fitted model

        for _, row in val_data.iterrows():
            try:
                preds = dc_fold.predict(
                    row.get("home_team", ""), row.get("away_team", "")
                )
            except Exception:
                preds = {"prob_home": 0.45, "prob_draw": 0.25, "prob_away": 0.30, "prob_over": 0.50}

            dc_oof.append({
                "match_id": row["match_id"],
                "dc_prob_home": preds["prob_home"],
                "dc_prob_draw": preds["prob_draw"],
                "dc_prob_away": preds["prob_away"],
                "dc_prob_over": preds["prob_over"],
            })

    return pd.DataFrame(dc_oof)


if __name__ == "__main__":
    main()
