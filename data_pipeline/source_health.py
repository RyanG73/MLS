"""Data source health recorder — per-feed fetch accounting.

Each data client calls record_source_run() after every fetch attempt. Results
land in the source_runs table so operators can answer "when did ASA last succeed,
and how many rows did it return?" without digging through logs.
"""

import hashlib
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)

# Warn when a fetch returns fewer rows than these floors
_COVERAGE_FLOORS: dict[str, int] = {
    "asa":      200,   # at least 200 historical matches per backfill run
    "espn":       1,   # at least 1 fixture in a 14-day window
    "pinnacle":   1,   # at least 1 odds row when games are upcoming
}


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
    """
    Record one data-fetch event to the source_runs table.

    Args:
        source_name:    logical name ("asa", "espn", "pinnacle")
        endpoint:       API method or URL stub called
        raw_count:      rows received from the external API
        parsed_count:   rows successfully parsed into the internal schema
        matched_count:  rows upserted / matched to DB records
        unmatched_count: rows that could not be matched (e.g. unknown team)
        null_rates:     {column: null_fraction} dict for key fields (optional)
        error_message:  exception message if the fetch failed

    Returns:
        source_run_id (UUID string)

    This function swallows all internal errors so it never crashes a caller.
    """
    from data_pipeline import db_utils  # lazy import to avoid circular deps

    run_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    schema_hash = hashlib.md5(
        json.dumps(null_rates or {}, sort_keys=True).encode()
    ).hexdigest()[:16]

    row = pd.DataFrame([{
        "source_run_id":    run_id,
        "source_name":      source_name,
        "endpoint":         endpoint,
        "fetched_at":       now.isoformat(),
        "raw_count":        raw_count,
        "parsed_count":     parsed_count,
        "matched_count":    matched_count,
        "unmatched_count":  unmatched_count,
        "schema_hash":      schema_hash,
        "null_rate_json":   json.dumps(null_rates or {}),
        "success":          error_message is None,
        "error_message":    error_message,
    }])

    try:
        db_utils.upsert_dataframe(row, "source_runs", ["source_run_id"])
        _check_coverage_floor(source_name, parsed_count, error_message)
    except Exception as exc:
        logger.warning("source_health: failed to record run for %s: %s", source_name, exc)

    return run_id


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
    """
    Structured pass/fail of the latest run per source against coverage floors.

    Returns {source_name: {"parsed": int, "floor": int, "ok": bool,
                           "success": bool, "error": str|None}}.
    Consumed by the promotion gate (Phase E) so a model is never promoted on
    top of a silently-degraded data feed.  Returns {} if the table is empty
    or unreachable (caller decides whether absence is a hard fail).
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
    from data_pipeline import db_utils

    try:
        return db_utils.query("""
            SELECT DISTINCT ON (source_name)
                source_name,
                endpoint,
                fetched_at,
                raw_count,
                parsed_count,
                matched_count,
                unmatched_count,
                success,
                error_message
            FROM source_runs
            ORDER BY source_name, fetched_at DESC
        """)
    except Exception as exc:
        logger.warning("source_health: get_report failed — %s", exc)
        return pd.DataFrame()


def feature_null_report(key_columns: Optional[list] = None) -> dict:
    """
    Return null rates for key feature columns in the team_features table.

    Useful for surfacing silent fallback / imputation issues. Returns
    {column_name: null_fraction} for each requested column.
    """
    from data_pipeline import db_utils

    cols = key_columns or [
        "xg_rolling_5", "xg_rolling_10", "xga_rolling_5", "xga_rolling_10",
        "elo_pre", "travel_km", "days_rest", "form_pts_5",
    ]
    try:
        null_exprs = ", ".join(
            f"SUM(CASE WHEN {c} IS NULL THEN 1 ELSE 0 END) AS null_{c}" for c in cols
        )
        df = db_utils.query(f"SELECT COUNT(*) AS total, {null_exprs} FROM team_features")
        if df.empty or int(df["total"].iloc[0]) == 0:
            return {}
        total = int(df["total"].iloc[0])
        return {c: round(int(df[f"null_{c}"].iloc[0]) / total, 4) for c in cols}
    except Exception as exc:
        logger.warning("source_health: feature_null_report failed — %s", exc)
        return {}
