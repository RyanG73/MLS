"""
ELO rating system for MLS teams.
- Standard ELO with configurable K-factor and home advantage
- Margin-of-victory multiplier
- Season-start regression toward 1500
- Expansion team prior (1500)
- Full history stored in `elo_history` table
"""

import logging
import math
from datetime import date

import pandas as pd

from config import SETTINGS
from data_pipeline import db_utils

logger = logging.getLogger(__name__)

_ELO_CFG = SETTINGS["elo"]
_INITIAL = _ELO_CFG["initial_rating"]
_K = _ELO_CFG["k_factor"]
_HOME_ADV = _ELO_CFG["home_advantage_elo"]
_USE_MOV = _ELO_CFG["mov_multiplier"]
_REGRESSION = _ELO_CFG["season_regression_pct"]


def expected_score(rating_a: float, rating_b: float) -> float:
    """ELO expected score for team A against team B."""
    return 1.0 / (1.0 + 10 ** ((rating_b - rating_a) / 400.0))


def mov_multiplier(goal_diff: int, elo_diff: float) -> float:
    """
    Margin-of-victory multiplier (Nate Silver / FiveThirtyEight style).
    Diminishing returns for blowouts; accounts for autocorrelation.
    """
    if not _USE_MOV:
        return 1.0
    return math.log(abs(goal_diff) + 1) * (2.2 / (elo_diff * 0.001 + 2.2))


def update_elo(
    home_rating: float,
    away_rating: float,
    home_goals: int,
    away_goals: int,
) -> tuple[float, float]:
    """
    Compute updated ELO ratings after a match.
    Returns (new_home_rating, new_away_rating).
    """
    adjusted_home = home_rating + _HOME_ADV
    exp_home = expected_score(adjusted_home, away_rating)
    exp_away = 1.0 - exp_home

    goal_diff = home_goals - away_goals
    if goal_diff > 0:
        actual_home, actual_away = 1.0, 0.0
    elif goal_diff < 0:
        actual_home, actual_away = 0.0, 1.0
    else:
        actual_home, actual_away = 0.5, 0.5

    elo_diff = adjusted_home - away_rating
    mult = mov_multiplier(goal_diff, elo_diff)

    new_home = home_rating + _K * mult * (actual_home - exp_home)
    new_away = away_rating + _K * mult * (actual_away - exp_away)
    return new_home, new_away


def regress_season(rating: float) -> float:
    """Regress rating toward 1500 at season start."""
    return rating + _REGRESSION * (_INITIAL - rating)


def compute_all_elo(matches_df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute full ELO history from a DataFrame of completed matches
    sorted chronologically. Returns DataFrame with (team_id, date, elo_rating).
    Matches must have columns: match_id, date, season, home_team, away_team,
    home_goals, away_goals, status.
    """
    completed = matches_df[matches_df["status"] == "completed"].copy()
    completed = completed.dropna(subset=["home_goals", "away_goals"])
    completed["date"] = pd.to_datetime(completed["date"])
    completed = completed.sort_values("date").reset_index(drop=True)

    ratings: dict[str, float] = {}
    history: list[dict] = []
    current_season: int | None = None

    for _, row in completed.iterrows():
        season = int(row["season"])
        # Season regression at season start
        if current_season is not None and season != current_season:
            for team in list(ratings.keys()):
                ratings[team] = regress_season(ratings[team])
        current_season = season

        home = row["home_team"]
        away = row["away_team"]

        h_pre = ratings.get(home, _INITIAL)
        a_pre = ratings.get(away, _INITIAL)

        history.append({"team_id": home, "date": row["date"].date().isoformat(), "elo_rating": h_pre})
        history.append({"team_id": away, "date": row["date"].date().isoformat(), "elo_rating": a_pre})

        h_new, a_new = update_elo(h_pre, a_pre, int(row["home_goals"]), int(row["away_goals"]))
        ratings[home] = h_new
        ratings[away] = a_new

    return pd.DataFrame(history)


def get_current_ratings() -> dict[str, float]:
    """Return the most recent ELO rating per team."""
    df = db_utils.query(
        """
        SELECT team_id, elo_rating
        FROM elo_history
        WHERE (team_id, date) IN (
            SELECT team_id, MAX(date) FROM elo_history GROUP BY team_id
        )
        """
    )
    if df.empty:
        return {}
    return dict(zip(df["team_id"], df["elo_rating"]))


def get_elo_at_date(team_id: str, as_of: str) -> float:
    """Return the team's ELO rating as of a specific date (latest record ≤ date)."""
    df = db_utils.query(
        """
        SELECT elo_rating FROM elo_history
        WHERE team_id = %s AND date <= %s
        ORDER BY date DESC LIMIT 1
        """,
        [team_id, as_of],
    )
    return float(df["elo_rating"].iloc[0]) if not df.empty else _INITIAL


def sync_elo_to_db() -> None:
    """Recompute full ELO history from all completed matches and upsert to DB."""
    matches_df = db_utils.query(
        "SELECT match_id, date, season, home_team, away_team, home_goals, away_goals, status FROM matches"
    )
    if matches_df.empty:
        logger.warning("No matches in DB; skipping ELO computation.")
        return

    history_df = compute_all_elo(matches_df)
    if not history_df.empty:
        n = db_utils.upsert_dataframe(history_df, "elo_history", ["team_id", "date"])
        logger.info("Upserted %d ELO history rows.", n)
