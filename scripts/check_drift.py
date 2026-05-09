#!/usr/bin/env python3
"""
Nightly drift detector.

Compares the rolling Brier score over the last 4 weeks against the
previous 12-week baseline. If degradation exceeds 5%, fires a
push alert via ntfy.sh.
"""

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("check_drift")

DRIFT_PCT_THRESHOLD = 5.0


def main():
    from data_pipeline import db_utils
    from scripts.notify import notify_drift_alert

    df = db_utils.query(
        """
        SELECT p.match_id, p.prob_home, p.prob_draw, p.prob_away,
               m.home_goals, m.away_goals, m.date
        FROM predictions p
        JOIN matches m ON p.match_id = m.match_id
        WHERE p.model = 'ensemble'
          AND m.status = 'completed'
          AND m.home_goals IS NOT NULL
          AND m.date >= current_date - INTERVAL '120 days'
        ORDER BY m.date
        """
    )
    if df.empty or len(df) < 30:
        logger.info("Insufficient data for drift check (%d rows).", len(df))
        return

    df["date"] = pd.to_datetime(df["date"])
    df["actual_home"] = (df["home_goals"] > df["away_goals"]).astype(int)
    df["actual_draw"] = (df["home_goals"] == df["away_goals"]).astype(int)
    df["actual_away"] = (df["home_goals"] < df["away_goals"]).astype(int)
    df["brier"] = (
        (df["prob_home"] - df["actual_home"]) ** 2 +
        (df["prob_draw"] - df["actual_draw"]) ** 2 +
        (df["prob_away"] - df["actual_away"]) ** 2
    ) / 2

    cutoff_recent   = df["date"].max() - pd.Timedelta(days=28)
    cutoff_baseline = df["date"].max() - pd.Timedelta(days=28 + 84)

    recent = df[df["date"] >= cutoff_recent]
    baseline = df[(df["date"] >= cutoff_baseline) & (df["date"] < cutoff_recent)]

    if recent.empty or baseline.empty:
        logger.info("Recent or baseline window empty; skipping.")
        return

    brier_recent = float(recent["brier"].mean())
    brier_baseline = float(baseline["brier"].mean())
    pct_change = (brier_recent - brier_baseline) / max(brier_baseline, 1e-6) * 100

    logger.info(
        "Drift check: recent Brier=%.4f baseline=%.4f delta=%+.1f%%",
        brier_recent, brier_baseline, pct_change,
    )

    if pct_change > DRIFT_PCT_THRESHOLD:
        notify_drift_alert(brier_recent, brier_baseline, pct_change)
        logger.warning("Drift alert fired.")
    else:
        logger.info("No drift detected.")


if __name__ == "__main__":
    main()
