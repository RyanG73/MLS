"""League-map ids verified by team-name overlap, not by string similarity.

On 2026-08-08 the map draft scored our display name "LaLiga 2" closer to
"La Liga" than to "Segunda Division" and mapped segunda to Spain's TOP flight
with "high" confidence. The error was invisible to every check that compared
names, and only surfaced when the xG join put Real Madrid and Barcelona into a
second-division frame. These ids are pinned because each was confirmed against
the clubs actually appearing in that league's fixtures.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

MAP = Path("config/api_football_league_map.json")

VERIFIED = {
    "championship": 40, "eredivisie": 88, "segunda": 141, "super-lig": 203,
    "primeira": 94, "belgian-pro": 144, "brazil-serie-a": 71,
    "canadian-pl": 479, "k-league-1": 292, "northern-super-league": 1182,
    "usl-super-league": 1130,
}


@pytest.mark.parametrize("league_id,af_id", sorted(VERIFIED.items()))
def test_verified_league_ids_are_unchanged(league_id, af_id):
    entry = json.loads(MAP.read_text())[league_id]
    assert entry["af_id"] == af_id, (
        f"{league_id} maps to {entry['af_id']} ({entry.get('af_name')}), "
        f"expected {af_id}. Verify against the clubs in that league's fixtures "
        f"before changing this — a name-similarity match is not evidence.")


def test_segunda_is_the_second_tier_not_la_liga():
    entry = json.loads(MAP.read_text())["segunda"]
    assert entry["af_id"] != 140, "segunda must not map to La Liga (140)"
    assert "segunda" in (entry.get("af_name") or "").lower()
