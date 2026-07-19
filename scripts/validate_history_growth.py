#!/usr/bin/env python3
"""F-5: CI guard for the historical-data flywheel (docs/product-roadmap-2026-07.md
§2, docs/intelligence-hub-implementation-instructions.md §5 "S0").

Run as the last step of every refresh workflow, after all builders and
archivers have run and BEFORE the commit step. Fails the build (non-zero
exit) rather than silently landing a regression when:

  - any accrual parquet (data/odds_history.parquet, data/match_prob_history.parquet,
    data/race_deltas_history.parquet) has FEWER rows than the version already
    committed at HEAD — these files are append-only; a shrink means something
    truncated or replaced history instead of appending to it.
  - any public per-league trajectory file (webapp/data/drift-traj/<lid>.js)
    carries a season-tagged point whose season doesn't match that league's
    current payload season — the public payload leaking a prior season across
    a rollover is exactly what F-2 (scripts/build_drift_report.py) exists to
    prevent.

Usage:
    python scripts/validate_history_growth.py
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.payload_utils import read_js_payload, registry_ids  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
ACCRUAL_FILES = [
    Path("data/odds_history.parquet"),
    Path("data/match_prob_history.parquet"),
    Path("data/race_deltas_history.parquet"),
]
TRAJ_DIR = Path("webapp/data/drift-traj")


def committed_row_count(rel_path: Path) -> int | None:
    """Row count of `rel_path` as committed at HEAD, or None if it wasn't
    tracked yet (nothing to compare against — first time it's being added)."""
    result = subprocess.run(
        ["git", "show", f"HEAD:{rel_path.as_posix()}"],
        cwd=REPO_ROOT, capture_output=True,
    )
    if result.returncode != 0:
        return None
    with tempfile.NamedTemporaryFile(suffix=".parquet") as tmp:
        tmp.write(result.stdout)
        tmp.flush()
        return len(pd.read_parquet(tmp.name))


def check_no_shrinkage() -> list[str]:
    errors = []
    for rel_path in ACCRUAL_FILES:
        abs_path = REPO_ROOT / rel_path
        if not abs_path.exists():
            continue
        before = committed_row_count(rel_path)
        if before is None:
            continue
        after = len(pd.read_parquet(abs_path))
        if after < before:
            errors.append(f"{rel_path}: {before} → {after} rows (SHRANK)")
    return errors


def check_trajectory_season_bounds() -> list[str]:
    errors = []
    for lid in registry_ids():
        league_payload = read_js_payload(f"webapp/data/{lid}.js")
        current_season = (league_payload or {}).get("season")
        if current_season is None:
            continue
        traj = read_js_payload(TRAJ_DIR / f"{lid}.js")
        if not traj:
            continue
        for team, series in (traj.get("teams") or {}).items():
            for point in series:
                point_season = point.get("season")
                if point_season not in (None, current_season):
                    errors.append(
                        f"{lid}/{team}: trajectory point {point.get('date')} has "
                        f"season {point_season!r}, current season is {current_season!r}"
                    )
    return errors


def main() -> int:
    errors = check_no_shrinkage() + check_trajectory_season_bounds()
    if errors:
        print("[validate-history-growth] FAILED:")
        for e in errors:
            print(f"  - {e}")
        return 1
    print("[validate-history-growth] OK — no shrinkage, no season leakage")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
