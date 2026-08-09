#!/usr/bin/env python3
"""Self-consistency checks over every published league payload.

Spec: docs/superpowers/specs/2026-08-09-platform-reliability-and-api-opportunity-spec.md
§5.2 (club-set validation) and §5.3 (fixture-count sanity).

Read the way a CLIENT reads (§8.13): only the published payload, never the
producer. A check that calls the builder passes tautologically — that is how
the Global ELO validator came to assert arithmetic the producer had stopped
doing.

Five checks, each catching a defect this repo has actually shipped:

  clubs      Every club in the fixture list appears in the table, and vice
             versa. Defects #4 and #5 were both caught by a human asking "do
             these clubs belong in this league?" — no automated check asked.
  played     Each club's completed-fixture count equals the `gp` its own table
             publishes. Two numbers in ONE payload that must agree; a
             disagreement is truncation, duplication, or a table computed from
             a different frame than the fixtures beneath it.
  fixtures   len(games) against N(N-1) and N(N-1)/2 — CLASSIFIED, not asserted.
             ~40% of the catalogue is not a plain double round-robin (cups,
             Apertura/Clausura, split seasons, feeds that publish only the
             next few weeks), so failing on a deviation would be noise.
  pairs      How many times each pair meets, and whether that is uniform.
             Argentina 2026 sums Apertura + Clausura + interzonal into one
             table: 30 clubs, pairs meeting 3x (§8.6).
  names      Club names that differ only by whitespace or punctuation. A
             trailing space in 'Liga Profesional ' was 2,114 rows away from an
             exact-match filter silently deleting a third of a league (§8.3).

Usage:
  check_payload_consistency.py [--league epl ...] [--report PATH] [--strict]
Default exit code is 0: this is a reporting surface, and several deviations are
correct for their competition — a cup table does not list every club that plays
in it, and an Apertura/Clausura league publishes one tournament's table over
both tournaments' fixtures. `--strict` therefore fails on anything NOT in the
committed baseline (`config/payload_consistency_baseline.json`), which is the
measured state on the day this landed. New deviation = regression; the baseline
shrinks as leagues are adjudicated. Regenerate it deliberately with
`--write-baseline`, never as a way of making a red run green.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.payload_utils import read_js_payload   # noqa: E402

PAYLOAD_DIR = Path("webapp/data")
# Cross-surface payloads with no league table of their own.
NOT_A_LEAGUE = {"power.js", "logos.js", "movers.js", "drift.js",
                "coefficients.js", "leagues.js", "home.js", "calendar.js"}
BASELINE_PATH = Path("config/payload_consistency_baseline.json")
# Checks compared against the baseline under --strict. `fixtures` is excluded:
# it is a classification, not a verdict, and 45 of 78 payloads are legitimately
# not a plain double round-robin.
STRICT_CHECKS = ("clubs", "played", "pairs", "names")


def _norm(name: str) -> str:
    s = unicodedata.normalize("NFD", str(name))
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def league_payloads(payload_dir: Path = PAYLOAD_DIR, only=None):
    for path in sorted(payload_dir.glob("*.js")):
        if path.name in NOT_A_LEAGUE:
            continue
        if only and path.stem not in only:
            continue
        payload = read_js_payload(path)
        if not isinstance(payload, dict):
            continue
        if not isinstance(payload.get("games"), list) or "standings" not in payload:
            continue
        yield path.stem, payload


def check_payload(league_id: str, payload: dict) -> dict:
    table = [r for r in (payload.get("standings") or [])
             if isinstance(r, dict) and r.get("team")]
    games = [g for g in (payload.get("games") or []) if isinstance(g, dict)]
    n = len(table)
    listed = {r["team"] for r in table}
    in_fixtures = {g.get(side) for g in games for side in ("home", "away")} - {None}

    # Knockout fixtures are published in `games` but are NOT league fixtures:
    # the standings loop filters `is_playoff`, so counting them here reports a
    # table defect where none exists. NWSL 2026 has exactly one — 2026-06-26
    # Gotham 2-0 Kansas City Current — which made both clubs read one game
    # short of their own fixtures and cost Gotham a phantom three points in
    # the arithmetic. Excluded from games-played AND from pair multiplicity,
    # since both checks describe the league table's own shape. Payloads built
    # before the `knockout` flag existed carry no such key and are
    # unaffected. The key is NOT `ko`: that is the kickoff timestamp, which 32
    # leagues publish on upcoming cards, and reusing it emptied both checks.
    played = Counter()
    pair_counts: Counter = Counter()
    for g in games:
        home, away = g.get("home"), g.get("away")
        if not home or not away or g.get("knockout"):
            continue
        pair_counts[tuple(sorted((home, away)))] += 1
        if g.get("result"):
            played[home] += 1
            played[away] += 1

    gp_mismatch = [
        {"team": r["team"], "table_gp": r["gp"], "fixtures_played": played.get(r["team"], 0)}
        for r in table
        if r.get("gp") is not None and int(r["gp"]) != played.get(r["team"], 0)
    ]

    double, single = n * (n - 1), n * (n - 1) // 2
    total = len(games)
    shape = ("double_round_robin" if total == double else
             "single_round_robin" if total == single else
             "partial_or_other")

    # Names that collapse to the same key differ only by whitespace,
    # punctuation or accents — one of them is a typo waiting to delete rows.
    by_key: dict[str, list[str]] = {}
    for name in sorted(listed | in_fixtures):
        by_key.setdefault(_norm(name), []).append(name)
    name_collisions = {k: v for k, v in by_key.items() if len(v) > 1}
    untrimmed = sorted(x for x in (listed | in_fixtures) if x != x.strip())

    multiplicities = sorted(set(pair_counts.values()))
    return {
        "league": league_id,
        "season": payload.get("season"),
        "clubs": n,
        "fixtures": total,
        "checks": {
            "clubs": {
                "ok": not (in_fixtures - listed) and not (listed - in_fixtures),
                "in_fixtures_not_in_table": sorted(in_fixtures - listed),
                "in_table_not_in_fixtures": sorted(listed - in_fixtures),
            },
            "played": {"ok": not gp_mismatch, "mismatches": gp_mismatch},
            "fixtures": {"ok": True, "shape": shape,
                         "double_round_robin": double, "single_round_robin": single},
            "pairs": {"ok": len(multiplicities) <= 1,
                      "multiplicities": multiplicities,
                      "max_meetings": max(pair_counts.values()) if pair_counts else 0},
            "names": {"ok": not name_collisions and not untrimmed,
                      "collisions": name_collisions, "untrimmed": untrimmed},
        },
    }


def annotate(results: list[dict]) -> None:
    for r in results:
        lid, checks = r["league"], r["checks"]
        for extra in checks["clubs"]["in_fixtures_not_in_table"]:
            print(f"::warning::payload {lid}: '{extra}' plays fixtures but is not "
                  f"in the table")
        for missing in checks["clubs"]["in_table_not_in_fixtures"]:
            print(f"::warning::payload {lid}: '{missing}' is in the table with no "
                  f"fixtures")
        for m in checks["played"]["mismatches"]:
            print(f"::warning::payload {lid}: {m['team']} table says "
                  f"{m['table_gp']} played, its fixtures say "
                  f"{m['fixtures_played']}")
        for name in checks["names"]["untrimmed"]:
            print(f"::warning::payload {lid}: club name {name!r} has untrimmed "
                  f"whitespace")
        for _, names in checks["names"]["collisions"].items():
            print(f"::warning::payload {lid}: names differing only by "
                  f"punctuation/whitespace: {names}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--league", nargs="*", default=None)
    ap.add_argument("--payload-dir", type=Path, default=PAYLOAD_DIR)
    ap.add_argument("--report", type=Path,
                    default=Path("output/payload-consistency.json"))
    ap.add_argument("--baseline", type=Path, default=BASELINE_PATH)
    ap.add_argument("--strict", action="store_true",
                    help="exit non-zero on a deviation not already in the baseline")
    ap.add_argument("--write-baseline", action="store_true",
                    help="record today's deviations as the baseline (deliberate "
                         "act: it accepts every current deviation as known)")
    args = ap.parse_args(argv)

    results = [check_payload(lid, p)
               for lid, p in league_payloads(args.payload_dir, args.league)]
    annotate(results)

    failing = {c: sorted(r["league"] for r in results if not r["checks"][c]["ok"])
               for c in ("clubs", "played", "pairs", "names")}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(
        {"checked": len(results), "failing": failing, "leagues": results},
        indent=1, sort_keys=True) + "\n")
    print(f"payload consistency: {len(results)} payloads · " +
          " · ".join(f"{c}: {len(v)} deviating" for c, v in failing.items()) +
          f" → {args.report}")
    if args.write_baseline:
        args.baseline.parent.mkdir(parents=True, exist_ok=True)
        args.baseline.write_text(json.dumps(
            {"_README": [
                "Known payload-consistency deviations, measured, not typed.",
                "A league is here because its deviation has NOT been adjudicated,",
                "not because it is correct. Anything outside this list is a",
                "regression. Shrink it by fixing or explaining a league; never",
                "grow it to make a red run green.",
             ], "deviations": {c: failing[c] for c in STRICT_CHECKS}},
            indent=1, sort_keys=True) + "\n")
        print(f"payload consistency: baseline written → {args.baseline}")
        return 0

    if args.strict:
        known = _baseline(args.baseline)
        regressions = {c: sorted(set(failing[c]) - set(known.get(c) or []))
                       for c in STRICT_CHECKS}
        if any(regressions.values()):
            for c, leagues in regressions.items():
                if leagues:
                    print(f"::error::payload consistency: NEW {c} deviation in "
                          f"{', '.join(leagues)}")
            return 1
        print("payload consistency: no deviation outside the baseline")
    return 0


def _baseline(path: Path) -> dict:
    try:
        return json.loads(path.read_text()).get("deviations") or {}
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


if __name__ == "__main__":                            # pragma: no cover
    sys.exit(main())
