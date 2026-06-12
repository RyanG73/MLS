"""
Weather features at kickoff time using the Open-Meteo API (free, no API key).
Caches results in the matches table to avoid refetching.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

import requests

from features.travel_features import stadium_coords, is_dome

logger = logging.getLogger(__name__)

_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
_HISTORICAL_URL = "https://archive-api.open-meteo.com/v1/archive"


def fetch_weather(
    home_team: str,
    match_date: str,
    kickoff_hour_local: int = 19,
) -> Optional[dict]:
    """
    Fetch weather conditions at kickoff for the home team's stadium.
    Returns dict with temp_c, wind_kph, precip_mm, humidity, or None on failure.

    Uses forecast endpoint for future dates, archive for past dates.
    """
    if is_dome(home_team):
        logger.debug("Skipping weather fetch for dome/retractable-roof stadium: %s", home_team)
        return None

    lat, lon = stadium_coords(home_team)
    today = datetime.now(timezone.utc).date().isoformat()
    is_future = match_date >= today

    url = _FORECAST_URL if is_future else _HISTORICAL_URL
    params = {
        "latitude":     lat,
        "longitude":    lon,
        "start_date":   match_date,
        "end_date":     match_date,
        "hourly":       "temperature_2m,wind_speed_10m,precipitation,relative_humidity_2m",
        "timezone":     "auto",
        "wind_speed_unit": "kmh",
        "temperature_unit": "celsius",
        "precipitation_unit": "mm",
    }

    try:
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        logger.warning("Open-Meteo fetch failed for %s on %s: %s", home_team, match_date, exc)
        return None

    hourly = data.get("hourly", {})
    times = hourly.get("time", [])
    if not times:
        return None

    # Pick the hour closest to local kickoff
    target_hour = max(0, min(23, int(kickoff_hour_local)))
    target_idx = None
    for i, t in enumerate(times):
        try:
            hr = int(t.split("T")[1][:2])
            if hr == target_hour:
                target_idx = i
                break
        except Exception:
            continue
    if target_idx is None:
        target_idx = min(target_hour, len(times) - 1)

    def _safe(arr, idx):
        try:
            v = arr[idx]
            return float(v) if v is not None else None
        except (IndexError, TypeError, ValueError):
            return None

    return {
        "weather_temp_c":    _safe(hourly.get("temperature_2m", []),       target_idx),
        "weather_wind_kph":  _safe(hourly.get("wind_speed_10m", []),       target_idx),
        "weather_precip_mm": _safe(hourly.get("precipitation", []),        target_idx),
        "weather_humidity":  _safe(hourly.get("relative_humidity_2m", []), target_idx),
    }


def update_match_weather(match_id: str, home_team: str, match_date: str, kickoff_hour: int = 19) -> bool:
    """
    Fetch weather for a match and write to matches table.
    Returns True if data was written, False on failure.
    """
    from data_pipeline import db_utils

    weather = fetch_weather(home_team, match_date, kickoff_hour)
    if not weather:
        return False

    db_utils.execute(
        """
        UPDATE matches
        SET weather_temp_c = %s, weather_wind_kph = %s,
            weather_precip_mm = %s, weather_humidity = %s
        WHERE match_id = %s
        """,
        [
            weather["weather_temp_c"],
            weather["weather_wind_kph"],
            weather["weather_precip_mm"],
            weather["weather_humidity"],
            match_id,
        ],
    )
    return True


def backfill_recent_weather(days_back: int = 14, days_ahead: int = 14) -> int:
    """Populate weather for matches in a window. Returns count updated."""
    from data_pipeline import db_utils

    matches = db_utils.query(
        f"""
        SELECT match_id, home_team, date, kickoff_time
        FROM matches
        WHERE date BETWEEN current_date - INTERVAL '{days_back} days'
                       AND current_date + INTERVAL '{days_ahead} days'
          AND weather_temp_c IS NULL
        ORDER BY date
        """
    )
    n_updated = 0
    for _, row in matches.iterrows():
        ko_hour = 19
        if row.get("kickoff_time") is not None:
            try:
                ko_hour = row["kickoff_time"].hour
            except Exception:
                pass
        if update_match_weather(row["match_id"], row["home_team"], str(row["date"]), ko_hour):
            n_updated += 1
    logger.info("Updated weather for %d matches.", n_updated)
    return n_updated
