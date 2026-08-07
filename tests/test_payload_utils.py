import pytest

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


# ── Season / field regression guard (2026-08-07) ──────────────────────────────
# Written after a local refresh regressed 38 payloads to the prior season while
# every 2026 upstream source returned 404/403. build_league_data catches its own
# network errors, falls back to the last completed season, writes a payload with
# a fresh `generated` timestamp and exits 0 — so nothing downstream could tell.
# The Spanish second tier came back holding ten Scottish clubs.

class TestPayloadRegressionGuard:
    @staticmethod
    def _payload(season=2026, teams=("A", "B", "C", "D", "E", "F", "G", "H")):
        return {"league": {"id": "testleague"}, "season": season,
                "standings": [{"team": t, "elo": 1500} for t in teams]}

    def _write(self, path, data):
        from scripts.payload_utils import write_js_payload
        write_js_payload(path, "LEAGUE_DATA", data)

    def test_refuses_a_season_that_goes_backwards(self, tmp_path):
        from scripts.payload_utils import PayloadRegression
        p = tmp_path / "testleague.js"
        self._write(p, self._payload(season=2026))
        with pytest.raises(PayloadRegression, match="season 2025 over 2026"):
            self._write(p, self._payload(season=2025))
        # the good payload is still on disk — a refused write must not truncate
        from scripts.payload_utils import read_js_payload
        assert read_js_payload(p)["season"] == 2026

    def test_refuses_a_wholesale_change_of_field(self, tmp_path):
        from scripts.payload_utils import PayloadRegression
        p = tmp_path / "testleague.js"
        self._write(p, self._payload())
        with pytest.raises(PayloadRegression, match="of the field changed"):
            self._write(p, self._payload(teams=("Q", "R", "S", "T", "U", "V", "W", "X")))

    def test_allows_a_normal_promotion_relegation_rollover(self, tmp_path):
        p = tmp_path / "testleague.js"
        self._write(p, self._payload(season=2026))
        # three of eight clubs replaced — more churn than a real 20-team league
        self._write(p, self._payload(
            season=2027, teams=("A", "B", "C", "D", "E", "X", "Y", "Z")))
        from scripts.payload_utils import read_js_payload
        assert read_js_payload(p)["season"] == 2027

    def test_first_write_is_never_blocked(self, tmp_path):
        p = tmp_path / "brandnew.js"
        self._write(p, self._payload())
        assert p.exists()

    def test_escape_hatch_allows_a_deliberate_rebaseline(self, tmp_path, monkeypatch):
        p = tmp_path / "testleague.js"
        self._write(p, self._payload(season=2026))
        monkeypatch.setenv("ENTENSER_ALLOW_PAYLOAD_REGRESSION", "1")
        self._write(p, self._payload(season=2025))
        from scripts.payload_utils import read_js_payload
        assert read_js_payload(p)["season"] == 2025

    def test_non_league_payloads_are_untouched(self, tmp_path):
        """power.js and friends have no standings — the guard must ignore them."""
        p = tmp_path / "power.js"
        from scripts.payload_utils import write_js_payload
        write_js_payload(p, "POWER_DATA", {"teams": [{"team": "A"}]})
        write_js_payload(p, "POWER_DATA", {"teams": [{"team": "Z"}]})
        from scripts.payload_utils import read_js_payload
        assert read_js_payload(p)["teams"][0]["team"] == "Z"
