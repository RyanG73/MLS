from scripts.payload_utils import make_fixture_id, make_snapshot_id


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
