"""Tests for the Segunda + Ligue 2 second-tier leagues and their cross-tier wiring."""
from __future__ import annotations


def test_segunda_and_ligue2_registered():
    from data_pipeline import football_data as fd
    assert fd.DIV["segunda"] == "SP2"
    assert fd.DIV["ligue-2"] == "F2"
    assert "segunda" in fd.GOALS_ONLY
    assert "ligue-2" in fd.GOALS_ONLY
    # they are model sources, not big-5 market sources
    assert "segunda" not in fd.BIG5 and "ligue-2" not in fd.BIG5


def test_segunda_ligue2_in_outlook():
    from scripts.build_league_data import OUTLOOK
    assert OUTLOOK["segunda"]["source"] == "footballdata"
    assert OUTLOOK["segunda"]["n"] == 22
    assert OUTLOOK["ligue-2"]["source"] == "footballdata"
    assert OUTLOOK["ligue-2"]["n"] == 18


def test_forward_pairs_cover_all_big5():
    from scripts.eval.tier_bridge import _TIER2_PAIRS
    from scripts.build_league_data import _TIER2_FOR
    from data_pipeline import coefficients as co
    pairs = set(_TIER2_PAIRS)
    assert ("segunda", "la-liga") in pairs and ("ligue-2", "ligue-1") in pairs
    assert _TIER2_FOR["la-liga"] == "segunda" and _TIER2_FOR["ligue-1"] == "ligue-2"
    # offset readable (falls back to static prior until fitted)
    assert co.tier2_offset("segunda") < 0 and co.tier2_offset("ligue-2") < 0
