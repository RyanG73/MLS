"""
Travel and schedule congestion features.
- Great-circle distance between stadiums (haversine)
- Days rest since last match
- Number of matches in past 14 days
- Cross-conference flag
"""

import logging
from datetime import date, timedelta

import pandas as pd
from haversine import haversine, Unit

from data_pipeline import db_utils

logger = logging.getLogger(__name__)

# MLS stadium coordinates (lat, lon)
_STADIUMS: dict[str, tuple[float, float]] = {
    "ATL":  (33.7554, -84.4000),   # Mercedes-Benz Stadium
    "ATX":  (30.3877, -97.7191),   # Q2 Stadium
    "CLT":  (35.2271, -80.8530),   # Bank of America Stadium
    "CHI":  (41.8623, -87.6167),   # Soldier Field
    "CIN":  (39.1118, -84.5197),   # TQL Stadium
    "COL":  (39.8059, -105.0177),  # Dick's Sporting Goods Park
    "CLB":  (39.9612, -82.9988),   # Lower.com Field
    "DC":   (38.8682, -77.0121),   # Audi Field
    "DAL":  (33.1543, -97.0572),   # Toyota Stadium
    "HOU":  (29.7522, -95.3588),   # Shell Energy Stadium
    "MIA":  (25.8017, -80.1239),   # Chase Stadium
    "LAG":  (33.8644, -118.2611),  # Dignity Health Sports Park
    "LAFC": (34.0136, -118.2852),  # BMO Stadium
    "MIN":  (44.9530, -93.1647),   # Allianz Field
    "MTL":  (45.5638, -73.5512),   # Stade Saputo
    "NSH":  (36.1300, -86.7678),   # GEODIS Park
    "NE":   (42.0908, -71.2643),   # Gillette Stadium
    "NYC":  (40.8296, -74.0744),   # Yankee Stadium (temporary; Red Bull Arena nearby)
    "NYRB": (40.7369, -74.1502),   # Red Bull Arena
    "ORL":  (28.5416, -81.3892),   # Inter&Co Stadium
    "PHI":  (39.9019, -75.1676),   # Subaru Park
    "POR":  (45.5219, -122.6917),  # Providence Park
    "RSL":  (40.5831, -111.8929),  # America First Field
    "SJ":   (37.3510, -121.9249),  # PayPal Park
    "SEA":  (47.5952, -122.3316),  # Lumen Field
    "SKC":  (39.1220, -94.8234),   # Children's Mercy Park
    "STL":  (38.6311, -90.1878),   # CityPark
    "TOR":  (43.6333, -79.4183),   # BMO Field
    "VAN":  (49.2768, -123.1118),  # BC Place
    "SD":   (32.7073, -117.1566),  # Snapdragon Stadium
}

_DEFAULT_COORDS = (39.5, -98.35)  # Geographic center of USA

# Stadiums with retractable roofs — weather data is irrelevant for these venues
_DOME_STADIUMS: set[str] = {
    "ATL",   # Mercedes-Benz Stadium (ETFE retractable roof, climate-controlled)
    "VAN",   # BC Place (retractable roof)
}


def stadium_coords(team_id: str) -> tuple[float, float]:
    return _STADIUMS.get(team_id, _DEFAULT_COORDS)


def is_dome(team_id: str) -> bool:
    """True if the home team's stadium has a retractable roof / dome."""
    return team_id in _DOME_STADIUMS


def travel_distance_km(home_team: str, away_team: str) -> float:
    """Great-circle distance the away team must travel."""
    home_loc = stadium_coords(home_team)
    away_loc = stadium_coords(away_team)
    return haversine(away_loc, home_loc, unit=Unit.KILOMETERS)


def days_since_last_match(team_id: str, before_date: str, matches_df: pd.DataFrame) -> int:
    """Days since the team's most recent completed match before before_date."""
    before = pd.Timestamp(before_date)
    team_matches = matches_df[
        ((matches_df["home_team"] == team_id) | (matches_df["away_team"] == team_id))
        & (matches_df["status"] == "completed")
    ].copy()
    team_matches["date"] = pd.to_datetime(team_matches["date"])
    past = team_matches[team_matches["date"] < before].sort_values("date", ascending=False)

    if past.empty:
        return 7  # Assume a week rest if no history

    last = past.iloc[0]["date"]
    return max(0, (before - last).days)


def games_in_window(team_id: str, before_date: str, matches_df: pd.DataFrame, days: int = 14) -> int:
    """Number of matches the team played in the N days before before_date."""
    before = pd.Timestamp(before_date)
    cutoff = before - pd.Timedelta(days=days)
    team_matches = matches_df[
        ((matches_df["home_team"] == team_id) | (matches_df["away_team"] == team_id))
        & (matches_df["status"] == "completed")
    ].copy()
    team_matches["date"] = pd.to_datetime(team_matches["date"])
    return int(team_matches[(team_matches["date"] >= cutoff) & (team_matches["date"] < before)].shape[0])


def compute_travel_features(
    home_team: str,
    away_team: str,
    match_date: str,
    matches_df: pd.DataFrame,
) -> dict:
    """
    Compute all travel and schedule features for both teams in a given match.
    Returns flat dict of feature name → value.
    """
    dist = travel_distance_km(home_team, away_team)
    home_rest = days_since_last_match(home_team, match_date, matches_df)
    away_rest = days_since_last_match(away_team, match_date, matches_df)
    home_density = games_in_window(home_team, match_date, matches_df)
    away_density = games_in_window(away_team, match_date, matches_df)

    return {
        "travel_km": dist,
        "home_days_rest": home_rest,
        "away_days_rest": away_rest,
        "home_games_in_14d": home_density,
        "away_games_in_14d": away_density,
        "rest_advantage": home_rest - away_rest,
    }
