#!/usr/bin/env python3
"""
Multi-league dashboard data builder — single-table (European) leagues.

Payload contract: all writes go through write_js_payload (allow_nan=False).

Produces webapp/data/<league>.js with the SAME payload schema the MLS build emits
(scripts/build_dashboard_data.py), but with league-table semantics instead of
MLS's conferences + playoff bracket + cup:

  - standings outcomes are Title / Top-4 (UCL) / Relegation, not playoff/shield/spoon
  - the season Monte-Carlo simulates remaining fixtures into a SINGLE final table
    (no bracket), via the same Dixon-Coles pairing probabilities
  - an `outlook` config block tells the webapp which favorite-cards + table markers
    to render (WS4 reads this; MLS keeps its hard-coded conference view)

Single data source: the Understat adapter (matches + xG + fixtures all come from
one place — upcoming fixtures are the is_result=False rows). Team crests + colors
are read from the ESPN coming-soon stub already scaffolded by
scripts/fetch_league_teams.py. The model + features are the shared, league-
agnostic pipeline (research_model + scripts/eval/league_features), unchanged.

Usage:
    python scripts/build_league_data.py --league epl
    python scripts/build_league_data.py --league la-liga --season 2025 --sims 20000
"""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd

from data_pipeline.understat import canonical_frame, espn_name, _COLS as _COLS_INTL
from data_pipeline.football_data import match_results
from data_pipeline.football_data_intl import (
    match_results as match_results_intl,
    NO_ESPN_SCHEDULE as fdi_no_espn,
)
from data_pipeline.espn_soccer import liga_mx_frame, season_label as liga_mx_label
from data_pipeline.espn_fixtures import european_fixtures
from data_pipeline.asa_frame import asa_canonical_frame
from models.research_model import (
    bag_proba, blend, calibrate_temperature, dc_predict_batch, fit_capped_blend,
    fit_dc, fit_temperature_scalar, fit_xgb,
)
import models.research_model as rm
from scripts.eval.elo import compute_elo
from scripts.eval.league_features import LEAGUE_FEAT_BASE, build_league_features
from scripts.eval.season_state import season_state, IN_PROGRESS, PRESEASON, CONCLUDED
from scripts.eval.sim_variance import preseason_sigma_for_source, perturb_probs
from scripts.eval.season_format import FORMATS, format_classification, regular_phase_mask
from scripts.postgame_win_expectancy import compute_we
from scripts.eval.upcoming_features import latest_team_features
from scripts.payload_utils import write_js_payload, health_feature_stats, outcome_skill_block
from data_pipeline import coefficients as co

# B9: same canonical family grouping as build_dashboard_data.py (kept as an
# independent copy per-file, not a shared module — two ~10-line dicts don't
# warrant one). European pipelines have no gk_z / avail_share columns at all
# (not a per-league gap — the feature pipeline never computes them), so those
# families render as an explicit null block for every European league via the
# same "suffix missing from feat_cols/frame -> None" default-fill mechanism
# used for goals-only leagues' xG columns.
FEATURE_FAMILIES = {
    "ELO":                       ["elo"],
    "xG For (rolling windows)":  ["xg_roll_3", "xg_roll_5", "xg_roll_10", "xg_roll_15"],
    "xG Against (rolling windows)": ["xga_roll_3", "xga_roll_5", "xga_roll_10", "xga_roll_15"],
    "Form (rolling windows)":   ["form_3", "form_5", "form_10", "form_15"],
    "Goalkeeper":                ["gk_z"],
    "Availability":              ["avail_share"],
}


def _clean(v):
    """NaN/None -> None, else round to 3dp float. Never emits NaN (allow_nan=False)."""
    if v is None:
        return None
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    return round(float(v), 3)


def build_team_inputs_full(df: pd.DataFrame, feat_cols: list[str],
                           tids: list, tname) -> dict:
    """{team_name: {family: {suffix: value_or_None}}} — see build_dashboard_data.py's
    twin for the full contract. `tname` is this builder's team-key -> display-name fn."""
    raw = latest_team_features(df, feat_cols)
    out = {}
    for t in tids:
        team_raw = raw.get(t, {})
        out[tname(t)] = {
            fam: {suf: _clean(team_raw.get(suf)) for suf in sufs}
            for fam, sufs in FEATURE_FAMILIES.items()
        }
    return out


def build_squad_value_league(lid: str, team_names: set[str]) -> dict | None:
    """B9 squad-value panel for non-MLS leagues (A9). Reads the freshest
    `data/transfermarkt_squad_values_<TM_CODE>_<season>_mapped.csv` for this
    league and keys rows on `canon_team_name` (already resolved to this
    builder's team_inputs naming by import_transfermarkt.canonical_team_name).

    Team-level aggregates ONLY — per docs/data-sources.md, player-level TM
    market values are local-only (redistribution uncertain); the MLS builder's
    player table is deliberately NOT mirrored here.

    Best-effort like build_dashboard_data.build_squad_value_mls: any read/parse
    failure returns None (the panel's "not available" state) — stale or missing
    squad-value data must never break a league build.
    """
    try:
        from scripts.import_transfermarkt import TM_CODE_TO_LEAGUE_ID
        codes = [c for c, l in TM_CODE_TO_LEAGUE_ID.items() if l == lid]
        if not codes:
            return None
        files = sorted(Path("data").glob(
            f"transfermarkt_squad_values_{codes[0]}_*_mapped.csv"))
        if not files:
            return None
        mapped = pd.read_csv(files[-1])  # lexicographic == chronological (…_<season>_)
        mapped = mapped[mapped["canon_team_name"].fillna("") != ""]
        mapped = mapped.dropna(subset=["squad_value_eur"])
        mapped = mapped[mapped["squad_value_eur"] > 0]
        if mapped.empty:
            return None
        mapped = mapped.sort_values("squad_value_eur", ascending=False).reset_index(drop=True)
        n_teams = len(mapped)
        league_mean_age = float(mapped["value_wtd_age"].mean()) \
            if "value_wtd_age" in mapped else None
        as_of = str(mapped["observed_at"].iloc[0])[:10] \
            if "observed_at" in mapped.columns else None
        out = {}
        for i, row in mapped.iterrows():
            name = row["canon_team_name"]
            if name not in team_names:
                continue  # e.g. relegated out since the snapshot season
            rank = i + 1
            pct = (n_teams - rank) / (n_teams - 1) * 100 if n_teams > 1 else 100.0
            out[name] = {
                "available": True,
                "squad_value_eur": _clean(row.get("squad_value_eur")),
                "league_rank": int(rank),
                "n_teams": int(n_teams),
                "percentile": round(pct, 1),
                "value_wtd_age": _clean(row.get("value_wtd_age")),
                "league_avg_value_wtd_age": _clean(league_mean_age),
                "att_value_pct": _clean(row.get("att_value_pct")),
                "mid_value_pct": _clean(row.get("mid_value_pct")),
                "def_value_pct": _clean(row.get("def_value_pct")),
                "gk_value_pct":  _clean(row.get("gk_value_pct")),
                "tilt": _clean(row.get("tilt")),
                "dp_value_share": _clean(row.get("dp_value_share")),
                "n_players": int(row["n_players"]) if pd.notna(row.get("n_players")) else None,
                "coverage": str(row.get("coverage_confidence") or "full"),
                "as_of": as_of,
            }
        return out or None
    except Exception as e:
        print(f"[{lid}] warn: squad-value panel unavailable ({e})")
        return None


# ── tier-2 promoted-team seeding ──────────────────────────────────────────────
# Maps top-flight league ID → its feeder tier-2 league ID.
_TIER2_FOR: dict[str, str] = {
    "epl":        "championship",
    "bundesliga": "bundesliga-2",
    "serie-a":    "serie-b",
    "la-liga":    "segunda",
    "ligue-1":    "ligue-2",
    # English chain continues: promotees INTO the Championship/League One come
    # from a covered lower tier too (found 2026-07-06 when the FD preseason
    # flip first exercised these paths — Lincoln/Bolton had real League One
    # ELO but were seeded flat). The dict-inverse below chains the relegation
    # direction for free (league-two ← league-one ← championship).
    "championship": "league-one",
    "league-one":   "league-two",
    # Tier-1 expansion (2026-07-10): completes the English pyramid 1→5.
    # No fitted offset exists yet for this pair — coefficients.tier2_offset/
    # tier1_offset fall back to their 0.0 "unknown pair" default (a safe,
    # functioning default; precision improves once enough movers accrue to
    # fit experiments/tier2_offsets.json).
    "league-two":   "national-league",
    # Scottish pyramid (2026-07-11): SC0→SC1→SC2→SC3. No fitted offsets yet;
    # coefficients.tier2_offset/tier1_offset fall back to the 0.0 default until
    # movers accrue (same posture as the England league-two→national-league hop).
    "scottish-prem":       "scottish-champ",
    "scottish-champ":      "scottish-league-one",
    "scottish-league-one": "scottish-league-two",
}
# Inverse: tier-2 league ID → its top-flight. Used to seed RELEGATED teams when building a
# second-tier league. Named distinctly from coefficients._TIER1_FOR to avoid confusion.
_TIER1_FOR_BUILD: dict[str, str] = {t2: t1 for t1, t2 in _TIER2_FOR.items()}

# ESPN/Understat team name → football-data short name for common promoted teams.
_FD_TEAM_ALIASES: dict[str, str] = {
    "Sheffield United":        "Sheff Utd",
    "Nottingham Forest":       "Nott'm Forest",
    "Queens Park Rangers":     "QPR",
    "West Bromwich Albion":    "West Brom",
    "Leicester City":          "Leicester",
    "Wolverhampton Wanderers": "Wolves",
    "Brighton & Hove Albion":  "Brighton",
    "AFC Bournemouth":         "Bournemouth",
    "Leeds United":            "Leeds",
    "Ipswich Town":            "Ipswich",
    "Luton Town":              "Luton",
    "Huddersfield Town":       "Huddersfield",
    "Swansea City":            "Swansea",
    "Coventry City":           "Coventry",
    "Watford":                 "Watford",
    "Brentford":               "Brentford",
    # ESPN full names for sides relegated OUT of the EPL (the FD tier-1 ELO
    # map abbreviates) — West Ham was seeded flat without this (2026-07-06).
    "West Ham United":         "West Ham",
    "Tottenham Hotspur":       "Tottenham",
    "Manchester United":       "Man United",
    "Manchester City":         "Man City",
    "Newcastle United":        "Newcastle",
}

_TIER2_ELO_CACHE: dict[str, dict[str, float]] = {}
_TIER_SERIES_CACHE: dict[str, dict[str, list]] = {}


def _tier_elo_series(lid: str) -> dict[str, list]:
    """Per-team dated pre-match ELO series for a football-data league:
    {fd_team_name: [(Timestamp, elo), ...]}. {} when the frame can't load.

    R2 display fix (2026-07-09): team-page ELO charts froze while a club was
    in another division ("the Hull City jump") — these series let the current
    league's chart stitch the club's seasons in neighboring tiers.
    """
    if lid in _TIER_SERIES_CACHE:
        return _TIER_SERIES_CACHE[lid]
    out: dict[str, list] = {}
    try:
        df = match_results(lid).sort_values("date")
        df = df.dropna(subset=["home_goals", "away_goals"])
        if not df.empty:
            edf, _ = compute_elo(df, K=25, home_adv=80, regress=0.40,
                                 club_prior_beta=0.75, return_ratings=True)
            long = pd.concat([
                edf[["date", "home_team", "home_elo"]].rename(
                    columns={"home_team": "team", "home_elo": "elo"}),
                edf[["date", "away_team", "away_elo"]].rename(
                    columns={"away_team": "team", "away_elo": "elo"}),
            ]).dropna(subset=["elo"]).sort_values("date", kind="stable")
            for team, g in long.groupby("team"):
                out[team] = list(zip(g["date"], g["elo"]))
    except Exception as e:  # noqa: BLE001
        print(f"[warning] tier ELO series load failed for {lid}: {e}")
    _TIER_SERIES_CACHE[lid] = out
    return out


def _neighbor_tier_offsets(lid: str) -> dict[str, float]:
    """Neighboring divisions in this league's promotion/relegation chain →
    cumulative ELO offset translating THEIR scale onto `lid`'s scale.

    Walk down (feeder tiers): offsets compose via tier2_offset per hop;
    walk up (parent flights): via tier1_offset per hop.
    """
    out: dict[str, float] = {}
    off, cur = 0.0, lid                     # downward: epl → championship → …
    while (child := _TIER2_FOR.get(cur)) is not None:
        off += co.tier2_offset(child)
        out[child] = off
        cur = child
    off, cur = 0.0, lid                     # upward: league-two → league-one → …
    while (parent := _TIER1_FOR_BUILD.get(cur)) is not None:
        off += co.tier1_offset(cur)
        out[parent] = off
        cur = parent
    return out


def _get_tier_elo_map(lid: str) -> dict[str, float]:
    """End-of-history ELO map for ANY football-data league, {fd_team_name: current_elo}.

    Used to seed both promoted teams (from their tier-2 ELO) and relegated teams (from
    their tier-1 ELO). Returns {} if the data cannot be loaded.
    """
    if lid in _TIER2_ELO_CACHE:
        return _TIER2_ELO_CACHE[lid]
    try:
        df = match_results(lid).sort_values("date")
        df = df.dropna(subset=["home_goals", "away_goals"])
        if df.empty:
            _TIER2_ELO_CACHE[lid] = {}
            return {}
        _, elo_now_t = compute_elo(df, K=25, home_adv=80, regress=0.40,
                                   club_prior_beta=0.75,  # A8: club-prior target
                                   return_ratings=True)
        _TIER2_ELO_CACHE[lid] = dict(elo_now_t)
    except Exception as e:  # noqa: BLE001
        print(f"[warning] tier ELO load failed for {lid}: {e}")
        _TIER2_ELO_CACHE[lid] = {}
    return _TIER2_ELO_CACHE[lid]


# Backward-compatible alias (existing callers/tests use the tier2 name).
_get_tier2_elo_map = _get_tier_elo_map


def _elo_to_dc_params(
    adj_elo: float,
    atk: dict[str, float],
    dfd: dict[str, float],
    elo_now: dict[str, float],
) -> tuple[float, float]:
    """Map a translated ELO to DC attack/defense params via a SMOOTH linear fit.

    The previous implementation picked atk/dfd at the discrete percentile of adj_elo
    in the tier-1 ELO distribution, clamped to [5th, 95th]. That created a CLIFF: a
    promoted team whose (champ_elo - offset) fell below the tier-1 ELO floor was snapped
    to the 5th-pct attack AND the 95th-pct (worst) defence — i.e. the weakest side in
    league history — yielding ~certain relegation, while a stronger promoted team landing
    inside the range seeded mid-table. Two promoted teams one tier apart ended at opposite
    ends of the table (e.g. EPL preseason: Coventry 1.4% vs Hull 99.9% relegation).

    Now we regress atk and dfd linearly on ELO across the fitted tier-1 teams and evaluate
    at adj_elo, with a soft floor (no promoted team seeds weaker than the ~25th-percentile
    established side) so strength varies continuously with ELO and the weakest promoted team
    stays a relegation favourite rather than a near-certainty. Validated end-to-end on the
    EPL preseason rebuild: Coventry rank 5→12 / UCL 34%→8% / rel 1%→11% (was seeded
    mid-table); Hull rel 99.9%→84% (was snapped to worst-ever). The fitted tier-2 offset is
    unchanged — the cliff, not the offset, was the defect. See scripts/
    validate_promoted_seeding.py for the offline reproduction.
    """
    common = [t for t in atk if t in dfd and t in elo_now]
    if len(common) < 5 or not atk or not dfd:
        return 0.0, 0.0

    e = np.array([elo_now[t] for t in common], dtype=float)
    a = np.array([atk[t] for t in common], dtype=float)
    d = np.array([dfd[t] for t in common], dtype=float)
    a_slope, a_int = np.polyfit(e, a, 1)
    d_slope, d_int = np.polyfit(e, d, 1)

    # Soft floor: a promoted team seeds no weaker than the ~20th-percentile established
    # team. Without it, the weakest promoted side (adj_elo below the tier-1 ELO floor)
    # seeds as the clear weakest team → near-certain (~97%) relegation; the floor pulls it
    # up to a plausible bottom-of-table strength while still leaving it a relegation
    # favourite. Stronger promoted teams sit above the floor and are unaffected.
    floor = float(np.quantile(e, 0.25))
    hi = float(e.max()) + 40.0
    x = max(floor, min(hi, adj_elo))
    return float(a_slope * x + a_int), float(d_slope * x + d_int)


# ── Per-league outlook: structure of each single-table league ────────────────
# Each league declares its data `source`, team count `n`, and the outcome
# `buckets` that the season Monte-Carlo tallies. A bucket is a rank range:
#   {"top": N}      → ranks 1..N        (Title=top-1, UCL=top-4, Promotion=top-2)
#   {"band":[lo,hi]}→ ranks lo..hi      (promotion Playoff places)
#   {"bottom": M}   → ranks (n-M+1)..n  (relegation zone)
# `label` is the favorite-card title, `col` the (shorter) table-column header.
# `green_line`/`red_line` drive the table's qualification + relegation cut-lines.
# 2nd-tier promotion/playoff/relegation counts are approximate (they vary by
# country and year); top-flight UEFA-coefficient extra spots are out of scope.
# Champions League spots vary by association: the top-performing leagues earn a 5th
# spot via the UEFA coefficient (England and Italy had 5 for 2025-26). Europa = the
# next place, Conference = the one after (domestic-cup-winner spots are unmodelable
# and omitted, so these are approximate). `card=False` keeps a bucket as a table
# COLUMN only — the favorite cards stay simple (Title / UCL / Relegation).
_TOP = lambda ucl=4, rel=3: [
    {"key": "title", "label": "Title", "col": "Title", "top": 1},
    {"key": "ucl", "label": "Champions Lg", "col": "UCL", "top": ucl},
    {"key": "europa", "label": "Europa Lg", "col": "Europa", "band": [ucl + 1, ucl + 1], "card": False},
    {"key": "conf", "label": "Conference Lg", "col": "Conf", "band": [ucl + 2, ucl + 2], "card": False},
    {"key": "releg", "label": "Relegation", "col": "Releg", "bottom": rel}]
# Promotion structure (2026-07-09 feedback): second tiers promote the top
# `promo` automatically AND the winner of a playoff among `play`; the table
# shows Auto / Playoff-berth / Promoted / Relegation, and the sim actually
# plays the playoff bracket (see _promo_playoff_winner). `barrage` = the
# probability the tier-2 side survives a cross-league barrage against the
# top flight's relegation-playoff team (Germany/France) — the opponent isn't
# in this league's pmatrix, so it's a historical base rate, not a sim.
_PROMO = lambda promo, play, rel, barrage=None: [
    {"key": "promo", "label": "Auto Promotion", "col": "Auto", "top": promo, "card": False},
    {"key": "playoff", "label": "Promo Playoff", "col": "Playoff", "band": play, "card": False},
    {"key": "promoted", "label": "Promoted", "col": "Promoted",
     "promo_top": promo, "playoff_band": play,
     **({"barrage_win_rate": barrage} if barrage else {})},
    {"key": "releg", "label": "Relegation", "col": "Releg", "bottom": rel}]
_LIGUILLA = lambda: [
    {"key": "liguilla", "label": "Liguilla", "col": "Liguilla", "top": 8}]
# Non-UEFA single tables (Tier-1 expansion, 2026-07-10): _TOP's bucket labels
# ("Champions Lg"/"Europa Lg"/"Conference Lg") are UEFA-specific and would be
# wrong for Brazil/Japan/Argentina's continental competitions (Copa
# Libertadores/Sudamericana, AFC Champions League Elite/Two, ...). This is a
# deliberately coarser 3-bucket shape (Champion / one lumped "Continental"
# qualification zone / Relegation) rather than modeling each competition's
# real qualification structure, which varies by country and — for
# Argentina — by season; see each league's `rules` string for the caveat.
_CONTINENTAL = lambda label, top, rel=0: [
    {"key": "title", "label": "Champion", "col": "Champ", "top": 1},
    {"key": "continental", "label": label, "col": "Continental", "top": top}] + (
    [{"key": "releg", "label": "Relegation", "col": "Releg", "bottom": rel}] if rel else [])

OUTLOOK = {
    # Big-5 top flights (Understat xG). buckets preserve the prior Title/UCL/Releg output.
    # UCL spots per the current coefficient allocation: England + Italy earned a 5th
    # Champions League place (2025-26 cycle); the others have 4. green_line = UCL spots.
    "epl":        {"name": "Premier League", "source": "understat", "n": 20,
                   "buckets": _TOP(5), "green_line": 5, "red_line": 3,
                   "rules": "Top 5 qualify for the Champions League (2025-26 coefficient allocation) · bottom 3 relegated"},
    "la-liga":    {"name": "La Liga", "source": "understat", "n": 20,
                   "buckets": _TOP(4), "green_line": 4, "red_line": 3,
                   "rules": "Top 4 qualify for the Champions League · bottom 3 relegated"},
    "serie-a":    {"name": "Serie A", "source": "understat", "n": 20,
                   "buckets": _TOP(5), "green_line": 5, "red_line": 3,
                   "rules": "Top 5 qualify for the Champions League (2025-26 coefficient allocation) · bottom 3 relegated"},
    "bundesliga": {"name": "Bundesliga", "source": "understat", "n": 18,
                   "buckets": _TOP(4), "green_line": 4, "red_line": 3,
                   "rules": "Top 4 qualify for the Champions League · bottom 2 relegated, 16th plays a barrage vs the 2. Bundesliga's 3rd"},
    "ligue-1":    {"name": "Ligue 1", "source": "understat", "n": 18,
                   "buckets": _TOP(4), "green_line": 4, "red_line": 3,
                   "rules": "Top 4 qualify for the Champions League · bottom 2 relegated, 16th plays a barrage vs the Ligue 2 playoff winner"},
    # European 2nd tiers (football-data goals-only + market). Auto/Playoff/Promoted/Relegation;
    # the sim plays the promotion playoff (see _promo_playoff_winner).
    "championship": {"name": "EFL Championship", "source": "footballdata", "n": 24,
                     "buckets": _PROMO(2, [3, 6], 3), "green_line": 6, "red_line": 3,
                     "rules": "Top 2 promoted automatically · 3–6 promotion playoff, winner also promoted · bottom 3 relegated"},
    "league-one":   {"name": "EFL League One", "source": "footballdata", "n": 24,
                     "buckets": _PROMO(2, [3, 6], 4), "green_line": 6, "red_line": 4,
                     "rules": "Top 2 promoted automatically · 3–6 promotion playoff, winner also promoted · bottom 4 relegated"},
    "league-two":   {"name": "EFL League Two", "source": "footballdata", "n": 24,
                     "buckets": _PROMO(3, [4, 7], 2), "green_line": 7, "red_line": 2,
                     "rules": "Top 3 promoted automatically · 4–7 promotion playoff, winner also promoted · bottom 2 relegated"},
    "bundesliga-2": {"name": "2. Bundesliga", "source": "footballdata", "n": 18,
                     "buckets": _PROMO(2, [3, 3], 3, barrage=0.33), "green_line": 3, "red_line": 3,
                     "rules": "Top 2 promoted automatically · 3rd plays a barrage vs the Bundesliga's 16th (modeled at 33%) · bottom 2 relegated, 16th plays the mirror barrage"},
    "serie-b":      {"name": "Serie B", "source": "footballdata", "n": 20,
                     "buckets": _PROMO(2, [3, 8], 3), "green_line": 8, "red_line": 3,
                     "rules": "Top 2 promoted automatically · 3–8 promotion playoff (3rd–4th get byes), winner also promoted · bottom 3 relegated"},
    "segunda":      {"name": "LaLiga 2", "source": "footballdata", "n": 22,
                     "buckets": _PROMO(2, [3, 6], 4), "green_line": 6, "red_line": 4,
                     "rules": "Top 2 promoted automatically · 3–6 promotion playoff, winner also promoted · bottom 4 relegated"},
    "ligue-2":      {"name": "Ligue 2", "source": "footballdata", "n": 18,
                     "buckets": _PROMO(2, [3, 5], 4, barrage=0.33), "green_line": 5, "red_line": 4,
                     "rules": "Top 2 promoted automatically · 3–5 playoff, winner faces the Ligue 1 barrage (modeled at 33%) · bottom 4 relegated"},
    # Tier-1 expansion (2026-07-10, run last per this session's ordering):
    # England tier 5, completes the pyramid 1→5. Real format: champion
    # promoted automatically, 2nd-7th playoff for one more promotion spot —
    # the exact _PROMO(1, [2,7], rel) shape the round-3 promotion-playoff
    # bracket sim was built for. Bottom 4 drop to National League North/South
    # (not modeled — outside our source coverage).
    "national-league": {"name": "National League", "source": "footballdata", "n": 24,
                        "buckets": _PROMO(1, [2, 7], 4), "green_line": 7, "red_line": 4,
                        "rules": "Champion promoted automatically · 2nd–7th promotion playoff, winner also promoted · bottom 4 relegated to National League North/South (not modeled)"},
    # Scottish lower tiers (2026-07-11, round 4). Plain promotion-playoff shape —
    # the real cross-division playoff (which pulls in the tier above's 11th/9th)
    # is approximated; see rules caveat. n=10 for all three.
    "scottish-champ": {"name": "Scottish Championship", "source": "footballdata", "n": 10,
                       "confederation": "UEFA",
                       "buckets": _PROMO(1, [2, 4], 1), "green_line": 4, "red_line": 1,
                       "rules": "Champion promoted to the Premiership · 2nd–4th enter a promotion playoff (the Premiership's 11th also joins — not modeled) · bottom club relegated, 9th plays a playoff"},
    "scottish-league-one": {"name": "Scottish League One", "source": "footballdata", "n": 10,
                            "confederation": "UEFA",
                            "buckets": _PROMO(1, [2, 4], 1), "green_line": 4, "red_line": 1,
                            "rules": "Champion promoted to the Championship · 2nd–4th promotion playoff · bottom club relegated, 9th plays a playoff"},
    "scottish-league-two": {"name": "Scottish League Two", "source": "footballdata", "n": 10,
                            "confederation": "UEFA",
                            "buckets": _PROMO(1, [2, 4], 1), "green_line": 4, "red_line": 1,
                            "rules": "Champion promoted to League One · 2nd–4th promotion playoff · bottom club plays the pyramid playoff vs the Highland/Lowland League winners (not modeled)"},
    # C1: non-big-5 top flights (football-data goals-only + market odds).
    # UCL/Europa/Conference spots are the coefficient-based approximations the
    # _TOP docstring already caveats; relegation counts include playoff spots
    # (the bundesliga precedent: bottom N = direct + playoff berths).
    "eredivisie":   {"name": "Eredivisie", "source": "footballdata", "n": 18,
                     "buckets": _TOP(2), "green_line": 2, "red_line": 3,
                     "rules": "Top 2 qualify for the Champions League · bottom 2 relegated, 16th enters the promotion/relegation playoffs"},
    "primeira":     {"name": "Primeira Liga", "source": "footballdata", "n": 18,
                     "buckets": _TOP(2), "green_line": 2, "red_line": 3,
                     "rules": "Top 2 qualify for the Champions League · bottom 2 relegated, 16th plays a barrage vs Liga Portugal 2"},
    "super-lig":    {"name": "Süper Lig", "source": "footballdata", "n": 18,
                     "buckets": _TOP(2), "green_line": 2, "red_line": 3,
                     "rules": "Top 2 qualify for the Champions League · bottom 3 relegated"},
    # Split/points-transform formats (Scotland split, Belgium halving+playoffs,
    # Greece playoff round) — sim format config lands with each league's ship.
    "scottish-prem": {"name": "Scottish Premiership", "source": "footballdata", "n": 12,
                      "buckets": _TOP(1, rel=2), "green_line": 1, "red_line": 2,
                      "rules": "Champion qualifies for the Champions League · table splits top/bottom 6 after 33 rounds · bottom club relegated, 11th plays a barrage"},
    "belgian-pro":  {"name": "Belgian Pro League", "source": "footballdata", "n": 18,
                     "buckets": _TOP(2, rel=2), "green_line": 2, "red_line": 2,
                     "rules": "Points halve before the championship playoff (top 6) · champion qualifies for the Champions League · bottom 2 relegated"},
    "greek-super":  {"name": "Greek Super League", "source": "footballdata", "n": 14,
                     "buckets": _TOP(1, rel=2), "green_line": 1, "red_line": 2,
                     "rules": "Top 6 enter the championship playoff round · champion qualifies for the Champions League · bottom 2 relegated"},
    # Concacaf — ESPN goals-only (no xG, no market odds)
    # eval_seasons=None → derived dynamically from frame's season integers
    "liga-mx":      {"name": "Liga MX", "source": "espn", "n": 18, "confederation": "Concacaf",
                     "buckets": _LIGUILLA(), "green_line": 8, "red_line": None,
                     "eval_seasons": None,
                     "rules": "Top 8 reach the Liguilla (championship playoff) · no relegation (suspended through 2026)"},
    # C2 — ASA leagues (goals + ASA xG; played rows from ASA, scheduled
    # remainder from ESPN). No relegation. Family champions:
    # experiments/champion_nwsl.json / champion_usl.json.
    "nwsl":         {"name": "NWSL", "source": "asa", "asa_key": "nwsl", "n": 16,
                     "confederation": "Concacaf",
                     "buckets": [
                         {"key": "shield", "label": "Shield", "col": "Shield", "top": 1},
                         {"key": "playoffs", "label": "Playoffs", "col": "Playoffs", "top": 8}],
                     "green_line": 8, "red_line": None, "eval_seasons": None,
                     "rules": "Top 8 make the playoffs · Shield = best regular-season record · no relegation"},
    # USL playoffs are top-8 PER CONFERENCE (M4 2026-07-07: conference-aware —
    # `per_conf_top` counts within ESPN's Eastern/Western groups; falls back
    # to pooled top-16 if the conference fetch fails).
    "usl-championship": {"name": "USL Championship", "source": "asa", "asa_key": "uslc",
                         "n": 25, "confederation": "Concacaf",
                         "conference_slug": "usa.usl.1",
                         "buckets": [
                             {"key": "shield", "label": "Best Record", "col": "Shield", "top": 1},
                             {"key": "playoffs", "label": "Playoffs", "col": "Playoffs",
                              "per_conf_top": 8, "top": 16}],
                         "green_line": 16, "red_line": None, "eval_seasons": None,
                         "rules": "Top 8 per conference make the playoffs · no relegation"},
    # Tier-1 expansion (2026-07-10, docs/league-expansion-report.md). Goals-only
    # (football-data-intl carries no xG, same model family as the European
    # 2nd tiers). Continental-qualification counts are ROUGH — each of these
    # federations' real qualification structure is more granular (multiple
    # named competitions, sometimes multi-year aggregate tables) than a single
    # end-of-season cut line can represent; see each `rules` string.
    "brazil-serie-a": {"name": "Brasileirão Série A", "source": "footballdata_intl",
                       "n": 20, "confederation": "CONMEBOL",
                       "buckets": _CONTINENTAL("Continental (Libertadores/Sudamericana)", 6, 4),
                       "green_line": 6, "red_line": 4, "eval_seasons": None,
                       "rules": "Champion + next 5 reach Libertadores/Sudamericana (approximate — Brazil actually splits these across several named berths) · bottom 4 relegated to Série B"},
    "japan-j1":       {"name": "J1 League", "source": "footballdata_intl",
                       "n": 20, "confederation": "AFC",
                       "buckets": _CONTINENTAL("AFC Champions League", 4, 3),
                       "green_line": 4, "red_line": 3, "eval_seasons": None,
                       "rules": "Champion + next 3 reach the AFC Champions League Elite/Two (approximate) · bottom 3 relegated to J2"},
    "sweden-allsvenskan": {"name": "Allsvenskan", "source": "footballdata_intl",
                           "n": 16, "confederation": "UEFA",
                           "buckets": _CONTINENTAL("Champions League / Europa", 3, 2),
                           "green_line": 3, "red_line": 2, "eval_seasons": None,
                           "rules": "Champion + next 2 reach UEFA competitions (approximate) · bottom 2 relegated (a playoff spot is not modeled)"},
    "norway-eliteserien": {"name": "Eliteserien", "source": "footballdata_intl",
                           "n": 16, "confederation": "UEFA",
                           "buckets": _CONTINENTAL("Champions League / Europa", 3, 2),
                           "green_line": 3, "red_line": 2, "eval_seasons": None,
                           "rules": "Champion + next 2 reach UEFA competitions (approximate) · bottom 2 relegated (a playoff spot is not modeled)"},
    "denmark-superliga": {"name": "Superliga", "source": "footballdata_intl",
                          "n": 12, "confederation": "UEFA",
                          "buckets": _CONTINENTAL("Champions League / Europa", 2, 2),
                          "green_line": 2, "red_line": 2, "eval_seasons": None,
                          "rules": "Champion + runner-up reach UEFA competitions (approximate) · bottom 2 relegated — the real championship/relegation split-round format is not modeled, this is the plain regular-season table"},
    "poland-ekstraklasa": {"name": "Ekstraklasa", "source": "footballdata_intl",
                           "n": 18, "confederation": "UEFA",
                           "buckets": _CONTINENTAL("Champions League / Europa", 2, 3),
                           "green_line": 2, "red_line": 3, "eval_seasons": None,
                           "rules": "Champion + runner-up reach UEFA competitions (approximate) · bottom 3 relegated — the real championship/relegation split-round format is not modeled. No confirmed ESPN schedule source: this league ships results-only until an in-season fixture feed is found (docs/league-expansion-report.md)"},
    "argentina-primera": {"name": "Liga Profesional Argentina", "source": "footballdata_intl",
                          "n": 30, "confederation": "CONMEBOL",
                          "buckets": _CONTINENTAL("Continental (Libertadores/Sudamericana)", 8),
                          "green_line": 8, "red_line": None, "eval_seasons": None,
                          "rules": "Top 8 reach Libertadores/Sudamericana (a rough approximation — Argentina's real qualification and relegation rules have changed repeatedly across recent seasons; relegation is not modeled here, see the expansion report's Tier-1 caveat)"},
    # Round-4 Tier-1 UEFA top flights (2026-07-11). Split-round formats (Austria's
    # points-halving championship/relegation groups, Romania's play-off/play-out)
    # are approximated as a plain table — caveat in each rules string.
    "austria-bundesliga": {"name": "Austrian Bundesliga", "source": "footballdata_intl",
                           "n": 12, "confederation": "UEFA",
                           "buckets": _CONTINENTAL("European qualification", 4, 2),
                           "green_line": 4, "red_line": 2, "eval_seasons": None,
                           "rules": "Champion → Champions League qualifying; top sides → European competitions (approximate) · bottom relegated (the real points-halving championship/relegation split is not modeled — plain regular-season table)"},
    "swiss-super-league": {"name": "Swiss Super League", "source": "footballdata_intl",
                           "n": 12, "confederation": "UEFA",
                           "buckets": _CONTINENTAL("European qualification", 4, 2),
                           "green_line": 4, "red_line": 2, "eval_seasons": None,
                           "rules": "Champion → Champions League qualifying; top sides → European competitions (approximate) · bottom club relegated, 11th plays a barrage (not modeled)"},
    "romania-liga1": {"name": "Liga I (Romania)", "source": "footballdata_intl",
                      "n": 16, "confederation": "UEFA",
                      "buckets": _CONTINENTAL("European qualification", 4, 3),
                      "green_line": 4, "red_line": 3, "eval_seasons": None,
                      "rules": "Champion → Champions League qualifying; top sides → European competitions (approximate) · bottom relegated. The real championship play-off / relegation play-out split (points halved) is not modeled — this is the plain full-season table, which can include promotion/relegation-playoff participants from Liga II, so the table may show more than 16 clubs"},
    "ireland-premier": {"name": "League of Ireland Premier", "source": "footballdata_intl",
                        "n": 10, "confederation": "UEFA",
                        "buckets": _CONTINENTAL("European qualification", 3, 1),
                        "green_line": 3, "red_line": 1, "eval_seasons": None,
                        "rules": "Champion → Champions League qualifying; top sides → European competitions (approximate) · bottom club relegated, 9th plays a promotion/relegation playoff (not modeled) · calendar-year season"},
    # Round-4 projection-only (2026-07-11). China/Russia keep the football-data
    # Pinnacle odds columns (backbone for a future edge layer) but are presented
    # projection-only. ESPN chn.1/rus.1 supply fixtures.
    "china-super": {"name": "Chinese Super League", "source": "footballdata_intl",
                    "n": 16, "confederation": "AFC",
                    "buckets": _CONTINENTAL("AFC Champions League", 3, 2),
                    "green_line": 3, "red_line": 2, "eval_seasons": None,
                    "rules": "Champion + next 2 reach AFC club competitions (approximate) · bottom 2 relegated · calendar-year season"},
    "russia-premier": {"name": "Russian Premier League", "source": "footballdata_intl",
                       "n": 16, "confederation": "UEFA",
                       "buckets": _CONTINENTAL("European qualification (currently suspended)", 3, 2),
                       "green_line": 3, "red_line": 2, "eval_seasons": None,
                       "rules": "Top 3 would qualify for UEFA competitions, but Russian clubs are currently suspended from European football (shown for domestic context) · bottom 2 relegated, 13th–14th play relegation playoffs (not modeled)"},
    # Round-4 projection-only, ESPN goals-only (no football-data odds). Same model
    # family as liga-mx / NWSL. eval_seasons=None → advisory only.
    "saudi-pro": {"name": "Saudi Pro League", "source": "espn", "n": 18,
                  "confederation": "AFC",
                  "buckets": _CONTINENTAL("AFC Champions League", 4, 3),
                  "green_line": 4, "red_line": 3, "eval_seasons": None,
                  "rules": "Champion + top sides reach the AFC Champions League Elite (approximate) · bottom 3 relegated"},
    "australia-aleague": {"name": "A-League Men", "source": "espn", "n": 12,
                          "confederation": "AFC",
                          "buckets": [
                              {"key": "premiers", "label": "Premiers Plate", "col": "Premiers", "top": 1},
                              {"key": "finals", "label": "Finals Series", "col": "Finals", "top": 6}],
                          "green_line": 6, "red_line": None, "eval_seasons": None,
                          "rules": "Premiers Plate = best regular-season record · top 6 reach the finals series (the championship is decided there, not by the table) · no relegation (closed league)"},
    "wsl": {"name": "Women's Super League", "source": "espn", "n": 12,
            "confederation": "UEFA",
            "buckets": _CONTINENTAL("Women's Champions League", 2, 1),
            "green_line": 2, "red_line": 1, "eval_seasons": None,
            "rules": "Top sides qualify for the UEFA Women's Champions League (approximate) · bottom club relegated · goals-only (no xG source for this league)"},
    # Round-4 Phase 3 (2026-07-11, API-Football schedule source).
    # Canadian Premier League: not on football-data OR ESPN — everything via
    # API-Football. Projection-only (no odds). Single table + playoffs, no relegation.
    "canadian-pl": {"name": "Canadian Premier League", "source": "api_football",
                    "n": 8, "confederation": "Concacaf",
                    "buckets": [
                        {"key": "premiers", "label": "Best Record", "col": "Premiers", "top": 1},
                        {"key": "playoffs", "label": "Playoffs", "col": "Playoffs", "top": 6}],
                    "green_line": 6, "red_line": None, "eval_seasons": None,
                    "rules": "Best regular-season record earns a home final · top 6 reach the playoffs (championship decided there) · no relegation · projections-only (no odds source)"},
    # Finland Veikkausliiga: results+odds from football-data (footballdata_intl),
    # upcoming fixtures via API-Football (ESPN fin.1 empty — see FIXTURE_OVERRIDE).
    "finland-veikkausliiga": {"name": "Veikkausliiga", "source": "footballdata_intl",
                              "n": 12, "confederation": "UEFA",
                              "buckets": _CONTINENTAL("European qualification", 3, 2),
                              "green_line": 3, "red_line": 2, "eval_seasons": None,
                              "rules": "Champion → Champions League qualifying; top sides → European competitions (approximate) · bottom relegated, others play a relegation group (the real championship/relegation split is not modeled — plain table) · calendar-year season · results-only: no ESPN schedule source, so no in-season upcoming-fixture list (projections from played matches)"},
    # Round 5 (2026-07-14): South America + more Asia + Eerste Divisie
    # (docs/league-expansion-report.md, round-5 section). All ESPN goals-only
    # (source="espn", same family as Saudi/A-League/WSL) except K League 1
    # (no ESPN slug — API-Football results-only, CPL's family). South American
    # top flights split into Apertura/Clausura(+Intermedio) tournaments with
    # their own playoffs and use multi-year rolling-average relegation tables —
    # NOT modeled here (same simplification precedent as Argentina's Tier-1
    # entry): this is a single combined-season table, continental/relegation
    # counts are real qualification counts even though the underlying format
    # is approximated. Verified live 2026-07-14: ESPN chi.1/col.1/uru.1/per.1/
    # tha.1/ned.2 all resolve; kor.1 (and kor.k1/k.league.1) do not.
    "chile-primera": {"name": "Liga de Primera", "source": "espn", "n": 16,
                      "confederation": "CONMEBOL",
                      "buckets": _CONTINENTAL("Copa Libertadores / Sudamericana", 7, 2),
                      "green_line": 7, "red_line": 2, "eval_seasons": None,
                      "rules": "Champion, runner-up, and the Copa Chile winner reach the Copa Libertadores; 4th-7th reach the Copa Sudamericana (approximate — the Copa Chile-linked spot creates a gap at 3rd that a simple cut line can't represent) · bottom 2 relegated by a 3-year rolling average table (not modeled here — this is the single-season table) · calendar-year season"},
    "colombia-primera-a": {"name": "Categoría Primera A", "source": "espn", "n": 20,
                           "confederation": "CONMEBOL",
                           "buckets": _CONTINENTAL("Copa Libertadores / Sudamericana", 8, 2),
                           "green_line": 8, "red_line": 2, "eval_seasons": None,
                           "rules": "Season splits into Apertura and Clausura round-robin tournaments, each followed by an 8-team playoff (not modeled here — this is a combined single table of all matches played) · the two tournament champions plus the next 2 in the aggregate table reach the Copa Libertadores, the next 3 reach the Copa Sudamericana (approximate) · bottom 2 relegated by a 3-year rolling average table (not modeled here) · calendar-year season"},
    "uruguay-primera": {"name": "Primera División", "source": "espn", "n": 16,
                        "confederation": "CONMEBOL",
                        "buckets": _CONTINENTAL("Copa Libertadores / Sudamericana", 4, 2),
                        "green_line": 4, "red_line": 2, "eval_seasons": None,
                        "rules": "Season combines Apertura, Intermedio, and Clausura phases into an annual aggregate table (not modeled here — this is a plain combined-season table) · champion + runner-up + next 2 reach the Copa Libertadores or Copa Sudamericana (approximate — some spots depend on the separate Copa AUF Uruguay and Intermedio results, not modeled) · bottom 2 relegated by a 2-year rolling average table (not modeled here) · calendar-year season"},
    "peru-liga1": {"name": "Liga 1", "source": "espn", "n": 18,
                  "confederation": "CONMEBOL",
                  "buckets": _CONTINENTAL("Copa Libertadores / Sudamericana", 8, 2),
                  "green_line": 8, "red_line": 2, "eval_seasons": None,
                  "rules": "Top 4 of the season's cumulative table reach the Copa Libertadores, next 4 reach the Copa Sudamericana · bottom 2 of the cumulative table relegated · the season is actually split into Apertura/Clausura tournaments plus a playoff for the title (not modeled here — this is a combined single table, matching how the cumulative/continental and relegation table is officially built) · calendar-year season"},
    "thai-league-1": {"name": "Thai League 1", "source": "espn", "n": 16,
                      "confederation": "AFC",
                      "buckets": _CONTINENTAL("AFC Champions League", 4, 3),
                      "green_line": 4, "red_line": 3, "eval_seasons": None,
                      "rules": "Top 4 reach the AFC Champions League Elite/Two (approximate) · bottom 3 relegated to Thai League 2"},
    # Eerste Divisie (Netherlands tier 2): no football-data coverage confirmed
    # (data.php's country list stops at Eredivisie tier 1) and no xG source, so
    # this ships goals-only via source="espn" rather than the footballdata
    # second-tier family — custom buckets (not the _PROMO helper) because there
    # is no reliably modelable automatic relegation (licensing-based, rare) to
    # put in a trailing "releg" bucket.
    "eerste-divisie": {"name": "Eerste Divisie", "source": "espn", "n": 20,
                       "confederation": "UEFA",
                       "buckets": [
                           {"key": "promo", "label": "Auto Promotion", "col": "Auto", "top": 2, "card": False},
                           {"key": "playoff", "label": "Promo Playoff", "col": "Playoff", "band": [3, 8], "card": False},
                           {"key": "promoted", "label": "Promoted", "col": "Promoted",
                            "promo_top": 2, "playoff_band": [3, 8]}],
                       "green_line": 8, "red_line": None, "eval_seasons": None,
                       "rules": "Champion and runner-up promoted automatically to the Eredivisie · 3rd-8th enter a promotion playoff whose winner faces the Eredivisie's 16th-placed team for the final promotion spot (that cross-league leg isn't modeled — the playoff-band winner is shown directly as promoted) · no fixed automatic relegation (licensing-based, not modeled) · goals-only (no xG source for this tier)"},
    # K League 1 (South Korea): no ESPN slug under any plausible guess (kor.1,
    # kor.k1, k.league.1 all confirmed live to return 0 teams) and not on
    # football-data.co.uk — ships results-only off API-Football's free-plan
    # seasons (2022-2024), same treatment as Canadian PL.
    "k-league-1": {"name": "K League 1", "source": "api_football", "n": 12,
                   "confederation": "AFC",
                   "buckets": _CONTINENTAL("AFC Champions League", 3, 1),
                   "green_line": 3, "red_line": 1, "eval_seasons": None,
                   "rules": "Champion, runner-up, and 3rd reach the AFC Champions League Elite/Two (approximate — a Korea Cup wildcard berth isn't modeled) · bottom club (12th) relegated automatically; 10th-11th enter a relegation playoff vs K League 2 sides (not modeled) · the real format splits into a Championship Round (top 6) / Relegation Round (bottom 6) after 33 rounds — not modeled here, this is the plain full-season table · results-only: no ESPN schedule source and the API-Football free plan only serves 2022-2024 (no current-season fixtures) · no odds source"},
}

# football-data team name → ESPN displayName (for crest/display on goals-only
# leagues; football-data uses abbreviated names). Only entries that differ from
# the ESPN displayName; teams with exact-matching names need no entry.
FD_ESPN: dict[str, dict[str, str]] = {
    # Scottish lower tiers (2026-07-11, round 4). Only names that differ from the
    # ESPN displayName; East Kilbride/Clyde match by name but ESPN carries no crest
    # for them (fall back to the global TEAM_LOGOS map / initials).
    "scottish-champ": {},
    "scottish-league-one": {
        "Inverness C": "Inverness Caledonian Thistle", "Hamilton": "Hamilton Academical",
        "Queen of Sth": "Queen of the South", "Alloa": "Alloa Athletic",
    },
    "scottish-league-two": {
        "Spartans": "Spartans FC", "Forfar": "Forfar Athletic",
        "Elgin": "Elgin City", "Stirling": "Stirling Albion",
    },
    "national-league": {
        "Aldershot": "Aldershot Town", "Boston Utd": "Boston United",
        "Carlisle": "Carlisle United", "Forest Green": "Forest Green Rovers",
        "Halifax": "FC Halifax Town", "Hartlepool": "Hartlepool United",
        "Scunthorpe": "Scunthorpe United", "Solihull": "Solihull Moors",
        "Southend": "Southend United", "Sutton": "Sutton United",
        "Yeovil": "Yeovil Town",
    },
    "championship": {
        "Birmingham": "Birmingham City", "Blackburn": "Blackburn Rovers",
        "Charlton": "Charlton Athletic", "Coventry": "Coventry City",
        "Derby": "Derby County", "Hull": "Hull City",
        "Ipswich": "Ipswich Town", "Leicester": "Leicester City",
        "Norwich": "Norwich City", "Oxford": "Oxford United",
        "Preston": "Preston North End", "QPR": "Queens Park Rangers",
        "Sheffield Weds": "Sheffield Wednesday", "Stoke": "Stoke City",
        "Swansea": "Swansea City", "West Brom": "West Bromwich Albion",
    },
    "league-one": {
        "Bolton": "Bolton Wanderers", "Bradford": "Bradford City",
        "Burton": "Burton Albion", "Cardiff": "Cardiff City",
        "Doncaster": "Doncaster Rovers", "Exeter": "Exeter City",
        "Huddersfield": "Huddersfield Town", "Lincoln": "Lincoln City",
        "Luton": "Luton Town", "Mansfield": "Mansfield Town",
        "Northampton": "Northampton Town", "Peterboro": "Peterborough United",
        "Plymouth": "Plymouth Argyle", "Rotherham": "Rotherham United",
        "Stockport": "Stockport County", "Wigan": "Wigan Athletic",
        "Wycombe": "Wycombe Wanderers",
    },
    "league-two": {
        "Accrington": "Accrington Stanley", "Bristol Rvs": "Bristol Rovers",
        "Cambridge": "Cambridge United", "Cheltenham": "Cheltenham Town",
        "Colchester": "Colchester United", "Crewe": "Crewe Alexandra",
        "Grimsby": "Grimsby Town", "Harrogate": "Harrogate Town",
        "Oldham": "Oldham Athletic", "Salford": "Salford City",
        "Shrewsbury": "Shrewsbury Town", "Swindon": "Swindon Town",
        "Tranmere": "Tranmere Rovers",
    },
    "bundesliga-2": {
        "Bielefeld": "Arminia Bielefeld", "Bochum": "VfL Bochum",
        "Braunschweig": "TSV Eintracht Braunschweig", "Darmstadt": "SV Darmstadt 98",
        "Dresden": "Dynamo Dresden", "Elversberg": "SV 07 Elversberg",
        "Fortuna Dusseldorf": "Fortuna Düsseldorf",
        "Greuther Furth": "SpVgg Greuther Fürth", "Hannover": "Hannover 96",
        "Hertha": "Hertha Berlin", "Karlsruhe": "Karlsruher SC",
        "Magdeburg": "1. FC Magdeburg", "Nurnberg": "1. FC Nürnberg",
        "Paderborn": "SC Paderborn 07",
        "PreuÃ\x9fen MÃ¼nster": "Preußen Münster",
    },
    "serie-b": {
        "Avellino": "US Avellino",
    },
    "segunda": {
        "Almeria": "Almería", "Andorra": "FC Andorra", "Cadiz": "Cádiz",
        "Castellon": "Castellón", "Cordoba": "Córdoba",
        "La Coruna": "Deportivo La Coruña", "Leganes": "Leganés",
        "Malaga": "Málaga", "Mirandes": "Mirandés", "Santander": "Racing Santander",
        "Sociedad B": "Real Sociedad II", "Sp Gijon": "Sporting Gijón",
        "Valladolid": "Real Valladolid", "Zaragoza": "Real Zaragoza",
    },
    "ligue-2": {
        "Clermont": "Clermont Foot", "Laval": "Stade Laval",
        "Nancy": "AS Nancy Lorraine", "Pau FC": "Pau", "Red Star": "Red Star FC 93",
        "Reims": "Stade de Reims", "Rodez": "Rodez Aveyron",
        "St Etienne": "Saint-Étienne", "Amiens": "Amiens SC", "Bastia": "SC Bastia",
    },
    "eredivisie": {
        "Ajax": "Ajax Amsterdam", "Den Haag": "ADO Den Haag",
        "Cambuur": "SC Cambuur", "For Sittard": "Fortuna Sittard",
        "Feyenoord": "Feyenoord Rotterdam", "Groningen": "FC Groningen",
        "Twente": "FC Twente", "Utrecht": "FC Utrecht",
        "Nijmegen": "NEC Nijmegen", "Zwolle": "PEC Zwolle",
    },
    "primeira": {
        "Famalicao": "FC Famalicao", "Guimaraes": "Vitória de Guimaraes",
        "Nacional": "C.D. Nacional", "Porto": "FC Porto",
        "Sp Braga": "Braga", "Sp Lisbon": "Sporting CP",
    },
    "super-lig": {
        "Buyuksehyr": "Istanbul Basaksehir", "Gaziantep": "Gaziantep FK",
        "Goztep": "Goztepe", "Karagumruk": "Fatih Karagümrük",
        "Rizespor": "Caykur Rizespor",
    },
    "scottish-prem": {
        "Hearts": "Heart of Midlothian",
    },
    "belgian-pro": {
        "Cercle Brugge": "Cercle Brugge KSV", "Charleroi": "Royal Charleroi SC",
        "Genk": "Racing Genk", "Gent": "KAA Gent", "Mechelen": "KV Mechelen",
        "Oud-Heverlee Leuven": "OH Leuven", "RAAL La Louviere": "RAAL La Louvière",
        "St Truiden": "Sint-Truidense", "St. Gilloise": "Union St.-Gilloise",
        "Standard": "Standard Liege", "Waregem": "Zulte-Waregem",
        "Westerlo": "KVC Westerlo",
    },
    "greek-super": {
        "AEK": "AEK Athens", "Asteras Tripolis": "Asteras Tripoli",
        "Larisa": "Larissa FC", "Levadeiakos": "Levadiakos",
        "Olympiakos": "Olympiacos", "PAOK": "PAOK Salonika",
        "Panserraikos": "Panserraikos FC",
    },
    # ASA leagues: ASA team_name → ESPN displayName (crest/display lookup;
    # inverse of espn_fixtures.ESPN_TO_UNDERSTAT["nwsl"]).
    "nwsl": {
        "NJ/NY Gotham FC": "Gotham FC",
        "Utah Royals FC": "Utah Royals",
    },
    "usl-championship": {
        "Lexington SC":               "Lexington",
        "The Miami FC":               "Miami FC",
        "Monterey Bay FC":            "Monterey Bay",
        "Oakland Roots SC":           "Oakland Roots",
        "Pittsburgh Riverhounds SC":  "Pittsburgh Riverhounds",
        "Sporting Club Jacksonville": "Sporting JAX",
    },
}


def _espn_names_to_fd(lid: str, fx: "pd.DataFrame") -> "pd.DataFrame":
    """Map ESPN displayNames in a fixtures frame to FD model keys.

    Inverse of FD_ESPN — the league's own map first, then a global inverse
    across all FD leagues (covers teams promoted from a covered lower tier,
    whose name entry lives in that tier's map). Unmapped names pass through
    (they hit the promoted-team prior path, which is correct).
    """
    inv = {v: k for k, v in FD_ESPN.get(lid, {}).items()}
    glob = {v: k for m in FD_ESPN.values() for k, v in m.items()}
    fx = fx.copy()
    for col in ("home_team", "away_team"):
        fx[col] = fx[col].map(lambda n: inv.get(n) or glob.get(n, n))
    return fx


# football-data-INTL (Brazil/Japan/Nordics/Argentina) team key → ESPN
# displayName. Diacritics and abbreviation differences (Sao Paulo → São Paulo,
# Malmo FF → Malmö FF, Argentinos Jrs → Argentinos Juniors, ...) verified live
# 2026-07-10 by diffing each league's current ESPN roster against the
# football-data-intl name set (docs/league-expansion-report.md). Only the
# overlap that needed a fix is listed; teams absent from ESPN's CURRENT top
# flight (relegated since, or ESPN simply doesn't carry them) are intentionally
# left unmapped — they pass through to the promoted-team prior path, same
# fallback as FD_ESPN's European entries.
FDI_ESPN: dict[str, dict[str, str]] = {
    # Round-4 Tier-1 (2026-07-11). football-data-intl short names → ESPN displayName.
    # Recently-relegated teams shown in a completed-season table (e.g. BW Linz) have
    # no entry in ESPN's current squad list — they self-resolve at the season flip.
    "austria-bundesliga": {
        "LASK": "LASK Linz", "Sturm Graz": "SK Sturm Graz", "Salzburg": "RB Salzburg",
        "SK Rapid": "Rapid Vienna", "Hartberg": "TSV Hartberg",
        "Altach": "SC Rheindorf Altach", "Ried": "SV Josko Ried",
        "Wolfsberger AC": "Wolfsberger", "Tirol": "WSG Swarovski Tirol",
        "A. Klagenfurt": "Austria Klagenfurt", "Austria Wien": "Austria Vienna",
        "Rapid Wien": "Rapid Vienna", "Lustenau": "Austria Lustenau",
        "Grazer AK": "Grazer AK",
    },
    "swiss-super-league": {
        "Thun": "FC Thun", "Lugano": "FC Lugano", "Sion": "FC Sion", "Basel": "FC Basel",
        "Luzern": "FC Luzern", "Lausanne": "Lausanne Sports", "Zurich": "FC Zürich",
        "St Gallen": "St. Gallen", "Grasshoppers": "Grasshoppers",
        "Yverdon": "Yverdon Sport", "Winterthur": "Winterthur", "Servette": "Servette",
        "Young Boys": "Young Boys",
    },
    "romania-liga1": {
        "Univ. Craiova": "CSU Craiova", "U. Cluj": "Universitatea Cluj",
        "CFR Cluj": "CFR Cluj-Napoca", "FC Rapid Bucuresti": "Rapid Bucuresti",
        "Otelul": "Otelul Galati", "Din. Bucuresti": "Dinamo Bucuresti",
        "Csikszereda M. Ciuc": "Csíkszereda", "Farul Constanta": "FC Farul Constanta",
        "Petrolul": "Petrolul Ploiesti", "FC Hermannstadt": "Hermannstadt",
        "Metaloglobus Bucharest": "Metaloglobus", "FCSB": "FCSB",
    },
    "ireland-premier": {
        "St. Patricks": "St. Patrick's Athletic", "Galway": "Galway United",
        "Drogheda": "Drogheda United",
    },
    "china-super": {
        "Zhejiang Professional": "Zhejiang Professional FC",
        "Henan Songshan Longmen": "Henan",
    },
    "russia-premier": {
        "Zenit": "Zenit St Petersburg", "Baltika": "FC Baltika Kaliningrad",
        "Dynamo Moscow": "Dinamo Moscow", "FK Rostov": "Rostov",
        "Krylya Sovetov": "Krylia Sovetov", "Orenburg": "Gazovik Orenburg",
        "Akron Togliatti": "Akron Tolyatti", "CSKA Moscow": "CSKA Moscow",
        "Akhmat Grozny": "Akhmat Grozny", "Spartak Moscow": "Spartak Moscow",
    },
    "brazil-serie-a": {
        "Atletico-MG": "Atlético-MG", "Botafogo RJ": "Botafogo",
        "Bragantino": "Red Bull Bragantino", "Chapecoense-SC": "Chapecoense",
        "Flamengo RJ": "Flamengo", "Gremio": "Grêmio", "Sao Paulo": "São Paulo",
        "Vasco": "Vasco da Gama", "Vitoria": "Vitória",
    },
    "japan-j1": {
        "Kyoto": "Kyoto Sanga", "Machida": "Machida Zelvia",
        "Okayama": "Fagiano Okayama", "Urawa Reds": "Urawa Red Diamonds",
        "Verdy": "Tokyo Verdy 1969",
    },
    "sweden-allsvenskan": {
        "Brommapojkarna": "IF Brommapojkarna", "Degerfors": "Degerfors IF",
        "Djurgarden": "Djurgården", "Elfsborg": "IF Elfsborg",
        "Goteborg": "IFK Göteborg", "Hacken": "BK Häcken",
        "Halmstad": "Halmstads BK", "Hammarby": "Hammarby IF",
        "Kalmar": "Kalmar FF", "Malmo FF": "Malmö FF",
        "Mjallby": "Mjällby AIF", "Orgryte": "Örgryte IS",
        "Sirius": "IK Sirius", "Vasteras SK": "Västerås SK",
    },
    "norway-eliteserien": {
        "Brann": "SK Brann", "HamKam": "Hamarkameratene",
        "Kristiansund": "Kristiansund BK", "Sarpsborg 08": "Sarpsborg FK",
        "Start": "IK Start", "Valerenga": "Vålerenga", "Viking": "Viking FK",
    },
    "denmark-superliga": {
        "Aarhus": "AGF", "Brondby": "Brøndby IF", "FC Copenhagen": "F.C. København",
        "Lyngby": "Lyngby Boldklub", "Midtjylland": "FC Midtjylland",
        "Nordsjaelland": "FC Nordsjælland", "Odense": "Odense Boldklub",
        "Silkeborg": "Silkeborg IF", "Sonderjyske": "Sønderjyske Fodbold",
        "Viborg": "Viborg FF",
    },
    "argentina-primera": {
        "Argentinos Jrs": "Argentinos Juniors", "Atl. Tucuman": "Atlético Tucumán",
        "Belgrano": "Belgrano (Córdoba)",
        "Central Cordoba": "Central Córdoba (Santiago del Estero)",
        "Dep. Riestra": "Deportivo Riestra",
        "Estudiantes L.P.": "Estudiantes de La Plata",
        "Estudiantes Rio Cuarto": "Estudiantes de Río Cuarto",
        "Gimnasia L.P.": "Gimnasia La Plata", "Gimnasia Mendoza": "Gimnasia (Mendoza)",
        "Huracan": "Huracán", "Ind. Rivadavia": "Independiente Rivadavia",
        "Instituto": "Instituto (Córdoba)", "Lanus": "Lanús",
        "Newells Old Boys": "Newell's Old Boys",
        "Sarmiento Junin": "Sarmiento (Junín)", "Talleres Cordoba": "Talleres (Córdoba)",
        "Union de Santa Fe": "Unión (Santa Fe)", "Velez Sarsfield": "Vélez Sarsfield",
    },
}


def _espn_names_to_fdintl(lid: str, fx: "pd.DataFrame") -> "pd.DataFrame":
    """Map ESPN displayNames in a fixtures frame to football-data-intl model
    keys — the FDI_ESPN analog of _espn_names_to_fd."""
    inv = {v: k for k, v in FDI_ESPN.get(lid, {}).items()}
    fx = fx.copy()
    for col in ("home_team", "away_team"):
        fx[col] = fx[col].map(lambda n: inv.get(n, n))
    return fx


# Optional per-league season ranges for the generic ESPN goals-only source.
# Absent → espn_results_frame defaults to 2015..current. Narrow a range when a
# league's ESPN history is short or noisy (e.g. WSL scoreboard coverage).
ESPN_GOALS_ONLY_SEASONS: dict[str, list[int]] = {}

# Leagues whose RESULTS come from `source` but whose UPCOMING FIXTURES come from
# a different provider because ESPN has no slug. Value = provider module key.
# Finland: footballdata_intl results+odds, but ESPN `fin.1` is empty (0 teams),
# so API-Football supplies the schedule. Generalises the Poland results-only gap.
# Leagues whose RESULTS come from `source` but whose UPCOMING FIXTURES come from
# a secondary provider (ESPN has no slug). Empty on the API-Football FREE plan,
# which can't serve current-season (2026) fixtures — Finland/Poland ship
# results-only off current football-data instead. Re-add {"finland-veikkausliiga":
# "api_football", "poland-ekstraklasa": "api_football"} (and their LEAGUE entries)
# once a paid plan unlocks the current season, to get their forward schedules.
FIXTURE_OVERRIDE: dict[str, str] = {}


def _load_frame(league_id: str, source: str, asa_key: str | None = None):
    """Route a league to its canonical-frame source."""
    if source == "understat":
        return canonical_frame(league_id)
    if source == "footballdata":
        return match_results(league_id)
    if source == "footballdata_intl":
        return match_results_intl(league_id)
    if source == "espn":
        # liga-mx keeps its torneo-specific (Apertura/Clausura) frame; every other
        # ESPN goals-only league (Saudi/A-League/WSL, round 4) uses the generic loop.
        if league_id == "liga-mx":
            return liga_mx_frame()
        from data_pipeline.espn_fixtures import espn_results_frame
        return espn_results_frame(league_id, ESPN_GOALS_ONLY_SEASONS.get(league_id))
    if source == "api_football":
        from data_pipeline.api_football import results_frame as apif_results
        return apif_results(league_id)
    if source == "asa":
        return asa_canonical_frame(asa_key or league_id)
    raise ValueError(f"Unknown source '{source}' for league '{league_id}'")


def _per_conf_members(key, conf_arrays, top_n: int):
    """Indices of the top `top_n` teams WITHIN each conference by sim key.

    M4 (2026-07-07): USL playoff spots are per-conference; a team 3rd overall
    but 1st in its conference qualifies. `conf_arrays` are index arrays into
    the team universe, one per conference.
    """
    out = []
    for ci in conf_arrays:
        out.extend(ci[np.argsort(-key[ci])][:top_n])
    return out


def _bucket_idx(bucket: dict, order, nT: int):
    """Team indices (into `order`, best-first) that fall in a bucket's rank range."""
    if "top" in bucket:
        return order[:bucket["top"]]
    if "bottom" in bucket:
        return order[nT - bucket["bottom"]:]
    if "band" in bucket:
        return order[bucket["band"][0] - 1:bucket["band"][1]]
    return order[:0]


def _promo_playoff_winner(seeds, PM, rng):
    """Simulate one promotion playoff among `seeds` (team indices, best seed
    first) and return the winning team index.

    Ties are abstracted to a single virtual match — higher seed hosts,
    P(host advances) = pH + 0.5·pD from the same DC pairing matrix the client
    what-if sim uses (the real formats are two-legged semis with a one-off or
    two-legged final; the seed-hosting bias stands in for the higher seed's
    aggregate edge). Bracket shapes (MUST stay mirrored in webapp/index.html
    runSimTable — SIM PORTING CONTRACT):
      1 team  → that team (cross-league barrage applied by the caller)
      3 teams → s1 v s2, winner at s0 (Ligue 2: 4th v 5th, winner at 3rd)
      4 teams → semis s0 v s3, s1 v s2, then the final (England/Spain)
      6 teams → prelims s2 v s5, s3 v s4; semis s0 v w(s3,s4), s1 v w(s2,s5);
                then the final (Serie B: 3rd–4th get byes)
    """
    def win(hi, ai):
        p = PM[hi, ai]
        return hi if rng.random() < p[0] + 0.5 * p[1] else ai

    def host(a, b):                      # better (earlier) seed hosts
        return win(a, b) if seeds.index(a) < seeds.index(b) else win(b, a)

    s = list(seeds)
    if len(s) == 1:
        return s[0]
    if len(s) == 3:
        return host(s[0], host(s[1], s[2]))
    if len(s) == 6:
        # prelims 5v8 / 6v7; semis pair 3rd with w(6v7) and 4th with w(5v8)
        s = [s[0], s[1], host(s[2], s[5]), host(s[3], s[4])]
    # 4-team bracket (also the tail of the 6-team format)
    return host(host(s[0], s[3]), host(s[1], s[2]))


def _stub_team_meta(league_id: str) -> dict[str, dict]:
    """Team-name → {logo, color} for crest/color lookup.

    Idempotent across rebuilds: reads the coming-soon stub's `teams[]` (keyed by
    ESPN displayName) AND, when the file is already a live payload, its
    `standings[]` (keyed by Understat title). The builder OVERWRITES this same
    file, so without the standings fallback a second run would lose every crest.
    """
    stub = Path(f"webapp/data/{league_id}.js")
    if not stub.exists():
        return {}
    txt = stub.read_text()
    payload = json.loads(txt[txt.index("=") + 1:].rstrip().rstrip(";"))
    meta: dict[str, dict] = {}
    for t in payload.get("teams", []):          # coming-soon stub: ESPN displayName
        if t.get("logo") or t.get("color"):
            meta[t["name"]] = {"logo": t.get("logo"), "color": t.get("color")}
    for s in payload.get("standings", []):      # live payload: Understat title
        if s.get("logo") and s["team"] not in meta:
            meta[s["team"]] = {"logo": s.get("logo"), "color": s.get("color")}
    return meta


def _stub_league_logo(league_id: str) -> str | None:
    stub = Path(f"webapp/data/{league_id}.js")
    if not stub.exists():
        return None
    txt = stub.read_text()
    payload = json.loads(txt[txt.index("=") + 1:].rstrip().rstrip(";"))
    return (payload.get("league") or {}).get("logo")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--league", required=True, choices=list(OUTLOOK))
    ap.add_argument("--season", type=int, default=None,
                    help="target season (default: latest with played matches)")
    ap.add_argument("--sims", type=int, default=20000)
    args = ap.parse_args()
    lid = args.league
    cfg = OUTLOOK[lid]

    # ── Load + feature-build the full history (played only) ───────────────────
    frame = _load_frame(lid, cfg["source"], cfg.get("asa_key"))
    # football-data-intl leagues: the source CSV's refresh cadence varies by
    # country (Brazil tracked live; Japan's file lagged a full season
    # boundary, per docs/league-expansion-report.md's live-verification note)
    # — when the frame's most recent season has NO rows for the season ESPN
    # is already reporting RESULTS for, backfill those ESPN-completed matches
    # onto the frame (goals-only, same _COLS schema) so they count as real
    # played history (ELO/DC/points) instead of being silently dropped when
    # the preseason-flip only asks ESPN for the still-unplayed remainder.
    if cfg["source"] == "footballdata_intl" and lid not in fdi_no_espn:
        try:
            _fdi_cur_max = int(frame[frame["is_result"]]["season"].max())
            _fdi_check = _fdi_cur_max + 1
            if int((frame["season"] == _fdi_check).sum()) == 0:
                _espn_bf = european_fixtures(lid, _fdi_check, use_cache=False)
                _espn_played = _espn_bf[_espn_bf["is_result"]]
                if len(_espn_played):
                    _espn_played = _espn_names_to_fdintl(lid, _espn_played)[_COLS_INTL]
                    frame = pd.concat([frame, _espn_played], ignore_index=True) \
                             .sort_values("date").reset_index(drop=True)
                    print(f"[{lid}] backfilled {len(_espn_played)} ESPN-played "
                          f"matches for season {_fdi_check} (source CSV lagged)")
        except Exception as _bf_err:
            print(f"[{lid}] ESPN played-match backfill skipped: {_bf_err}")
    played_all = frame[frame["is_result"]].copy()
    played_all["home_goals"] = played_all["home_goals"].astype(int)
    played_all["away_goals"] = played_all["away_goals"].astype(int)
    played_all["label_result"] = played_all["label_result"].astype(int)
    max_played_season = int(played_all["season"].max())
    ts = args.season or max_played_season
    df = build_league_features(played_all)
    feat = [c for c in LEAGUE_FEAT_BASE if c in df.columns]

    # ── Pre-season detection: check for ESPN next-season fixtures (understat leagues only) ──
    # When the next season (max_played+1) has a published ESPN schedule but Understat
    # has no rows for it yet, flip to pre-season mode: ts = next season, upcoming from ESPN.
    is_preseason = False
    espn_upcoming = None
    if cfg["source"] == "understat" and args.season is None:
        _next = max_played_season + 1
        try:
            # Live fetch: a parquet cached before ESPN published the schedule
            # is empty and would pin the league to "completed" forever.
            _espn = european_fixtures(lid, _next, use_cache=False)
            _espn_scheduled = _espn[~_espn["is_result"]]
            _understat_has_next = int((frame["season"] == _next).sum()) > 0
            if len(_espn_scheduled) > 0 and not _understat_has_next:
                ts = _next
                espn_upcoming = _espn_scheduled.copy()
                is_preseason = True
                print(f"[{lid}] pre-season mode: ts={ts}, "
                      f"{len(espn_upcoming)} ESPN fixtures found, Understat has no {ts} data yet")
        except Exception as _espn_err:
            print(f"[{lid}] ESPN next-season check failed (staying on {ts}): {_espn_err}")
    elif cfg["source"] == "understat" and args.season is not None:
        # Honor explicit --season; detect pre-season when that season has 0 played in Understat
        _understat_played_ts = int((played_all["season"] == ts).sum())
        if _understat_played_ts == 0:
            try:
                _espn = european_fixtures(lid, ts)
                _espn_scheduled = _espn[~_espn["is_result"]]
                if len(_espn_scheduled) > 0:
                    espn_upcoming = _espn_scheduled.copy()
                    is_preseason = True
                    print(f"[{lid}] pre-season mode (explicit --season {ts}): "
                          f"{len(espn_upcoming)} ESPN fixtures")
            except Exception as _espn_err:
                print(f"[{lid}] ESPN fixtures for season {ts} failed: {_espn_err}")
    elif cfg["source"] == "footballdata":
        # football-data preseason (offseason flip): FD CSVs appear only once a
        # season kicks off, so between seasons the next campaign lives solely
        # in ESPN's schedule. Same detection as understat; ESPN names map back
        # to FD model keys (dc/elo dicts are FD-keyed). Split/playoff rounds
        # (Scotland/Belgium/Greece) aren't scheduled preseason — those sims
        # cover the regular phase only, and the format-group machinery takes
        # over once real rows exist.
        _next = ts + 1 if args.season is None else ts
        if int((played_all["season"] == _next).sum()) == 0:
            try:
                _espn = european_fixtures(lid, _next, use_cache=False)
                _sched = _espn[~_espn["is_result"]]
                if len(_sched) > 0:
                    espn_upcoming = _espn_names_to_fd(lid, _sched)
                    ts = _next
                    is_preseason = True
                    print(f"[{lid}] pre-season mode: ts={ts}, "
                          f"{len(espn_upcoming)} ESPN fixtures (FD-mapped)")
            except Exception as _espn_err:
                print(f"[{lid}] ESPN next-season check failed (staying on {ts}): {_espn_err}")

    # ASA leagues: ASA serves played games only — the scheduled remainder of
    # the season comes from ESPN (mid-season forward sim, NOT preseason mode:
    # A10(b)'s widening correctly stays off once real results exist).
    if cfg["source"] == "asa":
        try:
            # Live fetch (no cache): the scheduled set shrinks every day and a
            # stale parquet would re-list games ASA already has as played.
            _espn = european_fixtures(lid, ts, use_cache=False)
            _sched = _espn[~_espn["is_result"]].copy()
            # Belt-and-braces vs ESPN lag: drop "scheduled" rows dated on/before
            # the last ASA result (a just-finished game ESPN hasn't flipped yet).
            _last_played = frame[frame["season"] == ts]["date"].max()
            if pd.notna(_last_played):
                _sched = _sched[_sched["date"] > _last_played]
            espn_upcoming = _sched
            print(f"[{lid}] ESPN remainder: {len(_sched)} scheduled fixtures for {ts}")
        except Exception as _espn_err:
            print(f"[{lid}] ESPN fixtures for season {ts} failed: {_espn_err}")

    # football-data-intl leagues: the results CSV has no future fixtures
    # (verified 2026-07-10, module docstring), so ESPN always supplies the
    # scheduled remainder of the CURRENT season (ASA's mid-season pattern).
    # NOTE: `ts` already reflects the real current season by this point even
    # when the source CSV lagged a season boundary — the backfill step above
    # (right after `frame = _load_frame(...)`) merges any already-played
    # ESPN matches for the next season into `frame` BEFORE max_played_season/
    # ts are computed, so there is no separate preseason-flip needed (or safe
    # to attempt) here: some leagues (J-League) publish next season's full
    # fixture list many months ahead, so a flip-ahead check at this point
    # would fire mid-season and wrongly treat an in-progress season as done.
    # Skipped entirely for NO_ESPN_SCHEDULE leagues (poland-ekstraklasa).
    if cfg["source"] == "footballdata_intl" and lid not in fdi_no_espn:
        try:
            _espn = european_fixtures(lid, ts, use_cache=False)
            _sched = _espn[~_espn["is_result"]].copy()
            _last_played = frame[frame["season"] == ts]["date"].max()
            if pd.notna(_last_played):
                _sched = _sched[_sched["date"] > _last_played]
            espn_upcoming = _espn_names_to_fdintl(lid, _sched)
            print(f"[{lid}] ESPN remainder: {len(_sched)} scheduled fixtures for {ts} (FDI-mapped)")
        except Exception as _espn_err:
            print(f"[{lid}] ESPN fixtures for season {ts} failed: {_espn_err}")

    # Fixture-override leagues (Finland): results+odds from `source`, but upcoming
    # fixtures from a secondary provider because ESPN has no slug. Only fires when
    # the ESPN paths above found nothing (espn_upcoming still None).
    if espn_upcoming is None and lid in FIXTURE_OVERRIDE:
        try:
            from data_pipeline.api_football import upcoming_fixtures as _apif_upcoming
            _sched = _apif_upcoming(lid)
            _last_played = frame[frame["season"] == ts]["date"].max()
            if pd.notna(_last_played):
                _sched = _sched[_sched["date"] > _last_played]
            espn_upcoming = _sched
            print(f"[{lid}] {FIXTURE_OVERRIDE[lid]} fixtures: {len(_sched)} scheduled for {ts}")
        except Exception as _ovr_err:
            print(f"[{lid}] {FIXTURE_OVERRIDE[lid]} fixture override failed: {_ovr_err}")

    played = df[df["season"] == ts].dropna(subset=["home_goals", "away_goals"]).copy()
    if espn_upcoming is not None:
        upcoming = espn_upcoming
    else:
        upcoming = frame[(frame["season"] == ts) & (~frame["is_result"])].copy()
    print(f"[{lid}] season {ts}: {len(played)} played, {len(upcoming)} upcoming, "
          f"{len(df)} historical matches, {len(feat)} features"
          + (" [PRE-SEASON]" if is_preseason else ""))

    # Team-name resolution: model keys are Understat titles; ESPN crests keyed by
    # displayName. tname() = the display string; tmeta() = its logo/color.
    stub_meta = _stub_team_meta(lid)
    # api_football-source leagues (Canadian PL) have no ESPN crest stub — seed
    # crests from the adapter's own team logos, keyed by API-Football team name.
    if cfg["source"] == "api_football" and not stub_meta:
        try:
            from data_pipeline.api_football import team_logos as _apif_logos
            stub_meta = _apif_logos(lid)
            print(f"[{lid}] api_football crests: {sum(1 for v in stub_meta.values() if v.get('logo'))} logos")
        except Exception as _logo_err:
            print(f"[{lid}] api_football team logos failed: {_logo_err}")
    _fd_map = (FD_ESPN.get(lid, {}) if cfg["source"] in ("footballdata", "asa")
              else FDI_ESPN.get(lid, {}) if cfg["source"] == "footballdata_intl"
              else {})

    def tmeta(key: str) -> dict:
        if cfg["source"] == "understat":
            return stub_meta.get(espn_name(lid, key)) or stub_meta.get(key) or {}
        return stub_meta.get(_fd_map.get(key, key)) or {}

    def tname(key: str) -> str:
        if cfg["source"] == "understat":
            return key
        return _fd_map.get(key, key)

    # ── Ensemble predictions for PLAYED games (in-season Brier + game cards) ───
    # Pre-season: train on ts-2 and earlier; cal on ts-1 (last completed season).
    # The split below uses ts-1 as the cal fold in all cases (pre-season or not).
    train = df[df["season"] < ts - 1].dropna(subset=["home_goals", "away_goals"])
    cal = df[df["season"] == ts - 1].dropna(subset=["home_goals", "away_goals"])
    pe = None
    _dc_T = 1.0  # fallback: no calibration if insufficient data
    if len(train) >= 200 and len(cal) >= 50 and len(played) >= 1:
        y_cal = cal["label_result"].values.astype(int); y_cal_oh = np.eye(3)[y_cal]
        atk0, dfd0, ha0, rho0 = fit_dc(train)
        _dc_cal_raw = dc_predict_batch(cal, atk0, dfd0, ha0, rho0)
        dccal = calibrate_temperature(_dc_cal_raw, y_cal, _dc_cal_raw)
        dcte = calibrate_temperature(_dc_cal_raw, y_cal, dc_predict_batch(played, atk0, dfd0, ha0, rho0))
        _dc_T = fit_temperature_scalar(_dc_cal_raw, y_cal)
        clfs, _ = fit_xgb(train, feat)
        xc = bag_proba(clfs, cal[feat].fillna(0).values)
        xt = bag_proba(clfs, played[feat].fillna(0).values)
        xgbcal = calibrate_temperature(xc, y_cal, xc)
        xgbte = calibrate_temperature(xc, y_cal, xt)
        w = fit_capped_blend(xgbcal, dccal, y_cal_oh)
        pe = blend(xgbte, dcte, w)
    played = played.reset_index(drop=True)

    in_season_brier = {"status": "pending", "n_games": int(len(played))}
    if pe is not None and len(played):
        y_played = played["label_result"].values.astype(int)
        brier_live = float(np.mean(np.sum((pe - np.eye(3)[y_played]) ** 2, axis=1)))
        _freq = np.bincount(train["label_result"].values.astype(int), minlength=3) / len(train)
        naive_live = float(np.mean(np.sum(
            (np.tile(_freq, (len(played), 1)) - np.eye(3)[y_played]) ** 2, axis=1)))
        in_season_brier = {"model": round(brier_live, 4), "naive": round(naive_live, 4),
                           "n_games": int(len(played)),
                           "improve_pct": round((naive_live - brier_live) / naive_live * 100, 2)}
        print(f"[{lid}] in-season {ts} Brier: model {brier_live:.4f} vs naive {naive_live:.4f}")

    # European analog of MLS market-Brier (Understat's own forecast) is a future
    # enhancement — stub it like MLS stubs odds before they accumulate.
    market_brier = {"status": "pending", "n_games": 0,
                    "note": "Understat-forecast baseline not yet wired."}

    # ── Dixon-Coles on ALL played-through-now (forward projection + pmatrix) ───
    # For pre-season mode: fit on all historical data (through ts-1). The DC params
    # are used for the upcoming ESPN fixtures; promoted teams (not in prior season)
    # are seeded with 15th-percentile attack/defence so they project near relegation
    # rather than defaulting to league-average (0 in log-space = exp(0)=1.0 = average).
    allplayed = df.dropna(subset=["home_goals", "away_goals"])
    atk, dfd, ha, rho = fit_dc(allplayed)
    _elo_df, elo_now = compute_elo(allplayed.sort_values("date"), K=25, home_adv=80,
                                   regress=0.40, return_ratings=True,
                                   club_prior_beta=0.75)  # A8: European seeding

    if is_preseason:
        # Identify teams from the prior season (ts-1) as the "established" set.
        _prior_season = df[df["season"] == ts - 1]["home_team"].tolist() + \
                        df[df["season"] == ts - 1]["away_team"].tolist()
        _prior_teams = set(_prior_season)
        # Identify all teams in the upcoming fixtures.
        _upcoming_teams = set(upcoming["home_team"].tolist() + upcoming["away_team"].tolist())
        # Promoted teams = in upcoming but NOT in the prior season.
        _promoted_teams = _upcoming_teams - _prior_teams
        if _promoted_teams:
            # Flat fallback (15th-pct attack, 85th-pct defence) — used when
            # no tier-2 ELO is available for a promoted team.
            _fitted_teams = set(atk.keys()) | set(dfd.keys())
            _atk_vals_all = sorted(atk.get(t, 0.0) for t in _fitted_teams)
            _dfd_vals_all = sorted(dfd.get(t, 0.0) for t in _fitted_teams)
            _p15 = max(0, int(len(_atk_vals_all) * 0.15) - 1)
            _p85 = min(len(_dfd_vals_all) - 1, int(len(_dfd_vals_all) * 0.85))
            _atk_flat = _atk_vals_all[_p15] if _atk_vals_all else -0.2
            _dfd_flat = _dfd_vals_all[_p85] if _dfd_vals_all else 0.2

            _tier2_lid = _TIER2_FOR.get(lid)          # set if lid is a top flight
            _tier2_elo_map = _get_tier_elo_map(_tier2_lid) if _tier2_lid else {}
            _tier1_lid = _TIER1_FOR_BUILD.get(lid)    # set if lid is a second tier
            _tier1_elo_map = _get_tier_elo_map(_tier1_lid) if _tier1_lid else {}

            for _pt in _promoted_teams:
                _fd_name = _FD_TEAM_ALIASES.get(_pt, _pt)
                _t2_elo = _tier2_elo_map.get(_pt) or _tier2_elo_map.get(_fd_name)
                _t1_elo = _tier1_elo_map.get(_pt) or _tier1_elo_map.get(_fd_name)
                if _t2_elo is not None and _tier2_lid is not None:
                    # promoted into a top flight → seed from tier-2 ELO (forward bridge)
                    _adj_elo = _t2_elo + co.tier2_offset(_tier2_lid)
                    atk[_pt], dfd[_pt] = _elo_to_dc_params(_adj_elo, atk, dfd, elo_now)
                    print(f"[{lid}] promoted {_pt}: tier2_elo={_t2_elo:.0f} adj={_adj_elo:.0f} "
                          f"DC=(atk={atk[_pt]:.3f}, dfd={dfd[_pt]:.3f})")
                elif _t1_elo is not None and _tier1_lid is not None:
                    # relegated into a second tier → seed from tier-1 ELO (reverse bridge)
                    _adj_elo = _t1_elo + co.tier1_offset(lid)
                    atk[_pt], dfd[_pt] = _elo_to_dc_params(_adj_elo, atk, dfd, elo_now)
                    print(f"[{lid}] relegated {_pt}: tier1_elo={_t1_elo:.0f} adj={_adj_elo:.0f} "
                          f"DC=(atk={atk[_pt]:.3f}, dfd={dfd[_pt]:.3f})")
                else:
                    atk[_pt] = _atk_flat
                    dfd[_pt] = _dfd_flat
                    print(f"[{lid}] new {_pt}: flat prior "
                          f"atk={_atk_flat:.3f} dfd={_dfd_flat:.3f}")

    def dc_probs(h, a):
        raw = np.array([rm._dc_predict(h, a, atk, dfd, ha, rho)])
        lp = np.log(np.clip(raw, 1e-9, 1.0)) / _dc_T
        lp -= lp.max(axis=1, keepdims=True)
        ep = np.exp(lp)
        p = (ep / ep.sum(axis=1, keepdims=True))[0]
        return (float(p[0]), float(p[1]), float(p[2]))

    def dc_lam_mu(h, a):
        import math
        return (math.exp(atk.get(h, 0) + dfd.get(a, 0) + ha),
                math.exp(atk.get(a, 0) + dfd.get(h, 0)))

    # ── Current ELO (champion config) + standings from this season's results ──
    # Playoff/knockout rows never count toward the regular-season table (ASA
    # marks them via knockout_game; every other source emits is_playoff=0, so
    # this filter is a no-op outside the ASA leagues).
    pts, gp, gf, ga, xgf, xga = {}, {}, {}, {}, {}, {}
    for _, r in played[played["is_playoff"].fillna(0).astype(int) == 0].iterrows():
        h, a = r["home_team"], r["away_team"]
        hg, ag = int(r["home_goals"]), int(r["away_goals"])
        hx, ax = float(np.nan_to_num(r["home_xg"])), float(np.nan_to_num(r["away_xg"]))
        for t in (h, a):
            gp[t] = gp.get(t, 0) + 1
        gf[h] = gf.get(h, 0) + hg; ga[h] = ga.get(h, 0) + ag
        gf[a] = gf.get(a, 0) + ag; ga[a] = ga.get(a, 0) + hg
        xgf[h] = xgf.get(h, 0) + hx; xga[h] = xga.get(h, 0) + ax
        xgf[a] = xgf.get(a, 0) + ax; xga[a] = xga.get(a, 0) + hx
        if hg > ag: pts[h] = pts.get(h, 0) + 3
        elif hg < ag: pts[a] = pts.get(a, 0) + 3
        else: pts[h] = pts.get(h, 0) + 1; pts[a] = pts.get(a, 0) + 1

    has_xg = bool(len(played) > 0 and played["home_xg"].notna().any())

    # ── Upcoming fixtures → game cards + remaining-sim inputs ──────────────────
    # F1/F2 (2026-07-09): kickoff/venue ride along when the fixture source is
    # ESPN (nullable extras); weather is fetched only for the next 7 days.
    from data_pipeline.weather import kickoff_weather
    _wx_horizon = pd.Timestamp.now() + pd.Timedelta(days=7)
    remaining, upcoming_cards = [], []
    for _, r in upcoming.sort_values("date").iterrows():
        h, a = r["home_team"], r["away_team"]
        pH, pD, pA = dc_probs(h, a)
        lam, mu = dc_lam_mu(h, a)
        _s = lambda v: v if (isinstance(v, str) and v) else None  # NaN → None
        _ko, _venue, _city = _s(r.get("ko_utc")), _s(r.get("venue")), _s(r.get("venue_city"))
        _wx = None
        if _ko and _city and r["date"] <= _wx_horizon:
            _wx = kickoff_weather(_city, _ko)
        upcoming_cards.append({"id": len(remaining), "date": r["date"].strftime("%Y-%m-%d"),
                               "home": tname(h), "away": tname(a),
                               "pH": round(pH, 3), "pD": round(pD, 3), "pA": round(pA, 3),
                               "lam": round(lam, 2), "mu": round(mu, 2),
                               "hg": None, "ag": None, "result": None,
                               "ko": _ko, "venue": _venue, "wx": _wx,
                               "hlogo": tmeta(h).get("logo"), "alogo": tmeta(a).get("logo"),
                               "hcolor": tmeta(h).get("color"), "acolor": tmeta(a).get("color")})
        remaining.append((h, a))

    # universe = teams that appear in this season's results or remaining fixtures
    tids = sorted({t for t in pts} | {t for fx in remaining for t in fx})
    idx = {t: i for i, t in enumerate(tids)}; nT = len(tids)
    base_pts = np.array([pts.get(t, 0) for t in tids], dtype=float)
    base_gd = np.array([gf.get(t, 0) - ga.get(t, 0) for t in tids], dtype=float)

    # C1 format leagues (Scottish split / Belgian points-halving / Greek playoff
    # round): the raw points table is NOT the official classification. Override
    # points with the carry-transformed totals and rank inside classification
    # groups (a bottom-six team can never classify above the split line). The
    # group constraint only binds once the regular phase is complete — before
    # that the classification equals the plain table.
    _fmt = FORMATS.get(lid)
    _grp_bonus = np.zeros(nT)
    _grp_of = None
    if _fmt is not None and len(played):
        _cls = format_classification(played.sort_values("date"), _fmt, tids)
        base_pts = np.array([_cls[t]["pts"] for t in tids], dtype=float)
        base_gd = np.array([_cls[t]["gd"] for t in tids], dtype=float)
        _reg_games = _fmt["rr"] * (nT - 1)
        _reg_complete = bool(regular_phase_mask(
            played.sort_values("date"), _reg_games).sum() >= _reg_games * nT / 2)
        if _reg_complete:
            _grp_of = {t: _cls[t]["group"] for t in tids}
            _grp_bonus = np.array([-_cls[t]["group"] * 1e7 for t in tids])

    # Pairing-probability matrix (powers the client what-if sim; row = host)
    PM = np.zeros((nT, nT, 3))
    for hi, th in enumerate(tids):
        for ai, ta in enumerate(tids):
            if hi != ai:
                PM[hi, ai] = dc_probs(th, ta)

    # ── Monte-Carlo: current pts + simulate remaining → SINGLE final table ────
    rng = np.random.default_rng(42)
    RP = np.array([dc_probs(h, a) for (h, a) in remaining]) if remaining else np.zeros((0, 3))
    RH = np.array([idx[h] for (h, a) in remaining], dtype=int)
    RA = np.array([idx[a] for (h, a) in remaining], dtype=int)
    N = args.sims
    buckets = cfg["buckets"]
    counts = {b["key"]: np.zeros(nT) for b in buckets}
    proj = np.zeros(nT); rank_sum = np.zeros(nT)
    # A10(b) + decay (2026-07-07): per-sim strength perturbations δ_t ~ N(0, σ)
    # with σ = PRESEASON_SIGMA · (1 − season_fraction) — full widening at
    # preseason, shrinking as evidence accrues, zero once the season is done.
    # Decay confirmed on the season-outcome replay at both seeds (releg Brier
    # −0.0015 at the 25% checkpoint, no regression anywhere); the earlier
    # preseason-only cutoff was the special case f=0. γ gap-scaling remains
    # judged-and-dropped (big-5 cohort replay).
    # M4: per-conference bucket support. Conference membership from ESPN's
    # standings groups (display names mapped back to model keys via FD_ESPN);
    # a failed fetch falls back to each bucket's pooled `top` definition.
    _conf_arrays = None
    if cfg.get("conference_slug") and any("per_conf_top" in b for b in buckets):
        try:
            from data_pipeline.http import espn_get
            _st = espn_get("https://site.api.espn.com/apis/v2/sports/soccer/"
                           f"{cfg['conference_slug']}/standings", {})
            _inv = {v: k for k, v in FD_ESPN.get(lid, {}).items()}
            _groups = []
            for _child in _st.get("children", []):
                _members = [idx[_inv.get(e["team"]["displayName"],
                                         e["team"]["displayName"])]
                            for e in _child.get("standings", {}).get("entries", [])
                            if _inv.get(e["team"]["displayName"],
                                        e["team"]["displayName"]) in idx]
                if _members:
                    _groups.append(np.array(_members, dtype=int))
            if len(_groups) >= 2 and sum(len(g) for g in _groups) >= nT - 2:
                _conf_arrays = _groups
                print(f"[{lid}] conferences: " +
                      " · ".join(str(len(g)) for g in _groups) + " teams")
        except Exception as _conf_err:
            print(f"[{lid}] conference fetch failed (pooled fallback): {_conf_err}")

    # M2/A10(a) (2026-07-07, KEEP at both seeds on the outcome replay):
    # preseason value-informed strength correction, BOTTOM-HALF-rated teams
    # only. Fit log(squad value of ts-1) → current ELO, tilt fixture log-odds
    # by β·(value_elo − elo) for teams rated at/below the league median —
    # relegation Brier −0.0055 with title flat (an untargeted tilt drags
    # title odds toward the richest club: +0.005 title, rejected).
    if is_preseason and len(remaining):
        try:
            from scripts.eval.tm_value_backfill import OUT as _VOUT, TM_TO_FD, map_to_fd
            import math as _math
            if _VOUT.exists():
                _vals = pd.read_csv(_VOUT)
                _vals = _vals[_vals["league"] == lid]
                if len(_vals):
                    _vmap = {(t2, s): v for (l2, t2, s), v in map_to_fd(
                        _vals, {lid: set(tids) | set(atk)}, aliases=TM_TO_FD).items()}
                    _xs, _ys = [], []
                    for _t, _r in elo_now.items():
                        _v = _vmap.get((_t, ts - 1))
                        if _v and _v > 0:
                            _xs.append(_math.log(_v)); _ys.append(_r)
                    if len(_xs) >= 6 and float(np.std(_xs)) > 1e-9:
                        _b, _a = np.polyfit(np.array(_xs), np.array(_ys), 1)
                        _med = float(np.median([elo_now.get(t, 1500.0) for t in tids]))
                        _vdelta = np.zeros(nT)
                        _VALUE_BETA = 0.5
                        for _i, _t in enumerate(tids):
                            _vn = _vmap.get((_t, ts))
                            if _vn and _vn > 0 and _t in elo_now and elo_now[_t] <= _med:
                                _vdelta[_i] = _VALUE_BETA * (
                                    (_a + _b * _math.log(_vn)) - elo_now[_t])
                        if _vdelta.any():
                            RP = perturb_probs(np.log(np.clip(RP, 1e-12, 1.0)),
                                               RH, RA, _vdelta)
                            print(f"[{lid}] value tilt applied to "
                                  f"{int((_vdelta != 0).sum())} bottom-half teams")
        except Exception as _vt_err:
            print(f"[{lid}] value tilt skipped: {_vt_err}")

    _season_frac = (len(played) / (len(played) + len(remaining))
                    if (len(played) + len(remaining)) else 1.0)
    _sigma_eff = preseason_sigma_for_source(cfg["source"]) * (1.0 - _season_frac)
    _widen = _sigma_eff > 1.0 and len(remaining) > 0
    _LRP = np.log(np.clip(RP, 1e-12, 1.0)) if _widen else None
    print(f"[{lid}] simulating {N:,} seasons · {len(remaining)} remaining · {nT} teams..."
          + (f" [widening σ={_sigma_eff:.0f}]" if _widen else ""))
    for _ in range(N):
        p = base_pts.copy()
        if len(remaining):
            if _widen:
                _delta = rng.standard_normal(nT) * _sigma_eff
                _RP = perturb_probs(_LRP, RH, RA, _delta)
            else:
                _RP = RP
            u = rng.random(len(remaining))
            o = np.where(u < _RP[:, 0], 0, np.where(u < _RP[:, 0] + _RP[:, 1], 1, 2))
            np.add.at(p, RH[o == 0], 3)
            np.add.at(p, RH[o == 1], 1); np.add.at(p, RA[o == 1], 1)
            np.add.at(p, RA[o == 2], 3)
        proj += p
        # Final ranking: [format group when applicable] → points → current real
        # GD → random (tie jitter)
        key = _grp_bonus + p * 10000 + base_gd * 10 + rng.random(nT) * 10
        order = np.argsort(-key)  # best first
        for b in buckets:
            if "promo_top" in b:
                # composite Promoted = auto spots + simulated playoff winner
                # (× barrage survival rate when the final hurdle is cross-league)
                counts[b["key"]][order[:b["promo_top"]]] += 1
                _band = b["playoff_band"]
                _seeds = list(order[_band[0] - 1:_band[1]])
                if _seeds and rng.random() < b.get("barrage_win_rate", 1.0):
                    counts[b["key"]][_promo_playoff_winner(_seeds, PM, rng)] += 1
            elif _conf_arrays is not None and "per_conf_top" in b:
                counts[b["key"]][_per_conf_members(key, _conf_arrays,
                                                   b["per_conf_top"])] += 1
            else:
                counts[b["key"]][_bucket_idx(b, order, nT)] += 1
        rank_sum[order] += np.arange(1, nT + 1)

    standings = []
    for t in tids:
        i = idx[t]
        row = {"team": tname(t),
               "pts": int(base_pts[i]), "gp": gp.get(t, 0),
               "gd": int(round(gf.get(t, 0) - ga.get(t, 0))),
               "proj_pts": round(proj[i] / N, 1),
               "proj_rank": round(rank_sum[i] / N, 1),
               "elo": int(round(elo_now.get(t, 1500))),
               "logo": tmeta(t).get("logo"), "color": tmeta(t).get("color")}
        for b in buckets:
            row[b["key"]] = round(counts[b["key"]][i] / N * 100, 1)
        row["xgd"] = round(xgf.get(t, 0) - xga.get(t, 0), 1) if has_xg else None
        if _grp_of is not None:
            row["grp"] = _grp_of[t]   # classification group (0 = championship)
        standings.append(row)
    standings.sort(key=lambda s: (s.get("grp", 0), -s["pts"], -s["gd"], -s["proj_pts"]))

    # ── Per-team current model inputs (latest rolling snapshot) ───────────────
    team_inputs = {}
    _df_s = df.sort_values("date")
    _input_cols = {"xg_for": ("home_xg_roll_5", "away_xg_roll_5"),
                   "xg_against": ("home_xga_roll_5", "away_xga_roll_5"),
                   "form": ("home_form_5", "away_form_5")}
    for t in tids:
        _rows = _df_s[(_df_s["home_team"] == t) | (_df_s["away_team"] == t)]
        if _rows.empty:
            continue
        _last = _rows.iloc[-1]; _is_home = _last["home_team"] == t
        snap = {"elo": int(round(elo_now.get(t, 1500)))}
        for _lab, (_hc, _ac) in _input_cols.items():
            _v = _last.get(_hc if _is_home else _ac)
            snap[_lab] = round(float(_v), 3) if _v is not None and pd.notna(_v) else None
        team_inputs[tname(t)] = snap

    # B9: full model-input snapshot (canonical suffix superset, family-grouped,
    # explicit null for suffixes this league's pipeline never computes — e.g.
    # gk_z/avail_share don't exist for European leagues at all — or that a
    # given team has no played rows for, e.g. goals-only leagues' xG columns).
    team_inputs_full = build_team_inputs_full(df, feat, tids, tname)

    # U4 (2026-07-07): "is this team for real?" panel inputs — three
    # position-vs-underlying signals, all null-safe:
    #   gap:      A7 club-prior gap (own 3-season ELO history − current rating;
    #             positive = fallen giant, results below the club's level)
    #   xg_delta: goals-for − xG-for this season (positive = finishing hot /
    #             results ahead of underlying numbers); null preseason
    #   value_rank_gap: squad-value rank − current table rank (positive =
    #             the market rates this squad higher than the table does)
    from scripts.eval.club_prior import club_prior_gap, elo_history_from_matches
    for_real = {}
    try:
        _hist = elo_history_from_matches(_elo_df)
        _gaps = club_prior_gap(_hist)
        for t in tids:
            _g = _gaps.get((t, ts))
            if _g is None:
                # preseason: ts has no rows in the history yet — compute the
                # A7 gap directly (mean of last ≤3 end-of-season ELOs − current
                # rating), same ≥2-prior-seasons guard as club_prior_gap.
                _rows = _hist[_hist["team"] == t].sort_values("season").tail(3)
                if len(_rows) >= 2 and t in elo_now:
                    _g = float(_rows["end_elo"].mean() - elo_now[t])
            _xgd = (round((gf.get(t, 0) - xgf.get(t, 0)), 1)
                    if has_xg and gp.get(t, 0) else None)
            for_real[tname(t)] = {
                "gap": round(float(_g), 0) if _g is not None else None,
                "xg_delta": _xgd,
            }
    except Exception as _fr_err:
        print(f"[{lid}] for_real panel skipped: {_fr_err}")

    # ── ELO history (full Understat depth, 2014+) per team, downsampled ───────
    # R2 (2026-07-09, "the Hull City jump"): a club's chart line used to freeze
    # while it played in another division, then jump on return. Stitch the
    # club's seasons from neighboring tiers (offset onto this league's scale
    # with the fitted promotion/relegation offsets) so the line is continuous.
    _neighbors = [(nlid, noff, _tier_elo_series(nlid))
                  for nlid, noff in _neighbor_tier_offsets(lid).items()]
    elo_hist = {}
    for t in tids:
        _hm = _elo_df[_elo_df["home_team"] == t][["date", "home_elo"]].rename(columns={"home_elo": "elo"})
        _aw = _elo_df[_elo_df["away_team"] == t][["date", "away_elo"]].rename(columns={"away_elo": "elo"})
        _ser = pd.concat([_hm, _aw]).sort_values("date")
        if _ser.empty:
            continue
        _pairs = list(zip(_ser["date"], _ser["elo"]))
        for _nlid, _noff, _nser in _neighbors:
            for _cand in {t, tname(t),
                          _FD_TEAM_ALIASES.get(t, t), _FD_TEAM_ALIASES.get(tname(t), tname(t))}:
                if _cand in _nser:
                    _pairs += [(d, e + _noff) for d, e in _nser[_cand]]
                    break
        _pairs.sort(key=lambda p: p[0])
        _step = max(1, len(_pairs) // 120)
        elo_hist[tname(t)] = [[d.strftime("%Y-%m-%d"), int(round(e))]
                              for d, e in _pairs[::_step]]

    # ── Market prob lookup for per-game edge display (football-data + understat leagues) ─
    from models.research_model import walk_forward_predictions
    from data_pipeline.football_data import DIV as _FD_DIV, attach_market as _fd_attach_market
    from data_pipeline.football_data_intl import (
        COUNTRY as _FDI_COUNTRY, attach_market as _fdi_attach_market)
    # One dispatcher covers both football-data adapters (old per-season-file
    # DIV leagues + the Tier-1 single-file-all-seasons COUNTRY leagues) — every
    # downstream caller just checks `lid in _has_market` / calls `attach_market`.
    _has_market = set(_FD_DIV) | set(_FDI_COUNTRY)
    attach_market = _fdi_attach_market if lid in _FDI_COUNTRY else _fd_attach_market
    _game_mkt: dict[tuple[str, str], dict] = {}
    if lid in _has_market:
        try:
            _mkt_frame = attach_market(
                played[["season", "home_team", "away_team"]].copy(), lid, [ts])
            for _, _mr in _mkt_frame[_mkt_frame["mkt_home"].notna()].iterrows():
                _game_mkt[(_mr["home_team"], _mr["away_team"])] = {
                    "mkt_home": float(_mr["mkt_home"]),
                    "mkt_draw": float(_mr["mkt_draw"]),
                    "mkt_away": float(_mr["mkt_away"]),
                }
        except Exception as _e:
            print(f"[{lid}] game market lookup failed: {_e}")

    # ── Game cards: played (ensemble if available, else DC) + upcoming ────────
    # Postgame win expectancy (2026-07-14 feedback: "how deserved was this
    # result" — Bill-Connelly-style, from scripts/postgame_win_expectancy.py).
    # Closed-form logistic model fit+validated per xG source family; only
    # Understat (big-5) and ASA (MLS/NWSL/USLC) sources were ever fit or
    # calibration-tested, so every other league's games simply carry no
    # postgame_we fields rather than misapplying a coefficient set calibrated
    # for a different xG scale.
    _we_family = {"understat": "understat", "asa": "asa"}.get(cfg["source"])
    _we_available = _we_family is not None and Path("experiments/postgame_we_report.json").exists()

    games = []
    for i, r in played.iterrows():
        h, a = r["home_team"], r["away_team"]
        res = "H" if r["home_goals"] > r["away_goals"] else "D" if r["home_goals"] == r["away_goals"] else "A"
        _lam, _mu = dc_lam_mu(h, a)
        if pe is not None:
            pH, pD, pA = float(pe[i, 0]), float(pe[i, 1]), float(pe[i, 2])
        else:
            pH, pD, pA = dc_probs(h, a)
        _mg = _game_mkt.get((h, a), {})
        _hxg, _axg = r.get("home_xg"), r.get("away_xg")
        _has_row_xg = _we_available and pd.notna(_hxg) and pd.notna(_axg)
        _we_h = compute_we(float(_hxg), float(_axg), _we_family) if _has_row_xg else None
        _we_a = compute_we(float(_axg), float(_hxg), _we_family) if _has_row_xg else None
        games.append({"date": r["date"].strftime("%Y-%m-%d"), "home": tname(h), "away": tname(a),
                      "pH": round(pH, 3), "pD": round(pD, 3), "pA": round(pA, 3),
                      "lam": round(_lam, 2), "mu": round(_mu, 2),
                      "hg": int(r["home_goals"]), "ag": int(r["away_goals"]), "result": res,
                      "hlogo": tmeta(h).get("logo"), "alogo": tmeta(a).get("logo"),
                      "hcolor": tmeta(h).get("color"), "acolor": tmeta(a).get("color"),
                      "mkt_home": round(_mg["mkt_home"], 3) if "mkt_home" in _mg else None,
                      "mkt_draw": round(_mg["mkt_draw"], 3) if "mkt_draw" in _mg else None,
                      "mkt_away": round(_mg["mkt_away"], 3) if "mkt_away" in _mg else None,
                      "edge_home": round((pH - _mg["mkt_home"]) * 100, 1) if "mkt_home" in _mg else None,
                      "edge_draw": round((pD - _mg["mkt_draw"]) * 100, 1) if "mkt_draw" in _mg else None,
                      "edge_away": round((pA - _mg["mkt_away"]) * 100, 1) if "mkt_away" in _mg else None,
                      "hxg": round(float(_hxg), 2) if pd.notna(_hxg) else None,
                      "axg": round(float(_axg), 2) if pd.notna(_axg) else None,
                      "we_h": _we_h, "we_a": _we_a})
    games += upcoming_cards
    games.sort(key=lambda g: g["date"])

    # ── Per-year model vs naive vs market (walk-forward predictions + bookmaker odds) ──
    # Per-match model probs let us score the model, the base-rate naive, AND the
    # betting market on the SAME matched matches per season — a fair "are we beating
    # the bookies?" read. Market odds from football-data.co.uk (Pinnacle/market-avg).
    perf_by_year = []
    backtest = None
    market_view = None
    try:
        # ESPN leagues use sequential season IDs (1-N), not calendar years.
        # Use last 8 seasons for eval (skip first 2 which lack enough training history).
        # European leagues keep the curated year list (intentionally skips 2018/2020).
        if cfg["source"] == "espn":
            _all_sids = sorted(set(df["season"]))
            _pyears = _all_sids[2:]  # skip first 2 torneos (insufficient training data)
        elif cfg.get("eval_seasons") is not None:
            _pyears = [y for y in cfg["eval_seasons"] if y in set(df["season"])]
        else:
            _pyears = [y for y in (2017, 2019, 2021, 2022, 2023, 2024, 2025)
                       if y in set(df["season"])]
        _preds, _ = walk_forward_predictions(df, feat, _pyears, n_bags=1)
        # Short-history leagues (e.g. Canadian PL: only 3 free API-Football seasons)
        # can't produce walk-forward predictions for any test year → empty frame with
        # no 'season' column. Skip the per-year accuracy diagnostic gracefully.
        if _preds.empty or "season" not in _preds.columns:
            _pyears = []
        if lid in _has_market and not _preds.empty:
            _preds = attach_market(_preds, lid, _pyears)
        _has_mkt = "mkt_home" in _preds.columns
        for _y in _pyears:
            _g = _preds[_preds["season"] == _y]
            if _g.empty:
                continue
            _yoh = np.eye(3)[_g["label_result"].values.astype(int)]
            _model_b = float(np.mean(np.sum(
                (_g[["prob_home", "prob_draw", "prob_away"]].values - _yoh) ** 2, axis=1)))
            _tr = df[df["season"] < _y - 1].dropna(subset=["label_result"])
            _fq = np.bincount(_tr["label_result"].values.astype(int), minlength=3) / max(len(_tr), 1)
            _nb = float(np.mean(np.sum((np.tile(_fq, (len(_g), 1)) - _yoh) ** 2, axis=1)))
            # label: human-readable for accuracy card. liga_mx_label decodes a
            # sequential Apertura/Clausura torneo index (liga-mx's own season
            # numbering) into "Cl.2026"/"Ap.2026" — it does NOT apply to other
            # source="espn" leagues, whose `season` is a real calendar year
            # (Saudi/A-League/WSL, and round-5's South America/Thailand/Eerste
            # Divisie); feeding a real year like 2026 through it previously
            # produced nonsense labels like "Ap.3028" (bug found + fixed
            # 2026-07-14 while shipping round 5 — see league-expansion-report.md).
            _label = liga_mx_label(_y) if lid == "liga-mx" else str(_y)
            _rec = {"year": _y, "label": _label,
                    "model": round(_model_b, 4), "naive": round(_nb, 4),
                    "improve_pct": round((_nb - _model_b) / _nb * 100, 2)}
            if _has_mkt and int(_g["mkt_home"].notna().sum()) >= 20:
                _gm = _g[_g["mkt_home"].notna()]
                _ym = np.eye(3)[_gm["label_result"].values.astype(int)]
                _mkt_b = float(np.mean(np.sum(
                    (_gm[["mkt_home", "mkt_draw", "mkt_away"]].values - _ym) ** 2, axis=1)))
                _mm = float(np.mean(np.sum(  # model on the SAME matched matches (fair)
                    (_gm[["prob_home", "prob_draw", "prob_away"]].values - _ym) ** 2, axis=1)))
                _rec["market"] = round(_mkt_b, 4)
                _rec["edge_pct"] = round((_mkt_b - _mm) / _mkt_b * 100, 2)
            perf_by_year.append(_rec)
        print(f"[{lid}] perf by year: {[(p['label'], p['model'], p.get('market')) for p in perf_by_year]}")

        # ── Edge backtest: flat-bet ROI for matches where model edge ≥ threshold ──
        # Uses walk-forward held-out predictions + de-vigged market probs.
        # "Fair odds" = 1/mkt_p (conservative: de-vigged, ~3-5% better than real Pinnacle).
        _THRESH = 8.0
        backtest = None
        market_view = None
        if _has_mkt and not _preds.empty:
            _br = []
            _all_bets = []   # every positive-edge bet, for the ROI-by-bucket table (B5)
            for _, _r in _preds[_preds["mkt_home"].notna()].iterrows():
                for _oc, _mp, _mkp in [
                    ("home", float(_r["prob_home"]), float(_r["mkt_home"])),
                    ("draw", float(_r["prob_draw"]), float(_r["mkt_draw"])),
                    ("away", float(_r["prob_away"]), float(_r["mkt_away"])),
                ]:
                    if _mkp <= 0:
                        continue
                    _edge = (_mp - _mkp) * 100
                    _won = int(_r["label_result"]) == {"home": 0, "draw": 1, "away": 2}[_oc]
                    _fair_odds = 1.0 / _mkp
                    if _edge >= 0:
                        _all_bets.append({"outcome": _oc, "edge": _edge, "won": _won,
                                          "pnl": (_fair_odds - 1.0) if _won else -1.0})
                    if _edge < _THRESH:
                        continue
                    _lbl = liga_mx_label(int(_r["season"])) if lid == "liga-mx" else str(int(_r["season"]))
                    _br.append({"season": int(_r["season"]), "label": _lbl,
                                 "outcome": _oc, "edge": _edge,
                                 "won": _won, "pnl": (_fair_odds - 1.0) if _won else -1.0})
            # B5: ROI by edge bucket (0–4 / 4–8 / 8+), plus a draw-only 8+ slice —
            # the honest trust anchor for the market view (negative ROI shown as-is).
            _abdf = pd.DataFrame(_all_bets)
            if not _abdf.empty:
                _buckets = []
                for _lo, _hi, _blbl in [(0, 4, "0–4%"), (4, 8, "4–8%"), (8, None, "8%+")]:
                    _bk = _abdf[(_abdf["edge"] >= _lo) &
                                ((_abdf["edge"] < _hi) if _hi else True)]
                    if len(_bk):
                        _buckets.append({"bucket": _blbl, "n": int(len(_bk)),
                                         "roi": round(float(_bk["pnl"].mean()), 3),
                                         "win_rate": round(float(_bk["won"].mean()), 3)})
                _dr = _abdf[(_abdf["edge"] >= _THRESH) & (_abdf["outcome"] == "draw")]
                market_view = {
                    "buckets": _buckets,
                    "n_matched_games": int(_preds["mkt_home"].notna().sum()),
                    "draw_8plus": ({"n": int(len(_dr)),
                                    "roi": round(float(_dr["pnl"].mean()), 3)}
                                   if len(_dr) else None),
                    "note": "flat-stake ROI at fair (de-vigged) odds, walk-forward "
                            "held-out predictions; draw-side Kelly suppressed until "
                            "A11 lands a draw-structure KEEP"}
            if _br:
                _bdf = pd.DataFrame(_br)
                _n = len(_bdf)
                _by_s = [
                    {"year": int(_sy),
                     "label": _bdf[_bdf["season"] == _sy]["label"].iloc[0],
                     "n_bets": len(_sg := _bdf[_bdf["season"] == _sy]),
                     "win_rate": round(float(_sg["won"].mean()), 3),
                     "roi": round(float(_sg["pnl"].sum() / len(_sg)), 3)}
                    for _sy in sorted(_bdf["season"].unique())
                ]
                backtest = {
                    "threshold_pct": _THRESH,
                    "n_bets": _n,
                    "win_rate": round(float(_bdf["won"].mean()), 3),
                    "roi": round(float(_bdf["pnl"].sum() / _n), 3),
                    "avg_edge_pct": round(float(_bdf["edge"].mean()), 1),
                    "by_season": _by_s,
                    "note": "flat-stake ROI at fair (de-vigged) odds; ~3-5% conservative vs. Pinnacle"}
                print(f"[{lid}] edge backtest: {_n} bets, "
                      f"win_rate={backtest['win_rate']:.3f}, roi={backtest['roi']:+.3f}")
    except Exception as _e:
        import traceback
        traceback.print_exc()
        print(f"[{lid}] perf_by_year/backtest failed: {_e}")
        backtest = None
        market_view = None

    # Headline league Brier = mean of the recent walk-forward folds.
    # ESPN leagues: recent = last 8 torneos (4 years). Others: 2022+.
    if cfg["source"] == "espn" and perf_by_year:
        _cutoff = sorted(p["year"] for p in perf_by_year)[-8] if len(perf_by_year) >= 8 else 0
        _recent = [p for p in perf_by_year if p["year"] >= _cutoff]
    else:
        _recent = [p for p in perf_by_year if p["year"] >= 2022]
    league_brier = round(float(np.mean([p["model"] for p in _recent])), 4) if _recent else None
    league_naive = round(float(np.mean([p["naive"] for p in _recent])), 4) if _recent else None
    _recent_mkt = [p for p in _recent if p.get("market") is not None]
    league_market = round(float(np.mean([p["market"] for p in _recent_mkt])), 4) if _recent_mkt else None
    if _recent_mkt:
        market_brier = {"status": "ok", "market": league_market, "model": league_brier,
                        "edge_pct": round(float(np.mean([p["edge_pct"] for p in _recent_mkt])), 2),
                        "n_years": len(_recent_mkt), "source": "football-data.co.uk (Pinnacle/avg)"}

    # ── Model-health block: league-agnostic feature families ──────────────────
    _FAMS = {"ELO": [c for c in feat if "elo" in c],
             "xG rolling": [c for c in feat if "xg" in c and "elo" not in c],
             "Form": [c for c in feat if "form" in c],
             "is_playoff": [c for c in feat if c == "is_playoff"]}
    _rows = df[df["season"] == ts]
    health = {"frame_file": f"{cfg['source']}:{lid}", "espn_ok": bool(stub_meta),
              "season_rows": int(len(_rows)), "played_rows": int(len(played)),
              "features": [{"family": fam, "cols": len(cols),
                            **health_feature_stats(_rows, cols)}
                           for fam, cols in _FAMS.items() if cols]}

    model_card = {
        "arch": ["Dixon-Coles", "Temperature", "XGBoost ×5 bag", "Capped-DC blend", "Temperature"],
        "forward_arch": ["Dixon-Coles", "Temperature"],
        "config": {"ELO K": 25, "Home adv": 80, "Season regress": "40% → club prior (β=0.75)", "DC decay": "120d",
                   "XGB weight ½-life": "6 seasons", "Seed bag": 5,
                   "xG / form windows": "3 · 5 · 10 · 15", "features": len(feat)},
        "per_class": {}, "n_test": None}

    try:
        git_commit = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], stderr=subprocess.DEVNULL).decode().strip()
    except Exception:
        git_commit = "unknown"

    pct = round(len([g for g in games if g["result"]]) / max(1, len(games)) * 100)
    _sstate = season_state(len(played), len(upcoming))
    _season_label = f"{ts}-{str(ts + 1)[2:]}" if is_preseason else None
    # Top-level route state (see docs/CURRENT_STATE.md § Route State Taxonomy).
    # Derived from the same match-count classification used for `in_season`, so the
    # webapp can branch on one canonical field instead of inferring from outlook.*.
    _route_status = {PRESEASON: "preseason", IN_PROGRESS: "live",
                     CONCLUDED: "completed"}.get(_sstate, "live")
    data = {
        "status": _route_status,
        "league": {"id": lid, "name": cfg["name"], "logo": _stub_league_logo(lid),
                   "confederation": cfg.get("confederation", "UEFA"),
                   "status": "live", "pct_complete": pct},
        "outlook": {"mode": "table", "n_teams": cfg["n"],
                    "green_line": cfg.get("green_line"),
                    "red_line": cfg.get("red_line"),
                    "has_xg": has_xg,
                    "preseason": True if is_preseason else None,
                    "season_label": _season_label,
                    "rules": cfg.get("rules"),
                    "cards": [{"key": b["key"], "label": b["label"]}
                              for b in buckets if b.get("card", True)],
                    "columns": [{"key": b["key"], "label": b.get("col", b["label"]),
                                 **{k: b[k] for k in ("top", "bottom", "band", "promo_top",
                                                      "playoff_band", "barrage_win_rate")
                                    if k in b}}
                                for b in buckets]},
        "perf_by_year": perf_by_year,
        "season": ts, "in_season": _sstate == IN_PROGRESS,
        "played": len(games) - len(upcoming_cards), "upcoming": len(upcoming_cards),
        "sim": {"teams": [tname(t) for t in tids],
                "pmatrix": [[None if hi == ai else
                             [int(round(PM[hi, ai, k] * 1000)) for k in range(3)]
                             for ai in range(nT)] for hi in range(nT)]},
        "in_season_brier": in_season_brier,
        "market_brier": market_brier,
        "team_inputs": team_inputs,
        "team_inputs_full": team_inputs_full,
        # B9 squad-value panel (A9): freshest TM snapshot for this league, team-level
        # aggregates keyed on canonical names; None (the "not available" state) when
        # no mapped CSV exists for the league — same convention as the model-input
        # nulls above, the frontend renders the honest empty treatment either way.
        "squad_value": build_squad_value_league(lid, {tname(t) for t in tids}),
        "for_real": for_real,   # U4: value_rank_gap joined client-side (squad_value + standings)
        "elo_history": elo_hist,
        "trophies": {},   # European trophy data is a future enhancement
        "health": health,
        "model_card": model_card,
        # B4 "Model Trust" slices (A1/A3) are sourced from the MLS champion report —
        # no per-league-family champion report exists yet (that's C2's per-family
        # champion pointer work). Explicit null rather than borrowing MLS's
        # calibration numbers for a European league they don't describe.
        "trust": None,
        # U1 (2026-07-07): season-outcome skill by checkpoint from the replay
        # baseline — how much better than base rates the title/promo/releg odds
        # are, and when they become trustworthy. None → honest empty state.
        "outcome_skill": outcome_skill_block(lid),
        "model": {"best_brier": league_brier, "naive": league_naive, "market": league_market,
                  "improve_pct": round((league_naive - league_brier) / league_naive * 100, 2)
                  if league_brier and league_naive else None,
                  "edge_pct": market_brier.get("edge_pct") if market_brier.get("status") == "ok" else None,
                  "cal_err": None, "name": "research_model", "metric": "brier_sum_form"},
        "n_sims": N,
        "value_layer": {
            "backtest": backtest,
            "market_view": market_view,  # B5: ROI-by-edge-bucket + matched-game count
            "value_bets": [],  # upcoming matches with edge >= threshold; requires live odds
        },
        "standings": standings, "games": games,
        "generated": pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%d %H:%M UTC"),
        "provenance": {"git_commit": git_commit, "model_file": "models/research_model.py",
                       "data_source": f"{cfg['source']}:{lid}",
                       "metric_convention": "brier_sum_form (range 0-2; random ~0.64); "
                                            "league avg = recent walk-forward folds"}}

    out = Path(f"webapp/data/{lid}.js")
    write_js_payload(out, "LEAGUE_DATA", data)
    print(f"[{lid}] wrote {out} ({out.stat().st_size/1024:.0f} KB) · "
          f"{data['played']} played + {data['upcoming']} upcoming · {len(standings)} teams")
    _bk0, _bkN = buckets[0]["key"], buckets[-1]["key"]
    for s in standings[:4]:
        print(f"    {s['team']:<22} {s['pts']}pts/{s['gp']}gp  proj {s['proj_pts']}  "
              f"{_bk0} {s[_bk0]}%  {_bkN} {s[_bkN]}%")


if __name__ == "__main__":
    main()
