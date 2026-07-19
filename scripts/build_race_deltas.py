#!/usr/bin/env python3
"""U2: per-race "since last build" deltas + cause → webapp/data/race-deltas.js.

For every league, look at its two most recent snapshots in
`data/odds_history.parquet` and, for each race metric (title / ucl / releg / …),
report the CURRENT leader's change in that probability plus WHY it changed:

  - `result`  the leader played (n_played increased) → movement is real signal
  - `model`   n_played unchanged but config_id / code_rev changed → a model update
  - `refresh` neither changed → a schedule/source refresh (churn)

The client (`raceCard`) renders this as a small chip on each race card, so the
site can answer its own tagline — "what changed?" — per race.

Runs after archive_odds_snapshot.py + build_movers.py in every refresh path.
Empty-safe: leagues with <2 snapshots simply carry no entry and no chip shows.
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

import pandas as pd

from scripts.archive_odds_snapshot import append_snapshot
from scripts.payload_utils import write_js_payload

HISTORY = Path("data/odds_history.parquet")
HISTORY_ARCHIVE = Path("data/race_deltas_history.parquet")
OUT = Path("webapp/data/race-deltas.js")

# Season-odds columns that back a race card (next-match probs excluded).
METRICS = ["title", "playoff", "shield", "cup", "ucl", "europa",
           "conf", "releg", "promo"]


def _cause(prev: pd.Series, now: pd.Series) -> str:
    """Why did this league's projection move between the two snapshots?"""
    pn, nn = prev.get("n_played"), now.get("n_played")
    if pd.notna(pn) and pd.notna(nn) and float(nn) > float(pn):
        return "result"
    for col in ("config_id", "code_rev"):
        a, b = prev.get(col), now.get(col)
        if pd.notna(a) and pd.notna(b) and a != b:
            return "model"
    return "refresh"


def compute_race_deltas(df: pd.DataFrame, min_delta: float = 0.3) -> dict:
    """{league: {metric: {team, now, delta, cause, from, to}}}.

    For each metric the entry is the CURRENT leader (max value in the latest
    snapshot) and its change vs the same team one snapshot earlier. A metric is
    emitted only when the leader existed in both snapshots and either moved at
    least `min_delta` pp or a real result came in (so "played, barely moved" is
    still shown, but pure zero-churn noise is not).
    """
    metrics = [m for m in METRICS if m in df.columns]
    out: dict[str, dict] = {}
    for league, grp in df.groupby("league"):
        dates = sorted(grp["snapshot_date"].unique())
        if len(dates) < 2:
            continue
        prev_snap = grp[grp["snapshot_date"] == dates[-2]]
        now_snap = grp[grp["snapshot_date"] == dates[-1]]
        prev_by_team = {r["team"]: r for _, r in prev_snap.iterrows()}
        league_entry: dict[str, dict] = {}
        for m in metrics:
            valid = now_snap[now_snap[m].notna()]
            if valid.empty:
                continue
            leader = valid.loc[valid[m].idxmax()]
            team = leader["team"]
            prev_row = prev_by_team.get(team)
            if prev_row is None or pd.isna(prev_row.get(m)):
                continue
            delta = round(float(leader[m]) - float(prev_row[m]), 1)
            cause = _cause(prev_row, leader)
            # keep if it moved enough, or a result landed (worth showing "steady after a result")
            if abs(delta) < min_delta and cause != "result":
                continue
            league_entry[m] = {
                "team": str(team),
                "now": round(float(leader[m]), 1),
                "delta": delta,
                "cause": cause,
                "from": str(dates[-2]),
                "to": str(dates[-1]),
            }
        if league_entry:
            out[str(league)] = league_entry
    return out


def append_race_delta_history(leagues: dict, path: Path = HISTORY_ARCHIVE) -> int:
    """Flatten {league: {metric: {team, now, delta, cause, from, to}}} into rows
    and append-dedup to `path`. Reuses archive_odds_snapshot's append_snapshot
    for the same idempotent-append contract used by odds_history.parquet: a
    same-day rerun over the same snapshot pair must not duplicate rows."""
    rows = []
    for league, metrics in leagues.items():
        for metric, v in metrics.items():
            rows.append({
                "league": league, "metric": metric, "team": v["team"],
                "now": v["now"], "delta": v["delta"], "cause": v["cause"],
                "from_date": v["from"], "to_date": v["to"], "snapshot_date": v["to"],
            })
    return append_snapshot(rows, path, dedup_keys=["league", "metric", "to_date"])


def main() -> None:
    generated = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    added = 0
    if not HISTORY.exists():
        payload = {"status": "empty", "generated": generated, "leagues": {},
                   "reason": "No odds history accrued yet."}
    else:
        df = pd.read_parquet(HISTORY)
        leagues = compute_race_deltas(df)
        if leagues:
            added = append_race_delta_history(leagues)
        payload = {"status": "ok" if leagues else "thin",
                   "generated": generated,
                   "cause_label": {"result": "new result",
                                   "model": "model update",
                                   "refresh": "refresh"},
                   "leagues": leagues,
                   "reason": None if leagues else
                   "Not enough snapshot history yet — deltas appear as builds accrue."}
    write_js_payload(OUT, "RACE_DELTAS", payload)
    n = sum(len(v) for v in payload["leagues"].values())
    print(f"[race-deltas] {payload['status']} · {len(payload['leagues'])} leagues, "
          f"{n} races → {OUT} · +{added} history rows")


if __name__ == "__main__":
    main()
