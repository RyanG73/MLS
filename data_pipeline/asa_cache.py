"""ASA (itscalledsoccer) cached adapter.

Wraps AmericanSoccerAnalysis API calls with a parquet file cache so repeated
build runs don't hit the network when the data is fresh, and so source health
is recorded after every fetch attempt.

Cache location: data/asa_cache/<endpoint>_<league>.parquet
Freshness:      max_age_hours (default 24 h) based on file mtime

Usage:
    from data_pipeline.asa_cache import get_games, get_teams, get_player_goals_added

    games = get_games("mls")           # cached, max 24 h old
    teams = get_teams("mls")           # cached, max 24 h old
    gplus = get_player_goals_added("mls", split_by_seasons=True)

The underlying client is created once per module load and shared across calls.
TLS verification is disabled because ASA's endpoint has a self-signed cert issue
that is already documented in PROJECT_HISTORY.md.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)

_CACHE_DIR = Path("data/asa_cache")
_DEFAULT_MAX_AGE_HOURS = 24

_asa_client: Any = None  # lazy singleton


def _client():
    """Return a shared AmericanSoccerAnalysis client (lazy init)."""
    global _asa_client
    if _asa_client is None:
        from itscalledsoccer.client import AmericanSoccerAnalysis
        _asa_client = AmericanSoccerAnalysis()
        try:
            _asa_client.session.verify = False
        except Exception:
            pass
    return _asa_client


def _cache_path(endpoint: str, league: str) -> Path:
    return _CACHE_DIR / f"{endpoint}_{league}.parquet"


def _is_fresh(path: Path, max_age_hours: float) -> bool:
    if not path.exists():
        return False
    age_hours = (time.time() - path.stat().st_mtime) / 3600
    return age_hours < max_age_hours


def _record_health(source_name: str, endpoint: str, df: pd.DataFrame | None,
                   error: str | None = None) -> None:
    try:
        from data_pipeline.source_health import record_source_run
        record_source_run(
            source_name=source_name,
            endpoint=endpoint,
            raw_count=len(df) if df is not None else 0,
            parsed_count=len(df) if df is not None else 0,
            error_message=error,
        )
    except Exception as exc:
        logger.debug("asa_cache: could not record health for %s: %s", endpoint, exc)


def _fetch_and_cache(endpoint: str, league: str, fetch_fn, **kwargs) -> pd.DataFrame:
    """Fetch from API, save to cache, record source health, return DataFrame."""
    cache = _cache_path(endpoint, league)
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)

    logger.info("asa_cache: fetching %s for %s from API", endpoint, league)
    error = None
    df = None
    try:
        df = fetch_fn(**kwargs)
        if df is not None and not df.empty:
            df.to_parquet(cache, index=False)
            logger.info("asa_cache: cached %s %s → %d rows → %s", endpoint, league, len(df), cache)
    except Exception as exc:
        error = str(exc)
        logger.warning("asa_cache: fetch failed for %s %s: %s", endpoint, league, exc)
        if cache.exists():
            logger.warning("asa_cache: using stale cache as fallback")
            df = pd.read_parquet(cache)

    _record_health("asa", endpoint, df, error=error)

    if df is None:
        return pd.DataFrame()
    return df


def _load_or_fetch(endpoint: str, league: str, fetch_fn, max_age_hours: float, **kwargs) -> pd.DataFrame:
    cache = _cache_path(endpoint, league)
    if _is_fresh(cache, max_age_hours):
        logger.info("asa_cache: cache hit for %s %s (age < %gh)", endpoint, league, max_age_hours)
        return pd.read_parquet(cache)
    return _fetch_and_cache(endpoint, league, fetch_fn, **kwargs)


# ── Public cached getters ──────────────────────────────────────────────────────

def get_games(leagues: str, seasons=None, max_age_hours: float = _DEFAULT_MAX_AGE_HOURS) -> pd.DataFrame:
    """Return ASA game rows for the given league, cached for up to max_age_hours.

    Args:
        leagues:        e.g. "mls" or ["mls"]
        seasons:        optional season filter; if None, all seasons are returned
        max_age_hours:  cache TTL in hours (default 24)
    """
    league_key = leagues if isinstance(leagues, str) else "_".join(sorted(leagues))
    asa = _client()

    def _fetch(leagues=leagues, seasons=seasons):
        kwargs: dict = {"leagues": leagues}
        if seasons is not None:
            kwargs["seasons"] = seasons
        return asa.get_games(**kwargs)

    return _load_or_fetch("get_games", league_key, _fetch, max_age_hours)


def get_teams(leagues: str, max_age_hours: float = _DEFAULT_MAX_AGE_HOURS) -> pd.DataFrame:
    """Return ASA team rows for the given league, cached for up to max_age_hours."""
    league_key = leagues if isinstance(leagues, str) else "_".join(sorted(leagues))
    asa = _client()
    return _load_or_fetch("get_teams", league_key, lambda: asa.get_teams(leagues=leagues), max_age_hours)


def get_players(leagues: str, max_age_hours: float = _DEFAULT_MAX_AGE_HOURS) -> pd.DataFrame:
    """Return ASA player rows for the given league, cached for up to max_age_hours."""
    league_key = leagues if isinstance(leagues, str) else "_".join(sorted(leagues))
    asa = _client()
    return _load_or_fetch("get_players", league_key, lambda: asa.get_players(leagues=leagues), max_age_hours)


def get_player_goals_added(
    leagues: str,
    split_by_seasons: bool = True,
    max_age_hours: float = _DEFAULT_MAX_AGE_HOURS,
) -> pd.DataFrame:
    """Return ASA player goals-added rows, cached for up to max_age_hours."""
    league_key = leagues if isinstance(leagues, str) else "_".join(sorted(leagues))
    suffix = "_by_season" if split_by_seasons else ""
    asa = _client()
    return _load_or_fetch(
        f"get_player_goals_added{suffix}", league_key,
        lambda: asa.get_player_goals_added(leagues=leagues, split_by_seasons=split_by_seasons),
        max_age_hours,
    )


def get_goalkeeper_goals_added(
    leagues: str,
    split_by_seasons: bool = True,
    max_age_hours: float = _DEFAULT_MAX_AGE_HOURS,
) -> pd.DataFrame:
    """Return ASA goalkeeper goals-added rows, cached for up to max_age_hours."""
    league_key = leagues if isinstance(leagues, str) else "_".join(sorted(leagues))
    suffix = "_by_season" if split_by_seasons else ""
    asa = _client()
    return _load_or_fetch(
        f"get_goalkeeper_goals_added{suffix}", league_key,
        lambda: asa.get_goalkeeper_goals_added(leagues=leagues, split_by_seasons=split_by_seasons),
        max_age_hours,
    )


def get_team_salaries(
    leagues: str,
    split_by_teams: bool = True,
    max_age_hours: float = _DEFAULT_MAX_AGE_HOURS,
) -> pd.DataFrame:
    """Return ASA team salary rows, cached for up to max_age_hours."""
    league_key = leagues if isinstance(leagues, str) else "_".join(sorted(leagues))
    suffix = "_by_team" if split_by_teams else ""
    asa = _client()
    return _load_or_fetch(
        f"get_team_salaries{suffix}", league_key,
        lambda: asa.get_team_salaries(leagues=leagues, split_by_teams=split_by_teams),
        max_age_hours,
    )


def cache_status() -> dict:
    """Return freshness status of all ASA cache files.

    Returns {filename: {"rows": int, "age_hours": float, "fresh": bool}}.
    """
    if not _CACHE_DIR.exists():
        return {}
    status = {}
    for p in sorted(_CACHE_DIR.glob("*.parquet")):
        age_h = (time.time() - p.stat().st_mtime) / 3600
        try:
            rows = len(pd.read_parquet(p))
        except Exception:
            rows = -1
        status[p.name] = {
            "rows": rows,
            "age_hours": round(age_h, 1),
            "fresh": age_h < _DEFAULT_MAX_AGE_HOURS,
            "fetched_at": datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc).isoformat(),
        }
    return status
