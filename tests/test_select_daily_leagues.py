"""Which leagues the daily refresh rebuilds.

`refresh-daily.yml` selected leagues by payload `status == "live"`, so a league
wrongly published as complete was excluded from the ONLY job that recomputes
it. That is a latch, not a filter: on 2026-08-23 eight leagues were showing a
final table mid-season, and six of them had been stuck there since a single
dark-feed build on 08-17 — the daily job could not rebuild them, and the Monday
catch-all that could had itself run while ESPN was refusing our requests.

The rule added here is the inverse of the one the builder now applies: a league
that played recently is a league that might still be playing, whatever its
payload claims. Rebuilding it is cheap and self-correcting; not rebuilding it
means the wrong answer survives until someone notices.
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import pytest

from scripts.select_daily_leagues import select_leagues
from scripts.eval.season_state import MAX_IDLE_DAYS

TODAY = date(2026, 8, 23)


def _write(dirpath: Path, name: str, payload) -> None:
    (dirpath / f"{name}.js").write_text(
        f"window.DATA = {json.dumps(payload)};", encoding="utf-8")


def _payload(status: str, last_result_days_ago: int | None = 3) -> dict:
    games = []
    if last_result_days_ago is not None:
        played = TODAY - timedelta(days=last_result_days_ago)
        games.append({"home": "A", "away": "B", "result": "H",
                      "date": played.isoformat()})
    return {"status": status, "standings": [{"team": "A"}], "games": games}


def test_a_live_league_is_rebuilt(tmp_path):
    _write(tmp_path, "epl", _payload("live"))
    assert select_leagues(tmp_path, TODAY) == ["epl"]


def test_a_league_calling_itself_complete_but_still_playing_is_rebuilt(tmp_path):
    """The latch. Allsvenskan on 2026-08-17: `status: completed`, last match
    seven days earlier, 113 of 240 fixtures unplayed."""
    _write(tmp_path, "sweden-allsvenskan", _payload("completed", 7))
    assert select_leagues(tmp_path, TODAY) == ["sweden-allsvenskan"]


def test_a_season_that_really_ended_is_not_rebuilt(tmp_path):
    """The exclusion is still worth having — it is what keeps the matrix small.
    Every genuinely finished season measured on 2026-08-23 was idle >= 84 days."""
    _write(tmp_path, "japan-j1", _payload("completed", 84))
    assert select_leagues(tmp_path, TODAY) == []


def test_the_idle_boundary_is_inclusive_and_shared_with_the_builder(tmp_path):
    """One source for the window: the builder's guard and this filter must not
    disagree about what 'recently played' means."""
    _write(tmp_path, "on-edge", _payload("completed", MAX_IDLE_DAYS))
    _write(tmp_path, "past-edge", _payload("completed", MAX_IDLE_DAYS + 1))
    assert select_leagues(tmp_path, TODAY) == ["on-edge"]


def test_a_preseason_league_is_not_rebuilt(tmp_path):
    """Unchanged behaviour: the weekly rebuild owns the preseason flip."""
    _write(tmp_path, "bundesliga", _payload("preseason", None))
    assert select_leagues(tmp_path, TODAY) == []


def test_a_completed_league_with_no_dated_results_is_not_rebuilt(tmp_path):
    """No evidence it played recently is not evidence that it did."""
    _write(tmp_path, "mystery", _payload("completed", None))
    assert select_leagues(tmp_path, TODAY) == []


def test_cross_league_artifacts_are_not_leagues(tmp_path):
    """These carry their own `status` and would produce bogus matrix jobs like
    `build (edge-board)`."""
    for name in ("power", "edge-board", "movers", "ledger", "drift",
                 "logos", "model-slices", "coefficients", "match-leverage"):
        _write(tmp_path, name, _payload("live"))
    assert select_leagues(tmp_path, TODAY) == []


def test_a_data_file_that_is_not_a_payload_dict_is_skipped(tmp_path):
    """search-index.js is a JSON array; `.get` on it would crash the job."""
    (tmp_path / "search-index.js").write_text(
        'window.SEARCH = [{"id": "epl"}];', encoding="utf-8")
    _write(tmp_path, "epl", _payload("live"))
    assert select_leagues(tmp_path, TODAY) == ["epl"]


def test_the_result_is_sorted_and_json_serialisable(tmp_path):
    """The workflow feeds this straight into a matrix via `fromJson`."""
    _write(tmp_path, "zulu", _payload("live"))
    _write(tmp_path, "alpha", _payload("live"))
    picked = select_leagues(tmp_path, TODAY)
    assert picked == ["alpha", "zulu"]
    assert json.loads(json.dumps(picked)) == picked
