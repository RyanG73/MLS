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
import requests
import urllib3

urllib3.disable_warnings()
logger = logging.getLogger("espn_continental")

_BASE = "https://site.api.espn.com/apis/site/v2/sports/soccer"
_HDR = {"User-Agent": "Mozilla/5.0"}
_CACHE_DIR = Path("data/espn_continental")

# Internal comp id -> ESPN slug.
SLUGS = {
    "ucl": "uefa.champions", "europa": "uefa.europa",
    "conference": "uefa.europa.conf", "concacaf-champions": "concacaf.champions",
    "concacaf-league": "concacaf.league",
}


def _fetch(slug: str, y0: int, y1: int) -> list[dict]:
    url = f"{_BASE}/{slug}/scoreboard"
    # Date window: season runs ~Aug–May; end at Jun 30 (not Jul 1 — ESPN rejects
    # {y+1}0701 for some seasons with HTTP 400).
    params = {"dates": f"{y0}0701-{y1}0630", "limit": 500}
    try:
        r = requests.get(url, params=params, headers=_HDR, timeout=30, verify=False)
        r.raise_for_status()
        return r.json().get("events", [])
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
        else:
            rec["home_goals"] = np.nan
            rec["away_goals"] = np.nan
        rec["is_result"] = bool(done)
        rows.append(rec)
    return rows


def continental_results(comp_id: str, seasons: range, use_cache: bool = True) -> pd.DataFrame:
    """Completed continental matches for `comp_id` across `seasons` (start years)."""
    slug = SLUGS[comp_id]
    cache = _CACHE_DIR / f"{comp_id}.parquet"
    if use_cache and cache.exists():
        return pd.read_parquet(cache)
    frames = []
    for y in seasons:
        rows = _parse(_fetch(slug, y, y + 1), y, completed_only=True)
        if rows:
            frames.append(pd.DataFrame(rows))
        time.sleep(0.25)
    df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    if not df.empty:
        cache.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(cache, index=False)
    return df


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
