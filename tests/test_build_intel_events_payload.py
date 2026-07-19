from scripts.build_intel_events_payload import build_payload


def test_build_payload_keys_by_team_name():
    events_by_team_id = {"TID_A": [{"event_type": "result", "materiality_score": 0.5}]}
    standings = [{"team": "Nashville SC", "team_id": "TID_A"}]
    payload = build_payload(events_by_team_id, standings)
    assert payload["status"] == "ok"
    assert payload["teams"]["Nashville SC"] == events_by_team_id["TID_A"]


def test_build_payload_keeps_recognized_team_with_no_matching_event():
    events_by_team_id = {"TID_UNKNOWN": [{"event_type": "result"}]}
    standings = [{"team": "Nashville SC", "team_id": "TID_A"}]
    payload = build_payload(events_by_team_id, standings)
    assert payload["teams"] == {"Nashville SC": []}
    assert payload["status"] == "ok"


def test_build_payload_marks_known_team_as_thin_when_no_events():
    payload = build_payload({}, [{"team": "Nashville SC", "team_id": "TID_A"}])
    assert payload["status"] == "ok"
    assert payload["teams"] == {"Nashville SC": []}


def test_build_payload_preserves_event_fields_unchanged():
    event = {"event_id": "v1:abc", "event_type": "threshold_crossing", "delta_pp": 5.2}
    events_by_team_id = {"TID_A": [event]}
    standings = [{"team": "Alpha", "team_id": "TID_A"}]
    payload = build_payload(events_by_team_id, standings)
    assert payload["teams"]["Alpha"][0] == event
