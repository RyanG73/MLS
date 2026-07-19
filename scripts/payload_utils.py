#!/usr/bin/env python3
"""Shared payload writing and health utilities for dashboard build scripts.

Two primitives that enforce the data contract across all builders:

  write_js_payload  — serialises to JS with allow_nan=False; raises rather than
                      writing a payload that contains NaN / Infinity.

  health_feature_stats — computes complete_pct / nondefault_pct for a feature
                         family but returns None for both when the row slice is
                         empty (preseason), preventing the NaN that json.dumps
                         would otherwise emit.

  registry_ids — every league id in webapp/leagues.js. Per-league lazy-loaded
                extras (news/<lid>.js, drift-traj/<lid>.js, ...) should write a
                file for every registry id, not just leagues with real data —
                an empty file beats a 404 in the console for 'soon' leagues
                (found 2026-07-09 for news, recurred 2026-07-10 for drift-traj).
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path
from typing import TYPE_CHECKING

# pandas is only needed by health_feature_stats; keeping the import lazy lets
# stdlib-only consumers (build_static_pages.py in the deploy workflow, which
# runs on bare python3 with no pip install) import this module.
if TYPE_CHECKING:
    import pandas as pd

FIXTURE_ID_VERSION = "v1"


def make_fixture_id(league_id: str, season: int | str, date: str,
                     home_id: str, away_id: str) -> str:
    """Deterministic fixture identifier, stable across rebuilds.

    docs/intelligence-hub-implementation-instructions.md §4.3: "deterministic
    identifier based on source ID where available; otherwise a versioned hash
    of competition, season, kickoff, home team ID, and away team ID." No
    upstream source (e.g. an ESPN event ID) is currently captured by any
    builder, so this always uses the hash form.

    Deliberately independent of the client-side simulator's array-index `id`
    field on game cards (see the "SIM PORTING CONTRACT" comment in
    scripts/build_dashboard_data.py and webapp/index.html) — that field is a
    position in that build's remaining-fixtures array and must never be
    repurposed as a stable identifier.

    Prefixed with FIXTURE_ID_VERSION so a future change to this formula is
    visibly distinguishable from old IDs rather than silently colliding.
    """
    raw = f"{league_id}|{season}|{date}|{home_id}|{away_id}"
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]
    return f"{FIXTURE_ID_VERSION}:{digest}"


def read_js_payload(path: Path | str) -> dict | list | None:
    """Parse a ``window.<VAR> = <json>;`` data file back into Python.

    The inverse of :func:`write_js_payload`, and the single source of truth
    for reading payload JS from Python (build_share_cards, build_static_pages,
    validate_payloads all consume this shape). Returns None when the file is
    missing, has no assignment wrapper, or the body isn't strict JSON — the
    callers all treat "unreadable" and "absent" the same way.
    """
    p = Path(path)
    if not p.exists():
        return None
    m = re.match(r"window\.\w+\s*=\s*(.*?);?\s*$",
                 p.read_text(encoding="utf-8"), re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError:
        return None


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


def registry_ids(registry_path: Path | str = "webapp/leagues.js") -> set[str]:
    """Every league id in webapp/leagues.js. Missing/unparseable file → {}."""
    try:
        txt = Path(registry_path).read_text()
        return {league["id"] for league in
                json.loads(txt[txt.index("=") + 1:].rstrip().rstrip(";"))}
    except Exception:
        return set()
