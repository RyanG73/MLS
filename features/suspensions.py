"""
Yellow card accumulation and suspension tracking.

MLS rule: a player is suspended for the next match after accumulating 5 yellow
cards in the regular season (resets at playoff start). Red cards trigger
immediate suspensions of varying length.
"""

import logging
from typing import Optional

import pandas as pd

from data_pipeline import db_utils

logger = logging.getLogger(__name__)

_YELLOW_THRESHOLD_REGULAR = 5
_YELLOW_THRESHOLD_PLAYOFF = 3   # Lower threshold in playoffs


def log_cards(match_id: str, season: int, cards: list[dict]) -> None:
    """
    Insert card events from a completed match into card_log.
    Each card dict: {player, team_id, color}
    """
    if not cards:
        return
    df = pd.DataFrame([
        {"match_id": match_id, "player": c["player"], "team_id": c.get("team_id"),
         "card_color": c["color"]}
        for c in cards
    ])
    db_utils.upsert_dataframe(df, "card_log", ["match_id", "player", "card_color"])


def players_suspended_next_match(team_id: str, season: int, as_of_date: str, is_playoff: bool = False) -> list[str]:
    """
    Return list of players suspended for the team's next match.
    Counts yellows in current season-phase + flags any unserved red.
    """
    threshold = _YELLOW_THRESHOLD_PLAYOFF if is_playoff else _YELLOW_THRESHOLD_REGULAR

    yellows = db_utils.query(
        """
        SELECT cl.player, COUNT(*) AS n_yellows
        FROM card_log cl
        JOIN matches m ON cl.match_id = m.match_id
        WHERE cl.team_id = %s
          AND cl.card_color = 'yellow'
          AND m.season = %s
          AND m.is_playoff = %s
          AND m.date < %s
        GROUP BY cl.player
        HAVING COUNT(*) %% %s = 0 AND COUNT(*) > 0
        """,
        [team_id, season, is_playoff, as_of_date, threshold],
    )

    suspended = []
    if not yellows.empty:
        # Suspended if accumulated yellows is divisible by threshold AND most recent card was last match
        suspended.extend(yellows["player"].tolist())

    # Reds: anyone with a red card in the most recent match
    reds = db_utils.query(
        """
        SELECT DISTINCT cl.player
        FROM card_log cl
        JOIN matches m ON cl.match_id = m.match_id
        WHERE cl.team_id = %s
          AND cl.card_color = 'red'
          AND m.season = %s
          AND m.date = (
              SELECT MAX(m2.date) FROM matches m2
              JOIN card_log cl2 ON m2.match_id = cl2.match_id
              WHERE cl2.team_id = %s AND cl2.card_color = 'red' AND m2.date < %s
          )
        """,
        [team_id, season, team_id, as_of_date],
    )
    suspended.extend(reds["player"].tolist())
    return list(set(suspended))


def has_key_player_suspended(team_id: str, season: int, as_of_date: str, is_playoff: bool = False) -> bool:
    """Boolean for feature builder. True if any suspended player exists."""
    return len(players_suspended_next_match(team_id, season, as_of_date, is_playoff)) > 0
