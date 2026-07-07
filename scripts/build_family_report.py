#!/usr/bin/env python3
"""C2 governance: family-level walk-forward reports for the European families.

The MLS/NWSL/USL families get harness reports from `eval_baseline.py --asa-league`;
the two European families have no single harness — their evidence is the
per-league walk-forward eval that `build_league_data.py` already runs and ships
in each payload's `perf_by_year` (model vs naive Brier per season). This script
pools those into one gate-compatible report per family so
`promotion_gate.py --champion-ptr experiments/champion_eur_*.json` has a
baseline to judge future family-wide experiments against.

Pooling is EQUAL-WEIGHT across league-seasons inside the 2022–2025 test window
(the payloads don't carry per-season match counts; league sizes are similar
enough that equal weighting is the honest simple choice — documented here and
in the report's `pooling` field). `coverage_by_season` counts contributing
LEAGUES, not matches; the gate's coverage check is only ever used to compare
two reports built by this same script, so the unit is consistent.

Usage:
    python scripts/build_family_report.py            # both families
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

REPO = Path(__file__).parent.parent
WINDOW = range(2022, 2026)

FAMILIES = {
    "eur-big5": ["epl", "la-liga", "serie-a", "bundesliga", "ligue-1"],
    "eur-tiers": ["championship", "league-one", "league-two", "bundesliga-2",
                  "serie-b", "segunda", "ligue-2",
                  "eredivisie", "primeira", "super-lig",
                  "scottish-prem", "belgian-pro", "greek-super"],
}


def _payload(lid: str) -> dict | None:
    p = REPO / "webapp" / "data" / f"{lid}.js"
    if not p.exists():
        return None
    txt = p.read_text()
    return json.loads(txt[txt.index("=") + 1:].rstrip().rstrip(";"))


def build(family: str, leagues: list[str]) -> dict:
    by_season: dict[int, list[tuple[str, float, float]]] = {}
    for lid in leagues:
        d = _payload(lid)
        if not d:
            print(f"  [warn] {lid}: no payload — skipped")
            continue
        for row in d.get("perf_by_year", []):
            y = int(row["year"])
            if y in WINDOW and row.get("model") is not None and row.get("naive") is not None:
                by_season.setdefault(y, []).append(
                    (lid, float(row["model"]), float(row["naive"])))

    per_season = {str(y): round(sum(m for _, m, _ in rows) / len(rows), 6)
                  for y, rows in sorted(by_season.items())}
    per_season_naive = {str(y): round(sum(n for _, _, n in rows) / len(rows), 6)
                        for y, rows in sorted(by_season.items())}
    all_rows = [r for rows in by_season.values() for r in rows]
    avg = sum(m for _, m, _ in all_rows) / len(all_rows)
    naive = sum(n for _, _, n in all_rows) / len(all_rows)

    return {
        "experiment_id": f"{family}-family",
        "family": family,
        "timestamp": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "pooling": "equal-weight across league-seasons, 2022-2025 window; "
                   "coverage_by_season counts leagues",
        "leagues": leagues,
        "avg_brier": round(avg, 6),
        "naive_brier": round(naive, 6),
        "per_season": per_season,
        "per_season_naive": per_season_naive,
        "coverage_by_season": {str(y): len(rows) for y, rows in sorted(by_season.items())},
        "per_league_seasons": {
            str(y): {lid: round(m, 4) for lid, m, _ in rows}
            for y, rows in sorted(by_season.items())},
    }


def main() -> None:
    for family, leagues in FAMILIES.items():
        rep = build(family, leagues)
        out = REPO / "experiments" / f"{family}-family.report.json"
        out.write_text(json.dumps(rep, indent=2))
        print(f"[{family}] {len(rep['leagues'])} leagues · "
              f"avg {rep['avg_brier']} vs naive {rep['naive_brier']} "
              f"({(rep['naive_brier'] - rep['avg_brier']) / rep['naive_brier'] * 100:+.1f}%) → {out.name}")


if __name__ == "__main__":
    main()
