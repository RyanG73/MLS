#!/usr/bin/env python3
"""
ESPN goals-only adapter for Liga MX.

Fetches free match results from the ESPN scoreboard API for Liga MX (mex.1).
Returns the same canonical frame schema as understat.canonical_frame but with
xG=NaN (goals-only). The ESPN slug field distinguishes the two annual torneos
(Clausura = Jan–May, Apertura = Jul–Dec).

Season encoding: sequential integer per torneo, starting from 1:
  Clausura 2017=1, Apertura 2017=2, Clausura 2018=3, ..., Clausura 2026=19.
  Formula: (year - 2017) * 2 + (1 if clausura else 2)
  Clausura 2020 is absent (COVID cancellation after 10 rounds, unusable).

Each integer season maps back to a human label via TORNEO_LABELS[sid].

Usage:
    python -m data_pipeline.espn_soccer
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

from data_pipeline.understat import _COLS, _coerce

urllib3.disable_warnings()
logger = logging.getLogger("espn_soccer")

_BASE = "https://site.api.espn.com/apis/site/v2/sports/soccer"
_HDR = {"User-Agent": "Mozilla/5.0"}
_ESPN_CACHE_DIR = Path("data/espn_soccer")
_LIGA_MX_SLUG = "mex.1"
_SEASON_BASE_YEAR = 2017

# Historical torneo windows: (year, start_mmdd, end_mmdd, is_clausura)
# Clausura plays Jan–May (start_mmdd="0101", end_mmdd="0630")
# Apertura plays Jul–Dec (start_mmdd="0701", end_mmdd="1231")
# Clausura 2020 omitted — cancelled after 10 rounds (COVID); too incomplete to use.
_LIGA_MX_WINDOWS: list[tuple[int, str, str, bool]] = [
    (2017, "0101", "0630", True),
    (2017, "0701", "1231", False),
    (2018, "0101", "0630", True),
    (2018, "0701", "1231", False),
    (2019, "0101", "0630", True),
    (2019, "0701", "1231", False),
    # Clausura 2020 excluded (COVID cancellation)
    (2020, "0701", "1231", False),  # Guardianes 2020 — completed in bubble
    (2021, "0101", "0630", True),
    (2021, "0701", "1231", False),
    (2022, "0101", "0630", True),
    (2022, "0701", "1231", False),
    (2023, "0101", "0630", True),
    (2023, "0701", "1231", False),
    (2024, "0101", "0630", True),
    (2024, "0701", "1231", False),
    (2025, "0101", "0630", True),
    (2025, "0701", "1231", False),
    (2026, "0101", "0630", True),
]


def season_id(year: int, is_clausura: bool) -> int:
    """Encode a torneo as a sequential integer (Clausura 2017=1, Apertura 2017=2, …)."""
    return (year - _SEASON_BASE_YEAR) * 2 + (1 if is_clausura else 2)


def season_label(sid: int) -> str:
    """Human-readable label for a sequential season integer (e.g. 19 → 'Cl.2026')."""
    idx = sid - 1  # 0-based
    year = _SEASON_BASE_YEAR + idx // 2
    is_clausura = (idx % 2 == 0)
    return f"{'Cl.' if is_clausura else 'Ap.'}{year}"


def _fetch_events(year: int, start_mmdd: str, end_mmdd: str) -> list[dict]:
    url = f"{_BASE}/{_LIGA_MX_SLUG}/scoreboard"
    params = {"dates": f"{year}{start_mmdd}-{year}{end_mmdd}", "limit": 500}
    try:
        r = requests.get(url, params=params, headers=_HDR, timeout=30, verify=False)
        r.raise_for_status()
        return r.json().get("events", [])
    except Exception as e:
        logger.warning("ESPN Liga MX %s%s fetch failed: %s", year, start_mmdd, e)
        return []


def _parse_events(events: list[dict], sid: int) -> list[dict]:
    """Extract completed regular-season matches. Liguilla/playoff slugs are skipped."""
    rows = []
    for e in events:
        slug = e.get("season", {}).get("slug", "")
        if "torneo-clausura" not in slug and "torneo-apertura" not in slug:
            continue  # skip liguilla, quarterfinals, etc.
        comps = e.get("competitions", [])
        if not comps:
            continue
        comp = comps[0]
        if not comp.get("status", {}).get("type", {}).get("completed"):
            continue
        competitors = comp.get("competitors", [])
        if len(competitors) != 2:
            continue
        home = next((c for c in competitors if c.get("homeAway") == "home"), None)
        away = next((c for c in competitors if c.get("homeAway") == "away"), None)
        if not home or not away:
            continue
        ht = home.get("team", {}).get("displayName", "")
        at = away.get("team", {}).get("displayName", "")
        if not ht or not at:
            continue
        try:
            hg = int(float(home.get("score") or 0))
            ag = int(float(away.get("score") or 0))
        except (ValueError, TypeError):
            continue
        dt = pd.to_datetime(e.get("date"), utc=True, errors="coerce")
        if pd.isna(dt):
            continue
        rows.append({
            "match_id": f"mex-{sid}-{ht}-{at}".replace(" ", "_"),
            "date": dt.normalize().tz_localize(None),
            "season": sid, "home_team": ht, "away_team": at,
            "home_goals": hg, "away_goals": ag,
            "home_xg": np.nan, "away_xg": np.nan,
            "label_result": 0 if hg > ag else (1 if hg == ag else 2),
            "is_result": True, "is_playoff": 0,
        })
    return rows


def liga_mx_frame(use_cache: bool = True, refresh_latest: bool = True) -> pd.DataFrame:
    """Canonical goals-only frame for all Liga MX torneos, parquet-cached.

    Same schema as understat.canonical_frame with xG=NaN.
    Season integers: Clausura 2017=1, Apertura 2017=2, ..., Clausura 2026=19.
    Season 7 (Clausura 2020) is absent — not fetched due to COVID cancellation.
    """
    cache_path = _ESPN_CACHE_DIR / "liga-mx.parquet"
    cached = (pd.read_parquet(cache_path)
              if use_cache and cache_path.exists() else pd.DataFrame(columns=_COLS))
    have: set[int] = set(cached["season"].unique().tolist()) if not cached.empty else set()

    last_window = _LIGA_MX_WINDOWS[-1]
    last_sid = season_id(last_window[0], last_window[3])

    frames: list[pd.DataFrame] = []
    fetched_sids: set[int] = set()
    for year, start_mmdd, end_mmdd, is_cl in _LIGA_MX_WINDOWS:
        sid = season_id(year, is_cl)
        is_latest = (sid == last_sid)
        if sid in have and not (refresh_latest and is_latest):
            continue
        events = _fetch_events(year, start_mmdd, end_mmdd)
        rows = _parse_events(events, sid)
        if rows:
            frames.append(pd.DataFrame(rows, columns=_COLS))
            fetched_sids.add(sid)
            lbl = season_label(sid)
            logger.info("ESPN Liga MX %s: %d results (season=%d)", lbl, len(rows), sid)
        else:
            logger.debug("ESPN Liga MX %s: 0 results (season=%d)", season_label(sid), sid)
        time.sleep(0.25)

    if frames:
        fresh = pd.concat(frames, ignore_index=True)
        kept = (cached[~cached["season"].isin(fetched_sids)]
                if not cached.empty else cached)
        combined = _coerce(
            pd.concat([f for f in (kept, fresh) if not f.empty], ignore_index=True)
            if not fresh.empty else kept
        )
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        combined.to_parquet(cache_path, index=False)
    else:
        combined = _coerce(cached)

    df = combined[combined["season"] > 0].copy()
    df["date"] = pd.to_datetime(df["date"])
    return df.sort_values("date").reset_index(drop=True)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--no-cache", action="store_true")
    a = ap.parse_args()
    df = liga_mx_frame(use_cache=not a.no_cache)
    played = df[df["is_result"]]
    print(f"Liga MX: {len(played)} results | "
          f"{played['season'].nunique()} torneos | "
          f"{played['home_team'].nunique()} teams")
    for sid in sorted(played["season"].unique()):
        g = played[played["season"] == sid]
        print(f"  {season_label(sid):8s} (sid={sid:2d}): {len(g):3d} matches, "
              f"{g['home_team'].nunique()} teams")
