#!/usr/bin/env python3
"""S4: build canonical intelligence events (docs/intelligence-hub-
implementation-instructions.md §4.4, §5 S4).

Detects five event types between the two most recent snapshot dates in
data/odds_history.parquet (S0/S1 — already public, already committed):

  forecast_move       a target metric moved by more than the noise floor
  threshold_crossing  a target metric crossed 25%/50%/75%
  result              a real match result arrived (n_played increased),
                      regardless of how much it moved anything
  model_change        the champion config_id changed between builds
                      (league-scoped, no team_id)
  data_health         the archived history is stale (no build in N days)

Reuses build_race_deltas.py's existing result/model/refresh classification
(_cause) rather than duplicating it. Suppresses forecast_move/
threshold_crossing/result events caused only by "refresh" (harmless build
churn) per docs/intelligence-hub-implementation-instructions.md §4.5 — a
model_change event still surfaces a real config change separately, so it
stays visible in the audit timeline without masquerading as football news.

ATTRIBUTION SCOPE: this is observational attribution only (cause_class:
result/model/refresh). The deeper counterfactual/Shapley decomposition
§4.6 also describes — replaying archived S3 simulation states with event
groups toggled independently — is separate, larger follow-on work once
enough archived states have accrued to replay against. Every event's
attribution_quality here is "observational" or "unavailable" (per §4.6's
own downgrade path), never "counterfactual".

Every event is derived only from already-public data (data/odds_history.parquet,
data/match_prob_history.parquet), so public_safe=True unconditionally and the
output (data/intelligence_events.parquet, data/intelligence_events_latest.json)
is committed to the repo — unlike S3's data/intelligence_snapshots/, which
carries the private pmatrix and is gitignored.

Usage:
    python scripts/build_intelligence_events.py            # MLS only, for now
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.archive_odds_snapshot import append_snapshot  # noqa: E402
from scripts.build_race_deltas import METRICS, _cause  # noqa: E402
from scripts.payload_utils import canonical_team_id, make_event_id  # noqa: E402

HISTORY = Path("data/odds_history.parquet")
MATCH_HISTORY = Path("data/match_prob_history.parquet")
EVENTS_OUT = Path("data/intelligence_events.parquet")
LATEST_INDEX_OUT = Path("data/intelligence_events_latest.json")

THRESHOLDS = (25.0, 50.0, 75.0)
MIN_MOVE_PP = 0.3          # noise floor, matches build_race_deltas.py
STALE_AFTER_DAYS = 2


def _crossed_thresholds(before: float, after: float, thresholds=THRESHOLDS) -> list[float]:
    return [t for t in thresholds if (before < t <= after) or (after < t <= before)]


def compute_materiality_score(delta_pp: float, crossed: list[float], cause_class: str) -> float:
    """First-pass materiality heuristic (docs/intelligence-hub-implementation-
    instructions.md §4.5): combines absolute movement, threshold-crossing, and
    whether a real result caused it. Deliberately does NOT yet incorporate
    fixture-impact-vs-remaining-uncertainty, pinned-team/rival relevance, or
    user notification thresholds — those depend on features not built yet
    (Match Leverage Radar, favorites/auth). Documented here rather than
    silently omitted."""
    move_component = min(abs(delta_pp) / 50.0, 1.0) * 0.6
    threshold_component = 0.3 if crossed else 0.0
    result_component = 0.1 if cause_class == "result" else 0.0
    return round(move_component + threshold_component + result_component, 3)


def _resolved_fixture_evidence(match_hist: pd.DataFrame, team_id, prev_date: str, cur_date: str,
                               team_name: str | None = None) -> list[str]:
    """Fixture(s) that were listed as upcoming for `team_id` as of `prev_date`
    but are no longer upcoming as of `cur_date` — i.e. resolved between the
    two snapshots. The evidence for a "result" event."""
    if match_hist is None or "home_id" not in match_hist.columns:
        return []
    id_match = (match_hist["home_id"].astype(str) == str(team_id)) | (match_hist["away_id"].astype(str) == str(team_id))
    name_match = ((match_hist.get("home") == team_name) | (match_hist.get("away") == team_name)
                  if team_name and "home" in match_hist and "away" in match_hist else False)
    is_team = id_match | name_match
    prev_ids = set(match_hist.loc[is_team & (match_hist["snapshot_date"] == prev_date), "fixture_id"].dropna())
    cur_ids = set(match_hist.loc[is_team & (match_hist["snapshot_date"] == cur_date), "fixture_id"].dropna())
    resolved = sorted(prev_ids - cur_ids)
    return [f"fixture:{fid}" for fid in resolved]


def _event_row(*, event_type, league_id, season, team_id, target_metric,
                before_pct, after_pct, delta_pp, materiality_score_, cause_class,
                attribution_kind, evidence_ids, attribution_quality, confidence_status,
                data_freshness, notes, generated_at, effective_at, config_id, code_rev) -> dict:
    return {
        "schema_version": 1,
        "event_id": make_event_id(event_type, team_id, target_metric, effective_at, evidence_ids),
        "generated_at": generated_at, "effective_at": effective_at,
        "league_id": league_id, "season": season,
        "season_id": str(season) if season is not None and pd.notna(season) else None,
        "team_id": team_id,
        "event_type": event_type, "target_metric": target_metric,
        "before_pct": before_pct, "after_pct": after_pct, "delta_pp": delta_pp,
        "materiality_score": materiality_score_, "cause_class": cause_class,
        "attribution_kind": attribution_kind, "evidence_ids": json.dumps(evidence_ids),
        "attribution_quality": attribution_quality,
        "attribution": json.dumps([{
            "kind": attribution_kind,
            "delta_pp": delta_pp,
            "evidence_ids": evidence_ids,
        }] if delta_pp is not None else []),
        "confidence_status": confidence_status, "data_freshness": data_freshness,
        "confidence": json.dumps({
            "status": confidence_status,
            "data_freshness": data_freshness,
            "attribution_quality": attribution_quality,
            "notes": notes,
        }),
        "notes": json.dumps(notes),
        "snapshot_before_id": None, "snapshot_after_id": None,
        "simulation_version": "v1",
        "template_id": "intelligence-event", "template_version": 1,
        "config_id": config_id, "code_rev": code_rev, "public_safe": True,
    }


def _data_health_events(dates: list[str], today: dt.date, league_id: str, generated_at: str,
                         stale_after_days: int = STALE_AFTER_DAYS) -> list[dict]:
    if not dates:
        return []
    latest = dt.date.fromisoformat(dates[-1])
    age_days = (today - latest).days
    if age_days <= stale_after_days:
        return []
    return [_event_row(
        event_type="data_health", league_id=league_id, season=None, team_id=None,
        target_metric=None, before_pct=None, after_pct=None, delta_pp=None,
        materiality_score_=1.0, cause_class="data_health",
        attribution_kind="data_health", evidence_ids=[f"snapshot:{dates[-1]}"],
        attribution_quality="observational", confidence_status="unsupported",
        data_freshness="stale", notes=[f"latest snapshot is {age_days} days old"],
        generated_at=generated_at, effective_at=dates[-1],
        config_id=None, code_rev=None,
    )]


def build_events(hist: pd.DataFrame, match_hist: pd.DataFrame | None, league_id: str = "mls",
                  generated_at: str | None = None, today: dt.date | None = None) -> list[dict]:
    """Detect intelligence events between the two most recent snapshot dates
    for `league_id`. Empty-safe: fewer than 2 snapshots yields no movement/
    threshold/result/model events (a data_health event can still fire)."""
    generated_at = generated_at or dt.datetime.now(dt.timezone.utc).isoformat()
    today = today or dt.datetime.now(dt.timezone.utc).date()
    events: list[dict] = []
    grp = hist[hist["league"] == league_id]
    if grp.empty:
        return events
    dates = sorted(grp["snapshot_date"].unique())

    events.extend(_data_health_events(dates, today, league_id, generated_at))
    if len(dates) < 2:
        return events
    prev_date, cur_date = dates[-2], dates[-1]
    prev_snap = grp[grp["snapshot_date"] == prev_date].set_index("team")
    cur_snap = grp[grp["snapshot_date"] == cur_date].set_index("team")

    prev_cfg = prev_snap["config_id"].dropna()
    cur_cfg = cur_snap["config_id"].dropna()
    if len(prev_cfg) and len(cur_cfg) and prev_cfg.iloc[0] != cur_cfg.iloc[0]:
        cur_rev = cur_snap["code_rev"].dropna()
        events.append(_event_row(
            event_type="model_change", league_id=league_id, season=None, team_id=None,
            target_metric=None, before_pct=None, after_pct=None, delta_pp=None,
            materiality_score_=1.0, cause_class="model",
            attribution_kind="model", evidence_ids=[f"config:{cur_cfg.iloc[0]}"],
            attribution_quality="observational", confidence_status="supported",
            data_freshness="current", notes=[],
            generated_at=generated_at, effective_at=cur_date,
            config_id=cur_cfg.iloc[0], code_rev=cur_rev.iloc[0] if len(cur_rev) else None,
        ))

    metrics = [m for m in METRICS if m in grp.columns]
    for team in sorted(set(prev_snap.index) & set(cur_snap.index)):
        prow, crow = prev_snap.loc[team], cur_snap.loc[team]
        raw_team_id = crow.get("team_id") if pd.notna(crow.get("team_id")) else prow.get("team_id")
        team_id = canonical_team_id(str(team), raw_team_id)
        cause = _cause(prow, crow)
        if cause == "refresh":
            continue  # suppress fan-facing events from harmless build churn
        for metric in metrics:
            bv, av = prow.get(metric), crow.get(metric)
            if pd.isna(bv) or pd.isna(av):
                continue
            bv, av = float(bv), float(av)
            delta = round(av - bv, 1)
            if abs(delta) < MIN_MOVE_PP and cause != "result":
                continue
            crossed = _crossed_thresholds(bv, av)
            if crossed:
                event_type = "threshold_crossing"
            elif cause == "result":
                event_type = "result"
            else:
                event_type = "forecast_move"
            evidence_ids = (_resolved_fixture_evidence(
                match_hist, team_id, prev_date, cur_date, team_name=str(team))
                if cause == "result" and pd.notna(team_id) and match_hist is not None else [])
            if cause == "result" and not evidence_ids:
                attribution_quality, confidence_status, notes = (
                    "unavailable", "unsupported",
                    ["resolving fixture not found in match_prob_history.parquet"])
            else:
                attribution_quality, confidence_status, notes = "observational", "supported", []
            events.append(_event_row(
                event_type=event_type, league_id=league_id, season=crow.get("season"),
                team_id=team_id, target_metric=metric,
                before_pct=bv, after_pct=av, delta_pp=delta,
                materiality_score_=compute_materiality_score(delta, crossed, cause),
                cause_class=cause, attribution_kind=cause, evidence_ids=evidence_ids,
                attribution_quality=attribution_quality, confidence_status=confidence_status,
                data_freshness="current", notes=notes,
                generated_at=generated_at, effective_at=cur_date,
                config_id=crow.get("config_id"), code_rev=crow.get("code_rev"),
            ))
    return events


def append_events(events: list[dict], path: Path = EVENTS_OUT) -> int:
    if not events:
        return 0
    return append_snapshot(events, path, dedup_keys=["event_id"])


def build_latest_index(events_df: pd.DataFrame, top_n: int = 10) -> dict:
    """{team_id: [most recent `top_n` events, newest first]} — the "compile
    current per-team snapshots for fast API delivery" bullet. Recomputed
    fresh from the full accrued archive every run (not itself appended)."""
    index: dict[str, list[dict]] = {}
    with_team = events_df[events_df["team_id"].notna()].sort_values("effective_at", ascending=False)
    for team_id, grp in with_team.groupby("team_id"):
        rows = []
        for _, r in grp.head(top_n).iterrows():
            rows.append({
                "event_id": r["event_id"], "event_type": r["event_type"],
                "target_metric": r["target_metric"], "before_pct": r["before_pct"],
                "after_pct": r["after_pct"], "delta_pp": r["delta_pp"],
                "materiality_score": r["materiality_score"], "cause_class": r["cause_class"],
                "evidence_ids": json.loads(r["evidence_ids"]) if r["evidence_ids"] else [],
                "attribution_quality": r["attribution_quality"],
                "effective_at": r["effective_at"],
            })
        index[str(team_id)] = rows
    return index


def write_latest_index(index: dict, path: Path = LATEST_INDEX_OUT) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(index, separators=(",", ":")))


def main() -> int:
    if not HISTORY.exists():
        print("[intelligence-events] no odds history yet — nothing to detect", file=sys.stderr)
        return 0
    hist = pd.read_parquet(HISTORY)
    match_hist = pd.read_parquet(MATCH_HISTORY) if MATCH_HISTORY.exists() else None
    generated_at = dt.datetime.now(dt.timezone.utc).isoformat()
    candidates = []
    for league_id in sorted(hist["league"].dropna().unique()):
        candidates.extend(build_events(
            hist, match_hist, league_id=str(league_id), generated_at=generated_at))
    added = append_events(candidates)
    all_events = pd.read_parquet(EVENTS_OUT) if EVENTS_OUT.exists() else pd.DataFrame()
    league_indexes = {}
    if len(all_events):
        for league_id, rows in all_events.groupby("league_id"):
            league_indexes[str(league_id)] = build_latest_index(rows)
    write_latest_index({
        "schema_version": 2,
        "generated_at": generated_at,
        "leagues": league_indexes,
    })
    print(f"[intelligence-events] {len(candidates)} candidate events across "
          f"{len(league_indexes)} leagues, +{added} new after dedup, "
          f"{len(all_events)} total accrued")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
