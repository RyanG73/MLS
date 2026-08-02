"""build_fixtures: upcoming games only, horizon-capped, prominence-first, capped count."""
import importlib.util
from datetime import date, timedelta
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "build_home", Path(__file__).resolve().parents[1] / "scripts" / "build_home.py")
build_home = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(build_home)


def _mk(lid, games):
    return (lid, {"league": {"name": lid.upper()}, "games": games})


def _g(days_out, home="H", away="A", result=None):
    d = (date.today() + timedelta(days=days_out)).isoformat()
    return {"date": d, "home": home, "away": away, "result": result,
            "pH": 0.5, "pD": 0.3, "pA": 0.2, "ko": d + "T19:00Z",
            "hlogo": None, "alogo": None}


def test_filters_played_and_horizon():
    files = [_mk("epl", [_g(1), _g(2, result="H"), _g(30)])]
    fx = build_home.build_fixtures(files)
    assert len(fx) == 1
    assert fx[0]["league"] == "epl"
    assert set(fx[0]) >= {"league", "name", "date", "home", "away", "pH", "pD", "pA"}


def test_prominent_league_first_and_cap():
    files = [_mk("finland-veikkausliiga", [_g(1) for _ in range(10)]),
             _mk("epl", [_g(2) for _ in range(10)])]
    fx = build_home.build_fixtures(files, limit=12)
    assert len(fx) == 12
    assert fx[0]["league"] == "epl"          # prominence beats date


def test_fixture_carries_colors_elo_and_projected_score():
    g = _g(1)
    g.update({"hcolor": "#ff0000", "acolor": "#0000ff", "lam": 1.8, "mu": 0.9})
    files = [("epl", {"league": {"name": "EPL"}, "games": [g],
                      "standings": [{"team": "H", "elo": 1700}, {"team": "A", "elo": 1600}]})]
    fx = build_home.build_fixtures(files)
    assert fx[0]["hcolor"] == "#ff0000" and fx[0]["acolor"] == "#0000ff"
    assert fx[0]["lam"] == 1.8 and fx[0]["mu"] == 0.9
    assert fx[0]["helo"] == 1700 and fx[0]["aelo"] == 1600


def test_mls_leader_is_most_likely_cup_winner():
    d = {"league": {"name": "MLS"},
         "outlook": {"cards": [{"key": "playoff", "label": "Playoff odds"},
                               {"key": "cup", "label": "MLS Cup"}]},
         "standings": [
             {"team": "Shield Winner", "proj_rank": 1, "playoff": 100.0, "cup": 18.0},
             {"team": "Cup Favorite",  "proj_rank": 2, "playoff": 99.0,  "cup": 24.0}]}
    leaders = build_home.build_leaders([("mls", d)])
    assert leaders[0]["team"] == "Cup Favorite"
    assert leaders[0]["metric"] == "cup"
    assert leaders[0]["metric_label"] == "MLS Cup"


def test_fixture_does_not_expose_proprietary_team_inputs():
    files = [("mls", {"league": {"name": "MLS"}, "games": [_g(1, home="LAFC", away="LA Galaxy")],
                      "team_inputs": {
                          "LAFC": {"elo": 1600, "xg_for": 1.8, "xg_against": 1.1,
                                   "form": 2.1, "gk_z": 0.5, "avail": 1.0},
                          "LA Galaxy": {"elo": 1500, "xg_for": 1.4, "xg_against": 1.3,
                                        "form": 1.2, "gk_z": -0.2, "avail": 0.9}}})]
    fx = build_home.build_fixtures(files)
    assert "hinp" not in fx[0]
    assert "ainp" not in fx[0]


def test_search_index_lists_all_teams():
    files = [("epl", {"league": {"name": "EPL"}, "games": [],
                      "standings": [{"team": "Arsenal"}, {"team": "Hull"}]}),
             ("mls", {"league": {"name": "MLS"}, "games": [],
                      "standings": [{"team": "LAFC"}]})]
    idx = build_home.build_search_index(files)
    assert {"t": "Arsenal", "l": "epl"} in idx
    assert {"t": "LAFC", "l": "mls"} in idx
    assert len(idx) == 3


def test_featured_tables_carry_belgium_and_a_dropdown_slot():
    """The Title Probabilities board gained Belgium as a fixed row and the
    Netherlands as the swappable slot at its foot (2026-07-31 feedback)."""
    assert "belgian-pro" in build_home._FEATURED
    assert build_home._SLOT_DEFAULT == "eredivisie"
    assert build_home._SLOT_DEFAULT not in build_home._FEATURED


def test_tables_attach_own_results_and_fixtures():
    played = _g(-3, home="Ajax", away="PSV", result="H")
    played.update({"hg": 2, "ag": 1})
    d = {"league": {"name": "Eredivisie"},
         "outlook": {"cards": [{"key": "title", "label": "Title"}]},
         "standings": [{"team": "Ajax", "pts": 3, "gd": 1, "title": 40.0,
                        "logo": "ajax.png"},
                       {"team": "PSV", "pts": 0, "gd": -1, "title": 30.0,
                        "logo": "psv.png"}],
         "games": [played, _g(2, home="PSV", away="Ajax")]}
    tables = build_home.build_tables([("eredivisie", d)])
    t = tables[0]
    assert t["slot"] is True
    assert [r["home"] for r in t["results"]] == ["Ajax"]
    assert t["results"][0]["hg"] == 2
    # game rows carry no crest of their own — the standings supply it
    assert t["results"][0]["hlogo"] == "ajax.png"
    assert [f["away"] for f in t["fixtures"]] == ["Ajax"]
    assert t["fixtures"][0]["pH"] == 0.5
