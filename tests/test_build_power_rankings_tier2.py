"""Tests for tier-2 group in build_power_rankings."""
from __future__ import annotations
from pathlib import Path
from unittest import mock
import json


def _fake_standings(league_id):
    """Fake _load_standings that returns a single team for each league."""
    return [{"team": f"TestTeam_{league_id}", "elo": 1550.0, "logo": None, "color": None}]


def test_build_power_rankings_includes_tier2_group():
    """build() produces a 'UEFA Tier 2' group with tier-2 leagues."""
    from scripts import build_power_rankings as bpr
    from pathlib import Path

    with mock.patch.object(bpr, "_load_standings", side_effect=_fake_standings), \
         mock.patch.object(bpr, "write_js_payload") as mock_write:
        # Mock the Path.stat() call to avoid FileNotFoundError
        with mock.patch.object(Path, "stat", return_value=mock.MagicMock(st_size=1024)):
            bpr.build()

    assert mock_write.called
    payload = mock_write.call_args[0][2]  # third positional arg is the data dict
    confs = [g["confederation"] for g in payload["groups"]]
    assert "UEFA Tier 2" in confs


def test_tier2_group_teams_have_tier_field():
    """Teams in the UEFA Tier 2 group have tier=2 in their entry."""
    from scripts import build_power_rankings as bpr

    with mock.patch.object(bpr, "_load_standings", side_effect=_fake_standings):
        ranked = bpr._rank_group(bpr._TIER2_LEAGUES, tier=2)
    assert all(r["tier"] == 2 for r in ranked)


def test_tier1_group_teams_have_tier_1():
    """Existing UEFA tier-1 teams still have tier=1 (default)."""
    from scripts import build_power_rankings as bpr

    with mock.patch.object(bpr, "_load_standings", side_effect=_fake_standings):
        ranked = bpr._rank_group(bpr._GROUPS["UEFA"])
    assert all(r.get("tier", 1) == 1 for r in ranked)
