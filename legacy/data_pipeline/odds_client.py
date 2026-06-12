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
    from data_pipeline.source_health import record_source_run

    error_msg = None
    df = pd.DataFrame()
    try:
        df = fetch_current_odds(snapshot_type=snapshot_type)
    except Exception as exc:
        error_msg = str(exc)
        logger.error("Pinnacle odds fetch failed: %s", exc)

    n = 0
    if not df.empty:
        n = db_utils.upsert_dataframe(df, "odds", ["odds_id"])
        logger.info("Synced %d %s odds rows to PostgreSQL.", n, snapshot_type)

    record_source_run(
        source_name="pinnacle",
        endpoint=f"odds/{snapshot_type}",
        raw_count=len(df),
        parsed_count=len(df),
        matched_count=n,
        error_message=error_msg,
    )
    return n


def odds_matching_report() -> dict:
    """
    Check upcoming matches (next 14 days) for complete 1X2 odds coverage.

    Returns a dict with:
      upcoming          — total upcoming match count
      matched_all_3     — matches that have home + draw + away odds
      missing_draw      — matches with home+away but no draw (invalid 1X2)
      unmatched         — matches with no Pinnacle odds at all
      coverage_pct      — percentage of upcoming matches fully covered
      missing_draw_list — list of "{home} vs {away} ({date})" strings

    Missing draw odds make a 1X2 market incomplete: callers must NOT infer
    draw probability = 0 from the absence of a draw line.
    """
    upcoming_df = db_utils.query("""
        SELECT match_id, home_team, away_team, date
        FROM matches
        WHERE status = 'scheduled'
          AND date >= CURRENT_DATE
          AND date <= CURRENT_DATE + INTERVAL '14 days'
        ORDER BY date
    """)

    if upcoming_df.empty:
        return {
            "upcoming": 0, "matched_all_3": 0,
            "missing_draw": 0, "unmatched": 0,
            "coverage_pct": 0.0, "missing_draw_list": [],
        }

    odds_df = db_utils.query("""
        SELECT DISTINCT ON (match_id, outcome) match_id, outcome
        FROM odds
        WHERE bookmaker = 'pinnacle'
          AND market = 'h2h'
          AND snapshot_type = 'open'
          AND open_odds IS NOT NULL
        ORDER BY match_id, outcome, fetched_at DESC
    """)

    odds_by_match: dict[str, set] = {}
    if not odds_df.empty:
        for mid, grp in odds_df.groupby("match_id"):
            odds_by_match[mid] = set(grp["outcome"].tolist())

    n_matched = n_missing_draw = n_unmatched = 0
    missing_draw_list = []

    for _, row in upcoming_df.iterrows():
        mid = row["match_id"]
        outcomes = odds_by_match.get(mid, set())
        if {"home", "draw", "away"}.issubset(outcomes):
            n_matched += 1
        elif {"home", "away"}.issubset(outcomes):
            n_missing_draw += 1
            missing_draw_list.append(
                f"{row['home_team']} vs {row['away_team']} ({row['date']})"
            )
        else:
            n_unmatched += 1

    total = len(upcoming_df)
    if n_missing_draw:
        logger.warning(
            "odds_matching: %d match(es) have home+away odds but NO draw line "
            "(incomplete 1X2 — do not infer draw=0): %s",
            n_missing_draw, "; ".join(missing_draw_list),
        )

    return {
        "upcoming": total,
        "matched_all_3": n_matched,
        "missing_draw": n_missing_draw,
        "unmatched": n_unmatched,
        "coverage_pct": round(100.0 * n_matched / total, 1) if total else 0.0,
        "missing_draw_list": missing_draw_list,
    }
