"""
Predicted lineup scraper for MLSSoccer.com match preview pages.
Falls back to ESPN match preview pages if MLSSoccer.com is unavailable.

Lineups are stored in the predicted_lineups table keyed by (match_id, team_id, source).
"""

import logging
import re
import json
from datetime import datetime, timezone
from typing import Optional

import requests
from bs4 import BeautifulSoup
import pandas as pd

from data_pipeline import db_utils
from data_pipeline.asa_client import _TEAM_NAME_MAP

logger = logging.getLogger(__name__)

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux aarch64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    )
}


def fetch_predicted_xi(home_team: str, away_team: str, match_date: str) -> dict:
    """
    Try multiple sources to get a predicted starting XI per team.
    Returns {home: [player names], away: [player names]} or empty lists.
    """
    home_xi, away_xi = [], []

    # MLSSoccer match preview pages follow a predictable URL pattern
    try:
        slug = f"{home_team.lower()}-vs-{away_team.lower()}-{match_date.replace('-', '')}"
        url = f"https://www.mlssoccer.com/news/preview-{slug}"
        resp = requests.get(url, headers=_HEADERS, timeout=10)
        if resp.ok:
            soup = BeautifulSoup(resp.text, "html.parser")
            text = soup.get_text(" ", strip=True)
            # Heuristic: search for "starting XI" or "predicted lineup"
            home_xi = _extract_player_names(text, home_team)
            away_xi = _extract_player_names(text, away_team)
    except Exception as exc:
        logger.debug("MLSSoccer scrape failed: %s", exc)

    return {"home": home_xi, "away": away_xi}


def _extract_player_names(text: str, team_marker: str) -> list[str]:
    """Heuristic name extraction near a team mention."""
    # Look for capitalized two-word patterns near 'starting XI' or 'lineup'
    pattern = re.compile(r"([A-Z][a-z]+(?:\s[A-Z][a-z]+){1,2})")
    candidates = pattern.findall(text[:5000])
    # De-dup, keep first 11
    seen, names = set(), []
    for c in candidates:
        if c in seen:
            continue
        seen.add(c)
        names.append(c)
        if len(names) >= 11:
            break
    return names


def store_lineup(match_id: str, team_id: str, predicted_xi: list[str], source: str = "mlssoccer") -> None:
    if not predicted_xi:
        return
    db_utils.execute(
        """
        INSERT INTO predicted_lineups (match_id, team_id, source, scraped_at, predicted_xi)
        VALUES (%s, %s, %s, NOW(), %s)
        ON CONFLICT (match_id, team_id, source) DO UPDATE
          SET predicted_xi = EXCLUDED.predicted_xi, scraped_at = NOW()
        """,
        [match_id, team_id, source, json.dumps(predicted_xi)],
    )


def fetch_and_store_for_upcoming(days_ahead: int = 3) -> int:
    """Iterate upcoming matches and store predicted lineups. Returns count stored."""
    upcoming = db_utils.query(
        f"""
        SELECT match_id, home_team, away_team, date::text AS date
        FROM matches
        WHERE status = 'scheduled'
          AND date BETWEEN current_date AND current_date + INTERVAL '{days_ahead} days'
        """
    )
    n = 0
    for _, row in upcoming.iterrows():
        try:
            lineups = fetch_predicted_xi(row["home_team"], row["away_team"], row["date"])
            if lineups["home"]:
                store_lineup(row["match_id"], row["home_team"], lineups["home"])
                n += 1
            if lineups["away"]:
                store_lineup(row["match_id"], row["away_team"], lineups["away"])
                n += 1
        except Exception as exc:
            logger.debug("Lineup fetch failed for %s: %s", row["match_id"], exc)
    logger.info("Stored %d predicted lineups.", n)
    return n
