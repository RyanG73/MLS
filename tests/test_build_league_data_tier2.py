"""Unit tests for tier-2 seeding helpers added to build_league_data."""
from __future__ import annotations
import pytest


# ── _elo_to_dc_params ─────────────────────────────────────────────────────────

def test_elo_to_dc_params_high_elo_gets_strong_seed():
    """Team at 90th ELO percentile gets stronger attack and weaker-defense seed."""
    from scripts.build_league_data import _elo_to_dc_params

    elo_now = {f"Team{i}": 1400.0 + i * 33 for i in range(10)}
    atk = {f"Team{i}": -0.4 + i * 0.08 for i in range(10)}
    dfd = {f"Team{i}":  0.4 - i * 0.08 for i in range(10)}

    high_atk, high_dfd = _elo_to_dc_params(1690.0, atk, dfd, elo_now)
    low_atk,  low_dfd  = _elo_to_dc_params(1430.0, atk, dfd, elo_now)

    assert high_atk > low_atk, "Stronger ELO should map to higher attack param"
    assert high_dfd < low_dfd, "Stronger ELO should map to lower defense param"


def test_elo_to_dc_params_clamps_to_5th_95th():
    """ELO below all existing teams clamps to 5th percentile, not min."""
    from scripts.build_league_data import _elo_to_dc_params

    elo_now = {f"T{i}": 1500.0 + i * 10 for i in range(20)}
    atk = {f"T{i}": float(i) for i in range(20)}
    dfd = {f"T{i}": float(20 - i) for i in range(20)}

    atk_seed, dfd_seed = _elo_to_dc_params(1000.0, atk, dfd, elo_now)
    atk_min = min(atk.values())
    assert atk_seed > atk_min, "Should clamp at 5th pct, not absolute min"


def test_elo_to_dc_params_empty_maps_return_zeros():
    """Empty atk/dfd/elo maps return (0.0, 0.0) without crashing."""
    from scripts.build_league_data import _elo_to_dc_params
    result = _elo_to_dc_params(1500.0, {}, {}, {})
    assert result == (0.0, 0.0)
