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


# ── inter-confederation shift (2026-07-26) ───────────────────────────────────
# league_offsets.json is fitted INSIDE each confederation against its own anchor
# (UEFA→epl, CONMEBOL→brazil-serie-a, Concacaf→mls, AFC→japan-j1), every anchor
# pinned at 0.0 — so MLS and EPL both read 0.0 without that meaning they are
# equal. This file adds one whole-scale shift per confederation, fitted on the
# FIFA Club World Cup (the only competition where confederations actually meet)
# by scripts/eval/interconf_calibrate.py, which puts all four scales on one
# ladder.
#
# It cannot regress a within-confederation projection: match_lambdas works on
# the strength DIFFERENCE, so a constant added to both sides of a domestic or
# same-confederation continental tie cancels exactly. The only predictions that
# move are the cross-confederation ones that were previously unfounded.
_CONF_SHIFT: dict[str, float] | None = None
_CONF_SHIFT_LOADED: bool = False
_CONF_JSON = Path(__file__).parent.parent / "experiments" / "confederation_offsets.json"

# league_id → confederation, read from the published registry so a new league is
# covered without editing this module.
_LEAGUE_CONF: dict[str, str] | None = None
_REGISTRY_JS = Path(__file__).parent.parent / "webapp" / "leagues.js"


def _load_conf_shift() -> dict[str, float]:
    global _CONF_SHIFT, _CONF_SHIFT_LOADED
    if _CONF_SHIFT_LOADED:
        return _CONF_SHIFT or {}
    _CONF_SHIFT_LOADED = True
    try:
        _CONF_SHIFT = json.loads(_CONF_JSON.read_text()).get("shifts") or {}
    except (FileNotFoundError, json.JSONDecodeError, AttributeError):
        _CONF_SHIFT = {}
    return _CONF_SHIFT


def _league_conf(league_id: str) -> str | None:
    global _LEAGUE_CONF
    if _LEAGUE_CONF is None:
        try:
            txt = _REGISTRY_JS.read_text(encoding="utf-8")
            rows = json.loads(txt.split("=", 1)[1].rstrip().rstrip(";"))
            _LEAGUE_CONF = {r["id"]: r.get("confederation") for r in rows}
        except Exception:          # noqa: BLE001 — registry absent in some test envs
            _LEAGUE_CONF = {}
    return _LEAGUE_CONF.get(league_id)


def confederation_shift(league_id: str) -> float:
    """Whole-scale shift putting `league_id`'s confederation on the UEFA ladder."""
    conf = _league_conf(league_id)
    return float(_load_conf_shift().get(conf, 0.0)) if conf else 0.0


# ELO points per UEFA-coefficient point (calibrated in validate_continental.py,
# a later task; this is the starting prior).
_K_COEFF = 3.0

# Strength (ELO points) assigned to an unknown/unlisted club — conservative,
# roughly a mid-table side in a weak European league.
BASELINE_STRENGTH = 1450.0

# Reference league (anchors the offset scale at 0).
_REF_LEAGUE = "epl"

# UEFA 5-year country coefficients (2025-26). Keyed by our internal league ids.
#
# ── 2026-07-31: this table is load-bearing in a way that is easy to miss. ──
# league_bridge's ridge pulls each league toward its prior, and its own docstring
# notes that "a league with few matches contributes ~nothing to the NLL and the
# ridge holds it at its prior". A league ABSENT from this table priors at 0.0 —
# which on an EPL-anchored scale does not mean "unknown", it means "exactly as
# strong as the Premier League". Ten modeled UEFA top flights were absent, so the
# ridge faithfully held Norway, Russia, Finland, Ireland, Denmark, Sweden,
# Austria, Romania, Switzerland and Poland within 25 ELO of the EPL. The result
# was a global ladder with Bodo/Glimt 4th, Zenit 5th, KuPS (Finland) 9th and IK
# Sirius (Sweden) 17th — all ahead of Real Madrid, PSG and Manchester United.
# The split was perfect: every league IN this table fitted to a sane negative
# offset, every league absent fitted to ~0.
#
# The same failure hit Primeira in 2026-07-13 (see _MANUAL_LEAGUE_OFFSET below).
# Twice is a pattern, so the fallback in league_offset() no longer returns 0.0
# for an unlisted UEFA league — see _UEFA_UNLISTED_COEFF.
#
# PROVENANCE: the big-5 + C1 values were captured 2026-06 from the UEFA 5-year
# country ranking. The values added 2026-07-31 are best-available ESTIMATES on
# that same scale, not a fresh capture — they should be refreshed from
# https://www.uefa.com/nationalassociations/uefarankings/country/ at the next
# annual review. What the ranking is actually sensitive to is their ORDER and
# rough spacing, both of which are well established; a few points either way
# moves a club a place or two, not thirty.
_LEAGUE_COEFF: dict[str, float] = {
    "epl": 94.0, "la-liga": 79.0, "serie-a": 76.0, "bundesliga": 74.0,
    "ligue-1": 67.0,
    # C1 leagues (2026-07): same coefficient scale. Used by the fallback path
    # only — experiments/league_offsets.json has no bridge fit for these yet.
    "eredivisie": 61.0, "primeira": 60.0, "belgian-pro": 55.0,
    "super-lig": 45.0, "greek-super": 38.0, "scottish-prem": 32.0,
    # Added 2026-07-31 — the ten modeled top flights that were priced as EPL
    # equivalents. Estimates on the scale above; see PROVENANCE.
    "norway-eliteserien": 35.0, "denmark-superliga": 34.0,
    "austria-bundesliga": 33.0, "swiss-super-league": 33.0,
    "poland-ekstraklasa": 32.0, "sweden-allsvenskan": 25.0,
    "romania-liga1": 23.0, "ireland-premier": 17.0,
    "finland-veikkausliiga": 13.0,
    # russia-premier is deliberately NOT here — see _russia_coeff().
}

# Coefficient assigned to a modeled UEFA league that is not in the table above.
# Deliberately low: an unlisted UEFA top flight is, by construction, one obscure
# enough that nobody has entered its coefficient, which is strong evidence it is
# not a strong league. The old behaviour — falling through to 0.0, i.e. the EPL's
# own offset — was the exact opposite inference.
_UEFA_UNLISTED_COEFF = 15.0

# ── Russia: a league with no external evidence, by political fact ─────────────
# Russian clubs have been suspended from UEFA since February 2022, so no
# coefficient accrues and the bridge has no match to fit on — russia-premier is
# structurally uncalibratable by the normal route, which is exactly why it sat
# at the 0.0 prior and put Zenit 5th in the world.
#
# Two things drift in the SAME direction while the suspension lasts, and the
# estimate has to answer both:
#   1. Real decline — no European football, and the foreign players who set the
#      league's ceiling largely left.
#   2. Measurement drift — a closed league's ELO is self-referential. Beating
#      the same opponents re-inflates the whole distribution with no external
#      check, so the domestic numbers climb whether or not the clubs improve.
# So the estimate decays from the last coefficient Russia actually earned toward
# the unlisted-league floor, one step per season of missing evidence. It never
# falls below the floor: absent evidence should end at "we do not know", not at
# an ever-more-confident claim of weakness.
#
# This is a documented estimate, not a measurement, and the league page reports
# it as such via global_elo_quality() -> "suspended_estimate".
_RUSSIA_LAST_VALID_COEFF = 36.0     # accrued through 2021-22, the last full season
_RUSSIA_SUSPENDED_FROM = 2022
_RUSSIA_DECAY_PER_SEASON = 0.85


def _russia_coeff(today_year: int | None = None) -> float:
    """Decayed coefficient for the suspended Russian top flight."""
    from datetime import date
    year = today_year if today_year is not None else date.today().year
    seasons = max(0, year - _RUSSIA_SUSPENDED_FROM)
    span = _RUSSIA_LAST_VALID_COEFF - _UEFA_UNLISTED_COEFF
    return _UEFA_UNLISTED_COEFF + span * (_RUSSIA_DECAY_PER_SEASON ** seasons)

# Concacaf-internal league offsets (ELO points). These are RELATIVE only — Concacaf
# teams never meet UEFA teams and match_lambdas uses strength differences, so the
# absolute anchor is irrelevant. MLS is the reference (0); Liga MX carries a modest
# edge reflecting recent near-parity in Concacaf Champions Cup play.
_CONCACAF_OFFSET: dict[str, float] = {
    "mls": 0.0,
    "liga-mx": 30.0,
}

# Hand-calibrated overrides for leagues not yet covered by the automated bridge fit
# (experiments/league_offsets.json), anchored to _CLUB_STRENGTH's cross-league
# estimates for that league's actual UCL-regular clubs. 2026-07-13 power-rankings
# bug: the generic _K_COEFF static fallback below gave Primeira only a -102 offset,
# which under-penalizes its inflated domestic ELO — Benfica/Porto/Sporting CP were
# outranking Real Madrid/Bayern Munich. _CLUB_STRENGTH already has a better answer
# for these exact clubs (Benfica 1635, Porto 1620, Sporting CP 1615); this offset is
# the mean gap between those anchors and the clubs' current webapp/data/primeira.js
# domestic ELO (1822/1811/1821) — i.e. reuses calibration the codebase already
# trusted elsewhere instead of inventing a new number. Superseded automatically if
# this league ever gets a real bridge-regression fit into league_offsets.json.
_MANUAL_LEAGUE_OFFSET: dict[str, float] = {
    "primeira": -195.0,
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
    # The confederation shift is added to EVERY path below, so the within-
    # confederation number each path produces keeps its meaning and only the
    # cross-confederation comparison changes (see _CONF_SHIFT).
    shift = confederation_shift(league_id)
    fitted = _load_fitted()
    if fitted is not None and league_id in fitted:
        return float(fitted[league_id]) + shift
    return static_league_offset(league_id)


def static_league_offset(league_id: str) -> float:
    """The EXTERNAL prior only — never the fitted file.

    league_bridge regularises its fit toward a prior, and it must be this one.
    Using league_offset() there instead created a fixed point: that function
    returns experiments/league_offsets.json when it exists, so each fit was
    ridged toward its own previous output. The very first fit ran when ten UEFA
    leagues genuinely priored at 0.0, and every run since re-anchored on that,
    drifting a few ELO at a time and never escaping. Editing the coefficient
    table had no effect at all until the two were separated. (2026-07-31)
    """
    shift = confederation_shift(league_id)
    if league_id in _CONCACAF_OFFSET:
        return _CONCACAF_OFFSET[league_id] + shift
    if league_id in _MANUAL_LEAGUE_OFFSET:
        return _MANUAL_LEAGUE_OFFSET[league_id] + shift
    coeff = uefa_coeff(league_id)
    if coeff is None:
        return 0.0 + shift
    return _K_COEFF * (coeff - _LEAGUE_COEFF[_REF_LEAGUE]) + shift


def uefa_coeff(league_id: str) -> float | None:
    """Country coefficient for a UEFA league, or None outside UEFA.

    A UEFA top flight ALWAYS gets a number here. Returning None for an unlisted
    one used to send league_offset() down a `return 0.0` path, and 0.0 on an
    EPL-anchored scale is a positive claim of Premier League strength rather
    than an absence of one — the bug that put four Nordic clubs and two Russian
    ones in the world top 20. Non-UEFA leagues still return None, because their
    confederations are anchored separately and this scale does not apply.
    """
    if league_id in _LEAGUE_COEFF:
        return _LEAGUE_COEFF[league_id]
    if league_id == "russia-premier":
        return _russia_coeff()
    if _league_conf(league_id) == "UEFA" and league_id not in _TIER1_FOR:
        return _UEFA_UNLISTED_COEFF
    return None


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
    "segunda_to_la-liga": -120.0,
    "ligue-2_to_ligue-1": -120.0,
    # English third/fourth-tier chain (2026-07-06, static priors only — no
    # bridge fit yet). Same magnitude as the fitted championship↔EPL gap;
    # without these a League One champion carried its raw domestic ELO into
    # the Championship (Lincoln seeded at 1722 → 94% promotion, absurd).
    "league-one_to_championship": -120.0,
    "league-two_to_league-one": -120.0,
}

# Maps tier-2 league ID → tier-1 league ID (used to construct the JSON key).
_TIER1_FOR: dict[str, str] = {
    "championship": "epl",
    "bundesliga-2": "bundesliga",
    "serie-b": "serie-a",
    "segunda": "la-liga",
    "ligue-2": "ligue-1",
    "league-one": "championship",
    "league-two": "league-one",
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


def global_elo_offset(league_id: str) -> float:
    """Additive offset from a league's domestic ELO onto the global EPL scale.

    ``league_offset`` already includes the fitted within-confederation bridge
    and the Club World Cup confederation shift for top flights. Lower divisions
    need one extra step: their tier bridge first translates domestic ELO onto
    the parent league's scale. English tiers compose recursively, so League Two
    is translated through League One and the Championship before reaching EPL.

    Keeping this composition here gives payload builders, team pages and the
    power rankings one canonical published-rating contract without changing
    the domestic ELO values used by league simulations.
    """
    offset = 0.0
    current = league_id
    seen: set[str] = set()
    while current in _TIER1_FOR and current not in seen:
        seen.add(current)
        offset += tier2_offset(current)
        current = _TIER1_FOR[current]
    return offset + league_offset(current)


def global_elo_quality(league_id: str) -> str:
    """Describe the strongest bridge evidence behind ``global_elo_offset``."""
    if league_id in _TIER1_FOR:
        return "tier_bridge"
    # Checked BEFORE "fitted": Russia has played no UEFA match since 2022, so a
    # fitted entry for it is the ridge echoing the prior back, not evidence.
    # Calling that "fitted" would overstate what stands behind the number.
    if league_id == "russia-premier":
        return "suspended_estimate"
    fitted = _load_fitted() or {}
    if league_id in fitted:
        return "fitted"
    if league_id in _CONCACAF_OFFSET:
        return "confederation_prior"
    if league_id in _MANUAL_LEAGUE_OFFSET or league_id in _LEAGUE_COEFF:
        return "calibrated_prior"
    if _league_conf(league_id) == "UEFA":
        return "estimated_prior"
    if _league_conf(league_id):
        return "confederation_anchor"
    return "unanchored"


# Reverse-direction static priors: translate a RELEGATED team's tier-1 ELO down to the
# tier-2 scale. Positive — a dropped top-flight side is strong in the second tier.
_TIER1_PRIORS: dict[str, float] = {
    "epl_to_championship": 120.0,
    "bundesliga_to_bundesliga-2": 100.0,
    "serie-a_to_serie-b": 130.0,
    "la-liga_to_segunda": 120.0,
    "ligue-1_to_ligue-2": 120.0,
    "championship_to_league-one": 120.0,
    "league-one_to_league-two": 120.0,
}


def tier1_offset(tier2_league_id: str) -> float:
    """ELO offset translating a RELEGATED team's tier-1 ELO down to the tier-2 scale.

    The reverse of tier2_offset: a team dropped from the top flight is strong in the
    second tier, so the offset is positive. Returns the fitted reverse offset from
    experiments/tier2_offsets.json when available, else the static prior. 0.0 for unknown.
    """
    tier1_lid = _TIER1_FOR.get(tier2_league_id)
    if tier1_lid is None:
        return 0.0
    key = f"{tier1_lid}_to_{tier2_league_id}"
    fitted = _load_tier2()
    if fitted is not None and key in fitted:
        return float(fitted[key])
    return _TIER1_PRIORS.get(key, 0.0)
