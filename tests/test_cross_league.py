import pytest
from scripts.eval import cross_league as cl


def test_modeled_team_strength_is_elo_plus_offset():
    assert cl.co.league_offset("epl") == 0.0  # EPL anchors the scale at 0
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


def test_modeled_league_but_missing_team_falls_back_observably(caplog):
    # Mapped to a modeled league but absent from its ELO dict -> observable fallback
    # to coefficient strength (a WARNING), never a silent baseline mis-rating.
    import logging
    with caplog.at_level(logging.WARNING):
        s = cl.team_strength("Porto", "epl", {"Arsenal": 1650.0})
    assert s == cl.co.club_strength("Porto")  # 1780.0, not the 1450 baseline
    assert "falling back" in caplog.text


class TestMatchModel:
    def test_equal_strength_neutral_is_symmetric(self):
        ph, pd_, pa = cl.match_probs(1700, 1700, neutral=True)
        assert abs(ph - pa) < 1e-9
        assert ph + pd_ + pa == pytest.approx(1.0)

    def test_home_advantage_favors_home(self):
        ph_n, _, _ = cl.match_probs(1700, 1700, neutral=True)
        ph_h, _, _ = cl.match_probs(1700, 1700, neutral=False)
        assert ph_h > ph_n

    def test_stronger_team_more_likely_to_win(self):
        ph_weak, _, _ = cl.match_probs(1600, 1700, neutral=True)
        ph_strong, _, _ = cl.match_probs(1800, 1700, neutral=True)
        assert ph_strong > ph_weak

    def test_lambdas_increase_with_strength_gap(self):
        lh1, la1 = cl.match_lambdas(1700, 1700, neutral=True)
        lh2, la2 = cl.match_lambdas(1900, 1700, neutral=True)
        assert lh2 > lh1 and la2 < la1
