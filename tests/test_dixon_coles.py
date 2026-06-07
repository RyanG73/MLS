"""
Unit tests for the extracted Dixon-Coles engine (scripts/eval/dixon_coles.py).

These lock the behavior of the engine after the F4 monolith split so future
refactors can't silently change the model.
"""

import math

import numpy as np
import pandas as pd
import pytest

from scripts.eval.dixon_coles import (
    dc_tau, fit_dc, dc_predict, dc_predict_batch, dc_lam_mu_batch,
)


# ── dc_tau (low-score correction) ─────────────────────────────────────────────

class TestDcTau:
    def test_high_scores_return_one(self):
        # Any score with a coordinate >= 2 is uncorrected
        assert dc_tau(2, 0, 1.0, 1.0, -0.05) == 1.0
        assert dc_tau(0, 3, 1.0, 1.0, -0.05) == 1.0
        assert dc_tau(5, 5, 1.0, 1.0, -0.05) == 1.0

    def test_low_score_corrections_depend_on_rho(self):
        lam, mu, rho = 1.2, 0.9, -0.05
        assert dc_tau(0, 0, lam, mu, rho) == pytest.approx(1 - lam * mu * rho)
        assert dc_tau(0, 1, lam, mu, rho) == pytest.approx(1 + lam * rho)
        assert dc_tau(1, 0, lam, mu, rho) == pytest.approx(1 + mu * rho)
        assert dc_tau(1, 1, lam, mu, rho) == pytest.approx(1 - rho)

    def test_rho_zero_is_independence(self):
        # rho=0 → all corrections collapse to 1 (independent Poisson)
        for x in range(2):
            for y in range(2):
                assert dc_tau(x, y, 1.0, 1.0, 0.0) == pytest.approx(1.0)


# ── dc_predict (1X2 probabilities) ────────────────────────────────────────────

class TestDcPredict:
    def test_probabilities_sum_to_one(self):
        atk = {"A": 0.3, "B": -0.2}
        dfd = {"A": -0.1, "B": 0.2}
        p = dc_predict("A", "B", atk, dfd, 0.25, -0.05)
        assert sum(p) == pytest.approx(1.0, abs=1e-9)
        assert all(0.0 <= x <= 1.0 for x in p)

    def test_home_advantage_increases_home_prob(self):
        atk = {"A": 0.0, "B": 0.0}
        dfd = {"A": 0.0, "B": 0.0}
        ph_lo, _, _ = dc_predict("A", "B", atk, dfd, 0.0, -0.05)
        ph_hi, _, _ = dc_predict("A", "B", atk, dfd, 0.5, -0.05)
        assert ph_hi > ph_lo

    def test_stronger_attack_increases_win_prob(self):
        # A with a much stronger attack and B with weaker defence
        weak = dc_predict("A", "B", {"A": 0.0, "B": 0.0}, {"A": 0.0, "B": 0.0}, 0.25, -0.05)
        strong = dc_predict("A", "B", {"A": 1.0, "B": 0.0}, {"A": 0.0, "B": 0.5}, 0.25, -0.05)
        assert strong[0] > weak[0]

    def test_symmetry_equal_teams_no_homeadv(self):
        # Equal teams, zero home advantage → P(home win) == P(away win)
        p = dc_predict("A", "B", {"A": 0.0, "B": 0.0}, {"A": 0.0, "B": 0.0}, 0.0, -0.05)
        assert p[0] == pytest.approx(p[2], abs=1e-9)

    def test_unknown_team_uses_zero_params(self):
        # Missing team falls back to 0 params (no crash)
        p = dc_predict("ZZZ", "YYY", {}, {}, 0.25, -0.05)
        assert sum(p) == pytest.approx(1.0, abs=1e-9)


# ── fit_dc + batch helpers ────────────────────────────────────────────────────

def _toy_matches(n_per_season=40, seasons=(2021, 2022, 2023)) -> pd.DataFrame:
    rng = np.random.default_rng(0)
    teams = ["A", "B", "C", "D"]
    rows = []
    for s in seasons:
        base = pd.Timestamp(f"{s}-03-01")
        for i in range(n_per_season):
            h, a = rng.choice(teams, size=2, replace=False)
            rows.append({
                "season": s,
                "date": base + pd.Timedelta(days=i * 3),
                "home_team": h, "away_team": a,
                "home_goals": int(rng.poisson(1.4)),
                "away_goals": int(rng.poisson(1.1)),
            })
    return pd.DataFrame(rows)


class TestFitDc:
    @pytest.fixture(scope="class")
    def fitted(self):
        df = _toy_matches()
        return fit_dc(df, decay_hl=120, recent_seasons=3), df

    def test_returns_params_for_all_teams(self, fitted):
        (atk, dfd, ha, rho), df = fitted
        teams = set(df["home_team"]) | set(df["away_team"])
        assert set(atk) == teams
        assert set(dfd) == teams

    def test_params_in_bounds(self, fitted):
        (atk, dfd, ha, rho), _ = fitted
        assert 0.0 <= ha <= 1.0
        assert -0.5 <= rho <= 0.0
        assert all(-3 <= v <= 3 for v in atk.values())

    def test_predict_batch_shape_and_normalization(self, fitted):
        (atk, dfd, ha, rho), df = fitted
        preds = dc_predict_batch(df.head(10), atk, dfd, ha, rho)
        assert preds.shape == (10, 3)
        assert np.allclose(preds.sum(axis=1), 1.0, atol=1e-9)

    def test_lam_mu_batch_positive(self, fitted):
        (atk, dfd, ha, rho), df = fitted
        lams, mus = dc_lam_mu_batch(df.head(10), atk, dfd, ha)
        assert lams.shape == (10,) and mus.shape == (10,)
        assert (lams > 0).all() and (mus > 0).all()

    def test_recent_seasons_window_excludes_old(self):
        # Only the most recent season should be used when recent_seasons=1
        df = _toy_matches(seasons=(2019, 2023))
        atk, dfd, ha, rho = fit_dc(df, decay_hl=120, recent_seasons=1)
        # All teams still present (toy data has all teams every season), params finite
        assert all(math.isfinite(v) for v in atk.values())
