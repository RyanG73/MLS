#!/usr/bin/env python3
"""football-data.co.uk "new leagues" adapter — Brazil/Japan/Nordics/Poland/Argentina.

This is a DIFFERENT file format from `data_pipeline.football_data` (the big-5 +
European 2nd-tier adapter): instead of one CSV per season at
`mmz4281/<season>/<DIV>.csv`, each of these countries publishes ONE CSV with
every season stacked at `new/<CCC>.csv` (`Country, League, Season, Date, Time,
Home, Away, HG, AG, Res, PSCH/PSCD/PSCA (Pinnacle CLOSING), Max/Avg/BFE/B365...`).
Verified live 2026-07-10 across all 7 candidates in
docs/league-expansion-report.md: identical 25-column schema, DD/MM/YYYY dates,
Pinnacle-closing coverage ~100% back to 2012 (dropping only for the
in-progress/future tail). Two gotchas found in that probe, handled here:
  - the file is RESULTS ONLY — it does not carry upcoming fixtures, so a
    schedule source (ESPN) is still required for live projections, same as
    the existing footballdata second-tier leagues.
  - Japan's CSV has a typo column ("B36CA" instead of "B365CA") — the
    Bet365-fallback odds set is looked up defensively and simply unavailable
    for that one country, never a crash.

`Season` is a plain year ("2012") for calendar-year leagues (Brazil, Japan,
Sweden, Norway) and a split year ("2012/2013") for Aug-May leagues (Denmark,
Poland, Argentina — Argentina's format also churns between the two across
eras, per the expansion report's Tier-1 caveat); `_season_int` extracts the
first four-digit year from either form.

Usage:
    python -m data_pipeline.football_data_intl --league brazil-serie-a --results
"""
from __future__ import annotations

import argparse
import io
import logging
import re
from pathlib import Path

import numpy as np
import pandas as pd
import requests

from data_pipeline.understat import _COLS, _coerce

logger = logging.getLogger("football_data_intl")

_BASE = "https://www.football-data.co.uk/new"
_HDR = {"User-Agent": "Mozilla/5.0"}
_RAW_CACHE_DIR = Path("data/football_data_intl/raw")
_RESULTS_CACHE_DIR = Path("data/football_data_intl")

# Platform league id → football-data country code.
COUNTRY: dict[str, str] = {
    "brazil-serie-a": "BRA",
    "japan-j1": "JPN",
    "sweden-allsvenskan": "SWE",
    "norway-eliteserien": "NOR",
    "denmark-superliga": "DNK",
    "poland-ekstraklasa": "POL",
    "argentina-primera": "ARG",
}

# poland-ekstraklasa: confirmed 2026-07-10 (docs/league-expansion-report.md) —
# no ESPN slug found under any plausible guess, so it has no live schedule
# source. Ships in results-only mode (no in-season projection) until a
# fixture source is found; excluded from PRESEASON_ESPN_LEAGUES so the
# builder never tries to fetch a schedule that doesn't exist.
NO_ESPN_SCHEDULE = {"poland-ekstraklasa"}

# Odds-column triples in preference order: Pinnacle CLOSING (sharpest, this
# file's headline column) → market max → market average → BetFair exchange →
# Bet365. Missing columns (e.g. Japan's B36CA typo) resolve to NaN, not a crash.
_ODDS_SETS = [("PSCH", "PSCD", "PSCA"), ("MaxCH", "MaxCD", "MaxCA"),
              ("AvgCH", "AvgCD", "AvgCA"), ("BFECH", "BFECD", "BFECA"),
              ("B365CH", "B365CD", "B365CA")]

_YEAR_RE = re.compile(r"(\d{4})")


def _season_int(season_str) -> int | None:
    """'2012' or '2012/2013' → 2012. Unparseable → None (row dropped)."""
    m = _YEAR_RE.search(str(season_str))
    return int(m.group(1)) if m else None


def _fetch_csv(country: str, use_cache: bool = True) -> pd.DataFrame | None:
    """Fetch the single all-seasons CSV for a country, disk-cached.

    Unlike the per-season files in `football_data.py`, this file is a live,
    ever-growing document — every call attempts a live refetch UNLESS
    use_cache=True finds a cached copy AND the live fetch fails (network
    resilience: a stalled football-data.co.uk falls back to the last good
    cache rather than blocking a build).
    """
    raw_path = _RAW_CACHE_DIR / f"{country}.csv"
    try:
        r = requests.get(f"{_BASE}/{country}.csv", headers=_HDR, timeout=(10, 30))
        r.raise_for_status()
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        raw_path.write_text(r.text)
        return pd.read_csv(io.StringIO(r.text))
    except Exception as e:
        logger.warning("football-data new-leagues %s fetch failed (%s)", country, e)
        if use_cache and raw_path.exists():
            try:
                return pd.read_csv(raw_path)
            except Exception:
                pass
        return None


def _parse_results(df: pd.DataFrame) -> pd.DataFrame:
    """Full multi-season CSV → canonical rows (goals, xG=NaN).

    Drops rows missing team names, a result (HG/AG NaN — e.g. Brazil's single
    suspended Chapecoense-SC fixture, Nov 2016), or an unparseable season.
    """
    out = []
    for _, r in df.iterrows():
        ht, at, hg, ag = r.get("Home"), r.get("Away"), r.get("HG"), r.get("AG")
        season = _season_int(r.get("Season"))
        if pd.isna(ht) or pd.isna(at) or pd.isna(hg) or pd.isna(ag) or season is None:
            continue
        hg, ag = int(hg), int(ag)
        date = pd.to_datetime(r.get("Date"), dayfirst=True, errors="coerce")
        if pd.isna(date):
            continue
        out.append({
            "match_id": f"fdintl-{season}-{ht}-{at}-{date.strftime('%Y%m%d')}".replace(" ", "_"),
            "date": date, "season": season, "home_team": ht, "away_team": at,
            "home_goals": hg, "away_goals": ag, "home_xg": np.nan, "away_xg": np.nan,
            "label_result": 0 if hg > ag else (1 if hg == ag else 2),
            "is_result": True, "is_playoff": 0,
        })
    return pd.DataFrame(out, columns=_COLS)


def match_results(league_id: str, seasons: list[int] | None = None,
                  use_cache: bool = True) -> pd.DataFrame:
    """Canonical goals-only match frame, parquet-cached like football_data.match_results.

    RESULTS ONLY — see the module docstring; upcoming fixtures come from ESPN
    (data_pipeline.espn_fixtures) except for NO_ESPN_SCHEDULE leagues.
    """
    if league_id not in COUNTRY:
        raise ValueError(f"Unknown football-data-intl league '{league_id}'. "
                         f"Known: {', '.join(COUNTRY)}")
    csv = _fetch_csv(COUNTRY[league_id], use_cache=use_cache)
    if csv is None:
        cache_path = _RESULTS_CACHE_DIR / f"{league_id}.parquet"
        if use_cache and cache_path.exists():
            df = pd.read_parquet(cache_path)
            df["date"] = pd.to_datetime(df["date"])
            return df if seasons is None else df[df["season"].isin(seasons)]
        return pd.DataFrame(columns=_COLS)
    df = _coerce(_parse_results(csv))
    df = df.sort_values("date").reset_index(drop=True)
    cache_path = _RESULTS_CACHE_DIR / f"{league_id}.parquet"
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(cache_path, index=False)
    return df if seasons is None else df[df["season"].isin(seasons)]


def _devig_row(row) -> tuple[float, float, float] | None:
    for h, d, a in _ODDS_SETS:
        oh, od, oa = row.get(h), row.get(d), row.get(a)
        if pd.notna(oh) and pd.notna(od) and pd.notna(oa) and min(oh, od, oa) > 1:
            ih, idr, ia = 1.0 / oh, 1.0 / od, 1.0 / oa
            s = ih + idr + ia
            return ih / s, idr / s, ia / s
    return None


def market_probs(league_id: str, seasons: list[int] | None = None) -> pd.DataFrame:
    """De-vigged Pinnacle-closing [home,draw,away] probs per match.

    Returns columns: season, home_team, away_team, mkt_home, mkt_draw, mkt_away.
    Rows without usable odds are dropped.
    """
    csv = _fetch_csv(COUNTRY[league_id])
    if csv is None:
        return pd.DataFrame(columns=["season", "home_team", "away_team",
                                     "mkt_home", "mkt_draw", "mkt_away"])
    out = []
    for _, r in csv.iterrows():
        season = _season_int(r.get("Season"))
        ht, at = r.get("Home"), r.get("Away")
        if season is None or pd.isna(ht) or pd.isna(at):
            continue
        if seasons is not None and season not in seasons:
            continue
        mp = _devig_row(r)
        if mp is None:
            continue
        out.append({"season": season, "home_team": ht, "away_team": at,
                    "mkt_home": mp[0], "mkt_draw": mp[1], "mkt_away": mp[2]})
    return pd.DataFrame(out)


def attach_market(frame: pd.DataFrame, league_id: str,
                  seasons: list[int] | None = None) -> pd.DataFrame:
    """Left-merge market probs onto a canonical frame by (season, home, away)."""
    mk = market_probs(league_id, seasons)
    out = frame.copy()
    if mk.empty:
        out[["mkt_home", "mkt_draw", "mkt_away"]] = np.nan
        return out
    return out.merge(mk, on=["season", "home_team", "away_team"], how="left")


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--league", choices=list(COUNTRY), required=True)
    ap.add_argument("--results", action="store_true",
                    help="show the goals-only canonical frame instead of market odds")
    a = ap.parse_args()
    if a.results:
        df = match_results(a.league)
        played = df[df["is_result"]]
        res = played["label_result"].value_counts(normalize=True).sort_index()
        print(f"{a.league}: {len(played)} results across {sorted(played['season'].unique())} | "
              f"teams {played['home_team'].nunique()} | "
              f"H/D/A {res.get(0,0):.0%}/{res.get(1,0):.0%}/{res.get(2,0):.0%}")
        print(played[["date", "season", "home_team", "away_team",
                      "home_goals", "away_goals"]].tail(5).to_string())
    else:
        mk = market_probs(a.league)
        print(f"{a.league}: {len(mk)} matches with market odds")
        if not mk.empty:
            print(mk.tail(5).to_string())
