"""Tests for scripts/eval/season_state.py — shared season-state detector."""
from __future__ import annotations

import pytest

from scripts.eval.season_state import season_state, BETWEEN, IN_PROGRESS, CONCLUDED


# ── BETWEEN ─────────────────────────────────────────────────────────────────

def test_between_nothing_played():
    assert season_state(0, 0) == BETWEEN

def test_between_no_played_upcoming_present():
    # upcoming > 0 but played == 0 → still BETWEEN (season not started)
    assert season_state(0, 5) == BETWEEN

def test_between_negative_played():
    # guard: negative played treated as not started
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
