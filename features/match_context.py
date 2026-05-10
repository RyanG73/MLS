"""
Match-context features:
- Rivalry / derby flag
- High-importance match flag (CCC knockouts, playoff implications)
- High-altitude stadium flag (Colorado, Real Salt Lake)
- Pitch surface (turf vs grass)
- Kickoff hour cyclic encoding + day-of-week
- FIFA international break flag
"""

import math
from datetime import date, timedelta
from typing import Optional

from features.travel_features import is_dome

# ── MLS rivalries (hardcoded list) ────────────────────────────────────────────
_RIVALRIES: set[frozenset] = {
    frozenset(["POR", "SEA"]),    # Cascadia
    frozenset(["POR", "VAN"]),    # Cascadia
    frozenset(["SEA", "VAN"]),    # Cascadia
    frozenset(["NYC", "NYRB"]),   # Hudson River Derby
    frozenset(["LAG", "LAFC"]),   # El Tráfico
    frozenset(["ATL", "ORL"]),    # Soccer Southeast
    frozenset(["DAL", "HOU"]),    # Texas Derby (El Capitán)
    frozenset(["NE",  "NYRB"]),   # Heritage Cup
    frozenset(["DC",  "NYRB"]),   # Atlantic Cup
    frozenset(["TOR", "MTL"]),    # 401 Derby
    frozenset(["CHI", "CLB"]),    # Trillium Cup peer
    frozenset(["MIA", "ORL"]),    # Sunshine Derby
    frozenset(["RSL", "COL"]),    # Rocky Mountain Cup
    frozenset(["SKC", "CHI"]),    # Original 10 rivalry
    frozenset(["LAG", "SJ"]),     # California Clásico
}

# ── High-altitude stadiums (>3000 ft / ~915 m elevation matters for soccer) ──
_HIGH_ALTITUDE_TEAMS = {"COL", "RSL"}

# ── Pitch surface map (artificial turf MLS stadiums) ──────────────────────────
_TURF_STADIUMS = {
    "ATL",    # Mercedes-Benz (FieldTurf)
    "NE",     # Gillette Stadium
    "VAN",    # BC Place
    "SEA",    # Lumen Field
    "POR",    # Providence Park
    "MTL",    # Stade Saputo (turf for CCC; grass for MLS — keep as turf for safety)
}

# ── FIFA international break dates (annual; approximate months) ───────────────
# Each tuple is (start_month_day, end_month_day) — we compute year-specific later
_FIFA_BREAK_WINDOWS = [
    ("03-20", "03-31"),  # March
    ("06-01", "06-15"),  # June
    ("09-01", "09-15"),  # September
    ("10-08", "10-18"),  # October
    ("11-12", "11-22"),  # November
]


def is_rivalry(team_a: str, team_b: str) -> bool:
    return frozenset([team_a, team_b]) in _RIVALRIES


def is_high_altitude(home_team: str) -> bool:
    return home_team in _HIGH_ALTITUDE_TEAMS


def pitch_surface(home_team: str) -> str:
    return "turf" if home_team in _TURF_STADIUMS else "grass"


def is_post_fifa_break(match_date: str) -> bool:
    """True if the match is the first weekend after a FIFA window closes."""
    try:
        d = date.fromisoformat(match_date)
    except ValueError:
        return False

    for _, end_md in _FIFA_BREAK_WINDOWS:
        try:
            end_date = date.fromisoformat(f"{d.year}-{end_md}")
        except ValueError:
            continue
        # Within 7 days after the FIFA window closes
        if 0 <= (d - end_date).days <= 7:
            return True
    return False


def kickoff_features(kickoff_time) -> dict:
    """
    Cyclic encoding for kickoff hour + one-hot day-of-week.
    Accepts datetime or string ISO timestamp.
    """
    if kickoff_time is None:
        return {
            "kickoff_hour_sin":  0.0,
            "kickoff_hour_cos":  1.0,
            "is_weekend":        0,
            "is_weeknight":      0,
        }

    try:
        if isinstance(kickoff_time, str):
            from datetime import datetime
            ko = datetime.fromisoformat(kickoff_time.replace("Z", "+00:00"))
        else:
            ko = kickoff_time
        hour = ko.hour
        dow = ko.weekday()  # 0=Monday
    except Exception:
        return {
            "kickoff_hour_sin":  0.0,
            "kickoff_hour_cos":  1.0,
            "is_weekend":        0,
            "is_weeknight":      0,
        }

    return {
        "kickoff_hour_sin":  math.sin(2 * math.pi * hour / 24),
        "kickoff_hour_cos":  math.cos(2 * math.pi * hour / 24),
        "is_weekend":        int(dow in (5, 6)),       # Sat/Sun
        "is_weeknight":      int(dow in (1, 2, 3, 4)), # Tue–Fri
    }


def is_high_importance(home_team: str, away_team: str, season: int, match_date: str, competition: str = "mls") -> bool:
    """
    Flag matches with elevated stakes:
    - Rivalries
    - CCC knockout rounds
    - End-of-season MLS games (final 6 weeks)
    """
    if is_rivalry(home_team, away_team):
        return True
    if competition == "ccc":
        return True

    try:
        d = date.fromisoformat(match_date)
        season_end_estimate = date(season, 10, 21)  # MLS regular season ~late October
        if (season_end_estimate - d).days <= 42:  # final 6 weeks
            return True
    except (ValueError, TypeError):
        pass
    return False


def build_match_context(home_team: str, away_team: str, season: int, match_date: str, kickoff_time=None, competition: str = "mls") -> dict:
    """Assemble all match-context features into a single dict."""
    ctx = {
        "is_rivalry":         int(is_rivalry(home_team, away_team)),
        "is_high_altitude":   int(is_high_altitude(home_team)),
        "is_high_importance": int(is_high_importance(home_team, away_team, season, match_date, competition)),
        "is_post_fifa_break": int(is_post_fifa_break(match_date)),
        "pitch_is_turf":      int(pitch_surface(home_team) == "turf"),
        "is_dome":            int(is_dome(home_team)),
    }
    ctx.update(kickoff_features(kickoff_time))
    return ctx
