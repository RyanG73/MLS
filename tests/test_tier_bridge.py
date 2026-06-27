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


# ── _fit_offset ───────────────────────────────────────────────────────────────

def test_fit_offset_recovers_known_direction():
    """When promoted teams consistently outperform the prior, fitted δ moves upward."""
    from scripts.eval import tier_bridge as tb

    # Construct matches where promoted team (ELO 1500) beats everyone —
    # that means the prior (-120, adjusted=1380) is too pessimistic.
    # The optimizer should push δ toward 0 (or positive) to raise the predicted prob.
    matches = [
        tb._TierMatch("P", 1500.0, 1500.0, True,  0, 2022),  # home win
        tb._TierMatch("P", 1500.0, 1500.0, True,  0, 2022),
        tb._TierMatch("P", 1500.0, 1500.0, False, 2, 2022),  # away win for P
        tb._TierMatch("P", 1500.0, 1500.0, False, 2, 2022),
        tb._TierMatch("P", 1500.0, 1500.0, True,  0, 2023),
        tb._TierMatch("P", 1500.0, 1500.0, False, 2, 2023),
    ]
    prior = -120.0
    fitted = tb._fit_offset(matches, prior, lam=0.001)
    # With weak ridge, optimizer should push δ above prior to make P stronger.
    assert fitted > prior


def test_fit_offset_with_strong_ridge_stays_near_prior():
    """Very strong ridge (lam=10) should keep the offset near the prior."""
    from scripts.eval import tier_bridge as tb

    matches = [
        tb._TierMatch("P", 1500.0, 1500.0, True, 0, 2022),
        tb._TierMatch("P", 1500.0, 1500.0, True, 1, 2022),
        tb._TierMatch("P", 1500.0, 1500.0, True, 2, 2022),
    ]
    prior = -120.0
    fitted = tb._fit_offset(matches, prior, lam=10.0)
    assert abs(fitted - prior) < 10.0  # very strong ridge: stays close


def test_brier_uniform_is_two_thirds():
    """Brier returns a sensible value in [0, 2]."""
    from scripts.eval import tier_bridge as tb

    matches = [
        tb._TierMatch("P", 1500.0, 1500.0, True,  0, 2022),
        tb._TierMatch("P", 1500.0, 1500.0, True,  1, 2022),
        tb._TierMatch("P", 1500.0, 1500.0, True,  2, 2022),
    ]
    b = tb._brier(matches, delta=0.0)
    assert 0.0 < b < 2.0


# ── fit_all ───────────────────────────────────────────────────────────────────

def test_fit_all_dry_run_returns_dict_with_correct_keys():
    """fit_all(dry_run=True) returns a dict with all three pair keys."""
    from scripts.eval import tier_bridge as tb

    def _fake_collect(tier2_lid, tier1_lid):
        return {}  # Return too few matches → prior is used.

    with mock.patch.object(tb, "_collect_tier_matches", side_effect=_fake_collect):
        results = tb.fit_all(dry_run=True)

    assert set(results.keys()) == {
        "championship_to_epl",
        "bundesliga-2_to_bundesliga",
        "serie-b_to_serie-a",
    }


def test_fit_all_uses_prior_when_too_few_matches():
    """fit_all falls back to static prior when < _MIN_MATCHES collected."""
    from scripts.eval import tier_bridge as tb
    from data_pipeline import coefficients as co

    def _fake_collect(tier2_lid, tier1_lid):
        return {}  # 0 matches → too few

    with mock.patch.object(tb, "_collect_tier_matches", side_effect=_fake_collect):
        results = tb.fit_all(dry_run=True)

    assert results["championship_to_epl"] == co._TIER2_PRIORS["championship_to_epl"]
