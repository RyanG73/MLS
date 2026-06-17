"""External strength anchors for cross-league continental modeling.

UEFA league (country) coefficients place modeled leagues on a common scale;
UEFA club coefficients give unmodeled continental entrants a strength estimate.
Both are mapped to ELO points by the single slope _K_COEFF.

Sources (refresh ~annually after the season ends):
  - League coefficients: UEFA 5-year country ranking
    https://www.uefa.com/nationalassociations/uefarankings/country/
  - Club coefficients: UEFA 5-year club ranking
    https://www.uefa.com/nationalassociations/uefarankings/club/
Values below captured 2026-06 (2025-26 season end).
"""
from __future__ import annotations

# ELO points per UEFA-coefficient point (calibrated in validate_continental.py,
# a later task; this is the starting prior).
_K_COEFF = 3.0

# Strength (ELO points) assigned to an unknown/unlisted club — conservative,
# roughly a mid-table side in a weak European league.
BASELINE_STRENGTH = 1450.0

# Reference league (anchors the offset scale at 0).
_REF_LEAGUE = "epl"

# UEFA 5-year country coefficients (2025-26). Keyed by our internal league ids.
_LEAGUE_COEFF: dict[str, float] = {
    "epl": 94.0, "la-liga": 79.0, "serie-a": 76.0, "bundesliga": 74.0,
    "ligue-1": 67.0,
}

# UEFA 5-year club coefficients for common unmodeled UCL entrants, expressed
# directly in ELO points to keep the table legible.
_CLUB_STRENGTH: dict[str, float] = {
    "Real Madrid": 2000.0, "Bayern Munich": 1980.0, "Manchester City": 1990.0,
    "Paris Saint-Germain": 1940.0, "Inter Milan": 1900.0, "Porto": 1780.0,
    "Benfica": 1800.0, "Sporting CP": 1760.0, "PSV Eindhoven": 1740.0,
    "Feyenoord": 1720.0, "Ajax": 1730.0, "Club Brugge": 1690.0,
    "Celtic": 1660.0, "Shakhtar Donetsk": 1700.0, "Red Bull Salzburg": 1710.0,
}


def league_offset(league_id: str) -> float:
    """Per-league additive ELO offset onto the common cross-league scale.

    EPL (the strongest modeled league) anchors at 0; weaker leagues are negative.
    Unknown leagues return 0 (no offset) rather than raising.
    """
    if league_id not in _LEAGUE_COEFF:
        return 0.0
    return _K_COEFF * (_LEAGUE_COEFF[league_id] - _LEAGUE_COEFF[_REF_LEAGUE])


def club_strength(club: str) -> float:
    """Cross-league strength (ELO points) for an unmodeled club, or BASELINE."""
    return _CLUB_STRENGTH.get(club, BASELINE_STRENGTH)
