"""
Dynamic match-importance scoring.

For each upcoming match, simulate the remainder of the season N times
and measure how much each team's playoff probability changes between
winning and losing this specific match. Higher delta = more important match.
"""

import logging
from typing import Optional

import numpy as np
import pandas as pd

from data_pipeline import db_utils

logger = logging.getLogger(__name__)

_DEFAULT_SIMS = 1000
_PLAYOFF_TEAMS_PER_CONFERENCE = 9


def get_current_standings(season: int) -> pd.DataFrame:
    """Compute current points table per team for a season."""
    df = db_utils.query(
        """
        SELECT
            home_team AS team_id, season,
            SUM(CASE WHEN home_goals > away_goals THEN 3
                     WHEN home_goals = away_goals THEN 1 ELSE 0 END) AS pts_home,
            COUNT(*) AS games_home
        FROM matches
        WHERE season = %s AND status = 'completed' AND competition = 'mls'
        GROUP BY home_team, season
        """,
        [season],
    )
    df_away = db_utils.query(
        """
        SELECT
            away_team AS team_id, season,
            SUM(CASE WHEN away_goals > home_goals THEN 3
                     WHEN home_goals = away_goals THEN 1 ELSE 0 END) AS pts_away,
            COUNT(*) AS games_away
        FROM matches
        WHERE season = %s AND status = 'completed' AND competition = 'mls'
        GROUP BY away_team, season
        """,
        [season],
    )

    if df.empty and df_away.empty:
        return pd.DataFrame(columns=["team_id", "points", "games"])

    merged = df.merge(df_away, on=["team_id", "season"], how="outer").fillna(0)
    merged["points"] = merged["pts_home"] + merged["pts_away"]
    merged["games"] = merged["games_home"] + merged["games_away"]
    return merged[["team_id", "points", "games"]]


def _conference_of(team_id: str) -> str:
    from data_pipeline.asa_client import get_conference
    return get_conference(team_id)


def simulate_remaining_season(
    season: int,
    upcoming_predictions: pd.DataFrame,
    n_sims: int = _DEFAULT_SIMS,
    forced_result: Optional[tuple[str, str]] = None,
) -> dict[str, float]:
    """
    Run Monte Carlo simulations of the remaining season.
    Returns {team_id: playoff_probability}.

    forced_result: (match_id, outcome) where outcome in {'home', 'draw', 'away'}.
    If provided, this match's outcome is fixed instead of sampled.
    """
    standings = get_current_standings(season)
    if standings.empty:
        return {}

    base_points = dict(zip(standings["team_id"], standings["points"]))

    if upcoming_predictions.empty:
        return _classify_playoffs(base_points)

    playoff_counts = {team: 0 for team in base_points.keys()}

    rng = np.random.default_rng(42)

    for _ in range(n_sims):
        sim_points = dict(base_points)
        for _, row in upcoming_predictions.iterrows():
            mid = row["match_id"]
            home = row["home_team"]
            away = row["away_team"]
            ph = row["prob_home"]
            pd_ = row["prob_draw"]

            if forced_result and forced_result[0] == mid:
                outcome = forced_result[1]
            else:
                u = rng.random()
                if u < ph:
                    outcome = "home"
                elif u < ph + pd_:
                    outcome = "draw"
                else:
                    outcome = "away"

            if outcome == "home":
                sim_points[home] = sim_points.get(home, 0) + 3
            elif outcome == "away":
                sim_points[away] = sim_points.get(away, 0) + 3
            else:
                sim_points[home] = sim_points.get(home, 0) + 1
                sim_points[away] = sim_points.get(away, 0) + 1

        playoff_set = _classify_playoffs(sim_points)
        for team in playoff_set:
            playoff_counts[team] = playoff_counts.get(team, 0) + 1

    return {team: playoff_counts.get(team, 0) / n_sims for team in base_points.keys()}


def _classify_playoffs(points: dict[str, int]) -> set[str]:
    """Top 9 teams in each conference qualify for playoffs."""
    by_conf: dict[str, list] = {"E": [], "W": []}
    for team, pts in points.items():
        conf = _conference_of(team)
        by_conf.setdefault(conf, []).append((team, pts))

    qualified = set()
    for conf, teams in by_conf.items():
        teams.sort(key=lambda t: -t[1])
        qualified.update(t for t, _ in teams[:_PLAYOFF_TEAMS_PER_CONFERENCE])
    return qualified


def compute_match_importance(
    match_id: str,
    home_team: str,
    away_team: str,
    season: int,
    upcoming_predictions: pd.DataFrame,
    n_sims: int = 500,
) -> dict:
    """
    Returns importance scores for a specific match:
    {home_importance, away_importance, max_importance}

    Importance = |P(playoff | win) - P(playoff | loss)| for each team.
    """
    if upcoming_predictions.empty:
        return {"home_importance": 0.0, "away_importance": 0.0, "max_importance": 0.0}

    p_home_win  = simulate_remaining_season(season, upcoming_predictions, n_sims, (match_id, "home"))
    p_away_win  = simulate_remaining_season(season, upcoming_predictions, n_sims, (match_id, "away"))

    home_imp = abs(p_home_win.get(home_team, 0.0) - p_away_win.get(home_team, 0.0))
    away_imp = abs(p_away_win.get(away_team, 0.0) - p_home_win.get(away_team, 0.0))

    return {
        "home_importance": home_imp,
        "away_importance": away_imp,
        "max_importance":  max(home_imp, away_imp),
    }
