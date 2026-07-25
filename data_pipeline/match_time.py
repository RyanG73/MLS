"""Competition-aware kickoff timestamp normalization.

Provider timestamps are UTC instants, but a match belongs to the calendar date
used by its competition.  That distinction matters for evening matches in the
Americas, where midnight UTC is still the prior local matchday.
"""

from __future__ import annotations

import pandas as pd


# These competitions publish and present their schedule in Eastern Time.  This
# also gives the intended national matchday for West Coast evening fixtures.
COMPETITION_TIMEZONES = {
    "nwsl": "America/New_York",
    "uslc": "America/New_York",
    "usl-championship": "America/New_York",
}


def competition_datetime(values, league_id: str):
    """Parse UTC provider timestamps and return timezone-naive competition time.

    Accepts any input supported by ``pandas.to_datetime``, including a scalar,
    Series, or DatetimeIndex.  Unmapped competitions retain the prior behavior:
    UTC with the timezone removed.
    """
    parsed = pd.to_datetime(values, utc=True, errors="coerce")
    timezone = COMPETITION_TIMEZONES.get(league_id)

    if isinstance(parsed, pd.Series):
        if timezone:
            parsed = parsed.dt.tz_convert(timezone)
        return parsed.dt.tz_localize(None)

    if isinstance(parsed, pd.DatetimeIndex):
        if timezone:
            parsed = parsed.tz_convert(timezone)
        return parsed.tz_localize(None)

    if pd.isna(parsed):
        return pd.NaT
    if timezone:
        parsed = parsed.tz_convert(timezone)
    return parsed.tz_localize(None)


def competition_date(value, league_id: str) -> pd.Timestamp:
    """Return the normalized competition-local calendar date for one kickoff."""
    parsed = competition_datetime(value, league_id)
    return parsed.normalize() if pd.notna(parsed) else pd.NaT
