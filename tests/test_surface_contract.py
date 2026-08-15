from __future__ import annotations

import json
import pathlib

import pytest

from scripts.send_personalized_briefings import _render
from server.intelligence_service import ArtifactNotFound, IntelligenceService
from server.surface_contract import club_surface_contract


ARSENAL_ID = "v1:1c90591709108353"
REPO = pathlib.Path(__file__).resolve().parent.parent


@pytest.fixture
def arsenal_record():
    """The committed contract, or a skip.

    Both tests below read a real artifact out of `data/team_intelligence/`,
    which is GITIGNORED — CI builds it, a fresh clone has none. Without this
    they fail with ArtifactNotFound on every developer machine and pass in CI,
    which is the failure mode that teaches people to ignore a red suite; the
    same asymmetry was fixed in test_static_pages.py on 2026-08-11 and missed
    here. Skipping keeps the contract enforced wherever the artifact exists
    and silent where it cannot.
    """
    path = (REPO / "data" / "team_intelligence" / "epl"
            / f"{ARSENAL_ID.replace(':', '_')}.json")
    if not path.exists():
        pytest.skip("data/team_intelligence/ not built (gitignored; CI builds it)")
    return IntelligenceService().get_team("epl", ARSENAL_ID)


def test_personalized_and_share_surfaces_use_the_canonical_club_contract(arsenal_record):
    service = IntelligenceService()
    record = arsenal_record
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


def test_artifact_identity_mismatch_fails_closed(tmp_path, arsenal_record):
    root = tmp_path / "artifacts" / "epl"
    root.mkdir(parents=True)
    source = dict(arsenal_record)
    source["team_id"] = "v1:wrong"
    path = root / f"{ARSENAL_ID.replace(':', '_')}.json"
    path.write_text(json.dumps(source))

    service = IntelligenceService(tmp_path / "artifacts")
    with pytest.raises(ArtifactNotFound, match="identity mismatch"):
        service.get_team("epl", ARSENAL_ID)
