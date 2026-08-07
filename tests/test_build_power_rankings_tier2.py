"""Tests for the one-ladder global power payload."""
from __future__ import annotations

from unittest import mock


def _fake_standings(league_id):
    return [{"team": f"TestTeam_{league_id}", "elo": 1550.0,
             "logo": None, "color": None}]


def _league(league_id, name, conf="UEFA", tier=1, country="England", season=2026):
    # country and season carry the dedupe decision (_dedupe_clubs): same country
    # means one club listed twice and the newest season wins; different countries
    # mean two real clubs that both stay, disambiguated by country.
    return {"id": league_id, "name": name, "confederation": conf,
            "tier": tier, "women": False, "quality": "fitted",
            "country": country, "season": season, "n_teams": 1}


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


# ── Payload agreement (2026-08-01) ───────────────────────────────────────────
# The published rankings drifted from the league payloads once: the UEFA
# coefficient refit landed in coefficients.py and was reapplied to
# webapp/data/*.js via apply_global_elo_payloads.py, but nothing rebuilt
# webapp/data/power.js. Production served Bodo/Glimt 4th and Zenit 5th for a
# day while the league payloads already had them at 39th and 57th — two
# sources for the same number, disagreeing in public.

def test_power_payload_agrees_with_the_league_payloads():
    """power.js `strength` must equal the league payload's `global_elo`.

    Both are elo + global_elo_offset(league); they can only disagree when one
    of the two has been rebuilt and the other has not.
    """
    import json
    from pathlib import Path

    repo = Path(__file__).resolve().parents[1]
    data = repo / "webapp" / "data"
    power_path = data / "power.js"
    if not power_path.exists():
        import pytest
        pytest.skip("power.js not built in this checkout")

    def read(p):
        t = p.read_text()
        return json.loads(t[t.index("=") + 1:].rstrip().rstrip(";"))

    power = read(power_path)
    rows = power.get("teams") or power.get("clubs") or power.get("rows") or []
    assert rows, "power.js has no rows"

    by_league: dict[str, dict[str, int]] = {}
    mismatches = []
    checked = 0
    for r in rows:
        lid = r.get("league")
        if lid not in by_league:
            p = data / f"{lid}.js"
            if not p.exists():
                by_league[lid] = {}
            else:
                payload = read(p)
                by_league[lid] = {
                    s["team"]: s["global_elo"]
                    for s in (payload.get("standings") or [])
                    if s.get("global_elo") is not None and s.get("team")
                }
        expected = by_league[lid].get(r.get("team"))
        if expected is None:
            continue
        checked += 1
        if abs(round(float(r["strength"])) - int(expected)) > 1:
            mismatches.append(
                f"{r['team']} ({lid}): power.js {r['strength']} vs payload {expected}")

    assert checked > 100, f"only cross-checked {checked} clubs"
    assert not mismatches, (
        f"{len(mismatches)} clubs disagree between power.js and their league "
        f"payload — one of the two is stale. First five: {mismatches[:5]}")
