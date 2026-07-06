"""Unit tests for scripts/eval/elo.py (F4 extraction)."""

import pandas as pd
import pytest

from scripts.eval.elo import compute_elo, DEFAULT_INITIAL_ELO, DEFAULT_REGRESS


def _make_df(records):
    """Build a minimal match DataFrame from (season, home, away, hg, ag) tuples."""
    return pd.DataFrame(
        records, columns=["season", "home_team", "away_team", "home_goals", "away_goals"]
    )


class TestComputeEloBasic:
    def test_output_has_required_columns(self):
        df = _make_df([(2022, "A", "B", 2, 1)])
        out = compute_elo(df, K=25, home_adv=80)
        assert "home_elo" in out.columns
        assert "away_elo" in out.columns
        assert "elo_diff" in out.columns

    def test_return_expected_adds_column(self):
        df = _make_df([(2022, "A", "B", 1, 0)])
        out = compute_elo(df, K=25, home_adv=80, return_expected=True)
        assert "elo_p_home" in out.columns

    def test_first_game_uses_initial_elo(self):
        df = _make_df([(2022, "A", "B", 1, 0)])
        out = compute_elo(df, K=25, home_adv=80)
        assert out["home_elo"].iloc[0] == DEFAULT_INITIAL_ELO
        assert out["away_elo"].iloc[0] == DEFAULT_INITIAL_ELO

    def test_elo_diff_equals_home_minus_away(self):
        df = _make_df([
            (2022, "A", "B", 2, 0),
            (2022, "B", "A", 1, 1),
        ])
        out = compute_elo(df, K=25, home_adv=80)
        for i in range(len(out)):
            assert out["elo_diff"].iloc[i] == pytest.approx(
                out["home_elo"].iloc[i] - out["away_elo"].iloc[i]
            )

    def test_row_count_preserved(self):
        df = _make_df([(2022, "A", "B", 1, 0)] * 10)
        out = compute_elo(df, K=25, home_adv=80)
        assert len(out) == 10


class TestEloUpdateDirection:
    def test_home_win_raises_home_elo(self):
        df = _make_df([
            (2022, "A", "B", 3, 0),
            (2022, "A", "C", 0, 0),  # second game so we can read A's updated rating
        ])
        out = compute_elo(df, K=25, home_adv=0)
        # After a 3-0 win, A should have higher rating than initial
        assert out["home_elo"].iloc[1] > DEFAULT_INITIAL_ELO

    def test_home_loss_lowers_home_elo(self):
        df = _make_df([
            (2022, "A", "B", 0, 3),
            (2022, "A", "C", 0, 0),
        ])
        out = compute_elo(df, K=25, home_adv=0)
        assert out["home_elo"].iloc[1] < DEFAULT_INITIAL_ELO

    def test_home_advantage_shifts_expected_probability(self):
        df = _make_df([(2022, "A", "B", 1, 1)])
        out_ha   = compute_elo(df, K=25, home_adv=100, return_expected=True)
        out_nha  = compute_elo(df, K=25, home_adv=0,   return_expected=True)
        # Higher home_adv → higher expected home win probability
        assert out_ha["elo_p_home"].iloc[0] > out_nha["elo_p_home"].iloc[0]


class TestEloSeasonRegression:
    def test_regression_pulls_toward_initial(self):
        df = _make_df([
            (2022, "A", "B", 5, 0),  # A gets very high after this
            (2022, "A", "B", 5, 0),
            (2022, "A", "B", 5, 0),
            (2023, "A", "B", 0, 0),  # New season: A's elo should be pulled down
        ])
        out_50 = compute_elo(df, K=40, home_adv=0, regress=0.50)
        out_00 = compute_elo(df, K=40, home_adv=0, regress=0.00)
        # With 50% regression, A's 2023 rating should be closer to initial than without regression
        a_2023_with    = out_50["home_elo"].iloc[3]
        a_2023_without = out_00["home_elo"].iloc[3]
        assert abs(a_2023_with - DEFAULT_INITIAL_ELO) < abs(a_2023_without - DEFAULT_INITIAL_ELO)

    def test_full_regression_resets_to_initial(self):
        df = _make_df([
            (2022, "A", "B", 5, 0),
            (2023, "A", "B", 0, 0),  # full reset should restore to initial
        ])
        out = compute_elo(df, K=100, home_adv=0, regress=1.0)
        assert out["home_elo"].iloc[1] == pytest.approx(DEFAULT_INITIAL_ELO, abs=1e-6)


class TestEloMarginOfVictory:
    def test_bigger_win_moves_elo_more(self):
        df_big  = _make_df([(2022, "A", "B", 5, 0), (2022, "A", "C", 0, 0)])
        df_small = _make_df([(2022, "A", "B", 1, 0), (2022, "A", "C", 0, 0)])
        out_big   = compute_elo(df_big,  K=25, home_adv=0)
        out_small = compute_elo(df_small, K=25, home_adv=0)
        # After a 5-0 win, A's rating should be higher than after a 1-0 win
        assert out_big["home_elo"].iloc[1] > out_small["home_elo"].iloc[1]


class TestEloExpectedProbability:
    def test_expected_probability_sums_toward_one(self):
        df = _make_df([(2022, "A", "B", 1, 0)])
        out = compute_elo(df, K=25, home_adv=80, return_expected=True)
        p = out["elo_p_home"].iloc[0]
        assert 0.0 < p < 1.0

    def test_equal_teams_with_home_adv_favors_home(self):
        df = _make_df([(2022, "A", "B", 1, 0)])
        out = compute_elo(df, K=25, home_adv=80, return_expected=True)
        assert out["elo_p_home"].iloc[0] > 0.5

    def test_zero_home_adv_equal_teams_is_half(self):
        df = _make_df([(2022, "A", "B", 0, 0)])
        out = compute_elo(df, K=25, home_adv=0, return_expected=True)
        assert out["elo_p_home"].iloc[0] == pytest.approx(0.5, abs=1e-6)


class TestClubPriorRegression:
    """A8: season-boundary regression toward a club-history prior (not flat 1500)."""

    @staticmethod
    def _four_season_df():
        # Team A beats B every match for 3 seasons (A ends high, B low),
        # then a 4th season begins — the boundary behavior is under test.
        rows = []
        for season in (2021, 2022, 2023):
            rows += [(season, "A", "B", 3, 0), (season, "B", "A", 0, 3)]
        rows.append((2024, "A", "B", 1, 1))
        return _make_df(rows)

    def test_beta_zero_matches_legacy_flat_regression(self):
        df = self._four_season_df()
        legacy = compute_elo(df, K=25, home_adv=80)
        new = compute_elo(df, K=25, home_adv=80, club_prior_beta=0.0)
        pd.testing.assert_frame_equal(legacy, new)

    def test_beta_pulls_seed_toward_club_history(self):
        df = self._four_season_df()
        flat = compute_elo(df, K=25, home_adv=80)
        prior = compute_elo(df, K=25, home_adv=80, club_prior_beta=0.5)
        # A's 2024 seed: history says strong → seed above the flat-1500 version
        a_flat = flat[flat["season"] == 2024]["home_elo"].iloc[0]
        a_prior = prior[prior["season"] == 2024]["home_elo"].iloc[0]
        assert a_prior > a_flat
        # B mirrors below
        b_flat = flat[flat["season"] == 2024]["away_elo"].iloc[0]
        b_prior = prior[prior["season"] == 2024]["away_elo"].iloc[0]
        assert b_prior < b_flat

    def test_fewer_than_two_prior_seasons_falls_back_to_flat(self):
        # only one prior season → target stays flat initial even with beta
        rows = [(2023, "A", "B", 3, 0), (2024, "A", "B", 1, 1)]
        df = _make_df(rows)
        flat = compute_elo(df, K=25, home_adv=80)
        prior = compute_elo(df, K=25, home_adv=80, club_prior_beta=0.75)
        pd.testing.assert_frame_equal(flat, prior)

    def test_gap_k_regresses_deviant_teams_harder(self):
        # A is strong for 3 seasons, then loses everything in season 4 (rating
        # collapses far below its history) — with gap_k, the season-5 boundary
        # regresses A harder toward the target than the flat rate would.
        rows = []
        for season in (2021, 2022, 2023):
            rows += [(season, "A", "B", 3, 0), (season, "B", "A", 0, 3)]
        for _ in range(6):
            rows += [(2024, "A", "B", 0, 3), (2024, "B", "A", 3, 0)]
        rows.append((2025, "A", "B", 1, 1))
        df = _make_df(rows)
        base = compute_elo(df, K=25, home_adv=80, club_prior_beta=1.0)
        gapk = compute_elo(df, K=25, home_adv=80, club_prior_beta=1.0,
                           regress_gap_k=0.4)
        # target = club prior (well above A's collapsed rating); harder rate →
        # 2025 seed closer to the prior → HIGHER than the base-rate seed
        a_base = base[base["season"] == 2025]["home_elo"].iloc[0]
        a_gapk = gapk[gapk["season"] == 2025]["home_elo"].iloc[0]
        assert a_gapk > a_base


class TestValueInformedTarget:
    """A10(a): season-boundary target blends toward a squad-value-implied ELO
    (log-value → end-of-season-ELO map fit walk-forward on the closed season)."""

    TEAMS = list("ABCDEFGH")

    @classmethod
    def _two_season_df(cls):
        # 2022: A/B/C/D beat E/F/G/H home and away → clean strong/weak split.
        rows = []
        for w, l in zip("ABCD", "HGFE"):
            rows += [(2022, w, l, 3, 0), (2022, l, w, 0, 3)]
        # 2023 openers: one fixture per team so every seed is observable.
        rows += [(2023, "A", "B", 1, 1), (2023, "C", "D", 1, 1),
                 (2023, "E", "F", 1, 1), (2023, "H", "G", 1, 1)]
        return _make_df(rows)

    @classmethod
    def _values(cls, h_2023=30e6):
        # 2022 values descend with strength (A rich → H poor) so the fitted
        # log-value→ELO slope is positive; 2023 keeps everyone flat except H.
        vals = {}
        for i, t in enumerate(cls.TEAMS):
            vals[(t, 2022)] = (100 - 10 * i) * 1e6
            vals[(t, 2023)] = (100 - 10 * i) * 1e6
        vals[("H", 2023)] = h_2023
        return vals

    def test_beta_zero_is_legacy(self):
        df = self._two_season_df()
        legacy = compute_elo(df, K=25, home_adv=80)
        off = compute_elo(df, K=25, home_adv=80,
                          value_beta=0.0, season_values=self._values())
        pd.testing.assert_frame_equal(legacy, off)

    def test_big_new_value_lifts_seed(self):
        df = self._two_season_df()
        flat = compute_elo(df, K=25, home_adv=80)
        rich = compute_elo(df, K=25, home_adv=80, value_beta=0.5,
                           season_values=self._values(h_2023=120e6))
        # H opens 2023 at home vs G — home_elo of that row is H's seed.
        h_flat = flat[(flat["season"] == 2023) & (flat["home_team"] == "H")]["home_elo"].iloc[0]
        h_rich = rich[(rich["season"] == 2023) & (rich["home_team"] == "H")]["home_elo"].iloc[0]
        assert h_rich > h_flat

    def test_missing_new_value_falls_back_to_flat(self):
        df = self._two_season_df()
        vals = self._values()
        del vals[("E", 2023)]  # E has no incoming-season value
        flat = compute_elo(df, K=25, home_adv=80)
        val = compute_elo(df, K=25, home_adv=80, value_beta=0.5, season_values=vals)
        e_flat = flat[(flat["season"] == 2023) & (flat["home_team"] == "E")]["home_elo"].iloc[0]
        e_val = val[(val["season"] == 2023) & (val["home_team"] == "E")]["home_elo"].iloc[0]
        assert e_val == pytest.approx(e_flat)

    def test_fit_needs_six_pairs(self):
        # Only 4 teams have 2022 values → no fit → identical to flat everywhere.
        df = self._two_season_df()
        vals = {(t, s): 50e6 for t in "ABCD" for s in (2022, 2023)}
        flat = compute_elo(df, K=25, home_adv=80)
        val = compute_elo(df, K=25, home_adv=80, value_beta=0.5, season_values=vals)
        pd.testing.assert_frame_equal(flat, val)
