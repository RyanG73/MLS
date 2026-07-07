#!/usr/bin/env python3
"""U2: model-odds movers strip → webapp/data/movers.js (market odds NOT required).

`data/odds_history.parquet` (B10) accrues one row per (league, team,
snapshot_date) with the model's season odds. Movers = the biggest changes in
those odds between each (league, team)'s two most recent snapshots — "who is
rising/falling in the model's eyes". Ships against pure model odds today;
market columns join whenever the odds feed activates (user-deferred).

Runs after archive_odds_snapshot.py in both refresh workflows. Empty-safe:
with fewer than two snapshots for every league the payload carries the honest
thin-history state and the strip stays hidden.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pandas as pd

from scripts.payload_utils import write_js_payload

HISTORY = Path("data/odds_history.parquet")
OUT = Path("webapp/data/movers.js")

# Season-odds columns worth surfacing (next-match probs excluded — too noisy).
METRICS = ["title", "playoff", "shield", "cup", "ucl", "europa", "releg", "promo"]
METRIC_LABEL = {"title": "Title", "playoff": "Playoffs", "shield": "Shield",
                "cup": "Cup", "ucl": "UCL", "europa": "Europa",
                "releg": "Relegation", "promo": "Promotion"}


def compute_movers(df: pd.DataFrame, min_delta: float = 1.5,
                   top_n: int = 12) -> list[dict]:
    """Top-|Δ| odds moves between each (league, team)'s last two snapshots.

    Returns [{league, team, metric, prev, now, delta, from, to}] sorted by
    |delta| desc. Teams with a single snapshot are skipped (nothing to diff).
    """
    metrics = [m for m in METRICS if m in df.columns]
    out: list[dict] = []
    for (league, team), grp in df.groupby(["league", "team"]):
        grp = grp.sort_values("snapshot_date")
        if len(grp) < 2:
            continue
        prev, now = grp.iloc[-2], grp.iloc[-1]
        for m in metrics:
            a, b = prev.get(m), now.get(m)
            if pd.isna(a) or pd.isna(b):
                continue
            delta = float(b) - float(a)
            if abs(delta) < min_delta:
                continue
            out.append({"league": league, "team": team, "metric": m,
                        "prev": round(float(a), 1), "now": round(float(b), 1),
                        "delta": round(delta, 1),
                        "from": str(prev["snapshot_date"]),
                        "to": str(now["snapshot_date"])})
    out.sort(key=lambda x: -abs(x["delta"]))
    return out[:top_n]


def main() -> None:
    generated = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    if not HISTORY.exists():
        payload = {"status": "empty", "generated": generated, "movers": [],
                   "reason": "No odds history accrued yet."}
    else:
        df = pd.read_parquet(HISTORY)
        movers = compute_movers(df)
        payload = {"status": "ok" if movers else "thin",
                   "generated": generated,
                   "metric_labels": METRIC_LABEL,
                   "movers": movers,
                   "reason": None if movers else
                   "Not enough odds history yet — movers appear once builds accrue."}
    write_js_payload(OUT, "MOVERS_DATA", payload)
    print(f"[movers] {payload['status']} · {len(payload['movers'])} rows → {OUT}")


if __name__ == "__main__":
    main()
