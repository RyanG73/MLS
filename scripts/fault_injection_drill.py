#!/usr/bin/env python3
"""Fault-injection drill: prove the build degrades as designed when ESPN is dark.

Spec: docs/superpowers/specs/2026-08-09-platform-reliability-and-api-opportunity-spec.md
§3.6. ESPN availability is bimodal — dark for hours on 2026-08-07 and 08-08,
answering 200 at 01:20 on 08-09 — and the source router exists precisely for
that. Nothing exercises the fallback path while ESPN is answering, so it rots
quietly, and the first anyone would learn of it is the next outage.

The drill blackholes ESPN at the HTTP layer (`ENTENSER_BLOCK_ESPN=1`, checked in
`data_pipeline.http.espn_get`, the chokepoint every adapter goes through) and
asserts four things:

  1. The blackhole actually works — a drill that silently stops injecting the
     fault passes forever and proves nothing.
  2. A ROUTED league still resolves its fixtures, from a source that is not
     ESPN. This is the assertion that rots if an adapter changes.
  3. An UNROUTED league fails VISIBLY — one error naming every source tried.
     Degrading quietly is the failure mode, not the goal.
  4. The MLS schedule falls through to its ordered fallback (§3.1).

Checks 2 and 4 make real spine requests and need `API_FOOTBALL_KEY`. Without
it they report `skipped` with the reason and the drill's verdict says so — a
drill that cannot reach the spine has not proven the fallback, and reporting
"pass" would be worse than reporting nothing.

Usage:
  fault_injection_drill.py [--report output/fault-injection.json] [--live]
`--live` opts into the real spine requests; without it, checks 2 and 4 are
structural only (the registry orders a non-ESPN source ahead of nothing).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

BLOCK_ENV = "ENTENSER_BLOCK_ESPN"


def _check(name: str, ok: bool | None, detail: str) -> dict:
    return {"check": name,
            "status": "pass" if ok else ("skipped" if ok is None else "fail"),
            "detail": detail}


def check_blackhole_works() -> dict:
    """The drill's own smoke test. Without it the other checks can pass because
    nothing was ever blocked."""
    from data_pipeline import http
    if not http.espn_is_blocked():
        return _check("blackhole_active", False,
                      f"{BLOCK_ENV} is not set — nothing was blocked")
    try:
        http.espn_get("https://site.api.espn.com/apis/site/v2/sports/soccer/"
                      "usa.1/scoreboard", attempts=1)
    except http.Blackholed as exc:
        return _check("blackhole_active", True, str(exc)[:200])
    except Exception as exc:                          # noqa: BLE001
        return _check("blackhole_active", False,
                      f"blocked request raised {type(exc).__name__}, not Blackholed")
    return _check("blackhole_active", False, "a blocked ESPN request SUCCEEDED")


def check_routed_league_survives(league_id: str, live: bool) -> dict:
    """A migrated league still gets fixtures, from a source that is not ESPN."""
    from data_pipeline.source_registry import sources_for
    order = sources_for(league_id, "fixtures", default="espn")
    if order[0] == "espn":
        return _check(f"routed:{league_id}", False,
                      f"expected a non-ESPN primary, registry says {order}")
    if not live:
        return _check(f"routed:{league_id}", None,
                      f"structural only: registry order {order}; rerun with "
                      f"--live and API_FOOTBALL_KEY to fetch")
    from data_pipeline import api_football
    try:
        frame = api_football.results_frame(league_id)
    except Exception as exc:                          # noqa: BLE001
        return _check(f"routed:{league_id}", False,
                      f"{type(exc).__name__}: {exc}")
    if frame is None or frame.empty:
        return _check(f"routed:{league_id}", False, "spine returned an empty frame")
    return _check(f"routed:{league_id}", True,
                  f"{len(frame)} rows from api_football with ESPN blackholed")


def check_unrouted_league_fails_loudly(league_id: str) -> dict:
    """An unmigrated league must fail with one error naming every source it
    tried — not degrade to a stale or partial payload."""
    from data_pipeline.source_registry import resolve

    def dead():
        from data_pipeline import http
        raise http.Blackholed("ESPN blackholed")

    try:
        resolve(league_id, "fixtures", {"espn": dead}, default="espn")
    except RuntimeError as exc:
        if "espn" in str(exc):
            return _check(f"unrouted:{league_id}", True, str(exc)[:200])
        return _check(f"unrouted:{league_id}", False,
                      f"failed without naming the source: {exc}")
    return _check(f"unrouted:{league_id}", False,
                  "an unrouted league resolved fixtures with ESPN dark")


def check_mls_schedule_falls_back(live: bool) -> dict:
    from data_pipeline.source_registry import sources_for
    order = sources_for("mls", "fixtures", default="espn")
    if "api_football" not in order:
        return _check("mls_schedule_fallback", False,
                      f"MLS has no ordered fallback: {order}")
    if not live:
        return _check("mls_schedule_fallback", None,
                      f"structural only: registry order {order}")
    from scripts.build_dashboard_data import routed_schedule
    from data_pipeline.asa_cache import get_teams
    import unicodedata

    def _norm(n):
        n = unicodedata.normalize("NFKD", str(n)).encode("ascii", "ignore").decode()
        return "".join(c for c in n.lower() if c.isalnum() or c == " ").strip()

    try:
        teams = get_teams("mls")
        ids = {_norm(r.team_name): r.team_id for r in teams.itertuples()}
        rows, src = routed_schedule(int(os.environ.get("DRILL_SEASON", 2026)),
                                    lambda n: ids.get(n))
    except Exception as exc:                          # noqa: BLE001
        return _check("mls_schedule_fallback", False, f"{type(exc).__name__}: {exc}")
    if src == "espn":
        return _check("mls_schedule_fallback", False,
                      "ESPN answered while blackholed")
    return _check("mls_schedule_fallback", True,
                  f"{len(rows)} fixtures from {src} with ESPN blackholed")


def run(live: bool = False) -> list[dict]:
    return [
        check_blackhole_works(),
        check_routed_league_survives("northern-super-league", live),
        check_routed_league_survives("usl-super-league", live),
        check_unrouted_league_fails_loudly("epl"),
        check_mls_schedule_falls_back(live),
    ]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--report", type=Path, default=Path("output/fault-injection.json"))
    ap.add_argument("--live", action="store_true",
                    help="make real spine requests (needs API_FOOTBALL_KEY)")
    args = ap.parse_args(argv)

    # The block is NOT set here. Setting it as a side effect would mutate the
    # environment of whatever imported this (it leaked into the test process
    # exactly once, and four unrelated http tests went red), and a drill run
    # without the fault injected should say so rather than quietly inject it:
    # `check_blackhole_works` fails with "nothing was blocked", which is the
    # honest verdict.
    results = run(live=args.live)
    for r in results:
        level = {"pass": "notice", "skipped": "warning", "fail": "error"}[r["status"]]
        print(f"::{level}::fault-injection {r['check']}: {r['status']} — {r['detail']}"
              if level != "notice" else
              f"fault-injection {r['check']}: pass — {r['detail']}")
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(results, indent=1) + "\n")
    failed = [r for r in results if r["status"] == "fail"]
    skipped = [r for r in results if r["status"] == "skipped"]
    print(f"fault-injection drill: {len(results) - len(failed) - len(skipped)} pass, "
          f"{len(skipped)} skipped, {len(failed)} fail → {args.report}")
    if skipped:
        print("::warning::fault-injection: some checks were structural only — "
              "the fallback path was NOT exercised end to end")
    return 1 if failed else 0


if __name__ == "__main__":                            # pragma: no cover
    sys.exit(main())
