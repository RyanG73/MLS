"""External strength anchors for cross-league continental modeling.

UEFA league (country) coefficients place modeled leagues on a common scale;
UEFA club coefficients give unmodeled continental entrants a strength estimate.
League (country) coefficients are scaled to ELO offsets via _K_COEFF (see
league_offset()); club coefficients are stored pre-resolved as ELO-point
strengths and are used directly without any further scaling.

Concacaf-internal league offsets (MLS/Liga MX/Central American) are stored in
a separate dict (_CONCACAF_OFFSET) and are RELATIVE only — Concacaf teams never
meet UEFA teams and match_lambdas uses strength differences, so the absolute
anchor is irrelevant. MLS is the Concacaf reference (0).

Sources (refresh ~annually after the season ends):
  - League coefficients: UEFA 5-year country ranking
    https://www.uefa.com/nationalassociations/uefarankings/country/
  - Club coefficients: UEFA 5-year club ranking
    https://www.uefa.com/nationalassociations/uefarankings/club/
Values below captured 2026-06 (2025-26 season end).
"""
from __future__ import annotations
import json
from pathlib import Path

# ── fitted-offset JSON (Approach C) ──────────────────────────────────────────
# Lazy-loaded once on first call to league_offset(); absent file ⇒ fallback to
# prior logic below.  This module MUST NOT import league_bridge or
# build_continental_data (cycle risk) — it only reads a pre-built JSON file.
_FITTED_OFFSETS: dict[str, float] | None = None
_FITTED_OFFSETS_LOADED: bool = False

_FITTED_JSON = Path(__file__).parent.parent / "experiments" / "league_offsets.json"


def _load_fitted() -> dict[str, float] | None:
    """Lazy-load experiments/league_offsets.json exactly once."""
    global _FITTED_OFFSETS, _FITTED_OFFSETS_LOADED
    if _FITTED_OFFSETS_LOADED:
        return _FITTED_OFFSETS
    _FITTED_OFFSETS_LOADED = True
    try:
        _FITTED_OFFSETS = json.loads(_FITTED_JSON.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        _FITTED_OFFSETS = None
    return _FITTED_OFFSETS


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

# Concacaf-internal league offsets (ELO points). These are RELATIVE only — Concacaf
# teams never meet UEFA teams and match_lambdas uses strength differences, so the
# absolute anchor is irrelevant. MLS is the reference (0); Liga MX carries a modest
# edge reflecting recent near-parity in Concacaf Champions Cup play.
_CONCACAF_OFFSET: dict[str, float] = {
    "mls": 0.0,
    "liga-mx": 30.0,
}

# Cross-league strength (ELO points) for clubs, on the SAME scale as the modeled
# domestic-ELO+offset ratings (which span ~1388-1711 for the UCL field). The big-5
# elite entries are used only by the coefficient-only validator (the dashboard build
# resolves big-5 teams via real ELO); non-big-5 clubs are the actual build fallback.
# Tiers: big-5 elite ~1660-1720; strong non-big-5 UCL regulars ~1540-1635; weaker
# qualifiers ~1425-1500. Calibrated 2026-06-16 against the observed modeled scale.
_CLUB_STRENGTH: dict[str, float] = {
    # Big-5 elite (validator only).
    "Real Madrid": 1720.0, "Manchester City": 1715.0, "Bayern Munich": 1710.0,
    "Arsenal": 1700.0, "Barcelona": 1695.0, "Liverpool": 1675.0,
    "Internazionale": 1670.0, "Paris Saint-Germain": 1660.0,
    # Strong non-big-5 UCL regulars — good but below the big-5 elite.
    "Benfica": 1635.0, "Porto": 1620.0, "Sporting CP": 1615.0,
    "Ajax": 1590.0, "PSV Eindhoven": 1585.0, "Feyenoord Rotterdam": 1565.0,
    "Shakhtar Donetsk": 1560.0, "Club Brugge": 1545.0, "Celtic": 1540.0,
    "RB Salzburg": 1535.0,
    # Mid / weaker qualifiers.
    "Dinamo Zagreb": 1495.0, "Red Star Belgrade": 1485.0, "Young Boys": 1470.0,
    "Sparta Prague": 1465.0, "SK Sturm Graz": 1455.0, "Slovan Bratislava": 1425.0,
    # --- Europa/Conference unmodeled entrants ---
    # Non-big-5 clubs that appear regularly in UEL/UECL; big-5 clubs excluded
    # (they are resolved via real domestic ELO). Values on the same ELO scale as
    # the modeled domestic leagues (~1450-1620 for this tier).
    "Galatasaray": 1575.0, "Fenerbahce": 1585.0, "Olympiacos": 1560.0,
    "Braga": 1560.0, "Slavia Prague": 1540.0, "Rangers": 1545.0,
    "PAOK": 1500.0, "Ferencvaros": 1490.0, "Anderlecht": 1520.0,
    "AZ Alkmaar": 1540.0, "Real Betis": 1590.0, "Fiorentina": 1590.0,
    "Viktoria Plzen": 1480.0, "Legia Warsaw": 1470.0, "Molde": 1450.0,
    # --- Concacaf unmodeled clubs ---
    # Central American / Caribbean clubs appearing in Concacaf Champions Cup and
    # Leagues Cup; MLS and Liga MX clubs are resolved via their domestic ELO.
    # Values ~1380-1500, RELATIVE to the Concacaf internal scale.
    "Alajuelense": 1490.0, "Saprissa": 1485.0, "Herediano": 1470.0,
    "Olimpia": 1460.0, "Motagua": 1450.0, "Real Espana": 1440.0,
    "Cavalier": 1390.0, "Forge FC": 1430.0, "Violette": 1385.0,
    "Robinhood": 1380.0, "Antigua GFC": 1400.0, "Real Esteli": 1420.0,
    "Sporting San Miguelito": 1400.0,
}


def league_offset(league_id: str) -> float:
    """Per-league additive ELO offset onto the common cross-league scale.

    When ``experiments/league_offsets.json`` exists (built by
    ``scripts.eval.league_bridge.fit_offsets``), that file's value is returned
    for any league it covers (Approach C — bridge-regression offsets).  For
    leagues absent from the file the prior logic below applies as a fallback.

    Prior logic — two independent regimes:

    * **UEFA leagues** (_LEAGUE_COEFF): EPL anchors at 0; weaker leagues are
      negative. Offset = _K_COEFF * (coeff - EPL_coeff).
    * **Concacaf leagues** (_CONCACAF_OFFSET): MLS anchors at 0; offsets are
      RELATIVE only — Concacaf and UEFA teams never meet, and match_lambdas
      uses strength differences, so these values are not comparable to the
      UEFA-derived offsets above.

    Concacaf leagues are checked first (within the prior path); if not found
    there the UEFA path is tried; unknown leagues return 0.0 rather than
    raising.
    """
    fitted = _load_fitted()
    if fitted is not None and league_id in fitted:
        return float(fitted[league_id])
    # Prior fallback
    if league_id in _CONCACAF_OFFSET:
        return _CONCACAF_OFFSET[league_id]
    if league_id not in _LEAGUE_COEFF:
        return 0.0
    return _K_COEFF * (_LEAGUE_COEFF[league_id] - _LEAGUE_COEFF[_REF_LEAGUE])


def club_strength(club: str) -> float:
    """Cross-league strength (ELO points) for an unmodeled club, or BASELINE."""
    return _CLUB_STRENGTH.get(club, BASELINE_STRENGTH)


# ── 2nd-tier → 1st-tier ELO offset ───────────────────────────────────────────
# Lazy-loaded from experiments/tier2_offsets.json (built by scripts.eval.tier_bridge).
# Falls back to static priors below when the file is absent or the key is missing.

_TIER2_OFFSETS: dict[str, float] | None = None
_TIER2_OFFSETS_LOADED: bool = False
_TIER2_JSON = Path(__file__).parent.parent / "experiments" / "tier2_offsets.json"

# Static priors: rough ELO gap between each 2nd-tier and 1st-tier league.
# These anchor the ridge penalty in tier_bridge and serve as permanent fallback.
_TIER2_PRIORS: dict[str, float] = {
    "championship_to_epl": -120.0,
    "bundesliga-2_to_bundesliga": -100.0,
    "serie-b_to_serie-a": -130.0,
}

# Maps tier-2 league ID → tier-1 league ID (used to construct the JSON key).
_TIER1_FOR: dict[str, str] = {
    "championship": "epl",
    "bundesliga-2": "bundesliga",
    "serie-b": "serie-a",
}


def _load_tier2() -> dict[str, float] | None:
    """Lazy-load experiments/tier2_offsets.json exactly once."""
    global _TIER2_OFFSETS, _TIER2_OFFSETS_LOADED
    if _TIER2_OFFSETS_LOADED:
        return _TIER2_OFFSETS
    _TIER2_OFFSETS_LOADED = True
    try:
        _TIER2_OFFSETS = json.loads(_TIER2_JSON.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        _TIER2_OFFSETS = None
    return _TIER2_OFFSETS


def tier2_offset(tier2_league_id: str) -> float:
    """ELO offset translating a tier-2 team's domestic ELO to the tier-1 scale.

    Returns the fitted offset from experiments/tier2_offsets.json when available,
    otherwise the static prior from _TIER2_PRIORS. Returns 0.0 for unknown pairs.
    """
    tier1_lid = _TIER1_FOR.get(tier2_league_id)
    if tier1_lid is None:
        return 0.0
    key = f"{tier2_league_id}_to_{tier1_lid}"
    fitted = _load_tier2()
    if fitted is not None and key in fitted:
        return float(fitted[key])
    return _TIER2_PRIORS.get(key, 0.0)
