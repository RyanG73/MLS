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

# ── Saturated-baseline suppression (2026-07-31 home feedback: "biggest movers
#    don't work well when there are new leagues in the model and a team goes
#    from 0 to 100 or reverse because they are brand new").
#    A metric parked at an exact certainty (0.0 / 100.0) and then swinging tens
#    of points is a bootstrap or end-of-season placeholder collapsing into a
#    real forecast, not new football evidence. The existing reset guards miss it
#    because they require n_played to be unchanged, and a brand-new league's
#    match count keeps climbing while its odds stay pinned (verified in
#    odds_history.parquet: romania-liga1 title 100→0, finland-veikkausliiga
#    releg 100→0, both with n_played moving).
#    Small moves off an exact 0 (0.0 → 3.4) stay — those are real.
SATURATION_EPS = 0.5
SATURATED_MIN_DELTA = 25.0

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
    movers, span, earliest, _ = compute_movers_with_diagnostics(
        df, min_delta=min_delta, top_n=top_n, window_days=window_days)
    return movers, span, earliest


def _same_number(a, b) -> bool:
    return pd.notna(a) and pd.notna(b) and float(a) == float(b)


def _is_saturated(v) -> bool:
    """True when a probability sits at an exact certainty endpoint."""
    if pd.isna(v):
        return False
    v = float(v)
    return v <= SATURATION_EPS or v >= 100.0 - SATURATION_EPS


def _latest_continuous_segment(grp: pd.DataFrame) -> tuple[pd.DataFrame, list[dict]]:
    """Keep the current season/run and label prior rows as reset boundaries."""
    resets = []
    start = 0
    rows = list(grp.to_dict("records"))
    for i in range(1, len(rows)):
        prior, current = rows[i - 1], rows[i]
        prior_season, season = prior.get("season"), current.get("season")
        season_changed = (
            pd.notna(prior_season) and pd.notna(season)
            and str(prior_season) != str(season)
        )
        played_reset = (
            pd.notna(prior.get("n_played")) and pd.notna(current.get("n_played"))
            and float(current["n_played"]) < float(prior["n_played"])
        )
        if season_changed or played_reset:
            resets.append({
                "date": str(current.get("snapshot_date") or ""),
                "state": "reset",
                "reason": "season_or_schedule_reset",
            })
            start = i
    return grp.iloc[start:].copy(), resets


def _metric_reset_indexes(grp: pd.DataFrame, metric: str) -> set[int]:
    """Find reset-like extreme points without suppressing real clinches.

    A jump of roughly 100 percentage points while the played-match count is
    unchanged is a pipeline reset, not new football evidence. A middle point
    that immediately returns to its prior value is also a reset spike.
    """
    reset: set[int] = set()
    values = list(grp[metric])
    played = list(grp["n_played"]) if "n_played" in grp else [None] * len(grp)
    for i in range(1, len(values)):
        a, b = values[i - 1], values[i]
        if pd.isna(a) or pd.isna(b):
            continue
        stable_played = _same_number(played[i - 1], played[i])
        if stable_played and abs(float(b) - float(a)) >= 95:
            reset.add(i)
    for i in range(1, len(values) - 1):
        a, b, c = values[i - 1], values[i], values[i + 1]
        if any(pd.isna(value) for value in (a, b, c)):
            continue
        if abs(float(b) - float(a)) >= 80 and abs(float(c) - float(a)) <= 5:
            reset.add(i)
    return reset


def compute_movers_with_diagnostics(
    df: pd.DataFrame,
    min_delta: float = 1.5,
    top_n: int = 200,
    window_days: int = WINDOW_DAYS,
) -> tuple[list[dict], int, str, dict]:
    """Top-|Δ| odds moves per (league, team) over a trailing `window_days` window.

    For each team, `prev` is the latest snapshot at or before (latest snapshot
    overall - window_days); if the archived history doesn't go back that far yet,
    `prev` falls back to that team's earliest USABLE snapshot (compares the whole
    available history rather than nothing). Returns (movers, actual_span_days,
    earliest_used_date) so the client can label the window honestly (e.g. "since
    Jul 7" pre-30-days).

    First observations, season resets, missing baselines, and reset-like extreme
    points are classified and withheld. They are returned as diagnostics so the
    client can disclose them instead of presenting ±100pp artifacts as football
    movement.
    """
    metrics = [m for m in METRICS if m in df.columns]
    region_of = _load_region_map()
    out: list[dict] = []
    used_dates: list[pd.Timestamp] = []
    diagnostics = {
        "first_observation": 0,
        "reset": 0,
        "missing_baseline": 0,
        "saturated_baseline": 0,
        "observations": [],
    }
    for (league, team), grp in df.groupby(["league", "team"]):
        grp = grp.assign(_d=pd.to_datetime(grp["snapshot_date"])).sort_values("_d")
        grp, boundary_resets = _latest_continuous_segment(grp)
        for reset in boundary_resets:
            diagnostics["reset"] += 1
            diagnostics["observations"].append({
                "league": league, "team": team, **reset,
            })
        for m in metrics:
            metric_rows = grp[grp[m].notna()].copy()
            if len(metric_rows) >= 2:
                first_value = float(metric_rows.iloc[0][m])
                second_value = float(metric_rows.iloc[1][m])
                if first_value == 100.0 and abs(first_value - second_value) >= 50.0:
                    first_row = metric_rows.iloc[0]
                    diagnostics["reset"] += 1
                    diagnostics["observations"].append({
                        "league": league, "team": team, "metric": m,
                        "date": str(first_row.get("snapshot_date") or ""),
                        "state": "reset",
                        "reason": "bootstrap_sentinel",
                    })
                    metric_rows = metric_rows.iloc[1:].copy()
            reset_indexes = _metric_reset_indexes(metric_rows, m)
            if reset_indexes:
                for idx in sorted(reset_indexes):
                    row = metric_rows.iloc[idx]
                    diagnostics["reset"] += 1
                    diagnostics["observations"].append({
                        "league": league, "team": team, "metric": m,
                        "date": str(row.get("snapshot_date") or ""),
                        "state": "reset",
                        "reason": "extreme_change_without_match_evidence",
                    })
                metric_rows = metric_rows.drop(metric_rows.index[list(reset_indexes)])
            if len(metric_rows) < 2:
                diagnostics["first_observation"] += 1
                diagnostics["observations"].append({
                    "league": league, "team": team, "metric": m,
                    "date": str(metric_rows.iloc[-1]["snapshot_date"])
                    if len(metric_rows) else "",
                    "state": "first_observation",
                    "reason": "no_comparable_prior_snapshot",
                })
                continue
            now = metric_rows.iloc[-1]
            cutoff = now["_d"] - pd.Timedelta(days=window_days)
            eligible = metric_rows[metric_rows["_d"] <= cutoff]
            prev = eligible.iloc[-1] if len(eligible) else metric_rows.iloc[0]
            if prev["_d"] == now["_d"]:
                diagnostics["missing_baseline"] += 1
                continue
            a, b = prev.get(m), now.get(m)
            if pd.isna(a) or pd.isna(b):
                diagnostics["missing_baseline"] += 1
                diagnostics["observations"].append({
                    "league": league, "team": team, "metric": m,
                    "date": str(now.get("snapshot_date") or ""),
                    "state": "missing_baseline",
                    "reason": "current_or_prior_value_missing",
                })
                continue
            delta = float(b) - float(a)
            if _is_saturated(a) and abs(delta) >= SATURATED_MIN_DELTA:
                diagnostics["saturated_baseline"] += 1
                diagnostics["observations"].append({
                    "league": league, "team": team, "metric": m,
                    "date": str(now.get("snapshot_date") or ""),
                    "state": "saturated_baseline",
                    "reason": "baseline_pinned_at_certainty",
                })
                continue
            used_dates.append(prev["_d"])
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
    diagnostics["observations"] = diagnostics["observations"][:200]
    return ranked[:top_n], global_span, earliest_used, diagnostics


def main() -> None:
    generated = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    if not HISTORY.exists():
        payload = {"status": "empty", "generated": generated, "movers": [],
                   "reason": "No odds history accrued yet."}
    else:
        df = pd.read_parquet(HISTORY)
        movers, span, earliest_used, diagnostics = compute_movers_with_diagnostics(df)
        window_label = f"last {WINDOW_DAYS} days" if span >= WINDOW_DAYS else \
            f"since tracking began ({earliest_used})"
        payload = {"status": "ok" if movers else "thin",
                   "generated": generated,
                   "window_days": WINDOW_DAYS,
                   "window_label": window_label,
                   "metric_labels": METRIC_LABEL,
                   "movers": movers,
                   "suppressed_observations": diagnostics,
                   "reason": None if movers else
                   "Not enough odds history yet — movers appear once builds accrue."}
    write_js_payload(OUT, "MOVERS_DATA", payload)
    print(f"[movers] {payload['status']} · {len(payload['movers'])} rows"
          f"{(' · ' + payload['window_label']) if 'window_label' in payload else ''} → {OUT}")


if __name__ == "__main__":
    main()
