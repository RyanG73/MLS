"""
Pure-function feature helpers extracted from eval_baseline.py (F4 phase).

All objects here are self-contained: no live API calls, no module-level side-effects,
no dependency on the eval_baseline df or ASA session.  eval_baseline.py imports from
this module; the smoke-test gate verifies behavior is identical after the move.

Extracted (2026-06-07):
  Constants: _PYTHAG_EXP, _PYTHAG_WIN, _FIFA_BREAKS, _HIGH_ALT_IDS
  Geometry: haversine_km
  Feature helpers: pythag_expected_pts, is_post_fifa, tz_band,
                   away_tz_shift_abs, away_tz_shift_signed
  Generic lookup helpers: zs_within_season, lagged_lookup,
                          pos_is_att, pos_is_def
"""

from __future__ import annotations

import math
from datetime import timedelta

import numpy as np
import pandas as pd

from data_pipeline.team_metadata import TEAM_COORDS as _TEAM_COORDS

# ── Pythagorean luck ──────────────────────────────────────────────────────────
PYTHAG_EXP: float = 1.83   # soccer exponent (Hamilton 2011)
PYTHAG_WIN: int   = 10     # rolling window for Pythagorean luck feature


def pythag_expected_pts(gf: float, ga: float, n: int) -> float:
    """Pythagorean expected points over n matches (soccer exponent ≈ 1.83).

    Returns n * 3 * win_rate using the 3*W approximation (draws ≈ partial
    wins).  Falls back to league-average rate (1.35 pts/match) when totals
    are zero.
    """
    if gf + ga == 0 or n == 0:
        return 1.35 * n
    win_rate = gf ** PYTHAG_EXP / (gf ** PYTHAG_EXP + ga ** PYTHAG_EXP)
    return 3.0 * win_rate * n


# ── Geometry ──────────────────────────────────────────────────────────────────

def haversine_km(a: "tuple | None", b: "tuple | None") -> float:
    """Great-circle distance (km) between two (lat, lon) tuples; 0 if either missing."""
    if not a or not b:
        return 0.0
    lat1, lon1, lat2, lon2 = map(math.radians, [a[0], a[1], b[0], b[1]])
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * 6371.0 * math.asin(math.sqrt(h))


# ── FIFA break dates ──────────────────────────────────────────────────────────
# International window end dates; match within 14 days after → is_post_fifa_break=1
FIFA_BREAKS: list[pd.Timestamp] = [pd.Timestamp(d) for d in [
    # 2017
    "2017-03-28", "2017-06-13", "2017-09-05", "2017-10-10",
    # 2018
    "2018-03-27", "2018-06-12", "2018-09-11", "2018-10-16",
    # 2019
    "2019-03-26", "2019-06-11", "2019-09-10", "2019-10-15",
    # 2020, 2021 excluded (COVID)
    # 2022
    "2022-03-29", "2022-06-14", "2022-09-27",
    "2022-11-15",  # World Cup year — November window displaces Oct
    # 2023
    "2023-03-28", "2023-06-20", "2023-09-12", "2023-10-17",
    # 2024
    "2024-03-26", "2024-06-11", "2024-09-10", "2024-10-15",
]]


def is_post_fifa(date: pd.Timestamp) -> int:
    """Return 1 if date falls within 14 days after a FIFA international window end."""
    for wb in FIFA_BREAKS:
        if timedelta(0) < (date - wb) <= timedelta(days=14):
            return 1
    return 0


# ── Altitude lookup ───────────────────────────────────────────────────────────
# Teams whose home stadium is ≥1000 m above sea level (relevant for physiology features)
HIGH_ALT_IDS: frozenset[str] = frozenset({"pzeQZ6xQKw", "a2lqR4JMr0"})  # Colorado, RSL


# ── TZ shift helpers ──────────────────────────────────────────────────────────

def tz_band(lon: float) -> int:
    """Approximate time-zone offset (integer hours east of UTC) from longitude."""
    return round(lon / 15)


def away_tz_shift_abs(home_team: str, away_team: str) -> float:
    """Absolute time-zone bands crossed by the away team (0 if coords missing)."""
    hc = _TEAM_COORDS.get(home_team)
    ac = _TEAM_COORDS.get(away_team)
    if not (hc and ac):
        return 0.0
    return float(abs(tz_band(hc[1]) - tz_band(ac[1])))


def away_tz_shift_signed(home_team: str, away_team: str) -> float:
    """Signed TZ shift: positive = away travels east (harder per chronobiology literature)."""
    hc = _TEAM_COORDS.get(home_team)
    ac = _TEAM_COORDS.get(away_team)
    if not (hc and ac):
        return 0.0
    return float(tz_band(hc[1]) - tz_band(ac[1]))


# ── Generic season-z-score helper ─────────────────────────────────────────────

def zs_within_season(raw: dict) -> dict:
    """Z-score a (team_id, season) → value dict within each season.

    Keys with < 3 values per season are silently omitted from the output.
    """
    out: dict[tuple, float] = {}
    for s in sorted({ss for (_, ss) in raw}):
        vals = [v for (t, ss), v in raw.items() if ss == s]
        if len(vals) < 3:
            continue
        mu = float(np.mean(vals))
        sd = max(float(np.std(vals)), 1e-6)
        for (t, ss), v in raw.items():
            if ss == s:
                out[(t, ss)] = (v - mu) / sd
    return out


# ── Season-lag lookup helper ──────────────────────────────────────────────────

def lagged_lookup(tbl: dict, team_id: str, season: int) -> "float | None":
    """Return the value for (team_id, season-1), falling back to (team_id, season-2).

    Returns None if neither lag is present.  Used to prevent leakage when a
    feature must use prior-season data only.
    """
    for lag in (1, 2):
        v = tbl.get((team_id, season - lag))
        if v is not None:
            return v
    return None


# ── Position-type predicates ──────────────────────────────────────────────────
# Substring-based matching (eval_baseline uses partial-string checks from ASA position strings)
_ATT_POS_KWS: frozenset[str] = frozenset([
    "fw", "forward", "winger", "attacking mid", "attacking midfielder",
    "am", "st", "cf", "lw", "rw",
])
_DEF_POS_KWS: frozenset[str] = frozenset([
    "cb", "fb", "defender", "centre back", "center back",
    "left back", "right back", "full back", "lb", "rb", "cd",
])


def pos_is_att(pos_val: object) -> bool:
    """True if the position string indicates an attacking role."""
    p = str(pos_val).lower().strip()
    return any(kw in p for kw in _ATT_POS_KWS)


def pos_is_def(pos_val: object) -> bool:
    """True if the position string indicates a defensive role."""
    p = str(pos_val).lower().strip()
    return any(kw in p for kw in _DEF_POS_KWS)
