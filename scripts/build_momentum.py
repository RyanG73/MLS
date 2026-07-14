#!/usr/bin/env python3
"""Momentum charts for completed matches -> webapp/data/momentum/<league>.js
(2026-07-14 feedback: "this github repo allows us to create momentum charts
for completed matches ... incorporate this into game results").

Big-5 leagues only (Understat's coverage limit — see UNDERSTAT_CODES).
Matches this league's OWN production payload (webapp/data/<lid>.js) games to
their Understat match_id by (home_team, away_team, date), so the client can
look a chart up by the same three fields it already renders a game row with
— no new IDs need to flow through the production build.

Scoped to the last `--days` completed matches (default 45) so a normal
build only fetches a handful of NEW shot-data payloads per run (each match's
shots are cached forever once fetched — see data_pipeline/understat_shots.py
— so re-runs are cheap regardless of window size).
"""
from __future__ import annotations

import argparse
import json
from datetime import date, timedelta
from pathlib import Path

from data_pipeline.understat import canonical_frame, UNDERSTAT_CODES
from data_pipeline.understat_shots import match_shots
from data_pipeline.momentum import compute_momentum
from scripts.payload_utils import write_js_payload

DATA = Path("webapp/data")
OUT_DIR = DATA / "momentum"


def _league_games(lid: str, days: int) -> list[dict]:
    """This league's own completed games within the last `days`, from its
    already-built production payload (not re-derived from Understat)."""
    path = DATA / f"{lid}.js"
    if not path.exists():
        return []
    txt = path.read_text()
    d = json.loads(txt[txt.index("{"): txt.rindex("}") + 1])
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    return [g for g in d.get("games", [])
            if g.get("result") is not None and (g.get("date") or "") >= cutoff]


def build_league(lid: str, days: int) -> dict:
    games = _league_games(lid, days)
    if not games:
        return {}
    frame = canonical_frame(lid, refresh_latest=False)
    # Understat date carries a time-of-day; key on the date portion to match
    # this repo's date-only game records.
    lookup = {}
    for _, row in frame.iterrows():
        key = (row["home_team"], row["away_team"], str(row["date"])[:10])
        lookup[key] = row["match_id"]

    out = {}
    for g in games:
        key = (g["home"], g["away"], g["date"])
        mid = lookup.get(key)
        if mid is None:
            continue
        shots = match_shots(mid)
        if not shots:
            continue
        out[f'{g["home"]}|{g["away"]}|{g["date"]}'] = compute_momentum(shots)
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--days", type=int, default=45,
                    help="Only build charts for matches within this many days (default 45)")
    ap.add_argument("--league", choices=list(UNDERSTAT_CODES), default=None,
                    help="Build one league only (default: all Big-5)")
    a = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    leagues = [a.league] if a.league else list(UNDERSTAT_CODES)
    for lid in leagues:
        charts = build_league(lid, a.days)
        write_js_payload(OUT_DIR / f"{lid}.js", "MOMENTUM_DATA", charts)
        print(f"[momentum] {lid}: {len(charts)} match charts → {OUT_DIR / f'{lid}.js'}")


if __name__ == "__main__":
    main()
