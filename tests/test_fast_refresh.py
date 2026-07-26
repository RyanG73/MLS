from __future__ import annotations

import copy
import datetime as dt
import json

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
