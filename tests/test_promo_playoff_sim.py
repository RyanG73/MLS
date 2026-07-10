"""Promotion-playoff bracket simulation (2026-07-09 feedback round 3).

The `promoted` composite bucket = auto-promotion spots + the simulated playoff
winner (× barrage rate where the last hurdle is cross-league). These tests pin
the bracket helper's symmetry and seed-hosting bias, and the composite math.
"""
import numpy as np

from scripts.build_league_data import _promo_playoff_winner, _PROMO


def _uniform_pm(n):
    """Pairing matrix where every match is a 1/3·1/3·1/3 coin flip."""
    pm = np.full((n, n, 3), 1 / 3.0)
    return pm


def _win_freq(seeds, pm, n=20000, seed=42):
    rng = np.random.default_rng(seed)
    wins = {s: 0 for s in seeds}
    for _ in range(n):
        wins[_promo_playoff_winner(list(seeds), pm, rng)] += 1
    return {s: w / n for s, w in wins.items()}


def test_uniform_4team_bracket_is_symmetric():
    # With every pairing 50/50 (after the pH + 0.5·pD draw split), each of the
    # 4 playoff teams must win ~25% of brackets.
    freq = _win_freq([0, 1, 2, 3], _uniform_pm(4))
    for s, f in freq.items():
        assert abs(f - 0.25) < 0.015, f"seed {s}: {f}"


def test_uniform_6team_byes_favor_top_seeds():
    # Serie B shape: seeds 0-1 skip the prelim round, so at uniform strength
    # they win the bracket 25% each; prelim teams (2-5) split the rest (12.5%).
    freq = _win_freq([0, 1, 2, 3, 4, 5], _uniform_pm(6))
    assert abs(freq[0] - 0.25) < 0.015
    assert abs(freq[1] - 0.25) < 0.015
    for s in (2, 3, 4, 5):
        assert abs(freq[s] - 0.125) < 0.015, f"seed {s}: {freq[s]}"


def test_3team_ladder_favors_rested_top_seed():
    # Ligue 2 shape: s1 v s2, winner visits s0. At uniform strength s0 plays
    # one match (wins 50%), s1/s2 must win two (25% each).
    freq = _win_freq([0, 1, 2], _uniform_pm(3))
    assert abs(freq[0] - 0.50) < 0.015
    assert abs(freq[1] - 0.25) < 0.015
    assert abs(freq[2] - 0.25) < 0.015


def test_single_team_band_returns_that_team():
    rng = np.random.default_rng(0)
    assert _promo_playoff_winner([7], _uniform_pm(8), rng) == 7


def test_home_advantage_flows_to_higher_seed():
    # pmatrix rows are host-POV: host wins 60%, draws 20%, loses 20%
    # → P(host advances) = 0.7. The higher seed always hosts, so seed 0 of a
    # 3-team ladder should win ~70% (one home tie).
    n = 3
    pm = np.zeros((n, n, 3))
    pm[:, :, 0], pm[:, :, 1], pm[:, :, 2] = 0.6, 0.2, 0.2
    freq = _win_freq([0, 1, 2], pm)
    assert abs(freq[0] - 0.70) < 0.015


def test_promo_bucket_shapes():
    # _PROMO emits Auto / Playoff / Promoted / Releg; the composite carries the
    # bracket definition and the barrage rate only when given.
    plain = {b["key"]: b for b in _PROMO(2, [3, 6], 3)}
    assert plain["promoted"]["promo_top"] == 2
    assert plain["promoted"]["playoff_band"] == [3, 6]
    assert "barrage_win_rate" not in plain["promoted"]
    barrage = {b["key"]: b for b in _PROMO(2, [3, 3], 3, barrage=0.33)}
    assert barrage["promoted"]["barrage_win_rate"] == 0.33
    # cards stay simple: Promoted + Relegation only
    assert [b["key"] for b in _PROMO(2, [3, 6], 3) if b.get("card", True)] == [
        "promoted", "releg"]
