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


def test_elo_to_dc_params_is_continuous_above_floor():
    """Smooth mapping: a small ELO change in the normal range → a small param change
    (no discrete-percentile cliff — the 2026-06-28 calibration fix)."""
    from scripts.build_league_data import _elo_to_dc_params

    elo_now = {f"t{i}": 1400.0 + i * 20 for i in range(16)}   # 1400..1700
    atk = {f"t{i}": -0.4 + i * 0.05 for i in range(16)}
    dfd = {f"t{i}":  0.4 - i * 0.05 for i in range(16)}

    a1, d1 = _elo_to_dc_params(1604.0, atk, dfd, elo_now)
    a2, d2 = _elo_to_dc_params(1596.0, atk, dfd, elo_now)
    assert abs(a1 - a2) < 0.03 and abs(d1 - d2) < 0.03, "8-ELO step must not jump"


def test_elo_to_dc_params_soft_floor_protects_subfloor_team():
    """A team far below the ELO floor seeds at the floor (no cliff below it) and is never
    snapped to the worst-ever team — the smooth+floor mapping replacing the old 5th/95th clamp."""
    from scripts.build_league_data import _elo_to_dc_params

    elo_now = {f"t{i}": 1400.0 + i * 20 for i in range(16)}
    atk = {f"t{i}": -0.4 + i * 0.05 for i in range(16)}
    dfd = {f"t{i}":  0.4 - i * 0.05 for i in range(16)}

    very_low_atk, _ = _elo_to_dc_params(1100.0, atk, dfd, elo_now)
    also_low_atk, _ = _elo_to_dc_params(1250.0, atk, dfd, elo_now)
    assert very_low_atk == also_low_atk, "two sub-floor ELOs clamp to the same floor"
    assert very_low_atk > min(atk.values()), "floored above the weakest-ever team"


def test_elo_to_dc_params_empty_maps_return_zeros():
    """Empty atk/dfd/elo maps return (0.0, 0.0) without crashing."""
    from scripts.build_league_data import _elo_to_dc_params
    result = _elo_to_dc_params(1500.0, {}, {}, {})
    assert result == (0.0, 0.0)


def test_build_exposes_tier1_for_inverse_map():
    """build module exposes _TIER1_FOR_BUILD = inverse of _TIER2_FOR (drives reverse seeding)."""
    from scripts.build_league_data import _TIER1_FOR_BUILD, _TIER2_FOR
    for t1, t2 in _TIER2_FOR.items():
        assert _TIER1_FOR_BUILD[t2] == t1
