#!/usr/bin/env python3
"""U2: model-odds movers strip → webapp/data/movers.js (market odds NOT required).

`data/odds_history.parquet` (B10) accrues one row per (league, team,
snapshot_date) with the model's season odds. Movers = the biggest changes in
those odds over a trailing ~30-day window — "who is rising/falling in the
model's eyes". Ships against pure model odds today; market columns join
whenever the odds feed activates (user-deferred).

Runs after archive_odds_snapshot.py in both refresh workflows. Empty-safe:
with fewer than two snapshots for every league the payload carries the honest
thin-history state and the strip stays hidden.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pandas as pd

from scripts.payload_utils import write_js_payload

HISTORY = Path("data/odds_history.parquet")
OUT = Path("webapp/data/movers.js")
LEAGUES_JS = Path("webapp/leagues.js")
WINDOW_DAYS = 30

# Season-odds columns worth surfacing (next-match probs excluded — too noisy).
METRICS = ["title", "playoff", "shield", "cup", "ucl", "europa", "releg", "promo"]
METRIC_LABEL = {"title": "Title", "playoff": "Playoffs", "shield": "Shield",
                "cup": "Cup", "ucl": "UCL", "europa": "Europa",
                "releg": "Relegation", "promo": "Promotion"}

# Broad region buckets for the homepage movers filter — collapses leagues.js's
# finer masthead groups (2026-07-13 feedback: "overall, europe, north america,
# and other combinations").
_REGION_OF_GROUP = {
    "England": "Europe", "Germany": "Europe", "France": "Europe",
    "Italy": "Europe", "Spain": "Europe", "Other Europe": "Europe",
    "MLS": "North America", "Americas": "North America",
    "South America": "South America", "Asia": "Asia", "Cups": "Cups",
}


def _load_region_map() -> dict[str, str]:
    """league_id -> broad region, from the webapp's own league registry."""
    try:
        t = LEAGUES_JS.read_text()
        registry = json.loads(t[t.index("["): t.rindex("]") + 1])
    except Exception:
        return {}
    return {r["id"]: _REGION_OF_GROUP.get(r.get("group"), "Other") for r in registry}


def compute_movers(df: pd.DataFrame, min_delta: float = 1.5,
                   top_n: int = 200, window_days: int = WINDOW_DAYS) -> tuple[list[dict], int, str]:
    """Top-|Δ| odds moves per (league, team) over a trailing `window_days` window.

    For each team, `prev` is the latest snapshot at or before (latest snapshot
    overall - window_days); if the archived history doesn't go back that far yet,
    `prev` falls back to that team's earliest USABLE snapshot (compares the whole
    available history rather than nothing). Returns (movers, actual_span_days,
    earliest_used_date) so the client can label the window honestly (e.g. "since
    Jul 7" pre-30-days).

    Each entity's very first-ever archived snapshot is dropped before this runs
    (confirmed 2026-07-13: it carries sentinel values — e.g. Hoffenheim's europa%
    read 100.0 on its first archive run, then 10.2 the next run and ~9-10 ever
    after; same 100.0-then-real pattern across many leagues, on whatever calendar
    date that league's archival happened to start). Comparing against that row
    manufactures huge fake "movers", so every (league, team) group's earliest row
    is treated as an unreliable bootstrap read, not a real snapshot to diff from.
    This is a movers-specific workaround; the root cause belongs in
    archive_odds_snapshot.py.
    """
    metrics = [m for m in METRICS if m in df.columns]
    region_of = _load_region_map()
    out: list[dict] = []
    used_dates: list[pd.Timestamp] = []
    for (league, team), grp in df.groupby(["league", "team"]):
        grp = grp.assign(_d=pd.to_datetime(grp["snapshot_date"])).sort_values("_d")
        grp = grp.iloc[1:]  # drop this entity's bootstrap-run row
        if len(grp) < 2:
            continue
        now = grp.iloc[-1]
        cutoff = now["_d"] - pd.Timedelta(days=window_days)
        eligible = grp[grp["_d"] <= cutoff]
        prev = eligible.iloc[-1] if len(eligible) else grp.iloc[0]
        if prev["_d"] == now["_d"]:
            continue
        used_dates.append(prev["_d"])
        for m in metrics:
            a, b = prev.get(m), now.get(m)
            if pd.isna(a) or pd.isna(b):
                continue
            delta = float(b) - float(a)
            if abs(delta) < min_delta:
                continue
            out.append({"league": league, "region": region_of.get(league, "Other"),
                        "team": team, "metric": m,
                        "prev": round(float(a), 1), "now": round(float(b), 1),
                        "delta": round(delta, 1),
                        "from": str(prev["snapshot_date"]),
                        "to": str(now["snapshot_date"])})
    # Keep the strongest riser and faller per team (its biggest metric swing in
    # each direction) rather than every metric — a team moving on both "title"
    # and "releg" at once would otherwise crowd out other teams.
    best: dict[tuple[str, str, bool], dict] = {}
    for m in out:
        key = (m["league"], m["team"], m["delta"] >= 0)
        if key not in best or abs(m["delta"]) > abs(best[key]["delta"]):
            best[key] = m
    ranked = sorted(best.values(), key=lambda x: -abs(x["delta"]))
    earliest_used = min(used_dates).strftime("%Y-%m-%d") if used_dates else ""
    global_span = int((max(used_dates) - min(used_dates)).days) if used_dates else 0
    return ranked[:top_n], global_span, earliest_used


def main() -> None:
    generated = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    if not HISTORY.exists():
        payload = {"status": "empty", "generated": generated, "movers": [],
                   "reason": "No odds history accrued yet."}
    else:
        df = pd.read_parquet(HISTORY)
        movers, span, earliest_used = compute_movers(df)
        window_label = f"last {WINDOW_DAYS} days" if span >= WINDOW_DAYS else \
            f"since tracking began ({earliest_used})"
        payload = {"status": "ok" if movers else "thin",
                   "generated": generated,
                   "window_days": WINDOW_DAYS,
                   "window_label": window_label,
                   "metric_labels": METRIC_LABEL,
                   "movers": movers,
                   "reason": None if movers else
                   "Not enough odds history yet — movers appear once builds accrue."}
    write_js_payload(OUT, "MOVERS_DATA", payload)
    print(f"[movers] {payload['status']} · {len(payload['movers'])} rows"
          f"{(' · ' + payload['window_label']) if 'window_label' in payload else ''} → {OUT}")


if __name__ == "__main__":
    main()
