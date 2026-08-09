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
    # Round-4 Tier-1 (2026-07-11). football-data "new leagues" CSVs, Pinnacle
    # closings back to ~2012. ESPN aut.1/sui.1/rou.1/irl.1 verified live.
    # NB: Switzerland's football-data code is SWZ, not SUI (report erratum).
    "austria-bundesliga": "AUT",
    "swiss-super-league": "SWZ",
    "romania-liga1": "ROU",
    "ireland-premier": "IRL",
    # Round-4 projection-only (2026-07-11). Odds columns retained as a future
    # edge-layer backbone; presented projection-only for now.
    "china-super": "CHN",
    "russia-premier": "RUS",
    # Round-4 Phase 3 (2026-07-11): results+odds from football-data; upcoming
    # fixtures via API-Football (ESPN fin.1 is empty). See build_league_data.FIXTURE_OVERRIDE.
    "finland-veikkausliiga": "FIN",
}

# poland-ekstraklasa: confirmed 2026-07-10 (docs/league-expansion-report.md) —
# no ESPN slug found under any plausible guess, so it has no live schedule
# source. Ships in results-only mode (no in-season projection) until a
# fixture source is found; excluded from PRESEASON_ESPN_LEAGUES so the
# builder never tries to fetch a schedule that doesn't exist.
NO_ESPN_SCHEDULE = {"poland-ekstraklasa", "finland-veikkausliiga"}

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


# ── competition filter ───────────────────────────────────────────────────────
# `new/<CCC>.csv` is a COUNTRY file, not a competition file, and until 2026-08-08
# this adapter filtered on season alone — it never read the `League` column its
# own CSVs carry. Two of the fourteen mix competitions:
#
#   ARG  Liga Profesional 5,360 + Copa De La Liga Profesional 920
#   SWZ  Super League 2,685 + Challenge League 2
#
# and five (ARG, DNK, FIN, IRL, SWE) carry a TRAILING-SPACE variant of their own
# name, which is an era split rather than a second competition — football-data
# renamed the column value mid-history. `'Liga Profesional '` alone is 2,114
# rows, a third of the Argentine file, so an exact-match filter would silently
# delete a third of the league. Compare normalised, never raw.
_WS_RE = re.compile(r"\s+")


def _norm_competition(value) -> str:
    """Competition label → comparison key: whitespace-collapsed, casefolded."""
    return _WS_RE.sub(" ", str(value)).strip().casefold()


# Competitions whose results ARE this league — they count toward the table.
LEAGUE_COMPETITIONS: dict[str, frozenset[str]] = {
    "brazil-serie-a":        frozenset({"serie a"}),
    "japan-j1":              frozenset({"j1 league"}),
    "sweden-allsvenskan":    frozenset({"allsvenskan"}),
    "norway-eliteserien":    frozenset({"eliteserien"}),
    "denmark-superliga":     frozenset({"superliga"}),
    "poland-ekstraklasa":    frozenset({"ekstraklasa"}),
    "argentina-primera":     frozenset({"liga profesional"}),
    "austria-bundesliga":    frozenset({"bundesliga"}),
    "swiss-super-league":    frozenset({"super league"}),
    "romania-liga1":         frozenset({"superliga"}),
    "ireland-premier":       frozenset({"premier division"}),
    "china-super":           frozenset({"super league"}),
    "russia-premier":        frozenset({"premier league"}),
    "finland-veikkausliiga": frozenset({"veikkausliiga"}),
}

# Competitions contested by the SAME top-flight clubs that are not league-table
# fixtures. Kept in the frame (ELO and Dixon-Coles read every played row) and
# marked `is_playoff=1`, which is the flag build_league_data already filters on
# for the points table and the table simulation.
#
# Argentina's Copa de la Liga Profesional is the only entry, and it is a
# deliberate KEEP rather than a drop. It is not an open cup on the Copa
# Argentina model: since 2020 it is one of the two top-flight championships,
# entered only by Primera clubs. Dropping it would delete the whole of 2020
# (134 Copa rows, and no Liga rows at all that year) and would split the
# history, because from 2025 football-data stopped distinguishing the two and
# files everything as `Liga Profesional` — 510 rows in 2025 with pairs meeting
# up to three times. Keeping it out of the table but inside the rating history
# is the only treatment that stays consistent across both eras.
NON_LEAGUE_COMPETITIONS: dict[str, frozenset[str]] = {
    "argentina-primera": frozenset({"copa de la liga profesional"}),
}

# Competitions present in a country file that are NOT this league's data at all.
# Listed rather than merely unlisted so the drop is a recorded decision and so
# the guard below can tell a known stray from a competition football-data has
# renamed under us — the latter is the failure worth shouting about.
#
# Switzerland's two 'Challenge League' rows are the Thun-Sion promotion/
# relegation barrage of 27 and 30 May 2021, filed by football-data under the
# second tier. Super League 2020/21 already carries its full 180 rows without
# them, so they are a two-legged tie between divisions, not missing league data.
FOREIGN_COMPETITIONS: dict[str, frozenset[str]] = {
    "swiss-super-league": frozenset({"challenge league"}),
}


def _select_competitions(df: pd.DataFrame, league_id: str) -> pd.DataFrame:
    """Restrict a country CSV to the competitions `league_id` declares.

    Returns the frame with foreign-competition rows removed and a `_non_league`
    boolean marking same-tier rows that must stay out of the league table.

    Rows are never dropped silently: an unclassified competition is logged with
    its own before/after counts, and a filter that matches NOTHING raises rather
    than handing back an empty league — the failure mode this guard exists to
    prevent is a mis-specified filter quietly halving a country's history.
    A file that declares no `League` column at all is passed through untouched;
    absence of evidence must not delete data.
    """
    league = LEAGUE_COMPETITIONS[league_id]
    non_league = NON_LEAGUE_COMPETITIONS.get(league_id, frozenset())
    out = df.copy()
    if out.empty or "League" not in out.columns:
        out["_non_league"] = False
        return out

    foreign = FOREIGN_COMPETITIONS.get(league_id, frozenset())
    key = out["League"].map(_norm_competition)
    is_league, is_non_league = key.isin(league), key.isin(non_league)
    unknown = ~(is_league | is_non_league | key.isin(foreign))
    if not is_league.any():
        raise ValueError(
            f"football-data-intl {league_id}: no rows match the declared "
            f"competition(s) {sorted(league)} — file declares "
            f"{sorted(key.unique())}. Refusing to return an empty league.")
    if unknown.any():
        logger.warning(
            "football-data-intl %s: %d of %d rows are from UNDECLARED "
            "competition(s) %s — dropped. If football-data renamed a "
            "competition, classify it in this module.", league_id,
            int(unknown.sum()), len(out),
            {k: int(v) for k, v in key[unknown].value_counts().items()})
    drop = unknown | key.isin(foreign)
    out = out[~drop].copy()
    out["_non_league"] = is_non_league[~drop].to_numpy()
    return out


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
        df = pd.read_csv(io.StringIO(r.text))
    except Exception as e:
        logger.warning("football-data new-leagues %s fetch failed (%s)", country, e)
        from data_pipeline.source_health import record_fetch
        if use_cache and raw_path.exists():
            try:
                cached = pd.read_csv(raw_path)
            except Exception:
                pass
            else:
                # Served from a stale cache. Recorded as a FAILURE on purpose:
                # the build succeeds, but the feed did not answer, and that is
                # precisely the state that is otherwise invisible — a run looks
                # green while its data quietly ages. (2026-08-08)
                record_fetch("football_data_intl", f"{country}.csv", ok=False,
                             raw=len(cached), error=f"served from cache: {e}")
                return cached
        record_fetch("football_data_intl", f"{country}.csv", ok=False, error=str(e))
        return None
    from data_pipeline.source_health import record_fetch
    record_fetch("football_data_intl", f"{country}.csv", ok=True, raw=len(df))
    return df


def _parse_results(df: pd.DataFrame, league_id: str) -> pd.DataFrame:
    """Full multi-season CSV → canonical rows (goals, xG=NaN).

    Drops rows missing team names, a result (HG/AG NaN — e.g. Brazil's single
    suspended Chapecoense-SC fixture, Nov 2016), or an unparseable season, and
    rows belonging to a competition `league_id` does not declare.
    """
    df = _select_competitions(df, league_id)
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
            "is_result": True, "is_playoff": int(bool(r["_non_league"])),
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
    df = _coerce(_parse_results(csv, league_id))
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

    Returns columns: season, date, home_team, away_team, mkt_home, mkt_draw,
    mkt_away. Rows without usable odds are dropped, as are rows from a
    competition `league_id` does not declare.

    `date` is carried because (season, home, away) is NOT a unique key in 9 of
    the 14 countries. Split-year leagues play a pair two to four times a season
    at the same venue, and Argentina adds meetings across the Liga/Copa boundary
    and, since the 2025 Apertura-Clausura format, inside the Liga itself.
    """
    csv = _fetch_csv(COUNTRY[league_id])
    if csv is None:
        return pd.DataFrame(columns=["season", "date", "home_team", "away_team",
                                     "mkt_home", "mkt_draw", "mkt_away"])
    out = []
    for _, r in _select_competitions(csv, league_id).iterrows():
        season = _season_int(r.get("Season"))
        ht, at = r.get("Home"), r.get("Away")
        if season is None or pd.isna(ht) or pd.isna(at):
            continue
        if seasons is not None and season not in seasons:
            continue
        mp = _devig_row(r)
        if mp is None:
            continue
        out.append({"season": season,
                    "date": pd.to_datetime(r.get("Date"), dayfirst=True,
                                           errors="coerce"),
                    "home_team": ht, "away_team": at,
                    "mkt_home": mp[0], "mkt_draw": mp[1], "mkt_away": mp[2]})
    return pd.DataFrame(out, columns=["season", "date", "home_team", "away_team",
                                      "mkt_home", "mkt_draw", "mkt_away"])


def attach_market(frame: pd.DataFrame, league_id: str,
                  seasons: list[int] | None = None) -> pd.DataFrame:
    """Left-merge market probs onto a canonical frame, never changing its size.

    Merges on (season, date, home, away) when the caller's frame carries a
    date. Without one the key is not unique — build_league_data slices to
    `[season, home_team, away_team]` for its per-game lookup — so the market
    side is collapsed to one row per key first. Either way the left-merge
    cannot multiply the caller's rows, which it silently did until 2026-08-08
    for 9 of the 14 leagues — ~15,500 duplicate rows carrying another fixture's
    closing odds (swiss 2,685 -> 5,253, austria 2,644 -> 4,732, ireland
    2,692 -> 4,802, and six more).
    """
    mk = market_probs(league_id, seasons)
    out = frame.copy()
    if mk.empty:
        out[["mkt_home", "mkt_draw", "mkt_away"]] = np.nan
        return out
    keys = ["season", "home_team", "away_team"]
    if "date" in out.columns and pd.api.types.is_datetime64_any_dtype(out["date"]):
        keys.append("date")
    else:
        mk = mk.drop_duplicates(subset=keys)
    return out.merge(mk[keys + ["mkt_home", "mkt_draw", "mkt_away"]],
                     on=keys, how="left")


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
