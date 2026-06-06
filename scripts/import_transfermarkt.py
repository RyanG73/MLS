#!/usr/bin/env python3
"""
Fetch Transfermarkt MLS squad values via worldfootballR (R subprocess),
then aggregate per-player data into PELE-style team-season features and
write a *_mapped.csv ready for the eval harness to consume.

PELE-inspired features computed per team-season:
  squad_value_eur   — adjusted total squad value (optional UEFA discount)
  att_value_pct     — FW/AM/W value as % of squad total (Tilt prior)
  def_value_pct     — CB/FB value as % of squad total
  tilt              — att_value_pct − def_value_pct (>0 = attacking)
  value_wtd_age     — age weighted by adjusted market value (lower = young+expensive)
  dp_value_share    — top-3 players' value / total (star concentration)
  avg_age           — simple squad mean age

Usage:
    python scripts/import_transfermarkt.py --season 2024
    python scripts/import_transfermarkt.py --seasons 2017-2025
    python scripts/import_transfermarkt.py --seasons 2017-2025 --skip-fetch
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
R_SCRIPT  = REPO_ROOT / "models" / "r_bridge" / "transfermarkt_squad_values.R"
DATA_DIR  = REPO_ROOT / "data"
MAP_PATH  = REPO_ROOT / "config" / "team_name_to_asa_id.yaml"

# Transfermarkt position → PELE position group
# Based on standard worldfootballR / Transfermarkt position strings
_POS_GROUP: dict[str, str] = {
    # Goalkeepers
    "goalkeeper": "GK",
    "gk": "GK",

    # Defenders
    "centre-back": "DEF", "center-back": "DEF",
    "cb": "DEF",
    "left-back": "DEF", "right-back": "DEF",
    "lb": "DEF", "rb": "DEF",
    "left back": "DEF", "right back": "DEF",
    "full back": "DEF", "fullback": "DEF",
    "sweeper": "DEF",
    "defender": "DEF",

    # Midfielders
    "central midfield": "MID", "central midfielder": "MID",
    "defensive midfield": "MID", "defensive midfielder": "MID",
    "dm": "MID", "cdm": "MID",
    "left midfield": "MID", "right midfield": "MID",
    "midfield": "MID", "midfielder": "MID",
    "cm": "MID",

    # Attackers (offensive midfielders + forwards)
    "attacking midfield": "ATT", "attacking midfielder": "ATT",
    "am": "ATT", "cam": "ATT",
    "left winger": "ATT", "right winger": "ATT",
    "lw": "ATT", "rw": "ATT",
    "winger": "ATT",
    "centre-forward": "ATT", "center-forward": "ATT",
    "cf": "ATT", "st": "ATT",
    "second striker": "ATT",
    "striker": "ATT", "forward": "ATT",
    "fw": "ATT",
}

# Top-5 European league country codes (for optional UEFA discount).
# Transfermarkt nationality fields use full country names; keep as guide for
# future use — not applied by default since MLS rosters already represent
# the market at MLS-level spending.
_UEFA_LEAGUES = frozenset([
    "England", "Spain", "Germany", "Italy", "France",
    "Netherlands", "Portugal", "Scotland", "Belgium",
])

UEFA_DISCOUNT = 0.0  # set to 0.30 to replicate PELE's ~30% pro-Europe correction


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


def _pos_group(raw_pos: str) -> str:
    if not isinstance(raw_pos, str):
        return "UNK"
    return _POS_GROUP.get(raw_pos.strip().lower(), "UNK")


def _build_player_db(raw_dir: Path) -> dict[str, dict]:
    """
    Build a cross-season player valuation index: player_name → most-recent known value.

    Used to fill in players whose current-season TM value is 0 or missing — e.g.
    a new signing whose value hasn't been published yet for the current season.
    We always prefer the most recent season's valuation.
    """
    player_db: dict[str, dict] = {}
    for csv_file in sorted(raw_dir.glob("transfermarkt_squad_values_*.csv")):
        if "mapped" in csv_file.name:
            continue
        try:
            season = int(csv_file.stem.rsplit("_", 1)[-1])
        except ValueError:
            continue
        try:
            df = pd.read_csv(csv_file)
        except Exception:
            continue
        if "market_value_eur" not in df.columns:
            df["market_value_eur"] = 0.0
        df["market_value_eur"] = pd.to_numeric(df["market_value_eur"], errors="coerce").fillna(0)
        if "age" not in df.columns:
            df["age"] = np.nan
        df["age"] = pd.to_numeric(df["age"], errors="coerce")
        for _, row in df.iterrows():
            name = str(row.get("player_name", "") or "").strip()
            value = float(row.get("market_value_eur", 0) or 0)
            if not name or value <= 0:
                continue
            existing = player_db.get(name)
            if existing is None or season > existing["season"]:
                player_db[name] = {
                    "value":    value,
                    "season":   season,
                    "position": str(row.get("position", "") or ""),
                }
    return player_db


def _aggregate_team(players: pd.DataFrame,
                    player_db: dict | None = None) -> dict:
    """Compute PELE-style team-level features from per-player rows.

    For players with value=0, look up their most recent individual valuation
    from the cross-season player database (handles mid-season signings and
    seasons where TM hasn't published updated values yet).
    """
    if players.empty:
        return {}

    vals = players["market_value_eur"].fillna(0).clip(lower=0).to_numpy(dtype=float)

    # Fill zeros from cross-season player lookup
    if player_db:
        for i, (_, row) in enumerate(players.iterrows()):
            if vals[i] == 0:
                name = str(row.get("player_name", "") or "").strip()
                entry = player_db.get(name)
                if entry:
                    vals[i] = entry["value"]

    ages = players["age"].to_numpy(dtype=float)
    pos_groups = players["position"].apply(_pos_group).to_numpy()

    total_val = float(vals.sum())
    if total_val <= 0:
        return {}

    # Position-group value sums
    att_val = float(vals[pos_groups == "ATT"].sum())
    def_val = float(vals[pos_groups == "DEF"].sum())
    gk_val  = float(vals[pos_groups == "GK"].sum())

    att_pct = att_val / total_val
    def_pct = def_val / total_val
    tilt    = att_pct - def_pct  # positive = more value in attack

    # Value-weighted age (lower = young roster with money concentrated in young players)
    valid_age = np.isfinite(ages)
    if valid_age.sum() > 0:
        v_ages = vals[valid_age]
        a_ages = ages[valid_age]
        val_wtd_age = float(np.dot(v_ages, a_ages) / v_ages.sum()) if v_ages.sum() > 0 else float(np.nanmean(ages))
        avg_age = float(np.nanmean(ages))
    else:
        val_wtd_age = np.nan
        avg_age = np.nan

    # Top-3 player value concentration (DP proxy / star concentration)
    top3_val = float(np.sort(vals)[::-1][:3].sum())
    dp_value_share = top3_val / total_val

    return {
        "squad_value_eur":  total_val,
        "att_value_pct":    att_pct,
        "def_value_pct":    def_pct,
        "tilt":             tilt,
        "value_wtd_age":    val_wtd_age,
        "avg_age":          avg_age,
        "dp_value_share":   dp_value_share,
        "n_players":        len(players),
        "n_att":            int((pos_groups == "ATT").sum()),
        "n_def":            int((pos_groups == "DEF").sum()),
        "n_gk":             int((pos_groups == "GK").sum()),
    }


def _map_one(season: int, name_map: dict[str, str],
             player_db: dict | None = None) -> tuple[int, int]:
    # Accept both naming conventions: YEAR.csv (from _run_r) and YEAR_raw.csv (manual runs)
    raw = DATA_DIR / f"transfermarkt_squad_values_{season}.csv"
    if not raw.exists() or raw.stat().st_size == 0:
        raw = DATA_DIR / f"transfermarkt_squad_values_{season}_raw.csv"
    if not raw.exists() or raw.stat().st_size == 0:
        print(f"  ! no raw CSV for {season}, skipping")
        return (0, 0)

    players_df = pd.read_csv(raw)
    if players_df.empty:
        print(f"  ! empty raw CSV for {season}, skipping")
        return (0, 0)

    # Ensure required columns exist with sensible defaults
    for col in ("player_name", "position", "market_value_eur", "age", "nationality"):
        if col not in players_df.columns:
            players_df[col] = None

    players_df["market_value_eur"] = pd.to_numeric(players_df["market_value_eur"],
                                                    errors="coerce").fillna(0.0)
    players_df["age"]              = pd.to_numeric(players_df["age"], errors="coerce")

    n_zero_before = int((players_df["market_value_eur"] == 0).sum())

    # Group by team, aggregate to PELE features
    team_rows = []
    for tm_name, grp in players_df.groupby("tm_team_name"):
        asa_id = name_map.get(str(tm_name), "")
        feats = _aggregate_team(grp, player_db=player_db)
        if not feats:
            continue
        row = {
            "season":       season,
            "tm_team_name": tm_name,
            "asa_team_id":  asa_id,
            **feats,
        }
        team_rows.append(row)

    if not team_rows:
        print(f"  ! no valid team rows for {season}")
        return (0, 0)

    out_df = pd.DataFrame(team_rows)
    unmapped = sorted(out_df.loc[out_df["asa_team_id"] == "", "tm_team_name"].unique())
    if unmapped:
        print(f"  Unmapped TM teams ({len(unmapped)}): {unmapped[:8]}"
              f"{' ...' if len(unmapped) > 8 else ''}")

    out = DATA_DIR / f"transfermarkt_squad_values_{season}_mapped.csv"
    out_df.to_csv(out, index=False)
    mapped_n = int((out_df["asa_team_id"] != "").sum())
    n_total = int(players_df["market_value_eur"].count())
    n_filled = n_zero_before - int((players_df["market_value_eur"] == 0).sum())
    if n_zero_before > 0:
        print(f"  Player lookup filled {n_filled}/{n_zero_before} zero-value players "
              f"({n_zero_before/n_total:.0%} of roster had no same-season value)")
    print(f"  → {out.name} ({len(out_df)} teams, {mapped_n} mapped to ASA id)")
    return (len(out_df), mapped_n)


def main() -> int:
    p = argparse.ArgumentParser(description="Import Transfermarkt squad values for MLS")
    p.add_argument("--season",     type=int, help="single season")
    p.add_argument("--seasons",    type=str, help="range like '2017-2025' or comma list")
    p.add_argument("--skip-fetch", action="store_true",
                   help="skip Rscript fetch, only re-aggregate existing raw CSVs")
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

    # Fetch requested seasons first, then build cross-season player lookup
    total, mapped = 0, 0
    for s in seasons:
        print(f"\n=== Season {s} ===")
        if not args.skip_fetch:
            try:
                _run_r(s, DATA_DIR / f"transfermarkt_squad_values_{s}.csv")
            except Exception as e:
                print(f"  ! R fetch failed: {e}", file=sys.stderr)
                continue

    # Build player DB from all raw CSVs (includes seasons just fetched above)
    print("\nBuilding cross-season player valuation index...")
    player_db = _build_player_db(DATA_DIR)
    print(f"  {len(player_db):,} unique players indexed across all seasons")

    for s in seasons:
        print(f"\n=== Aggregating season {s} ===")
        t, m = _map_one(s, name_map, player_db=player_db)
        total += t
        mapped += m

    print(f"\nDone. Total teams: {total} | Mapped to ASA id: {mapped}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
