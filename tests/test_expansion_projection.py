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


def test_espn_projection_leagues():
    from scripts.build_league_data import OUTLOOK
    from data_pipeline.espn_fixtures import SLUGS
    expect = {"saudi-pro": ("ksa.1", 18, "AFC"),
              "australia-aleague": ("aus.1", 12, "AFC"),
              "wsl": ("eng.w.1", 12, "UEFA")}
    for lid, (slug, n, conf) in expect.items():
        cfg = OUTLOOK[lid]
        assert cfg["source"] == "espn"
        assert cfg["n"] == n
        assert cfg["confederation"] == conf
        assert SLUGS[lid] == slug


def test_aleague_has_no_relegation():
    from scripts.build_league_data import OUTLOOK
    assert OUTLOOK["australia-aleague"]["red_line"] is None
