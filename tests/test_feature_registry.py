"""Unit tests for scripts/eval/feature_registry.py (F4 extraction)."""

import math
import pandas as pd
import pytest

from scripts.eval.feature_registry import (
    PYTHAG_EXP, PYTHAG_WIN,
    FIFA_BREAKS, HIGH_ALT_IDS,
    pythag_expected_pts,
    haversine_km,
    is_post_fifa,
    tz_band,
    away_tz_shift_abs, away_tz_shift_signed,
    zs_within_season,
    lagged_lookup,
    pos_is_att, pos_is_def,
)


class TestPythagorean:
    def test_zero_goals_returns_league_average(self):
        assert pythag_expected_pts(0, 0, 10) == pytest.approx(1.35 * 10)

    def test_zero_games_returns_zero(self):
        assert pythag_expected_pts(5, 3, 0) == 0.0

    def test_equal_goals_returns_half_max(self):
        # win_rate=0.5 → expected = 3*0.5*n = 1.5*n
        assert pythag_expected_pts(5, 5, 10) == pytest.approx(1.5 * 10, abs=1e-6)

    def test_dominant_team(self):
        # gf >> ga → win_rate close to 1 → expected close to 3*n
        val = pythag_expected_pts(50, 5, 10)
        assert val > 25.0  # close to 3*10=30

    def test_exponent_is_1_83(self):
        assert PYTHAG_EXP == pytest.approx(1.83)


class TestHaversine:
    def test_same_point_is_zero(self):
        assert haversine_km((40.75, -74.0), (40.75, -74.0)) == pytest.approx(0.0)

    def test_missing_coord_is_zero(self):
        assert haversine_km(None, (40.75, -74.0)) == 0.0
        assert haversine_km((40.75, -74.0), None) == 0.0

    def test_nyc_to_la_approx(self):
        nyc = (40.71, -74.01)
        la  = (34.05, -118.24)
        dist = haversine_km(nyc, la)
        assert 3900 < dist < 4200  # ~4,000 km

    def test_cross_equator(self):
        north = (10.0, 0.0)
        south = (-10.0, 0.0)
        dist = haversine_km(north, south)
        assert dist == pytest.approx(2 * 10 * 110.57, rel=0.01)


class TestFifaBreaks:
    def test_break_list_nonempty(self):
        assert len(FIFA_BREAKS) > 0

    def test_within_14_days_is_post_fifa(self):
        first_break = FIFA_BREAKS[0]
        assert is_post_fifa(first_break + pd.Timedelta(days=7)) == 1

    def test_day_of_break_not_post_fifa(self):
        # "< date - wb > timedelta(0)" — same day gives delta=0, not counted
        assert is_post_fifa(FIFA_BREAKS[0]) == 0

    def test_15_days_after_not_post_fifa(self):
        assert is_post_fifa(FIFA_BREAKS[0] + pd.Timedelta(days=15)) == 0

    def test_non_break_date_is_zero(self):
        assert is_post_fifa(pd.Timestamp("2024-01-15")) == 0


class TestTzShift:
    def test_tz_band_zero_longitude(self):
        assert tz_band(0.0) == 0

    def test_tz_band_new_york(self):
        assert tz_band(-74.0) == -5

    def test_tz_band_la(self):
        assert tz_band(-118.0) == -8

    def test_away_tz_shift_missing_coord(self):
        assert away_tz_shift_abs("UNKNOWN_TEAM", "ALSO_UNKNOWN") == 0.0
        assert away_tz_shift_signed("UNKNOWN_TEAM", "ALSO_UNKNOWN") == 0.0


class TestHighAlt:
    def test_colorado_is_high_alt(self):
        assert "pzeQZ6xQKw" in HIGH_ALT_IDS

    def test_rsl_is_high_alt(self):
        assert "a2lqR4JMr0" in HIGH_ALT_IDS


class TestZsWithinSeason:
    def test_basic_zscore(self):
        raw = {("A", 2022): 10.0, ("B", 2022): 20.0, ("C", 2022): 30.0}
        result = zs_within_season(raw)
        assert len(result) == 3
        vals = list(result.values())
        assert pytest.approx(sum(vals), abs=1e-6) == 0.0

    def test_too_few_per_season_skipped(self):
        raw = {("A", 2022): 1.0, ("B", 2022): 2.0}  # only 2, needs ≥3
        result = zs_within_season(raw)
        assert len(result) == 0

    def test_multiple_seasons_independent(self):
        raw = {("A", 2022): 5.0, ("B", 2022): 5.0, ("C", 2022): 5.0,
               ("A", 2023): 0.0, ("B", 2023): 1.0, ("C", 2023): 2.0}
        result = zs_within_season(raw)
        # 2022: all equal → z=0 for all
        for t in ("A", "B", "C"):
            assert result[(t, 2022)] == pytest.approx(0.0, abs=1e-4)
        # 2023: A < B < C
        assert result[("A", 2023)] < result[("B", 2023)] < result[("C", 2023)]


class TestLaggedLookup:
    def test_lag_1_found(self):
        tbl = {("A", 2022): 1.5}
        assert lagged_lookup(tbl, "A", 2023) == pytest.approx(1.5)

    def test_lag_2_fallback(self):
        tbl = {("A", 2021): 1.2}
        assert lagged_lookup(tbl, "A", 2023) == pytest.approx(1.2)

    def test_missing_returns_none(self):
        assert lagged_lookup({}, "A", 2023) is None

    def test_lag_1_preferred_over_lag_2(self):
        tbl = {("A", 2022): 1.0, ("A", 2021): 2.0}
        assert lagged_lookup(tbl, "A", 2023) == pytest.approx(1.0)


class TestPositionPredicates:
    def test_forward_is_att(self):
        assert pos_is_att("FW") is True
        assert pos_is_att("forward") is True
        assert pos_is_att("CF") is True

    def test_defender_is_def(self):
        assert pos_is_def("CB") is True
        assert pos_is_def("left back") is True

    def test_goalkeeper_neither(self):
        assert pos_is_att("GK") is False
        assert pos_is_def("GK") is False

    def test_midfielder_neither(self):
        assert pos_is_att("CM") is False
        assert pos_is_def("CM") is False
