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
from datetime import datetime, timezone
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


def _stamp_raw_csv(raw_csv: Path) -> None:
    """Add observed_at and value_snapshot_type columns to a freshly-fetched raw CSV.

    These columns enforce the leakage rule: a match may only use values where
    observed_at < match_date.  Called immediately after _run_r() succeeds so the
    timestamp reflects the actual scrape time, not a later aggregation run.
    """
    if not raw_csv.exists() or raw_csv.stat().st_size == 0:
        return
    try:
        df = pd.read_csv(raw_csv)
        if df.empty:
            return
        now_iso = datetime.now(timezone.utc).isoformat()
        df["observed_at"] = now_iso
        df["value_snapshot_type"] = "current_scrape"
        df.to_csv(raw_csv, index=False)
    except Exception as exc:
        print(f"  WARN: could not stamp {raw_csv.name}: {exc}", file=sys.stderr)


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


def _aggregate_team(players: pd.DataFrame) -> dict:
    """Compute PELE-style team-level features from per-player rows."""
    if players.empty:
        return {}

    vals = players["market_value_eur"].fillna(0).clip(lower=0).to_numpy(dtype=float)
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


def _load_raw_csv(season: int) -> pd.DataFrame | None:
    """Find and load a raw player CSV for this season.

    Tries _raw.csv first (written by manual R runs that succeeded) then
    the plain .csv (written by _run_r). Skips files that exist but contain
    only headers (headers-only from a previously failed fetch).
    """
    for suffix in ("_raw", ""):
        path = DATA_DIR / f"transfermarkt_squad_values_{season}{suffix}.csv"
        if not path.exists() or path.stat().st_size == 0:
            continue
        try:
            df = pd.read_csv(path)
            if not df.empty:
                return df
        except Exception:
            continue
    return None


def _map_one(season: int, name_map: dict[str, str],
             player_db: dict | None = None) -> tuple[int, int]:
    players_df = _load_raw_csv(season)
    if players_df is None:
        print(f"  ! no raw CSV for {season}, skipping")
        return (0, 0)

    # Carry observed_at from the raw CSV if stamped; fall back to "unknown"
    observed_at = "unknown"
    if "observed_at" in players_df.columns and not players_df["observed_at"].isna().all():
        observed_at = str(players_df["observed_at"].iloc[0])

    # Ensure required columns exist with sensible defaults
    for col in ("player_name", "position", "market_value_eur", "age", "nationality"):
        if col not in players_df.columns:
            players_df[col] = None

    players_df["market_value_eur"] = pd.to_numeric(players_df["market_value_eur"],
                                                    errors="coerce").fillna(0.0)
    players_df["age"]              = pd.to_numeric(players_df["age"], errors="coerce")

    # Track which players are filled from prior-season data for value_source
    players_df["_filled_from_prior"] = False

    # Fill zero-value players from cross-season player lookup directly on the DataFrame
    # so that the fill is reflected in the aggregation and in the coverage report.
    n_zero_before = int((players_df["market_value_eur"] == 0).sum())
    if player_db and n_zero_before > 0:
        zero_mask = players_df["market_value_eur"] == 0
        for idx in players_df.index[zero_mask]:
            name = str(players_df.at[idx, "player_name"] or "").strip()
            entry = player_db.get(name)
            if entry:
                players_df.at[idx, "market_value_eur"] = entry["value"]
                players_df.at[idx, "_filled_from_prior"] = True

    n_filled = n_zero_before - int((players_df["market_value_eur"] == 0).sum())
    n_total  = len(players_df)
    if n_zero_before > 0:
        print(f"  Player lookup filled {n_filled}/{n_zero_before} zero-value players "
              f"({n_zero_before/n_total:.0%} of roster had no same-season value)")

    # Group by team, aggregate to PELE features
    team_rows = []
    for tm_name, grp in players_df.groupby("tm_team_name"):
        asa_id = name_map.get(str(tm_name), "")
        feats = _aggregate_team(grp)
        if not feats:
            continue
        n_filled_team = int(grp["_filled_from_prior"].sum())
        row = {
            "season":           season,
            "tm_team_name":     tm_name,
            "asa_team_id":      asa_id,
            "observed_at":      observed_at,
            "value_snapshot_type": "current_scrape" if observed_at != "unknown" else "unknown",
            "n_prior_fill":     n_filled_team,
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
    print(f"  → {out.name} ({len(out_df)} teams, {mapped_n} mapped to ASA id)")
    return (len(out_df), mapped_n)


def validate_transfermarkt(season: int, name_map: dict[str, str] | None = None,
                           min_teams: int = 25, min_players_per_team: int = 15,
                           min_valued_share: float = 0.70) -> bool:
    """Validate a mapped Transfermarkt season CSV and print a report.

    Gates checked:
    - Team count ≥ min_teams (MLS currently has 29-30 teams)
    - Every mapped team has an ASA ID
    - Each team has ≥ min_players_per_team player rows
    - Each team has squad_value_eur > 0 (at least some valued players)
    - Valued-player share ≥ min_valued_share across the league
    - observed_at is present (leakage-rule enforced)

    Returns True if all gates pass, False otherwise.
    """
    mapped_csv = DATA_DIR / f"transfermarkt_squad_values_{season}_mapped.csv"
    raw_csv = _load_raw_csv(season)

    ok = True

    # ── Raw player data checks ──────────────────────────────────────────────
    if raw_csv is None:
        print(f"  FAIL: no raw CSV found for season {season}")
        return False

    n_players = len(raw_csv)
    teams_in_raw = raw_csv["tm_team_name"].nunique() if "tm_team_name" in raw_csv.columns else 0
    has_observed_at = "observed_at" in raw_csv.columns and not raw_csv["observed_at"].isna().all()

    if "market_value_eur" in raw_csv.columns:
        raw_csv["market_value_eur"] = pd.to_numeric(raw_csv["market_value_eur"], errors="coerce").fillna(0)
        n_valued = int((raw_csv["market_value_eur"] > 0).sum())
        valued_share = n_valued / n_players if n_players > 0 else 0.0
        players_per_team = raw_csv.groupby("tm_team_name").size() if "tm_team_name" in raw_csv.columns else pd.Series(dtype=int)
        thin_teams = players_per_team[players_per_team < min_players_per_team].index.tolist() if not players_per_team.empty else []
    else:
        n_valued, valued_share, thin_teams = 0, 0.0, []

    # ── Mapped team-level checks ────────────────────────────────────────────
    if not mapped_csv.exists():
        print(f"  FAIL: mapped CSV not found: {mapped_csv.name}")
        return False

    out_df = pd.read_csv(mapped_csv)
    n_teams = len(out_df)
    unmapped = out_df.loc[out_df["asa_team_id"].fillna("") == "", "tm_team_name"].tolist()
    zero_value_teams = out_df.loc[out_df["squad_value_eur"].fillna(0) == 0, "tm_team_name"].tolist()
    out_observed_at = out_df["observed_at"].iloc[0] if "observed_at" in out_df.columns else "MISSING"

    # ── Print report ────────────────────────────────────────────────────────
    print(f"  Season:            {season}")
    print(f"  Teams (raw):       {teams_in_raw}")
    print(f"  Teams (mapped):    {n_teams}  {'✓' if n_teams >= min_teams else '✗ FAIL (min ' + str(min_teams) + ')'}")
    print(f"  Players (total):   {n_players}")
    print(f"  Valued players:    {n_valued} / {n_players}  ({valued_share:.0%})  {'✓' if valued_share >= min_valued_share else '✗ FAIL (min ' + str(int(min_valued_share*100)) + '%)'}")
    print(f"  Thin rosters (<{min_players_per_team}): {len(thin_teams)}  {('— ' + str(thin_teams[:4])) if thin_teams else '✓ none'}")
    print(f"  Unmapped teams:    {len(unmapped)}  {('✗ ' + str(unmapped[:4])) if unmapped else '✓ none'}")
    print(f"  Zero-value teams:  {len(zero_value_teams)}  {('✗ ' + str(zero_value_teams[:4])) if zero_value_teams else '✓ none'}")
    print(f"  observed_at:       {out_observed_at}  {'✓' if out_observed_at not in ('MISSING', 'unknown') else '✗ MISSING — leakage rule cannot be enforced'}")

    # ── Gate decisions ──────────────────────────────────────────────────────
    if n_teams < min_teams:
        print(f"  GATE FAIL: only {n_teams} teams — expected ≥ {min_teams}")
        ok = False
    if unmapped:
        print(f"  GATE FAIL: {len(unmapped)} teams have no ASA ID — check config/team_name_to_asa_id.yaml")
        ok = False
    if valued_share < min_valued_share:
        print(f"  GATE FAIL: valued-player share {valued_share:.0%} < {min_valued_share:.0%} — check value parsing")
        ok = False
    if zero_value_teams:
        print(f"  GATE WARN: {len(zero_value_teams)} teams have squad_value_eur=0")
    if out_observed_at in ("MISSING", "unknown"):
        print(f"  GATE FAIL: observed_at missing — run without --skip-fetch or re-stamp the raw CSV")
        ok = False

    print(f"\n  Validation: {'PASS' if ok else 'FAIL'}")
    return ok


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
    fetch_ok = []
    for s in seasons:
        print(f"\n=== Season {s} ===")
        if not args.skip_fetch:
            raw_csv = DATA_DIR / f"transfermarkt_squad_values_{s}.csv"
            try:
                _run_r(s, raw_csv)
                _stamp_raw_csv(raw_csv)
                fetch_ok.append(s)
            except Exception as e:
                print(f"  ! R fetch failed: {e}", file=sys.stderr)
                continue
        else:
            fetch_ok.append(s)

    # Build player DB from all raw CSVs (includes seasons just fetched above)
    print("\nBuilding cross-season player valuation index...")
    player_db = _build_player_db(DATA_DIR)
    print(f"  {len(player_db):,} unique players indexed across all seasons")

    for s in fetch_ok:
        print(f"\n=== Aggregating season {s} ===")
        t, m = _map_one(s, name_map, player_db=player_db)
        total += t
        mapped += m

    print(f"\nDone. Total teams: {total} | Mapped to ASA id: {mapped}")

    # Validate the most recently processed season
    if fetch_ok:
        last_season = fetch_ok[-1]
        print(f"\n=== Validation report: season {last_season} ===")
        validate_transfermarkt(last_season, name_map)

    return 0


if __name__ == "__main__":
    sys.exit(main())
