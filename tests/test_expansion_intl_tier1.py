"""Round-4 footballdata_intl Tier-1 top flights: Austria, Switzerland, Romania, Ireland."""
from __future__ import annotations


def test_intl_countries_registered():
    from data_pipeline.football_data_intl import COUNTRY
    assert COUNTRY["austria-bundesliga"] == "AUT"
    assert COUNTRY["swiss-super-league"] == "SWZ"  # football-data code is SWZ, not SUI
    assert COUNTRY["romania-liga1"] == "ROU"
    assert COUNTRY["ireland-premier"] == "IRL"


def test_intl_tier1_outlook():
    from scripts.build_league_data import OUTLOOK
    expect = {"austria-bundesliga": 12, "swiss-super-league": 12,
              "romania-liga1": 16, "ireland-premier": 10}
    for lid, n in expect.items():
        cfg = OUTLOOK[lid]
        assert cfg["source"] == "footballdata_intl"
        assert cfg["n"] == n
        assert cfg["confederation"] == "UEFA"


def test_intl_tier1_slugs_and_calendar():
    from data_pipeline.espn_fixtures import SLUGS, CALENDAR_YEAR_LEAGUES
    assert SLUGS["austria-bundesliga"] == "aut.1"
    assert SLUGS["swiss-super-league"] == "sui.1"
    assert SLUGS["romania-liga1"] == "rou.1"
    assert SLUGS["ireland-premier"] == "irl.1"
    # Ireland runs Feb–Nov (calendar year); the other three are Aug–May straddles.
    assert "ireland-premier" in CALENDAR_YEAR_LEAGUES
    assert "austria-bundesliga" not in CALENDAR_YEAR_LEAGUES
