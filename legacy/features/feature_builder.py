"""
Master feature builder.
Assembles all engineered features (ELO, xG, travel, referee, MLS-specific)
into a single match-level DataFrame ready for model training and prediction.
"""

import logging
from typing import Optional
from datetime import date

import pandas as pd
import numpy as np

from config import SETTINGS
from data_pipeline import db_utils
from data_pipeline.asa_client import get_conference, is_expansion_team
from data_pipeline.injury_scraper import get_team_availability
from features.elo_ratings import get_elo_at_date, _INITIAL as ELO_INITIAL
from features.xg_features import (
    compute_team_xg_history,
    compute_rolling_features,
    compute_form_points,
)
from features.travel_features import compute_travel_features
from features.referee_features import get_referee_stats
from features.match_context import build_match_context
from features.style_features import compute_style_features, compute_setpiece_xg_split
from features.suspensions import has_key_player_suspended

logger = logging.getLogger(__name__)

_FT_CFG = SETTINGS["features"]
_WINDOWS = _FT_CFG["xg_windows"]


def build_match_features(
    match_id: str,
    home_team: str,
    away_team: str,
    match_date: str,
    season: int,
    referee_id: Optional[str],
    matches_df: pd.DataFrame,
    injury_df: Optional[pd.DataFrame] = None,
    kickoff_time=None,
    competition: str = "mls",
    weather: Optional[dict] = None,
    is_playoff: bool = False,
) -> dict:
    """
    Build the complete feature vector for a single match.
    matches_df must contain all historical matches (completed + scheduled).
    """
    features: dict = {"match_id": match_id}

    # ── Match context (rivalry, altitude, kickoff, FIFA break, surface, dome) ─
    features.update(build_match_context(home_team, away_team, season, match_date, kickoff_time, competition))

    # ── Weather ──────────────────────────────────────────────────────────────
    if weather:
        features["weather_temp_c"]    = weather.get("weather_temp_c")
        features["weather_wind_kph"]  = weather.get("weather_wind_kph")
        features["weather_precip_mm"] = weather.get("weather_precip_mm")
        features["weather_humidity"]  = weather.get("weather_humidity")

    # ── ELO ──────────────────────────────────────────────────────────────────
    home_elo = get_elo_at_date(home_team, match_date)
    away_elo = get_elo_at_date(away_team, match_date)
    features["home_elo"] = home_elo
    features["away_elo"] = away_elo
    features["elo_diff"] = home_elo - away_elo

    # ── xG rolling features ──────────────────────────────────────────────────
    # Leagues Cup intent varies by team; exclude from form/xG windows.
    # Fatigue (travel features below) still uses all competitions.
    if "competition" in matches_df.columns:
        form_df = matches_df[matches_df["competition"] != "leagues_cup"]
    else:
        form_df = matches_df

    for team_id, role in [(home_team, "home"), (away_team, "away")]:
        history = compute_team_xg_history(form_df, team_id)
        xg_feats = compute_rolling_features(history, match_date, _WINDOWS)
        form = compute_form_points(history, form_df, team_id, match_date)
        features[f"{role}_form_pts_5"] = form
        for k, v in xg_feats.items():
            features[f"{role}_{k}"] = v

    # ── Travel & schedule ────────────────────────────────────────────────────
    # Use full matches_df (all competitions) — Leagues Cup creates real fatigue.
    travel = compute_travel_features(home_team, away_team, match_date, matches_df)
    features.update(travel)

    # ── Referee ──────────────────────────────────────────────────────────────
    ref_stats = get_referee_stats(referee_id)
    features.update(ref_stats)

    # ── MLS-specific ─────────────────────────────────────────────────────────
    features["conference_h"] = get_conference(home_team)
    features["conference_a"] = get_conference(away_team)
    features["is_cross_conference"] = int(features["conference_h"] != features["conference_a"])
    features["is_expansion_home"] = int(is_expansion_team(home_team, season))
    features["is_expansion_away"] = int(is_expansion_team(away_team, season))

    # ── Injury / DP availability ─────────────────────────────────────────────
    home_avail = get_team_availability(home_team, injury_df)
    away_avail = get_team_availability(away_team, injury_df)
    for k, v in home_avail.items():
        features[f"home_{k}"] = int(v)
    for k, v in away_avail.items():
        features[f"away_{k}"] = int(v)

    features["home_dp_count"] = sum([
        features.get("home_dp1_available", 1),
        features.get("home_dp2_available", 1),
        features.get("home_dp3_available", 1),
    ])
    features["away_dp_count"] = sum([
        features.get("away_dp1_available", 1),
        features.get("away_dp2_available", 1),
        features.get("away_dp3_available", 1),
    ])

    # ── Style features (PPDA, possession) ────────────────────────────────────
    for team_id, role in [(home_team, "home"), (away_team, "away")]:
        try:
            style = compute_style_features(team_id, match_date, matches_df)
            for k, v in style.items():
                features[f"{role}_{k}"] = v
        except Exception:
            pass

    # ── Set-piece xG split ───────────────────────────────────────────────────
    for team_id, role in [(home_team, "home"), (away_team, "away")]:
        try:
            sp = compute_setpiece_xg_split(team_id, match_date, matches_df)
            for k, v in sp.items():
                features[f"{role}_{k}"] = v
        except Exception:
            pass

    # ── Suspensions (yellow card accumulation + reds) ────────────────────────
    try:
        features["home_key_player_suspended"] = int(
            has_key_player_suspended(home_team, season, match_date, is_playoff)
        )
        features["away_key_player_suspended"] = int(
            has_key_player_suspended(away_team, season, match_date, is_playoff)
        )
    except Exception:
        features["home_key_player_suspended"] = 0
        features["away_key_player_suspended"] = 0

    features["season"] = season
    return features


def build_training_dataset(matches_df: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """
    Build the full training dataset: one row per completed match with
    all features + outcomes (home_win, draw, away_win, over_2.5).
    """
    if matches_df is None:
        matches_df = db_utils.query(
            "SELECT * FROM matches ORDER BY date ASC"
        )

    completed = matches_df[matches_df["status"] == "completed"].copy()
    completed = completed.dropna(subset=["home_goals", "away_goals"])
    # Leagues Cup matches excluded from training: competitive intent varies by team
    # and they mix MLS clubs against Liga MX opponents (different quality level).
    if "competition" in completed.columns:
        completed = completed[completed["competition"] != "leagues_cup"]
    completed["date"] = pd.to_datetime(completed["date"])
    completed = completed.sort_values("date").reset_index(drop=True)

    rows = []
    logger.info("Building feature matrix for %d completed matches...", len(completed))

    for idx, row in completed.iterrows():
        # Only use matches that occurred before the current row as history
        history_mask = matches_df["date"] < row["date"]
        historical = matches_df[history_mask]

        if len(historical) < 20:
            continue  # Skip very early matches with insufficient history

        try:
            feats = build_match_features(
                match_id=row["match_id"],
                home_team=row["home_team"],
                away_team=row["away_team"],
                match_date=str(row["date"].date()),
                season=int(row["season"]),
                referee_id=row.get("referee_id"),
                matches_df=historical,
            )
        except Exception as exc:
            logger.debug("Feature build failed for %s: %s", row["match_id"], exc)
            continue

        # Labels
        hg, ag = int(row["home_goals"]), int(row["away_goals"])
        feats["date"] = str(row["date"].date())
        feats["home_team"] = row["home_team"]
        feats["away_team"] = row["away_team"]
        feats["home_goals"] = hg
        feats["away_goals"] = ag
        feats["total_goals"] = hg + ag
        feats["label_result"] = 0 if hg > ag else (1 if hg == ag else 2)  # 0=H, 1=D, 2=A
        feats["label_over25"] = int((hg + ag) > 2.5)

        rows.append(feats)

    df = pd.DataFrame(rows)
    logger.info("Feature matrix built: %d rows, %d columns.", len(df), len(df.columns))
    return df


def build_upcoming_features(injury_df=None) -> pd.DataFrame:
    """
    Build features for all upcoming scheduled matches.
    Used at prediction time (no labels).
    """
    all_matches = db_utils.query("SELECT * FROM matches ORDER BY date ASC")
    upcoming = all_matches[all_matches["status"] == "scheduled"].copy()
    upcoming["date"] = pd.to_datetime(upcoming["date"])

    rows = []
    for _, row in upcoming.iterrows():
        try:
            feats = build_match_features(
                match_id=row["match_id"],
                home_team=row["home_team"],
                away_team=row["away_team"],
                match_date=str(row["date"].date()),
                season=int(row["season"]),
                referee_id=row.get("referee_id"),
                matches_df=all_matches,
                injury_df=injury_df,
            )
            feats["date"] = str(row["date"].date())
            feats["home_team"] = row["home_team"]
            feats["away_team"] = row["away_team"]
            rows.append(feats)
        except Exception as exc:
            logger.warning("Feature build failed for upcoming %s: %s", row["match_id"], exc)

    return pd.DataFrame(rows) if rows else pd.DataFrame()


def get_feature_columns(df: pd.DataFrame) -> list[str]:
    """Return model-ready feature columns (exclude IDs, labels, meta cols)."""
    exclude = {
        "match_id", "date", "home_team", "away_team", "home_goals", "away_goals",
        "total_goals", "label_result", "label_over25", "season",
        "conference_h", "conference_a",
        "ref_is_known",
    }
    return [c for c in df.columns if c not in exclude and not c.startswith("_")]
