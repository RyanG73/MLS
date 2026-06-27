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
