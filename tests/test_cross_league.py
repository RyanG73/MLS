import pytest
from scripts.eval import cross_league as cl


def test_modeled_team_strength_is_elo_plus_offset():
    elos = {"Arsenal": 1650.0}
    # EPL offset is 0, so strength == domestic ELO.
    s = cl.team_strength("Arsenal", "epl", elos)
    assert s == 1650.0


def test_modeled_team_in_weaker_league_shifts_down():
    elos = {"Lyon": 1650.0}
    s = cl.team_strength("Lyon", "ligue-1", elos)
    assert s < 1650.0  # ligue-1 offset is negative


def test_unmodeled_team_uses_club_strength_fallback():
    # Team not in the elos dict and league None -> coefficient fallback.
    s = cl.team_strength("Porto", None, {})
    assert s == 1780.0  # from _CLUB_STRENGTH


def test_unknown_unmodeled_team_uses_baseline():
    s = cl.team_strength("FC Nowhere", None, {})
    assert s == cl.co.BASELINE_STRENGTH
