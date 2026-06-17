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


def test_schedule_is_balanced_each_team_plays_matches_each():
    from collections import Counter
    field = _field(36)
    sched = bs.make_league_schedule(field, matches_each=8, seed=5)
    games_per_team = Counter()
    for hi, ai, _ in sched:
        games_per_team[hi] += 1
        games_per_team[ai] += 1
    assert all(games_per_team[i] == 8 for i in range(36))
    # no team plays itself
    assert all(hi != ai for hi, ai, _ in sched)


class TestKnockout:
    def test_two_leg_tie_favors_stronger(self):
        wins = 0
        rng = np.random.default_rng(0)
        for _ in range(500):
            if bs.sim_two_leg(1900, 1600, rng, fmt=bs.FORMATS["ucl"]) == 0:
                wins += 1
        assert wins > 250  # stronger team (idx 0) wins the tie majority

    def test_single_leg_final_returns_a_winner(self):
        rng = np.random.default_rng(0)
        w = bs.sim_single_leg(1700, 1700, rng, neutral=True)
        assert w in (0, 1)

    def test_full_simulate_returns_champion_odds_summing_to_one(self):
        field = [{"team": f"T{i}", "strength": 1900 - i * 10} for i in range(36)]
        out = bs.simulate("ucl", field, N=200, seed=3)
        total = sum(t["odds"]["win"] for t in out["field"])
        assert total == pytest.approx(1.0, abs=1e-6)
        assert len(out["standings"]) == 36


def test_europa_conference_formats():
    assert bs.FORMATS["europa"]["phase"]["matches_each"] == 8
    assert bs.FORMATS["conference"]["phase"]["matches_each"] == 6
    for c in ("europa", "conference"):
        assert bs.FORMATS[c]["phase"]["auto_advance"] == 8
        assert bs.FORMATS[c]["phase"]["playoff"] == (9, 24)
        assert [r["round"] for r in bs.FORMATS[c]["ko"]] == ["R16", "QF", "SF", "Final"]


class TestPureKnockout:
    def test_concacaf_cc_format(self):
        f = bs.FORMATS["concacaf-champions"]
        assert f["phase"]["type"] == "bracket"
        assert f["phase"]["teams"] == 27
        assert f["phase"]["byes"] == 5

    def test_pure_knockout_simulate(self):
        field = [{"team": f"T{i}", "strength": 1700 - i * 8} for i in range(27)]
        out = bs.simulate("concacaf-champions", field, N=400, seed=1)
        assert abs(sum(t["odds"]["win"] for t in out["field"]) - 1.0) < 1e-6
        byt = {t["team"]: t for t in out["field"]}
        assert byt["T0"]["odds"]["win"] > byt["T26"]["odds"]["win"]  # top seed favored
        assert out["standings"] == []                                # no league table
        # the 5 byes never play Round One; the rest do
        assert sum(1 for t in out["field"] if t.get("bye")) == 5
        assert byt["T0"].get("bye") is True                          # strongest gets a bye
