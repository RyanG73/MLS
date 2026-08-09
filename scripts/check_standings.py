#!/usr/bin/env python3
"""Cross-check every published league table against API-Football's own.

Spec: docs/superpowers/specs/2026-08-09-platform-reliability-and-api-opportunity-spec.md
§5.1. ~70 requests a day — 0.05% of the Mega allowance — for an independent
witness to the single class of defect this platform keeps finding by accident.

A disagreement means exactly one of:

  * a missing fixture (our table is short a game),
  * a wrong scoreline (points/GD drift with played matching),
  * a competition-mixing bug (defect #6 put 920 Argentine cup matches inside a
    league frame; defect #4 put La Liga clubs in a second-tier table), or
  * a points deduction we do not model (a real, benign disagreement).

The first three are bugs we would otherwise ship. The fourth is why this
reports rather than fails: an administrative deduction is not a defect, and a
check that cries wolf on it stops being read.

**Names are matched exactly or not at all.** Fuzzy matching is banned here, and
not out of caution: during the Stage-3 migration a fuzzy matcher proposed
`Bristol City → Stoke City`, which would have attributed one club's record to
another and looked entirely plausible in the output. A club we cannot match by
exact normalized name (after the configured name maps) is reported as
`unmatched`, which is a different finding from a disagreement — and the
unmatched list is exactly the raw material for generating a name map.

Usage:
  check_standings.py                    # every league with an approved af_id
  check_standings.py --league epl la-liga
  check_standings.py --report output/standings-crosscheck.json
Requires API_FOOTBALL_KEY. Without it every league is reported as `skipped`
with the reason, and the exit code stays 0 — a machine that cannot ask has
found nothing, which is not the same as finding nothing wrong.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.payload_utils import read_js_payload   # noqa: E402

PAYLOAD_DIR = Path("webapp/data")
MAP_PATH = Path("config/api_football_league_map.json")
# Our canonical name → API-Football name, the direction the xG join already
# uses. Reused rather than duplicated so one map serves both consumers.
XG_NAMES_PATH = Path("config/api_football_xg_names.json")

# Tolerances. Zero for points and played: those are counted integers and a
# difference is either a defect or a deduction, never rounding.
TOLERANCE = {"points": 0, "played": 0, "gd": 0}


def _norm(name: str) -> str:
    s = unicodedata.normalize("NFD", str(name))
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def league_map(path: Path = MAP_PATH) -> dict:
    try:
        return json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _name_map(league_id: str, path: Path = XG_NAMES_PATH) -> dict[str, str]:
    """API-Football name → our canonical name (the inverse of the stored map)."""
    try:
        cfg = json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    return {af: ours for ours, af in (cfg.get(league_id) or {}).items()}


def our_table(league_id: str, payload_dir: Path = PAYLOAD_DIR) -> tuple[list[dict], int | None]:
    """Our published table: [{team, played, points, gd}], plus its season."""
    path = payload_dir / f"{league_id}.js"
    if not path.exists():
        return [], None
    payload = read_js_payload(path)
    if not isinstance(payload, dict):
        return [], None
    rows = []
    for row in payload.get("standings") or []:
        if not isinstance(row, dict) or not row.get("team"):
            continue
        rows.append({"team": row["team"], "played": row.get("gp"),
                     "points": row.get("pts"), "gd": row.get("gd")})
    season = payload.get("season")
    return rows, int(season) if season is not None else None


def diff_tables(ours: list[dict], theirs: list[dict]) -> dict:
    """Exact-name diff of two tables. Never guesses a pairing.

    Returns {matched, disagreements, unmatched_ours, unmatched_theirs}. A
    disagreement carries every field that differs, with both values, so the
    report says what to go and look at rather than that something is wrong.
    """
    by_theirs = {}
    for row in theirs:
        by_theirs.setdefault(_norm(row["team"]), row)
    seen: set[str] = set()
    disagreements, unmatched_ours = [], []
    for row in ours:
        key = _norm(row["team"])
        other = by_theirs.get(key)
        if other is None:
            unmatched_ours.append(row["team"])
            continue
        seen.add(key)
        fields = {}
        for field, tol in TOLERANCE.items():
            a, b = row.get(field), other.get(field)
            if a is None or b is None:
                continue
            if abs(int(a) - int(b)) > tol:
                fields[field] = {"ours": int(a), "theirs": int(b)}
        if fields:
            disagreements.append({"team": row["team"], "fields": fields})
    unmatched_theirs = [r["team"] for k, r in by_theirs.items() if k not in seen]
    return {
        "matched": len(ours) - len(unmatched_ours),
        "disagreements": disagreements,
        "unmatched_ours": sorted(unmatched_ours),
        "unmatched_theirs": sorted(unmatched_theirs),
    }


def check_league(league_id: str, entry: dict, fetch=None,
                 payload_dir: Path = PAYLOAD_DIR) -> dict:
    ours, season = our_table(league_id, payload_dir)
    if not ours:
        return {"league": league_id, "status": "skipped",
                "reason": "no published table"}
    if season is None:
        return {"league": league_id, "status": "skipped",
                "reason": "payload carries no season"}
    if fetch is None:                                   # pragma: no cover
        from data_pipeline.api_football import standings_rows as fetch
    try:
        theirs = fetch(int(entry["af_id"]), season, _name_map(league_id))
    except Exception as exc:                            # noqa: BLE001
        return {"league": league_id, "status": "error", "season": season,
                "reason": f"{type(exc).__name__}: {exc}"}
    if not theirs:
        # Genuinely normal: an off-season or not-yet-started league has no
        # table upstream (§8.14). Not an error, and not a clean bill either.
        return {"league": league_id, "status": "no_upstream_table",
                "season": season}
    result = diff_tables(ours, theirs)
    result.update({"league": league_id, "season": season,
                   "clubs_ours": len(ours), "clubs_theirs": len(theirs),
                   "status": "disagree" if result["disagreements"] else
                             ("unmatched" if result["unmatched_ours"] else "agree")})
    return result


def annotate(results: list[dict]) -> None:
    for r in results:
        lid = r["league"]
        for d in r.get("disagreements") or []:
            detail = ", ".join(f"{f}: ours {v['ours']} vs {v['theirs']}"
                               for f, v in d["fields"].items())
            print(f"::warning::standings {lid}: {d['team']} — {detail}")
        if r.get("unmatched_ours"):
            print(f"::warning::standings {lid}: {len(r['unmatched_ours'])} club(s) "
                  f"in our table with no exact match upstream: "
                  f"{', '.join(r['unmatched_ours'][:6])}")
        if r.get("status") == "error":
            print(f"::warning::standings {lid}: {r['reason']}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--league", nargs="*", default=None)
    ap.add_argument("--report", type=Path, default=Path("output/standings-crosscheck.json"))
    ap.add_argument("--payload-dir", type=Path, default=PAYLOAD_DIR)
    ap.add_argument("--strict", action="store_true",
                    help="exit non-zero on any disagreement (default: warn only, "
                         "because a points deduction is a real disagreement and "
                         "not a defect)")
    args = ap.parse_args(argv)

    catalogue = league_map()
    wanted = args.league or sorted(catalogue)
    results = []
    for lid in wanted:
        entry = catalogue.get(lid)
        if not entry or not entry.get("af_id"):
            results.append({"league": lid, "status": "skipped",
                            "reason": "no approved API-Football id"})
            continue
        results.append(check_league(lid, entry, payload_dir=args.payload_dir))
    annotate(results)

    counts: dict[str, int] = {}
    for r in results:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(
        {"counts": counts, "leagues": results}, indent=1, sort_keys=True) + "\n")
    print(f"standings cross-check: " +
          ", ".join(f"{k}={v}" for k, v in sorted(counts.items())) +
          f" → {args.report}")
    if args.strict and counts.get("disagree"):
        print("::error::standings cross-check found disagreements (--strict)")
        return 1
    return 0


if __name__ == "__main__":                              # pragma: no cover
    sys.exit(main())
