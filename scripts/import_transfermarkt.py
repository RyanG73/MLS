#!/usr/bin/env python3
"""
Fetch Transfermarkt MLS squad values via worldfootballR (R subprocess),
then join the team-name → ASA team_id map and write a *_mapped.csv ready
for the eval harness to consume.

Eval-only — no DB writes. Mirrors the structure of import_referee_stats.py
but stays self-contained for scripts/eval_baseline.py.

Usage:
    python scripts/import_transfermarkt.py --season 2024
    python scripts/import_transfermarkt.py --seasons 2017-2024
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

import pandas as pd
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
R_SCRIPT = REPO_ROOT / "models" / "r_bridge" / "transfermarkt_squad_values.R"
DATA_DIR = REPO_ROOT / "data"
MAP_PATH = REPO_ROOT / "config" / "team_name_to_asa_id.yaml"


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
    raw = DATA_DIR / f"transfermarkt_squad_values_{season}.csv"
    if not raw.exists() or raw.stat().st_size == 0:
        print(f"  ! no raw CSV for {season}, skipping")
        return (0, 0)

    df = pd.read_csv(raw)
    if df.empty:
        print(f"  ! empty raw CSV for {season}, skipping")
        return (0, 0)

    df["asa_team_id"] = df["tm_team_name"].map(name_map).fillna("")
    unmapped = sorted(df.loc[df["asa_team_id"] == "", "tm_team_name"].unique())
    if unmapped:
        print(f"  Unmapped TM teams ({len(unmapped)}): {unmapped[:8]}"
              f"{' ...' if len(unmapped) > 8 else ''}")

    out = DATA_DIR / f"transfermarkt_squad_values_{season}_mapped.csv"
    df.to_csv(out, index=False)
    print(f"  → {out.name} ({len(df)} rows, {(df['asa_team_id'] != '').sum()} mapped)")
    return (len(df), int((df["asa_team_id"] != "").sum()))


def main() -> int:
    p = argparse.ArgumentParser(description="Import Transfermarkt squad values for MLS")
    p.add_argument("--season", type=int, help="single season")
    p.add_argument("--seasons", type=str, help="range like '2017-2024' or comma list")
    p.add_argument("--skip-fetch", action="store_true",
                   help="skip Rscript fetch, only re-map existing raw CSVs")
    args = p.parse_args()

    if args.season:
        seasons = [args.season]
    elif args.seasons:
        seasons = _parse_seasons(args.seasons)
    else:
        seasons = [int(__import__("datetime").datetime.now().year)]

    name_map = _load_name_map()
    if not name_map:
        print(f"WARN: no transfermarkt entries in {MAP_PATH}", file=sys.stderr)

    total, mapped = 0, 0
    for s in seasons:
        print(f"\n=== Season {s} ===")
        if not args.skip_fetch:
            try:
                _run_r(s, DATA_DIR / f"transfermarkt_squad_values_{s}.csv")
            except Exception as e:
                print(f"  ! R fetch failed: {e}", file=sys.stderr)
                continue
        t, m = _map_one(s, name_map)
        total += t
        mapped += m

    print(f"\nDone. Total rows: {total} | Mapped to ASA id: {mapped}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
