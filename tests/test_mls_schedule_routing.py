"""MLS schedule routing — ESPN primary, API-Football ordered fallback. No network.

Spec: docs/superpowers/specs/2026-08-09-platform-reliability-and-api-opportunity-spec.md
§3.1. `build (mls)` has been red since ~2026-08-06 because a 403 on ESPN's
`usa.1/scoreboard` is fatal: the MLS path is the ONLY build that never went
through the source router, since MLS is not in `build_league_data.OUTLOOK`.

What these tests pin, and why each one exists:

- With ESPN answering, the routed schedule is exactly what `espn_schedule`
  returned — the acceptance criterion is a byte-comparable payload, so the
  healthy path must not change at all.
- With ESPN blackholed at the HTTP layer, the build still gets a schedule.
- A spine answer whose club names do not resolve to ASA ids is a FAILURE, not
  a short season. This is the defect shape the whole spec is about: an
  unmapped club is silently dropped downstream as "not an MLS team", so an
  ungenerated name map would ship a truncated fixture list at 200 OK.
"""
from __future__ import annotations

import pandas as pd
import pytest

from scripts import build_dashboard_data as bdd


ESPN_ROWS = [
    ("2026-08-01", "atlanta united", "chicago fire", "post", 2, 1,
     "2026-08-01T23:30Z", "Mercedes-Benz Stadium", "Atlanta"),
    ("2026-08-08", "chicago fire", "atlanta united", "pre", None, None,
     "2026-08-08T23:30Z", "Soldier Field", "Chicago"),
]

SPINE_ROWS = [
    {"date": "2026-08-01", "home": "Atlanta United", "away": "Chicago Fire",
     "state": "post", "home_goals": 2, "away_goals": 1,
     "ko_utc": "2026-08-01T23:30:00+00:00", "venue": "Mercedes-Benz Stadium",
     "venue_city": "Atlanta"},
    {"date": "2026-08-08", "home": "Chicago Fire", "away": "Atlanta United",
     "state": "pre", "home_goals": None, "away_goals": None,
     "ko_utc": "2026-08-08T23:30:00+00:00", "venue": "Soldier Field",
     "venue_city": "Chicago"},
]

_IDS = {"atlanta united": "t-atl", "chicago fire": "t-chi"}


def _map_team(norm_name):
    return _IDS.get(norm_name)


@pytest.fixture
def isolated_health(tmp_path, monkeypatch):
    """source_health writes to a real parquet; keep the suite off the real one."""
    from data_pipeline import source_health
    monkeypatch.setattr(source_health, "_HEALTH_PATH",
                        tmp_path / "source_health.parquet")


@pytest.fixture
def espn_dark(monkeypatch):
    """ESPN blackholed at the HTTP layer, the way a 403 storm presents."""
    def _boom(*a, **k):
        raise RuntimeError("403 Forbidden (blackholed)")
    monkeypatch.setattr(bdd, "espn_schedule", _boom)


def test_healthy_build_is_unchanged_and_espn_first(monkeypatch, isolated_health):
    monkeypatch.setattr(bdd, "espn_schedule", lambda season: ESPN_ROWS)
    rows, src = bdd.routed_schedule(2026, _map_team)
    assert src == "espn"
    assert rows == ESPN_ROWS


def test_registry_keeps_espn_ahead_of_the_spine_for_mls():
    """The fallback must not become a migration by accident: making the spine
    primary needs §3.2's 100% diff and a generated name map."""
    from data_pipeline.source_registry import sources_for
    assert sources_for("mls", "fixtures", default="espn") == ["espn", "api_football"]


def test_fast_refresh_does_not_treat_mls_as_a_spine_league():
    """`uses_spine` keys off the FIRST source; an ordered fallback must not
    flip the fast-refresh path onto API-Football."""
    from scripts.fast_refresh import uses_spine
    assert uses_spine("mls") is False


def test_spine_answers_when_espn_is_blackholed(monkeypatch, isolated_health, espn_dark):
    from data_pipeline import api_football
    monkeypatch.setattr(api_football, "schedule_rows",
                        lambda league_id, season: SPINE_ROWS)
    rows, src = bdd.routed_schedule(2026, _map_team)
    assert src == "api_football"
    assert len(rows) == 2
    # Same row shape as ESPN's, names normalized the same way, venue preserved.
    assert rows[0] == ("2026-08-01", "atlanta united", "chicago fire", "post",
                       2, 1, "2026-08-01T23:30:00+00:00",
                       "Mercedes-Benz Stadium", "Atlanta")
    assert rows[1][3] == "pre"


def test_unmapped_spine_names_fail_closed_rather_than_truncate(
        monkeypatch, isolated_health, espn_dark):
    """When a spine club spelling does not resolve to an ASA id, the caller
    drops that fixture as "not an MLS club". That must be an error, not a half
    season. The map is committed now, so this stubs the resolver to prove the
    guard still holds for a club the map has yet to learn."""
    from data_pipeline import api_football
    monkeypatch.setattr(api_football, "schedule_rows",
                        lambda league_id, season: SPINE_ROWS)
    with pytest.raises(RuntimeError) as exc:
        bdd.routed_schedule(2026, lambda n: None)
    # The router names every source it tried, and the guard says what to fix.
    assert "api_football" in str(exc.value)
    assert "name" in str(exc.value).lower()


def test_every_source_failing_is_loud():
    """Today's behaviour on a dark ESPN is a failed build. It stays a failed
    build — the fallback must never turn a total outage into a quiet success."""
    from data_pipeline.source_registry import resolve
    with pytest.raises(RuntimeError):
        resolve("mls", "fixtures",
                {"espn": lambda: pd.DataFrame(),
                 "api_football": lambda: pd.DataFrame()},
                default="espn")


def test_schedule_provenance_is_published_not_assumed():
    """`espn_ok` was a hardcoded True. Defect #1 was exactly this shape — an
    invariant claimed in code and never measured in the payload."""
    src = (bdd.__file__ and open(bdd.__file__).read())
    assert '"schedule_source": sched_source' in src
    assert '"espn_ok": sched_source == "espn"' in src
    assert '"espn_ok": True' not in src


# ── the name floor is EVERY club, not most of them ───────────────────────────

def test_the_name_floor_admits_no_unmapped_club():
    """Measured 2026-08-09 while generating the map: 29 of API-Football's 30
    MLS clubs resolved on token matching alone. 29/30 is 96.7% — it CLEARS a
    95% floor while dropping every LA Galaxy fixture on the season, and the
    payload looks healthy. A share threshold is the wrong shape for a closed
    league with a known club set."""
    assert bdd._SPINE_NAME_FLOOR == 1.0


def test_one_unmapped_club_in_thirty_is_refused(monkeypatch, isolated_health,
                                                espn_dark):
    """The exact 29/30 case that motivated the floor: a single unknown club
    must fail the source closed rather than silently truncate the season."""
    from data_pipeline import api_football
    clubs = [f"Club {i}" for i in range(29)] + ["Unmapped United"]
    rows = [{"date": "2026-03-01", "home": clubs[i], "away": clubs[(i + 1) % 30],
             "state": "pre", "home_goals": None, "away_goals": None,
             "ko_utc": None, "venue": None, "venue_city": None}
            for i in range(30)]
    monkeypatch.setattr(api_football, "schedule_rows",
                        lambda league_id, season: rows)

    def resolver(norm_name):
        return None if "unmapped" in norm_name else "asa-id"

    with pytest.raises(RuntimeError) as exc:
        bdd.routed_schedule(2026, resolver)
    assert "29/30" in str(exc.value), str(exc.value)


def test_the_committed_map_records_the_one_club_token_matching_misses():
    """LA Galaxy is the single MLS club whose API-Football spelling ('Los
    Angeles Galaxy') shares no token set with the ASA name. Proven by fixture
    diff, not by name similarity: all 19 played 2026 meetings matched on date
    and opponent with ZERO scoreline disagreements (one at a 23:30 UTC kickoff
    matched a calendar day later, same 2-1 scoreline)."""
    import json
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent
    names = json.loads((root / "config/api_football_team_names.json").read_text())
    assert names["mls"] == {"Los Angeles Galaxy": "LA Galaxy"}
