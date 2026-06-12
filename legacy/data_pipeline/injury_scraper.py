"""
Injury and suspension flag scraper.
Sources:
 1. ESPN MLS injury report API (hidden endpoint)
 2. Fallback: parse MLS injury news from RSS headlines
Each team gets binary DP availability flags (dp1, dp2, dp3).
"""

import logging
import re
from datetime import date
from typing import Optional

import requests
import pandas as pd

from config import SETTINGS
from data_pipeline import db_utils
from data_pipeline.asa_client import _TEAM_NAME_MAP

logger = logging.getLogger(__name__)

_ESPN_INJURIES_URL = (
    "https://site.api.espn.com/apis/site/v2/sports/soccer/usa.1/injuries"
)

# Heuristic: players listed as "Out" or "Questionable" with high value are DPs
_OUT_STATUSES = {"out", "injured reserve", "day-to-day", "questionable"}

# Starting goalkeepers per team (manually curated; update at season start)
# Used to flag when a backup GK is likely starting
_STARTING_GKS: dict[str, list[str]] = {
    "ATL":  ["Brad Guzan", "Quentin Westberg"],
    "ATX":  ["Brad Stuver"],
    "CLT":  ["Kristijan Kahlina"],
    "CHI":  ["Chris Brady"],
    "CIN":  ["Roman Celentano"],
    "COL":  ["Zack Steffen"],
    "CLB":  ["Patrick Schulte"],
    "DC":   ["Luis Barraza"],
    "DAL":  ["Maarten Paes"],
    "HOU":  ["Steve Clark"],
    "MIA":  ["Drake Callender", "Oscar Ustari"],
    "LAG":  ["Novak Mićović"],
    "LAFC": ["Hugo Lloris"],
    "MIN":  ["Dayne St. Clair"],
    "MTL":  ["Jonathan Sirois"],
    "NSH":  ["Joe Willis"],
    "NE":   ["Aljaž Ivačič"],
    "NYC":  ["Matt Freese"],
    "NYRB": ["Carlos Coronel"],
    "ORL":  ["Pedro Gallese"],
    "PHI":  ["Andre Blake"],
    "POR":  ["James Pantemis"],
    "RSL":  ["Rafael Cabral"],
    "SJ":   ["Daniel"],
    "SEA":  ["Stefan Frei"],
    "SKC":  ["Tim Melia", "John Pulskamp"],
    "STL":  ["Roman Bürki"],
    "TOR":  ["Sean Johnson"],
    "VAN":  ["Yohei Takaoka"],
    "SD":   ["CJ Dos Santos"],
}


def fetch_espn_injuries() -> pd.DataFrame:
    """
    Pull the ESPN injury report for MLS. Returns one row per injured player.
    Columns: team_id, player_name, status, is_dp_flag
    """
    try:
        resp = requests.get(_ESPN_INJURIES_URL, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        logger.warning("ESPN injury API failed: %s. Returning empty.", exc)
        return pd.DataFrame(columns=["team_id", "player_name", "status", "is_dp_flag"])

    rows = []
    for team_entry in data.get("injuries", []):
        team_name = team_entry.get("team", {}).get("displayName", "")
        team_id = _TEAM_NAME_MAP.get(team_name, team_name)

        for injury in team_entry.get("injuries", []):
            athlete = injury.get("athlete", {})
            status_raw = injury.get("status", {}).get("type", {}).get("description", "")
            position = athlete.get("position", {}).get("abbreviation", "")
            salary = athlete.get("salary", 0) or 0

            rows.append({
                "team_id": team_id,
                "player_name": athlete.get("displayName", ""),
                "status": status_raw.lower(),
                "position": position,
                "salary": salary,
                "is_dp_flag": False,  # populated below
            })

    df = pd.DataFrame(rows)
    return df


def compute_dp_availability(
    injury_df: pd.DataFrame,
    team_id: str,
) -> dict[str, bool]:
    """
    Return dp1_available, dp2_available, dp3_available for a team.
    Assumes top-3 salary earners are the Designated Players.
    An unavailable DP is one with an out/questionable status.
    """
    if injury_df.empty:
        return {"dp1_available": True, "dp2_available": True, "dp3_available": True}

    team_injuries = injury_df[
        (injury_df["team_id"] == team_id)
        & (injury_df["status"].isin(_OUT_STATUSES))
    ]

    # We don't have salary data directly from ESPN injuries; use position heuristic.
    # Forwards (F, FW) and attacking mids (AM) with injury flags are most impactful.
    attacker_positions = {"f", "fw", "cf", "am", "rw", "lw"}
    attacking_out = team_injuries[
        team_injuries["position"].str.lower().isin(attacker_positions)
    ]

    n_out = len(attacking_out)
    return {
        "dp1_available": n_out < 1,
        "dp2_available": n_out < 2,
        "dp3_available": n_out < 3,
    }


def starting_gk_available(injury_df: pd.DataFrame, team_id: str) -> bool:
    """
    Returns False if the team's primary starting GK is on the injury list.
    Falls back to True if data is unavailable.
    """
    if injury_df.empty:
        return True
    starters = _STARTING_GKS.get(team_id, [])
    if not starters:
        return True
    out = injury_df[
        (injury_df["team_id"] == team_id)
        & (injury_df["status"].isin(_OUT_STATUSES))
        & (injury_df["player_name"].isin(starters))
    ]
    return out.empty


def get_team_availability(team_id: str, injury_df: Optional[pd.DataFrame] = None) -> dict:
    """Return availability flags for a team. Fetches fresh data if not provided."""
    if injury_df is None:
        injury_df = fetch_espn_injuries()
    avail = compute_dp_availability(injury_df, team_id)
    avail["gk_starting_available"] = starting_gk_available(injury_df, team_id)
    return avail


def build_availability_snapshot() -> pd.DataFrame:
    """
    Build a snapshot of DP + GK availability for all MLS teams as of today.
    """
    injury_df = fetch_espn_injuries()
    all_teams = list(set(_TEAM_NAME_MAP.values()))
    rows = []
    for team_id in all_teams:
        avail = compute_dp_availability(injury_df, team_id)
        avail["gk_starting_available"] = starting_gk_available(injury_df, team_id)
        avail["team_id"] = team_id
        avail["as_of"] = date.today().isoformat()
        rows.append(avail)
    return pd.DataFrame(rows)


def count_internationals_unavailable(injury_df: pd.DataFrame, team_id: str, post_fifa_break: bool) -> int:
    """
    Estimate how many internationals are unavailable due to a recent FIFA window.
    Uses the injury status text 'on international duty' if present; otherwise
    returns 0 unless we're directly in the post-break window.
    """
    if not post_fifa_break or injury_df.empty:
        return 0
    matches = injury_df[
        (injury_df["team_id"] == team_id)
        & (injury_df["status"].str.contains("international", case=False, na=False))
    ]
    return len(matches)
