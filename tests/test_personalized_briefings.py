from __future__ import annotations

import datetime as dt

import pytest

import scripts.build_personalized_briefing as briefing_builder
from scripts.intelligence.builder import _prematch_stakes
from scripts.send_personalized_briefings import _cadence_allows, _render
from server.intel_store import get_or_create_user, update_preferences
from server.kv_client import get_kv, reset_kv_for_tests
from server.kv_store import InMemoryKVStore


@pytest.fixture(autouse=True)
def _fresh_kv():
    reset_kv_for_tests()
    yield
    reset_kv_for_tests()


def _stake(date="2026-08-21"):
    return {
        "fixture_id": "v1:fixture",
        "date": date,
        "delivery_date": date,
        "home": "Arsenal",
        "away": "Coventry City",
        "target_metric": "title",
        "target_label": "title",
        "baseline_pct": 32.0,
        "outcomes": [
            {"code": "H", "label": "Win", "pct": 36.5, "delta_pp": 4.5},
            {"code": "D", "label": "Draw", "pct": 31.0, "delta_pp": -1.0},
            {"code": "A", "label": "Loss", "pct": 25.0, "delta_pp": -7.0},
        ],
        "evidence_ids": ["fixture:v1:fixture", "snapshot:v1:snapshot"],
    }


def _record(stake):
    return {
        "league_id": "epl",
        "league_name": "Premier League",
        "team_id": "v1:arsenal",
        "team": "Arsenal",
        "season_id": "2026",
        "generated": "2026-08-21 08:00 UTC",
        "snapshot_id": "v1:snapshot",
        "target_metric": "title",
        "calendar_mode": {"mode": "active_matchweek"},
        "features": {
            "1": {"data": {"current_pct": 32.0}},
            "2": {"data": {"events": []}},
            "8": {"data": {"sections": {
                "team_pulse": {
                    "summary": "Title is 32.0%.",
                    "snapshot_id": "v1:snapshot",
                },
                "prematch_stakes": stake,
            }}},
        },
    }


def test_prematch_stakes_uses_next_own_fixture_and_team_perspective():
    card = _prematch_stakes([
        {
            "fixture_id": "later", "date": "2026-09-01",
            "home_id": "v1:arsenal", "away_id": "v1:city",
            "home": "Arsenal", "away": "Manchester City",
            "is_own_fixture": True, "baseline_pct": 30,
            "conditional_pct": {"H": 40, "D": 29, "A": 20},
        },
        {
            "fixture_id": "next", "date": "2026-08-21",
            "home_id": "v1:coventry", "away_id": "v1:arsenal",
            "home": "Coventry City", "away": "Arsenal",
            "is_own_fixture": True, "baseline_pct": 30,
            "conditional_pct": {"H": 23, "D": 29, "A": 35},
            "evidence_ids": ["fixture:next"],
        },
    ], "v1:arsenal", "Arsenal", "title")

    assert card["fixture_id"] == "next"
    assert card["opponent"] == "Coventry City"
    assert [row["label"] for row in card["outcomes"]] == [
        "Loss", "Draw", "Win"]
    assert [row["delta_pp"] for row in card["outcomes"]] == [-7.0, -1.0, 5.0]


def test_matchday_stake_is_due_only_in_users_local_morning(monkeypatch):
    kv = get_kv()
    get_or_create_user(kv, "user-1", "user@example.test")
    update_preferences(
        kv, "user-1", timezone="America/New_York",
        teams=[{"league_id": "epl", "team_id": "v1:arsenal"}])

    class FakeService:
        @staticmethod
        def get_team(_league_id, _team_id):
            return _record(_stake())

    monkeypatch.setattr(briefing_builder, "IntelligenceService", FakeService)
    morning = briefing_builder.build_user_briefing(
        "user-1", now=dt.datetime(
            2026, 8, 21, 12, 30, tzinfo=dt.timezone.utc))
    before_window = briefing_builder.build_user_briefing(
        "user-1", now=dt.datetime(
            2026, 8, 21, 9, 30, tzinfo=dt.timezone.utc))

    assert morning["local_hour"] == 8
    assert morning["prematch_due"] is True
    assert morning["due_fixture_ids"] == ["v1:fixture"]
    assert morning["should_send"] is True
    assert before_window["should_send"] is False
    assert before_window["skip_reason"] == "outside local morning delivery window"


def test_matchday_uses_subscribers_local_fixture_date(monkeypatch):
    kv = get_kv()
    get_or_create_user(kv, "user-1", "user@example.test")
    update_preferences(
        kv, "user-1", timezone="Asia/Tokyo",
        teams=[{"league_id": "epl", "team_id": "v1:arsenal"}])

    stake = _stake("2026-08-21")
    stake["ko"] = "2026-08-21T23:30:00Z"

    class FakeService:
        @staticmethod
        def get_team(_league_id, _team_id):
            return _record(stake)

    monkeypatch.setattr(briefing_builder, "IntelligenceService", FakeService)
    result = briefing_builder.build_user_briefing(
        "user-1", now=dt.datetime(
            2026, 8, 21, 22, 30, tzinfo=dt.timezone.utc))

    assert result["local_date"] == "2026-08-22"
    assert result["teams"][0]["briefing"]["sections"][
        "prematch_stakes"]["delivery_date"] == "2026-08-22"
    assert result["prematch_due"] is True
    assert result["should_send"] is True


def test_matchday_stake_bypasses_weekly_cadence_and_renders_outcomes():
    kv = InMemoryKVStore()
    kv.set("briefing:last:user-1", (
        '{"sent_at":"2026-08-20T12:00:00+00:00","modes":["active_matchweek"]}'))
    assert not _cadence_allows(kv, "user-1", {"active_matchweek"})
    assert _cadence_allows(
        kv, "user-1", {"active_matchweek"}, prematch_due=True)

    briefing = {
        "local_date": "2026-08-21",
        "teams": [{
            **{
                key: value for key, value in _record(_stake()).items()
                if key != "features"
            },
            "briefing": {"sections": {
                "team_pulse": {"summary": "Title is 32.0%."},
                "prematch_stakes": _stake(),
            }},
        }],
    }
    subject, html_body, text_body = _render(
        {"user_id": "user-1"}, briefing)
    assert subject == "Your Entenser Club Watch briefing"
    assert "Forecast as of 2026-08-21 08:00 UTC" in html_body
    assert "Snapshot v1:snapshot" in text_body
    assert "What’s at stake: Arsenal vs Coventry City" in html_body
    assert "Win:</strong> 36.5% (+4.5pp)" in html_body
    assert "Loss: 25.0% (-7.0pp)" in text_body
