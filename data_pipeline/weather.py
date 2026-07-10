"""Kickoff weather via open-meteo (no API key) — F2, 2026-07-09 feedback.

Two calls, both free-tier and cached:
  geocode(city)              → (lat, lon), disk-cached in data/venue_geo.json
  kickoff_weather(city, iso) → {"temp_c", "precip_pct"} at the kickoff hour,
                               or None when anything is missing/unavailable

Failure policy: every error returns None — weather must never break a build.
Forecast horizon is ~16 days; callers should only ask for matches within the
next week (further out the answer is noise anyway).
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

import pandas as pd
import requests

logger = logging.getLogger(__name__)

_HDR = {"User-Agent": "Mozilla/5.0"}
_GEO_CACHE = Path("data/venue_geo.json")
_GEO_URL = "https://geocoding-api.open-meteo.com/v1/search"
_FC_URL = "https://api.open-meteo.com/v1/forecast"

_geo_mem: dict[str, list[float] | None] | None = None
_fc_mem: dict[str, dict | None] = {}   # per-run forecast memo: city|date-hour


def _geo_cache() -> dict:
    global _geo_mem
    if _geo_mem is None:
        try:
            _geo_mem = json.loads(_GEO_CACHE.read_text())
        except (FileNotFoundError, json.JSONDecodeError):
            _geo_mem = {}
    return _geo_mem


def geocode(city: str) -> tuple[float, float] | None:
    """City name → (lat, lon). Disk-cached, including negative results."""
    if not city:
        return None
    cache = _geo_cache()
    if city in cache:
        v = cache[city]
        return (v[0], v[1]) if v else None
    try:
        r = requests.get(_GEO_URL, params={"name": city, "count": 1},
                         headers=_HDR, timeout=15)
        r.raise_for_status()
        hits = r.json().get("results") or []
        val = [hits[0]["latitude"], hits[0]["longitude"]] if hits else None
    except Exception as exc:                       # noqa: BLE001
        logger.warning("geocode(%s) failed: %s", city, exc)
        return None                                # transient: don't cache
    cache[city] = val
    try:
        _GEO_CACHE.parent.mkdir(parents=True, exist_ok=True)
        _GEO_CACHE.write_text(json.dumps(cache, indent=0, sort_keys=True))
    except OSError:
        pass
    return (val[0], val[1]) if val else None


def kickoff_weather(city: str, ko_utc: str) -> dict | None:
    """Forecast at the kickoff hour: {"temp_c": float, "precip_pct": int}."""
    if not city or not ko_utc:
        return None
    ts = pd.to_datetime(ko_utc, utc=True, errors="coerce")
    if pd.isna(ts):
        return None
    hour_key = f"{city}|{ts.strftime('%Y-%m-%dT%H')}"
    if hour_key in _fc_mem:
        return _fc_mem[hour_key]
    loc = geocode(city)
    out = None
    if loc:
        try:
            day = ts.strftime("%Y-%m-%d")
            r = requests.get(_FC_URL, params={
                "latitude": loc[0], "longitude": loc[1],
                "hourly": "temperature_2m,precipitation_probability",
                "start_date": day, "end_date": day,
                "timezone": "UTC"}, headers=_HDR, timeout=15)
            r.raise_for_status()
            hourly = r.json().get("hourly") or {}
            times = hourly.get("time") or []
            want = ts.strftime("%Y-%m-%dT%H:00")
            if want in times:
                i = times.index(want)
                temp = (hourly.get("temperature_2m") or [None] * len(times))[i]
                prec = (hourly.get("precipitation_probability") or [None] * len(times))[i]
                if temp is not None:
                    out = {"temp_c": round(float(temp), 1),
                           "precip_pct": int(prec) if prec is not None else None}
        except Exception as exc:                   # noqa: BLE001
            logger.warning("kickoff_weather(%s, %s) failed: %s", city, ko_utc, exc)
    _fc_mem[hour_key] = out
    return out
