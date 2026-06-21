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
