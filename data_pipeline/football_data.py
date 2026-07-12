#!/usr/bin/env python3
"""
football-data.co.uk market-odds adapter — the betting-market benchmark.

Fetches free historical 1X2 closing odds for the big-5 European leagues and
de-vigs them into implied [home, draw, away] probabilities, so the dashboard can
answer "is the model beating the bookmakers?" per season — the European analog of
the MLS opening-line market-Brier (which football-data does not cover; MLS keeps
`data_pipeline/odds_log.py`).

Odds preference: **Pinnacle** (PSH/PSD/PSA — the sharpest book) → market average
(AvgH/AvgD/AvgA) → Bet365 (B365H/B365D/B365A), whichever is present per row.

Matching to the Understat canonical frame is by **date + team name**; football-
data uses its own short names ("Man City", "Ath Madrid"), so `_NAME_MAP` maps the
~26 that differ from the Understat titles (the rest match exactly). Season `Y`
(the Understat start-year, e.g. 2023 = 2023-24) maps to football-data's `2324`.

Usage:
    python -m data_pipeline.football_data --league epl --seasons 2022,2023,2024
"""

from __future__ import annotations

import argparse
import io
import logging
from pathlib import Path

import numpy as np
import pandas as pd
import requests

# Canonical-frame helpers shared with the Understat adapter (single source of
# truth for the schema both adapters must produce).
from data_pipeline.understat import _COLS, _coerce, _default_seasons

logger = logging.getLogger("football_data")

# Platform league id → football-data division code. The big-5 top flights are
# here as the MARKET source for the Understat-xG leagues; the 2nd tiers are here
# as the GOALS-ONLY model source (no xG on football-data → goals-only model).
DIV = {
    "epl": "E0", "la-liga": "SP1", "serie-a": "I1", "bundesliga": "D1", "ligue-1": "F1",
    "championship": "E1", "league-one": "E2", "league-two": "E3",
    "bundesliga-2": "D2", "serie-b": "I2",
    "segunda": "SP2", "ligue-2": "F2",
    # C1 batch (2026-07): non-big-5 top flights from football-data's "extra" set.
    "eredivisie": "N1", "primeira": "P1", "super-lig": "T1",
    "scottish-prem": "SC0", "belgian-pro": "B1", "greek-super": "G1",
    # England tier 5 (2026-07-10, docs/league-expansion-report.md's lower-
    # division item) — verified live: same mmz4281 per-season-file scheme,
    # ESPN carries it at eng.5.
    "national-league": "EC",
    # Scottish lower tiers (2026-07-11, expansion round 4). mmz4281 SC1/SC2/SC3,
    # ESPN sco.2/sco.3/sco.4. Chain up to scottish-prem (SC0) for tier-bridge seeding.
    "scottish-champ": "SC1", "scottish-league-one": "SC2", "scottish-league-two": "SC3",
}
BIG5 = ["epl", "la-liga", "serie-a", "bundesliga", "ligue-1"]
GOALS_ONLY = ["championship", "league-one", "league-two", "bundesliga-2", "serie-b",
              "segunda", "ligue-2",
              "eredivisie", "primeira", "super-lig",
              "scottish-prem", "belgian-pro", "greek-super",
              "national-league",
              "scottish-champ", "scottish-league-one", "scottish-league-two"]

_RESULTS_CACHE_DIR = Path("data/football_data")
_RAW_CACHE_DIR = _RESULTS_CACHE_DIR / "raw"

_BASE = "https://www.football-data.co.uk/mmz4281"
_HDR = {"User-Agent": "Mozilla/5.0"}

# football-data short name → Understat title (only the ones that differ).
_NAME_MAP: dict[str, dict[str, str]] = {
    "epl": {
        "Man City": "Manchester City", "Man United": "Manchester United",
        "Newcastle": "Newcastle United", "Nott'm Forest": "Nottingham Forest",
        "Wolves": "Wolverhampton Wanderers",
    },
    "la-liga": {
        "Ath Bilbao": "Athletic Club", "Ath Madrid": "Atletico Madrid",
        "Betis": "Real Betis", "Celta": "Celta Vigo", "Espanol": "Espanyol",
        "Sociedad": "Real Sociedad", "Valladolid": "Real Valladolid",
        "Vallecano": "Rayo Vallecano", "Oviedo": "Real Oviedo",
    },
    "serie-a": {"Milan": "AC Milan", "Parma": "Parma Calcio 1913"},
    "bundesliga": {
        "Dortmund": "Borussia Dortmund", "Ein Frankfurt": "Eintracht Frankfurt",
        "Heidenheim": "FC Heidenheim", "Leverkusen": "Bayer Leverkusen",
        "M'gladbach": "Borussia M.Gladbach", "Mainz": "Mainz 05",
        # RB Leipzig: no entry needed — football-data's raw name already matches
        # the canonical name (2026-07-12: canonical changed from "RasenBallsport
        # Leipzig" to "RB Leipzig", see data_pipeline/understat.py).
        "St Pauli": "St. Pauli",
        "Stuttgart": "VfB Stuttgart", "FC Koln": "FC Cologne",
        "Hamburg": "Hamburger SV", "Hertha": "Hertha Berlin",
    },
    "ligue-1": {"Paris SG": "Paris Saint Germain", "St Etienne": "Saint-Etienne",
                "Clermont": "Clermont Foot"},
}

# Odds-column triples in preference order (sharpest first).
_ODDS_SETS = [("PSH", "PSD", "PSA"), ("AvgH", "AvgD", "AvgA"),
              ("B365H", "B365D", "B365A")]


def _season_code(start_year: int) -> str:
    """Understat start year → football-data code (2023 → '2324')."""
    return f"{start_year % 100:02d}{(start_year + 1) % 100:02d}"


def _fetch_csv(div: str, start_year: int) -> pd.DataFrame | None:
    """Fetch one season's football-data CSV, disk-cached as raw text.

    The raw CSV is cached under data/football_data/raw/ so repeat callers
    (match_results AND market_probs) read from disk instead of re-downloading.
    On a network failure the cached copy is used as a fallback, so a stalled
    football-data.co.uk never blocks a build whose data already exists locally.
    """
    raw_path = _RAW_CACHE_DIR / f"{div}-{_season_code(start_year)}.csv"
    if raw_path.exists():
        try:
            return pd.read_csv(raw_path)
        except Exception:
            pass  # corrupt cache → re-fetch below

    url = f"{_BASE}/{_season_code(start_year)}/{div}.csv"
    try:
        r = requests.get(url, headers=_HDR, timeout=(10, 30))
        r.raise_for_status()
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        raw_path.write_text(r.text)
        return pd.read_csv(io.StringIO(r.text))
    except Exception as e:
        logger.warning("football-data %s %s fetch failed (%s)", div, start_year, e)
        return None


def _parse_results(df: pd.DataFrame, league_id: str, season: int) -> pd.DataFrame:
    """One season's football-data results CSV → canonical rows (goals, xG=NaN).

    football-data carries no expected goals, so home_xg/away_xg are NaN; the
    feature pipeline (add_rolling_features) falls back to goals automatically, so
    these leagues run the same model as a goals-only variant. Team names are
    football-data's own (the model keys); display/crest mapping to ESPN happens in
    the dashboard build.
    """
    out = []
    for _, r in df.iterrows():
        ht, at, hg, ag = r.get("HomeTeam"), r.get("AwayTeam"), r.get("FTHG"), r.get("FTAG")
        if pd.isna(ht) or pd.isna(at) or pd.isna(hg) or pd.isna(ag):
            continue
        hg, ag = int(hg), int(ag)
        out.append({
            "match_id": f"{DIV[league_id]}-{season}-{ht}-{at}".replace(" ", "_"),
            "date": pd.to_datetime(r.get("Date"), dayfirst=True, errors="coerce"),
            "season": int(season), "home_team": ht, "away_team": at,
            "home_goals": hg, "away_goals": ag, "home_xg": np.nan, "away_xg": np.nan,
            "label_result": 0 if hg > ag else (1 if hg == ag else 2),
            "is_result": True, "is_playoff": 0,
        })
    return pd.DataFrame(out, columns=_COLS)


def match_results(league_id: str, seasons: list[int] | None = None,
                  use_cache: bool = True, refresh_latest: bool = True) -> pd.DataFrame:
    """Canonical goals-only match frame for a football-data division, parquet-cached.

    Same schema and caching contract as `data_pipeline.understat.canonical_frame`
    (complete seasons fetched once; the latest re-pulled), but with xG=NaN. Used
    for the league-table leagues football-data covers but Understat/FBref do not
    (the European 2nd tiers).
    """
    if league_id not in DIV:
        raise ValueError(f"Unknown football-data league '{league_id}'. "
                         f"Known: {', '.join(DIV)}")
    seasons = sorted(seasons or _default_seasons())
    cache_path = _RESULTS_CACHE_DIR / f"{league_id}.parquet"

    cached = (pd.read_parquet(cache_path)
              if use_cache and cache_path.exists() else pd.DataFrame(columns=_COLS))
    have = set(cached["season"].unique()) if not cached.empty else set()
    to_fetch = [s for s in seasons if s not in have]
    if refresh_latest and seasons and seasons[-1] not in to_fetch:
        to_fetch.append(seasons[-1])
    to_fetch = sorted(set(to_fetch))

    if to_fetch:
        frames = []
        for s in to_fetch:
            csv = _fetch_csv(DIV[league_id], s)
            if csv is None or "HomeTeam" not in csv.columns:
                continue
            frames.append(_parse_results(csv, league_id, s))
            logger.info("football-data %s %s: %d results", DIV[league_id], s, len(frames[-1]))
        fresh = (pd.concat(frames, ignore_index=True) if frames
                 else pd.DataFrame(columns=_COLS))
        kept = cached[~cached["season"].isin(to_fetch)] if not cached.empty else cached
        combined = _coerce(pd.concat([f for f in (kept, fresh) if not f.empty],
                                     ignore_index=True) if not fresh.empty else kept)
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        combined.to_parquet(cache_path, index=False)
    else:
        combined = _coerce(cached)

    df = combined[combined["season"].isin(seasons)].copy()
    df["date"] = pd.to_datetime(df["date"])
    return df.sort_values("date").reset_index(drop=True)


def _devig_row(row) -> tuple[float, float, float] | None:
    """First available odds triple → de-vigged [home, draw, away] probabilities."""
    for h, d, a in _ODDS_SETS:
        oh, od, oa = row.get(h), row.get(d), row.get(a)
        if pd.notna(oh) and pd.notna(od) and pd.notna(oa) and min(oh, od, oa) > 1:
            ih, idr, ia = 1.0 / oh, 1.0 / od, 1.0 / oa
            s = ih + idr + ia
            return ih / s, idr / s, ia / s
    return None


def market_probs(league_id: str, seasons: list[int]) -> pd.DataFrame:
    """De-vigged market [home,draw,away] probs per match, keyed to Understat titles.

    Returns columns: date (datetime, normalised to midnight), home_team, away_team
    (Understat titles), mkt_home, mkt_draw, mkt_away. Rows without usable odds are
    dropped.
    """
    nm = _NAME_MAP.get(league_id, {})
    div = DIV[league_id]
    out = []
    for y in seasons:
        df = _fetch_csv(div, y)
        if df is None or "HomeTeam" not in df.columns:
            continue
        for _, r in df.iterrows():
            ht, at = r.get("HomeTeam"), r.get("AwayTeam")
            if pd.isna(ht) or pd.isna(at):
                continue
            mp = _devig_row(r)
            if mp is None:
                continue
            out.append({
                "season": int(y),
                "home_team": nm.get(ht, ht), "away_team": nm.get(at, at),
                "mkt_home": mp[0], "mkt_draw": mp[1], "mkt_away": mp[2],
            })
    return pd.DataFrame(out)


def attach_market(frame: pd.DataFrame, league_id: str,
                  seasons: list[int]) -> pd.DataFrame:
    """Left-merge market probs onto a canonical frame by (season, home, away).

    `frame` needs season / home_team / away_team (Understat titles). The merge key
    is (season, home, away) — unique in a double round-robin (A hosts B once per
    season), which avoids any kickoff-time/timezone date mismatch. Returns a copy
    with mkt_home/mkt_draw/mkt_away added (NaN where unmatched).
    """
    mk = market_probs(league_id, seasons)
    out = frame.copy()
    if mk.empty:
        out[["mkt_home", "mkt_draw", "mkt_away"]] = np.nan
        return out
    return out.merge(mk, on=["season", "home_team", "away_team"], how="left")


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--league", choices=list(DIV), required=True)
    ap.add_argument("--seasons", default="2022,2023,2024,2025")
    ap.add_argument("--results", action="store_true",
                    help="show the goals-only canonical frame instead of market odds")
    a = ap.parse_args()
    seasons = [int(s) for s in a.seasons.split(",")]
    if a.results:
        df = match_results(a.league, seasons)
        played = df[df["is_result"]]
        res = played["label_result"].value_counts(normalize=True).sort_index()
        print(f"{a.league}: {len(played)} results across {seasons} | "
              f"teams {played['home_team'].nunique()} | "
              f"H/D/A {res.get(0,0):.0%}/{res.get(1,0):.0%}/{res.get(2,0):.0%}")
        print(played[["date", "season", "home_team", "away_team",
                      "home_goals", "away_goals"]].head(3).to_string())
    else:
        mk = market_probs(a.league, seasons)
        print(f"{a.league}: {len(mk)} matches with market odds across {seasons}")
        if not mk.empty:
            print(mk.head(3).to_string())
