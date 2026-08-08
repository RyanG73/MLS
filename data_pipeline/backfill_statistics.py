"""Resumable, idempotent statistics backfill — the §6.5 job, statistics only.

Spec: docs/superpowers/specs/2026-08-08-api-football-migration-execution-spec.md
(§4.2 scope, §6.5 resumability, §7 Stage 4). Owner decisions 2026-08-08: the
backfill fetches `/fixtures/statistics` ONLY — lineups, odds and events are
deferred — for the competitions that lack a real xG source, in the measured
xG era (2023+, Stage-1 fact), recent-first across leagues.

Design properties, in the order they matter:

- **Cannot outspend.** Every request goes through api_football._get with
  budget="backfill" — a *separate* allowance from ops, 0 by construction on
  the free plan, so the job physically refuses to run before the purchase.
  BudgetExceeded is a clean exit with progress kept, never a crash.
- **Restart re-reads, never re-requests.** One JSON per fixture id under
  STORE; an empty stat sheet is cached as empty and never asked again.
  Fixture inventories cache per (af_id, season) — past seasons are immutable,
  and newly played matches are the daily refresh's job, not the backfill's.
- **A lapse stops the job.** PlanMismatch propagates; it must look like an
  outage, never be absorbed as a per-fixture failure.
- **Progress is a disk read.** --status and progress() never spend a request.

CLI:
    python -m data_pipeline.backfill_statistics --plan     # work list, 0 requests
    python -m data_pipeline.backfill_statistics --status   # progress, 0 requests
    python -m data_pipeline.backfill_statistics --run [--max-requests N]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

STORE = Path("data/api_football/statistics")
FIXTURES_CACHE = Path("data/api_football/backfill_fixtures")
MAP_PATH = Path("config/api_football_league_map.json")

XG_SINCE = 2023            # measured 2026-08-08: expected_goals absent 2022, present 2023+
_FINISHED = {"FT", "AET", "PEN"}
# Transient provider errors (measured live 2026-08-08: a '5xEr' "bug on our
# side" response mid-run) are skipped per fixture and retried on the next run.
# Sustained failure is systemic — abort rather than burn quota on a broken
# endpoint.
MAX_CONSECUTIVE_FAILURES = 20


def plan_backfill(league_map: dict, exclude: set[str],
                  xg_since: int = XG_SINCE) -> list[tuple[str, int, int]]:
    """Work units (league_id, af_id, season), recent-first ACROSS leagues:
    every league's newest season is fetched before any league goes deeper
    (XGB weight ½-life is 6 seasons — value lands early)."""
    units = []
    for lid, entry in league_map.items():
        if lid in exclude or not entry.get("af_id"):
            continue
        since = entry.get("statistics_since")
        last = entry.get("last_season")
        if since is None or last is None:
            continue
        for season in range(max(int(since), xg_since), int(last) + 1):
            units.append((lid, int(entry["af_id"]), season))
    return sorted(units, key=lambda u: (-u[2], u[0]))


def default_exclude() -> set[str]:
    """Competitions with a real xG source already (Tier C holds them):
    understat and ASA leagues from the build registry, plus MLS."""
    from scripts.build_league_data import OUTLOOK
    return {lid for lid, cfg in OUTLOOK.items()
            if cfg.get("source") in ("understat", "asa")} | {"mls"}


def _inventory(af_id: int, season: int) -> dict:
    """Fixture inventory for one league-season, cached immutably."""
    from data_pipeline import api_football
    FIXTURES_CACHE.mkdir(parents=True, exist_ok=True)
    cache = FIXTURES_CACHE / f"{af_id}_{season}.json"
    if cache.exists():
        return json.loads(cache.read_text())
    payload = api_football._get("fixtures",
                                {"league": af_id, "season": season},
                                budget="backfill")
    cache.write_text(json.dumps(payload))
    return payload


def _finished_ids(inventory: dict) -> list[int]:
    return [int(f["fixture"]["id"]) for f in inventory.get("response", [])
            if f.get("fixture", {}).get("status", {}).get("short") in _FINISHED]


def run_units(units: list[tuple[str, int, int]],
              max_requests: int | None = None) -> int:
    """Fetch missing stat sheets for `units`, in order. Returns the number of
    NEW sheets fetched this run. Exits cleanly on BudgetExceeded (resume
    later); PlanMismatch and everything else propagate."""
    from data_pipeline import api_football
    from data_pipeline.api_budget import BudgetExceeded, PlanMismatch
    STORE.mkdir(parents=True, exist_ok=True)
    done = 0
    consecutive_failures = 0
    for lid, af_id, season in units:
        try:
            inventory = _inventory(af_id, season)
        except BudgetExceeded as exc:
            print(f"[backfill] budget stop before {lid}/{season}: {exc}")
            return done
        for fid in _finished_ids(inventory):
            out = STORE / f"{fid}.json"
            if out.exists():
                continue
            if max_requests is not None and done >= max_requests:
                print(f"[backfill] --max-requests {max_requests} reached")
                return done
            try:
                payload = api_football._get("fixtures/statistics",
                                            {"fixture": fid},
                                            budget="backfill")
            except BudgetExceeded as exc:
                print(f"[backfill] budget stop at {lid}/{season} "
                      f"fixture {fid}: {exc}")
                return done
            except PlanMismatch:
                raise            # a lapse must stop the job, loudly
            except Exception as exc:  # noqa: BLE001 — transient provider error
                consecutive_failures += 1
                print(f"[backfill] fixture {fid} failed ({exc}); "
                      f"skipping, will retry next run "
                      f"({consecutive_failures} consecutive)")
                if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                    raise RuntimeError(
                        f"{consecutive_failures} consecutive failures — "
                        "aborting as systemic, resume when the provider "
                        "recovers") from exc
                continue
            consecutive_failures = 0
            out.write_text(json.dumps(payload))
            done += 1
    return done


def progress(units: list[tuple[str, int, int]]) -> dict:
    """Done/total from disk only — inventories not yet cached count as
    unknown, never trigger a fetch."""
    total = done = 0
    units_known = 0
    for _lid, af_id, season in units:
        cache = FIXTURES_CACHE / f"{af_id}_{season}.json"
        if not cache.exists():
            continue
        units_known += 1
        for fid in _finished_ids(json.loads(cache.read_text())):
            total += 1
            if (STORE / f"{fid}.json").exists():
                done += 1
    return {"units": len(units), "units_with_inventory": units_known,
            "fixtures_done": done, "fixtures_total": total}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--plan", action="store_true")
    g.add_argument("--status", action="store_true")
    g.add_argument("--run", action="store_true")
    ap.add_argument("--max-requests", type=int, default=None)
    args = ap.parse_args()

    league_map = json.loads(MAP_PATH.read_text())
    units = plan_backfill(league_map, exclude=default_exclude())

    if args.plan:
        leagues = sorted({u[0] for u in units})
        print(f"{len(units)} league-season units across {len(leagues)} "
              f"competitions (xG era {XG_SINCE}+):")
        for lid, af_id, season in units:
            print(f"  {season}  {lid} (af {af_id})")
        return
    if args.status:
        p = progress(units)
        from data_pipeline.api_budget import spend_today
        print(json.dumps({**p, "spend_today": spend_today()}, indent=1))
        return
    done = run_units(units, max_requests=args.max_requests)
    print(f"[backfill] fetched {done} new stat sheets this run")
    print(json.dumps(progress(units), indent=1))


if __name__ == "__main__":
    main()
