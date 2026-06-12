#!/usr/bin/env python3
"""
Opening-line odds logger — DB-free, parquet-backed.

Captures Pinnacle 1X2 (h2h) **opening** lines for upcoming MLS matches and
appends them to data/odds_log.parquet. "Opening" is operationalised as the
FIRST time we observe a given (home, away, commence_time) fixture: once a
fixture is in the log it is never overwritten, so repeated runs accumulate new
fixtures' openers without drifting toward the closing line.

Why opening, not closing: the model is market-blind and its edge only exists if
we can act on it before the market sharpens. Closing lines are more efficient;
to beat the market we must be willing to bet as soon as lines post — so the
opening line is the right benchmark for edge = model_prob − market_prob.

This is the data-collection half of the future CLV/edge workstream. With a
season of openers logged we can compute Pinnacle's own MLS Brier on the same
matches the model predicts, turning "how close are we to the book?" from a
literature estimate into a measured number.

Usage:
    python -m data_pipeline.odds_log            # fetch + append new openers
    python -m data_pipeline.odds_log --dry-run  # fetch, print, don't write

Requires the ODDS_API_KEY environment variable (The Odds API, free tier is
forward-only). With no key the call is a clean no-op so the daily build never
fails on it.
"""

from __future__ import annotations

import argparse
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

from config import SETTINGS

logger = logging.getLogger("odds_log")

_BASE_URL = "https://api.the-odds-api.com/v4/sports"
_SPORT = SETTINGS["market"]["sport_key"]
_REGIONS = SETTINGS["market"]["regions"]
_ODDS_FORMAT = SETTINGS["market"]["odds_format"]
_LOG_PATH = Path("data/odds_log.parquet")


def _fixture_key(home: str, away: str, commence: str) -> str:
    """Stable identity for a fixture's opener (date portion of commence_time)."""
    return f"{home}|{away}|{(commence or '')[:10]}"


def fetch_opening_odds() -> pd.DataFrame:
    """Fetch current Pinnacle h2h odds for upcoming MLS. One row per outcome.

    Columns: fixture_key, home_team, away_team, commence_time, outcome
    ('home'|'draw'|'away'), decimal_odds, fetched_at. Empty DataFrame if the
    API key is missing or the request fails (logged, never raised).
    """
    cols = ["fixture_key", "home_team", "away_team", "commence_time",
            "outcome", "decimal_odds", "fetched_at"]
    key = os.environ.get("ODDS_API_KEY", "")
    if not key:
        logger.warning("ODDS_API_KEY not set — skipping odds fetch (no-op).")
        return pd.DataFrame(columns=cols)

    try:
        resp = requests.get(
            f"{_BASE_URL}/{_SPORT}/odds",
            params={"apiKey": key, "regions": _REGIONS, "markets": "h2h",
                    "oddsFormat": _ODDS_FORMAT, "bookmakers": "pinnacle"},
            timeout=15)
        resp.raise_for_status()
    except Exception as e:  # network/quota/key errors must not crash the build
        logger.warning("Odds API request failed (%s) — skipping.", e)
        return pd.DataFrame(columns=cols)

    logger.info("Odds API: %s used, %s remaining.",
                resp.headers.get("x-requests-used", "?"),
                resp.headers.get("x-requests-remaining", "?"))

    now = datetime.now(timezone.utc).isoformat()
    rows = []
    for ev in resp.json():
        home, away = ev.get("home_team"), ev.get("away_team")
        commence = ev.get("commence_time", "")
        if not home or not away:
            continue
        fk = _fixture_key(home, away, commence)
        for bk in ev.get("bookmakers", []):
            if bk.get("key") != "pinnacle":
                continue
            for mkt in bk.get("markets", []):
                if mkt.get("key") != "h2h":
                    continue
                for o in mkt.get("outcomes", []):
                    name, price = o.get("name"), o.get("price")
                    if price is None:
                        continue
                    outcome = ("home" if name == home else
                               "away" if name == away else "draw")
                    rows.append({"fixture_key": fk, "home_team": home,
                                 "away_team": away, "commence_time": commence,
                                 "outcome": outcome, "decimal_odds": float(price),
                                 "fetched_at": now})
    return pd.DataFrame(rows, columns=cols)


def log_openers(dry_run: bool = False) -> int:
    """Append openers for fixtures not yet in the log. Returns rows added."""
    fresh = fetch_opening_odds()
    if fresh.empty:
        print("[odds_log] nothing fetched (no key, no fixtures, or API error).")
        return 0

    existing = pd.read_parquet(_LOG_PATH) if _LOG_PATH.exists() else \
        pd.DataFrame(columns=fresh.columns)
    seen = set(existing["fixture_key"]) if not existing.empty else set()
    new = fresh[~fresh["fixture_key"].isin(seen)]
    n_fix = new["fixture_key"].nunique()

    if new.empty:
        print(f"[odds_log] no new fixtures (log has "
              f"{existing['fixture_key'].nunique() if not existing.empty else 0}).")
        return 0
    if dry_run:
        print(f"[odds_log] DRY-RUN: would add {len(new)} rows / {n_fix} new "
              f"fixtures (openers):")
        for fk in new["fixture_key"].unique()[:10]:
            g = new[new["fixture_key"] == fk]
            od = dict(zip(g["outcome"], g["decimal_odds"]))
            print(f"  {fk}  H={od.get('home')} D={od.get('draw')} A={od.get('away')}")
        return 0

    _LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    pd.concat([existing, new], ignore_index=True).to_parquet(_LOG_PATH, index=False)
    print(f"[odds_log] appended {len(new)} rows / {n_fix} new fixtures → "
          f"{_LOG_PATH} (total fixtures: {len(seen) + n_fix}).")
    return len(new)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true",
                    help="Fetch and print openers without writing the parquet log")
    log_openers(dry_run=ap.parse_args().dry_run)
