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

import numpy as np
import pandas as pd
import requests

logger = logging.getLogger("football_data")

# Understat league id → football-data division code.
DIV = {"epl": "E0", "la-liga": "SP1", "serie-a": "I1",
       "bundesliga": "D1", "ligue-1": "F1"}
BIG5 = list(DIV)

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
        "RB Leipzig": "RasenBallsport Leipzig", "St Pauli": "St. Pauli",
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
    url = f"{_BASE}/{_season_code(start_year)}/{div}.csv"
    try:
        r = requests.get(url, headers=_HDR, timeout=25)
        r.raise_for_status()
        return pd.read_csv(io.StringIO(r.text))
    except Exception as e:
        logger.warning("football-data %s %s fetch failed (%s)", div, start_year, e)
        return None


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
    ap.add_argument("--league", choices=BIG5, required=True)
    ap.add_argument("--seasons", default="2022,2023,2024,2025")
    a = ap.parse_args()
    seasons = [int(s) for s in a.seasons.split(",")]
    mk = market_probs(a.league, seasons)
    print(f"{a.league}: {len(mk)} matches with market odds across {seasons}")
    if not mk.empty:
        print(mk.head(3).to_string())
