"""Stage-1 probe — answer the five measured questions on the free key (~10 requests).

Spec: docs/superpowers/specs/2026-08-08-api-football-migration-execution-spec.md §7 Stage 1.

Every request goes through api_football._get, so the Stage-0 governor applies:
budget-checked, plan-asserted, throttled at the free plan's pace (12 s/request),
and recorded in source_health. Raw responses are cached to
data/api_football/probe/*.json as the evidence the spec requires.

The five questions:
  1. statistics/odds/lineups keyed per fixture or per league+season?
  2. does /statistics carry real xG, where, how far back?
  3. are /odds Pinnacle closing, or another book/timing?
  4. how far back do seasons go — does coverage reach 2017?
  5. does a 552-fixture season page? (232 did not)

Run: python -m scripts.api_football_probe
"""
from __future__ import annotations

import json
from pathlib import Path

from data_pipeline import api_football

OUT = Path("data/api_football/probe")


def _save(name: str, payload: dict) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{name}.json").write_text(json.dumps(payload, indent=1))


def probe(name: str, path: str, params: dict) -> dict:
    """One recorded, throttled request; errors are evidence, not crashes."""
    if (OUT / f"{name}.json").exists():          # resumable: never re-spend
        payload = json.loads((OUT / f"{name}.json").read_text())
        print(f"[cached] {name}")
        return payload
    try:
        payload = api_football._get(path, params)
    except Exception as exc:  # noqa: BLE001 — the error IS the measurement
        payload = {"probe_error": str(exc), "response": []}
    _save(name, payload)
    n = len(payload.get("response") or [])
    print(f"[probe]  {name}: {n} rows"
          + (f"  ERROR: {payload['probe_error']}" if "probe_error" in payload else ""))
    return payload


def _find_league(catalogue: dict, name: str, country: str) -> int | None:
    for row in catalogue.get("response", []):
        if (row["league"]["name"].lower() == name.lower()
                and row["country"]["name"].lower() == country.lower()):
            return int(row["league"]["id"])
    return None


def _first_finished_fixture(fixtures: dict) -> int | None:
    for f in fixtures.get("response", []):
        if f["fixture"].get("status", {}).get("short") in ("FT", "AET", "PEN"):
            return int(f["fixture"]["id"])
    return None


def main() -> None:
    # ── Q4 + the league map's raw material: the full catalogue, ONE request ──
    catalogue = probe("leagues_catalogue", "leagues", {})

    champ_id = _find_league(catalogue, "Championship", "England")
    bra_id = _find_league(catalogue, "Serie A", "Brazil")
    print(f"resolved ids: Championship={champ_id}, Brasileirão={bra_id}")

    # ── Q5: a 552-fixture season (Championship, 24 teams) — does it page? ────
    champ_fx = probe("fixtures_championship_2024", "fixtures",
                     {"league": champ_id, "season": 2024})
    print("  paging:", champ_fx.get("paging"),
          "| fixtures:", len(champ_fx.get("response") or []))

    # ── Q1 + Q2: statistics per fixture (works?) and per league+season (?) ──
    champ_fid = _first_finished_fixture(champ_fx)
    stats_one = probe("statistics_championship_fixture", "fixtures/statistics",
                      {"fixture": champ_fid})
    probe("statistics_league_season_probe", "fixtures/statistics",
          {"league": champ_id, "season": 2024})

    # xG presence: does any statistics block carry expected_goals?
    types = {s["type"] for side in (stats_one.get("response") or [])
             for s in side.get("statistics", [])}
    print("  statistic types:", sorted(types))

    # ── Q2 outside Europe: Brasileirão statistics ────────────────────────────
    bra_fx = probe("fixtures_brasileirao_2024", "fixtures",
                   {"league": bra_id, "season": 2024})
    bra_fid = _first_finished_fixture(bra_fx)
    bra_stats = probe("statistics_brasileirao_fixture", "fixtures/statistics",
                      {"fixture": bra_fid})
    bra_types = {s["type"] for side in (bra_stats.get("response") or [])
                 for s in side.get("statistics", [])}
    print("  brasileirão statistic types:", sorted(bra_types))

    # ── lineups: keyed per fixture, present for a 2024 match? ────────────────
    probe("lineups_championship_fixture", "fixtures/lineups",
          {"fixture": champ_fid})

    # ── Q3: is Pinnacle a bookmaker here, and do closing odds persist? ───────
    books = probe("odds_bookmakers", "odds/bookmakers", {})
    names = [b.get("name") for b in (books.get("response") or [])]
    print("  bookmakers:", names)
    probe("odds_finished_fixture", "odds", {"fixture": champ_fid})

    # ── spend receipt ────────────────────────────────────────────────────────
    from data_pipeline import api_budget
    print(f"\nspend today (recorded): {api_budget.spend_today()}")


if __name__ == "__main__":
    main()
