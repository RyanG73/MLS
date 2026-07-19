"""Data source health recorder — per-feed fetch accounting (DB-free).

Each data client calls record_source_run() after every fetch attempt. Results
are appended to data/source_health.parquet so operators can answer "when did
ASA last succeed, and how many rows did it return?" without digging through logs.

Public API is unchanged from the previous DB-backed version so all callers work
without modification.
"""

import hashlib
import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)

_HEALTH_PATH = Path("data/source_health.parquet")

# Row-count floors per source — checked against the most recent *significant* endpoint run.
# Auxiliary endpoints (get_teams, get_players) are excluded from gate checks via
# _SIGNIFICANT_ENDPOINTS so a lightweight metadata call can't poison the gate.
_COVERAGE_FLOORS: dict[str, int] = {
    "asa":           400,   # historical MLS match rows across all seasons
    "espn":           50,   # MLS or Liga MX fixtures for the current season
    "understat":     100,   # xG match rows for a league season
    "football_data":  50,   # historical results rows per league
    "pinnacle":        1,   # at least 1 odds row when games are upcoming
}

# Which endpoints count for the gate. If a source has recorded runs for both a
# significant and an auxiliary endpoint, only the significant ones are considered.
_SIGNIFICANT_ENDPOINTS: dict[str, list[str]] = {
    "asa":           ["get_games"],
    "espn":          ["liga_mx_scoreboard", "mls_scoreboard", "scoreboard"],
    "understat":     ["canonical_frame"],
    "football_data": ["results"],
}

_SCHEMA = [
    "source_run_id", "source_name", "endpoint", "fetched_at",
    "raw_count", "parsed_count", "matched_count", "unmatched_count",
    "schema_hash", "null_rate_json", "success", "error_message",
]


def record_source_run(
    source_name: str,
    endpoint: str,
    raw_count: int,
    parsed_count: int,
    matched_count: int = 0,
    unmatched_count: int = 0,
    null_rates: Optional[dict] = None,
    error_message: Optional[str] = None,
) -> str:
    """Append one data-fetch event to data/source_health.parquet.

    Args:
        source_name:    logical name ("asa", "espn", "pinnacle", "transfermarkt")
        endpoint:       API method or URL stub called
        raw_count:      rows received from the external API
        parsed_count:   rows successfully parsed into the internal schema
        matched_count:  rows matched to canonical entities
        unmatched_count: rows that could not be matched (e.g. unknown team)
        null_rates:     {column: null_fraction} dict for key fields (optional)
        error_message:  exception message if the fetch failed

    Returns:
        source_run_id (UUID string)

    This function swallows all internal errors so it never crashes a caller.
    """
    run_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    schema_hash = hashlib.md5(
        json.dumps(null_rates or {}, sort_keys=True).encode()
    ).hexdigest()[:16]

    row = {
        "source_run_id":   run_id,
        "source_name":     source_name,
        "endpoint":        endpoint,
        "fetched_at":      now.isoformat(),
        "raw_count":       raw_count,
        "parsed_count":    parsed_count,
        "matched_count":   matched_count,
        "unmatched_count": unmatched_count,
        "schema_hash":     schema_hash,
        "null_rate_json":  json.dumps(null_rates or {}),
        "success":         error_message is None,
        "error_message":   error_message,
    }

    try:
        _append_row(row)
        _check_coverage_floor(source_name, parsed_count, error_message)
    except Exception as exc:
        logger.warning("source_health: failed to record run for %s: %s", source_name, exc)

    return run_id


def _append_row(row: dict) -> None:
    """Read existing parquet, append row, write back."""
    new_df = pd.DataFrame([row])
    _HEALTH_PATH.parent.mkdir(parents=True, exist_ok=True)
    if _HEALTH_PATH.exists():
        existing = pd.read_parquet(_HEALTH_PATH)
        combined = pd.concat([existing, new_df], ignore_index=True)
    else:
        combined = new_df
    combined.to_parquet(_HEALTH_PATH, index=False)


def _check_coverage_floor(
    source_name: str, parsed_count: int, error_message: Optional[str]
) -> None:
    if error_message:
        logger.warning("source_health [%s]: fetch error — %s", source_name, error_message)
        return
    floor = _COVERAGE_FLOORS.get(source_name)
    if floor is not None and parsed_count < floor:
        logger.warning(
            "source_health [%s]: low coverage — %d rows (floor=%d)",
            source_name, parsed_count, floor,
        )


def coverage_gate_status(floors: Optional[dict] = None) -> dict:
    """Structured pass/fail of the latest significant-endpoint run per source.

    Returns {source_name: {"parsed": int, "floor": int, "ok": bool,
                           "success": bool, "error": str|None,
                           "fetched_at": str|None, "endpoint": str}}.
    For sources listed in _SIGNIFICANT_ENDPOINTS, only runs matching those
    endpoints are considered — auxiliary calls like get_teams cannot mask a
    missing match-data fetch. Returns {} if the health file is missing or empty.
    """
    floors = floors or _COVERAGE_FLOORS
    if not _HEALTH_PATH.exists():
        return {}
    try:
        df = pd.read_parquet(_HEALTH_PATH)
        if df.empty:
            return {}
        df["fetched_at"] = pd.to_datetime(df["fetched_at"], utc=True)
    except Exception as exc:
        logger.warning("source_health: coverage_gate_status failed — %s", exc)
        return {}

    status: dict = {}
    for source_name, floor in floors.items():
        src = df[df["source_name"] == source_name]
        if src.empty:
            continue
        sig_eps = _SIGNIFICANT_ENDPOINTS.get(source_name)
        if sig_eps:
            sig = src[src["endpoint"].isin(sig_eps)]
            if not sig.empty:
                src = sig
        r = src.sort_values("fetched_at", ascending=False).iloc[0]
        parsed = int(r.get("parsed_count") or 0)
        success = bool(r.get("success"))
        fetched_at = r.get("fetched_at")
        status[source_name] = {
            "parsed":     parsed,
            "floor":      floor,
            "ok":         success and parsed >= floor,
            "success":    success,
            "error":      r.get("error_message"),
            "fetched_at": fetched_at.isoformat() if hasattr(fetched_at, "isoformat") else str(fetched_at),
            "endpoint":   str(r.get("endpoint", "")),
        }
    return status
