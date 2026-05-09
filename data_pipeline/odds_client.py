"""
Fetch Pinnacle MLS odds via The Odds API (free tier: ~500 req/month).
Stores both opening and closing odds for CLV tracking.
API key sourced from ODDS_API_KEY environment variable.
"""

import os
import hashlib
import logging
from datetime import datetime, timezone
from typing import Optional

import requests
import pandas as pd

from config import SETTINGS
from data_pipeline import db_utils

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.the-odds-api.com/v4/sports"
_SPORT = SETTINGS["market"]["sport_key"]
_REGIONS = SETTINGS["market"]["regions"]
_MARKETS = SETTINGS["market"]["markets"]
_ODDS_FORMAT = SETTINGS["market"]["odds_format"]


def _api_key() -> str:
    key = os.environ.get("ODDS_API_KEY", "")
    if not key:
        raise EnvironmentError("ODDS_API_KEY environment variable not set.")
    return key


def _odds_id(match_id: str, bookmaker: str, market: str, outcome: str) -> str:
    return hashlib.md5(f"{match_id}_{bookmaker}_{market}_{outcome}".encode()).hexdigest()[:20]


def fetch_current_odds() -> pd.DataFrame:
    """
    Fetch current Pinnacle 1X2 odds for all upcoming MLS games.
    Returns DataFrame matching the `odds` table schema.
    """
    url = f"{_BASE_URL}/{_SPORT}/odds"
    params = {
        "apiKey": _api_key(),
        "regions": _REGIONS,
        "markets": _MARKETS,
        "oddsFormat": _ODDS_FORMAT,
        "bookmakers": "pinnacle",
    }
    resp = requests.get(url, params=params, timeout=15)
    resp.raise_for_status()
    events = resp.json()

    logger.info(
        "Odds API: %s requests used, %s remaining.",
        resp.headers.get("x-requests-used", "?"),
        resp.headers.get("x-requests-remaining", "?"),
    )

    rows = []
    now = datetime.now(timezone.utc).isoformat()
    for event in events:
        match_id = _resolve_match_id(event)
        if not match_id:
            continue
        for bookmaker in event.get("bookmakers", []):
            bk = bookmaker.get("key", "")
            for market in bookmaker.get("markets", []):
                mkt = market.get("key", "")
                for outcome in market.get("outcomes", []):
                    name = outcome.get("name", "")
                    price = outcome.get("price")
                    if price is None:
                        continue
                    rows.append({
                        "odds_id": _odds_id(match_id, bk, mkt, name),
                        "match_id": match_id,
                        "bookmaker": bk,
                        "market": mkt,
                        "outcome": name,
                        "open_odds": price,
                        "close_odds": None,
                        "fetched_at": now,
                    })

    return pd.DataFrame(rows)


def update_closing_odds() -> pd.DataFrame:
    """
    For matches that just kicked off, re-fetch odds and mark as closing.
    Should be called ~15 minutes before each match.
    """
    # Re-use the same endpoint; The Odds API returns odds closest to kickoff
    df = fetch_current_odds()
    if df.empty:
        return df
    # Mark these as closing odds by updating close_odds column
    df = df.rename(columns={"open_odds": "close_odds"})
    df["open_odds"] = None
    return df


def get_pinnacle_implied_prob(match_id: str) -> Optional[dict]:
    """
    Return vig-adjusted implied probabilities for a match from stored odds.
    Returns dict with keys: home, draw, away, or None if no odds found.
    """
    df = db_utils.query(
        """
        SELECT outcome, open_odds
        FROM odds
        WHERE match_id = %s AND bookmaker = 'pinnacle' AND market = 'h2h'
        ORDER BY fetched_at DESC
        LIMIT 6
        """,
        [match_id],
    )
    if df.empty:
        return None

    outcome_map = {}
    for _, row in df.iterrows():
        outcome_map[row["outcome"]] = row["open_odds"]

    home_odds = outcome_map.get("Home") or outcome_map.get(list(outcome_map.keys())[0] if outcome_map else None)
    draw_odds = outcome_map.get("Draw")
    away_odds = outcome_map.get("Away") or outcome_map.get(list(outcome_map.keys())[-1] if outcome_map else None)

    if not (home_odds and away_odds):
        return None

    raw_home = 1.0 / home_odds
    raw_draw = (1.0 / draw_odds) if draw_odds else 0.0
    raw_away = 1.0 / away_odds
    total = raw_home + raw_draw + raw_away

    if total <= 0:
        return None

    return {
        "home": raw_home / total,
        "draw": raw_draw / total,
        "away": raw_away / total,
    }


def _resolve_match_id(event: dict) -> Optional[str]:
    """Map ESPN event to internal match_id via home/away team and date."""
    from data_pipeline.schedule_client import _ESPN_TO_TEAM, _match_id
    home = _ESPN_TO_TEAM.get(event.get("home_team", ""), event.get("home_team", ""))
    away = _ESPN_TO_TEAM.get(event.get("away_team", ""), event.get("away_team", ""))
    dt = event.get("commence_time", "")[:10]
    if not (home and away and dt):
        return None
    return _match_id(home, away, dt)


def sync_to_db() -> None:
    df = fetch_current_odds()
    if not df.empty:
        n = db_utils.upsert_dataframe(df, "odds", ["odds_id"])
        logger.info("Synced %d odds rows to DuckDB.", n)
