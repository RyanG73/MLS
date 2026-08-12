"""Join backfilled API-Football statistics onto the canonical frame as xG.

Spec: docs/superpowers/specs/2026-08-08-api-football-migration-execution-spec.md
(Stage 4). The Stage-4 backfill stores one stat sheet per API-Football fixture
id, but a canonical frame built from football-data or ESPN carries no such id.
The join therefore runs through the backfill's own fixture inventories, which
already map (af_id, season) -> fixtures -> team ids and names.

Three properties the tests pin, each guarding a way this could be silently
wrong rather than loudly broken:

- **Assign by team id, never by sheet order.** The stat sheet lists its two
  teams in the provider's order, which is not always home-first; positional
  assignment would swap home and away xG and look entirely plausible.
- **Usable means BOTH teams carry a non-null value.** API-Football emits
  `expected_goals` with a null value about half the time. Counting the field's
  presence overstated coverage 2x on 2026-08-08 (92.1% reported vs 43.9%
  real) — a rolling window needs the number, not the key.
- **Never overwrite an existing value.** understat and ASA own xG for their
  leagues (Tier C); the spine fills gaps, it does not adjudicate.

`coverage(league_id)` is the per-league gate the feature campaign reads: only
7 competitions clear 90% (championship, brazil-serie-a, segunda, super-lig,
eredivisie, primeira, belgian-pro), so "the backfill ran" is not evidence that
a given league can use xG.
"""
from __future__ import annotations

import functools
import json
import re
import unicodedata
from pathlib import Path

import numpy as np
import pandas as pd

STORE = Path("data/api_football/statistics")
FIXTURES_CACHE = Path("data/api_football/backfill_fixtures")
MAP_PATH = Path("config/api_football_league_map.json")
# Our canonical (ESPN/football-data) name -> API-Football name. This is the
# INVERSE direction of api_football._NAMES_PATH, which maps the other way for
# frames the spine itself produces.
NAMES_PATH = Path("config/api_football_xg_names.json")

_FINISHED = {"FT", "AET", "PEN"}


@functools.lru_cache(maxsize=1)
def _team_names() -> dict[str, dict[str, str]]:
    try:
        return json.loads(NAMES_PATH.read_text())
    except FileNotFoundError:
        return {}


def _norm(name: str) -> str:
    s = unicodedata.normalize("NFD", str(name))
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def _af_id(league_id: str) -> int | None:
    try:
        entry = json.loads(MAP_PATH.read_text()).get(league_id) or {}
    except FileNotFoundError:
        return None
    return entry.get("af_id")


def _sheet_xg(fixture_id: int) -> dict[int, float]:
    """{team_id: xg} for one fixture; empty when the sheet is missing, empty,
    or carries the field with a null value."""
    path = STORE / f"{fixture_id}.json"
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return {}
    out: dict[int, float] = {}
    for side in payload.get("response") or []:
        team_id = (side.get("team") or {}).get("id")
        value = next((s.get("value") for s in side.get("statistics") or []
                      if s.get("type") == "expected_goals"), None)
        if team_id is None or value is None:
            continue
        try:
            out[int(team_id)] = float(value)
        except (TypeError, ValueError):
            continue
    return out


def _inventories(league_id: str):
    af_id = _af_id(league_id)
    if af_id is None:
        return
    for path in sorted(FIXTURES_CACHE.glob(f"{af_id}_*.json")):
        try:
            yield json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            continue


def xg_rows(league_id: str) -> list[dict]:
    """Matches with usable xG, in API-Football's team-name space."""
    rows = []
    for inventory in _inventories(league_id):
        for event in inventory.get("response") or []:
            fixture = event.get("fixture") or {}
            if (fixture.get("status") or {}).get("short") not in _FINISHED:
                continue
            teams = event.get("teams") or {}
            home, away = teams.get("home") or {}, teams.get("away") or {}
            xg = _sheet_xg(fixture.get("id"))
            if home.get("id") not in xg or away.get("id") not in xg:
                continue                       # usable = BOTH sides, non-null
            rows.append({
                "season": int((event.get("league") or {}).get("season")),
                "home_team": home.get("name"), "away_team": away.get("name"),
                "home_xg": xg[home["id"]], "away_xg": xg[away["id"]],
            })
    return rows


def coverage(league_id: str) -> dict:
    """Finished fixtures vs those with usable xG — the per-league gate."""
    total = 0
    for inventory in _inventories(league_id):
        total += sum(1 for e in inventory.get("response") or []
                     if ((e.get("fixture") or {}).get("status") or {}
                         ).get("short") in _FINISHED)
    usable = len(xg_rows(league_id))
    return {"league": league_id, "fixtures": total, "usable": usable,
            "share": (usable / total) if total else 0.0}


# ── campaign verdicts (spec 2026-08-09 §4.1/§4.2) — WIRED for the KEEPs ──────
# Measured by scripts/xg_feature_campaign.py, two seeds at n_bags=5, the only
# variable being whether xG carries values. Brier is sum-form, so a NEGATIVE
# delta is an improvement.
#
# Two windows, both kept, because they answer different questions. The
# 2022-2025 folds DILUTE every delta ~25%: xG begins in 2023, so the first fold
# is identical in both arms. The 2023-2025 re-run (§4.2) sizes the effect
# honestly, and it is the one these verdicts are drawn from. Owner authorised
# the port on 2026-08-09 (spec §9.1).
#
# `super-lig` is the one league the re-run was meant to decide, and it decided
# AGAINST promotion. Its mean (-0.0012) clears the -0.0010 bar, but its seeds
# span -0.0020 to -0.0004 — the second seed is indistinguishable from zero, and
# every league that IS wired clears the bar on both seeds independently. The
# verification protocol asks a second seed to CONFIRM a gate-bound claim, and
# seed 7 does not confirm this one. Left marginal, with the numbers here so
# promoting it later is a decision rather than a rediscovery.
#
# The Brasileirão REJECTION is the one thing that must be impossible to lose:
# its 100% coverage and its Stage-2 diff matching football-data 1,140/1,140
# rule out a data explanation, and the undiluted window made it WORSE
# (+0.0026 -> +0.0037, both seeds). Do not "fix" the inconsistency.
XG_CAMPAIGN_VERDICT: dict[str, dict] = {
    "primeira":       {"mean_delta_brier": -0.0075, "seeds": (-0.0074, -0.0075),
                       "diluted_mean": -0.0055, "verdict": "keep"},
    "belgian-pro":    {"mean_delta_brier": -0.0027, "seeds": (-0.0027, -0.0026),
                       "diluted_mean": -0.0020, "verdict": "keep"},
    "eredivisie":     {"mean_delta_brier": -0.0018, "seeds": (-0.0016, -0.0020),
                       "diluted_mean": -0.0011, "verdict": "keep"},
    "championship":   {"mean_delta_brier": -0.0015, "seeds": (-0.0012, -0.0019),
                       "diluted_mean": -0.0012, "verdict": "keep"},
    "super-lig":      {"mean_delta_brier": -0.0012, "seeds": (-0.0020, -0.0004),
                       "diluted_mean": -0.0009, "verdict": "marginal",
                       "note": "The mean clears the bar; the SEEDS do not "
                               "agree. -0.0020 vs -0.0004 is a 0.0016 spread "
                               "against a stated single-run sigma of ~0.0002, "
                               "and seed 7 alone would not promote it. The "
                               "diluted campaign already saw this league and "
                               "championship swap places between seeds. Not "
                               "wired; promote only on evidence that holds at "
                               "both seeds."},
    "brazil-serie-a": {"mean_delta_brier": +0.0037, "seeds": (+0.0037, +0.0038),
                       "diluted_mean": +0.0026, "verdict": "reject",
                       "note": "REGRESSES on both seeds, and the undiluted "
                               "window made it worse. Coverage is 100% and the "
                               "Stage-2 diff matched football-data 1,140/1,140, "
                               "so this is not a data defect — real xG makes "
                               "this league's model worse. Do not 'fix' the "
                               "inconsistency."},
}

XG_KEEP_LEAGUES = tuple(lid for lid, v in XG_CAMPAIGN_VERDICT.items()
                        if v["verdict"] == "keep")


def attach_xg(frame: pd.DataFrame, league_id: str) -> pd.DataFrame:
    """Fill empty home_xg/away_xg from the backfill store. Row count is
    unchanged, existing values are preserved, and unmatched rows stay NaN."""
    rows = xg_rows(league_id)
    if not rows or frame.empty:
        return frame
    ours_to_af = _team_names().get(league_id, {})
    lookup = {(r["season"], _norm(r["home_team"]), _norm(r["away_team"])):
              (r["home_xg"], r["away_xg"]) for r in rows}

    out = frame.copy()
    for col in ("home_xg", "away_xg"):
        if col not in out.columns:
            out[col] = np.nan
    for idx, row in out.iterrows():
        if pd.notna(row.get("home_xg")) and pd.notna(row.get("away_xg")):
            continue                           # Tier C owns its own xG
        home = ours_to_af.get(row["home_team"], row["home_team"])
        away = ours_to_af.get(row["away_team"], row["away_team"])
        hit = lookup.get((int(row["season"]), _norm(home), _norm(away)))
        if hit is None:
            continue
        out.at[idx, "home_xg"], out.at[idx, "away_xg"] = hit
    return out
