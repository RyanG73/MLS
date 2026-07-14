#!/usr/bin/env python3
"""
Fetch Transfermarkt MLS transfer-window spend/income (arrivals fee sum,
departures fee sum, net spend, split by summer/winter window) via the R
bridge (models/r_bridge/transfermarkt_transfer_spend.R), then map each
team-season row onto this dashboard's ASA short-code team id using the same
config/team_name_to_asa_id.yaml `transfermarkt:` alias table the existing
squad-value importer (scripts/import_transfermarkt.py) already uses — the TM
team display names on the transfers page match the kader page's names, so no
new mapping table is needed.

The R bridge already aggregates to one row per team-season (fee sums,
transfer counts, both combined and summer/winter-split). This script's only
job is: run the R fetch, load the raw CSV, attach asa_team_id + observed_at,
write the _mapped.csv the eval harness reads.

MLS only — this feature is being A/B tested against the MLS eval harness.
See docs/feature-hunt-log.md "Transfer spend/earnings" entry.

Usage:
    python scripts/import_transfermarkt_transfers.py --season 2024
    python scripts/import_transfermarkt_transfers.py --seasons 2017-2025
    python scripts/import_transfermarkt_transfers.py --seasons 2017-2025 --skip-fetch
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
R_SCRIPT  = REPO_ROOT / "models" / "r_bridge" / "transfermarkt_transfer_spend.R"
DATA_DIR  = REPO_ROOT / "data"
MAP_PATH  = REPO_ROOT / "config" / "team_name_to_asa_id.yaml"


def _raw_path(season: int) -> Path:
    return DATA_DIR / f"transfermarkt_transfers_{season}.csv"


def _mapped_path(season: int) -> Path:
    return DATA_DIR / f"transfermarkt_transfers_{season}_mapped.csv"


def _parse_seasons(spec: str) -> list[int]:
    if "-" in spec:
        a, b = spec.split("-", 1)
        return list(range(int(a), int(b) + 1))
    return [int(s) for s in spec.split(",") if s.strip()]


def _load_name_map() -> dict[str, str]:
    if not MAP_PATH.exists():
        print(f"WARN: {MAP_PATH} missing — mapped CSV will have empty asa_team_id.",
              file=sys.stderr)
        return {}
    with open(MAP_PATH) as fh:
        data = yaml.safe_load(fh) or {}
    return data.get("transfermarkt", {}) or {}


def _run_r(season: int, raw_csv: Path) -> None:
    raw_csv.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["Rscript", "--vanilla", str(R_SCRIPT), str(season), str(raw_csv)]
    print(f"  $ {' '.join(cmd)}")
    res = subprocess.run(cmd, timeout=3600)
    if res.returncode != 0:
        raise RuntimeError(f"R script failed for season {season} (rc={res.returncode})")


def _map_one(season: int, name_map: dict[str, str]) -> tuple[int, int]:
    raw_csv = _raw_path(season)
    if not raw_csv.exists() or raw_csv.stat().st_size == 0:
        print(f"  ! no raw CSV for {season}, skipping")
        return (0, 0)
    try:
        df = pd.read_csv(raw_csv)
    except Exception as exc:
        print(f"  ! could not read {raw_csv.name}: {exc}", file=sys.stderr)
        return (0, 0)
    if df.empty:
        print(f"  ! empty raw CSV for {season}, skipping")
        return (0, 0)

    df["asa_team_id"] = df["tm_team_name"].map(lambda n: name_map.get(str(n), ""))
    df["observed_at"] = datetime.now(timezone.utc).isoformat()

    unmapped = sorted(df.loc[df["asa_team_id"] == "", "tm_team_name"].unique())
    if unmapped:
        print(f"  Unmapped TM teams ({len(unmapped)}): {unmapped[:8]}"
              f"{' ...' if len(unmapped) > 8 else ''}")

    out = _mapped_path(season)
    df.to_csv(out, index=False)
    mapped_n = int((df["asa_team_id"] != "").sum())
    print(f"  -> {out.name} ({len(df)} teams, {mapped_n} mapped)")
    return (len(df), mapped_n)


def run_one_season(season: int, skip_fetch: bool) -> bool:
    print(f"\n{'='*70}\nMLS transfer-window spend — season {season}\n{'='*70}")
    name_map = _load_name_map()
    if not name_map:
        print(f"WARN: no transfermarkt entries in {MAP_PATH}", file=sys.stderr)

    if not skip_fetch:
        raw_csv = _raw_path(season)
        try:
            _run_r(season, raw_csv)
        except Exception as e:
            print(f"  ! R fetch failed: {e}", file=sys.stderr)
            return False

    t, _m = _map_one(season, name_map)
    return t > 0


def main() -> int:
    p = argparse.ArgumentParser(
        description="Import Transfermarkt transfer-window spend/income (MLS)")
    p.add_argument("--season", type=int, help="single season")
    p.add_argument("--seasons", type=str, help="range like '2017-2025' or comma list")
    p.add_argument("--skip-fetch", action="store_true",
                   help="skip Rscript fetch, only re-map existing raw CSVs")
    args = p.parse_args()

    if args.season:
        seasons = [args.season]
    elif args.seasons:
        seasons = _parse_seasons(args.seasons)
    else:
        seasons = [datetime.now().year]

    ok = True
    for s in seasons:
        ok = run_one_season(s, args.skip_fetch) and ok
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
