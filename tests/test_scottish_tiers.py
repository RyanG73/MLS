"""Scottish Championship / League One / League Two registration + pyramid chain."""
from __future__ import annotations


def test_scottish_tiers_registered():
    from data_pipeline import football_data as fd
    assert fd.DIV["scottish-champ"] == "SC1"
    assert fd.DIV["scottish-league-one"] == "SC2"
    assert fd.DIV["scottish-league-two"] == "SC3"
    for lid in ("scottish-champ", "scottish-league-one", "scottish-league-two"):
        assert lid in fd.GOALS_ONLY
        assert lid not in fd.BIG5


def test_scottish_pyramid_chain():
    from scripts.build_league_data import _TIER2_FOR, _TIER1_FOR_BUILD
    assert _TIER2_FOR["scottish-prem"] == "scottish-champ"
    assert _TIER2_FOR["scottish-champ"] == "scottish-league-one"
    assert _TIER2_FOR["scottish-league-one"] == "scottish-league-two"
    # inverse chain (relegation direction) is derived for free
    assert _TIER1_FOR_BUILD["scottish-league-two"] == "scottish-league-one"


def test_scottish_outlook():
    from scripts.build_league_data import OUTLOOK
    for lid in ("scottish-champ", "scottish-league-one", "scottish-league-two"):
        cfg = OUTLOOK[lid]
        assert cfg["source"] == "footballdata"
        assert cfg["n"] == 10
