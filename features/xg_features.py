"""
Rolling xG (expected goals) feature computation.
Uses exponential decay weighting so recent matches count more.
Computes per-team rolling xG, xGA, xGD at 5/10/20 match windows.
"""

import math
import logging
from typing import Optional

import pandas as pd
import numpy as np

from config import SETTINGS
from data_pipeline import db_utils

logger = logging.getLogger(__name__)

_FT_CFG = SETTINGS["features"]
_HALF_LIFE = _FT_CFG["xg_half_life_days"]
_WINDOWS = _FT_CFG["xg_windows"]
_MIN_MATCHES = _FT_CFG["min_matches_for_features"]

_LAMBDA = math.log(2) / _HALF_LIFE  # decay constant


def _decay_weight(days_ago: float) -> float:
    return math.exp(-_LAMBDA * days_ago)


def compute_team_xg_history(matches_df: pd.DataFrame, team_id: str) -> pd.DataFrame:
    """
    For a given team, build a per-match record of xG and xGA
    in chronological order, with exponential decay weights.
    Returns DataFrame sorted by date with columns:
      date, xg, xga, xgd
    """
    home = matches_df[(matches_df["home_team"] == team_id) & (matches_df["status"] == "completed")].copy()
    away = matches_df[(matches_df["away_team"] == team_id) & (matches_df["status"] == "completed")].copy()

    home["xg"] = home["home_xg"].fillna(home["home_goals"])
    home["xga"] = home["away_xg"].fillna(home["away_goals"])
    away["xg"] = away["away_xg"].fillna(away["away_goals"])
    away["xga"] = away["home_xg"].fillna(away["home_goals"])

    frames = []
    for df in [home, away]:
        if df.empty:
            continue
        df = df[["date", "xg", "xga", "match_id"]].copy()
        df["date"] = pd.to_datetime(df["date"])
        frames.append(df)

    if not frames:
        return pd.DataFrame(columns=["date", "xg", "xga", "xgd", "match_id"])

    history = pd.concat(frames).sort_values("date").reset_index(drop=True)
    history["xgd"] = history["xg"] - history["xga"]
    return history


def _ewm_window(values: list[float], weights: list[float]) -> float:
    """Weighted average of values using provided weights."""
    if not values:
        return float("nan")
    total_w = sum(weights)
    if total_w == 0:
        return float("nan")
    return sum(v * w for v, w in zip(values, weights)) / total_w


def compute_rolling_features(
    history: pd.DataFrame, as_of_date: str, windows: list[int]
) -> dict[str, Optional[float]]:
    """
    Given team history (all matches before as_of_date), compute rolling
    xG features for each window size using exponential decay.
    """
    as_of = pd.Timestamp(as_of_date)
    past = history[history["date"] < as_of].tail(max(windows) * 2)  # keep buffer

    result: dict[str, Optional[float]] = {}

    for window in windows:
        recent = past.tail(window)
        if len(recent) < _MIN_MATCHES:
            for col in ["xg", "xga", "xgd"]:
                result[f"{col}_rolling_{window}"] = None
            continue

        # Compute days ago for each match relative to as_of
        days_ago_list = [(as_of - row["date"]).days for _, row in recent.iterrows()]
        weights = [_decay_weight(d) for d in days_ago_list]

        xg_vals = recent["xg"].fillna(0).tolist()
        xga_vals = recent["xga"].fillna(0).tolist()
        xgd_vals = recent["xgd"].fillna(0).tolist()

        result[f"xg_rolling_{window}"] = _ewm_window(xg_vals, weights)
        result[f"xga_rolling_{window}"] = _ewm_window(xga_vals, weights)
        result[f"xgd_rolling_{window}"] = _ewm_window(xgd_vals, weights)

    return result


def compute_form_points(history: pd.DataFrame, matches_df: pd.DataFrame, team_id: str, as_of_date: str, window: int = 5) -> Optional[float]:
    """
    Compute rolling form as average points per game (W=3, D=1, L=0) over last N matches.
    """
    as_of = pd.Timestamp(as_of_date)
    home = matches_df[(matches_df["home_team"] == team_id) & (matches_df["status"] == "completed")].copy()
    away = matches_df[(matches_df["away_team"] == team_id) & (matches_df["status"] == "completed")].copy()

    home["date"] = pd.to_datetime(home["date"])
    away["date"] = pd.to_datetime(away["date"])

    home = home[home["date"] < as_of].copy()
    away = away[away["date"] < as_of].copy()

    def pts(row, is_home):
        h, a = row["home_goals"], row["away_goals"]
        if pd.isna(h) or pd.isna(a):
            return None
        h, a = int(h), int(a)
        if is_home:
            return 3 if h > a else (1 if h == a else 0)
        else:
            return 3 if a > h else (1 if h == a else 0)

    home["pts"] = home.apply(lambda r: pts(r, True), axis=1)
    away["pts"] = away.apply(lambda r: pts(r, False), axis=1)

    combined = pd.concat([home[["date", "pts"]], away[["date", "pts"]]]).sort_values("date")
    combined = combined.dropna(subset=["pts"]).tail(window)

    if len(combined) < _MIN_MATCHES:
        return None

    return combined["pts"].mean()


def build_all_team_xg_features(matches_df: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """
    Build xG feature history for every team. Returns a dict {team_id: history_df}.
    """
    teams = set(matches_df["home_team"].tolist() + matches_df["away_team"].tolist())
    return {team: compute_team_xg_history(matches_df, team) for team in teams}
