from __future__ import annotations

import json

import pytest

from scripts.send_personalized_briefings import _render
from server.intelligence_service import ArtifactNotFound, IntelligenceService
from server.surface_contract import club_surface_contract


ARSENAL_ID = "v1:1c90591709108353"


def test_personalized_and_share_surfaces_use_the_canonical_club_contract():
    service = IntelligenceService()
    record = service.get_team("epl", ARSENAL_ID)
    contract = club_surface_contract(record)
    assert contract == {
        "league_id": "epl",
        "league_name": "Premier League",
        "team_id": ARSENAL_ID,
        "team": "Arsenal",
        "season_id": "2026",
        "generated": record["generated"],
        "snapshot_id": record["snapshot_id"],
        "target_metric": "title",
        "current_probability_pct": (
            record["features"]["1"]["data"]["current_pct"]),
    }

    card = service.public_card_payload(
        "epl", ARSENAL_ID, "highest_leverage")
    for key, value in contract.items():
        assert card[key] == value

    briefing = {
        "local_date": "2026-07-29",
        "teams": [{
            **contract,
            "briefing": {
                "sections": {
                    "team_pulse": {
                        "summary": "Arsenal remain in the title race.",
                    },
                },
            },
        }],
    }
    subject, html_body, text_body = _render(
        {"user_id": "user-1"}, briefing)
    assert subject == "Your Entenser Club Watch briefing"
    for value in (
        contract["team"], contract["generated"], contract["snapshot_id"],
    ):
        assert value in html_body
        assert value in text_body


def test_artifact_identity_mismatch_fails_closed(tmp_path):
    root = tmp_path / "artifacts" / "epl"
    root.mkdir(parents=True)
    source = IntelligenceService().get_team("epl", ARSENAL_ID)
    source["team_id"] = "v1:wrong"
    path = root / f"{ARSENAL_ID.replace(':', '_')}.json"
    path.write_text(json.dumps(source))

    service = IntelligenceService(tmp_path / "artifacts")
    with pytest.raises(ArtifactNotFound, match="identity mismatch"):
        service.get_team("epl", ARSENAL_ID)
