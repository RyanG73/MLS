"""ESPN adapter for continental competitions (results + fixtures).

Mirrors data_pipeline/espn_soccer.py but for a continental slug (e.g.
'uefa.champions'). Parquet-cached under data/espn_continental/<comp>.parquet.
"""
from __future__ import annotations

import argparse
import logging
import time
from pathlib import Path

import numpy as np
import pandas as pd

from data_pipeline.http import espn_get

logger = logging.getLogger("espn_continental")

_BASE = "https://site.api.espn.com/apis/site/v2/sports/soccer"
_CACHE_DIR = Path("data/espn_continental")

# Internal comp id -> ESPN slug.
SLUGS = {
    "ucl": "uefa.champions", "europa": "uefa.europa",
    "conference": "uefa.europa.conf", "concacaf-champions": "concacaf.champions",
    "leagues-cup": "concacaf.leagues.cup",
}


def _fetch(slug: str, y0: int, y1: int) -> list[dict]:
    url = f"{_BASE}/{slug}/scoreboard"
    # Date window: season runs ~Aug–May; end at Jun 30 (not Jul 1 — ESPN rejects
    # {y+1}0701 for some seasons with HTTP 400).
    params = {"dates": f"{y0}0701-{y1}0630", "limit": 500}
    try:
        return espn_get(url, params).get("events", [])
    except Exception as e:
        logger.warning("ESPN %s %s fetch failed: %s", slug, y0, e)
        return []


def _parse(events: list[dict], season: int, completed_only: bool) -> list[dict]:
    rows = []
    for e in events:
        comps = e.get("competitions", [])
        if not comps:
            continue
        comp = comps[0]
        done = comp.get("status", {}).get("type", {}).get("completed", False)
        if completed_only and not done:
            continue
        cs = comp.get("competitors", [])
        if len(cs) != 2:
            continue
        home = next((c for c in cs if c.get("homeAway") == "home"), None)
        away = next((c for c in cs if c.get("homeAway") == "away"), None)
        if not home or not away:
            continue
        ht = home.get("team", {}).get("displayName", "")
        at = away.get("team", {}).get("displayName", "")
        if not ht or not at:
            continue
        dt = pd.to_datetime(e.get("date"), utc=True, errors="coerce")
        rnd = e.get("season", {}).get("slug", "") or (comp.get("notes", [{}]) or [{}])[0].get("headline", "")
        rec = {
            "match_id": f"{season}-{ht}-{at}".replace(" ", "_"),
            "date": dt.normalize().tz_localize(None) if pd.notna(dt) else pd.NaT,
            "season": season, "round": rnd, "home_team": ht, "away_team": at,
            "neutral": bool(comp.get("neutralSite", False)),
        }
        if done:
            try:
                rec["home_goals"] = int(float(home.get("score") or 0))
                rec["away_goals"] = int(float(away.get("score") or 0))
            except (ValueError, TypeError):
                continue
            # ESPN sets `winner` on the advancing side, including penalty shootouts —
            # the only reliable way to resolve a level (PK-decided) tie/final.
            if home.get("winner"):
                rec["winner"] = ht
            elif away.get("winner"):
                rec["winner"] = at
            elif rec["home_goals"] != rec["away_goals"]:
                rec["winner"] = ht if rec["home_goals"] > rec["away_goals"] else at
            else:
                rec["winner"] = None
        else:
            rec["home_goals"] = np.nan
            rec["away_goals"] = np.nan
            rec["winner"] = None
        rec["is_result"] = bool(done)
        rows.append(rec)
    return rows


def continental_results(comp_id: str, seasons: range | None = None,
                        use_cache: bool = True) -> pd.DataFrame:
    """Completed continental matches for `comp_id`, filtered to `seasons` (start years).

    On a cache hit the full cache is loaded then FILTERED to `seasons` (None = all
    cached seasons). The filter is required: the cache may hold several editions, and
    a caller that wants one edition must not receive a season mix.

    When `use_cache=False`, fetches `seasons` (defaulting to 2018..current) and MERGES
    the fresh rows into any existing cache: old seasons not in the refetch window are
    retained, and the newly-fetched seasons replace their old counterparts (dedup on
    match_id keeping the fresh copy). This allows periodic "refresh current season" runs
    without dropping historical seasons from the cache.
    """
    slug = SLUGS[comp_id]
    cache = _CACHE_DIR / f"{comp_id}.parquet"
    if use_cache and cache.exists():
        df = pd.read_parquet(cache)
    else:
        fetch_range = seasons if seasons is not None else range(2018, 2027)
        frames = []
        for y in fetch_range:
            rows = _parse(_fetch(slug, y, y + 1), y, completed_only=True)
            if rows:
                frames.append(pd.DataFrame(rows))
            time.sleep(0.25)
        fresh = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

        # Merge with existing cache: keep all old seasons NOT in the refetch window,
        # then append the freshly-fetched rows, deduplicating on match_id (fresh wins).
        if cache.exists():
            existing = pd.read_parquet(cache)
            refetch_season_set = set(fetch_range)
            old_kept = existing[~existing["season"].isin(refetch_season_set)]
            if not fresh.empty:
                combined = pd.concat([old_kept, fresh], ignore_index=True)
                # Dedup on match_id: keep last occurrence (fresh rows were appended last).
                df = combined.drop_duplicates(subset=["match_id"], keep="last").reset_index(drop=True)
            else:
                df = old_kept.reset_index(drop=True)
        else:
            df = fresh

        if not df.empty:
            cache.parent.mkdir(parents=True, exist_ok=True)
            df.to_parquet(cache, index=False)

    if seasons is not None and not df.empty:
        df = df[df["season"].isin(list(seasons))].reset_index(drop=True)
    return df


def latest_season(comp_id: str) -> int | None:
    """Most recent season (start year) present in the cached results, or None."""
    df = continental_results(comp_id)
    return int(df["season"].max()) if not df.empty else None


def continental_fixtures(comp_id: str, season: int) -> pd.DataFrame:
    """Upcoming (undrawn ties absent) fixtures for the current season."""
    rows = _parse(_fetch(SLUGS[comp_id], season, season + 1), season, completed_only=False)
    df = pd.DataFrame(rows)
    return df[~df["is_result"]] if not df.empty else df


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--comp", default="ucl")
    ap.add_argument("--from-year", type=int, default=2018)
    ap.add_argument("--to-year", type=int, default=2025)
    a = ap.parse_args()
    df = continental_results(a.comp, range(a.from_year, a.to_year + 1), use_cache=False)
    print(f"{a.comp}: {len(df)} completed matches, "
          f"{df['season'].nunique() if not df.empty else 0} seasons")
    if not df.empty:
        print("\nColumns:", list(df.columns))
        print("\nSample rows:")
        print(df.head(10).to_string())
        print("\nUnique teams (sample):", sorted(
            set(df["home_team"].tolist() + df["away_team"].tolist())
        )[:20])
