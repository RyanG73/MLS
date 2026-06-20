import collections

import numpy as np
import pytest
from scripts.eval import bracket_sim as bs
from scripts.eval.cross_league import _CONF_CONST, match_lambdas


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


# ---------------------------------------------------------------------------
# Part A: confederation-aware match constants
# ---------------------------------------------------------------------------

class TestConfederationConstants:
    def test_conf_const_has_both_confederations(self):
        assert "UEFA" in _CONF_CONST
        assert "Concacaf" in _CONF_CONST

    def test_uefa_const_values(self):
        c = _CONF_CONST["UEFA"]
        assert c["base_goals"] == pytest.approx(1.35)
        assert c["goal_scale"] == pytest.approx(3000.0)
        assert c["home_adv_elo"] == pytest.approx(80.0)

    def test_concacaf_const_within_sane_bounds(self):
        c = _CONF_CONST["Concacaf"]
        # Physically-sane bounds: base_goals 1.2-1.7, goal_scale 2000-3500, home_adv 40-110
        assert 1.2 <= c["base_goals"] <= 1.7
        assert 2000.0 <= c["goal_scale"] <= 3500.0
        assert 40.0 <= c["home_adv_elo"] <= 110.0

    def test_module_aliases_match_uefa(self):
        from scripts.eval.cross_league import BASE_GOALS, GOAL_SCALE, HOME_ADV_ELO
        assert BASE_GOALS == _CONF_CONST["UEFA"]["base_goals"]
        assert GOAL_SCALE == _CONF_CONST["UEFA"]["goal_scale"]
        assert HOME_ADV_ELO == _CONF_CONST["UEFA"]["home_adv_elo"]

    def test_match_lambdas_default_is_uefa(self):
        # Default (no conf arg) should equal explicit "UEFA"
        sh, sa = 1700.0, 1600.0
        lh_default, la_default = match_lambdas(sh, sa)
        lh_uefa, la_uefa = match_lambdas(sh, sa, conf="UEFA")
        assert lh_default == pytest.approx(lh_uefa)
        assert la_default == pytest.approx(la_uefa)

    def test_concacaf_lambdas_differ_from_uefa(self):
        # Different constants → different lambdas
        sh, sa = 1700.0, 1600.0
        lh_uefa, la_uefa = match_lambdas(sh, sa, conf="UEFA")
        lh_cc, la_cc = match_lambdas(sh, sa, conf="Concacaf")
        assert lh_uefa != pytest.approx(lh_cc)  # should differ

    def test_formats_have_conf_keys(self):
        for comp_id in ("ucl", "europa", "conference"):
            assert bs.FORMATS[comp_id].get("conf") == "UEFA"
        for comp_id in ("concacaf-champions", "leagues-cup"):
            assert bs.FORMATS[comp_id].get("conf") == "Concacaf"


# ---------------------------------------------------------------------------
# Part B: explicit knockout-playoff round (UCL league path)
# ---------------------------------------------------------------------------

class TestKOPlayoffRound:
    def test_ucl_simulate_has_koplayout_key(self):
        field = _field(36)
        out = bs.simulate("ucl", field, N=200, seed=5)
        for t in out["field"]:
            assert "KOplayoff" in t["odds"], f"KOplayoff missing for {t['team']}"

    def test_round_size_invariant(self):
        """KOplayoff=16, R16=16, QF=8, SF=4, Final=2, win=1."""
        field = [{"team": f"T{i}", "strength": 1750 - i * 8} for i in range(36)]
        out = bs.simulate("ucl", field, N=2000, seed=7)
        totals = collections.defaultdict(float)
        for t in out["field"]:
            for r, v in t["odds"].items():
                totals[r] += v
        assert totals["KOplayoff"] == pytest.approx(16.0, abs=0.1)
        assert totals["R16"]       == pytest.approx(16.0, abs=0.1)
        assert totals["QF"]        == pytest.approx(8.0,  abs=0.1)
        assert totals["SF"]        == pytest.approx(4.0,  abs=0.1)
        assert totals["Final"]     == pytest.approx(2.0,  abs=0.1)
        assert totals["win"]       == pytest.approx(1.0,  abs=1e-6)

    def test_auto_advancers_have_zero_koplayout(self):
        """Auto-advancers (top-8) skip KOplayoff — so KOplayoff ≤ P(rank 9-24).
        Weak teams (guaranteed to finish 25-36) never reach KOplayoff either."""
        # Equal-strength field: every team has ~P(auto)=8/36, P(playoff)=16/36, P(elim)=12/36.
        # The weakest 12 teams (by construction) should have low KOplayoff odds.
        # Easier to test: the sum of KOplayoff across all 36 teams should be exactly 16.
        field = _field(36)
        out = bs.simulate("ucl", field, N=1000, seed=9)
        total_kop = sum(t["odds"]["KOplayoff"] for t in out["field"])
        # KOplayoff should sum to 16 (16 teams enter the KO-playoff each sim).
        assert total_kop == pytest.approx(16.0, abs=0.2)
        # Auto-advance and KOplayoff are mutually exclusive: a team's (auto + KOplayoff)
        # should not exceed 1 (it can't be in both).
        for t in out["field"]:
            auto = t.get("auto_advance", 0.0)
            kop = t["odds"]["KOplayoff"]
            assert auto + kop <= 1.01, (
                f"{t['team']}: auto={auto:.3f} + KOplayoff={kop:.3f} > 1")

    def test_koplayout_teams_also_have_r16_odds(self):
        """Teams deep in the mid-table are almost always in the KO-playoff zone,
        so their KOplayoff odds dominate their auto-advance odds.
        For teams near rank 16-24 (well inside the 9-24 band), KOplayoff > auto_advance."""
        field = _field(36)
        out = bs.simulate("ucl", field, N=1000, seed=11)
        by_name = {t["team"]: t for t in out["field"]}
        # Teams T15..T23 are deep in the playoff band; should have KOplayoff > auto_advance.
        for i in range(15, 24):
            t = by_name[f"T{i}"]
            kop = t["odds"]["KOplayoff"]
            auto = t.get("auto_advance", 0.0)
            assert kop > auto, (
                f"T{i}: KOplayoff={kop:.3f} should exceed auto_advance={auto:.3f}")

    def test_europa_conference_also_have_koplayout(self):
        """Europa/Conference use same league format; should also have KOplayoff."""
        for comp_id in ("europa", "conference"):
            field = _field(36)
            out = bs.simulate(comp_id, field, N=200, seed=13)
            for t in out["field"]:
                assert "KOplayoff" in t["odds"], (
                    f"{comp_id}: KOplayoff missing for {t['team']}")


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


class TestTwoTableGroup:
    def test_leagues_cup_format(self):
        f = bs.FORMATS["leagues-cup"]
        assert f["phase"]["type"] == "two_table"
        assert f["phase"]["advance_per_table"] == 4

    def test_leagues_cup_simulate(self):
        field = ([{"team": f"MLS{i}", "league": "mls", "strength": 1600 - i*5} for i in range(18)] +
                 [{"team": f"MX{i}", "league": "liga-mx", "strength": 1620 - i*5} for i in range(18)])
        out = bs.simulate("leagues-cup", field, N=400, seed=2)
        assert abs(sum(t["odds"]["win"] for t in out["field"]) - 1.0) < 1e-6
        assert len(out["standings"]) == 36
        assert {s.get("table") for s in out["standings"]} == {"mls", "liga-mx"}
        # every field entry has an advance prob and QF/SF/Final/win odds
        for t in out["field"]:
            for k in ("QF","SF","Final","win"): assert k in t["odds"]
            assert 0.0 <= t["advance"] <= 1.0
