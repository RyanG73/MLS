"""Season windows for the continental ESPN adapter.

The adapter asked every competition for seasons from 2018, which for one founded
later means requests that can never return a row — five per refresh for the
Leagues Cup (2018-2022). ESPN rate-limits by IP and then refuses EVERY endpoint,
so wasted requests are not free: run 31234585894 asked for nine Leagues Cup
seasons and lost all nine to 403s, leaving CI with no cache at all.
"""
from unittest.mock import patch

import pandas as pd
import pytest

from data_pipeline import espn_continental as ec


@pytest.fixture
def no_cache(tmp_path, monkeypatch):
    """Force the fetch path — with a cache present nothing is requested."""
    monkeypatch.setattr(ec, "_CACHE_DIR", tmp_path)
    return tmp_path


def _years_requested(comp_id, seasons=None):
    seen = []

    def fake_fetch(slug, y0, y1, calendar_year=False):
        seen.append(y0)
        return []                      # answered, no events

    # The loop sleeps 0.25s between fetches to be polite to ESPN. That is right
    # in production and pure latency here — nine seasons a test adds up.
    with patch.object(ec, "_fetch", side_effect=fake_fetch), \
         patch.object(ec.time, "sleep"):
        ec.continental_results(comp_id, seasons, use_cache=False)
    return seen


def test_leagues_cup_is_never_asked_for_seasons_before_it_existed(no_cache):
    """Owner, 2026-08-08: "leagues cup began in 2023"."""
    years = _years_requested("leagues-cup")
    assert min(years) == 2023, f"asked for {sorted(years)[:5]}…"
    assert not [y for y in years if y < 2023]


def test_a_caller_supplied_range_is_clamped_not_obeyed(no_cache):
    """The CLI defaults to --from-year 2018, so the floor has to apply to an
    explicit range too or the waste comes straight back."""
    years = _years_requested("leagues-cup", range(2018, 2027))
    assert min(years) == 2023


def test_long_running_competitions_keep_the_default_window(no_cache):
    for comp in ("ucl", "libertadores"):
        assert min(_years_requested(comp)) == ec._DEFAULT_FIRST_SEASON


def test_conference_starts_at_its_first_edition(no_cache):
    assert min(_years_requested("conference")) == 2021


def test_a_narrower_caller_range_is_still_respected(no_cache):
    """Clamping must not widen a window — the refresh workflow asks for just the
    previous and current year and must keep getting exactly that."""
    years = _years_requested("leagues-cup", range(2025, 2027))
    assert years == [2025, 2026]
