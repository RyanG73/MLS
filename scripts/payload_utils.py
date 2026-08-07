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
import os
import re
from pathlib import Path
from typing import TYPE_CHECKING

# pandas is only needed by health_feature_stats; keeping the import lazy lets
# stdlib-only consumers (build_static_pages.py in the deploy workflow, which
# runs on bare python3 with no pip install) import this module.
if TYPE_CHECKING:
    import pandas as pd

FIXTURE_ID_VERSION = "v1"
TEAM_ID_VERSION = "v1"


def canonical_team_id(display_name: str, source_id: str | None = None) -> str:
    """Return a stable, versioned club identifier.

    Source identifiers remain authoritative when a builder has one (MLS uses
    ASA IDs). Other builders currently expose names only, so their fallback
    ID is deliberately league-independent: exact canonical names survive
    promotion/relegation and competition changes. Alias/name-change mapping
    belongs upstream; changing that mapping never changes this hash contract
    for already archived records.
    """
    if source_id is not None and str(source_id).strip():
        return str(source_id).strip()
    canonical = " ".join(str(display_name).strip().casefold().split())
    digest = hashlib.sha1(canonical.encode("utf-8")).hexdigest()[:16]
    return f"{TEAM_ID_VERSION}:{digest}"


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


SNAPSHOT_ID_VERSION = "v1"


def make_snapshot_id(league_id: str, season: int | str, generated: str,
                      config_id: str, simulation_version: str) -> str:
    """Deterministic snapshot identifier (docs/intelligence-hub-implementation-instructions.md
    §4.3): league, season, generated timestamp, configuration ID, and
    simulation version — hashed and versioned the same way as make_fixture_id,
    but as its own independent version counter (bumping the fixture_id formula
    should not silently imply bumping the snapshot_id formula, or vice versa).
    """
    raw = f"{league_id}|{season}|{generated}|{config_id}|{simulation_version}"
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]
    return f"{SNAPSHOT_ID_VERSION}:{digest}"


EVENT_ID_VERSION = "v1"


def make_event_id(event_type: str, team_id, target_metric, effective_at: str,
                   evidence_ids: list[str]) -> str:
    """Stable event identifier (docs/intelligence-hub-implementation-instructions.md
    §4.3): a hash of event type, team, target metric, effective time, and
    evidence references, so the same underlying change is never archived
    twice even if this build reruns. `team_id`/`target_metric` may be None
    (league-scoped events like model_change/data_health carry no team).
    `evidence_ids` is sorted before hashing so evidence order never affects
    identity."""
    raw = f"{event_type}|{team_id}|{target_metric}|{effective_at}|{','.join(sorted(evidence_ids))}"
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]
    return f"{EVENT_ID_VERSION}:{digest}"


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


class PayloadRegression(ValueError):
    """A write would replace a payload with an older or unrelated season."""


# Fraction of the previous team set that may disappear in one write. Promotion
# and relegation move 2-4 clubs in an 18-24 team league, so a legitimate season
# rollover churns ~10-30%. 0.6 is far above anything real and far below the
# 100% that a wrong-league write produces.
_MAX_TEAM_CHURN = 0.6
_ALLOW_REGRESSION_ENV = "ENTENSER_ALLOW_PAYLOAD_REGRESSION"


def _assert_not_a_regression(path: Path, data: dict) -> None:
    """Refuse a league payload that goes backwards in season or swaps its field.

    Why this is a hard gate rather than a warning (2026-08-07): every upstream
    fetch failure in this pipeline is silent. `build_league_data` catches its
    own network errors, falls back to whatever history it can assemble — which
    is the last COMPLETED season — writes a payload with a fresh `generated`
    timestamp, and exits 0. Nothing downstream can tell.

    Observed that morning: a local refresh ran while every 2026 source returned
    404/403 and **38 payloads regressed to the prior season at once**. The
    Spanish second tier came back holding ten Scottish clubs, and `power.js`
    was then rebuilt from the corrupted set, so the published global ladder was
    wrong too. The only reason it was caught is that someone happened to read
    `segunda.js` by hand.

    Set ENTENSER_ALLOW_PAYLOAD_REGRESSION=1 for a deliberate re-baseline.
    """
    if os.environ.get(_ALLOW_REGRESSION_ENV):
        return
    if not isinstance(data, dict) or not data.get("standings"):
        return
    old = read_js_payload(path)
    if not isinstance(old, dict) or not old.get("standings"):
        return                                  # first write, or unreadable

    lid = (data.get("league") or {}).get("id") or path.stem
    old_season, new_season = old.get("season"), data.get("season")
    if (isinstance(old_season, int) and isinstance(new_season, int)
            and new_season < old_season):
        raise PayloadRegression(
            f"{lid}: refusing to write season {new_season} over {old_season}. "
            f"This is what a failed upstream fetch looks like — the builder "
            f"falls back to the last completed season and reports success. "
            f"Check the fetch log before retrying; set {_ALLOW_REGRESSION_ENV}=1 "
            f"only if the rollback is intended.")

    old_teams = {r.get("team") for r in old["standings"] if r.get("team")}
    new_teams = {r.get("team") for r in data["standings"] if r.get("team")}
    if old_teams:
        churn = len(old_teams - new_teams) / len(old_teams)
        if churn > _MAX_TEAM_CHURN:
            gone = sorted(old_teams - new_teams)[:4]
            arrived = sorted(new_teams - old_teams)[:4]
            raise PayloadRegression(
                f"{lid}: refusing to write — {churn:.0%} of the field changed in "
                f"one build (limit {_MAX_TEAM_CHURN:.0%}). Promotion and "
                f"relegation cannot do that; a wrong-league or wrong-season "
                f"fetch can. Leaving: {gone}… Arriving: {arrived}… "
                f"Set {_ALLOW_REGRESSION_ENV}=1 if this really is intended.")


def write_js_payload(path: Path, var_name: str, data: dict) -> None:
    """Write ``window.<var_name> = <json>;`` enforcing finite values only.

    Raises ValueError (and does NOT write the file) if any non-finite float
    (NaN, Infinity, -Infinity) is present in *data*.  This is a hard gate:
    a partial or invalid payload is worse than a missing one.

    Also refuses a league payload that regresses to an older season or swaps
    out its field wholesale — see _assert_not_a_regression.
    """
    try:
        js = json.dumps(data, separators=(",", ":"), allow_nan=False)
    except ValueError as exc:
        raise ValueError(
            f"Non-finite value in payload for {path}: {exc}"
        ) from exc
    path = Path(path)
    _assert_not_a_regression(path, data)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"window.{var_name} = {js};\n")


def apply_global_elo_scale(data: dict, league_id: str) -> dict:
    """Publish shared-scale ELO alongside the raw domestic model rating.

    League simulations intentionally continue to consume ``standings[].elo``:
    adding one constant to every club in a league cannot change a domestic
    strength difference. Public comparison surfaces consume ``global_elo``
    instead, while ``elo_scale.offset`` lets the browser translate the compact
    historical series without duplicating it in every payload.
    """
    from data_pipeline import coefficients as co  # lazy: keep stdlib-only imports cheap

    offset = float(co.global_elo_offset(league_id))
    # Lower divisions also get their SPREAD translated, not just their level:
    # a second tier's rating gaps overstate the favourite relative to its parent
    # league's, so carrying a club's deviation across the boundary unchanged
    # imports the exaggeration (see coefficients.tier_dispersion). 1.0 for every
    # top flight, which is all but seven leagues, so this is a no-op for them.
    disp = float(co.tier_dispersion(league_id))
    ratings = [float(r["elo"]) for r in (data.get("standings") or [])
               if isinstance(r.get("elo"), (int, float)) and math.isfinite(float(r["elo"]))]
    # Pivot on the league's own mean: compressing about the mean leaves the
    # league's overall position exactly where the fitted tier shift put it and
    # only narrows the spread around it.
    pivot = (sum(ratings) / len(ratings)) if ratings else 0.0

    for row in data.get("standings") or []:
        value = row.get("elo")
        if isinstance(value, (int, float)) and math.isfinite(float(value)):
            scaled = pivot + disp * (float(value) - pivot) if disp != 1.0 else float(value)
            # A club that has played in Europe is additionally judged on its own
            # record there. The league offset is anchored on a COUNTRY
            # coefficient, which measures how deep an association is rather than
            # how good any one of its clubs is — so it under-rates the elite of
            # a top-heavy league and over-rates the elite of a deep one. Zero
            # for a club with no continental history, which is most of them.
            adj = co.club_continental_offset(league_id, row.get("team") or "")
            if adj:
                row["global_elo_adj"] = round(adj, 1)
            else:
                row.pop("global_elo_adj", None)
            row["global_elo"] = int(round(scaled + offset + adj))
    data["elo_scale"] = {
        "anchor": "EPL = 0",
        "base_field": "elo",
        "rating_field": "global_elo",
        "offset": round(offset, 3),
        # dispersion/pivot let the browser translate the compact historical
        # series the same way. Both are inert at 1.0/0.0 for a top flight, and
        # older clients that only read `offset` degrade to the previous
        # shift-only behaviour rather than breaking.
        "dispersion": round(disp, 4),
        "pivot": round(pivot, 2),
        "quality": co.global_elo_quality(league_id),
        "method": "domestic ELO + league bridge + Club World Cup confederation shift",
        "cross_conf_matches": 60,
    }
    return data


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
