import pytest
from data_pipeline import coefficients as co


def test_reference_league_has_zero_offset():
    # The strongest modeled league (EPL) anchors the scale at 0.
    assert co.league_offset("epl") == 0.0


def test_weaker_league_has_negative_offset():
    # A weaker league sits below EPL on the common scale.
    assert co.league_offset("ligue-1") < 0.0


def test_unknown_league_offset_is_zero_with_no_crash():
    # Graceful fallback: an unmapped league contributes no offset.
    assert co.league_offset("nonexistent-league") == 0.0


def test_club_strength_maps_coefficient_to_elo_scale():
    # A top club coefficient maps to a strength near a strong domestic ELO.
    assert co.club_strength("Real Madrid") == 1720.0


def test_unknown_club_strength_returns_baseline():
    # Unknown club -> conservative baseline, never a crash.
    assert co.club_strength("FC Nonexistent") == co.BASELINE_STRENGTH


def test_concacaf_offsets_are_relative_not_uefa_scale():
    assert co.league_offset("mls") == 0.0
    assert co.league_offset("liga-mx") > co.league_offset("mls")
    assert co.league_offset("liga-mx") <= 60  # modest, not a UEFA-sized gap


def test_concacaf_club_strength_below_modeled_top():
    # An unmodeled Central-American club sits well below the MLS/Liga MX modeled range.
    assert co.club_strength("Alajuelense") < 1550
