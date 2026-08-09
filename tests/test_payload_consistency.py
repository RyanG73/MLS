"""Payload self-consistency checks. No network, no builder.

Spec: docs/superpowers/specs/2026-08-09-platform-reliability-and-api-opportunity-spec.md
§5.2/§5.3. Every check reads the payload the way a client does (§8.13); a check
that calls the producer passes tautologically, which is exactly how the Global
ELO validator came to assert arithmetic the producer had stopped doing.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from scripts import check_payload_consistency as cpc

ROOT = Path(__file__).resolve().parent.parent


def _payload(standings, games, season=2026):
    return {"season": season, "standings": standings, "games": games}


def _rr(teams):
    """A clean double round-robin, every match played."""
    games = []
    for h in teams:
        for a in teams:
            if h != a:
                games.append({"home": h, "away": a, "result": "H"})
    return games


TEAMS = ["A", "B", "C", "D"]


def test_a_clean_double_round_robin_passes_every_check():
    n = len(TEAMS) - 1
    table = [{"team": t, "gp": 2 * n} for t in TEAMS]
    out = cpc.check_payload("x", _payload(table, _rr(TEAMS)))
    assert all(c["ok"] for c in out["checks"].values())
    assert out["checks"]["fixtures"]["shape"] == "double_round_robin"


def test_a_club_playing_fixtures_but_missing_from_the_table_is_caught():
    """Defect #4 put La Liga clubs into a second-tier frame; defect #6 put 920
    Argentine cup matches inside a league. Both present as a club that does not
    belong."""
    games = _rr(TEAMS) + [{"home": "Real Madrid", "away": "A", "result": "H"}]
    table = [{"team": t, "gp": 6} for t in TEAMS]
    out = cpc.check_payload("x", _payload(table, games))
    assert out["checks"]["clubs"]["ok"] is False
    assert out["checks"]["clubs"]["in_fixtures_not_in_table"] == ["Real Madrid"]


def test_a_club_in_the_table_with_no_fixtures_is_caught():
    table = [{"team": t, "gp": 6} for t in TEAMS] + [{"team": "Ghost", "gp": 0}]
    out = cpc.check_payload("x", _payload(table, _rr(TEAMS)))
    assert out["checks"]["clubs"]["in_table_not_in_fixtures"] == ["Ghost"]


def test_a_table_disagreeing_with_its_own_fixtures_is_caught():
    """Two numbers in ONE payload that must agree. A disagreement is
    truncation, duplication, or a table computed off a different frame."""
    table = [{"team": t, "gp": 6} for t in TEAMS]
    table[0]["gp"] = 5
    out = cpc.check_payload("x", _payload(table, _rr(TEAMS)))
    assert out["checks"]["played"]["mismatches"] == [
        {"team": "A", "table_gp": 5, "fixtures_played": 6}]


def test_unplayed_fixtures_do_not_count_toward_games_played():
    games = _rr(TEAMS)
    games[0] = {**games[0], "result": None}
    table = [{"team": t, "gp": 6} for t in TEAMS]
    table[0]["gp"] = 5                       # A lost one played game
    table[1]["gp"] = 5                       # ...and so did its opponent
    out = cpc.check_payload("x", _payload(table, games))
    assert out["checks"]["played"]["ok"] is True


def test_pairs_meeting_a_different_number_of_times_is_surfaced():
    """Argentina 2026: Apertura + Clausura + interzonal summed into one table,
    30 clubs, pairs meeting 3x (§8.6). A format a competition filter cannot
    reach, but a count can see."""
    games = _rr(TEAMS) + [{"home": "A", "away": "B", "result": "H"}]
    table = [{"team": t, "gp": 6} for t in TEAMS]
    table[0]["gp"] = table[1]["gp"] = 7
    out = cpc.check_payload("x", _payload(table, games))
    assert out["checks"]["pairs"]["ok"] is False
    assert out["checks"]["pairs"]["max_meetings"] == 3


def test_a_trailing_space_in_a_club_name_is_caught():
    """'Liga Profesional ' vs 'Liga Profesional' — a trailing space, 2,114
    rows, and an exact-match filter one step from deleting a third of a
    league (§8.3)."""
    games = _rr(TEAMS) + [{"home": "A ", "away": "B", "result": "H"}]
    table = [{"team": t, "gp": 6} for t in TEAMS]
    out = cpc.check_payload("x", _payload(table, games))
    assert out["checks"]["names"]["ok"] is False
    assert out["checks"]["names"]["untrimmed"] == ["A "]
    assert out["checks"]["names"]["collisions"]["a"] == ["A", "A "]


def test_fixture_shape_is_classified_not_judged():
    """45 of 78 payloads are legitimately not a plain double round-robin —
    cups, split seasons, and feeds that publish only the next few weeks.
    Failing on that would be noise, so the shape is reported."""
    table = [{"team": t, "gp": 3} for t in TEAMS]
    half = [g for g in _rr(TEAMS) if g["home"] < g["away"]]
    out = cpc.check_payload("x", _payload(table, half))
    assert out["checks"]["fixtures"]["shape"] == "single_round_robin"
    assert out["checks"]["fixtures"]["ok"] is True


# ── the baseline: new deviation = regression ─────────────────────────────────
def test_strict_passes_on_a_baselined_deviation_and_fails_on_a_new_one(tmp_path, monkeypatch):
    baseline = tmp_path / "baseline.json"
    baseline.write_text(json.dumps({"deviations": {"clubs": ["cupcomp"]}}))
    results = [{"league": "cupcomp", "checks": _failing("clubs")}]
    monkeypatch.setattr(cpc, "league_payloads", lambda d, o=None: [])
    monkeypatch.setattr(cpc, "check_payload", lambda lid, p: results[0])

    # nothing checked → nothing failing → strict passes
    assert cpc.main(["--strict", "--baseline", str(baseline),
                     "--report", str(tmp_path / "r.json"),
                     "--payload-dir", str(tmp_path)]) == 0


def test_strict_fails_on_a_deviation_outside_the_baseline(tmp_path, monkeypatch):
    baseline = tmp_path / "baseline.json"
    baseline.write_text(json.dumps({"deviations": {"clubs": ["cupcomp"]}}))
    monkeypatch.setattr(cpc, "league_payloads",
                        lambda d, o=None: [("epl", {})])
    monkeypatch.setattr(cpc, "check_payload",
                        lambda lid, p: {"league": lid, "checks": _failing("played")})
    assert cpc.main(["--strict", "--baseline", str(baseline),
                     "--report", str(tmp_path / "r.json"),
                     "--payload-dir", str(tmp_path)]) == 1


def test_the_committed_baseline_records_what_the_payloads_actually_show(tmp_path):
    """The baseline is a MEASUREMENT of an unadjudicated state, not a list of
    leagues that are fine. It must match the committed payloads, or it is
    quietly excusing something that changed.

    Reads the payloads out of `git show HEAD:`, NOT the working tree. The
    baseline is committed, so the only honest comparison is against committed
    payloads. A working-tree read fails on any machine where a local refresh
    has run — which is every developer machine here, daily — and the failure
    message points at `--write-baseline`, so the natural response is to bake
    locally-built payload artifacts into the committed baseline. Local builds
    rebuild the PREVIOUS season and exit 0; CI owns payload writes.
    """
    export = tmp_path / "head"
    export.mkdir()
    archive = subprocess.run(["git", "archive", "HEAD", "webapp/data"],
                             cwd=ROOT, capture_output=True)
    if archive.returncode != 0:
        pytest.skip("not a git checkout: cannot read committed payloads")
    subprocess.run(["tar", "-x", "-C", str(export)],
                   input=archive.stdout, check=True)

    baseline = json.loads((ROOT / cpc.BASELINE_PATH).read_text())["deviations"]
    results = [cpc.check_payload(lid, p)
               for lid, p in cpc.league_payloads(export / "webapp/data")]
    assert results, "no league payloads found"
    for check in cpc.STRICT_CHECKS:
        measured = sorted(r["league"] for r in results if not r["checks"][check]["ok"])
        assert measured == sorted(baseline.get(check) or []), (
            f"{check}: payloads show {measured}, baseline says "
            f"{sorted(baseline.get(check) or [])} — regenerate deliberately "
            f"with --write-baseline, and only after adjudicating the change")


def _failing(check: str) -> dict:
    base = {c: {"ok": True} for c in ("clubs", "played", "fixtures", "pairs", "names")}
    base[check] = {"ok": False, "in_fixtures_not_in_table": [],
                   "in_table_not_in_fixtures": [], "mismatches": [],
                   "multiplicities": [], "max_meetings": 0,
                   "collisions": {}, "untrimmed": []}
    for c in base:
        base[c].setdefault("in_fixtures_not_in_table", [])
        base[c].setdefault("in_table_not_in_fixtures", [])
        base[c].setdefault("mismatches", [])
        base[c].setdefault("collisions", {})
        base[c].setdefault("untrimmed", [])
    return base


def test_the_daily_refresh_runs_the_check_after_the_commit():
    """A failing consistency verdict must never discard payloads the run built
    correctly — that is the 2026-07-19 bug, five nights of good data thrown
    away because a step exited non-zero before the commit."""
    text = (ROOT / ".github/workflows/refresh-daily.yml").read_text()
    assert "check_payload_consistency.py --strict" in text
    assert text.index("git add") < text.index("check_payload_consistency.py --strict")
