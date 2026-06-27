"""ESPN schedule adapter for European leagues — upcoming-season FIXTURES only.

Understat doesn't publish a European season until ~August; ESPN has the official
schedule earlier. This returns the canonical UPCOMING rows (no results/xG) used to
drive pre-season projections; xG-based data resumes from Understat once it publishes.

Schema mirrors data_pipeline.understat._COLS:
    match_id, date, season, home_team, away_team,
    home_goals, away_goals, home_xg, away_xg,
    label_result (0 home / 1 draw / 2 away), is_result, is_playoff

For completed matches: is_result=True, goals filled, label_result set.
For scheduled matches: is_result=False, home_goals/away_goals/label_result=NaN.

Usage:
    python -m data_pipeline.espn_fixtures --league epl --season 2026
"""
from __future__ import annotations

import argparse
import logging
from pathlib import Path

import numpy as np
import pandas as pd

from data_pipeline.http import espn_get
from data_pipeline.understat import _COLS, _coerce

logger = logging.getLogger("espn_fixtures")

_BASE = "https://site.api.espn.com/apis/site/v2/sports/soccer"
_CACHE_DIR = Path("data/espn_fixtures")

# Platform league id → ESPN slug.
SLUGS = {
    "epl":        "eng.1",
    "la-liga":    "esp.1",
    "serie-a":    "ita.1",
    "bundesliga": "ger.1",
    "ligue-1":    "fra.1",
}

# ESPN displayName → Understat team key, per league.
# Only names that DIFFER between the two sources need an entry.
# Promoted teams (no Understat EPL history) are left unmapped — they pass through
# as their ESPN name and pick up an ELO prior from the league mean.
ESPN_TO_UNDERSTAT: dict[str, dict[str, str]] = {
    "epl": {
        "AFC Bournemouth":       "Bournemouth",
        "Brighton & Hove Albion": "Brighton",
        "Hull City":             "Hull",
        "Ipswich Town":          "Ipswich",
        "Leeds United":          "Leeds",
        "Tottenham Hotspur":     "Tottenham",
        "West Ham United":       "West Ham",
    },
    "la-liga": {
        "Alavés":             "Alaves",
        "Atlético Madrid":    "Atletico Madrid",
        "Deportivo Alavés":   "Alaves",
    },
    "serie-a": {
        "AS Roma":           "Roma",
        "Internazionale":    "Inter",
        "Parma":             "Parma Calcio 1913",
        "Hellas Verona":     "Verona",
    },
    "bundesliga": {
        "FC Augsburg":                  "Augsburg",
        "Borussia Mönchengladbach":     "Borussia M.Gladbach",
        "1. FC Heidenheim 1846":        "FC Heidenheim",
        "SC Freiburg":                  "Freiburg",
        "Hamburg SV":                   "Hamburger SV",
        "TSG Hoffenheim":               "Hoffenheim",
        "Mainz":                        "Mainz 05",
        "RB Leipzig":                   "RasenBallsport Leipzig",
        "1. FC Union Berlin":           "Union Berlin",
        "VfL Wolfsburg":                "Wolfsburg",
    },
    "ligue-1": {
        "AJ Auxerre":          "Auxerre",
        "AS Monaco":           "Monaco",
        "Le Havre AC":         "Le Havre",
        "Paris Saint-Germain": "Paris Saint Germain",
        "Stade Rennais":       "Rennes",
    },
}


def _to_understat(league_id: str, espn_name: str) -> str:
    """Map an ESPN displayName to the Understat team key for `league_id`.

    If the name is not in the map (either it already matches Understat, or it is
    a newly promoted team with no Understat history), the ESPN name is returned
    unchanged.
    """
    return ESPN_TO_UNDERSTAT.get(league_id, {}).get(espn_name, espn_name)


def _fetch_events(slug: str, season: int) -> list[dict]:
    """Fetch all events (played + scheduled) for `slug` in season Y/Y+1."""
    url = f"{_BASE}/{slug}/scoreboard"
    y0, y1 = season, season + 1
    params = {"dates": f"{y0}0701-{y1}0630", "limit": 500}
    try:
        return espn_get(url, params).get("events", [])
    except Exception as e:
        logger.warning("ESPN %s season=%s fetch failed: %s", slug, season, e)
        return []


def _parse_events(events: list[dict], league_id: str, season: int) -> list[dict]:
    """Parse ESPN events into canonical row dicts (played + scheduled)."""
    rows = []
    for e in events:
        comps = e.get("competitions", [])
        if not comps:
            continue
        comp = comps[0]
        cs = comp.get("competitors", [])
        if len(cs) != 2:
            continue
        home = next((c for c in cs if c.get("homeAway") == "home"), None)
        away = next((c for c in cs if c.get("homeAway") == "away"), None)
        if not home or not away:
            continue
        espn_ht = home.get("team", {}).get("displayName", "")
        espn_at = away.get("team", {}).get("displayName", "")
        if not espn_ht or not espn_at:
            continue

        ht = _to_understat(league_id, espn_ht)
        at = _to_understat(league_id, espn_at)

        done = comp.get("status", {}).get("type", {}).get("completed", False)
        dt = pd.to_datetime(e.get("date"), utc=True, errors="coerce")
        date = dt.normalize().tz_localize(None) if pd.notna(dt) else pd.NaT

        rec: dict = {
            "match_id":    f"espn-{league_id}-{season}-{espn_ht}-{espn_at}".replace(" ", "_"),
            "date":        date,
            "season":      season,
            "home_team":   ht,
            "away_team":   at,
            "home_xg":     np.nan,
            "away_xg":     np.nan,
            "is_playoff":  0,
        }

        if done:
            try:
                hg = int(float(home.get("score") or 0))
                ag = int(float(away.get("score") or 0))
            except (ValueError, TypeError):
                continue
            rec["home_goals"] = float(hg)
            rec["away_goals"] = float(ag)
            rec["label_result"] = 0.0 if hg > ag else (1.0 if hg == ag else 2.0)
            rec["is_result"] = True
        else:
            rec["home_goals"] = np.nan
            rec["away_goals"] = np.nan
            rec["label_result"] = np.nan
            rec["is_result"] = False

        rows.append(rec)
    return rows


def european_fixtures(league_id: str, season: int,
                      use_cache: bool = True) -> pd.DataFrame:
    """Return ALL matches (played + scheduled) for a European league season.

    Parameters
    ----------
    league_id : str
        One of the keys in SLUGS ("epl", "la-liga", "serie-a", "bundesliga",
        "ligue-1").
    season : int
        Start year of the season (e.g. 2026 for the 2026-27 campaign).
    use_cache : bool
        If True (default) and a cached parquet exists, load from disk.
        Pass False to force a live fetch (and refresh the cache).

    Returns
    -------
    pd.DataFrame
        Canonical frame with columns matching understat._COLS.  Team names are
        mapped to Understat keys so ELO history carries over.
    """
    if league_id not in SLUGS:
        raise ValueError(
            f"Unknown league '{league_id}'. Known: {', '.join(SLUGS)}"
        )

    cache = _CACHE_DIR / f"{league_id}-{season}.parquet"
    if use_cache and cache.exists():
        df = pd.read_parquet(cache)
        df["date"] = pd.to_datetime(df["date"])
        return df

    slug = SLUGS[league_id]
    events = _fetch_events(slug, season)
    rows = _parse_events(events, league_id, season)

    if rows:
        df = _coerce(pd.DataFrame(rows)[_COLS])
    else:
        df = _coerce(pd.DataFrame(columns=_COLS))

    df = df.sort_values("date").reset_index(drop=True)

    cache.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(cache, index=False)
    logger.info(
        "ESPN fixtures %s %s: %d matches (%d scheduled, %d played) cached → %s",
        league_id, season,
        len(df),
        int((~df["is_result"]).sum()),
        int(df["is_result"].sum()),
        cache,
    )
    return df


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--league", default="epl", choices=list(SLUGS),
                    help="League id (default: epl)")
    ap.add_argument("--season", type=int, default=2026,
                    help="Season start year (default: 2026)")
    ap.add_argument("--no-cache", action="store_true",
                    help="Ignore parquet cache and re-fetch from ESPN")
    a = ap.parse_args()

    df = european_fixtures(a.league, a.season, use_cache=not a.no_cache)
    teams = sorted(set(df["home_team"]) | set(df["away_team"]))
    played = int(df["is_result"].sum())
    scheduled = int((~df["is_result"]).sum())
    print(f"{a.league} {a.season}: {len(df)} fixtures, {len(teams)} teams "
          f"({played} played, {scheduled} scheduled)")
    print("Teams:", teams)
