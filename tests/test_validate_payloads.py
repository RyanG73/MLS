import json

from scripts.validate_payloads import validate_file


def _mls_payload(**overrides):
    base = {
        "status": "live",
        "league": {"id": "mls", "name": "MLS", "status": "live"},
        "generated": "2026-07-18 12:00 UTC",
        "standings": [{"team": "Alpha", "team_id": "TID_A"}],
        "games": [{"home": "Alpha", "away": "Beta", "home_id": "TID_A",
                   "away_id": "TID_B", "fixture_id": "v1:abc123"}],
        "health": {},
    }
    base.update(overrides)
    return base


def _write(tmp_path, payload):
    p = tmp_path / "mls.js"
    p.write_text(f"window.LEAGUE_DATA = {json.dumps(payload)};")
    return p


def test_mls_payload_with_ids_has_no_id_errors(tmp_path):
    errors = validate_file(_write(tmp_path, _mls_payload()))
    assert not any("team_id" in e or "fixture_id" in e or "home_id" in e for e in errors)


def test_mls_payload_missing_team_id_flagged(tmp_path):
    payload = _mls_payload()
    del payload["standings"][0]["team_id"]
    errors = validate_file(_write(tmp_path, payload))
    assert any("team_id" in e for e in errors)


def test_mls_payload_missing_fixture_id_flagged(tmp_path):
    payload = _mls_payload()
    del payload["games"][0]["fixture_id"]
    errors = validate_file(_write(tmp_path, payload))
    assert any("fixture_id" in e for e in errors)


def test_non_mls_league_not_checked_for_ids(tmp_path):
    payload = _mls_payload(league={"id": "epl", "name": "EPL", "status": "live"})
    del payload["standings"][0]["team_id"]
    errors = validate_file(_write(tmp_path, payload))
    assert not any("team_id" in e for e in errors)
