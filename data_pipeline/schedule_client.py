"""
Fetch upcoming MLS fixtures and completed results from the ESPN hidden API.
No API key required — publicly accessible JSON endpoints.
"""

import logging
import hashlib
from datetime import date, timedelta
from typing import Optional

import requests
import pandas as pd

from config import SETTINGS
from data_pipeline import db_utils
from data_pipeline.asa_client import _safe_int
from data_pipeline.team_metadata import TEAM_NAME_MAP as _TEAM_NAME_MAP, ESPN_TO_TEAM as _ESPN_TO_TEAM, get_conference

logger = logging.getLogger(__name__)

_ESPN_SCOREBOARD_URL = (
    "https://site.api.espn.com/apis/site/v2/sports/soccer/usa.1/scoreboard"
)
_ESPN_SCHEDULE_URL = (
    "https://site.api.espn.com/apis/site/v2/sports/soccer/usa.1/schedule"
)


def _match_id(home: str, away: str, match_date: str) -> str:
    return hashlib.md5(f"{home}_{away}_{match_date}".encode()).hexdigest()[:16]


def _espn_team(competitor: dict) -> str:
    display = competitor.get("team", {}).get("displayName", "")
    short = competitor.get("team", {}).get("abbreviation", "")
    return _ESPN_TO_TEAM.get(display, _TEAM_NAME_MAP.get(display, short))


def fetch_scoreboard(target_date: Optional[date] = None) -> pd.DataFrame:
    """Fetch a single day's ESPN scoreboard. Defaults to today."""
    d = target_date or date.today()
    params = {"dates": d.strftime("%Y%m%d"), "limit": 100}
    resp = requests.get(_ESPN_SCOREBOARD_URL, params=params, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    rows = []
    for event in data.get("events", []):
        competition = event.get("competitions", [{}])[0]
        competitors = competition.get("competitors", [])
        if len(competitors) < 2:
            continue

        home_comp = next((c for c in competitors if c.get("homeAway") == "home"), competitors[0])
        away_comp = next((c for c in competitors if c.get("homeAway") == "away"), competitors[1])

        home = _espn_team(home_comp)
        away = _espn_team(away_comp)
        match_date_str = event.get("date", "")[:10]
        mid = _match_id(home, away, match_date_str)

        status_type = competition.get("status", {}).get("type", {})
        is_finished = status_type.get("completed", False)

        home_score = _safe_int(home_comp.get("score"))
        away_score = _safe_int(away_comp.get("score"))

        season_year = event.get("season", {}).get("year", d.year)

        rows.append({
            "match_id": mid,
            "date": match_date_str,
            "season": season_year,
            "home_team": home,
            "away_team": away,
            "home_goals": home_score if is_finished else None,
            "away_goals": away_score if is_finished else None,
            "home_xg": None,
            "away_xg": None,
            "conference_h": get_conference(home),
            "conference_a": get_conference(away),
            "is_playoff": False,
            "referee_id": None,
            "status": "completed" if is_finished else "scheduled",
            "source": "espn",
        })

    return pd.DataFrame(rows)


def fetch_upcoming_fixtures(days_ahead: int = 14) -> pd.DataFrame:
    """Fetch fixtures for the next N days."""
    frames = []
    for offset in range(days_ahead + 1):
        d = date.today() + timedelta(days=offset)
        try:
            df = fetch_scoreboard(d)
            frames.append(df)
        except Exception as exc:
            logger.warning("ESPN fetch failed for %s: %s", d, exc)
    return pd.concat(frames, ignore_index=True).drop_duplicates("match_id") if frames else pd.DataFrame()


def fetch_recent_results(days_back: int = 7) -> pd.DataFrame:
    """Fetch recent completed results to update match table."""
    frames = []
    for offset in range(1, days_back + 1):
        d = date.today() - timedelta(days=offset)
        try:
            df = fetch_scoreboard(d)
            frames.append(df[df["status"] == "completed"])
        except Exception as exc:
            logger.warning("ESPN fetch failed for %s: %s", d, exc)
    return pd.concat(frames, ignore_index=True).drop_duplicates("match_id") if frames else pd.DataFrame()


def sync_to_db(days_ahead: int = 14, days_back: int = 7) -> int:
    """Sync upcoming fixtures and recent results to PostgreSQL."""
    from data_pipeline.source_health import record_source_run

    error_msg = None
    combined = pd.DataFrame()
    try:
        upcoming = fetch_upcoming_fixtures(days_ahead)
        recent = fetch_recent_results(days_back)
        combined = pd.concat([upcoming, recent], ignore_index=True).drop_duplicates("match_id")
    except Exception as exc:
        error_msg = str(exc)
        logger.error("ESPN schedule fetch failed: %s", exc)

    n = 0
    if not combined.empty:
        n = db_utils.upsert_dataframe(combined, "matches", ["match_id"])
        logger.info("Synced %d fixture/result rows to PostgreSQL.", n)

    record_source_run(
        source_name="espn",
        endpoint="scoreboard",
        raw_count=len(combined),
        parsed_count=len(combined),
        matched_count=n,
        error_message=error_msg,
    )
    return n
