from __future__ import annotations

import copy
import datetime as dt
import json
import pathlib

import pytest
import requests

from scripts import fast_refresh
from scripts.fast_refresh import apply_feed, in_match_window, select_leagues
from scripts.intelligence.simulation import run_simulation
from scripts.payload_utils import write_js_payload


NOW = dt.datetime(2026, 7, 26, 19, 0, tzinfo=dt.timezone.utc)


def _payload(kickoff="2026-07-26T19:30:00Z"):
    return {
        "status": "live",
        "data_status": "full_forecast",
        "league": {"id": "test", "name": "Test League", "pct_complete": 0},
        "season": 2026,
        "generated": "2026-07-26 11:00 UTC",
        "n_sims": 400,
        "provenance": {"champion_run": "champion-v1"},
        "outlook": {
            "mode": "table",
            "columns": [
                {"key": "title", "top": 1},
                {"key": "releg", "bottom": 1},
            ],
        },
        "standings": [
            {
                "team": "Alpha FC", "team_id": "v1:alpha", "pts": 0,
                "gp": 0, "gd": 0, "proj_pts": 1.5, "proj_rank": 1.5,
                "title": 50.0, "releg": 50.0,
            },
            {
                "team": "Beta United", "team_id": "v1:beta", "pts": 0,
                "gp": 0, "gd": 0, "proj_pts": 1.5, "proj_rank": 1.5,
                "title": 50.0, "releg": 50.0,
            },
        ],
        "games": [{
            "date": "2026-07-26", "ko": kickoff,
            "home": "Alpha FC", "away": "Beta United",
            "home_id": "v1:alpha", "away_id": "v1:beta",
            "fixture_id": "v1:fixture",
            "pH": 0.5, "pD": 0.25, "pA": 0.25,
            "hg": None, "ag": None, "result": None,
        }],
        "sim": {
            "teams": ["Alpha FC", "Beta United"],
            "pmatrix": [[None, [500, 250, 250]], [[250, 250, 500], None]],
        },
    }


def test_match_window_uses_kickoff_and_date_fallback():
    assert in_match_window(_payload(), NOW)
    assert not in_match_window(
        _payload("2026-07-27T12:00:00Z"), NOW)
    date_only = _payload(None)
    assert in_match_window(date_only, NOW)


def test_selector_runs_all_hourly_and_only_match_windows_between(tmp_path):
    registry = tmp_path / "leagues.js"
    payload_dir = tmp_path / "data"
    write_js_payload(registry, "LEAGUES", [
        {
            "id": "active", "status": "live", "espn_code": "test.1",
            "data_status": "full_forecast",
        },
        {
            "id": "quiet", "status": "live", "espn_code": "test.2",
            "data_status": "full_forecast",
        },
    ])
    write_js_payload(payload_dir / "active.js", "LEAGUE_DATA", _payload())
    quiet = _payload("2026-07-28T19:30:00Z")
    quiet["league"]["id"] = "quiet"
    write_js_payload(payload_dir / "quiet.js", "LEAGUE_DATA", quiet)

    assert select_leagues(
        payload_dir, registry, NOW.replace(minute=5)) == ["active", "quiet"]
    assert select_leagues(
        payload_dir, registry, NOW.replace(minute=30)) == ["active"]


def test_completed_result_advances_table_without_changing_probability_matrix():
    payload = _payload()
    original_matrix = copy.deepcopy(payload["sim"]["pmatrix"])
    result = apply_feed(payload, [{
        "provider_id": "espn-1",
        "date": "2026-07-26",
        "ko": "2026-07-26T19:30:00Z",
        "home": "Alpha",
        "away": "Beta United FC",
        "completed": True,
        "hg": 2,
        "ag": 0,
    }], now=NOW, sims=200)

    assert result["results_applied"] == 1
    assert payload["games"][0]["result"] == "H"
    assert payload["standings"][0]["pts"] == 3
    assert payload["standings"][0]["gp"] == 1
    assert payload["standings"][0]["gd"] == 2
    assert payload["standings"][0]["title"] == 100.0
    assert payload["standings"][1]["releg"] == 100.0
    assert payload["sim"]["pmatrix"] == original_matrix
    assert payload["fast_refresh"]["fitted_model_at"] == "2026-07-26 11:00 UTC"
    assert payload["fast_refresh"]["market_prices_at"] == "2026-07-26 11:00 UTC"
    assert payload["fast_refresh"]["odds_refreshed"] is False

    # Applying the same completed feed again cannot double-count the table.
    before = json.dumps(payload["standings"], sort_keys=True)
    again = apply_feed(payload, [{
        "date": "2026-07-26", "ko": "2026-07-26T19:30:00Z",
        "home": "Alpha", "away": "Beta United",
        "completed": True, "hg": 2, "ag": 0,
    }], now=NOW + dt.timedelta(minutes=15), sims=200)
    assert again["results_applied"] == 0
    assert json.dumps(payload["standings"], sort_keys=True) == before


def _stub_refresh(monkeypatch, selected, dead):
    """Point --refresh-selected at `selected`, failing the feed for `dead`."""
    refreshed = []

    def fake_refresh(league_id, sims=None):
        if league_id in dead:
            raise requests.HTTPError(
                f"403 Client Error: Forbidden for url: .../{league_id}/scoreboard")
        refreshed.append(league_id)
        return {"league_id": league_id, "results_applied": 0,
                "kickoff_updates": 0, "feed_rows": 0, "generated": None}

    monkeypatch.setattr(fast_refresh, "select_leagues", lambda: list(selected))
    monkeypatch.setattr(fast_refresh, "refresh_league", fake_refresh)
    monkeypatch.setattr("sys.argv", ["fast_refresh.py", "--refresh-selected"])
    return refreshed


def test_one_dead_league_feed_does_not_stop_the_others(monkeypatch, capsys):
    refreshed = _stub_refresh(
        monkeypatch, ["arg.1", "bol.1", "bra.1", "usa.1"], dead={"bol.1"})

    assert fast_refresh.main() == 0
    assert refreshed == ["arg.1", "bra.1", "usa.1"]

    report = json.loads(capsys.readouterr().out)
    assert [row["league_id"] for row in report["refreshed"]] == [
        "arg.1", "bra.1", "usa.1"]
    assert [row["league_id"] for row in report["failed"]] == ["bol.1"]


def test_refresh_exits_non_zero_when_most_league_feeds_fail(monkeypatch, capsys):
    """An IP-wide ESPN block must stay loud — it is not one dead league."""
    refreshed = _stub_refresh(
        monkeypatch, ["arg.1", "bol.1", "bra.1", "usa.1"],
        dead={"arg.1", "bol.1", "bra.1"})

    assert fast_refresh.main() != 0
    assert refreshed == ["usa.1"]
    assert len(json.loads(capsys.readouterr().out)["failed"]) == 3


def test_refresh_with_nothing_selected_succeeds(monkeypatch, capsys):
    """Guards the threshold's zero denominator — no leagues is not a failure."""
    _stub_refresh(monkeypatch, [], dead=set())

    assert fast_refresh.main() == 0
    assert json.loads(capsys.readouterr().out) == {"refreshed": [], "failed": []}


def test_refresh_isolation_does_not_swallow_payload_bugs(monkeypatch):
    """Only feed errors are per-league. A broken payload is still a hard stop."""
    monkeypatch.setattr(fast_refresh, "select_leagues", lambda: ["arg.1"])
    monkeypatch.setattr("sys.argv", ["fast_refresh.py", "--refresh-selected"])

    def fake_refresh(league_id, sims=None):
        raise AssertionError("fast refresh mutated the fitted probability matrix")

    monkeypatch.setattr(fast_refresh, "refresh_league", fake_refresh)
    try:
        fast_refresh.main()
    except AssertionError as exc:
        assert "probability matrix" in str(exc)
    else:
        raise AssertionError("payload integrity failure was swallowed")


def test_mls_fast_simulation_updates_conference_and_cup_targets():
    teams = [
        {
            "team": f"{conference} {index}",
            "team_id": f"v1:{conference.lower()}-{index}",
            "conf": conference,
            "pts": 30 - index,
            "gd": 9 - index,
        }
        for conference in ("East", "West")
        for index in range(9)
    ]
    size = len(teams)
    pmatrix = [
        [
            None if home == away else [400, 300, 300]
            for away in range(size)
        ]
        for home in range(size)
    ]
    snapshot = {
        "teams": teams,
        "fixtures": [],
        "pmatrix": pmatrix,
        "n_sims": 200,
        "replay_seed": 42,
        "rules": {
            "mode": "mls",
            "targets": [
                {"key": "playoff", "per_conf_top": 9},
                {"key": "hfa", "per_conf_top": 4},
                {"key": "shield", "top": 1},
                {"key": "spoon", "bottom": 1},
            ],
        },
    }

    result = run_simulation(snapshot, n=200)

    assert round(sum(row["conf_win"] for row in result.values()), 1) == 200.0
    assert round(sum(row["cup"] for row in result.values()), 1) == 100.0
    assert result["v1:east-0"]["conf_win"] == 100.0
    assert result["v1:west-0"]["conf_win"] == 100.0


# ── spine routing (Stage 3): migrated leagues must not depend on ESPN ────────
# The fast refresh is what failed seven consecutive times on 2026-08-07 and
# motivated the whole API-Football migration — yet on 2026-08-08 it was still
# 100% ESPN, so leagues already migrated in build_league_data (northern-super-
# league, usl-super-league) kept failing here behind the ESPN circuit breaker.

def _af_fixtures_payload():
    return {"response": [
        {"fixture": {"id": 77, "date": "2026-08-08T23:00:00+00:00",
                     "status": {"short": "FT"}},
         "league": {"season": 2026},
         "teams": {"home": {"name": "Calgary Wild W"},
                   "away": {"name": "AFC Toronto W"}},
         "goals": {"home": 2, "away": 1}},
        {"fixture": {"id": 78, "date": "2026-08-10T23:00:00+00:00",
                     "status": {"short": "NS"}},
         "league": {"season": 2026},
         "teams": {"home": {"name": "Ottawa Rapid W"},
                   "away": {"name": "Halifax Tides W"}},
         "goals": {"home": None, "away": None}},
    ]}


def test_spine_scoreboard_is_provider_neutral_and_name_mapped(monkeypatch):
    """Same row shape as fetch_scoreboard, with team names mapped to OUR
    canonical spellings — the payload is keyed on those."""
    from data_pipeline import api_football
    monkeypatch.setattr(api_football, "_get",
                        lambda path, params, budget="ops": _af_fixtures_payload())
    rows = fast_refresh.fetch_spine_scoreboard(
        "northern-super-league", now=dt.datetime(2026, 8, 9, tzinfo=dt.timezone.utc))
    assert {r["home"] for r in rows} == {"Calgary Wild FC", "Ottawa Rapid FC"}
    assert set(rows[0]) == {"provider_id", "date", "ko", "home", "away",
                            "completed", "hg", "ag"}
    done = [r for r in rows if r["completed"]]
    assert len(done) == 1 and done[0]["hg"] == 2 and done[0]["ag"] == 1
    assert [r for r in rows if not r["completed"]][0]["hg"] is None


def test_refresh_league_uses_spine_and_never_calls_espn(monkeypatch, tmp_path):
    from data_pipeline import api_football
    from data_pipeline import source_registry

    def no_espn(*a, **k):
        raise AssertionError("ESPN called for a spine-routed league")

    monkeypatch.setattr(fast_refresh, "fetch_scoreboard", no_espn)
    monkeypatch.setattr(api_football, "_get",
                        lambda path, params, budget="ops": _af_fixtures_payload())
    monkeypatch.setitem(source_registry.REGISTRY, "northern-super-league",
                        {"fixtures": ["api_football", "espn"]})
    seen = {}
    monkeypatch.setattr(fast_refresh, "apply_feed",
                        lambda payload, rows, **kw: seen.update(rows=rows) or {"updated": 0})
    payload_dir = tmp_path
    write_js_payload(payload_dir / "northern-super-league.js", "LEAGUE_DATA",
                     {"league": {"id": "northern-super-league"}})
    reg = tmp_path / "leagues.js"
    write_js_payload(reg, "LEAGUES", [{"id": "northern-super-league",
                                       "espn_code": "can.w.nsl", "status": "live"}])
    out = fast_refresh.refresh_league("northern-super-league",
                                      payload_dir=payload_dir, registry_path=reg)
    assert out["league_id"] == "northern-super-league"
    assert {r["home"] for r in seen["rows"]} == {"Calgary Wild FC", "Ottawa Rapid FC"}


def test_refresh_league_still_uses_espn_when_unrouted(monkeypatch, tmp_path):
    called = {}
    monkeypatch.setattr(fast_refresh, "fetch_scoreboard",
                        lambda code, now=None: called.setdefault("code", code) or [])
    monkeypatch.setattr(fast_refresh, "apply_feed",
                        lambda payload, rows, **kw: {"updated": 0})
    write_js_payload(tmp_path / "epl.js", "LEAGUE_DATA", {"league": {"id": "epl"}})
    reg = tmp_path / "leagues.js"
    write_js_payload(reg, "LEAGUES", [{"id": "epl", "espn_code": "eng.1",
                                       "status": "live"}])
    fast_refresh.refresh_league("epl", payload_dir=tmp_path, registry_path=reg)
    assert called["code"] == "eng.1"


def test_select_leagues_includes_spine_league_without_espn_code(monkeypatch, tmp_path):
    """A spine-routed league with no ESPN slug must still be selectable —
    gating on espn_code alone excluded the very leagues the migration serves."""
    from data_pipeline import source_registry
    monkeypatch.setitem(source_registry.REGISTRY, "canadian-pl",
                        {"fixtures": ["api_football"]})
    reg = tmp_path / "leagues.js"
    write_js_payload(reg, "LEAGUES", [{"id": "canadian-pl", "espn_code": None,
                                       "status": "live"}])
    write_js_payload(tmp_path / "canadian-pl.js", "LEAGUE_DATA",
                     {"sim": {"n": 1}, "standings": [{}], "games": [{}],
                      "data_status": "full_forecast"})
    out = fast_refresh.select_leagues(
        payload_dir=tmp_path, registry_path=reg,
        now=dt.datetime(2026, 8, 9, 10, 5, tzinfo=dt.timezone.utc))
    assert out == ["canadian-pl"]


# ── Ordered fallback and blast radius (2026-08-15) ──────────────────────────
#
# The fast refresh failed 12 of 15 runs on 2026-08-14 with "API_FOOTBALL_KEY not
# set". Three defects compounded: the workflow never carried the secret, the
# per-league isolation caught only requests.RequestException so a RuntimeError
# still aborted every remaining league, and refresh_league honoured no fallback
# though source_registry declares ["api_football", "espn"] in that order.


def _spine_league(monkeypatch, tmp_path, *, espn_code="can.w.nsl"):
    """A spine-routed league with both sources declared, payload and registry on disk."""
    from data_pipeline import source_registry
    monkeypatch.setitem(source_registry.REGISTRY, "northern-super-league",
                        {"fixtures": ["api_football", "espn"]})
    monkeypatch.setattr(fast_refresh, "apply_feed",
                        lambda payload, rows, **kw: {"updated": 0, "rows_seen": len(rows)})
    write_js_payload(tmp_path / "northern-super-league.js", "LEAGUE_DATA",
                     {"league": {"id": "northern-super-league"}})
    reg = tmp_path / "leagues.js"
    write_js_payload(reg, "LEAGUES", [{"id": "northern-super-league",
                                       "espn_code": espn_code, "status": "live"}])
    return reg


def test_a_dead_spine_falls_through_to_espn(monkeypatch, tmp_path):
    """The registry has declared this order since 2026-08-08; only this path ignored it."""
    reg = _spine_league(monkeypatch, tmp_path)
    monkeypatch.setattr(fast_refresh, "fetch_spine_scoreboard",
                        lambda lid, now=None: (_ for _ in ()).throw(
                            RuntimeError("API_FOOTBALL_KEY not set")))
    monkeypatch.setattr(fast_refresh, "fetch_scoreboard",
                        lambda code, now=None: [{"home": "Calgary Wild FC"}])

    out = fast_refresh.refresh_league("northern-super-league",
                                      payload_dir=tmp_path, registry_path=reg)
    assert out["source"] == "espn", "a dead primary must fall through, not fail"
    assert out["rows_seen"] == 1


def test_an_empty_spine_answer_is_an_answer_and_does_not_fall_through(monkeypatch, tmp_path):
    """Why source_registry.resolve() is deliberately NOT reused here.

    resolve() treats an empty frame as a failed source — correct for a standings
    frame, wrong for fixtures: a league with no matches in the ±2-day window
    legitimately returns zero rows. Demoting that to "source failed" would call
    ESPN on a perfectly good answer, and then raise when ESPN agreed there were
    none — inventing an outage out of a quiet Tuesday.
    """
    reg = _spine_league(monkeypatch, tmp_path)
    monkeypatch.setattr(fast_refresh, "fetch_spine_scoreboard", lambda lid, now=None: [])
    monkeypatch.setattr(fast_refresh, "fetch_scoreboard",
                        lambda code, now=None: (_ for _ in ()).throw(
                            AssertionError("ESPN called after a valid empty spine answer")))

    out = fast_refresh.refresh_league("northern-super-league",
                                      payload_dir=tmp_path, registry_path=reg)
    assert out["source"] == "api_football" and out["rows_seen"] == 0


def test_every_source_failing_names_all_of_them(monkeypatch, tmp_path):
    reg = _spine_league(monkeypatch, tmp_path)
    monkeypatch.setattr(fast_refresh, "fetch_spine_scoreboard",
                        lambda lid, now=None: (_ for _ in ()).throw(
                            RuntimeError("API_FOOTBALL_KEY not set")))
    monkeypatch.setattr(fast_refresh, "fetch_scoreboard",
                        lambda code, now=None: (_ for _ in ()).throw(
                            RuntimeError("403 Forbidden")))

    with pytest.raises(fast_refresh.FeedUnavailable) as caught:
        fast_refresh.refresh_league("northern-super-league",
                                    payload_dir=tmp_path, registry_path=reg)
    message = str(caught.value)
    assert "api_football" in message and "espn" in message, (
        "one error must explain the whole chain, not just the last link")
    assert "API_FOOTBALL_KEY" in message and "403" in message


def test_a_league_with_no_feed_left_does_not_abort_the_others(monkeypatch, capsys):
    """The blast radius the 2026-08-07 isolation was written to remove.

    A missing API key raises RuntimeError, which sailed straight through a
    handler that caught only requests.RequestException.
    """
    monkeypatch.setattr(fast_refresh, "select_leagues",
                        lambda: ["arg.1", "northern-super-league", "bra.1"])
    monkeypatch.setattr("sys.argv", ["fast_refresh.py", "--refresh-selected"])

    def refresh(league_id, sims=None):
        if league_id == "northern-super-league":
            raise fast_refresh.FeedUnavailable(
                "every fixture source failed for northern-super-league: "
                "api_football: API_FOOTBALL_KEY not set; espn: 403 Forbidden")
        return {"league_id": league_id, "updated": 0}

    monkeypatch.setattr(fast_refresh, "refresh_league", refresh)
    assert fast_refresh.main() == 0
    report = json.loads(capsys.readouterr().out)
    assert [r["league_id"] for r in report["refreshed"]] == ["arg.1", "bra.1"]
    assert [r["league_id"] for r in report["failed"]] == ["northern-super-league"]


def test_widening_the_handler_did_not_start_swallowing_payload_bugs(monkeypatch):
    """FeedUnavailable is a distinct type precisely so this stays true.

    Catching a bare RuntimeError in refresh_selected would have isolated the
    missing key AND buried every RuntimeError a payload can raise.
    """
    monkeypatch.setattr(fast_refresh, "select_leagues", lambda: ["arg.1"])
    monkeypatch.setattr("sys.argv", ["fast_refresh.py", "--refresh-selected"])
    monkeypatch.setattr(fast_refresh, "refresh_league",
                        lambda league_id, sims=None: (_ for _ in ()).throw(
                            RuntimeError("standings row count changed under us")))

    with pytest.raises(RuntimeError, match="standings row count"):
        fast_refresh.main()


def test_a_fallback_is_recorded_in_source_health(monkeypatch, tmp_path):
    """No silent fallback — the registry's second stated property."""
    reg = _spine_league(monkeypatch, tmp_path)
    recorded = []
    monkeypatch.setattr("data_pipeline.source_health.record_fetch",
                        lambda source, endpoint, ok, **kw: recorded.append(
                            (source, endpoint, ok, kw.get("error"))))
    monkeypatch.setattr(fast_refresh, "fetch_spine_scoreboard",
                        lambda lid, now=None: (_ for _ in ()).throw(
                            RuntimeError("API_FOOTBALL_KEY not set")))
    monkeypatch.setattr(fast_refresh, "fetch_scoreboard", lambda code, now=None: [])

    fast_refresh.refresh_league("northern-super-league",
                                payload_dir=tmp_path, registry_path=reg)
    assert recorded == [("api_football", "fast_refresh:northern-super-league",
                         False, "API_FOOTBALL_KEY not set")]


def test_the_fast_refresh_workflow_carries_the_spine_credentials():
    """The defect was in CI config, so the guard belongs on CI config.

    refresh-fast.yml was the only refresh workflow without the key; it was last
    edited the day before the spine path landed and nobody re-read it.
    """
    import yaml
    workflows = pathlib.Path(__file__).resolve().parent.parent / ".github" / "workflows"
    spine_users = ["refresh-fast.yml", "refresh-daily.yml", "refresh-leagues.yml"]
    for name in spine_users:
        env = yaml.safe_load((workflows / name).read_text()).get("env") or {}
        assert "API_FOOTBALL_KEY" in env, f"{name} can reach the spine without a key"
        assert env.get("API_FOOTBALL_PLAN") == "mega", (
            f"{name} plan value drifted — the governor's lapse guard reads it")


# ── fixture matching: refuse rather than guess (2026-08-15) ─────────────────
#
# The fast refresh matched a feed row to a payload fixture on the AVERAGE of
# two SequenceMatcher ratios with a 0.58 floor, then took the max candidate
# with no ambiguity guard — and this path writes scorelines into the table
# every fifteen minutes. Measured against real confusables at that rule:
# Bristol City/Stoke City 0.727, Sheffield United/Sheffield Wednesday 0.686,
# Manchester United/Manchester City 0.812. Thirteen of fifteen genuinely
# different clubs cleared it. Fuzzy matching had already been banned outright
# in check_standings for the Bristol City case; it survived here.


def _one(home, away, date="2026-03-01"):
    return [{"date": date, "home": home, "away": away, "result": None}]


def _feed(home, away, date="2026-03-01", **kw):
    return {"date": date, "home": home, "away": away, **kw}


@pytest.mark.parametrize("ours, theirs", [
    ("Bristol City", "Stoke City"),                  # the pairing that banned fuzzy
    ("Manchester United", "Manchester City"),
    ("Sheffield United", "Sheffield Wednesday"),
    ("Deportivo Cali", "Deportivo Pasto"),
    ("Atletico Nacional", "Atletico Junior"),
    ("Queens Park", "Queens Park Rangers"),
    ("San Antonio FC", "San Antonio Bulo Bulo"),
    ("Newcastle United", "Newcastle Jets"),
])
def test_two_different_clubs_are_never_matched(ours, theirs):
    """Each of these cleared the old floor. A wrong match here attributes a
    result to the wrong club, and it propagates into the table, the simulation
    and the published forecast with nothing downstream able to tell."""
    assert fast_refresh._match_game(
        _one(ours, "Common Opponent"), _feed(theirs, "Common Opponent"), set()) is None


@pytest.mark.parametrize("ours, theirs", [
    ("Arsenal", "Arsenal FC"),
    ("Inter Miami CF", "Inter Miami"),
    ("St. Louis City SC", "St Louis City"),
    ("Bayern Munich", "FC Bayern Munich"),
    ("Peñarol", "Penarol"),
])
def test_real_spelling_variation_still_matches(ours, theirs):
    """Tightening must not stop results applying — that is the failure this
    change could introduce, and it looks like a healthy but frozen league."""
    assert fast_refresh._match_game(
        _one(ours, "Rival"), _feed(theirs, "Rival"), set()) is not None


def test_a_fixture_is_only_as_good_as_its_weaker_side():
    """Averaging let a perfect home match carry a hopeless away one. A fixture
    is identified by both of its clubs or by neither."""
    games = [{"date": "2026-03-01", "home": "Arsenal", "away": "Liverpool",
              "result": None}]
    assert fast_refresh._match_game(
        games, _feed("Arsenal", "Everton"), set()) is None


def test_two_plausible_fixtures_on_one_day_are_both_refused():
    """No ambiguity guard existed: max() silently picked a winner. On a derby
    round both clubs of a confusable pair play on the same day."""
    games = [{"date": "2026-03-01", "home": "Manchester United", "away": "Rival",
              "result": None},
             {"date": "2026-03-01", "home": "Manchester City", "away": "Rival",
              "result": None}]
    assert fast_refresh._match_game(
        games, _feed("Manchester Utd", "Rival"), set()) is None


def test_the_same_two_clubs_twice_on_one_day_is_ambiguous():
    games = [{"date": "2026-03-01", "home": "Arsenal", "away": "Liverpool",
              "result": None},
             {"date": "2026-03-01", "home": "Arsenal", "away": "Liverpool",
              "result": None}]
    assert fast_refresh._match_game(
        games, _feed("Arsenal", "Liverpool"), set()) is None


def test_an_unmatched_completed_result_is_reported_not_swallowed():
    """Refusing is right; refusing silently is not. A league whose feed names
    drifted would otherwise just stop updating and still look healthy."""
    payload = _payload()
    report = apply_feed(payload, [{
        "date": "2026-07-26", "ko": "2026-07-26T19:30:00Z",
        "home": "Completely Different FC", "away": "Also Unrelated United",
        "completed": True, "hg": 3, "ag": 0,
    }], now=NOW, sims=200)

    assert report["results_applied"] == 0
    assert report["unmatched"] == ["2026-07-26 Completely Different FC v Also Unrelated United"]
    assert payload["standings"][0]["pts"] == 0, "no table movement from a refused row"
