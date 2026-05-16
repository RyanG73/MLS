"""
Referee tendency features.
Pulls referee match data from PostgreSQL (populated via worldfootballR in R bridge).

Null vs league-average distinction:
  - referee_id is None/empty → assignment not yet made → return NULL for all columns
    (XGBoost handles nulls natively; using averages here would be a false signal)
  - referee_id is set but not in our DB → genuinely unknown tendency → league averages
"""

import logging
from typing import Optional

import pandas as pd

from data_pipeline import db_utils

logger = logging.getLogger(__name__)

# League-average fallbacks (computed from historical data; updated periodically)
_LEAGUE_AVG_CARDS_PER90 = 3.8
_LEAGUE_AVG_PENS_PER90 = 0.22
_LEAGUE_AVG_HOME_WIN_RATE = 0.44

_REFEREE_FEATURE_COLS = ["ref_cards_per90", "ref_pens_per90", "ref_home_win_rate", "ref_is_known"]


def get_referee_stats(referee_id: Optional[str]) -> dict:
    """
    Return referee tendency stats.
    Returns NULLs when referee is not yet assigned (referee_id is falsy).
    Falls back to league averages when referee_id is set but not in our DB.
    """
    if not referee_id:
        # Referee not yet assigned — leave features null so model doesn't see a false signal
        return {col: None for col in _REFEREE_FEATURE_COLS}

    df = db_utils.query(
        "SELECT card_rate_per90, penalty_rate_per90, home_win_rate, matches_officiated "
        "FROM referee_stats WHERE referee_id = %s",
        [referee_id],
    )

    if df.empty or df.iloc[0]["matches_officiated"] < 10:
        # Referee known but insufficient history → league average is a reasonable prior
        return _league_average_stats()

    row = df.iloc[0]
    return {
        "ref_cards_per90": float(row["card_rate_per90"]),
        "ref_pens_per90": float(row["penalty_rate_per90"]),
        "ref_home_win_rate": float(row["home_win_rate"]),
        "ref_is_known": True,
    }


def _league_average_stats() -> dict:
    return {
        "ref_cards_per90": _LEAGUE_AVG_CARDS_PER90,
        "ref_pens_per90": _LEAGUE_AVG_PENS_PER90,
        "ref_home_win_rate": _LEAGUE_AVG_HOME_WIN_RATE,
        "ref_is_known": False,
    }


def update_referee_stats_from_r(stats_csv_path: str) -> None:
    """
    Import referee stats computed by the R worldfootballR script.
    Expects a CSV with columns: referee_id, name, card_rate_per90, penalty_rate_per90,
    home_win_rate, matches_officiated.
    """
    df = pd.read_csv(stats_csv_path)
    for col, fallback in [
        ("card_rate_per90", _LEAGUE_AVG_CARDS_PER90),
        ("penalty_rate_per90", _LEAGUE_AVG_PENS_PER90),
        ("home_win_rate", _LEAGUE_AVG_HOME_WIN_RATE),
    ]:
        if col not in df.columns:
            df[col] = fallback
        else:
            df[col] = df[col].fillna(fallback)
    df["last_updated"] = pd.Timestamp.now().isoformat()
    n = db_utils.upsert_dataframe(df, "referee_stats", ["referee_id"])
    logger.info("Updated %d referee stat rows from R output.", n)
