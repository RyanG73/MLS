import pytest

from server.intel_store import (
    delete_user_data, export_user_data, get_or_create_user, get_plan,
    merge_client_state, set_plan, update_preferences,
)
from server.kv_store import InMemoryKVStore


def test_get_or_create_user_creates_default_record():
    kv = InMemoryKVStore()
    user = get_or_create_user(kv, "user-1", "a@example.com")
    assert user["user_id"] == "user-1" and user["email"] == "a@example.com"
    assert user["plan"] == "free"
    assert user["teams"] == [] and user["leagues"] == []
    assert user["notifications"] == {"weekly": True, "material_change": True}


def test_get_or_create_user_is_idempotent():
    kv = InMemoryKVStore()
    first = get_or_create_user(kv, "user-1", "a@example.com")
    set_plan(kv, "user-1", "intel")
    second = get_or_create_user(kv, "user-1", "a@example.com")
    assert second["plan"] == "intel"  # not reset back to the default record
    assert first["user_id"] == second["user_id"]


def test_update_preferences_merges_not_overwrites():
    kv = InMemoryKVStore()
    get_or_create_user(kv, "user-1", "a@example.com")
    update_preferences(kv, "user-1", threshold_pp=10)
    record = update_preferences(kv, "user-1", timezone="America/New_York")
    assert record["threshold_pp"] == 10          # earlier update preserved
    assert record["timezone"] == "America/New_York"


def test_update_preferences_missing_user_raises():
    kv = InMemoryKVStore()
    with pytest.raises(KeyError):
        update_preferences(kv, "nope", threshold_pp=10)


def test_set_and_get_plan_roundtrip():
    kv = InMemoryKVStore()
    get_or_create_user(kv, "user-1", "a@example.com")
    set_plan(kv, "user-1", "intel")
    assert get_plan(kv, "user-1") == "intel"


def test_get_plan_defaults_to_free_for_unknown_user():
    kv = InMemoryKVStore()
    assert get_plan(kv, "never-created") == "free"


def test_export_user_data_returns_full_record():
    kv = InMemoryKVStore()
    get_or_create_user(kv, "user-1", "a@example.com")
    exported = export_user_data(kv, "user-1")
    assert exported["email"] == "a@example.com"


def test_export_user_data_returns_none_for_missing_user():
    kv = InMemoryKVStore()
    assert export_user_data(kv, "nope") is None


def test_delete_user_data_removes_record():
    kv = InMemoryKVStore()
    get_or_create_user(kv, "user-1", "a@example.com")
    delete_user_data(kv, "user-1")
    assert export_user_data(kv, "user-1") is None


def test_merge_client_state_unions_leagues_and_teams_without_dropping_server_data():
    server_record = {
        "leagues": ["mls"],
        "teams": [{"team_id": "TID_A", "league_id": "mls"}],
    }
    merged = merge_client_state(server_record, fav_leagues=["epl"],
                                 fav_teams=[{"team_id": "TID_B", "league_id": "epl"}])
    assert set(merged["leagues"]) == {"mls", "epl"}
    team_ids = {t["team_id"] for t in merged["teams"]}
    assert team_ids == {"TID_A", "TID_B"}


def test_merge_client_state_does_not_duplicate_existing_team():
    server_record = {"leagues": ["mls"], "teams": [{"team_id": "TID_A", "league_id": "mls"}]}
    merged = merge_client_state(server_record, fav_leagues=[],
                                 fav_teams=[{"team_id": "TID_A", "league_id": "mls"}])
    assert len(merged["teams"]) == 1
