#!/usr/bin/env python3
"""
High-frequency pre-match prediction refresh.

Cron schedule: */5 7-23 * * *  (every 5 min during likely match hours)

For each scheduled match within the next 90 minutes:
  1. Refetch lineups (predicted XI scrape)
  2. Refresh injury flags
  3. Re-run prediction with the latest features
  4. Compare to previous prediction; log probability changes
  5. If new value bet appears, trigger ntfy.sh alert
"""

import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("pre_match_update")


WINDOW_MINUTES = 90        # Match must kick off within this many minutes
MIN_REFRESH_INTERVAL_MIN = 30   # Don't re-predict more often than this


def main():
    from data_pipeline import db_utils
    from data_pipeline.lineup_scraper import fetch_predicted_xi, store_lineup
    from data_pipeline.injury_scraper import build_availability_snapshot
    from features.feature_builder import build_match_features
    from models.dixon_coles import DixonColesModel
    from models.gradient_boost import GradientBoostModels
    from models.stacking_ensemble import StackingEnsemble
    from market.kelly import vig_adjusted_prob
    from market.clv_tracker import evaluate_match, store_bets
    from data_pipeline.odds_client import get_pinnacle_implied_prob
    from scripts.notify import notify_value_bet

    now = datetime.now(timezone.utc)
    cutoff = now + timedelta(minutes=WINDOW_MINUTES)

    upcoming = db_utils.query(
        """
        SELECT match_id, home_team, away_team, kickoff_time, season,
               referee_id, competition, date::text AS date
        FROM matches
        WHERE status = 'scheduled'
          AND kickoff_time IS NOT NULL
          AND kickoff_time BETWEEN NOW() AND %s
        ORDER BY kickoff_time
        """,
        [cutoff.isoformat()],
    )

    if upcoming.empty:
        logger.info("No matches in next %d minutes.", WINDOW_MINUTES)
        return

    try:
        dc_model = DixonColesModel.load()
        gb_models = GradientBoostModels.load()
        ensemble = StackingEnsemble.load()
    except FileNotFoundError as exc:
        logger.error("Models not loaded: %s", exc)
        return

    injury_df = build_availability_snapshot()
    all_matches = db_utils.query("SELECT * FROM matches ORDER BY date ASC")

    for _, row in upcoming.iterrows():
        mid = row["match_id"]

        # Throttle: skip if predicted recently
        last_pred = db_utils.query(
            """
            SELECT MAX(predicted_at) AS latest
            FROM predictions
            WHERE match_id = %s AND model = 'ensemble'
            """,
            [mid],
        )
        if not last_pred.empty and last_pred["latest"].iloc[0] is not None:
            age_min = (now - last_pred["latest"].iloc[0].replace(tzinfo=timezone.utc)).total_seconds() / 60
            if age_min < MIN_REFRESH_INTERVAL_MIN:
                continue

        # Refresh lineups
        try:
            xi = fetch_predicted_xi(row["home_team"], row["away_team"], row["date"])
            if xi.get("home"):
                store_lineup(mid, row["home_team"], xi["home"])
            if xi.get("away"):
                store_lineup(mid, row["away_team"], xi["away"])
        except Exception as exc:
            logger.debug("Lineup refresh failed for %s: %s", mid, exc)

        try:
            feats = build_match_features(
                match_id=mid,
                home_team=row["home_team"],
                away_team=row["away_team"],
                match_date=row["date"],
                season=int(row["season"]),
                referee_id=row.get("referee_id"),
                matches_df=all_matches,
                injury_df=injury_df,
                kickoff_time=row.get("kickoff_time"),
                competition=row.get("competition", "mls"),
            )

            dc_probs = dc_model.predict(row["home_team"], row["away_team"])
            gb_probs = gb_models.predict(feats)
            ens_probs = ensemble.predict(dc_probs, gb_probs, dc_probs)
            ensemble.store_predictions(mid, "ensemble", ens_probs)
        except Exception as exc:
            logger.warning("Re-prediction failed for %s: %s", mid, exc)
            continue

        # Check for value bet
        try:
            mp = get_pinnacle_implied_prob(mid)
            if not mp:
                continue
            opening_odds = {k: 1.0 / v if v > 0 else 0 for k, v in mp.items()}
            bets = evaluate_match(mid, ens_probs, opening_odds)
            if bets:
                store_bets(bets)
                for b in bets:
                    notify_value_bet(
                        row["home_team"], row["away_team"],
                        b["outcome_backed"], b["edge_pct"], b["open_odds"] or 0,
                    )
        except Exception as exc:
            logger.debug("Value bet check failed for %s: %s", mid, exc)


if __name__ == "__main__":
    main()
