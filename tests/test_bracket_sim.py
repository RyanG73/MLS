import numpy as np
import pytest
from scripts.eval import bracket_sim as bs


def _field(n):
    # n teams with descending strength, no domestic ELO needed (pre-resolved).
    return [{"team": f"T{i}", "strength": 1900 - i * 10} for i in range(n)]


def test_ucl_format_spec_exists():
    fmt = bs.FORMATS["ucl"]
    assert fmt["phase"]["type"] == "league"
    assert fmt["phase"]["teams"] == 36
    assert fmt["phase"]["auto_advance"] == 8


def test_league_phase_returns_row_per_team():
    field = _field(36)
    schedule = bs.make_league_schedule(field, matches_each=8, seed=1)
    standings = bs.simulate_league_phase(field, schedule, bs.FORMATS["ucl"], N=200, seed=1)
    assert len(standings) == 36
    for row in standings:
        assert 0.0 <= row["auto_advance"] <= 1.0
        assert 0.0 <= row["eliminated"] <= 1.0


def test_stronger_teams_advance_more_often():
    field = _field(36)
    schedule = bs.make_league_schedule(field, matches_each=8, seed=2)
    standings = bs.simulate_league_phase(field, schedule, bs.FORMATS["ucl"], N=300, seed=2)
    by_team = {r["team"]: r for r in standings}
    assert by_team["T0"]["auto_advance"] > by_team["T35"]["auto_advance"]
