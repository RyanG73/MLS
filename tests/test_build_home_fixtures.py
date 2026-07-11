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
