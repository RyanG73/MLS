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
import logging
from pathlib import Path

_log = logging.getLogger(__name__)

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


# ELO points per UEFA-coefficient point.
#
# FITTED 2026-08-06/07 (was 3.0, described in its own comment as "the starting
# prior" for a calibration task that was never done). This one number sets how
# far apart the leagues sit on the published ladder, and it was too small by
# more than half:
#
#     fitted 4.04 +/- 0.33 on the 743 cross-league continental matches
#     z vs 3.0 = +3.2 · held-out Brier 0.5621 -> 0.5596 (-0.0025), 6/10 seeds
#
# REFITTED 2026-08-07 alongside the fresh coefficient capture. It first came out
# 4.72 against the old table; the captured table spans England-to-France 34.2
# points where the old one spanned 27, so the same physical gap needs a smaller
# multiplier. k and _LEAGUE_COEFF are one calibration in two pieces — refit k
# whenever the table is recaptured, and never edit one alone.
#
# The held-out margin is smaller than it was (-0.0025 against -0.0079) because
# the baseline itself got better: at k=3.0 the fresh coefficients already score
# 0.5621 where the old ones scored 0.5656. Most of what k was straining to
# correct was a wrong input table, not a wrong multiplier.
#
# What 3.0 did: the ENTIRE Belgian league sat 117 ELO below the Premier League —
# about the gap between an EPL title contender and a mid-table side — so any club
# that dominated a weak league landed in the world top ten. That is the general
# cause behind every "X is not a top ten team in Europe" report: PSV on
# 2026-08-05, then Club Brugge, Union SG and Galatasaray on 2026-08-07. It was
# never really about those leagues; the whole scale was compressed.
#
# Corroborated two ways beyond the fit itself. Per-league: at 3.0 the leagues
# drift off their own coefficient priors and at the fitted value they sit on it,
# mean |z| across 16 leagues falling to ~0.9 where a perfectly calibrated set
# gives ~0.8. Per-club: residuals ran from big-five elite UNDER-rated (Bayern
# +2.6, Real Madrid +2.0) to small-league clubs OVER-rated (Celtic -2.1,
# Galatasaray -1.3) — exactly the gradient a too-small multiplier produces.
#
# 4.0, not 4.04: the standard error is 0.33, so the third digit is noise.
_K_COEFF = 4.0

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
# PROVENANCE: FRESH CAPTURE 2026-08-07, five-year association coefficients as
# published for 2025-26. This replaces a mixed table in which only the big five
# and six C1 leagues had ever been captured (2026-06) and ten more were typed
# estimates added 2026-07-31 — the note this replaces asked for exactly this
# refresh "at the next annual review", and by 2026-08-07 the estimates were
# carrying the whole cross-league scale through _K_COEFF.
#
# The refresh is not cosmetic. Four of the estimates were wrong by enough to
# move clubs tens of places, and every correction lands in the direction the
# continental residuals had independently been pointing:
#
#   league               was    now     residual measured before the capture
#   eredivisie          61.0   51.6     z = -2.8 (over-rated)  <- the largest
#   austria-bundesliga  33.0   25.3     z = -0.9 (over-rated)
#   scottish-prem       32.0   25.1     z = -0.3 (over-rated)
#   swiss-super-league  33.0   29.1     z = +0.2
#   poland-ekstraklasa  32.0   43.5     z = +1.9 (UNDER-rated) <- wrong way up
#   serie-a             76.0   87.7     Italy was below Spain here; it is not
#
# The Eredivisie is the headline. It carried a hand-written -206 override that
# existed purely because its coefficient said 61 while its results said far
# less; the true value is 51.6, which is most of that gap. A wrong input had
# been patched at the output for a month.
#
# The scale also changed: England-to-France spans 34.2 points here against 27
# before, so _K_COEFF is refitted alongside this table — the two are meaningless
# apart. Do not edit one without the other.
_LEAGUE_COEFF: dict[str, float] = {
    "epl": 101.852, "serie-a": 87.660, "la-liga": 82.368,
    "bundesliga": 80.116, "ligue-1": 67.653,
    "primeira": 63.650, "belgian-pro": 57.850, "eredivisie": 51.562,
    "super-lig": 47.575, "poland-ekstraklasa": 43.525, "greek-super": 41.312,
    "denmark-superliga": 36.181, "norway-eliteserien": 34.212,
    "swiss-super-league": 29.075, "sweden-allsvenskan": 25.625,
    "austria-bundesliga": 25.250, "scottish-prem": 25.050,
    "romania-liga1": 24.500, "ireland-premier": 16.093,
    # Finland is outside the published top 35 and keeps an estimate, on the new
    # scale — the only value in this table that is not a capture.
    "finland-veikkausliiga": 12.500,
    # russia-premier is deliberately NOT here — see _russia_coeff().
}

# Coefficient assigned to a modeled UEFA league that is not in the table above.
# Deliberately low: an unlisted UEFA top flight is, by construction, one obscure
# enough that nobody has entered its coefficient, which is strong evidence it is
# not a strong league. The old behaviour — falling through to 0.0, i.e. the EPL's
# own offset — was the exact opposite inference.
# 12.0 on the 2026-08-07 scale: the published table runs to ~13.5 at 35th, so an
# association absent from it sits just below that. Was 15.0 on the old scale.
_UEFA_UNLISTED_COEFF = 12.0

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
# 39.0 on the 2026-08-07 coefficient scale (was 36.0 on the pre-refresh one, and
# the whole table moved). The decay then lands 2026 at ~20, against the 17.3
# UEFA still publishes for a country that has played nobody since 2022 — close
# enough that the mechanism is behaving, and deliberately not pinned to the
# published figure, which is itself a frozen number rather than a measurement.
_RUSSIA_LAST_VALID_COEFF = 39.0     # accrued through 2021-22, the last full season
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
#
# eredivisie, 2026-08-06: the SAME failure as Primeira, found the same way and
# fixed with a measurement instead of an anchor. After the UEFA match constants
# were recalibrated (see cross_league._CONF_CONST), every league's coefficient
# prior was tested one at a time against its own continental record by profile
# likelihood — all others held at their priors, so the question is only "does
# THIS league's record reject THIS league's prior". Seventeen leagues were
# inside noise of their prior. The Eredivisie was not:
#
#   n=101 appearances · observed 1.12 points per appearance · expected 1.51
#   MLE offset -197 +/- 30  vs prior -99   ->  z = -3.3
#
# -197 is that MLE. It is the reason PSV Eindhoven ranked 6th in the world off
# a 1804 domestic ELO: the Eredivisie's internal ratings are inflated by a
# top-heavy league, and a -99 offset did not remove enough of it. Note that
# Ligue 1, the other league reported as too high on 2026-08-06, came out at
# z=+1.7 — its -81 prior is FINE and needed no override; what had put Lens 10th
# was the fitted offset (-18) that the mis-calibrated constants demanded.
#
# Superseded automatically if this league gets a bridge-regression fit that
# passes the robustness gate into league_offsets.json.
# BOTH ENTRIES REMOVED 2026-08-07. They were the same bug wearing two names.
#
# Primeira was added 2026-07-13 because "the generic _K_COEFF static fallback
# gave it only a -102 offset, which under-penalizes its inflated domestic ELO".
# Eredivisie was added 2026-08-06 for the identical symptom, measured the same
# way. Neither league was the problem: _K_COEFF was 3.0, so EVERY league below
# the big five was under-penalised, and these two were simply the first to be
# noticed. With _K_COEFF fitted to 4.7 the coefficient scale reaches them on its
# own — Primeira's own continental record now sits 0.7 sigma from its
# coefficient-derived prior, against 1.1 before, and it no longer needs a
# hand-placed number to look right.
#
# Eredivisie is the one league still drifting (z = -2.9 at k = 4.7). It is left
# to the bridge regression, which has 101 matches of evidence for it and a gate
# that decides whether to trust them. A hand-written override here would
# pre-empt that gate with a number nobody re-measures.
#
# The bar for an entry here: THIS league's own continental record has to reject
# THIS league's coefficient prior, repeatedly and independently. Looking wrong is
# not enough — if several leagues need an entry at once, the scale is wrong, and
# that is the mistake this dict made twice before.
#
# EMPTY, and the way it emptied is the point.
#
# The Eredivisie entry (-206, added 2026-08-06) survived less than a day. It was
# measured honestly — profile-likelihood MLE -244 +/- 30, z = -2.9, corroborated
# by a league-residual check over 101 appearances — and it was still a patch on
# the wrong layer. Its coefficient said 61 when the published value is 51.6. The
# league was never anomalous; the input was wrong, and every "measurement" of
# the anomaly was really a measurement of that error.
#
# With the 2026-08-07 capture the Eredivisie sits 1.2 sigma from its own
# coefficient prior and needs nothing at all. Primeira, the other long-standing
# override, went the same way for the same reason.
#
# So the bar for adding an entry here is higher than "I measured a deviation".
# Check the INPUT first: is this league's coefficient current, and is _K_COEFF
# fitted against the table it belongs to? Two overrides in this repo's history,
# both hand-measured, both correct arithmetic, and both symptoms of a stale
# coefficient table. An entry is only justified for a league whose published
# coefficient is right and whose results still disagree.
_MANUAL_LEAGUE_OFFSET: dict[str, float] = {}

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

    # A hand-measured override outranks the fitted file. This used to be the
    # other way round, on the reasoning that "a real bridge-regression fit
    # supersedes a hand-calibrated value" — which was true when the file only
    # ever held fits. It no longer does: when `league_bridge` rejects a fit at
    # its robustness gate it writes the PRIORS to the same file, so an override
    # was being shadowed by a copy of the very prior it existed to correct.
    #
    # Found the hard way on 2026-08-07 — the Eredivisie override was added,
    # payloads and power.js were rebuilt, and PSV Eindhoven did not move an ELO
    # point. Nothing warned; the number was simply ignored. An entry in
    # _MANUAL_LEAGUE_OFFSET is a deliberate, documented measurement and the file
    # is regenerated by a script, so the human decision wins and a genuine
    # future fit supersedes it by DELETING the entry (as Primeira's was).
    if league_id in _MANUAL_LEAGUE_OFFSET:
        manual = _MANUAL_LEAGUE_OFFSET[league_id] + shift
        fitted = _load_fitted() or {}
        if league_id in fitted and abs(float(fitted[league_id]) + shift - manual) > 1.0:
            _log.info(
                "coefficients: %s uses the manual override %.1f, not the %.1f in "
                "experiments/league_offsets.json (delete the override to adopt the file)",
                league_id, manual, float(fitted[league_id]) + shift)
        return manual

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


# ── cross-tier DISPERSION ─────────────────────────────────────────────────────
# A tier bridge has always been a pure shift, which assumes a second tier's
# rating gaps mean the same thing as its parent's. Measured on the domestic
# matches of both leagues, they do not.
#
# The test is a logistic refit of match result on the league's own pre-match
# rating gap: a slope of 1.0 means the league's ELO gaps predict its own results
# honestly, below 1.0 means they overstate the favourite. Top flights average
# 0.91; second tiers average 0.70. So a club 200 points clear of the Championship
# is NOT 200 points clear on the Premier League's scale, and translating it with
# a shift alone carries the whole exaggeration across the boundary. That is the
# mechanism behind relegated and promoted clubs arriving over-rated.
#
# Ratios below are child_slope / parent_slope, each measured 2026-08-07 over
# 3,600-6,600 domestic matches per league:
#
#   championship / epl          0.782 +/- 0.055     league-one / championship  1.026 +/- 0.079
#   bundesliga-2 / bundesliga   0.723 +/- 0.074     league-two / league-one    0.823 +/- 0.071
#   ligue-2      / ligue-1      0.802 +/- 0.072     serie-b    / serie-a       0.872 +/- 0.067
#   segunda      / la-liga      0.875 +/- 0.062
#
# league-one/championship is 1.03 — the English third tier is no more dispersed
# than the second. The compression is at the EPL boundary, not at every step, so
# it is stored per hop rather than assumed uniform.
_TIER_DISPERSION: dict[str, float] = {
    "championship": 0.782,
    "bundesliga-2": 0.723,
    "serie-b": 0.872,
    "segunda": 0.875,
    "ligue-2": 0.802,
    "league-one": 1.026,
    "league-two": 0.823,
}


def tier_dispersion(league_id: str) -> float:
    """Multiplier on a club's deviation from its LEAGUE MEAN, onto the top-flight
    scale. 1.0 for a top flight; composes along the promotion chain, so League
    Two is translated through League One and the Championship.
    """
    factor, current, seen = 1.0, league_id, set()
    while current in _TIER1_FOR and current not in seen:
        seen.add(current)
        factor *= _TIER_DISPERSION.get(current, 1.0)
        current = _TIER1_FOR[current]
    return factor


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


# ── per-club continental adjustment ──────────────────────────────────────────
# Fitted by scripts/eval/club_bridge.py. A league offset is anchored on the UEFA
# country coefficient, which measures an association's DEPTH — how many of its
# clubs qualify and how far they collectively go — and is therefore not a claim
# about any single club. Applied flat it under-rates the elite of a top-heavy
# league and over-rates the elite of a deep-but-not-elite one.
#
# This layer speaks only for clubs that have actually played in Europe, using
# their own results, shrunk by how many they have. A club with no continental
# history is untouched, which is correct: for that club the league really is the
# only evidence there is.
_CLUB_CONT: dict[str, float] | None = None
_CLUB_CONT_LOADED: bool = False
_CLUB_CONT_JSON = Path(__file__).parent.parent / "experiments" / "club_continental_offsets.json"


def _load_club_cont() -> dict[str, float]:
    global _CLUB_CONT, _CLUB_CONT_LOADED
    if _CLUB_CONT_LOADED:
        return _CLUB_CONT or {}
    _CLUB_CONT_LOADED = True
    try:
        blob = json.loads(_CLUB_CONT_JSON.read_text())
        # `offsets` is empty unless the fit beat the league-only ladder on
        # held-out data, so a rejected fit degrades to no adjustment at all.
        _CLUB_CONT = blob.get("offsets") or {}
    except (FileNotFoundError, json.JSONDecodeError, AttributeError):
        _CLUB_CONT = {}
    return _CLUB_CONT


def club_continental_offset(league_id: str, team: str) -> float:
    """ELO adjustment from this club's OWN European record. 0.0 if it has none."""
    return float(_load_club_cont().get(f"{league_id}|{team}", 0.0))


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
