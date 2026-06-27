"""
Tests that walk-forward train/cal/test splits never leak future data.

These tests simulate the split logic used in eval_baseline.py and assert
that no training row has a date >= the test cutoff, and no calibration row
has a date >= the test season's first day.
"""

import pandas as pd
import numpy as np
import pytest


# ── Helpers replicating the eval_baseline split logic ──────────────────────

COVID = {2020}


def make_splits(df: pd.DataFrame, test_seasons: list[int]) -> list[dict]:
    """
    Replicate the walk-forward split logic from eval_baseline.py.
    Returns a list of dicts with keys: test_season, train, cal, test.
    """
    splits = []
    for test_season in test_seasons:
        cal_season = test_season - 1
        # Skip back over COVID years for the cal fold
        while cal_season in COVID:
            cal_season -= 1

        train = df[df["season"] < cal_season].copy()
        cal   = df[df["season"] == cal_season].copy()
        test  = df[df["season"] == test_season].copy()
        splits.append(dict(
            test_season=test_season,
            cal_season=cal_season,
            train=train, cal=cal, test=test,
        ))
    return splits


# ── Fixtures ────────────────────────────────────────────────────────────────

def _make_df(seasons=range(2017, 2026), matches_per_season=10) -> pd.DataFrame:
    rows = []
    for s in seasons:
        if s in COVID:
            continue
        for i in range(matches_per_season):
            rows.append({
                "match_id": f"{s}_{i}",
                "season": s,
                "date": pd.Timestamp(f"{s}-03-01") + pd.Timedelta(weeks=i),
                "home_team": "ATL",
                "away_team": "MIA",
                "home_goals": 1,
                "away_goals": 0,
            })
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    return df


# ── Tests ───────────────────────────────────────────────────────────────────

class TestSplitDisjointness:
    """Train, cal, and test splits must be fully disjoint."""

    @pytest.fixture
    def splits(self):
        df = _make_df()
        return make_splits(df, test_seasons=[2022, 2023, 2024, 2025])

    def test_train_cal_test_match_ids_disjoint(self, splits):
        for sp in splits:
            train_ids = set(sp["train"]["match_id"])
            cal_ids   = set(sp["cal"]["match_id"])
            test_ids  = set(sp["test"]["match_id"])
            assert train_ids.isdisjoint(cal_ids),  \
                f"Train/cal overlap in test season {sp['test_season']}"
            assert train_ids.isdisjoint(test_ids), \
                f"Train/test overlap in test season {sp['test_season']}"
            assert cal_ids.isdisjoint(test_ids),   \
                f"Cal/test overlap in test season {sp['test_season']}"

    def test_all_seasons_represented_in_train(self, splits):
        for sp in splits:
            # Train must contain at least 2017 data
            assert 2017 in sp["train"]["season"].values, \
                f"2017 missing from train for test season {sp['test_season']}"

    def test_cal_is_season_before_test(self, splits):
        for sp in splits:
            assert sp["cal"]["season"].nunique() == 1
            assert sp["cal"]["season"].iloc[0] == sp["cal_season"]


class TestNoFutureLeakage:
    """No row in train or cal must have a date on or after the test season."""

    @pytest.fixture
    def splits(self):
        df = _make_df()
        return make_splits(df, test_seasons=[2022, 2023, 2024, 2025])

    def test_train_dates_before_cal_season(self, splits):
        for sp in splits:
            cal_season_start = pd.Timestamp(f"{sp['cal_season']}-01-01")
            future_in_train = sp["train"][sp["train"]["date"] >= cal_season_start]
            assert len(future_in_train) == 0, (
                f"Train set for test_season={sp['test_season']} contains "
                f"{len(future_in_train)} rows from cal season or later. "
                f"Earliest offending date: {future_in_train['date'].min()}"
            )

    def test_cal_dates_before_test_season(self, splits):
        for sp in splits:
            test_season_start = pd.Timestamp(f"{sp['test_season']}-01-01")
            future_in_cal = sp["cal"][sp["cal"]["date"] >= test_season_start]
            assert len(future_in_cal) == 0, (
                f"Cal set for test_season={sp['test_season']} contains "
                f"{len(future_in_cal)} rows from test season or later."
            )

    def test_test_dates_within_test_season(self, splits):
        for sp in splits:
            ts = sp["test_season"]
            out_of_season = sp["test"][sp["test"]["season"] != ts]
            assert len(out_of_season) == 0, \
                f"Test set for {ts} contains rows from other seasons."


class TestRollingFeatureLeakage:
    """
    Rolling features computed for a match must only use games strictly before
    that match's date (no same-day or future rows).
    """

    def _compute_rolling_xg(self, df: pd.DataFrame, team: str,
                            as_of: pd.Timestamp, window: int) -> float:
        """Replicate the rolling xG computation from eval_baseline."""
        team_games = df[
            (df["home_team"] == team) | (df["away_team"] == team)
        ].copy()
        team_games = team_games[team_games["date"] < as_of]   # strict < : match itself excluded
        team_games = team_games.sort_values("date").tail(window)
        if team_games.empty:
            return float("nan")
        xg_vals = team_games.apply(
            lambda r: r["home_xg"] if r["home_team"] == team else r["away_xg"], axis=1
        )
        return float(xg_vals.mean())

    def test_rolling_excludes_current_match(self):
        """The match being predicted must not contribute to its own rolling feature."""
        df = pd.DataFrame([
            {"match_id": "m1", "date": pd.Timestamp("2023-03-01"), "season": 2023,
             "home_team": "ATL", "away_team": "MIA", "home_xg": 1.0, "away_xg": 0.5,
             "home_goals": 1, "away_goals": 0},
            {"match_id": "m2", "date": pd.Timestamp("2023-03-08"), "season": 2023,
             "home_team": "ATL", "away_team": "CHI", "home_xg": 9.0, "away_xg": 0.1,
             "home_goals": 9, "away_goals": 0},
            {"match_id": "m3", "date": pd.Timestamp("2023-03-15"), "season": 2023,
             "home_team": "MIA", "away_team": "ATL", "home_xg": 2.0, "away_xg": 1.5,
             "home_goals": 2, "away_goals": 1},
        ])

        # When computing the feature for m3 (ATL, 2023-03-15), m3 itself must be excluded
        feat = self._compute_rolling_xg(df, "ATL", pd.Timestamp("2023-03-15"), window=5)
        # Only m1 (xg=1.0) and m2 (xg=9.0) should be included
        assert feat == pytest.approx((1.0 + 9.0) / 2, abs=1e-6), \
            f"Rolling xG leaked current match: {feat}"

    def test_rolling_excludes_future_matches(self):
        """Matches after the as_of date must never appear in rolling features."""
        df = pd.DataFrame([
            {"match_id": "m1", "date": pd.Timestamp("2023-03-01"), "season": 2023,
             "home_team": "ATL", "away_team": "MIA", "home_xg": 1.0, "away_xg": 0.5,
             "home_goals": 1, "away_goals": 0},
            # m2 is AFTER m3's date — must not appear in m3's rolling features
            {"match_id": "m2", "date": pd.Timestamp("2023-04-01"), "season": 2023,
             "home_team": "ATL", "away_team": "CHI", "home_xg": 99.0, "away_xg": 0.1,
             "home_goals": 9, "away_goals": 0},
            {"match_id": "m3", "date": pd.Timestamp("2023-03-15"), "season": 2023,
             "home_team": "MIA", "away_team": "ATL", "home_xg": 2.0, "away_xg": 1.5,
             "home_goals": 2, "away_goals": 1},
        ])

        feat = self._compute_rolling_xg(df, "ATL", pd.Timestamp("2023-03-15"), window=5)
        # Only m1 should be included (m2 is in the future)
        assert feat == pytest.approx(1.0, abs=1e-6), \
            f"Rolling xG leaked a future match: {feat}"


class TestRefereeFeatureLeakage:
    """
    Referee season-lagged features must use only stats from season-1,
    never the current match's season.
    """

    def _compute_ref_stats(self, games: pd.DataFrame) -> dict:
        """Replicate the referee lookup logic from eval_baseline section 5m."""
        games = games.copy()
        games["home_win"] = (games["home_goals"] > games["away_goals"]).astype(float)
        games["is_draw"]  = (games["home_goals"] == games["away_goals"]).astype(float)

        ref_season = (
            games.groupby(["referee", "season"])
            .agg(ref_hw_rate=("home_win", "mean"), ref_draw_rate=("is_draw", "mean"),
                 ref_n=("home_win", "count"))
            .reset_index()
        )
        ref_season = ref_season[ref_season["ref_n"] >= 1]

        lookup = {}
        for _, rr in ref_season.iterrows():
            lookup[(rr["referee"], int(rr["season"]) + 1)] = (
                float(rr["ref_hw_rate"]), float(rr["ref_draw_rate"])
            )
        return lookup

    def test_referee_lookup_uses_prior_season(self):
        """Feature for season N must use ref stats from season N-1 only."""
        games = pd.DataFrame([
            # Season 2022: ref_A always home win → hw_rate=1.0
            {"referee": "ref_A", "season": 2022, "home_goals": 1, "away_goals": 0},
            {"referee": "ref_A", "season": 2022, "home_goals": 2, "away_goals": 0},
            # Season 2023: ref_A always away win → hw_rate=0.0 (must NOT be used for 2023 matches)
            {"referee": "ref_A", "season": 2023, "home_goals": 0, "away_goals": 1},
            {"referee": "ref_A", "season": 2023, "home_goals": 0, "away_goals": 2},
        ])
        lookup = self._compute_ref_stats(games)

        # For a 2023 match with ref_A, we must get 2022 stats (hw_rate=1.0), not 2023 (0.0)
        hw_rate_2023, _ = lookup.get(("ref_A", 2023), (float("nan"), float("nan")))
        assert hw_rate_2023 == pytest.approx(1.0, abs=1e-6), \
            f"Expected 2022 ref stats for 2023 match, got hw_rate={hw_rate_2023}"

    def test_referee_lookup_unavailable_for_debut_season(self):
        """A ref with no prior-season history must not appear in the lookup for their debut."""
        games = pd.DataFrame([
            # ref_B only appears in 2024 — no 2023 data, so lookup[(ref_B, 2024)] must be absent
            {"referee": "ref_B", "season": 2024, "home_goals": 1, "away_goals": 0},
        ])
        lookup = self._compute_ref_stats(games)

        # Should be keyed for 2025 (season+1), not 2024
        assert ("ref_B", 2024) not in lookup, \
            "ref_B should not be in lookup for 2024 (no prior-season data)"
        assert ("ref_B", 2025) in lookup, \
            "ref_B should appear as a 2025 key (2024 data lagged to 2025)"
