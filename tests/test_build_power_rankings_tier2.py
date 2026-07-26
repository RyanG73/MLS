"""Tests for the one-ladder global power payload."""
from __future__ import annotations

from unittest import mock


def _fake_standings(league_id):
    return [{"team": f"TestTeam_{league_id}", "elo": 1550.0,
             "logo": None, "color": None}]


def _league(league_id, name, conf="UEFA", tier=1):
    return {"id": league_id, "name": name, "confederation": conf,
            "tier": tier, "women": False, "quality": "fitted",
            "n_teams": 1}


def test_rankings_use_composed_global_offset_for_second_tiers():
    from scripts import build_power_rankings as bpr
    from data_pipeline import coefficients as co

    leagues = [
        _league("bundesliga", "Bundesliga"),
        _league("bundesliga-2", "2. Bundesliga", tier=2),
    ]
    with mock.patch.object(bpr, "_load_standings", side_effect=_fake_standings):
        ranked = bpr._rank_leagues(leagues)
    by_league = {row["league"]: row for row in ranked}
    assert by_league["bundesliga-2"]["strength"] == round(
        1550 + co.global_elo_offset("bundesliga-2"), 1)
    assert by_league["bundesliga"]["strength"] == round(
        1550 + co.global_elo_offset("bundesliga"), 1)


def test_rankings_are_global_and_contiguous_across_confederations():
    from scripts import build_power_rankings as bpr

    leagues = [
        _league("epl", "Premier League"),
        _league("mls", "MLS", conf="Concacaf"),
        _league("brazil-serie-a", "Brasileirão", conf="CONMEBOL"),
    ]
    with mock.patch.object(bpr, "_load_standings", side_effect=_fake_standings):
        ranked = bpr._rank_leagues(leagues)
    assert [row["global_rank"] for row in ranked] == [1, 2, 3]
    assert [row["strength"] for row in ranked] == sorted(
        (row["strength"] for row in ranked), reverse=True)
    groups = bpr._groups(ranked)
    assert sum(group["n_teams"] for group in groups) == len(ranked)


def test_second_tier_row_keeps_tier_metadata():
    from scripts import build_power_rankings as bpr

    with mock.patch.object(bpr, "_load_standings", side_effect=_fake_standings):
        ranked = bpr._rank_leagues([
            _league("championship", "Championship", tier=2),
        ])
    assert ranked[0]["tier"] == 2
