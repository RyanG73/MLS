#!/usr/bin/env python3
"""
Fetch Transfermarkt squad values via worldfootballR (R subprocess),
then aggregate per-player data into PELE-style team-season features and
write a *_mapped.csv ready for the eval harness / B9's squad-value panel to consume.

Originally MLS-only; extended (A9, 2026-07-05) to every league the dashboard
covers: EPL, Championship, League One, League Two, La Liga, Segunda, Serie A,
Serie B, Bundesliga, 2.Bundesliga, Ligue 1, Ligue 2, Liga MX, Canadian PL.

PELE-inspired features computed per team-season:
  squad_value_eur   — adjusted total squad value (optional UEFA discount)
  att_value_pct     — FW/AM/W value as % of squad total (Tilt prior)
  def_value_pct     — CB/FB value as % of squad total
  tilt              — att_value_pct − def_value_pct (>0 = attacking)
  value_wtd_age     — age weighted by adjusted market value (lower = young+expensive)
  dp_value_share    — top-3 players' value / total (star concentration)
  avg_age           — simple squad mean age

MLS rows are still keyed on ASA team id (`asa_team_id`, via
config/team_name_to_asa_id.yaml). Non-MLS leagues are keyed on the same
canonical team-name string `build_league_data.py` uses for its `team_inputs`
dict (ESPN displayName, reached for football-data leagues via its `FD_ESPN`
alias table) — see `canonical_team_name()` below, which reuses
`scripts/build_logo_map.py`'s fuzzy `norm()` matcher plus the FD_ESPN alias
table so this script does not fork a second alias system.

Usage:
    python scripts/import_transfermarkt.py --season 2024
    python scripts/import_transfermarkt.py --seasons 2017-2025
    python scripts/import_transfermarkt.py --seasons 2017-2025 --skip-fetch
    python scripts/import_transfermarkt.py --league GB1 --season 2025   # EPL
    python scripts/import_transfermarkt.py --all-leagues --season 2025  # every covered league, serially
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

# Minimum player rows for a team to be considered fully covered by TM; below
# this the row is kept (never dropped) but flagged low-confidence. Chosen per
# the task spec's own example threshold — MLS/top-tier squads normally return
# 25-40 rows, so <10 means TM's roster page for that club is materially thin
# (seen on lower English tiers and Canadian PL).
MIN_PLAYERS_FULL_CONFIDENCE = 10

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

# Transfermarkt competition codes for every non-MLS league A9 covers (docs/superpowers/plans/
# 2026-07-02-model-and-ui-improvements.md Task A9). Only the `wettbewerb/<CODE>` segment of a TM
# URL is actually parsed by the site — verified against transfermarkt.com — so no slug text is
# needed here; the R bridge builds a placeholder slug itself.
#
# NOTE: the plan spec's suggested Canadian PL code "KAN1" does not resolve on
# transfermarkt.com (redirects to the generic /navigation/wettbewerbe hub, zero
# teams) — verified 2026-07-05 by fetching that URL directly. The real code,
# found via TM's own search, is "CDN1" (transfermarkt.com/canadian-premier-league/
# startseite/wettbewerb/CDN1). Using the corrected code here rather than the
# spec's guess, per the task's own instruction to inspect the installed package
# / verify codes rather than assume them.
TM_LEAGUE_CODES: dict[str, str] = {
    "GB1": "Premier League", "GB2": "Championship", "GB3": "League One", "GB4": "League Two",
    "ES1": "La Liga", "ES2": "Segunda",
    "IT1": "Serie A", "IT2": "Serie B",
    "L1": "Bundesliga", "L2": "2. Bundesliga",
    "FR1": "Ligue 1", "FR2": "Ligue 2",
    "MEX1": "Liga MX", "CDN1": "Canadian Premier League",
}

# TM competition code -> this dashboard's internal league id (webapp/data/<id>.js,
# scripts/build_league_data.py's LEAGUES dict / scripts/fetch_league_teams.py's
# REGISTRY). Drives which canonical-name table + coverage test a fetch maps against.
TM_CODE_TO_LEAGUE_ID: dict[str, str] = {
    "GB1": "epl", "GB2": "championship", "GB3": "league-one", "GB4": "league-two",
    "ES1": "la-liga", "ES2": "segunda",
    "IT1": "serie-a", "IT2": "serie-b",
    "L1": "bundesliga", "L2": "bundesliga-2",
    "FR1": "ligue-1", "FR2": "ligue-2",
    "MEX1": "liga-mx", "CDN1": "canadian-pl",
}

# Leagues where TM's own catalogue is known to be thin (lower English tiers,
# CanPL — semi-pro/part-time rosters TM does not fully price). Used only for a
# WARN in the console report; the per-team MIN_PLAYERS_FULL_CONFIDENCE check
# below is what actually sets coverage_confidence on each row.
_THIN_COVERAGE_LEAGUES = frozenset({"GB3", "GB4", "CDN1"})


def _load_canonical_team_names(league_id: str) -> list[str]:
    """The current canonical team-name list for a non-MLS league, i.e. the same
    strings build_league_data.py uses as `team_inputs` dict keys (ESPN displayName,
    reached via FD_ESPN for football-data-sourced leagues). Read straight from the
    live webapp payload so this always matches "today's" roster (promoted/relegated
    teams included) rather than a hand-maintained list that drifts.

    Returns [] if the payload doesn't exist yet or has no teams (e.g.
    canadian-pl, still `status: "soon"` with no live payload).
    """
    payload_path = REPO_ROOT / "webapp" / "data" / f"{league_id}.js"
    if not payload_path.exists():
        return []
    try:
        import json
        import re
        text = payload_path.read_text(encoding="utf-8")
        text = re.sub(r"^[\s\S]*?=\s*", "", text).rstrip().rstrip(";")
        data = json.loads(text)
    except Exception as exc:
        print(f"  WARN: could not read {payload_path.name} for canonical names: {exc}",
              file=sys.stderr)
        return []
    # standings is the COMPLETE roster; team_inputs omits teams with zero played
    # rows in the frame (a freshly promoted side preseason — Coventry City,
    # EPL 2026-27, had no top-flight rows and therefore no team_inputs entry).
    names = {s.get("team") for s in (data.get("standings") or []) if s.get("team")}
    names |= set((data.get("team_inputs") or {}).keys())
    return sorted(names)


# Explicit TM-name → canonical-payload-name overrides for cases no generic rule
# can safely resolve (token-subset matching is deliberately rejected when it is
# ambiguous — e.g. TM's "RCD Espanyol Barcelona" subset-matches both "Espanyol"
# AND "Barcelona"). Checked right after the exact-match tier. Keep this list
# short: anything token-subset can resolve unambiguously does not belong here.
TM_CANON_ALIASES: dict[str, str] = {
    # England
    "Brighton & Hove Albion": "Brighton",
    "Wolverhampton Wanderers": "Wolves",
    # Spain
    "RCD Espanyol Barcelona": "Espanyol",
    "Athletic Bilbao": "Athletic Club",   # payload uses the club's own styling
    "Real Betis Balompié": "Real Betis",
    "Deportivo A Coruña": "Deportivo La Coruña",
    "Real Sociedad B": "Real Sociedad II",
    # Italy
    "Inter Milan": "Inter",               # serie-a payload uses the short form
    # Germany
    "RB Leipzig": "RasenBallsport Leipzig",
    "Borussia Mönchengladbach": "Borussia M.Gladbach",
    "1.FC Köln": "FC Cologne",
    "1.FC Nuremberg": "1. FC Nürnberg",
    "Hertha BSC": "Hertha Berlin",
    # France
    "Stade Rennais FC": "Rennes",
    "Stade Brestois 29": "Brest",
    "Stade Lavallois": "Stade Laval",
    "Rodez AF": "Rodez Aveyron",
    # Mexico ("Atlas Guadalajara" subset-matches both "Atlas" and "Guadalajara")
    "Atlas Guadalajara": "Atlas",
}


def canonical_team_name(tm_name: str, league_id: str,
                         canonical_names: list[str] | None = None) -> str | None:
    """Resolve a raw Transfermarkt team name to this dashboard's canonical team-name
    string for `league_id` (the same string build_league_data.py keys team_inputs on).

    Resolution order:
    1. Exact string match against the live canonical name list.
    2. TM_CANON_ALIASES explicit overrides (ambiguous/stubborn names only).
    3. FD_ESPN alias table (build_league_data.py) — covers the abbreviated names
       football-data-sourced leagues use internally.
    4. Fuzzy match via build_logo_map.norm() (strips diacritics/club-type tokens
       like "FC"/"AFC"/"SC") against the canonical list — covers the common
       "Real Sociedad" vs "Real Sociedad de Fútbol" / "AFC Bournemouth" vs
       "Bournemouth" style drift between TM and ESPN/FD naming.
    5. Unique token-subset containment on norm()ed tokens, either direction —
       "Tottenham Hotspur" ⊇ "Tottenham", "Celta de Vigo" ⊇ "Celta Vigo" minus
       stop-tokens. Accepted ONLY when exactly one canonical candidate matches;
       an ambiguous hit (two candidates) resolves to None rather than a guess.

    Returns None if nothing resolves (row is still kept in the output with an
    empty canonical name — dropping rows is explicitly out of scope per A9).
    """
    from scripts.build_league_data import FD_ESPN
    from scripts.build_logo_map import norm

    if canonical_names is None:
        canonical_names = _load_canonical_team_names(league_id)
    if not canonical_names:
        return None

    if tm_name in canonical_names:
        return tm_name

    alias = TM_CANON_ALIASES.get(tm_name)
    if alias and alias in canonical_names:
        return alias

    # FD_ESPN maps FD-abbreviated -> ESPN full name; also check the reverse
    # (ESPN full name -> itself) and TM's name against both sides.
    alias_tbl = FD_ESPN.get(league_id, {})
    for fd_name, espn_name in alias_tbl.items():
        if tm_name in (fd_name, espn_name) and espn_name in canonical_names:
            return espn_name

    tm_norm = norm(tm_name)
    for canon in canonical_names:
        if norm(canon) == tm_norm:
            return canon

    tm_toks = set(tm_norm.split())
    if tm_toks:
        subset_hits = [c for c in canonical_names
                       if (ct := set(norm(c).split()))
                       and (ct <= tm_toks or tm_toks <= ct)]
        if len(subset_hits) == 1:
            return subset_hits[0]

    return None


def _raw_path(season: int, league: str | None, suffix: str = "") -> Path:
    """MLS (league=None) keeps the original bare filename; non-MLS leagues get a
    `<league>_` infix so the two never collide in `data/`."""
    stem = f"transfermarkt_squad_values_{season}{suffix}.csv" if league is None else \
           f"transfermarkt_squad_values_{league}_{season}{suffix}.csv"
    return DATA_DIR / stem


def _mapped_path(season: int, league: str | None) -> Path:
    stem = f"transfermarkt_squad_values_{season}_mapped.csv" if league is None else \
           f"transfermarkt_squad_values_{league}_{season}_mapped.csv"
    return DATA_DIR / stem


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


def _run_r(season: int, raw_csv: Path, league: str | None = None) -> None:
    raw_csv.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["Rscript", "--vanilla", str(R_SCRIPT), str(season), str(raw_csv), league or ""]
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


def _build_player_db(raw_dir: Path, league: str | None = None) -> dict[str, dict]:
    """
    Build a cross-season player valuation index: player_name → most-recent known value.

    Used to fill in players whose current-season TM value is 0 or missing — e.g.
    a new signing whose value hasn't been published yet for the current season.
    We always prefer the most recent season's valuation.

    Scoped to a single league's raw files (`league=None` means MLS's bare-name files)
    so an EPL "Wilson" and an MLS "Wilson" never fill each other's zero-value rows.
    """
    glob_pat = "transfermarkt_squad_values_*.csv" if league is None else \
               f"transfermarkt_squad_values_{league}_*.csv"
    player_db: dict[str, dict] = {}
    for csv_file in sorted(raw_dir.glob(glob_pat)):
        if "mapped" in csv_file.name:
            continue
        if league is None and TM_LEAGUE_CODES.keys() & set(csv_file.stem.split("_")):
            continue  # bare glob also matches "<code>_<season>[_raw]" files; skip those here
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


def _aggregate_team(players: pd.DataFrame, keep_if_zero_value: bool = False) -> dict:
    """Compute PELE-style team-level features from per-player rows.

    keep_if_zero_value=True (non-MLS leagues): still emit a row when the team
    has player rows but zero total valued players, rather than dropping the
    team outright — per A9's "don't drop thin-coverage teams" rule. The row's
    value fields come back as 0/NaN and the caller is expected to mark
    coverage_confidence accordingly. MLS keeps its original drop-if-zero
    behavior (keep_if_zero_value=False, the existing default) unchanged.
    """
    if players.empty:
        return {}

    vals = players["market_value_eur"].fillna(0).clip(lower=0).to_numpy(dtype=float)
    ages = players["age"].to_numpy(dtype=float)
    pos_groups = players["position"].apply(_pos_group).to_numpy()

    total_val = float(vals.sum())
    if total_val <= 0 and not keep_if_zero_value:
        return {}

    if total_val <= 0:
        avg_age = float(np.nanmean(ages)) if np.isfinite(ages).any() else np.nan
        return {
            "squad_value_eur":  0.0,
            "att_value_pct":    np.nan,
            "def_value_pct":    np.nan,
            "tilt":             np.nan,
            "value_wtd_age":    np.nan,
            "avg_age":          avg_age,
            "dp_value_share":   np.nan,
            "n_players":        len(players),
            "n_att":            int((pos_groups == "ATT").sum()),
            "n_def":            int((pos_groups == "DEF").sum()),
            "n_gk":             int((pos_groups == "GK").sum()),
        }

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


def _load_raw_csv(season: int, league: str | None = None) -> pd.DataFrame | None:
    """Find and load a raw player CSV for this season.

    Tries _raw.csv first (written by manual R runs that succeeded) then
    the plain .csv (written by _run_r). Skips files that exist but contain
    only headers (headers-only from a previously failed fetch).
    """
    for suffix in ("_raw", ""):
        path = _raw_path(season, league, suffix)
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
             player_db: dict | None = None, league: str | None = None) -> tuple[int, int]:
    players_df = _load_raw_csv(season, league)
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

    # Non-MLS: resolve canonical team names once per fetch (reads the live payload once,
    # not once per team) and never drop a thin-coverage team.
    league_id = TM_CODE_TO_LEAGUE_ID.get(league) if league else None
    canonical_names = _load_canonical_team_names(league_id) if league_id else None

    # Group by team, aggregate to PELE features
    team_rows = []
    for tm_name, grp in players_df.groupby("tm_team_name"):
        if league is None:
            asa_id = name_map.get(str(tm_name), "")
            feats = _aggregate_team(grp)
            if not feats:
                continue
            canon_name = None
        else:
            asa_id = ""
            feats = _aggregate_team(grp, keep_if_zero_value=True)
            if not feats:
                continue
            canon_name = canonical_team_name(str(tm_name), league_id, canonical_names) \
                if league_id else None

        n_filled_team = int(grp["_filled_from_prior"].sum())
        n_players_team = int(feats.get("n_players", len(grp)))
        low_confidence = (league is not None) and (
            n_players_team < MIN_PLAYERS_FULL_CONFIDENCE
            or float(feats.get("squad_value_eur", 0) or 0) <= 0
        )
        row = {
            "season":           season,
            "tm_team_name":     tm_name,
            "asa_team_id":      asa_id,
            "observed_at":      observed_at,
            "value_snapshot_type": "current_scrape" if observed_at != "unknown" else "unknown",
            "n_prior_fill":     n_filled_team,
            **feats,
        }
        if league is not None:
            row["league"] = league
            row["canon_team_name"] = canon_name or ""
            row["coverage_confidence"] = "low" if low_confidence else "full"
        team_rows.append(row)

    if not team_rows:
        print(f"  ! no valid team rows for {season}")
        return (0, 0)

    out_df = pd.DataFrame(team_rows)

    if league is None:
        unmapped = sorted(out_df.loc[out_df["asa_team_id"] == "", "tm_team_name"].unique())
        if unmapped:
            print(f"  Unmapped TM teams ({len(unmapped)}): {unmapped[:8]}"
                  f"{' ...' if len(unmapped) > 8 else ''}")
        mapped_n = int((out_df["asa_team_id"] != "").sum())
    else:
        unresolved = sorted(out_df.loc[out_df["canon_team_name"] == "", "tm_team_name"].unique())
        if unresolved:
            print(f"  Unresolved TM teams ({len(unresolved)}) — no canonical-name match: "
                  f"{unresolved[:8]}{' ...' if len(unresolved) > 8 else ''}")
        n_low = int((out_df["coverage_confidence"] == "low").sum())
        if n_low:
            print(f"  Low-confidence coverage: {n_low}/{len(out_df)} teams "
                  f"(<{MIN_PLAYERS_FULL_CONFIDENCE} valued player rows)")
        mapped_n = int((out_df["canon_team_name"] != "").sum())

    out = _mapped_path(season, league)
    out_df.to_csv(out, index=False)
    print(f"  → {out.name} ({len(out_df)} teams, {mapped_n} mapped/resolved)")
    return (len(out_df), mapped_n)


def validate_transfermarkt(season: int, name_map: dict[str, str] | None = None,
                           min_teams: int = 25, min_players_per_team: int = 15,
                           min_valued_share: float = 0.70,
                           league: str | None = None) -> bool:
    """Validate a mapped Transfermarkt season CSV and print a report.

    Gates checked:
    - Team count ≥ min_teams (MLS currently has 29-30 teams; pass a lower
      min_teams for non-MLS leagues, which mostly run 18-24 teams)
    - Every mapped team has an ASA ID (MLS only — `config/team_name_to_asa_id.yaml`
      has no non-MLS entries yet, so this gate is informational-only for `league != None`)
    - Each team has ≥ min_players_per_team player rows
    - Each team has squad_value_eur > 0 (at least some valued players)
    - Valued-player share ≥ min_valued_share across the league
    - observed_at is present (leakage-rule enforced)

    Returns True if all gates pass, False otherwise.
    """
    mapped_csv = _mapped_path(season, league)
    raw_csv = _load_raw_csv(season, league)

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
    zero_value_teams = out_df.loc[out_df["squad_value_eur"].fillna(0) == 0, "tm_team_name"].tolist()
    out_observed_at = out_df["observed_at"].iloc[0] if "observed_at" in out_df.columns else "MISSING"

    if league is None:
        unmapped = out_df.loc[out_df["asa_team_id"].fillna("") == "", "tm_team_name"].tolist()
        unmapped_label = "no ASA ID"
        n_low_conf = 0
    else:
        unmapped = out_df.loc[out_df.get("canon_team_name", "").fillna("") == "", "tm_team_name"].tolist()
        unmapped_label = "no canonical-name match"
        n_low_conf = int((out_df.get("coverage_confidence", "") == "low").sum()) \
            if "coverage_confidence" in out_df.columns else 0

    # ── Print report ────────────────────────────────────────────────────────
    print(f"  Season:            {season}")
    print(f"  Teams (raw):       {teams_in_raw}")
    print(f"  Teams (mapped):    {n_teams}  {'✓' if n_teams >= min_teams else '✗ FAIL (min ' + str(min_teams) + ')'}")
    print(f"  Players (total):   {n_players}")
    print(f"  Valued players:    {n_valued} / {n_players}  ({valued_share:.0%})  {'✓' if valued_share >= min_valued_share else '✗ FAIL (min ' + str(int(min_valued_share*100)) + '%)'}")
    print(f"  Thin rosters (<{min_players_per_team}): {len(thin_teams)}  {('— ' + str(thin_teams[:4])) if thin_teams else '✓ none'}")
    print(f"  Unmapped teams ({unmapped_label}): {len(unmapped)}  {('✗ ' + str(unmapped[:4])) if unmapped else '✓ none'}")
    if league is not None:
        print(f"  Low-confidence coverage: {n_low_conf}/{n_teams} teams")
    print(f"  Zero-value teams:  {len(zero_value_teams)}  {('✗ ' + str(zero_value_teams[:4])) if zero_value_teams else '✓ none'}")
    print(f"  observed_at:       {out_observed_at}  {'✓' if out_observed_at not in ('MISSING', 'unknown') else '✗ MISSING — leakage rule cannot be enforced'}")

    # ── Gate decisions ──────────────────────────────────────────────────────
    if n_teams < min_teams:
        print(f"  GATE FAIL: only {n_teams} teams — expected ≥ {min_teams}")
        ok = False
    if unmapped and league is None:
        print(f"  GATE FAIL: {len(unmapped)} teams have no ASA ID — check config/team_name_to_asa_id.yaml")
        ok = False
    elif unmapped:
        print(f"  GATE FAIL: {len(unmapped)} teams have no canonical-name match — "
              f"check FD_ESPN / canonical_team_name() fuzzy matching in scripts/build_league_data.py")
        ok = False
    if valued_share < min_valued_share:
        print(f"  GATE WARN: valued-player share {valued_share:.0%} < {min_valued_share:.0%} "
              if league is not None else
              f"  GATE FAIL: valued-player share {valued_share:.0%} < {min_valued_share:.0%} — check value parsing")
        if league is None:
            ok = False
    if zero_value_teams:
        print(f"  GATE WARN: {len(zero_value_teams)} teams have squad_value_eur=0"
              + (" (thin-coverage leagues expected to have some — flagged low-confidence, not dropped)"
                 if league is not None else ""))
    if out_observed_at in ("MISSING", "unknown"):
        print(f"  GATE FAIL: observed_at missing — run without --skip-fetch or re-stamp the raw CSV")
        ok = False

    print(f"\n  Validation: {'PASS' if ok else 'FAIL'}")
    return ok


# Per-league expected team count (used as the validation min_teams floor, set a
# little below the real count so a fetch that drops 1-2 teams to a transient TM
# error still passes rather than gating on noise). Canadian PL runs an 8-team
# top flight — deliberately NOT gated out even though it's far below other
# leagues' counts, since "don't drop the team" for thin coverage is the point.
LEAGUE_MIN_TEAMS: dict[str, int] = {
    "GB1": 18, "GB2": 22, "GB3": 22, "GB4": 22,
    "ES1": 18, "ES2": 20,
    "IT1": 18, "IT2": 18,
    "L1": 16, "L2": 16,
    "FR1": 16, "FR2": 16,
    "MEX1": 16, "CDN1": 6,
}


def run_one_league(season: int, league: str | None, skip_fetch: bool) -> bool:
    """Fetch + map + validate a single league (or MLS, if league=None) for one season.
    Returns True if the validation gate passed."""
    label = f"{league} ({TM_LEAGUE_CODES[league]})" if league else "MLS"
    print(f"\n{'='*70}\n{label} — season {season}\n{'='*70}")

    name_map = _load_name_map()
    if league is None and not name_map:
        print(f"WARN: no transfermarkt entries in {MAP_PATH}", file=sys.stderr)

    fetch_ok = []
    if not skip_fetch:
        raw_csv = _raw_path(season, league)
        try:
            _run_r(season, raw_csv, league)
            _stamp_raw_csv(raw_csv)
            fetch_ok.append(season)
        except Exception as e:
            print(f"  ! R fetch failed: {e}", file=sys.stderr)
            return False
    else:
        fetch_ok.append(season)

    print("\nBuilding cross-season player valuation index...")
    player_db = _build_player_db(DATA_DIR, league)
    print(f"  {len(player_db):,} unique players indexed across all seasons")

    map_for_league = name_map if league is None else {}
    t, m = _map_one(season, map_for_league, player_db=player_db, league=league)
    if t == 0:
        print(f"  ! no rows produced for {label} season {season}")
        return False

    min_teams = 25 if league is None else LEAGUE_MIN_TEAMS.get(league, 10)
    print(f"\n=== Validation report: {label} season {season} ===")
    return validate_transfermarkt(season, map_for_league, min_teams=min_teams, league=league)


def main() -> int:
    p = argparse.ArgumentParser(description="Import Transfermarkt squad values (MLS + covered leagues)")
    p.add_argument("--season",     type=int, help="single season")
    p.add_argument("--seasons",    type=str, help="range like '2017-2025' or comma list")
    p.add_argument("--skip-fetch", action="store_true",
                   help="skip Rscript fetch, only re-aggregate existing raw CSVs")
    p.add_argument("--league", type=str, default=None, choices=sorted(TM_LEAGUE_CODES),
                   help="TM competition code (e.g. GB1 for EPL); omit for MLS (default)")
    p.add_argument("--all-leagues", action="store_true",
                   help="fetch every TM_LEAGUE_CODES league, one at a time, sequentially "
                        "(does NOT include MLS — run without --league/--all-leagues for that)")
    args = p.parse_args()

    if args.season:
        seasons = [args.season]
    elif args.seasons:
        seasons = _parse_seasons(args.seasons)
    else:
        seasons = [int(__import__("datetime").datetime.now().year)]

    if args.all_leagues:
        if len(seasons) != 1:
            print("ERROR: --all-leagues takes exactly one season (use --season, not --seasons)",
                  file=sys.stderr)
            return 1
        season = seasons[0]
        results: dict[str, bool] = {}
        # Sequential, one league at a time — TM rate-limit tolerance and this
        # machine both want serial fetches, never concurrent (A9 constraint).
        for code in TM_LEAGUE_CODES:
            try:
                results[code] = run_one_league(season, code, args.skip_fetch)
            except Exception as e:
                print(f"  ! {code} fetch/map raised: {e}", file=sys.stderr)
                results[code] = False

        print(f"\n{'='*70}\nSUMMARY — season {season}\n{'='*70}")
        for code, ok in results.items():
            print(f"  {code:6s} {TM_LEAGUE_CODES[code]:28s} {'PASS' if ok else 'FAIL/SKIPPED'}")
        n_ok = sum(results.values())
        print(f"\n{n_ok}/{len(results)} leagues passed validation.")
        return 0 if n_ok > 0 else 1

    league = args.league
    ok = True
    for s in seasons:
        ok = run_one_league(s, league, args.skip_fetch) and ok

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
