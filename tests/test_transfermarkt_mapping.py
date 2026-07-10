"""A9 mapping coverage: TM team names must resolve to the dashboard's canonical
payload names (the strings build_league_data.py keys team_inputs on).

Two layers:
1. Unit tests on canonical_team_name()'s resolution tiers (synthetic lists —
   no network, no payload dependency).
2. The plan's coverage gate: every team in the current EPL payload resolves to
   a row in the freshest GB1 mapped CSV. Skipped (not failed) when no GB1 CSV
   exists yet, so a fresh checkout without local TM data still has a green suite.
"""
import json
import re
from pathlib import Path

import pandas as pd
import pytest

from scripts.import_transfermarkt import canonical_team_name

REPO = Path(__file__).resolve().parents[1]


def _payload_teams(lid: str) -> list[str]:
    p = REPO / "webapp" / "data" / f"{lid}.js"
    text = re.sub(r"^[\s\S]*?=\s*", "", p.read_text(encoding="utf-8")).rstrip().rstrip(";")
    return sorted((json.loads(text).get("team_inputs") or {}).keys())


# ── Tier unit tests (synthetic canonical lists; league_id irrelevant when the
#    list is passed explicitly) ──────────────────────────────────────────────

def test_exact_match_wins():
    canon = ["Tottenham", "Arsenal"]
    assert canonical_team_name("Tottenham", "epl", canon) == "Tottenham"


def test_alias_overrides_resolve_stubborn_names():
    assert canonical_team_name("Inter Milan", "serie-a", ["Inter", "AC Milan"]) == "Inter"
    assert canonical_team_name("Atlas Guadalajara", "liga-mx",
                               ["Atlas", "Guadalajara"]) == "Atlas"


def test_token_subset_resolves_long_tm_names():
    canon = ["Tottenham", "Brighton", "Manchester United", "Manchester City"]
    assert canonical_team_name("Tottenham Hotspur", "epl", canon) == "Tottenham"
    # club-type tokens (FC/AFC) are stripped before the subset check
    assert canonical_team_name("Celta de Vigo", "la-liga",
                               ["Celta Vigo", "Sevilla"]) == "Celta Vigo"


def test_ambiguous_subset_refuses_to_guess():
    # "Alpha Beta FC" subset-matches both candidates → must return None, never guess
    assert canonical_team_name("Alpha Beta FC", "epl", ["Alpha", "Beta"]) is None


def test_unknown_team_returns_none():
    assert canonical_team_name("Nonexistent Rovers", "epl", ["Arsenal"]) is None


def test_empty_canonical_list_returns_none():
    # e.g. canadian-pl: no live payload yet → no canonical names to resolve against
    assert canonical_team_name("Forge FC", "canadian-pl", []) is None


# ── Coverage gate (the plan's A9 test requirement) ──────────────────────────

def test_every_epl_payload_team_has_tm_row():
    files = sorted((REPO / "data").glob("transfermarkt_squad_values_GB1_*_mapped.csv"))
    if not files:
        pytest.skip("no GB1 mapped CSV on disk (TM import not run)")
    latest = files[-1]  # lexicographic == chronological for GB1_<season>
    canon = set(pd.read_csv(latest)["canon_team_name"].fillna(""))
    teams = _payload_teams("epl")
    missing = [t for t in teams if t not in canon]
    assert not missing, (
        f"EPL payload teams with no TM row in {latest.name}: {missing} — "
        f"either the TM season snapshot lags the payload roster (re-fetch the "
        f"current season) or canonical_team_name() needs an alias")


# ── _aggregate_team(): four-way (ATT/MID/DEF/GK) value-percentage split ─────

from scripts.import_transfermarkt import _aggregate_team


def _players(rows):
    """rows: list of (name, position, value_eur, age)."""
    return pd.DataFrame(rows, columns=["player_name", "position", "market_value_eur", "age"])


def test_aggregate_team_emits_four_way_split():
    players = _players([
        ("GK1", "Goalkeeper", 10_000_000, 25),
        ("DEF1", "Centre-Back", 20_000_000, 24),
        ("MID1", "Central Midfield", 30_000_000, 26),
        ("ATT1", "Striker", 40_000_000, 22),
    ])
    feats = _aggregate_team(players)
    assert feats["att_value_pct"] == pytest.approx(0.4)
    assert feats["def_value_pct"] == pytest.approx(0.2)
    assert feats["mid_value_pct"] == pytest.approx(0.3)
    assert feats["gk_value_pct"] == pytest.approx(0.1)
    assert feats["n_mid"] == 1
    # the four percentages must sum to 1.0 (no player's value silently dropped)
    total_pct = feats["att_value_pct"] + feats["def_value_pct"] + feats["mid_value_pct"] + feats["gk_value_pct"]
    assert total_pct == pytest.approx(1.0)


def test_aggregate_team_zero_value_branch_still_has_four_way_keys():
    players = _players([("P1", "Central Midfield", 0, 24)])
    feats = _aggregate_team(players, keep_if_zero_value=True)
    assert feats["n_mid"] == 1
    import math
    assert math.isnan(feats["mid_value_pct"])
    assert math.isnan(feats["gk_value_pct"])


# ── top15_value_eur (R1, 2026-07-09): position-constrained best-XI+bench sum ──

def test_top15_excludes_unplayable_striker_depth():
    """16 strikers can't all play: only the 4 most valuable ATT count, while a
    full complement of GK/DEF/MID does."""
    rows = [("GK1", "Goalkeeper", 5_000_000, 25)]
    rows += [(f"D{i}", "Centre-Back", 4_000_000, 25) for i in range(5)]
    rows += [(f"M{i}", "Central Midfield", 4_000_000, 25) for i in range(5)]
    rows += [(f"A{i}", "Striker", 10_000_000, 25) for i in range(4)]
    rows += [("A_extra", "Striker", 9_000_000, 25)]      # 5th striker: excluded
    feats = _aggregate_team(_players(rows))
    # 5m + 5*4m + 5*4m + 4*10m = 85m; the 9m fifth striker must NOT count
    assert feats["top15_value_eur"] == pytest.approx(85_000_000)
    assert feats["squad_value_eur"] == pytest.approx(94_000_000)


def test_top15_backfills_short_defense_from_best_remaining():
    """Only 2 DEF on the books → the 3 missing slots go to the next most
    valuable players regardless of position (positional flexibility)."""
    rows = [("GK1", "Goalkeeper", 5_000_000, 25),
            ("D1", "Centre-Back", 4_000_000, 25),
            ("D2", "Right-Back", 4_000_000, 25)]
    rows += [(f"M{i}", "Central Midfield", 6_000_000, 25) for i in range(5)]
    rows += [(f"A{i}", "Striker", 8_000_000, 25) for i in range(7)]
    feats = _aggregate_team(_players(rows))
    # quota picks: 1 GK (5m) + 2 DEF (8m) + 5 MID (30m) + 4 ATT (32m) = 75m
    # backfill 3 slots from the remaining 3 strikers (8m each) = +24m → 99m
    assert feats["top15_value_eur"] == pytest.approx(99_000_000)


def test_top15_equals_total_for_small_squads():
    rows = [("GK1", "Goalkeeper", 5_000_000, 25),
            ("M1", "Central Midfield", 6_000_000, 25),
            ("A1", "Striker", 8_000_000, 25)]
    feats = _aggregate_team(_players(rows))
    assert feats["top15_value_eur"] == pytest.approx(feats["squad_value_eur"])


def test_top15_zero_value_branch_key_present():
    feats = _aggregate_team(_players([("P1", "Striker", 0, 24)]),
                            keep_if_zero_value=True)
    assert feats["top15_value_eur"] == 0.0
