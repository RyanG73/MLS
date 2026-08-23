"""Tests for scripts/eval/season_state.py — shared season-state detector."""
from __future__ import annotations

import pytest

from scripts.eval.season_state import (
    season_state, expected_games_per_team, looks_unfinished, typical_games,
    BETWEEN, PRESEASON, IN_PROGRESS, CONCLUDED,
)


# ── PRESEASON ────────────────────────────────────────────────────────────────

def test_preseason_zero_played_upcoming_present():
    # Schedule published but nothing played yet → PRESEASON
    assert season_state(0, 5) == PRESEASON

def test_preseason_zero_played_many_upcoming():
    # Full 380-match EPL schedule with 0 played → PRESEASON
    assert season_state(0, 380) == PRESEASON

def test_preseason_single_upcoming():
    assert season_state(0, 1) == PRESEASON


# ── BETWEEN ─────────────────────────────────────────────────────────────────

def test_between_nothing_played():
    assert season_state(0, 0) == BETWEEN

def test_between_negative_played():
    # guard: negative played treated as not started, no upcoming → BETWEEN
    assert season_state(-1, 0) == BETWEEN


# ── IN_PROGRESS ──────────────────────────────────────────────────────────────

def test_in_progress_upcoming_present():
    assert season_state(10, 5) == IN_PROGRESS

def test_in_progress_single_upcoming():
    assert season_state(1, 1) == IN_PROGRESS

def test_in_progress_final_not_yet_played():
    # Played matches but final has not happened yet (continental knockout)
    assert season_state(50, 0, final_played=False) == IN_PROGRESS

def test_in_progress_final_false_overrides_no_upcoming():
    # Even with 0 upcoming, if final_played=False → still in progress
    assert season_state(100, 0, final_played=False) == IN_PROGRESS


# ── CONCLUDED ────────────────────────────────────────────────────────────────

def test_concluded_played_no_upcoming_no_final_arg():
    # Round-robin league: no final_played arg → CONCLUDED when nothing upcoming
    assert season_state(380, 0) == CONCLUDED

def test_concluded_final_played_true():
    # Continental: final has been played, no upcoming
    assert season_state(125, 0, final_played=True) == CONCLUDED

def test_concluded_final_played_none_no_upcoming():
    # final_played=None (default) with no upcoming → CONCLUDED
    assert season_state(380, 0, final_played=None) == CONCLUDED


# ── Boundary: single played match ────────────────────────────────────────────

def test_boundary_one_played_no_upcoming():
    # Only one match played, none upcoming → CONCLUDED (round-robin sense)
    assert season_state(1, 0) == CONCLUDED

def test_boundary_transition_0_to_1_played():
    assert season_state(0, 0) == BETWEEN
    assert season_state(1, 0) == CONCLUDED


# ── The CONCLUDED verdict, cross-examined ────────────────────────────────────
# season_state() classifies from match COUNTS alone, so "no upcoming fixtures"
# is indistinguishable from "we could not fetch the fixtures". Its callers own
# that distinction. build_league_data's rescue guard compared games played
# against `nT - 1` — ONE round-robin — which only ever covered the first half
# of a double round-robin season, and could not cover a four-round league at
# all. On 2026-08-23 eight leagues published a final table mid-season, Ireland
# among them at 27 of its 36 rounds: 27 exceeds `nT - 1` (9) and even a double
# round-robin (18), so no round-robin yardstick could have caught it.

def test_a_league_halfway_through_a_double_round_robin_is_not_finished():
    """Allsvenskan on 2026-08-17: 16 of 30 rounds, last match 7 days earlier."""
    assert looks_unfinished(16, 30, 7) is True


def test_a_four_round_league_is_not_finished_even_past_a_double_round_robin():
    """League of Ireland: 27 of 36 played. The reason `nT - 1` cannot work —
    27 is already past two round-robins (18) and the season has 9 rounds left."""
    assert looks_unfinished(27, 36, 8) is True


def test_a_league_that_played_its_full_campaign_is_finished():
    assert looks_unfinished(30, 30, 1) is False


def test_a_season_cut_short_and_long_idle_is_finished_not_stalled():
    """The Indian Super League's 2025-26 edition was cut to a three-month
    campaign, so it is short of a normal season AND genuinely over. Games
    played alone would hold it in progress forever; the idle gap decides."""
    assert looks_unfinished(13, 22, 94) is False


def test_no_measurable_expectation_means_no_verdict():
    """A league in its first season here has no history to measure against."""
    assert looks_unfinished(16, None, 7) is False


def test_expected_games_is_measured_from_the_most_recent_prior_season():
    """Ireland ran 11 clubs / 37 games in 2024 and 10 clubs / 36 in 2025."""
    assert expected_games_per_team({2024: 37, 2025: 36}, n_teams=10) == 36


def test_expected_games_falls_back_to_one_round_robin_without_history():
    assert expected_games_per_team({}, n_teams=16) == 15


# ── The yardstick must describe the TYPICAL club, not the busiest ────────────
# Measured 2026-08-23 from the football-data frames: Allsvenskan and Eliteserien
# both run 30 rounds, but their busiest club played 32 in 2024 because the
# relegation play-off rows sit in the same frame. Taking the maximum therefore
# expected 32, and a completed 30-round 2025 season read as two games short —
# a FALSE rescue that would have published a finished league as still in play.
# The League of Ireland fails the same way across a club-count change: 11 clubs
# / max 37 in 2024, 10 clubs / max 36 in 2025. The median is stable across both
# (30, 30, 30 and 36, 36, 36) and needs no tolerance factor to separate them.

def test_the_yardstick_ignores_a_relegation_playoff_tail():
    """Allsvenskan 2024: fourteen clubs on 30, two carried into a play-off."""
    assert typical_games([30] * 14 + [32, 32]) == 30


def test_the_yardstick_survives_a_club_count_change():
    """League of Ireland 2024 (11 clubs) → 2025 (10). Both run 36 rounds."""
    assert typical_games([36] * 9 + [37, 37]) == 36


def test_the_yardstick_of_an_empty_season_is_none():
    assert typical_games([]) is None


def test_a_completed_season_two_games_short_of_last_years_maximum_is_final():
    """The regression this pair exists to prevent: Allsvenskan 2025 played its
    full 30 rounds and must stay FINAL against a 2024 yardstick of 30 — not 32."""
    expected = expected_games_per_team({2024: typical_games([30] * 14 + [32, 32])},
                                       n_teams=16)
    assert looks_unfinished(30, expected, 1) is False


def test_a_league_that_restructures_yearly_errs_toward_still_playing():
    """Argentina's Liga Profesional ran 41, 41, 41, then 34 games per club
    (2022-25) as the torneo format was reshuffled; 2026 is on 21. No history
    can predict that season's length, so the guard cannot get it right — and
    when it is wrong it is wrong in the direction the guard exists to choose:
    holding at in-progress rather than publishing a false final table. The
    error also expires, because the idle window closes 30 days after the last
    match. Tuning a tolerance to make this one case pass would fit two data
    points — the tightest true positive is 23/30 — and lose that margin.
    """
    assert looks_unfinished(34, 41, 1) is True      # inside the idle window
    assert looks_unfinished(34, 41, 31) is False    # and it expires
