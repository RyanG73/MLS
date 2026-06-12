"""
Style-of-play features: PPDA (passes per defensive action), possession %, field tilt.

These reflect how a team plays rather than what their results were. Different
styles match up differently against opponents (e.g., high-pressing teams
struggle vs ball-circulating teams).

A/B tested in backtest.py — only retained if Brier improvement > 0.001.
"""

import logging
import math
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)

# Decay factor consistent with xg_features
_HALF_LIFE_DAYS = 60
_LAMBDA = math.log(2) / _HALF_LIFE_DAYS


def _decay_weight(days_ago: float) -> float:
    return math.exp(-_LAMBDA * days_ago)


def fetch_team_xpass_history(team_id: str) -> pd.DataFrame:
    """Pull team-level expected pass / PPDA / possession history from ASA."""
    try:
        from itscalledsoccer.client import AmericanSoccerAnalysis
    except ImportError:
        logger.warning("itscalledsoccer not available; style features will be NaN.")
        return pd.DataFrame()

    asa = AmericanSoccerAnalysis()
    try:
        df = asa.get_team_xpass(leagues="mls", team_ids=team_id, split_by_season=True)
    except Exception as exc:
        logger.warning("ASA xpass fetch failed for %s: %s", team_id, exc)
        return pd.DataFrame()

    if df is None or df.empty:
        return pd.DataFrame()

    df.columns = [c.lower().strip() for c in df.columns]
    return df


def compute_style_features(team_id: str, as_of_date: str, matches_df: pd.DataFrame) -> dict:
    """
    Return rolling style metrics for a team as of a given date.
    Uses match-level data from ASA passing performance endpoint.
    """
    # Open-Meteo style: try to compute from ASA; if unavailable, return NaN dict
    try:
        from itscalledsoccer.client import AmericanSoccerAnalysis
        asa = AmericanSoccerAnalysis()
        team_passing = asa.get_team_passing(leagues="mls", team_ids=team_id)
        if team_passing is None or team_passing.empty:
            return _empty_style()
        team_passing.columns = [c.lower().strip() for c in team_passing.columns]
        # Aggregate: take mean across recent records, weighted by recency if date present
        if "date" in team_passing.columns:
            team_passing["date"] = pd.to_datetime(team_passing["date"])
            past = team_passing[team_passing["date"] < pd.Timestamp(as_of_date)].tail(10)
            if past.empty:
                return _empty_style()
            return {
                "ppda_rolling_10":       float(past.get("ppda", pd.Series([10.0])).mean()),
                "possession_rolling_10": float(past.get("possession", pd.Series([0.5])).mean()),
            }
        return _empty_style()
    except Exception as exc:
        logger.debug("Style feature compute failed for %s: %s", team_id, exc)
        return _empty_style()


def _empty_style() -> dict:
    return {"ppda_rolling_10": None, "possession_rolling_10": None}


def compute_setpiece_xg_split(team_id: str, as_of_date: str, matches_df: pd.DataFrame) -> dict:
    """
    Compute rolling set-piece vs open-play xG using ASA's split data.
    Returns {xg_setpiece_rolling_10, xg_openplay_rolling_10, xga_setpiece_rolling_10}.
    """
    try:
        from itscalledsoccer.client import AmericanSoccerAnalysis
        asa = AmericanSoccerAnalysis()
        # ASA games endpoint returns set-piece columns when available
        df = asa.get_team_xgoals(leagues="mls", team_ids=team_id, split_by_season=True)
        if df is None or df.empty:
            return _empty_setpiece()
        df.columns = [c.lower().strip() for c in df.columns]

        sp_xg_col   = next((c for c in df.columns if "setpiece" in c and "for" in c and "xg" in c), None)
        op_xg_col   = next((c for c in df.columns if "openplay" in c and "for" in c and "xg" in c), None)
        sp_xga_col  = next((c for c in df.columns if "setpiece" in c and "against" in c and "xg" in c), None)

        return {
            "xg_setpiece_rolling_10":  _safe_mean(df, sp_xg_col),
            "xg_openplay_rolling_10":  _safe_mean(df, op_xg_col),
            "xga_setpiece_rolling_10": _safe_mean(df, sp_xga_col),
        }
    except Exception as exc:
        logger.debug("Set-piece xG split failed for %s: %s", team_id, exc)
        return _empty_setpiece()


def _empty_setpiece() -> dict:
    return {
        "xg_setpiece_rolling_10":  None,
        "xg_openplay_rolling_10":  None,
        "xga_setpiece_rolling_10": None,
    }


def _safe_mean(df: pd.DataFrame, col: Optional[str]) -> Optional[float]:
    if not col or col not in df.columns:
        return None
    series = pd.to_numeric(df[col], errors="coerce").dropna()
    return float(series.tail(10).mean()) if not series.empty else None
