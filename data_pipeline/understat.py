#!/usr/bin/env python3
"""
Understat per-league match adapter — DB-free, parquet-backed.

Fetches per-match expected-goals data for the big-5 European leagues via the
`understatapi` library and produces the **canonical match frame** the model
already consumes for MLS (the ASA schema), so the league-agnostic model code
below the fetch layer needs no changes:

    match_id, date, season, home_team, away_team,
    home_goals, away_goals, home_xg, away_xg,
    label_result (0 home / 1 draw / 2 away), is_result, is_playoff (0)

Why Understat: direct page scraping is walled (the HTML ships stripped of the
embedded JSON), but the library's fetch path returns per-match goals + xG for
every big-5 league back to **2014** — three more seasons than MLS's 2017+.
European seasons are keyed by START year (Understat "2023" = the 2023-24
campaign); we store that start year as the integer `season`, which is all the
walk-forward split needs.

Team identity: the model uses `home_team`/`away_team` as opaque categorical
keys, so Understat titles are fed straight through. Logo alignment with ESPN
crests is a separate, best-effort concern — `espn_name()` maps the handful of
titles that differ from ESPN's displayName (accents, dropped FC/AC prefixes,
"United"/"Hotspur" suffixes); everything else is assumed identical.

Caching: one parquet per league at data/understat/<league_id>.parquet. Complete
historical seasons are fetched once and never re-pulled; the latest (possibly
in-progress) season is refreshed each run so new results land.

Usage:
    python -m data_pipeline.understat --league epl        # fetch + report one
    python -m data_pipeline.understat --all               # all big-5
    python -m data_pipeline.understat --league epl --no-cache  # ignore parquet
"""

from __future__ import annotations

import argparse
import logging
import unicodedata
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

logger = logging.getLogger("understat")

# Platform league id → Understat league code (the library's `league=` argument).
UNDERSTAT_CODES = {
    "epl":        "EPL",
    "la-liga":    "La_Liga",
    "serie-a":    "Serie_A",
    "bundesliga": "Bundesliga",
    "ligue-1":    "Ligue_1",
}

BIG5 = list(UNDERSTAT_CODES)

# Understat publishes from the 2014-15 season onward.
_FIRST_SEASON = 2014
_CACHE_DIR = Path("data/understat")

# Canonical column order (mirrors the MLS frame's core columns).
_COLS = ["match_id", "date", "season", "home_team", "away_team",
         "home_goals", "away_goals", "home_xg", "away_xg",
         "label_result", "is_result", "is_playoff"]

# ── Understat title → ESPN displayName, per league (logo alignment only) ──────
# Only the titles that differ from ESPN's name need an entry; anything absent is
# assumed to already match. Covers current big-5 squads (the teams that surface
# in standings/projections); historical-only clubs fall back to their Understat
# title and simply may not resolve a crest.
_ESPN_NAME_OVERRIDES: dict[str, dict[str, str]] = {
    "epl": {
        "Bournemouth": "AFC Bournemouth",
        "Brighton": "Brighton & Hove Albion",
        "Leeds": "Leeds United",
        "Tottenham": "Tottenham Hotspur",
        "West Ham": "West Ham United",
        "Wolverhampton Wanderers": "Wolverhampton Wanderers",
    },
    "la-liga": {
        "Alaves": "Alavés",
        "Atletico Madrid": "Atlético Madrid",
    },
    "serie-a": {
        "Inter": "Internazionale",
        "Roma": "AS Roma",
        "Parma Calcio 1913": "Parma",
        "Verona": "Hellas Verona",
    },
    "bundesliga": {
        "Augsburg": "FC Augsburg",
        "Borussia M.Gladbach": "Borussia Mönchengladbach",
        "FC Heidenheim": "1. FC Heidenheim 1846",
        "Freiburg": "SC Freiburg",
        "Hamburger SV": "Hamburg SV",
        "Hoffenheim": "TSG Hoffenheim",
        "Mainz 05": "Mainz",
        "Union Berlin": "1. FC Union Berlin",
        "Wolfsburg": "VfL Wolfsburg",
    },
    "ligue-1": {
        "Auxerre": "AJ Auxerre",
        "Le Havre": "Le Havre AC",
        "Monaco": "AS Monaco",
        "Paris Saint Germain": "Paris Saint-Germain",
        "Rennes": "Stade Rennais",
    },
}


def espn_name(league_id: str, title: str) -> str:
    """Map an Understat team title to ESPN's displayName (for crest lookup)."""
    return _ESPN_NAME_OVERRIDES.get(league_id, {}).get(title, title)


def _strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s)
                   if not unicodedata.combining(c))


def _default_seasons() -> list[int]:
    """All Understat seasons through the latest that has started.

    A European season "Y" (Y/Y+1) has started once we reach August of year Y;
    before then year Y's campaign does not yet exist on Understat.
    """
    now = datetime.now()
    latest = now.year if now.month >= 8 else now.year - 1
    return list(range(_FIRST_SEASON, latest + 1))


def _parse_season(rows: list[dict], season: int) -> pd.DataFrame:
    """Turn one season's raw Understat match dicts into canonical rows."""
    out = []
    for m in rows:
        played = bool(m.get("isResult"))
        g, xg = m.get("goals") or {}, m.get("xG") or {}
        hg = pd.to_numeric(g.get("h"), errors="coerce") if played else np.nan
        ag = pd.to_numeric(g.get("a"), errors="coerce") if played else np.nan
        out.append({
            "match_id":  str(m.get("id")),
            "date":      pd.to_datetime(m.get("datetime"), errors="coerce"),
            "season":    int(season),
            "home_team": (m.get("h") or {}).get("title"),
            "away_team": (m.get("a") or {}).get("title"),
            "home_goals": hg,
            "away_goals": ag,
            "home_xg":   pd.to_numeric(xg.get("h"), errors="coerce"),
            "away_xg":   pd.to_numeric(xg.get("a"), errors="coerce"),
            "is_result": played,
            "is_playoff": 0,  # European top flights are single-table, no playoffs
        })
    df = pd.DataFrame(out, columns=[c for c in _COLS if c != "label_result"])
    df["label_result"] = np.where(
        ~df["is_result"], np.nan,
        np.where(df["home_goals"] > df["away_goals"], 0,
                 np.where(df["home_goals"] == df["away_goals"], 1, 2)))
    return df[_COLS]


def _coerce(df: pd.DataFrame) -> pd.DataFrame:
    """Pin canonical dtypes (concat/parquet round-trips otherwise drift to object).

    Goals stay float, not int, because upcoming fixtures carry NaN goals; WS2's
    harness filters is_result and casts to int, exactly as the MLS path does.
    """
    if df.empty:
        return df.reindex(columns=_COLS)
    df = df.copy()
    df["match_id"] = df["match_id"].astype(str)
    df["date"] = pd.to_datetime(df["date"])
    df["season"] = pd.to_numeric(df["season"], errors="coerce").astype(int)
    for c in ["home_goals", "away_goals", "home_xg", "away_xg", "label_result"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["is_result"] = df["is_result"].astype(bool)
    df["is_playoff"] = pd.to_numeric(df["is_playoff"], errors="coerce") \
        .fillna(0).astype(int)
    return df[_COLS]


# Understat's raw title is this pipeline's canonical team name (the base identity
# source everything else — ESPN, football-data, Transfermarkt — joins against via
# their own NAME_MAP/ESPN_TO_UNDERSTAT/TM_CANON_ALIASES tables). Renames applied
# here are canonical-identity changes, not the cosmetic espn_name() logo-lookup
# override table above — keep this list short and scoped; a rename here ripples
# into every other source's join table (2026-07-12: "RasenBallsport Leipzig" is
# nobody's real name for the club — the other three sources already natively
# call it "RB Leipzig", so their now-unneeded translation entries were removed).
_CANONICAL_RENAMES: dict[str, dict[str, str]] = {
    "bundesliga": {"RasenBallsport Leipzig": "RB Leipzig"},
}


def _canonicalize_names(df: pd.DataFrame, league_id: str) -> pd.DataFrame:
    renames = _CANONICAL_RENAMES.get(league_id)
    if not renames or df.empty:
        return df
    df = df.copy()
    df["home_team"] = df["home_team"].replace(renames)
    df["away_team"] = df["away_team"].replace(renames)
    return df


def _fetch_seasons(code: str, seasons: list[int]) -> pd.DataFrame:
    """Fetch the given seasons from Understat and parse to canonical rows."""
    from understatapi import UnderstatClient  # local import: optional dependency
    frames = []
    with UnderstatClient() as client:
        league = client.league(league=code)
        for s in seasons:
            try:
                raw = league.get_match_data(season=str(s))
            except Exception as e:  # a missing/future season must not crash a build
                logger.warning("Understat %s %s fetch failed (%s) — skipping.",
                               code, s, e)
                continue
            if not raw:
                continue
            frames.append(_parse_season(raw, s))
            logger.info("Understat %s %s: %d matches", code, s, len(raw))
    return _coerce(pd.concat(frames, ignore_index=True) if frames
                   else pd.DataFrame(columns=_COLS))


def canonical_frame(league_id: str, seasons: list[int] | None = None,
                    use_cache: bool = True, refresh_latest: bool = True
                    ) -> pd.DataFrame:
    """Canonical match frame for one league, cached per league as parquet.

    Complete historical seasons are pulled once; the latest target season is
    re-fetched each run (it may be in progress) unless `refresh_latest` is off.
    Pass `use_cache=False` to ignore and overwrite the parquet entirely.
    """
    if league_id not in UNDERSTAT_CODES:
        raise ValueError(f"Unknown Understat league '{league_id}'. "
                         f"Known: {', '.join(BIG5)}")
    code = UNDERSTAT_CODES[league_id]
    seasons = sorted(seasons or _default_seasons())
    cache_path = _CACHE_DIR / f"{league_id}.parquet"

    cached = (pd.read_parquet(cache_path)
              if use_cache and cache_path.exists() else
              pd.DataFrame(columns=_COLS))
    have = set(cached["season"].unique()) if not cached.empty else set()

    to_fetch = [s for s in seasons if s not in have]
    if refresh_latest and seasons and seasons[-1] not in to_fetch:
        to_fetch.append(seasons[-1])  # re-pull the (possibly in-progress) latest
    to_fetch = sorted(set(to_fetch))

    if to_fetch:
        fresh = _fetch_seasons(code, to_fetch)
        kept = cached[~cached["season"].isin(to_fetch)] if not cached.empty \
            else cached
        # Concat only non-empty frames so an empty cache can't poison dtypes.
        combined = _coerce(pd.concat([f for f in (kept, fresh) if not f.empty],
                                     ignore_index=True) if not fresh.empty
                           else kept)
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        combined.to_parquet(cache_path, index=False)
    else:
        combined = _coerce(cached)

    df = combined[combined["season"].isin(seasons)].copy()
    df = df.sort_values("date").reset_index(drop=True)
    df = _canonicalize_names(df, league_id)

    try:
        from data_pipeline.source_health import record_source_run
        played = int(df["is_result"].sum()) if "is_result" in df.columns else len(df)
        record_source_run(
            source_name="understat",
            endpoint="canonical_frame",
            raw_count=len(df),
            parsed_count=played,
            null_rates={"league": league_id, "seasons": len(seasons)},
        )
    except Exception as _exc:
        logger.debug("understat: could not record source health: %s", _exc)

    return df


def _report(league_id: str, df: pd.DataFrame) -> None:
    played = df[df["is_result"]]
    if played.empty:
        print(f"  {league_id:11s} no completed matches"); return
    seasons = f"{int(df['season'].min())}–{int(df['season'].max())}"
    xg_cov = played["home_xg"].notna().mean()
    res = played["label_result"].value_counts(normalize=True).sort_index()
    upcoming = int((~df["is_result"]).sum())
    print(f"  {league_id:11s} {len(played):4d} played ({seasons}) · "
          f"xG {xg_cov:.0%} · "
          f"H/D/A {res.get(0,0):.0%}/{res.get(1,0):.0%}/{res.get(2,0):.0%}"
          + (f" · {upcoming} upcoming" if upcoming else ""))


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--league", choices=BIG5, help="single league id")
    ap.add_argument("--all", action="store_true", help="all big-5 leagues")
    ap.add_argument("--no-cache", action="store_true",
                    help="ignore the parquet cache and re-fetch all seasons")
    ap.add_argument("--seasons", help="comma-separated start years, e.g. 2022,2023")
    a = ap.parse_args()

    targets = BIG5 if a.all else ([a.league] if a.league else [])
    if not targets:
        ap.error("pass --league <id> or --all")
    seasons = [int(s) for s in a.seasons.split(",")] if a.seasons else None

    print(f"Understat canonical frames ({'no-cache' if a.no_cache else 'cached'}):")
    for lid in targets:
        frame = canonical_frame(lid, seasons=seasons, use_cache=not a.no_cache)
        _report(lid, frame)
