#!/usr/bin/env python3
"""Shared payload writing and health utilities for dashboard build scripts.

Two primitives that enforce the data contract across all builders:

  write_js_payload  — serialises to JS with allow_nan=False; raises rather than
                      writing a payload that contains NaN / Infinity.

  health_feature_stats — computes complete_pct / nondefault_pct for a feature
                         family but returns None for both when the row slice is
                         empty (preseason), preventing the NaN that json.dumps
                         would otherwise emit.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import pandas as pd


def write_js_payload(path: Path, var_name: str, data: dict) -> None:
    """Write ``window.<var_name> = <json>;`` enforcing finite values only.

    Raises ValueError (and does NOT write the file) if any non-finite float
    (NaN, Infinity, -Infinity) is present in *data*.  This is a hard gate:
    a partial or invalid payload is worse than a missing one.
    """
    try:
        js = json.dumps(data, separators=(",", ":"), allow_nan=False)
    except ValueError as exc:
        raise ValueError(
            f"Non-finite value in payload for {path}: {exc}"
        ) from exc
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"window.{var_name} = {js};\n")


def health_feature_stats(rows: pd.DataFrame, cols: list[str]) -> dict:
    """Return health stats for one feature family, safe when *rows* is empty.

    When the current-season row slice is empty (e.g. preseason, no matches
    played yet), pandas .mean() returns NaN.  We return None instead so the
    payload writer can serialise null rather than NaN, which is valid JSON.

    Returns a dict ready to be spread into the per-family health entry::

        {"complete_pct": <float|None>, "nondefault_pct": <float|None>,
         "status": "ok"|"no_rows"}
    """
    if rows.empty or not cols:
        return {"complete_pct": None, "nondefault_pct": None, "status": "no_rows"}
    subset = rows[cols]
    return {
        "complete_pct": round(float(subset.notna().mean().mean() * 100), 1),
        "nondefault_pct": round(float((subset != 0).mean().mean() * 100), 1),
        "status": "ok",
    }


def outcome_skill_block(league_id: str) -> dict | None:
    """Per-league outcome-skill summary for the Health tab (U1, 2026-07-07).

    Reads `experiments/season-outcomes-baseline.report.json` (the season-outcome
    replay baseline) and returns
        {checkpoint: {outcome: {brier, skill, p_on_achievers}}}
    where skill = 1 − brier / (obs·(1−obs)) — 0 means no better than always
    quoting the base rate, negative means worse. None when the league isn't in
    the baseline (e.g. liga-mx) or the report is missing: the UI renders the
    honest empty state, mirroring the B4 `trust` convention.
    """
    rep_path = Path(__file__).parent.parent / "experiments" / "season-outcomes-baseline.report.json"
    try:
        rep = json.loads(rep_path.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return None
    league = rep.get("per_league", {}).get(league_id)
    if not league:
        return None
    out: dict = {}
    for cp, outcomes in league.items():
        row = {}
        for k, m in outcomes.items():
            p = m.get("obs_rate") or 0.0
            clim = p * (1.0 - p)
            skill = (1.0 - m["brier"] / clim) if clim > 1e-9 else None
            row[k] = {"brier": round(m["brier"], 3),
                      "skill": round(skill, 2) if skill is not None else None,
                      "p_hit": m.get("p_actual_mean")}
        out[cp] = row
    return out
