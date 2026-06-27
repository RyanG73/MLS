"""Tests for scripts/eval/tier_bridge.py."""
from __future__ import annotations

import bisect
import math
from typing import NamedTuple
from unittest import mock

import pandas as pd
import pytest


# ── _build_fd_elo_history ─────────────────────────────────────────────────────

def _make_fd_df(rows):
    """Build a minimal football_data-style DataFrame for testing."""
    return pd.DataFrame(rows, columns=[
        "match_id", "date", "season", "home_team", "away_team",
        "home_goals", "away_goals", "home_xg", "away_xg",
        "label_result", "is_result", "is_playoff",
    ])


def test_build_fd_elo_history_returns_per_team_history():
    """_build_fd_elo_history returns a dict of (dates, elos) per team."""
    rows = [
        ("m1", pd.Timestamp("2022-08-01"), 2022, "Alpha", "Beta", 2, 0, None, None, 0, True, 0),
        ("m2", pd.Timestamp("2022-08-08"), 2022, "Beta",  "Alpha", 1, 1, None, None, 1, True, 0),
        ("m3", pd.Timestamp("2022-08-15"), 2022, "Alpha", "Beta", 0, 1, None, None, 2, True, 0),
    ]
    df = _make_fd_df(rows)

    from scripts.eval import tier_bridge as tb
    tb._FD_ELO_HISTORY_CACHE.clear()
    with mock.patch("data_pipeline.football_data.match_results", return_value=df):
        history = tb._build_fd_elo_history("championship")

    assert "Alpha" in history
    assert "Beta" in history
    dates_a, elos_a = history["Alpha"]
    assert len(dates_a) == 3  # 3 matches: appears twice as home, once as away
    # ELOs should be pre-match (same pattern as league_bridge)
    assert all(isinstance(e, float) for e in elos_a)


def test_build_fd_elo_history_empty_df_returns_empty():
    """Empty dataframe (no results yet) returns empty history."""
    from scripts.eval import tier_bridge as tb
    tb._FD_ELO_HISTORY_CACHE.clear()
    empty = pd.DataFrame(columns=[
        "match_id", "date", "season", "home_team", "away_team",
        "home_goals", "away_goals", "home_xg", "away_xg",
        "label_result", "is_result", "is_playoff",
    ])
    with mock.patch("data_pipeline.football_data.match_results", return_value=empty):
        history = tb._build_fd_elo_history("championship")
    assert history == {}


# ── _identify_promotions ──────────────────────────────────────────────────────

def test_identify_promotions_detects_new_teams():
    """Teams in season Y but not Y-1 are identified as promoted."""
    df = _make_fd_df([
        # 2021: Alpha and Beta
        ("m1", pd.Timestamp("2021-08-01"), 2021, "Alpha", "Beta", 1, 0, None, None, 0, True, 0),
        ("m2", pd.Timestamp("2021-09-01"), 2021, "Beta", "Alpha", 0, 0, None, None, 1, True, 0),
        # 2022: Alpha, Beta, and Gamma (new = promoted)
        ("m3", pd.Timestamp("2022-08-01"), 2022, "Alpha", "Gamma", 2, 1, None, None, 0, True, 0),
        ("m4", pd.Timestamp("2022-09-01"), 2022, "Gamma", "Beta", 0, 1, None, None, 2, True, 0),
    ])

    from scripts.eval import tier_bridge as tb
    promotions = tb._identify_promotions(df)
    assert 2022 in promotions
    assert "Gamma" in promotions[2022]
    assert "Alpha" not in promotions[2022]
    assert "Beta" not in promotions[2022]


def test_identify_promotions_first_season_has_no_promotions():
    """The first season in the dataset has no prior to compare against."""
    df = _make_fd_df([
        ("m1", pd.Timestamp("2021-08-01"), 2021, "Alpha", "Beta", 1, 0, None, None, 0, True, 0),
    ])
    from scripts.eval import tier_bridge as tb
    promotions = tb._identify_promotions(df)
    assert 2021 not in promotions


# ── _collect_tier_matches ─────────────────────────────────────────────────────

def test_collect_tier_matches_returns_matches_for_promoted_team():
    """Promoted team's first-season matches are collected with their tier2 ELO."""
    tier2_df = _make_fd_df([
        # Championship: Gamma finishes 2021 season
        ("c1", pd.Timestamp("2021-05-01"), 2021, "Gamma", "Delta", 2, 0, None, None, 0, True, 0),
        ("c2", pd.Timestamp("2021-05-08"), 2021, "Delta", "Gamma", 0, 2, None, None, 2, True, 0),
    ])
    tier1_df = _make_fd_df([
        # EPL: Alpha and Beta in 2021; Gamma arrives in 2022
        ("e1", pd.Timestamp("2021-08-01"), 2021, "Alpha", "Beta",  1, 0, None, None, 0, True, 0),
        ("e2", pd.Timestamp("2022-08-01"), 2022, "Alpha", "Gamma", 3, 0, None, None, 0, True, 0),
        ("e3", pd.Timestamp("2022-08-08"), 2022, "Gamma", "Beta",  1, 1, None, None, 1, True, 0),
    ])

    from scripts.eval import tier_bridge as tb

    def _fake_results(league_id, **_):
        return tier2_df if "championship" in league_id else tier1_df

    with mock.patch("data_pipeline.football_data.match_results", side_effect=_fake_results):
        tb._FD_ELO_HISTORY_CACHE.clear()
        matches_by_season = tb._collect_tier_matches("championship", "epl")

    assert 2022 in matches_by_season
    gamma_matches = [m for m in matches_by_season[2022] if m.promoted_team == "Gamma"]
    assert len(gamma_matches) == 2  # two first-season EPL matches involving Gamma
    for m in gamma_matches:
        assert m.promoted_elo > 0
        assert m.season == 2022
