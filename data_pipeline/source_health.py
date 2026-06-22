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

# Warn when a fetch returns fewer rows than these floors
_COVERAGE_FLOORS: dict[str, int] = {
    "asa":      200,   # at least 200 historical matches per backfill run
    "espn":       1,   # at least 1 fixture in a 14-day window
    "pinnacle":   1,   # at least 1 odds row when games are upcoming
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
    """Structured pass/fail of the latest run per source against coverage floors.

    Returns {source_name: {"parsed": int, "floor": int, "ok": bool,
                           "success": bool, "error": str|None}}.
    Consumed by the promotion gate so a model is never promoted on top of a
    silently-degraded data feed. Returns {} if the health file is missing
    or empty (caller decides whether absence is a hard fail).
    """
    floors = floors or _COVERAGE_FLOORS
    report = get_source_health_report()
    if report is None or report.empty:
        return {}

    status: dict = {}
    for _, r in report.iterrows():
        name = r.get("source_name")
        floor = floors.get(name, 0)
        parsed = int(r.get("parsed_count") or 0)
        success = bool(r.get("success"))
        status[name] = {
            "parsed":  parsed,
            "floor":   floor,
            "ok":      success and parsed >= floor,
            "success": success,
            "error":   r.get("error_message"),
        }
    return status


def get_source_health_report() -> pd.DataFrame:
    """Return the most recent run stats for each source."""
    if not _HEALTH_PATH.exists():
        return pd.DataFrame(columns=_SCHEMA)
    try:
        df = pd.read_parquet(_HEALTH_PATH)
        if df.empty:
            return df
        df["fetched_at"] = pd.to_datetime(df["fetched_at"], utc=True)
        return (
            df.sort_values("fetched_at", ascending=False)
            .drop_duplicates(subset=["source_name"], keep="first")
            .reset_index(drop=True)
        )
    except Exception as exc:
        logger.warning("source_health: get_report failed — %s", exc)
        return pd.DataFrame(columns=_SCHEMA)


def feature_null_report(key_columns: Optional[list] = None) -> dict:
    """Return null rates for key feature columns.

    In the DB-free active path there is no team_features table to query.
    Callers should pass a DataFrame directly instead. This stub returns {}
    so the promotion gate degrades gracefully rather than crashing.
    """
    logger.debug("source_health.feature_null_report: DB-free path returns {}; pass a DataFrame directly")
    return {}


def feature_null_report_from_df(df: pd.DataFrame, key_columns: Optional[list] = None) -> dict:
    """Return null rates for key feature columns from a DataFrame.

    Replacement for the DB-backed feature_null_report(). Pass the model frame
    directly to get null fractions for the columns that matter.
    """
    cols = key_columns or [
        "xg_rolling_5", "xg_rolling_10", "xga_rolling_5", "xga_rolling_10",
        "elo_pre", "form_pts_5",
    ]
    total = len(df)
    if total == 0:
        return {}
    return {
        c: round(df[c].isna().sum() / total, 4)
        for c in cols
        if c in df.columns
    }
