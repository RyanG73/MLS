#!/usr/bin/env python3
"""Drift-tracking report → webapp/data/drift.js (step 2, docs/projection-drift-tracking.md).

Reads data/odds_history.parquet + data/match_prob_history.parquet (written by
scripts/archive_odds_snapshot.py, which MUST run after every league build —
see scripts/build_all.sh) and computes four things:

  churn           per-league mean |delta outcome-odds| between the two most
                   recent snapshot builds where n_played is UNCHANGED (no new
                   matches played between them — a healthy build pair should
                   show ~0 movement). Alert threshold: mean |delta| > 1.5pp,
                   per docs/projection-drift-tracking.md. Also carries the
                   biggest individual team/outcome swings inside that same
                   no-new-matches window (distinct from build_movers.py,
                   which does NOT filter for "nothing happened" pairs).
  config_markers  snapshot_dates where the champion's config_id changed —
                   every dashboard using this data should draw a vertical
                   line here: drift AFTER a marker is expected, drift
                   WITHOUT one is a bug.
  kickoff_funnel  from match_prob_history, for matches that have since been
                   played (looked up in the CURRENTLY LOADED payload's played
                   games), the 3-way Brier of the probability quoted at each
                   days-to-kickoff bucket — does the model actually sharpen
                   as kickoff approaches, or just wobble?

Trajectories (per-(league, team) outcome-odds time series, for the UI
sparkline) are NOT in the main file — they're written one small file per
league (webapp/data/drift-traj/<league>.js), loaded lazily like
webapp/data/news/<league>.js, because 26 leagues × ~20 teams × up to 180
points × 14 fields does not belong in a payload every page view fetches.

Every metric degrades to an explicit "insufficient history" state instead of
a crash or a misleading number — most of this becomes meaningful only after
2-4 weeks of nightly accrual. See docs/drift-playbook.md for how to read it.

Usage:
    python scripts/build_drift_report.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd

from scripts.archive_odds_snapshot import _DATA, _NON_PAYLOAD, _ODDS_KEYS, _load_payload
from scripts.payload_utils import registry_ids, write_js_payload

ODDS_HIST = Path("data/odds_history.parquet")
MATCH_HIST = Path("data/match_prob_history.parquet")
OUT = Path("webapp/data/drift.js")
TRAJ_DIR = Path("webapp/data/drift-traj")

CHURN_ALERT_PP = 1.5           # mean |delta| percentage points with zero new matches
FUNNEL_BUCKETS = [(7, 999, "7d+"), (4, 6, "4-6d"), (2, 3, "2-3d"), (0, 1, "0-1d")]
_TRAJ_MAX_POINTS = 180


def _n(v):
    """JSON-safe scalar: numpy/pandas NaN → None, numpy scalar → native Python."""
    if v is None:
        return None
    if isinstance(v, float) and (np.isnan(v) or np.isinf(v)):
        return None
    if hasattr(v, "item"):
        return v.item()
    return v


def load_odds_history() -> pd.DataFrame | None:
    if not ODDS_HIST.exists():
        return None
    df = pd.read_parquet(ODDS_HIST)
    return df if len(df) else None


def load_match_history() -> pd.DataFrame | None:
    if not MATCH_HIST.exists():
        return None
    df = pd.read_parquet(MATCH_HIST)
    return df if len(df) else None


def _latest_no_new_match_pair(league_df: pd.DataFrame) -> tuple[str, str] | None:
    """The most recent two consecutive snapshot_dates for this league where
    n_played didn't change — i.e. nothing happened between the builds, so any
    odds movement is pure churn, not information response."""
    dates = sorted(league_df["snapshot_date"].unique())
    for prev, cur in zip(reversed(dates[:-1]), reversed(dates[1:])):
        n_prev = league_df.loc[league_df["snapshot_date"] == prev, "n_played"]
        n_cur = league_df.loc[league_df["snapshot_date"] == cur, "n_played"]
        if len(n_prev) and len(n_cur) and n_prev.iloc[0] == n_cur.iloc[0]:
            return prev, cur
    return None


def compute_churn(hist: pd.DataFrame) -> dict:
    """Per-league churn index + top individual movers within the same window."""
    out = {}
    for league, g in hist.groupby("league"):
        pair = _latest_no_new_match_pair(g)
        if pair is None:
            out[league] = {"status": "insufficient_history",
                           "note": "need ≥2 same-n_played consecutive snapshots"}
            continue
        prev_date, cur_date = pair
        prev = g[g["snapshot_date"] == prev_date].set_index("team")
        cur = g[g["snapshot_date"] == cur_date].set_index("team")
        teams = sorted(set(prev.index) & set(cur.index))
        deltas, movers = [], []
        for team in teams:
            for k in _ODDS_KEYS:
                pv, cv = prev.loc[team, k], cur.loc[team, k]
                if pd.isna(pv) or pd.isna(cv):
                    continue
                d = float(cv) - float(pv)
                deltas.append(abs(d))
                if abs(d) > 0.05:   # ignore sub-0.05pp float noise
                    movers.append({"team": team, "key": k, "delta": round(d, 2)})
        movers.sort(key=lambda m: -abs(m["delta"]))
        index = round(float(np.mean(deltas)), 3) if deltas else 0.0
        out[league] = {
            "status": "ok", "index_pp": index,
            "alert": index > CHURN_ALERT_PP,
            "window": f"{prev_date}→{cur_date}", "n_teams": len(teams),
            "top_movers": movers[:5],
        }
    return out


def compute_trajectories(hist: pd.DataFrame, current_season: dict) -> dict:
    """{league: {team: [{date, elo, proj_pts, season, <outcome keys...>}, ...]}}
    Written one file per league (see write_trajectory_files) — never shipped
    inside the main drift.js payload.

    `current_season` maps league_id -> that league's current payload `season`
    value (an opaque per-league identifier — a calendar year for most leagues,
    a torneo ordinal for Liga MX). Rows whose recorded season doesn't match are
    excluded so the public trajectory never leaks a prior season across a
    rollover (docs/intelligence-hub-implementation-instructions.md §4.9). Rows
    with season=None (accrued before this field was captured) are kept as-is
    rather than silently dropped, since we can't bound what we don't know.
    """
    out: dict = {}
    cols = ["elo", "proj_pts", "season"] + _ODDS_KEYS
    for (league, team), g in hist.groupby(["league", "team"]):
        season = current_season.get(league)
        if season is not None and "season" in g.columns:
            g = g[g["season"].isna() | (g["season"] == season)]
        g = g.sort_values("snapshot_date").tail(_TRAJ_MAX_POINTS)
        series = [{"date": row["snapshot_date"],
                  **{c: _n(row[c]) for c in cols}}
                 for _, row in g.iterrows()]
        out.setdefault(league, {})[team] = series
    return out


def write_trajectory_files(trajectories: dict, generated: str) -> int:
    """One small window.DRIFT_TRAJ file per league, lazy-loaded like
    webapp/data/news/<league>.js — keeps the always-fetched drift.js small
    regardless of how many teams/leagues/snapshots have accrued.

    Writes a file for EVERY registry league, not just leagues with accrued
    history — an empty {} beats a 404 in the console for leagues that have
    never been archived yet ('soon' placeholders, or a league added since the
    last archiver run). Same fix as build_news.py's registry_ids() use.
    """
    all_leagues = set(trajectories) | registry_ids()
    for league in all_leagues:
        write_js_payload(TRAJ_DIR / f"{league}.js", "DRIFT_TRAJ",
                         {"league": league, "generated": generated,
                          "teams": trajectories.get(league, {})})
    return len(all_leagues)


def compute_config_markers(hist: pd.DataFrame) -> list[dict]:
    """snapshot_dates where config_id changed (global — one champion, every league)."""
    by_date = (hist[["snapshot_date", "config_id"]]
               .dropna(subset=["config_id"])
               .drop_duplicates()
               .sort_values("snapshot_date"))
    markers, prev_id = [], None
    for _, row in by_date.iterrows():
        cid = row["config_id"]
        if cid != prev_id:
            markers.append({"date": row["snapshot_date"], "config_id": cid})
            prev_id = cid
    return markers


def _played_lookup(payloads: dict) -> dict[tuple, str]:
    """{(league, home, away, date): result} from every currently-loaded payload's
    played games — the join target for the kickoff funnel."""
    out = {}
    for lid, payload in payloads.items():
        for g in payload.get("games") or []:
            if g.get("result") is not None and g.get("date"):
                out[(lid, g.get("home"), g.get("away"), g["date"])] = g["result"]
    return out


def compute_kickoff_funnel(match_hist: pd.DataFrame | None, payloads: dict) -> dict:
    """3-way Brier of the quoted probability, bucketed by days-to-kickoff, for
    matches that have since been played. Needs match_prob_history rows whose
    fixture later resolved — legitimately empty until matches complete."""
    if match_hist is None:
        return {"status": "insufficient_history",
                "note": "match_prob_history.parquet not accrued yet"}
    played = _played_lookup(payloads)
    if not played:
        return {"status": "insufficient_history", "note": "no played games loaded"}
    bucket_sums: dict[str, list[float]] = {b[2]: [] for b in FUNNEL_BUCKETS}
    matched = 0
    for _, r in match_hist.iterrows():
        key = (r["league"], r["home"], r["away"], r["date"])
        result = played.get(key)
        if result is None or pd.isna(r.get("days_to_kickoff")) or pd.isna(r.get("pH")):
            continue
        one_hot = {"H": (1, 0, 0), "D": (0, 1, 0), "A": (0, 0, 1)}.get(result)
        if one_hot is None:
            continue
        brier = ((r["pH"] - one_hot[0]) ** 2 + (r["pD"] - one_hot[1]) ** 2
                 + (r["pA"] - one_hot[2]) ** 2)
        dtk = r["days_to_kickoff"]
        for lo, hi, label in FUNNEL_BUCKETS:
            if lo <= dtk <= hi:
                bucket_sums[label].append(brier)
                matched += 1
                break
    if matched == 0:
        return {"status": "insufficient_history",
                "note": "no archived quote yet matches a completed fixture"}
    buckets = [{"label": label, "n": len(vals),
               "brier": round(float(np.mean(vals)), 4) if vals else None}
              for _, _, label in FUNNEL_BUCKETS for vals in [bucket_sums[label]]]
    return {"status": "ok", "n_matched": matched, "buckets": buckets}


def load_all_payloads() -> dict:
    payloads = {}
    for p in sorted(_DATA.glob("*.js")):
        if p.name in _NON_PAYLOAD:
            continue
        try:
            payload = _load_payload(p)
        except Exception:
            continue
        if payload.get("status") != "placeholder":
            payloads[p.stem] = payload
    return payloads


def build() -> tuple[dict, dict]:
    """Returns (main_payload, trajectories) — trajectories are written
    separately (per-league files), never embedded in the main payload."""
    hist = load_odds_history()
    match_hist = load_match_history()
    payloads = load_all_payloads()
    from datetime import datetime, timezone
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    if hist is None:
        return ({"generated": generated, "status": "insufficient_history",
                 "note": "odds_history.parquet empty or missing — accrues after the "
                         "next few nightly builds"}, {})
    main = {
        "generated": generated,
        "status": "ok",
        "n_snapshots": int(hist["snapshot_date"].nunique()),
        "churn": compute_churn(hist),
        "config_markers": compute_config_markers(hist),
        "kickoff_funnel": compute_kickoff_funnel(match_hist, payloads),
    }
    current_season = {lid: p.get("season") for lid, p in payloads.items()}
    return main, compute_trajectories(hist, current_season)


def main() -> int:
    data, trajectories = build()
    write_js_payload(OUT, "DRIFT_DATA", data)
    n_traj = write_trajectory_files(trajectories, data.get("generated", ""))
    n_leagues = len((data.get("churn") or {}))
    alerts = [lg for lg, c in (data.get("churn") or {}).items() if c.get("alert")]
    print(f"Wrote {OUT} · {data.get('n_snapshots', 0)} snapshot dates · "
          f"{n_leagues} leagues in churn report · {n_traj} trajectory files"
          + (f" · ALERTS: {alerts}" if alerts else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
