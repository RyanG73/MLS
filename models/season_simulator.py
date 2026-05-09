"""
Monte Carlo season simulation.

Reuses the simulation logic in features/match_importance.py but adds:
- Detailed per-team output (playoff %, Shield %, projected points)
- Persistent storage in season_simulations table
- 10k sims by default for stable estimates
"""

import json
import logging
import uuid
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from data_pipeline import db_utils
from data_pipeline.asa_client import get_conference
from features.match_importance import (
    get_current_standings,
    simulate_remaining_season,
)

logger = logging.getLogger(__name__)

_DEFAULT_SIMS = 10_000
_PLAYOFF_TEAMS_PER_CONFERENCE = 9


def run_season_simulation(season: int, n_sims: int = _DEFAULT_SIMS) -> dict:
    """
    Simulate the rest of the season N times.
    Returns:
      {
        "playoff_probabilities": {team: pct, ...},
        "shield_probabilities": {team: pct, ...},
        "projected_points": {team: mean_pts, ...},
        "projected_finish": {team: mean_finish_position, ...}
      }
    """
    standings = get_current_standings(season)
    if standings.empty:
        return {"error": "No completed matches for this season."}

    base_points = dict(zip(standings["team_id"], standings["points"]))

    upcoming = db_utils.query(
        """
        SELECT p.match_id, p.prob_home, p.prob_draw, p.prob_away,
               m.home_team, m.away_team, m.season, m.date
        FROM predictions p
        JOIN matches m ON p.match_id = m.match_id
        WHERE p.model = 'ensemble'
          AND m.status = 'scheduled'
          AND m.season = %s
          AND m.competition = 'mls'
        """,
        [season],
    )

    if upcoming.empty:
        # No remaining matches; just classify current
        playoff_set = _classify_playoffs(base_points)
        return {
            "playoff_probabilities": {t: (1.0 if t in playoff_set else 0.0) for t in base_points},
            "shield_probabilities":  {t: 0.0 for t in base_points},
            "projected_points":      base_points,
            "projected_finish":      {},
            "n_sims":                0,
        }

    rng = np.random.default_rng(42)

    playoff_counts = {team: 0 for team in base_points}
    shield_counts  = {team: 0 for team in base_points}
    points_sums    = {team: 0.0 for team in base_points}
    finish_sums    = {team: 0.0 for team in base_points}

    for _ in range(n_sims):
        sim_points = dict(base_points)
        for _, row in upcoming.iterrows():
            home, away = row["home_team"], row["away_team"]
            ph, pd_, pa = row["prob_home"], row["prob_draw"], row["prob_away"]

            u = rng.random()
            if u < ph:
                sim_points[home] = sim_points.get(home, 0) + 3
            elif u < ph + pd_:
                sim_points[home] = sim_points.get(home, 0) + 1
                sim_points[away] = sim_points.get(away, 0) + 1
            else:
                sim_points[away] = sim_points.get(away, 0) + 3

        playoff_set = _classify_playoffs(sim_points)
        for t in playoff_set:
            playoff_counts[t] = playoff_counts.get(t, 0) + 1

        # Supporters Shield: most points overall
        max_pts = max(sim_points.values())
        winners = [t for t, p in sim_points.items() if p == max_pts]
        for w in winners:
            shield_counts[w] = shield_counts.get(w, 0) + 1.0 / len(winners)

        # Track projected points + finish
        sorted_pts = sorted(sim_points.items(), key=lambda x: -x[1])
        for pos, (t, p) in enumerate(sorted_pts, start=1):
            points_sums[t] = points_sums.get(t, 0) + p
            finish_sums[t] = finish_sums.get(t, 0) + pos

    result = {
        "playoff_probabilities": {t: playoff_counts.get(t, 0) / n_sims for t in base_points},
        "shield_probabilities":  {t: shield_counts.get(t, 0) / n_sims for t in base_points},
        "projected_points":      {t: round(points_sums.get(t, 0) / n_sims, 1) for t in base_points},
        "projected_finish":      {t: round(finish_sums.get(t, 0) / n_sims, 1) for t in base_points},
        "n_sims":                n_sims,
        "season":                season,
    }

    # Persist
    run_id = str(uuid.uuid4())[:20]
    db_utils.execute(
        """
        INSERT INTO season_simulations (run_id, season, simulated_at, results_json)
        VALUES (%s, %s, NOW(), %s)
        """,
        [run_id, season, json.dumps(result)],
    )
    return result


def _classify_playoffs(points: dict[str, int]) -> set[str]:
    by_conf: dict[str, list] = {"E": [], "W": []}
    for team, pts in points.items():
        conf = get_conference(team)
        by_conf.setdefault(conf, []).append((team, pts))

    qualified = set()
    for conf, teams in by_conf.items():
        teams.sort(key=lambda t: -t[1])
        qualified.update(t for t, _ in teams[:_PLAYOFF_TEAMS_PER_CONFERENCE])
    return qualified


def get_latest_simulation(season: int):
    """Fetch most recent simulation result for a season."""
    df = db_utils.query(
        """
        SELECT results_json, simulated_at FROM season_simulations
        WHERE season = %s ORDER BY simulated_at DESC LIMIT 1
        """,
        [season],
    )
    if df.empty:
        return None
    return {
        "results": json.loads(df["results_json"].iloc[0]),
        "simulated_at": df["simulated_at"].iloc[0],
    }
