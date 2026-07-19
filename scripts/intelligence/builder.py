"""Build deterministic, private per-team Intelligence Hub artifacts."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
from collections import Counter
from pathlib import Path
from typing import Any

import pandas as pd

from scripts.intelligence.schema import (
    FEATURES,
    SCHEMA_VERSION,
    TARGET_LABELS,
    feature,
)
from scripts.intelligence.simulation import fixture_leverage
from scripts.payload_utils import canonical_team_id, read_js_payload

ADVERSE_TARGETS = {"releg", "spoon"}
PRIVATE_ROOT = Path("data/team_intelligence")
LEAGUE_DATA = Path("webapp/data")
ODDS_HISTORY = Path("data/odds_history.parquet")
MATCH_HISTORY = Path("data/match_prob_history.parquet")
EVENT_HISTORY = Path("data/intelligence_events.parquet")


def _iso_date(value: Any) -> dt.date | None:
    if value is None:
        return None
    try:
        return dt.date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _finite(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if math.isfinite(float(value)) else None


def _json_value(value: Any) -> Any:
    if value is None or (not isinstance(value, (list, dict)) and pd.isna(value)):
        return None
    if hasattr(value, "item"):
        return value.item()
    return value


def _parse_json(value: Any, default):
    if isinstance(value, type(default)):
        return value
    if not isinstance(value, str) or not value:
        return default
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, type(default)) else default
    except json.JSONDecodeError:
        return default


def calendar_mode(payload: dict, today: dt.date | None = None) -> dict:
    """Classify active, lull, break, offseason, and preseason automatically."""
    today = today or dt.datetime.now(dt.timezone.utc).date()
    games = payload.get("games") or []
    played_dates = sorted(filter(None, (_iso_date(game.get("date"))
                                        for game in games
                                        if game.get("result") is not None)))
    upcoming_dates = sorted(filter(None, (_iso_date(game.get("date"))
                                          for game in games
                                          if game.get("result") is None)))
    last_match = played_dates[-1] if played_dates else None
    next_match = next((date for date in upcoming_dates if date >= today),
                      upcoming_dates[0] if upcoming_dates else None)
    days_since = (today - last_match).days if last_match else None
    days_to = (next_match - today).days if next_match else None
    status = payload.get("status")
    pct = (payload.get("league") or {}).get("pct_complete")

    if status == "preseason" or (not played_dates and upcoming_dates):
        mode, cadence = "preseason", "baseline"
    elif status == "completed" or (pct == 100 and not upcoming_dates):
        mode, cadence = "offseason", "monthly_or_event"
    elif next_match is not None and days_to is not None and days_to <= 7:
        mode, cadence = "active_matchweek", "weekly"
    elif next_match is not None and days_to is not None and days_to <= 21:
        mode, cadence = "short_lull", "event_driven"
    elif status == "live":
        mode, cadence = "scheduled_break", "phase_report"
    else:
        mode, cadence = "offseason", "monthly_or_event"
    return {
        "mode": mode,
        "cadence": cadence,
        "classified_at": today.isoformat(),
        "last_match": last_match.isoformat() if last_match else None,
        "next_match": next_match.isoformat() if next_match else None,
        "days_since_last_match": days_since,
        "days_to_next_match": days_to,
        "evidence": {
            "route_status": status,
            "pct_complete": pct,
            "played_fixture_count": len(played_dates),
            "upcoming_fixture_count": len(upcoming_dates),
        },
    }


def _target_rules(snapshot: dict) -> list[dict]:
    return snapshot.get("rules", {}).get("targets") or []


def _target_for_team(team: dict, snapshot: dict) -> str | None:
    published = team.get("published") or {}
    keys = [rule["key"] for rule in _target_rules(snapshot)
            if _finite(published.get(rule["key"])) is not None]
    if not keys:
        keys = [key for key in TARGET_LABELS if _finite(published.get(key)) is not None]
    if not keys:
        return None
    live = [key for key in keys if 5 <= float(published[key]) <= 95]
    candidates = live or keys
    return min(candidates, key=lambda key: abs(float(published[key]) - 50))


def _event_rows(events: pd.DataFrame, league_id: str, team_id: str) -> list[dict]:
    if events.empty or "league_id" not in events:
        return []
    rows = events[(events["league_id"] == league_id)
                  & (events["team_id"].astype(str) == str(team_id))]
    if rows.empty:
        return []
    rows = rows.sort_values(["effective_at", "materiality_score"], ascending=[False, False])
    out = []
    for _, row in rows.iterrows():
        evidence = _parse_json(row.get("evidence_ids"), [])
        notes = _parse_json(row.get("notes"), [])
        out.append({
            "event_id": row.get("event_id"),
            "event_type": row.get("event_type"),
            "target_metric": row.get("target_metric"),
            "before_pct": _finite(row.get("before_pct")),
            "after_pct": _finite(row.get("after_pct")),
            "delta_pp": _finite(row.get("delta_pp")),
            "materiality_score": _finite(row.get("materiality_score")) or 0,
            "cause_class": row.get("cause_class"),
            "attribution_quality": row.get("attribution_quality") or "unavailable",
            "confidence_status": row.get("confidence_status") or "unsupported",
            "effective_at": row.get("effective_at"),
            "evidence_ids": evidence,
            "notes": notes,
            "config_id": _json_value(row.get("config_id")),
            "public_safe": bool(row.get("public_safe", False)),
        })
    return out


def _trajectory_rows(history: pd.DataFrame, league_id: str,
                     team_id: str, team_name: str) -> list[dict]:
    if history.empty:
        return []
    rows = history[history["league"] == league_id]
    if "team_id" in rows:
        id_match = rows["team_id"].astype(str) == str(team_id)
        rows = rows[id_match | (rows["team"] == team_name)]
    else:
        rows = rows[rows["team"] == team_name]
    result = []
    for _, row in rows.sort_values("snapshot_date").iterrows():
        values = {
            key: _finite(row.get(key))
            for key in TARGET_LABELS
            if key in row and _finite(row.get(key)) is not None
        }
        result.append({
            "snapshot_date": str(row.get("snapshot_date")),
            "season_id": str(row.get("season")) if pd.notna(row.get("season")) else None,
            "config_id": _json_value(row.get("config_id")),
            "proj_pts": _finite(row.get("proj_pts")),
            "values": values,
        })
    return result


def _receipts(payload: dict, match_history: pd.DataFrame, league_id: str,
              team_id: str, team_name: str) -> list[dict]:
    if match_history.empty:
        return []
    completed = [game for game in payload.get("games") or []
                 if game.get("result") in {"H", "D", "A"}
                 and team_name in (game.get("home"), game.get("away"))]
    receipts = []
    for game in completed:
        kickoff = _iso_date(game.get("date"))
        if not kickoff:
            continue
        candidates = match_history[
            (match_history["league"] == league_id)
            & (match_history["home"] == game.get("home"))
            & (match_history["away"] == game.get("away"))
        ]
        candidates = candidates[
            pd.to_datetime(candidates["snapshot_date"]).dt.date < kickoff]
        if candidates.empty:
            continue
        row = candidates.sort_values("snapshot_date").iloc[-1]
        probs = {"H": _finite(row.get("pH")), "D": _finite(row.get("pD")),
                 "A": _finite(row.get("pA"))}
        if any(value is None for value in probs.values()):
            continue
        actual = game["result"]
        brier = sum((probs[key] - (1.0 if key == actual else 0.0)) ** 2
                    for key in ("H", "D", "A"))
        fixture_id = row.get("fixture_id")
        receipts.append({
            "receipt_id": f"receipt:{fixture_id or hashlib.sha1(str(row.to_dict()).encode()).hexdigest()[:16]}",
            "fixture_id": _json_value(fixture_id),
            "home": game.get("home"),
            "away": game.get("away"),
            "date": game.get("date"),
            "snapshot_date": str(row.get("snapshot_date")),
            "cutoff_rule": "latest archived forecast strictly before kickoff date",
            "probabilities": probs,
            "result": actual,
            "score_brier": round(float(brier), 4),
            "config_id": _json_value(row.get("config_id")),
            "evidence_ids": [f"fixture:{fixture_id}"] if pd.notna(fixture_id) else [],
        })
    receipts.sort(key=lambda row: row["date"], reverse=True)
    return receipts


def _expectation(receipts: list[dict], team_name: str) -> dict | None:
    if not receipts:
        return None
    rows = []
    for receipt in receipts:
        is_home = receipt["home"] == team_name
        win = receipt["probabilities"]["H" if is_home else "A"]
        draw = receipt["probabilities"]["D"]
        expected = 3 * win + draw
        result = receipt["result"]
        actual = (3 if (is_home and result == "H") or (not is_home and result == "A")
                  else 1 if result == "D" else 0)
        rows.append((expected, actual, receipt["receipt_id"]))
    def window(size: int) -> dict:
        selected = rows[:size]
        expected = sum(row[0] for row in selected)
        actual = sum(row[1] for row in selected)
        return {
            "matches": len(selected),
            "expected_points": round(expected, 1),
            "actual_points": actual,
            "delta_points": round(actual - expected, 1),
            "receipt_ids": [row[2] for row in selected],
            "sample_warning": len(selected) < 5,
        }
    return {"season": window(len(rows)), "last_five": window(5),
            "last_ten": window(10) if len(rows) >= 6 else None,
            "wording": "Results are running ahead of pre-match expectation."
            if window(len(rows))["delta_points"] > 1 else
            "Results are running behind pre-match expectation."
            if window(len(rows))["delta_points"] < -1 else
            "Results are close to pre-match expectation."}


def _hydrate_fixture_ids(payload: dict, snapshot: dict) -> None:
    """Backfill stable IDs into legacy public payload rows from the snapshot."""
    lookup = {(row.get("home"), row.get("away"), str(row.get("date"))[:10]): row
              for row in snapshot.get("fixtures") or []}
    for game in payload.get("games") or []:
        if game.get("result") is not None:
            continue
        row = lookup.get((game.get("home"), game.get("away"), str(game.get("date"))[:10]))
        if row:
            game.setdefault("fixture_id", row.get("fixture_id"))
            game.setdefault("home_id", row.get("home_id"))
            game.setdefault("away_id", row.get("away_id"))


def _schedule(payload: dict, team_name: str) -> dict | None:
    fixtures = []
    for game in payload.get("games") or []:
        if game.get("result") is not None or team_name not in (game.get("home"), game.get("away")):
            continue
        is_home = game.get("home") == team_name
        win = _finite(game.get("pH" if is_home else "pA"))
        draw = _finite(game.get("pD"))
        if win is None or draw is None:
            continue
        expected_points = 3 * win + draw
        fixtures.append({
            "fixture_id": game.get("fixture_id"),
            "date": game.get("date"),
            "opponent": game.get("away") if is_home else game.get("home"),
            "venue": "home" if is_home else "away",
            "win_pct": round(win * 100, 1),
            "expected_points": round(expected_points, 2),
            "difficulty": round(3 - expected_points, 2),
            "evidence_ids": ([f"fixture:{game.get('fixture_id')}"]
                             if game.get("fixture_id") else []),
        })
    if not fixtures:
        return None
    fixtures.sort(key=lambda row: row["date"])
    hardest = sorted(fixtures, key=lambda row: -row["difficulty"])[:3]
    easiest = sorted(fixtures, key=lambda row: row["difficulty"])[:3]
    return {
        "remaining_count": len(fixtures),
        "average_expected_points": round(sum(row["expected_points"] for row in fixtures) / len(fixtures), 2),
        "hardest_run": hardest,
        "easiest_run": easiest,
        "fixtures": fixtures,
        "coverage": {"rest": False, "travel": False, "congestion": True,
                     "strength_basis": "model-implied fixture probabilities"},
    }


def _consensus(payload: dict, team_name: str) -> dict | None:
    rows = []
    for game in payload.get("games") or []:
        if game.get("result") is not None or team_name not in (game.get("home"), game.get("away")):
            continue
        if not all(_finite(game.get(key)) is not None
                   for key in ("mkt_home", "mkt_draw", "mkt_away")):
            continue
        side = "home" if game.get("home") == team_name else "away"
        model = float(game["pH" if side == "home" else "pA"]) * 100
        market = float(game["mkt_home" if side == "home" else "mkt_away"]) * 100
        rows.append({
            "fixture_id": game.get("fixture_id"),
            "date": game.get("date"),
            "opponent": game.get("away") if side == "home" else game.get("home"),
            "model_pct": round(model, 1),
            "consensus_pct": round(market, 1),
            "gap_pp": round(model - market, 1),
            "normalization": "no-vig three-way probabilities",
            "language": "more optimistic than consensus" if model > market
                        else "more pessimistic than consensus",
        })
    return {"comparisons": rows, "login_only": True, "quiet_middle": True} if rows else None


def _confidence(payload: dict, snapshot: dict, team_events: list[dict],
                top_leverage: dict | None, trajectory: list[dict]) -> dict:
    generated = _iso_date(snapshot.get("generated"))
    age = ((dt.datetime.now(dt.timezone.utc).date() - generated).days
           if generated else None)
    freshness = "current" if age is not None and age <= 2 else "stale"
    health = payload.get("health") or {}
    features = health.get("features") if isinstance(health, dict) else {}
    coverage_values = []
    feature_values = features.values() if isinstance(features, dict) else features or []
    for value in feature_values:
        if isinstance(value, dict):
            pct = _finite(value.get("completeness") or value.get("complete_pct"))
            if pct is not None:
                coverage_values.append(pct)
    coverage = (round(sum(coverage_values) / len(coverage_values), 1)
                if coverage_values else None)
    fragility = top_leverage.get("leverage_pp") if top_leverage else 0
    recent_moves = [abs(event.get("delta_pp") or 0) for event in team_events[:5]]
    return {
        "freshness": {"status": freshness, "age_days": age,
                      "generated": snapshot.get("generated")},
        "source_coverage": {"status": "measured" if coverage is not None else "unavailable",
                            "complete_pct": coverage},
        "historical_calibration": {
            "status": "available" if payload.get("outcome_skill") else "unavailable",
            "evidence": payload.get("outcome_skill"),
        },
        "projection_stability": {
            "status": "stable" if max(recent_moves or [0]) < 5 else "moving",
            "recent_max_move_pp": max(recent_moves or [0]),
            "trajectory_points": len(trajectory),
        },
        "season_progress": {"pct_complete": (payload.get("league") or {}).get("pct_complete")},
        "scenario_fragility": {
            "status": "high" if fragility >= 15 else "medium" if fragility >= 5 else "low",
            "top_fixture_range_pp": fragility,
        },
    }


def _race_context(snapshot: dict, team_id: str, target: str,
                  leverage_rows: list[dict]) -> dict:
    subject = next(team for team in snapshot["teams"] if team["team_id"] == team_id)
    subject_value = _finite(subject["published"].get(target)) or 0
    rivals = []
    for team in snapshot["teams"]:
        if team["team_id"] == team_id:
            continue
        value = _finite(team["published"].get(target))
        if value is None:
            continue
        direct = [fixture for fixture in snapshot.get("fixtures") or []
                  if {fixture["home_id"], fixture["away_id"]} == {team_id, team["team_id"]}]
        dependencies = [row for row in leverage_rows
                        if not row["is_own_fixture"]
                        and team["team_id"] in (row["home_id"], row["away_id"])]
        rivals.append({
            "team_id": team["team_id"],
            "team": team["team"],
            "target_pct": value,
            "gap_pp": round(value - subject_value, 1),
            "proj_pts": team["published"].get("proj_pts"),
            "proj_rank": team["published"].get("proj_rank"),
            "inclusion_reason": "nearest target-probability competitor",
            "head_to_heads": direct,
            "largest_dependency": dependencies[0] if dependencies else None,
        })
    rivals.sort(key=lambda row: abs(row["gap_pp"]))
    return {"target_metric": target, "team_pct": subject_value,
            "rivals": rivals[:5], "recommended_rival_id": rivals[0]["team_id"] if rivals else None}


def _thesis(team: dict, target: str, expectation: dict | None,
            schedule: dict | None, confidence: dict, events: list[dict],
            snapshot: dict) -> dict:
    published = team["published"]
    target_value = _finite(published.get(target))
    elo = _finite(team.get("elo"))
    elos = [float(row["elo"]) for row in snapshot["teams"] if _finite(row.get("elo")) is not None]
    elo_rank = (1 + sum(value > elo for value in elos)) if elo is not None else None
    evidence = [f"snapshot:{snapshot['snapshot_id']}"]
    if events:
        evidence.append(f"event:{events[0]['event_id']}")
    claims = [{
        "kind": "season_expectation",
        "text": f"The model puts {TARGET_LABELS.get(target, target)} at {target_value:.1f}%."
                if target_value is not None else "No supported season target is available.",
        "evidence_ids": evidence,
    }]
    if elo_rank is not None:
        claims.append({
            "kind": "primary_strength",
            "text": f"Current model strength ranks {elo_rank} of {len(elos)} teams in this competition.",
            "evidence_ids": [f"snapshot:{snapshot['snapshot_id']}"],
        })
    if expectation:
        claims.append({
            "kind": "sustainability",
            "text": expectation["wording"],
            "evidence_ids": expectation["season"]["receipt_ids"],
        })
    if schedule:
        claims.append({
            "kind": "unresolved_uncertainty",
            "text": f"{schedule['remaining_count']} scheduled matches remain; the hardest modeled fixture is "
                    f"against {schedule['hardest_run'][0]['opponent']}.",
            "evidence_ids": schedule["hardest_run"][0]["evidence_ids"],
        })
    raw = json.dumps({"team": team["team_id"], "target": target, "claims": claims,
                      "confidence": confidence}, sort_keys=True, separators=(",", ":"))
    thesis_id = f"thesis:v1:{hashlib.sha1(raw.encode()).hexdigest()[:16]}"
    return {
        "thesis_id": thesis_id,
        "schema_version": 1,
        "effective_at": snapshot["generated"],
        "target_metric": target,
        "claims": claims,
        "confidence_state": confidence,
        "previous_version": None,
        "change_reason": "initial compiled thesis",
    }


def _watchpoints(leverage_rows: list[dict], target: str,
                 threshold_pp: float = 5.0) -> list[dict]:
    rows = []
    for leverage in leverage_rows:
        baseline = leverage["baseline_pct"]
        best_outcome = max(leverage["conditional_pct"],
                           key=lambda key: abs(leverage["conditional_pct"][key] - baseline))
        value = leverage["conditional_pct"][best_outcome]
        move = round(value - baseline, 1)
        if abs(move) < threshold_pp:
            continue
        probability = {"H": 0, "D": 0, "A": 0}
        rows.append({
            "watchpoint_id": f"watch:{leverage['fixture_id']}:{best_outcome}:{target}",
            "fixture_id": leverage["fixture_id"],
            "date": leverage["date"],
            "condition": {"outcome": best_outcome},
            "summary": f"If {leverage['home']} vs {leverage['away']} ends {best_outcome}, "
                       f"{TARGET_LABELS.get(target, target)} moves to about {value:.1f}%.",
            "baseline_pct": baseline,
            "conditional_pct": value,
            "move_pp": move,
            "scenario": {"assumptions": {leverage["fixture_id"]: best_outcome}},
            "expires_at": leverage["date"],
            "evidence_ids": leverage["evidence_ids"],
            "plausibility": probability,
        })
    rows.sort(key=lambda row: (row["date"], -abs(row["move_pp"])))
    return rows[:3]


def _paths(watchpoints: list[dict], target: str) -> list[dict]:
    paths = []
    labels = ("shortest", "most_probable", "rival_dependent")
    for index, watchpoint in enumerate(watchpoints[:3]):
        paths.append({
            "kind": labels[index],
            "target_metric": target,
            "assumptions": watchpoint["scenario"]["assumptions"],
            "approx_joint_likelihood": None,
            "resulting_pct": watchpoint["conditional_pct"],
            "snapshot_language": "conditional estimate from the current archived snapshot",
            "evidence_ids": watchpoint["evidence_ids"],
        })
    return paths


def _critical_dates(leverage_rows: list[dict], schedule: dict | None) -> list[dict]:
    entries = []
    for row in leverage_rows[:5]:
        entries.append({
            "date": row["date"], "type": "high_leverage_fixture",
            "label": f"{row['home']} vs {row['away']}",
            "leverage_pp": row["leverage_pp"],
            "fixture_id": row["fixture_id"],
            "tentative": row.get("ko") is None,
            "evidence_ids": row["evidence_ids"],
        })
    if schedule:
        dates = [_iso_date(row["date"]) for row in schedule["fixtures"]]
        for index in range(max(0, len(dates) - 2)):
            if dates[index] and dates[index + 2] and (dates[index + 2] - dates[index]).days <= 8:
                entries.append({
                    "date": dates[index].isoformat(), "type": "congested_run",
                    "label": "Three matches in eight days",
                    "tentative": False,
                    "evidence_ids": [evidence for row in schedule["fixtures"][index:index + 3]
                                     for evidence in row["evidence_ids"]],
                })
    return sorted(entries, key=lambda row: row["date"])


def _analogs(trajectory: list[dict], current_season: str) -> dict | None:
    prior = [row for row in trajectory
             if row.get("season_id") and row["season_id"] != current_season]
    seasons = sorted({row["season_id"] for row in prior})
    if not seasons:
        return None
    return {
        "method": "same-club checkpoint distance over projected points and target probability",
        "sample_size": len(seasons),
        "club_baselines": [{"season_id": season,
                            "checkpoint_count": sum(row["season_id"] == season for row in prior)}
                           for season in seasons],
        "similar_teams": [],
        "coverage_note": "Cross-club analogs require compatible archived checkpoints.",
        "future_leakage_guard": True,
    }


def build_team_record(payload: dict, snapshot: dict, team: dict, target: str,
                      leverage_rows: list[dict], baseline: dict,
                      history: pd.DataFrame, match_history: pd.DataFrame,
                      events: pd.DataFrame, mode: dict) -> dict:
    league_id, team_id, team_name = snapshot["league_id"], team["team_id"], team["team"]
    team_events = _event_rows(events, league_id, team_id)
    trajectory = _trajectory_rows(history, league_id, team_id, team_name)
    receipts = _receipts(payload, match_history, league_id, team_id, team_name)
    expectation = _expectation(receipts, team_name)
    schedule = _schedule(payload, team_name)
    consensus = _consensus(payload, team_name)
    top_leverage = leverage_rows[0] if leverage_rows else None
    confidence = _confidence(payload, snapshot, team_events, top_leverage, trajectory)
    race = _race_context(snapshot, team_id, target, leverage_rows)
    thesis = _thesis(team, target, expectation, schedule, confidence, team_events, snapshot)
    watchpoints = _watchpoints(leverage_rows, target)
    paths = _paths(watchpoints, target)
    analogs = _analogs(trajectory, str(snapshot["season"]))
    current_pct = _finite(team["published"].get(target))
    seven_day = next((event["delta_pp"] for event in team_events
                      if event["target_metric"] == target), None)
    why_events = [event for event in team_events if event["evidence_ids"]]
    turning = [event for event in team_events
               if event["cause_class"] == "result"
               and event["event_type"] not in {"model_change", "data_health"}]
    turning.sort(key=lambda event: -abs(event.get("delta_pp") or 0))
    summary = (
        f"{TARGET_LABELS.get(target, target).capitalize()} is {current_pct:.1f}%"
        + (f", {seven_day:+.1f} points since the prior material event." if seven_day is not None else ".")
        if current_pct is not None else
        "No supported current target is available."
    )
    brief_data = {
        "calendar_mode": mode,
        "target_metric": target,
        "target_label": TARGET_LABELS.get(target, target),
        "current_pct": current_pct,
        "seven_day_change_pp": seven_day,
        "projected_points": team["published"].get("proj_pts"),
        "projected_rank": team["published"].get("proj_rank"),
        "summary": summary,
        "largest_driver": why_events[0] if why_events else None,
        "next_high_impact_fixture": top_leverage,
        "snapshot_id": snapshot["snapshot_id"],
        "generated": snapshot["generated"],
    }
    if mode["mode"] != "active_matchweek":
        brief_data["quiet_lead"] = {
            "thesis": thesis,
            "unresolved_question": thesis["claims"][-1] if thesis["claims"] else None,
            "next_evidence": watchpoints[0] if watchpoints else None,
        }
    features = {
        "1": feature(1, "live", brief_data),
        "2": feature(2, "live" if team_events else "thin_history", {
            "events": team_events, "initial_window_days": 7,
            "quiet_state": None if team_events else {"thesis_id": thesis["thesis_id"],
                                                     "watchpoints": watchpoints},
        }, None if team_events else "No material archived event is available yet."),
        "3": feature(3, "live" if why_events else "unavailable", {
            "events": [{
                **event,
                "attribution": [{
                    "kind": "observed_window",
                    "delta_pp": event["delta_pp"],
                    "evidence_ids": event["evidence_ids"],
                }],
                "residual_pp": 0,
            } for event in why_events],
        }, None if why_events else "No evidence-linked forecast movement is available."),
        "4": feature(4, "live" if leverage_rows else "unavailable", {
            "target_metric": target, "fixtures": leverage_rows,
            "method": "forced H/D/A common-random Monte Carlo range",
        }, None if leverage_rows else "No scheduled fixture has supported probabilities."),
        "5": feature(5, "live" if snapshot.get("fixtures") else "unavailable", {
            "snapshot_id": snapshot["snapshot_id"], "simulation_version": snapshot["simulation_version"],
            "seed": snapshot["replay_seed"], "n": min(snapshot["n_sims"], 5000),
            "baseline": baseline, "fixtures": snapshot.get("fixtures") or [],
            "url_schema_version": 1, "outcomes": ["H", "D", "A"],
        }, None if snapshot.get("fixtures") else "No remaining fixture can be forced."),
        "6": feature(6, "live" if paths else "unavailable", {
            "target_metric": target, "paths": paths, "search": "bounded leverage beam",
        }, None if paths else "No plausible near-term path crosses the configured movement threshold."),
        "7": feature(7, "live", {
            "candidates": [event for event in team_events
                           if event["event_type"] in {"threshold_crossing", "result", "forecast_move"}
                           and event["cause_class"] != "refresh"],
            "default_cap": "one non-urgent alert per team per 24 hours",
            "send_state": "controlled_by_private_send_ledger",
        }),
        "8": feature(8, "live", {
            "calendar_mode": mode["mode"], "cadence": mode["cadence"],
            "sections": {"team_pulse": brief_data, "what_changed": team_events[:3],
                         "match_to_watch": top_leverage, "receipt": receipts[0] if receipts else None,
                         "scenario_prompt": watchpoints[0] if watchpoints else None},
            "skip_when_empty": True,
        }),
        "9": feature(9, "live" if race["rivals"] else "unavailable", race,
                     None if race["rivals"] else "No compatible rival has a supported target probability."),
        "10": feature(10, "live" if expectation else "thin_history", expectation,
                      None if expectation else "No frozen pre-kickoff receipts have accrued for this team."),
        "11": feature(11, "live" if trajectory else "thin_history", {
            "seasons": sorted({row["season_id"] for row in trajectory if row["season_id"]}),
            "points": trajectory, "annotations": team_events,
            "full_resolution": True, "entitlement_gated": True,
        }, None if trajectory else "No archived forecast trajectory has accrued."),
        "12": feature(12, "live" if consensus else "unavailable", consensus,
                      None if consensus else "No current multi-source consensus is available."),
        "13": feature(13, "live" if schedule else "unavailable", schedule,
                      None if schedule else "No remaining modeled schedule is published."),
        "14": feature(14, "live" if leverage_rows else "unavailable", {
            "timezone_basis": "user preference at delivery time",
            "entries": _critical_dates(leverage_rows, schedule),
        }, None if leverage_rows else "No fixture-derived critical dates are available."),
        "15": feature(15, "live", confidence),
        "16": feature(16, "live", {
            "intents": ["current_state", "why_changed", "scenario", "next_high_impact_match",
                        "rival_importance", "path_to_target", "schedule_difficulty",
                        "historical_comparison", "receipt_lookup"],
            "calculation_source": "corresponding feature records",
            "raw_question_analytics": False,
        }),
        "17": feature(17, "live" if turning else "thin_history", {
            "target_metric": target, "events": turning,
        }, None if turning else "No result-driven turning point has accrued."),
        "18": feature(18, "live" if receipts else "thin_history", {
            "receipts": receipts, "cutoff_rule": "latest archived forecast strictly before kickoff date",
            "immutable": True,
        }, None if receipts else "No immutable pre-kickoff receipt can yet be joined to a result."),
        "19": feature(19, "live" if race["rivals"] else "unavailable", {
            "recommended_rival_id": race["recommended_rival_id"],
            "available_rivals": race["rivals"],
            "target_metric": target,
            "snapshot_id": snapshot["snapshot_id"],
        }, None if race["rivals"] else "No compatible rival comparison is available."),
        "20": feature(20, "live" if (why_events or leverage_rows or receipts) else "unavailable", {
            "approved_templates": ["material_move", "highest_leverage", "turning_point",
                                   "race_comparison", "receipt"],
            "eligible_event_ids": [event["event_id"] for event in why_events if event["public_safe"]],
            "verification_required": True,
        }, None if (why_events or leverage_rows or receipts) else "No public-safe card evidence is available."),
        "21": feature(21, "live", {
            "export_formats": ["csv", "json", "png"],
            "workspace_filters": ["team", "metric", "date_range", "comparison", "template"],
            "provenance": {"snapshot_id": snapshot["snapshot_id"],
                           "generated": snapshot["generated"],
                           "methodology_url": "/methodology"},
            "creator_entitlement_required": True,
        }),
        "22": feature(22, "live", thesis),
        "23": feature(23, "live" if watchpoints else "unavailable", {
            "target_metric": target, "watchpoints": watchpoints,
            "threshold_pp": 5, "snapshot_id": snapshot["snapshot_id"],
        }, None if watchpoints else "No plausible near-term result moves the target by five points."),
        "24": feature(24, "live" if analogs else "thin_history", analogs,
                      None if analogs else "Comparable prior-season checkpoints have not accrued."),
        "25": feature(25, "live", {
            "calendar_mode": mode,
            "composition": {"team_thesis": thesis, "expectation": expectation,
                            "unresolved_question": thesis["claims"][-1] if thesis["claims"] else None,
                            "schedule": schedule, "rival_context": race,
                            "watchpoints": watchpoints},
            "offseason_ledger_categories": ["observed_development", "model_input_changed",
                                            "forecast_impact_calculated"],
        }),
        "26": feature(26, "live", {
            "checkpoint_policy": ["preseason", "monthly_optional"],
            "fields": ["predicted_finish", "target_probability", "confidence", "private_notes"],
            "versioned": True, "private_by_default": True,
            "scoring_minimum": 5, "server_persistence_required": True,
        }),
    }
    assert set(features) == {str(index) for index in FEATURES}
    return {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": "team_intelligence",
        "league_id": league_id,
        "league_name": snapshot["league_name"],
        "season_id": str(snapshot["season"]),
        "team_id": team_id,
        "team": team_name,
        "target_metric": target,
        "snapshot_id": snapshot["snapshot_id"],
        "generated": snapshot["generated"],
        "calendar_mode": mode,
        "feature_count": len(features),
        "features": features,
    }


def build_league(payload: dict, snapshot: dict, history: pd.DataFrame,
                 match_history: pd.DataFrame, events: pd.DataFrame,
                 today: dt.date | None = None, leverage_n: int = 400) -> list[dict]:
    _hydrate_fixture_ids(payload, snapshot)
    targets = {team["team_id"]: _target_for_team(team, snapshot)
               for team in snapshot["teams"]}
    targets = {team_id: target for team_id, target in targets.items() if target}
    if not targets:
        return []
    baseline, leverage = fixture_leverage(snapshot, targets, n=leverage_n)
    mode = calendar_mode(payload, today=today)
    return [
        build_team_record(payload, snapshot, team, targets[team["team_id"]],
                          leverage.get(team["team_id"], [])[:12],
                          baseline[team["team_id"]], history, match_history, events, mode)
        for team in snapshot["teams"] if team["team_id"] in targets
    ]


def load_frame(path: Path) -> pd.DataFrame:
    return pd.read_parquet(path) if path.exists() else pd.DataFrame()


def write_records(records: list[dict], output_root: Path = PRIVATE_ROOT) -> list[Path]:
    paths = []
    for record in records:
        league_dir = output_root / record["league_id"]
        league_dir.mkdir(parents=True, exist_ok=True)
        path = league_dir / f"{record['team_id'].replace(':', '_')}.json"
        path.write_text(json.dumps(record, separators=(",", ":"), allow_nan=False))
        paths.append(path)
    return paths


def build_all(output_root: Path = PRIVATE_ROOT, leverage_n: int = 400) -> dict:
    from scripts.archive_intelligence_state import build_snapshot

    history = load_frame(ODDS_HISTORY)
    match_history = load_frame(MATCH_HISTORY)
    events = load_frame(EVENT_HISTORY)
    manifest = {
        "schema_version": 1,
        "generated": dt.datetime.now(dt.timezone.utc).isoformat(),
        "leagues": {},
        "feature_count": len(FEATURES),
    }
    for payload_path in sorted(LEAGUE_DATA.glob("*.js")):
        payload = read_js_payload(payload_path)
        if not isinstance(payload, dict) or not payload.get("standings") or not payload.get("sim"):
            continue
        league_id = (payload.get("league") or {}).get("id") or payload_path.stem
        if payload.get("data_status") in {"results_only", "historical"} or payload.get("season") is None:
            continue
        try:
            snapshot = build_snapshot(payload, league_id=league_id)
            records = build_league(payload, snapshot, history, match_history, events,
                                   leverage_n=leverage_n)
        except Exception as exc:
            manifest["leagues"][league_id] = {
                "status": "failed", "reason": str(exc), "team_count": 0}
            continue
        paths = write_records(records, output_root)
        status_counts = Counter(
            value["status"] for record in records
            for value in record["features"].values())
        manifest["leagues"][league_id] = {
            "status": "ok", "team_count": len(records),
            "snapshot_id": snapshot["snapshot_id"],
            "calendar_mode": calendar_mode(payload)["mode"],
            "feature_states": dict(status_counts),
            "files": [path.name for path in paths],
        }
    output_root.mkdir(parents=True, exist_ok=True)
    (output_root / "manifest.json").write_text(
        json.dumps(manifest, separators=(",", ":"), allow_nan=False))
    return manifest
