"""American Soccer Analysis API client using the itscalledsoccer Python package."""

import logging
import hashlib
import pandas as pd
from datetime import date
from typing import Optional

from config import SETTINGS
from data_pipeline import db_utils

logger = logging.getLogger(__name__)

# MLS team name normalization — ASA uses full names
_TEAM_NAME_MAP: dict[str, str] = {
    "Atlanta United": "ATL",
    "Austin FC": "ATX",
    "Charlotte FC": "CLT",
    "Chicago Fire": "CHI",
    "FC Cincinnati": "CIN",
    "Colorado Rapids": "COL",
    "Columbus Crew": "CLB",
    "D.C. United": "DC",
    "FC Dallas": "DAL",
    "Houston Dynamo": "HOU",
    "Inter Miami CF": "MIA",
    "LA Galaxy": "LAG",
    "Los Angeles FC": "LAFC",
    "Minnesota United": "MIN",
    "CF Montréal": "MTL",
    "Nashville SC": "NSH",
    "New England Revolution": "NE",
    "New York City FC": "NYC",
    "New York Red Bulls": "NYRB",
    "Orlando City": "ORL",
    "Philadelphia Union": "PHI",
    "Portland Timbers": "POR",
    "Real Salt Lake": "RSL",
    "San Jose Earthquakes": "SJ",
    "Seattle Sounders": "SEA",
    "Sporting Kansas City": "SKC",
    "St. Louis City SC": "STL",
    "Toronto FC": "TOR",
    "Vancouver Whitecaps": "VAN",
    "San Diego FC": "SD",
}


def _match_id(home: str, away: str, match_date: str) -> str:
    key = f"{home}_{away}_{match_date}"
    return hashlib.md5(key.encode()).hexdigest()[:16]


def fetch_matches(
    season: Optional[int] = None,
    start_season: Optional[int] = None,
) -> pd.DataFrame:
    """
    Pull MLS match results from the ASA API.
    Returns a DataFrame conforming to the `matches` table schema.
    """
    try:
        from itscalledsoccer.client import AmericanSoccerAnalysis
    except ImportError:
        logger.error("itscalledsoccer not installed. Run: pip install itscalledsoccer")
        raise

    asa = AmericanSoccerAnalysis()

    seasons = None
    if season:
        seasons = [season]
    elif start_season:
        current = SETTINGS["data"]["current_season"]
        seasons = list(range(start_season, current + 1))

    logger.info("Fetching MLS games from ASA API (seasons=%s)...", seasons)
    games = asa.get_games(leagues="mls", seasons=seasons)

    if games is None or games.empty:
        logger.warning("No games returned from ASA API.")
        return pd.DataFrame()

    # Normalise column names (ASA may change them across versions)
    games.columns = [c.lower().strip() for c in games.columns]

    # Build standardised match rows
    rows = []
    for _, row in games.iterrows():
        home = str(row.get("home_team_name", row.get("home_team", "")))
        away = str(row.get("away_team_name", row.get("away_team", "")))
        match_date = str(row.get("date_time_utc", row.get("date", "")))[:10]
        kickoff_iso = str(row.get("date_time_utc", row.get("date", "")))
        mid = _match_id(home, away, match_date)

        comp_raw = str(row.get("competition", row.get("league", "mls"))).lower()
        if "open" in comp_raw and "cup" in comp_raw:
            competition = "usoc"
        elif "leagues" in comp_raw and "cup" in comp_raw:
            competition = "leagues_cup"
        elif "champions" in comp_raw or "ccc" in comp_raw or "concacaf" in comp_raw:
            competition = "ccc"
        else:
            competition = "mls"

        rows.append({
            "match_id": mid,
            "date": match_date,
            "season": int(row.get("season_name", row.get("season", 0))),
            "home_team": _TEAM_NAME_MAP.get(home, home),
            "away_team": _TEAM_NAME_MAP.get(away, away),
            "home_goals": _safe_int(row.get("home_score", row.get("home_goals"))),
            "away_goals": _safe_int(row.get("away_score", row.get("away_goals"))),
            "home_xg": _safe_float(row.get("home_team_xg", row.get("home_xg"))),
            "away_xg": _safe_float(row.get("away_team_xg", row.get("away_xg"))),
            "conference_h": None,
            "conference_a": None,
            "is_playoff": bool(row.get("is_playoffs", False)),
            "referee_id": None,
            "status": "completed" if _safe_int(row.get("home_score")) is not None else "scheduled",
            "source": "asa",
            "competition": competition,
            "kickoff_time": kickoff_iso if "T" in kickoff_iso else None,
        })

    df = pd.DataFrame(rows).drop_duplicates(subset="match_id")
    logger.info("Fetched %d MLS matches from ASA.", len(df))
    return df


def fetch_team_xg_stats(season: Optional[int] = None) -> pd.DataFrame:
    """
    Pull team-level xG, xGA, and possession stats from ASA.
    Used to seed rolling features before enough per-game data exists.
    """
    try:
        from itscalledsoccer.client import AmericanSoccerAnalysis
    except ImportError:
        raise

    asa = AmericanSoccerAnalysis()
    seasons = [season] if season else None
    stats = asa.get_team_xgoals(leagues="mls", seasons=seasons, split_by_season=True)

    if stats is None or stats.empty:
        return pd.DataFrame()

    stats.columns = [c.lower().strip() for c in stats.columns]
    return stats


def sync_to_db(start_season: Optional[int] = None) -> int:
    """Fetch matches from ASA and upsert into the PostgreSQL matches table."""
    cfg = SETTINGS["data"]
    start = start_season or cfg["backfill_start_season"]
    df = fetch_matches(start_season=start)
    if not df.empty:
        n = db_utils.upsert_dataframe(df, "matches", ["match_id"])
        logger.info("Synced %d match rows to PostgreSQL.", n)
        return n
    return 0


# ─── Conference assignments ───────────────────────────────────────────────────
_CONFERENCE_MAP: dict[str, str] = {
    "ATL": "E", "CLT": "E", "CHI": "E", "CIN": "E", "CLB": "E",
    "DC": "E", "MIA": "E", "MTL": "E", "NSH": "E", "NE": "E",
    "NYC": "E", "NYRB": "E", "ORL": "E", "PHI": "E", "TOR": "E",
    "ATX": "W", "COL": "W", "DAL": "W", "HOU": "W", "LAG": "W",
    "LAFC": "W", "MIN": "W", "POR": "W", "RSL": "W", "SJ": "W",
    "SEA": "W", "SKC": "W", "STL": "W", "VAN": "W", "SD": "W",
}


def get_conference(team_id: str) -> str:
    return _CONFERENCE_MAP.get(team_id, "E")


# ─── Expansion team registry ─────────────────────────────────────────────────
_FIRST_SEASON: dict[str, int] = {
    "ATL": 2017, "ATX": 2021, "CLT": 2022, "CIN": 2019, "MIA": 2020,
    "NSH": 2020, "STL": 2023, "SD": 2025,
}

_EXPANSION_YEARS = SETTINGS["features"]["expansion_team_seasons"]


def is_expansion_team(team_id: str, season: int) -> bool:
    first = _FIRST_SEASON.get(team_id, 1996)
    return (season - first) < _EXPANSION_YEARS


# ─── Helpers ─────────────────────────────────────────────────────────────────
def _safe_int(val) -> Optional[int]:
    try:
        return int(val) if val is not None and str(val) != "nan" else None
    except (ValueError, TypeError):
        return None


def _safe_float(val) -> Optional[float]:
    try:
        return float(val) if val is not None and str(val) != "nan" else None
    except (ValueError, TypeError):
        return None
