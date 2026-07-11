"""Round-4 projection-only leagues: China, Russia (footballdata_intl, odds backbone)
and Saudi / A-League / WSL (ESPN goals-only)."""
from __future__ import annotations


def test_china_russia_registered():
    from data_pipeline.football_data_intl import COUNTRY
    assert COUNTRY["china-super"] == "CHN"
    assert COUNTRY["russia-premier"] == "RUS"


def test_china_russia_outlook():
    from scripts.build_league_data import OUTLOOK
    for lid, conf in (("china-super", "AFC"), ("russia-premier", "UEFA")):
        cfg = OUTLOOK[lid]
        assert cfg["source"] == "footballdata_intl"  # odds backbone retained
        assert cfg["n"] == 16
        assert cfg["confederation"] == conf
