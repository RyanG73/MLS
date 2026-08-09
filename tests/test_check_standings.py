"""Standings cross-check against API-Football's own table. No network.

Spec: docs/superpowers/specs/2026-08-09-platform-reliability-and-api-opportunity-spec.md
§5.1. Four of the eight defects on 2026-08-08 would have shown up here as a
table that disagreed with an independent witness, and every one of them was
found by accident instead.
"""
from __future__ import annotations

import json

import pytest

from scripts import check_standings as cs


OURS = [
    {"team": "Arsenal", "played": 10, "points": 24, "gd": 12},
    {"team": "Manchester City", "played": 10, "points": 22, "gd": 15},
    {"team": "Nottingham Forest", "played": 10, "points": 11, "gd": -3},
]


def _theirs(**overrides):
    rows = [dict(r) for r in OURS]
    for team, patch in overrides.items():
        for r in rows:
            if r["team"].replace(" ", "_") == team:
                r.update(patch)
    return rows


def test_identical_tables_agree():
    out = cs.diff_tables(OURS, _theirs())
    assert out["disagreements"] == []
    assert out["matched"] == 3 and out["unmatched_ours"] == []


def test_a_missing_fixture_shows_up_as_a_played_disagreement():
    out = cs.diff_tables(OURS, _theirs(Arsenal={"played": 11, "points": 27}))
    assert len(out["disagreements"]) == 1
    fields = out["disagreements"][0]["fields"]
    assert fields["played"] == {"ours": 10, "theirs": 11}
    assert fields["points"] == {"ours": 24, "theirs": 27}


def test_a_wrong_scoreline_shows_up_with_played_agreeing():
    out = cs.diff_tables(OURS, _theirs(Arsenal={"points": 23, "gd": 11}))
    fields = out["disagreements"][0]["fields"]
    assert "played" not in fields and "points" in fields and "gd" in fields


def test_a_points_deduction_is_reported_not_hidden():
    """A deduction is a real disagreement and NOT a defect — which is why the
    check reports rather than fails by default."""
    out = cs.diff_tables(OURS, _theirs(Nottingham_Forest={"points": 7}))
    assert out["disagreements"][0]["team"] == "Nottingham Forest"


def test_names_are_matched_exactly_or_reported_never_guessed():
    """Fuzzy matching proposed `Bristol City → Stoke City` during the Stage-3
    migration. A wrong pairing here would attribute one club's record to
    another and read as a plausible disagreement."""
    theirs = [dict(r) for r in OURS]
    theirs[2]["team"] = "Nottingham Forest FC"
    out = cs.diff_tables(OURS, theirs)
    assert out["disagreements"] == []
    assert out["unmatched_ours"] == ["Nottingham Forest"]
    assert out["unmatched_theirs"] == ["Nottingham Forest FC"]


def test_accent_and_punctuation_differences_still_match():
    theirs = [dict(r) for r in OURS]
    theirs[0]["team"] = "ARSENAL"
    theirs[1]["team"] = "Manchester-City"
    out = cs.diff_tables(OURS, theirs)
    assert out["matched"] == 3 and out["disagreements"] == []


def test_a_competition_mixing_bug_shows_up_as_extra_clubs():
    """Defect #6 put 920 Argentine cup matches inside the league frame; defect
    #4 put La Liga clubs into a second-tier table. Both present as a club set
    that does not belong."""
    ours = OURS + [{"team": "Racing Club", "played": 10, "points": 9, "gd": -5}]
    out = cs.diff_tables(ours, _theirs())
    assert out["unmatched_ours"] == ["Racing Club"]


# ── per-league orchestration ─────────────────────────────────────────────────
def _payload_dir(tmp_path, league_id="epl", season=2026, rows=None):
    from scripts.payload_utils import write_js_payload
    d = tmp_path / "data"
    d.mkdir(exist_ok=True)
    write_js_payload(d / f"{league_id}.js", "LEAGUE_DATA", {
        "league": {"id": league_id}, "season": season,
        "standings": [{"team": r["team"], "gp": r["played"],
                       "pts": r["points"], "gd": r["gd"]} for r in (rows or OURS)]})
    return d


def test_check_league_reports_agreement(tmp_path):
    d = _payload_dir(tmp_path)
    out = cs.check_league("epl", {"af_id": 39},
                          fetch=lambda af_id, season, names: _theirs(),
                          payload_dir=d)
    assert out["status"] == "agree" and out["season"] == 2026


def test_check_league_requests_the_season_our_payload_publishes(tmp_path):
    """Asking for the wrong season would diff this year's table against last
    year's and report every club as disagreeing."""
    d = _payload_dir(tmp_path, season=2025)
    seen = {}

    def fetch(af_id, season, names):
        seen.update(af_id=af_id, season=season)
        return _theirs()

    cs.check_league("epl", {"af_id": 39}, fetch=fetch, payload_dir=d)
    assert seen == {"af_id": 39, "season": 2025}


def test_an_upstream_error_is_recorded_not_raised(tmp_path):
    """No credential, a 403, a plan lapse — the check reports and moves to the
    next league. One dead league must not cost the other 77 their check."""
    d = _payload_dir(tmp_path)

    def boom(af_id, season, names):
        raise RuntimeError("API_FOOTBALL_KEY not set")

    out = cs.check_league("epl", {"af_id": 39}, fetch=boom, payload_dir=d)
    assert out["status"] == "error" and "API_FOOTBALL_KEY" in out["reason"]


def test_an_empty_upstream_table_is_off_season_not_a_defect(tmp_path):
    d = _payload_dir(tmp_path)
    out = cs.check_league("epl", {"af_id": 39},
                          fetch=lambda *a: [], payload_dir=d)
    assert out["status"] == "no_upstream_table"


def test_a_league_with_no_published_table_is_skipped(tmp_path):
    out = cs.check_league("epl", {"af_id": 39}, fetch=lambda *a: [],
                          payload_dir=tmp_path / "empty")
    assert out["status"] == "skipped"


def test_disagreements_surface_as_warnings(capsys):
    cs.annotate([{"league": "epl", "status": "disagree", "disagreements": [
        {"team": "Arsenal", "fields": {"points": {"ours": 24, "theirs": 27}}}]}])
    out = capsys.readouterr().out
    assert "::warning::" in out and "Arsenal" in out and "24" in out and "27" in out


def test_main_writes_a_report_and_does_not_fail_on_disagreement(tmp_path, monkeypatch):
    d = _payload_dir(tmp_path)
    report = tmp_path / "report.json"
    monkeypatch.setattr(cs, "league_map", lambda path=None: {"epl": {"af_id": 39}})
    monkeypatch.setattr(cs, "check_league",
                        lambda lid, entry, payload_dir=None: {
                            "league": lid, "status": "disagree",
                            "disagreements": [{"team": "Arsenal", "fields": {}}]})
    assert cs.main(["--report", str(report), "--payload-dir", str(d)]) == 0
    assert json.loads(report.read_text())["counts"]["disagree"] == 1
    # ...and fails only when asked to.
    assert cs.main(["--report", str(report), "--payload-dir", str(d), "--strict"]) == 1


def test_every_approved_league_id_is_an_int():
    """The check is driven by the owner-approved map; a malformed id would skip
    a league silently."""
    catalogue = cs.league_map()
    assert catalogue, "config/api_football_league_map.json must be readable"
    bad = {k: v.get("af_id") for k, v in catalogue.items()
           if not isinstance(v.get("af_id"), int)}
    assert not bad, bad


# ── the response is validated before it is believed (R1) ────────────────────
def test_standings_rows_reject_a_wrong_league_response(monkeypatch):
    from data_pipeline import api_football
    monkeypatch.setattr(api_football, "_get", lambda path, params, budget="ops": {
        "response": [{"league": {"id": 140, "season": 2026, "standings": [[]]}}]})
    with pytest.raises(api_football.IdentityMismatch):
        api_football.standings_rows(141, 2026)


def test_standings_rows_flatten_groups_and_apply_names(monkeypatch):
    from data_pipeline import api_football
    monkeypatch.setattr(api_football, "_get", lambda path, params, budget="ops": {
        "response": [{"league": {"id": 39, "season": 2026, "standings": [
            [{"rank": 1, "team": {"name": "Arsenal FC"}, "points": 24,
              "goalsDiff": 12, "group": "A",
              "all": {"played": 10, "goals": {"for": 20, "against": 8}}}],
            [{"rank": 1, "team": {"name": "Chelsea"}, "points": 20,
              "goalsDiff": 6, "group": "B",
              "all": {"played": 10, "goals": {"for": 15, "against": 9}}}],
        ]}}]})
    rows = api_football.standings_rows(39, 2026, {"Arsenal FC": "Arsenal"})
    assert [r["team"] for r in rows] == ["Arsenal", "Chelsea"]
    assert rows[0] == {"rank": 1, "team": "Arsenal", "played": 10, "points": 24,
                       "gf": 20, "ga": 8, "gd": 12, "group": "A"}


def test_the_daily_refresh_runs_the_cross_check():
    """§5.1 is worth nothing if it only ever runs by hand."""
    from pathlib import Path
    text = (Path(__file__).resolve().parent.parent /
            ".github/workflows/refresh-daily.yml").read_text()
    assert "check_standings.py" in text
    # Non-fatal by construction: an unmodelled points deduction must not turn a
    # good refresh red.
    step = text[text.index("check_standings.py"):]
    assert "non-fatal" in step.split("\n")[0]
