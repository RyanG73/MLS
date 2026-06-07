"""Unit tests for scripts/eval/feature_builders.py (F4 extraction)."""

from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import pytest

from scripts.eval.feature_builders import add_rolling_features, add_h2h_draw_features


# ── Test helpers ──────────────────────────────────────────────────────────────

def _ts(days_offset: int) -> pd.Timestamp:
    return pd.Timestamp(datetime(2022, 3, 1) + timedelta(days=days_offset))


def _df(records):
    """Build a minimal match frame from (home, away, hg, ag, days_offset) tuples."""
    rows = []
    for i, (ht, at, hg, ag, d) in enumerate(records):
        rows.append({
            "match_id": str(i),
            "date": _ts(d),
            "season": 2022,
            "home_team": ht, "away_team": at,
            "home_goals": hg, "away_goals": ag,
            "home_xg": float(hg), "away_xg": float(ag),
        })
    return pd.DataFrame(rows)


_XG_WIN  = (3, 5)
_FORM_WIN = (3, 5)
_EMPTY_XPASS: dict = {}


# ── add_rolling_features: output schema ──────────────────────────────────────

class TestRollingSchema:
    def test_xg_columns_created(self):
        df = _df([("A", "B", 1, 0, 0)])
        out = add_rolling_features(df, _XG_WIN, _FORM_WIN, 14, _EMPTY_XPASS)
        for role in ("home", "away"):
            for w in _XG_WIN:
                assert f"{role}_xg_roll_{w}" in out.columns
                assert f"{role}_xga_roll_{w}" in out.columns

    def test_form_columns_created(self):
        df = _df([("A", "B", 1, 0, 0)])
        out = add_rolling_features(df, _XG_WIN, _FORM_WIN, 14, _EMPTY_XPASS)
        for role in ("home", "away"):
            for fw in _FORM_WIN:
                assert f"{role}_form_{fw}" in out.columns

    def test_venue_form_columns_created(self):
        df = _df([("A", "B", 1, 0, 0)])
        out = add_rolling_features(df, _XG_WIN, _FORM_WIN, 14, _EMPTY_XPASS)
        assert "home_home_form_5" in out.columns
        assert "away_away_form_5" in out.columns

    def test_derived_diff_columns_created(self):
        df = _df([("A", "B", 1, 0, 0)])
        out = add_rolling_features(df, _XG_WIN, _FORM_WIN, 14, _EMPTY_XPASS)
        assert "xg_diff" in out.columns
        assert "form_diff" in out.columns
        assert "ha_tilt_sum" in out.columns
        assert "travel_km" in out.columns

    def test_row_count_preserved(self):
        df = _df([("A", "B", i, 0, i) for i in range(10)])
        out = add_rolling_features(df, _XG_WIN, _FORM_WIN, 14, _EMPTY_XPASS)
        assert len(out) == 10


# ── add_rolling_features: walk-forward correctness ───────────────────────────

class TestRollingLeakageSafety:
    def test_first_game_uses_fallback_xg(self):
        """First game has no history → falls back to 1.3."""
        df = _df([("A", "B", 2, 1, 0)])
        out = add_rolling_features(df, (5,), _FORM_WIN, 14, _EMPTY_XPASS)
        assert out["home_xg_roll_5"].iloc[0] == pytest.approx(1.3)
        assert out["away_xg_roll_5"].iloc[0] == pytest.approx(1.3)

    def test_first_game_uses_fallback_form(self):
        df = _df([("A", "B", 1, 0, 0)])
        out = add_rolling_features(df, _XG_WIN, (5,), 14, _EMPTY_XPASS)
        assert out["home_form_5"].iloc[0] == pytest.approx(1.0)

    def test_second_game_uses_first_result(self):
        """After a home win (3pts), form_5 should be 3.0."""
        df = _df([
            ("A", "B", 3, 0, 0),   # A wins 3-0 as home
            ("A", "C", 0, 0, 10),  # A plays again 10 days later
        ])
        out = add_rolling_features(df, _XG_WIN, (5,), 14, _EMPTY_XPASS)
        assert out["home_form_5"].iloc[1] == pytest.approx(3.0)

    def test_does_not_use_current_match_result(self):
        """form_5 in game 2 should NOT reflect game 2's result."""
        df = _df([
            ("A", "B", 1, 0, 0),    # A wins
            ("A", "C", 0, 3, 10),   # A loses badly — form_5 still shows game1 result only
        ])
        out = add_rolling_features(df, _XG_WIN, (5,), 14, _EMPTY_XPASS)
        # After game 1 (A won), form in game 2 = 3.0 (one game of history)
        assert out["home_form_5"].iloc[1] == pytest.approx(3.0)
        # form_5 in game 3 (if we had one) should show game 2's result

    def test_window_respected(self):
        """With window=2, only the last 2 games should be used."""
        df = _df([
            ("A", "B", 1, 0, 0),   # A: 3pts
            ("A", "C", 0, 0, 7),   # A: 1pt
            ("A", "D", 3, 0, 14),  # A: 3pts
            ("A", "E", 0, 0, 21),  # A plays, form_2 should average games 2+3 only
        ])
        out = add_rolling_features(df, _XG_WIN, (2,), 14, _EMPTY_XPASS)
        # Game 4 (index 3): last 2 games for A are game 3 (3pts) and game 2 (1pt) → mean=2.0
        assert out["home_form_2"].iloc[3] == pytest.approx(2.0)


# ── add_rolling_features: congestion ─────────────────────────────────────────

class TestCongestionFeature:
    def test_no_history_gives_zero_games_in_window(self):
        df = _df([("A", "B", 1, 0, 0)])
        out = add_rolling_features(df, _XG_WIN, _FORM_WIN, 14, _EMPTY_XPASS)
        assert out["home_games_in_14d"].iloc[0] == 0

    def test_games_within_window_counted(self):
        df = _df([
            ("A", "B", 1, 0, 0),
            ("A", "C", 1, 0, 5),
            ("A", "D", 1, 0, 10),  # home_games_in_14d should count games at days 0 and 5
        ])
        out = add_rolling_features(df, _XG_WIN, _FORM_WIN, 14, _EMPTY_XPASS)
        assert out["home_games_in_14d"].iloc[2] == 2  # days 0 and 5 are within 14-day lookback

    def test_game_outside_window_not_counted(self):
        df = _df([
            ("A", "B", 1, 0, 0),
            ("A", "C", 1, 0, 20),  # 20 days later, day-0 game is outside 14-day window
        ])
        out = add_rolling_features(df, _XG_WIN, _FORM_WIN, 14, _EMPTY_XPASS)
        assert out["home_games_in_14d"].iloc[1] == 0


# ── add_h2h_draw_features ─────────────────────────────────────────────────────

class TestH2HDrawFeatures:
    def test_output_columns_exist(self):
        df = _df([("A", "B", 1, 0, 0)])
        out = add_h2h_draw_features(df)
        assert "h2h_draw_rate" in out.columns
        assert "h2h_n_games" in out.columns

    def test_first_meeting_has_zero_history(self):
        df = _df([("A", "B", 1, 1, 0)])
        out = add_h2h_draw_features(df, min_games=1)
        assert out["h2h_n_games"].iloc[0] == 0
        assert out["h2h_draw_rate"].iloc[0] == pytest.approx(0.0)

    def test_draw_rate_computed_from_prior_meetings(self):
        df = _df([
            ("A", "B", 1, 1, 0),   # draw
            ("B", "A", 0, 0, 10),  # draw (reversed fixture, same pair)
            ("A", "B", 2, 1, 20),  # win — h2h_draw_rate should be 2/2 = 1.0 at min_games=2
        ])
        out = add_h2h_draw_features(df, min_games=2)
        assert out["h2h_draw_rate"].iloc[2] == pytest.approx(1.0)  # both prior were draws

    def test_min_games_threshold_respected(self):
        df = _df([
            ("A", "B", 1, 1, 0),
            ("A", "B", 0, 0, 10),
            ("A", "B", 1, 0, 20),  # 3rd meeting, min_games=3: rate should still be 0
        ])
        out = add_h2h_draw_features(df, min_games=3)
        # Only 2 prior meetings at game 3 → below threshold → rate = 0.0
        assert out["h2h_draw_rate"].iloc[2] == pytest.approx(0.0)

    def test_direction_agnostic(self):
        """A vs B and B vs A count as the same pair."""
        df = _df([
            ("A", "B", 1, 1, 0),
            ("B", "A", 0, 0, 10),
            ("A", "B", 1, 0, 20),
        ])
        out_direct   = add_h2h_draw_features(df, min_games=1)
        # After game 2 (B vs A), the 3rd game sees 2 prior meetings
        assert out_direct["h2h_n_games"].iloc[2] == 2

    def test_different_pairs_independent(self):
        df = _df([
            ("A", "B", 1, 1, 0),
            ("C", "D", 2, 1, 5),  # different pair
            ("A", "B", 1, 0, 10),
        ])
        out = add_h2h_draw_features(df, min_games=1)
        assert out["h2h_n_games"].iloc[2] == 1  # only 1 prior A vs B meeting

    def test_walk_forward_no_future_leakage(self):
        """h2h_draw_rate for game N must NOT include game N's result."""
        df = _df([
            ("A", "B", 1, 1, 0),   # draw
            ("A", "B", 1, 1, 10),  # draw: at this point h2h_n_games=1, rate=1.0 (1 draw)
            ("A", "B", 3, 0, 20),  # win: h2h sees 2 draws → rate=1.0 (not yet updated)
        ])
        out = add_h2h_draw_features(df, min_games=1)
        # Game 3 (index 2) sees 2 prior draws → rate = 1.0
        assert out["h2h_draw_rate"].iloc[2] == pytest.approx(1.0)
        # Not 2/3 (which would mean game 3's result was included)
