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


def test_settled_seasons_already_cached_are_not_refetched(tmp_path, monkeypatch):
    """A completed season's results cannot change, so refetching them every run
    spent the request budget re-learning fixed facts — eight continental slugs
    cost 19 requests each in the 2026-08-08 rebuild. Only the current season and
    the one before it can still move."""
    monkeypatch.setattr(ec, "_CACHE_DIR", tmp_path)
    cache = tmp_path / "ucl.parquet"
    pd.DataFrame([
        {"match_id": f"m{y}", "date": f"{y}-09-01", "season": y,
         "round": "league-phase", "home_team": "A", "away_team": "B",
         "neutral": False, "home_goals": 1, "away_goals": 0,
         "winner": "A", "is_result": True, "home_id": None, "away_id": None}
        for y in range(2018, 2025)
    ]).to_parquet(cache)

    seen = []
    with patch.object(ec, "_fetch", side_effect=lambda s, y0, y1, calendar_year=False:
                      (seen.append(y0), [])[1]), \
         patch.object(ec.time, "sleep"):
        ec.continental_results("ucl", range(2018, 2027), use_cache=False)

    assert 2018 not in seen and 2023 not in seen, f"refetched settled seasons: {seen}"
    assert 2025 in seen and 2026 in seen, f"did not refresh live seasons: {seen}"


def test_an_uncached_old_season_is_still_fetched(tmp_path, monkeypatch):
    """The skip is 'already held', not 'old'. A gap in history must still fill."""
    monkeypatch.setattr(ec, "_CACHE_DIR", tmp_path)
    pd.DataFrame([
        {"match_id": "m", "date": "2024-09-01", "season": 2024,
         "round": "league-phase", "home_team": "A", "away_team": "B",
         "neutral": False, "home_goals": 1, "away_goals": 0,
         "winner": "A", "is_result": True, "home_id": None, "away_id": None}
    ]).to_parquet(tmp_path / "ucl.parquet")

    seen = []
    with patch.object(ec, "_fetch", side_effect=lambda s, y0, y1, calendar_year=False:
                      (seen.append(y0), [])[1]), \
         patch.object(ec.time, "sleep"):
        ec.continental_results("ucl", range(2018, 2027), use_cache=False)
    assert 2021 in seen, f"a season missing from the cache must be fetched: {seen}"


def test_a_narrower_caller_range_is_still_respected(no_cache):
    """Clamping must not widen a window — the refresh workflow asks for just the
    previous and current year and must keep getting exactly that."""
    years = _years_requested("leagues-cup", range(2025, 2027))
    assert years == [2025, 2026]
