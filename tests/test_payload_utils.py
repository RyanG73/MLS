from scripts.payload_utils import make_event_id, make_fixture_id, make_snapshot_id


def test_make_fixture_id_deterministic():
    a = make_fixture_id("mls", 2026, "2026-07-20", "TID_HOME", "TID_AWAY")
    b = make_fixture_id("mls", 2026, "2026-07-20", "TID_HOME", "TID_AWAY")
    assert a == b


def test_make_fixture_id_differs_by_fixture():
    a = make_fixture_id("mls", 2026, "2026-07-20", "TID_HOME", "TID_AWAY")
    b = make_fixture_id("mls", 2026, "2026-07-20", "TID_AWAY", "TID_HOME")  # swapped venue
    c = make_fixture_id("mls", 2026, "2026-07-21", "TID_HOME", "TID_AWAY")  # different date
    d = make_fixture_id("epl", 2026, "2026-07-20", "TID_HOME", "TID_AWAY")  # different league
    assert len({a, b, c, d}) == 4


def test_make_fixture_id_is_versioned():
    fid = make_fixture_id("mls", 2026, "2026-07-20", "TID_HOME", "TID_AWAY")
    assert fid.startswith("v1:")


def test_make_snapshot_id_deterministic():
    a = make_snapshot_id("mls", 2026, "2026-07-18 12:00 UTC", "run-1", "v1")
    b = make_snapshot_id("mls", 2026, "2026-07-18 12:00 UTC", "run-1", "v1")
    assert a == b


def test_make_snapshot_id_differs_by_generated_timestamp():
    a = make_snapshot_id("mls", 2026, "2026-07-18 12:00 UTC", "run-1", "v1")
    b = make_snapshot_id("mls", 2026, "2026-07-19 12:00 UTC", "run-1", "v1")
    assert a != b


def test_make_snapshot_id_is_versioned():
    sid = make_snapshot_id("mls", 2026, "2026-07-18 12:00 UTC", "run-1", "v1")
    assert sid.startswith("v1:")


def test_make_event_id_deterministic():
    a = make_event_id("result", "TID_A", "playoff", "2026-07-18", ["fixture:v1:abc"])
    b = make_event_id("result", "TID_A", "playoff", "2026-07-18", ["fixture:v1:abc"])
    assert a == b


def test_make_event_id_order_independent_on_evidence_ids():
    a = make_event_id("result", "TID_A", "playoff", "2026-07-18", ["fixture:v1:a", "fixture:v1:b"])
    b = make_event_id("result", "TID_A", "playoff", "2026-07-18", ["fixture:v1:b", "fixture:v1:a"])
    assert a == b


def test_make_event_id_differs_by_team():
    a = make_event_id("result", "TID_A", "playoff", "2026-07-18", [])
    b = make_event_id("result", "TID_B", "playoff", "2026-07-18", [])
    assert a != b


def test_make_event_id_handles_none_team_for_league_scoped_events():
    eid = make_event_id("model_change", None, None, "2026-07-18", ["config:run-2"])
    assert eid.startswith("v1:")


def test_make_event_id_is_versioned():
    eid = make_event_id("result", "TID_A", "playoff", "2026-07-18", [])
    assert eid.startswith("v1:")
