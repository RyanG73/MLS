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


def _odds_id(match_id: str, bookmaker: str, market: str, outcome: str, snapshot_type: str) -> str:
    return hashlib.md5(
        f"{match_id}_{bookmaker}_{market}_{outcome}_{snapshot_type}".encode()
    ).hexdigest()[:20]


def normalize_outcome(outcome_name: str, event: dict) -> Optional[str]:
    """Normalize sportsbook outcome names to home/draw/away."""
    name = (outcome_name or "").strip()
    if name.lower() in {"draw", "tie"}:
        return "draw"
    if name == event.get("home_team"):
        return "home"
    if name == event.get("away_team"):
        return "away"
    return None


def fetch_current_odds(snapshot_type: str = "open") -> pd.DataFrame:
    """
    Fetch current Pinnacle 1X2 odds for all upcoming MLS games.
    Returns DataFrame matching the `odds` table schema.
    """
    if snapshot_type not in {"open", "close"}:
        raise ValueError("snapshot_type must be 'open' or 'close'")

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
                    name = normalize_outcome(outcome.get("name", ""), event)
                    price = outcome.get("price")
                    if price is None or name is None:
                        continue
                    rows.append({
                        "odds_id": _odds_id(match_id, bk, mkt, name, snapshot_type),
                        "match_id": match_id,
                        "bookmaker": bk,
                        "market": mkt,
                        "outcome": name,
                        "snapshot_type": snapshot_type,
                        "open_odds": price if snapshot_type == "open" else None,
                        "close_odds": price if snapshot_type == "close" else None,
                        "fetched_at": now,
                    })

    return pd.DataFrame(rows)


def update_closing_odds() -> pd.DataFrame:
    """
    For matches that just kicked off, re-fetch odds and mark as closing.
    Should be called ~15 minutes before each match.
    """
    return fetch_current_odds(snapshot_type="close")


def get_pinnacle_odds(match_id: str, snapshot_type: str = "open") -> Optional[dict]:
    """Return latest normalized decimal odds for home/draw/away."""
    odds_col = "close_odds" if snapshot_type == "close" else "open_odds"
    df = db_utils.query(
        f"""
        SELECT DISTINCT ON (outcome) outcome, {odds_col} AS odds
        FROM odds
        WHERE match_id = %s
          AND bookmaker = 'pinnacle'
          AND market = 'h2h'
          AND snapshot_type = %s
          AND {odds_col} IS NOT NULL
        ORDER BY outcome, fetched_at DESC
        """,
        [match_id, snapshot_type],
    )
    if df.empty:
        return None

    result = {row["outcome"]: row["odds"] for _, row in df.iterrows()}
    if not {"home", "away"}.issubset(result):
        return None
    result.setdefault("draw", 0)
    return result


def get_pinnacle_implied_prob(match_id: str) -> Optional[dict]:
    """
    Return vig-adjusted implied probabilities for a match from stored odds.
    Returns dict with keys: home, draw, away, or None if no odds found.
    """
    outcome_map = get_pinnacle_odds(match_id, snapshot_type="open")
    if not outcome_map:
        return None

    home_odds = outcome_map.get("home")
    draw_odds = outcome_map.get("draw")
    away_odds = outcome_map.get("away")

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
    from data_pipeline.asa_client import _TEAM_NAME_MAP

    raw_home = event.get("home_team", "")
    raw_away = event.get("away_team", "")
    home = _ESPN_TO_TEAM.get(raw_home, _TEAM_NAME_MAP.get(raw_home, raw_home))
    away = _ESPN_TO_TEAM.get(raw_away, _TEAM_NAME_MAP.get(raw_away, raw_away))
    dt = event.get("commence_time", "")[:10]
    if not (home and away and dt):
        return None
    return _match_id(home, away, dt)


def sync_to_db(snapshot_type: str = "open") -> int:
    df = fetch_current_odds(snapshot_type=snapshot_type)
    if not df.empty:
        n = db_utils.upsert_dataframe(df, "odds", ["odds_id"])
        logger.info("Synced %d %s odds rows to PostgreSQL.", n, snapshot_type)
        return n
    return 0
