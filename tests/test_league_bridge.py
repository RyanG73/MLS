"""Tests for scripts/eval/league_bridge.py and coefficients.py JSON wire-in.

Tests are structured into four groups:
1. elo_asof — historical ELO-as-of-date lookup: fallback, before-first, correct index.
2. Anchors — anchored leagues must always be exactly 0.
3. Synthetic fit — a small contrived dataset with known offset direction must
   be recovered by the optimizer.
4. JSON wire-in — coefficients.league_offset() prefers the fitted JSON when
   present (monkeypatched path), and falls back to priors when absent.
"""
from __future__ import annotations

import json
import math
import tempfile
from pathlib import Path
from unittest import mock

import pandas as pd
import pytest


# ── 1. elo_asof — as-of-date ELO lookup ──────────────────────────────────────

class TestEloAsof:
    """Unit tests for elo_asof() — historical ELO point-in-time lookup.

    We monkeypatch _build_elo_history to inject a controlled time series so
    tests run without touching the real domestic data frames.
    """

    def _patch_history(self, monkeypatch, league_id: str, team: str, entries: list[tuple]):
        """Inject a synthetic history: entries = [(date_str, elo), ...]."""
        from scripts.eval import league_bridge as lb
        dates = [pd.Timestamp(d) for d, _ in entries]
        elos  = [float(e) for _, e in entries]
        fake_history = {team: (dates, elos)}
        monkeypatch.setitem(lb._ELO_HISTORY_CACHE, league_id, fake_history)

    def test_fallback_to_init_when_team_unknown(self, monkeypatch):
        """Team with no history at all returns _INIT (1500.0)."""
        from scripts.eval import league_bridge as lb
        # Inject an empty history for the league (team absent).
        monkeypatch.setitem(lb._ELO_HISTORY_CACHE, "test-lg", {})
        result = lb.elo_asof("test-lg", "Ghost FC", pd.Timestamp("2023-10-01"))
        assert result == lb._INIT, f"Expected {lb._INIT}, got {result}"

    def test_fallback_before_first_match(self, monkeypatch):
        """A date before the team's first domestic match returns _INIT."""
        from scripts.eval import league_bridge as lb
        self._patch_history(monkeypatch, "test-lg", "Alpha FC", [
            ("2023-03-01", 1520.0),
            ("2023-06-15", 1535.0),
        ])
        # Query date before 2023-03-01 — no prior entry.
        result = lb.elo_asof("test-lg", "Alpha FC", pd.Timestamp("2023-01-01"))
        assert result == lb._INIT, f"Expected {lb._INIT}, got {result}"

    def test_returns_last_entry_before_date(self, monkeypatch):
        """Returns the most recent ELO strictly before the query date."""
        from scripts.eval import league_bridge as lb
        self._patch_history(monkeypatch, "test-lg", "Beta FC", [
            ("2023-03-01", 1510.0),
            ("2023-06-15", 1530.0),
            ("2023-09-20", 1550.0),
        ])
        # Query 2023-07-01 → last entry before it is 2023-06-15 → 1530.0
        result = lb.elo_asof("test-lg", "Beta FC", pd.Timestamp("2023-07-01"))
        assert result == pytest.approx(1530.0), f"Expected 1530.0, got {result}"

    def test_exact_date_not_included(self, monkeypatch):
        """A query date equal to a match date returns the PREVIOUS entry (strictly before)."""
        from scripts.eval import league_bridge as lb
        self._patch_history(monkeypatch, "test-lg", "Gamma FC", [
            ("2023-03-01", 1510.0),
            ("2023-06-15", 1530.0),
        ])
        # Query exactly 2023-06-15 — strictly before means we get the 2023-03-01 entry.
        result = lb.elo_asof("test-lg", "Gamma FC", pd.Timestamp("2023-06-15"))
        assert result == pytest.approx(1510.0), f"Expected 1510.0, got {result}"

    def test_returns_latest_when_date_after_all(self, monkeypatch):
        """A query date after all matches returns the most recent ELO."""
        from scripts.eval import league_bridge as lb
        self._patch_history(monkeypatch, "test-lg", "Delta FC", [
            ("2023-03-01", 1510.0),
            ("2023-06-15", 1530.0),
            ("2023-09-20", 1550.0),
        ])
        # Query 2025-01-01 — after all entries, returns last: 1550.0
        result = lb.elo_asof("test-lg", "Delta FC", pd.Timestamp("2025-01-01"))
        assert result == pytest.approx(1550.0), f"Expected 1550.0, got {result}"

    def test_single_entry_history_before_returns_init(self, monkeypatch):
        """Single-entry history: query before the entry returns _INIT."""
        from scripts.eval import league_bridge as lb
        self._patch_history(monkeypatch, "test-lg", "Epsilon FC", [
            ("2023-06-01", 1600.0),
        ])
        result = lb.elo_asof("test-lg", "Epsilon FC", pd.Timestamp("2023-05-01"))
        assert result == lb._INIT

    def test_single_entry_history_after_returns_elo(self, monkeypatch):
        """Single-entry history: query after the entry returns that ELO."""
        from scripts.eval import league_bridge as lb
        self._patch_history(monkeypatch, "test-lg", "Epsilon FC", [
            ("2023-06-01", 1600.0),
        ])
        result = lb.elo_asof("test-lg", "Epsilon FC", pd.Timestamp("2023-07-01"))
        assert result == pytest.approx(1600.0)


# ── 2. Anchor offsets are exactly 0 ──────────────────────────────────────────

class TestAnchors:  # group 2
    def test_epl_anchor_zero(self):
        """UEFA anchor (EPL) must always be 0 in the fitted output."""
        from scripts.eval.league_bridge import _fit_group, _collect_matches, _UEFA_LEAGUES, _UEFA_ANCHOR
        # Use a tiny lambda so the prior doesn't overwhelm, but keep it non-zero
        # to avoid divergence.
        matches = _collect_matches("UEFA")
        if not matches:
            pytest.skip("No continental data cached")
        fitted, _, _, _ = _fit_group(matches, _UEFA_LEAGUES, _UEFA_ANCHOR, lam=0.0001)
        assert fitted[_UEFA_ANCHOR] == 0.0, (
            f"EPL anchor must be 0.0, got {fitted[_UEFA_ANCHOR]}"
        )

    def test_mls_anchor_zero(self):
        """Concacaf anchor (MLS) must always be 0 in the fitted output."""
        from scripts.eval.league_bridge import _fit_group, _collect_matches, _CONCACAF_LEAGUES, _CONCACAF_ANCHOR
        matches = _collect_matches("Concacaf")
        if not matches:
            pytest.skip("No continental data cached")
        fitted, _, _, _ = _fit_group(matches, _CONCACAF_LEAGUES, _CONCACAF_ANCHOR, lam=0.0001)
        assert fitted[_CONCACAF_ANCHOR] == 0.0, (
            f"MLS anchor must be 0.0, got {fitted[_CONCACAF_ANCHOR]}"
        )


# ── 3. Synthetic fit — recovers a known offset direction ──────────────────────

class TestSyntheticFit:
    """Construct a small dataset where league B teams consistently beat league A
    teams despite equal domestic ELOs.  The optimizer should raise B's offset
    above A's (or lower A's, since A is the anchor at 0).

    Setup:
    - anchor: "lg-a"  (fixed at 0)
    - free:   "lg-b"  (should be fitted > 0 because B beats A)
    - 40 synthetic matches: B home vs A away, B wins every time.
      → B's offset should be pushed positive.
    """
    from scripts.eval.league_bridge import _Match, _brier_score, _fit_group

    @staticmethod
    def _synthetic_matches(n: int = 40, home_wins: bool = True) -> list:
        """n matches where lg-b (home) beats lg-a (away)."""
        from scripts.eval.league_bridge import _Match
        outcome = 0 if home_wins else 2  # 0=home win
        return [
            _Match(
                home_league="lg-b",
                away_league="lg-a",
                home_elo=1500.0,
                away_elo=1500.0,
                neutral=False,
                outcome=outcome,
            )
            for _ in range(n)
        ]

    def test_optimizer_raises_offset_when_b_dominates(self):
        """With B consistently winning home vs A, fitted offset for B > prior."""
        from scripts.eval.league_bridge import _Match, _fit_group

        matches = self._synthetic_matches(n=40, home_wins=True)
        # The prior is 0 for both (we pass {lid: 0.0} as priors); use patch
        # to avoid calling the real coefficients.league_offset.
        import data_pipeline.coefficients as co
        with mock.patch.object(co, "league_offset", side_effect=lambda lid: 0.0):
            fitted, priors, brier_prior, brier_fitted = _fit_group(
                matches,
                all_leagues=["lg-a", "lg-b"],
                anchor="lg-a",
                lam=0.0001,
                seed=0,
            )
        # B's fitted offset should be strictly greater than A's (0), because
        # B teams win at home far more than equal-ELO teams should.
        assert fitted["lg-b"] > fitted["lg-a"], (
            f"Expected lg-b > lg-a; got lg-b={fitted['lg-b']:.2f}, lg-a={fitted['lg-a']:.2f}"
        )

    def test_optimizer_lowers_offset_when_b_loses(self):
        """With A consistently winning (B home losses), fitted offset for B < prior."""
        from scripts.eval.league_bridge import _Match, _fit_group

        matches = self._synthetic_matches(n=40, home_wins=False)  # away wins every time
        import data_pipeline.coefficients as co
        with mock.patch.object(co, "league_offset", side_effect=lambda lid: 0.0):
            fitted, priors, brier_prior, brier_fitted = _fit_group(
                matches,
                all_leagues=["lg-a", "lg-b"],
                anchor="lg-a",
                lam=0.0001,
                seed=0,
            )
        # A wins as away team → A is the stronger league → B offset should be < 0
        assert fitted["lg-b"] < fitted["lg-a"], (
            f"Expected lg-b < lg-a; got lg-b={fitted['lg-b']:.2f}, lg-a={fitted['lg-a']:.2f}"
        )

    def test_brier_decreases_on_held_out(self):
        """Fitted offsets should reduce (or match) held-out Brier vs priors on clear signal."""
        from scripts.eval.league_bridge import _Match, _fit_group

        matches = self._synthetic_matches(n=80, home_wins=True)  # more data for stability
        import data_pipeline.coefficients as co
        with mock.patch.object(co, "league_offset", side_effect=lambda lid: 0.0):
            fitted, priors, brier_prior, brier_fitted = _fit_group(
                matches,
                all_leagues=["lg-a", "lg-b"],
                anchor="lg-a",
                lam=0.0001,
                seed=0,
            )
        # With strong artificial signal (80 consecutive B wins), Brier must decrease
        assert brier_fitted <= brier_prior, (
            f"Expected fitted Brier <= prior Brier; got {brier_fitted:.4f} vs {brier_prior:.4f}"
        )


# ── 4. coefficients.league_offset JSON wire-in ───────────────────────────────

class TestJsonWireIn:
    """Test that coefficients.league_offset() reads from the JSON when present."""

    def test_json_value_takes_precedence_over_prior(self, tmp_path, monkeypatch):
        """When the JSON exists with a known value, league_offset() returns that."""
        import data_pipeline.coefficients as co

        # Write a temp JSON with a sentinel value for 'bundesliga'
        sentinel = -999.0
        payload = {"bundesliga": sentinel, "epl": 0.0}
        json_file = tmp_path / "league_offsets.json"
        json_file.write_text(json.dumps(payload))

        # Monkeypatch the path and reset cached state
        monkeypatch.setattr(co, "_FITTED_JSON", json_file)
        monkeypatch.setattr(co, "_FITTED_OFFSETS", None)
        monkeypatch.setattr(co, "_FITTED_OFFSETS_LOADED", False)

        result = co.league_offset("bundesliga")
        assert result == sentinel, (
            f"Expected {sentinel} from JSON, got {result}"
        )

    def test_prior_used_when_league_missing_from_json(self, tmp_path, monkeypatch):
        """When the JSON doesn't contain a league, the prior fallback is used."""
        import data_pipeline.coefficients as co

        # JSON that covers only 'epl', not 'ligue-1'
        json_file = tmp_path / "league_offsets.json"
        json_file.write_text(json.dumps({"epl": 0.0}))

        monkeypatch.setattr(co, "_FITTED_JSON", json_file)
        monkeypatch.setattr(co, "_FITTED_OFFSETS", None)
        monkeypatch.setattr(co, "_FITTED_OFFSETS_LOADED", False)

        # The prior for ligue-1 = _K_COEFF * (67 - 94) = 3.0 * -27 = -81.0
        result = co.league_offset("ligue-1")
        expected_prior = co._K_COEFF * (co._LEAGUE_COEFF["ligue-1"] - co._LEAGUE_COEFF[co._REF_LEAGUE])
        assert result == pytest.approx(expected_prior), (
            f"Expected prior {expected_prior}, got {result}"
        )

    def test_prior_used_when_json_absent(self, tmp_path, monkeypatch):
        """When the JSON file doesn't exist, league_offset() returns the prior."""
        import data_pipeline.coefficients as co

        missing = tmp_path / "nonexistent_offsets.json"
        monkeypatch.setattr(co, "_FITTED_JSON", missing)
        monkeypatch.setattr(co, "_FITTED_OFFSETS", None)
        monkeypatch.setattr(co, "_FITTED_OFFSETS_LOADED", False)

        result = co.league_offset("bundesliga")
        expected_prior = co._K_COEFF * (co._LEAGUE_COEFF["bundesliga"] - co._LEAGUE_COEFF[co._REF_LEAGUE])
        assert result == pytest.approx(expected_prior), (
            f"Expected prior {expected_prior}, got {result}"
        )

    def test_epl_anchor_zero_from_json(self, tmp_path, monkeypatch):
        """EPL should be 0 whether from the JSON or the prior."""
        import data_pipeline.coefficients as co

        json_file = tmp_path / "league_offsets.json"
        json_file.write_text(json.dumps({"epl": 0.0, "bundesliga": -60.5}))

        monkeypatch.setattr(co, "_FITTED_JSON", json_file)
        monkeypatch.setattr(co, "_FITTED_OFFSETS", None)
        monkeypatch.setattr(co, "_FITTED_OFFSETS_LOADED", False)

        assert co.league_offset("epl") == 0.0

    def test_mls_anchor_zero_from_json(self, tmp_path, monkeypatch):
        """MLS should be 0 whether from the JSON or the prior."""
        import data_pipeline.coefficients as co

        json_file = tmp_path / "league_offsets.json"
        json_file.write_text(json.dumps({"mls": 0.0, "liga-mx": 30.0}))

        monkeypatch.setattr(co, "_FITTED_JSON", json_file)
        monkeypatch.setattr(co, "_FITTED_OFFSETS", None)
        monkeypatch.setattr(co, "_FITTED_OFFSETS_LOADED", False)

        assert co.league_offset("mls") == 0.0
