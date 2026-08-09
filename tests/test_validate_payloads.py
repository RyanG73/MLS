import json

import pytest

from scripts.payload_utils import apply_global_elo_scale
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


# --- Global ELO reconciliation -------------------------------------------
# The published global_elo must be reproducible from the payload's OWN
# elo_scale metadata, because that is exactly what the browser does
# (webapp/index.html scaledElo/publishedElo). The transformation stopped
# being a pure shift on 2026-08-07: lower divisions also compress their
# spread about the league mean, and clubs with continental history carry a
# per-row adjustment.

def _scaled_payload(rows, scale, league_id="epl"):
    return _mls_payload(
        league={"id": league_id, "name": league_id, "status": "live"},
        outlook={"mode": "table"},
        standings=rows,
        games=[],
        elo_scale=scale,
    )


def _elo_errors(tmp_path, payload):
    return [e for e in validate_file(_write(tmp_path, payload)) if "global_elo" in e]


def test_second_tier_dispersion_reconciles(tmp_path):
    # Hannover 96 as published in bundesliga-2.js on 2026-08-08:
    # 1503 + 0.723*(1597-1503) - 186.964 = 1383.998 -> 1384
    payload = _scaled_payload(
        [{"team": "Hannover 96", "elo": 1597, "global_elo": 1384}],
        {"offset": -186.964, "dispersion": 0.723, "pivot": 1503.0},
        league_id="bundesliga-2",
    )
    assert _elo_errors(tmp_path, payload) == []


def test_continental_adjustment_reconciles(tmp_path):
    # A top flight is a pure shift EXCEPT for clubs carrying global_elo_adj.
    payload = _scaled_payload(
        [{"team": "Chelsea", "elo": 1547, "global_elo": 1610,
          "global_elo_adj": 62.5}],
        {"offset": 0.0, "dispersion": 1.0, "pivot": 1500.0},
    )
    assert _elo_errors(tmp_path, payload) == []


def test_desynced_global_elo_still_flagged(tmp_path):
    # The check must keep catching a real divergence -- the 2026-08-07
    # power-ladder bug put a club ~45 points off its own league page.
    payload = _scaled_payload(
        [{"team": "Burnley", "elo": 1597, "global_elo": 1429}],
        {"offset": -186.964, "dispersion": 0.723, "pivot": 1503.0},
        league_id="championship",
    )
    assert _elo_errors(tmp_path, payload)


def test_missing_dispersion_degrades_to_shift_only(tmp_path):
    # Older payloads predate dispersion/pivot; the browser defaults them to
    # the inert 1.0/0.0, and so must the validator.
    payload = _scaled_payload(
        [{"team": "Alpha", "elo": 1500, "global_elo": 1450}],
        {"offset": -50.0},
    )
    assert _elo_errors(tmp_path, payload) == []


# The producer (apply_global_elo_scale) and the checker above implement the
# same translation twice, on purpose — a checker that called the producer
# would pass tautologically. The cost of that independence is that they can
# drift, and on 2026-08-07 they did: f4994158 added dispersion and
# global_elo_adj to the producer, taught every consumer, missed the checker,
# and the next nightly refresh died at `validate_payloads.py` with 26 of 79
# payloads "failing" arithmetic no surface used any more. Everything after it
# in that workflow step — validate_history_growth through
# validate_intelligence_launch — was skipped with it.
#
# This is the test that binds them: run the REAL producer, then assert the
# checker accepts what it wrote.
@pytest.mark.parametrize("league_id", ["epl", "bundesliga-2", "championship"])
def test_producer_output_satisfies_the_checker(tmp_path, league_id):
    payload = _mls_payload(
        league={"id": league_id, "name": league_id, "status": "live"},
        outlook={"mode": "table"},
        standings=[{"team": name, "elo": elo} for name, elo in [
            ("Liverpool", 1620), ("Chelsea", 1547), ("Alpha FC", 1500),
            ("Beta United", 1455), ("Gamma City", 1390),
        ]],
        games=[],
    )
    apply_global_elo_scale(payload, league_id)
    assert _elo_errors(tmp_path, payload) == []
