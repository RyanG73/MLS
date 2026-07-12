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


def test_search_index_lists_all_teams():
    files = [("epl", {"league": {"name": "EPL"}, "games": [],
                      "standings": [{"team": "Arsenal"}, {"team": "Hull"}]}),
             ("mls", {"league": {"name": "MLS"}, "games": [],
                      "standings": [{"team": "LAFC"}]})]
    idx = build_home.build_search_index(files)
    assert {"t": "Arsenal", "l": "epl"} in idx
    assert {"t": "LAFC", "l": "mls"} in idx
    assert len(idx) == 3
