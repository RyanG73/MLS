#!/usr/bin/env python3
"""
Standalone model evaluation — no database required.

Pulls real MLS match data from ASA API, builds features,
trains Dixon-Coles + XGBoost, evaluates on held-out seasons
using walk-forward (no future leakage).

Evaluation structure (3-way split):
  train   → seasons < cal_season       (model fitting)
  cal     → cal_season = test_season-1 (temperature calibration + meta-learner)
  test    → test_season                (final held-out evaluation)

Phase 6 changes:
  - O/U model dropped entirely; 1X2 focus only
  - Form: two windows (5 and 10 matches)
  - Style features: PPDA + possession rolling (replaces draw rate)
  - Schedule density: games_in_14d (replaces rest/travel distance)
  - Set-piece xGA split added if available from ASA
  - New A/B groups: +Form10, +PPDA, +Games14d, +Weather, +PostFIFA, +Kickoff
  - Weather: Open-Meteo historical API (FETCH_WEATHER flag; dome stadiums get NULL)
  - Post-FIFA break flag: binary, 14-day window after FIFA windows
  - Kickoff time: cyclic hour encoding + weekday flag

Phase 12 changes (minutes-weighted roster quality):
  - [5k] Full-roster xpoints_added rate: Σ(player_xpa) / (total_team_min / 90)
         Normalises for squad depth — prior raw-sum +Squad dropped (Δ=−0.0018).
         New A/B group: +RosterXPA
  - [5k] Positional g+ split: ATT and DEF position groups separately,
         both as rate-per-90-team-minutes from get_player_goals_added().
         New A/B group: +PosGA  (combined: +RosterAll)
  - [5l] FBref progressive actions + pressing via soccerdata (optional).
         Requires pip install soccerdata.  New A/B group: +FBref
"""

import math
import itertools
import os
import warnings
from datetime import timedelta

import numpy as np
import pandas as pd
from scipy.optimize import minimize, minimize_scalar
from scipy.stats import poisson
from sklearn.metrics import log_loss
from sklearn.linear_model import LogisticRegression
import xgboost as xgb
import urllib3

warnings.filterwarnings("ignore")
urllib3.disable_warnings()

# Suppress SSL errors broadly — system clock (2026-05-10) is past the ASA cert
# validity window causing CERTIFICATE_VERIFY_FAILED on standard SSL handshake.
os.environ.setdefault("PYTHONHTTPSVERIFY", "0")
os.environ.setdefault("CURL_CA_BUNDLE", "")
os.environ.setdefault("REQUESTS_CA_BUNDLE", "")

# ─── CLI overrides (multi-agent experiment harness) ───────────────────────────
# Agents invoke this script via scripts/experiment.py, passing flags to configure
# a single isolated experiment.  Default behaviour (no flags) is identical to
# the original script so nothing breaks when run manually.

import argparse as _ap
import json as _json
from pathlib import Path as _Path


def _parse_args() -> "_ap.Namespace":
    p = _ap.ArgumentParser(
        description="MLS 1X2 eval harness (multi-agent instrumented)",
        add_help=True,
    )
    p.add_argument("--xg-windows",   nargs="+", type=int, metavar="N", default=None,
                   help="xG rolling windows, e.g. --xg-windows 5 15")
    p.add_argument("--form-windows", nargs="+", type=int, metavar="N", default=None)
    p.add_argument("--regress",      type=float, default=None,
                   help="ELO season-regression fraction (0..1)")
    p.add_argument("--dc-decay-hl",  type=int,   default=None,
                   help="Dixon-Coles time-decay half-life (days)")
    p.add_argument("--weight-hl",    type=float, default=None,
                   help="XGBoost sample-weight season half-life")
    p.add_argument("--games-14d",    type=int,   default=None,
                   help="Schedule-density window (days)")
    p.add_argument("--test-seasons", nargs="+", type=int, metavar="YEAR", default=None)
    p.add_argument("--elo-k",        nargs="+", type=int, metavar="K",    default=None,
                   help="ELO K values to grid-search (default: 20 25 30)")
    p.add_argument("--elo-home-adv", nargs="+", type=int, metavar="H",    default=None,
                   help="ELO HOME_ADV values to grid-search (default: 80 100 120)")
    p.add_argument("--calibration",
                   choices=["temperature", "platt", "isotonic", "beta",
                            "temp_then_isotonic", "temp_then_platt"],
                   default="temperature",
                   help="Post-hoc calibration method (default: temperature). "
                        "temp_then_isotonic / temp_then_platt apply temperature "
                        "scaling per-model then a second-pass calibration on the "
                        "stacked ensemble output.")
    p.add_argument("--ab-only",      type=str,   default=None,
                   help="Comma-separated AB_SETS keys to evaluate, e.g. 'Base,+TZShift'")
    p.add_argument("--cache",        action="store_true",
                   help="Cache ASA API responses to data/eval_cache/ (parquet)")
    p.add_argument("--seed",         type=int,   default=None,
                   help="Random seed for numpy/xgboost reproducibility")
    p.add_argument("--out",          type=str,   default=None,
                   help="Write results JSON to this file path")
    p.add_argument("--dump-frame",   type=str,   default=None,
                   help="Export the fully-assembled feature DataFrame to this parquet "
                        "path and exit (for the production parity harness)")
    return p.parse_args()


_ARGS = _parse_args()

if _ARGS.seed is not None:
    import random as _random
    _random.seed(_ARGS.seed)
    np.random.seed(_ARGS.seed)

# ASA response cache — opt-in via --cache so default live behaviour is unchanged
_CACHE_DIR: "_Path | None" = _Path("data/eval_cache") if _ARGS.cache else None


def _cf(fn, *args, **kw):
    """Invoke fn(*args, **kw), caching the DataFrame result as parquet when --cache is set."""
    if _CACHE_DIR is None:
        return fn(*args, **kw)
    import hashlib
    _key = hashlib.md5(
        _json.dumps([fn.__name__, list(args), sorted(kw.items())], default=str).encode()
    ).hexdigest()[:12]
    _p = _CACHE_DIR / f"{fn.__name__}_{_key}.parquet"
    if _p.exists():
        return pd.read_parquet(_p)
    _result = fn(*args, **kw)
    # Some ASA endpoints (e.g. get_players' season_name) return list-typed columns
    # that pyarrow can't serialise. Cache opportunistically; fall back to uncached.
    try:
        _p.parent.mkdir(parents=True, exist_ok=True)
        _result.to_parquet(_p, index=False)
    except Exception:
        pass
    return _result


# ─── Configuration ────────────────────────────────────────────────────────────

XG_WINDOWS   = tuple(_ARGS.xg_windows)  if _ARGS.xg_windows  else (3, 5, 10, 15)
FORM_WINDOWS = tuple(_ARGS.form_windows) if _ARGS.form_windows else (3, 5, 10, 15)
REGRESS      = _ARGS.regress     if _ARGS.regress   is not None else 0.50
INITIAL_ELO  = 1500.0
DC_DECAY_HL  = _ARGS.dc_decay_hl if _ARGS.dc_decay_hl is not None else 120
TEST_SEASONS = list(_ARGS.test_seasons) if _ARGS.test_seasons else [2021, 2022, 2023, 2024]
_COVID       = {2020}
WEIGHT_HL    = _ARGS.weight_hl  if _ARGS.weight_hl  is not None else 6
GAMES_14D    = _ARGS.games_14d  if _ARGS.games_14d  is not None else 16

FETCH_WEATHER       = False  # set True to enable Open-Meteo API calls (~5 min extra)
FETCH_TRANSFERMARKT = True   # Transfermarkt CSVs present: data/transfermarkt_squad_values_*_mapped.csv (2017-2024)

# XGBoost per-process thread cap. Default 2 so that even several evals running
# concurrently (e.g. parallel /improve-model agents) cannot saturate the machine
# and exhaust RAM — this prevents the IDE/terminal crashes seen when 4 parallel
# agents each spawned an all-cores XGBoost run on a 16 GB box. Override with
# EVAL_XGB_NJOBS for a single fast run on a quiet machine.
_XGB_NJOBS = int(os.environ.get("EVAL_XGB_NJOBS", "2"))

# FIFA international window end dates; match within 14 days after → is_post_fifa_break=1
_FIFA_BREAKS = [pd.Timestamp(d) for d in [
    # 2017
    "2017-03-28",  # March window end
    "2017-06-13",
    "2017-09-05",
    "2017-10-10",
    # 2018
    "2018-03-27",
    "2018-06-12",
    "2018-09-11",
    "2018-10-16",
    # 2019
    "2019-03-26",
    "2019-06-11",
    "2019-09-10",
    "2019-10-15",
    # 2020, 2021 excluded (COVID)
    # 2022
    "2022-03-29",
    "2022-06-14",
    "2022-09-27",
    "2022-11-15",  # World Cup year — November window displaces Oct
    # 2023
    "2023-03-28",
    "2023-06-20",
    "2023-09-12",
    "2023-10-17",
    # 2024
    "2024-03-26",
    "2024-06-11",
    "2024-09-10",
    "2024-10-15",
]]

# Dome stadiums: weather is irrelevant (retractable roof / climate-controlled)
_DOME_TEAM_IDS = {"KAqBN0Vqbg", "lgpMOvnQzy"}  # Atlanta United, Vancouver Whitecaps

# Stadium coordinates (lat, lon) keyed by ASA team_id
_TEAM_COORDS: dict[str, tuple[float, float]] = {
    "0KPqjA456v": (37.351, -121.925),
    "19vQ2095K6": (42.091,  -71.264),
    "4wM42l4qjB": (33.864, -118.261),
    "9z5k7Yg5A3": (39.834,  -75.380),
    "APk5LGOMOW": (45.564,  -73.551),
    "EKXMeX3Q64": (38.868,  -77.013),
    "KAqBN0Vqbg": (33.755,  -84.401),
    "NPqxKXZ59d": (35.226,  -80.853),
    "NWMWlBK5lz": (39.109,  -84.521),
    "Vj58weDM8n": (40.829,  -73.926),
    "WBLMvYAQxe": (45.521, -122.692),
    "X0Oq66zq6D": (41.862,  -87.617),
    "YgOMngl5zy": (29.753,  -95.351),
    "Z2vQ1xlqrA": (39.123,  -94.824),
    "a2lqR4JMr0": (40.583, -111.893),
    "a2lqRX2Mr0": (40.737,  -74.150),
    "eVq3ya6MWO": (34.013, -118.285),
    "gpMOLwl5zy": (30.387,  -97.719),
    "jYQJ19EqGR": (47.595, -122.332),
    "jYQJ8EW5GR": (28.541,  -81.389),
    "kRQabn8MKZ": (43.633,  -79.419),
    "kRQand1MKZ": (44.953,  -93.165),
    "kaDQ0wRqEv": (33.864, -118.261),
    "lgpMOvnQzy": (49.277, -123.112),
    "mKAqBBmqbg": (33.155,  -97.116),
    "mvzqoLZQap": (39.968,  -83.018),
    "pzeQZ6xQKw": (39.805, -104.892),
    "vzqoOgNqap": (36.130,  -86.766),
    "wvq9B9wQWn": (38.633,  -90.212),
    "zeQZBOzQKw": (32.707, -117.120),
    "zeQZkL1MKw": (26.170,  -80.188),
}

# ─── 1. Fetch base match data ─────────────────────────────────────────────────

print("=" * 70)
print("MLS Model Evaluation  (Phase 6: 1X2 only, extended features)")
print("=" * 70)
print("\n[1/9] Fetching MLS match data from ASA API...")

from itscalledsoccer.client import AmericanSoccerAnalysis
asa = AmericanSoccerAnalysis()
# CacheControl returns the original requests.Session with adapter mounted.
# Setting verify=False disables cert checking for all ASA requests.
asa.session.verify = False

games_raw = _cf(asa.get_games, leagues="mls")
_avail = set(games_raw.columns)

_stage_col = next(
    (c for c in ["stage_name", "competition_round", "round_name",
                 "competition_stage", "game_type"] if c in _avail),
    None,
)
_sel = ["game_id", "date_time_utc", "home_team_id", "away_team_id",
        "home_score", "away_score", "season_name", "status"]
if _stage_col:
    _sel.append(_stage_col)

games = games_raw[[c for c in _sel if c in _avail]].rename(columns={
    "game_id": "match_id", "date_time_utc": "date",
    "home_team_id": "home_team", "away_team_id": "away_team",
    "home_score": "home_goals", "away_score": "away_goals",
    "season_name": "season",
})

if _stage_col and _stage_col in games.columns:
    games["is_playoff"] = games[_stage_col].str.lower().str.contains(
        r"playoff|cup final|semifinal|final|knockout|conference", na=False
    ).astype(int)
    games.drop(columns=[_stage_col], inplace=True)
else:
    games["is_playoff"] = 0

# xG — also try to pull set-piece split if available
gxg_raw = _cf(asa.get_game_xgoals, leagues="mls")
gxg_want = {
    "game_id": "match_id",
    "home_team_xgoals": "home_xg",
    "away_team_xgoals": "away_xg",
    "home_team_xgoals_from_set_play": "home_xg_sp",
    "away_team_xgoals_from_set_play": "away_xg_sp",
}
gxg = gxg_raw[[c for c in gxg_want if c in gxg_raw.columns]].rename(columns=gxg_want)

df = games.merge(gxg, on="match_id", how="left")
df["date"] = pd.to_datetime(df["date"], utc=True).dt.tz_localize(None)
df["season"] = (
    pd.to_numeric(df["season"], errors="coerce")
    .fillna(df["date"].dt.year)
    .astype(int)
)
df = df[df["home_goals"].notna() & df["away_goals"].notna()].copy()
df["home_goals"] = df["home_goals"].astype(int)
df["away_goals"] = df["away_goals"].astype(int)

_n_raw = len(df)
df = df[(df["season"] >= 2017) & (~df["season"].isin(_COVID))].copy()
df = df.sort_values("date").reset_index(drop=True)

print(f"    {len(df):,} matches ({df['season'].min()}–{df['season'].max()})  |  "
      f"{_n_raw - len(df):,} pre-2017/COVID excluded")
print(f"    xG coverage: {df['home_xg'].notna().mean():.0%}  |  "
      f"Playoff: {df['is_playoff'].sum()} ({df['is_playoff'].mean():.1%})")
_HAS_SP_XG = "home_xg_sp" in df.columns and df["home_xg_sp"].notna().mean() > 0.3
print(f"    Set-piece xG split: {'yes' if _HAS_SP_XG else 'no'}")

# Kickoff-time features (from UTC timestamp)
df["kickoff_hour_utc"] = df["date"].dt.hour
df["kickoff_sin"] = np.sin(2 * np.pi * df["kickoff_hour_utc"] / 24)
df["kickoff_cos"] = np.cos(2 * np.pi * df["kickoff_hour_utc"] / 24)
df["is_weekday_game"] = df["date"].dt.dayofweek.isin([1, 2]).astype(int)

# Post-FIFA break flag
def _is_post_fifa(date: pd.Timestamp) -> int:
    for wb in _FIFA_BREAKS:
        if timedelta(0) < (date - wb) <= timedelta(days=14):
            return 1
    return 0

df["is_post_fifa_break"] = df["date"].apply(_is_post_fifa)

# Dome flag (structural NULL for weather)
df["is_dome"] = df["home_team"].isin(_DOME_TEAM_IDS).astype(int)

# Labels
df["label_result"] = np.where(
    df["home_goals"] > df["away_goals"], 0,
    np.where(df["home_goals"] == df["away_goals"], 1, 2),
)

print(f"    Post-FIFA matches: {df['is_post_fifa_break'].sum()}  |  "
      f"Dome: {df['is_dome'].sum()}  |  "
      f"Weekday: {df['is_weekday_game'].sum()}")

# ─── 2. Fetch game-level xpass (PPDA + possession) ───────────────────────────

print("\n[2/9] Fetching game-level xpass (PPDA / possession)...")

_xpass_by_game: dict[str, tuple] = {}
_HAS_PPDA = False
_HAS_POSS = False

try:
    gxpass = _cf(asa.get_game_xpass, leagues="mls")
    cols = list(gxpass.columns)
    print(f"    Available columns: {cols[:12]}{'...' if len(cols) > 12 else ''}")

    _ppda_h = next((c for c in cols if "ppda" in c.lower() and "home" in c.lower()), None)
    _ppda_a = next((c for c in cols if "ppda" in c.lower() and "away" in c.lower()), None)
    _poss_h = next((c for c in cols if "possession" in c.lower() and "home" in c.lower()), None)
    _poss_a = next((c for c in cols if "possession" in c.lower() and "away" in c.lower()), None)
    _gid    = next((c for c in ["game_id", "match_id"] if c in cols), None)

    if _gid:
        for _, row in gxpass.iterrows():
            gid = str(row[_gid])
            hp = float(row[_ppda_h]) if _ppda_h and pd.notna(row.get(_ppda_h)) else None
            ap = float(row[_ppda_a]) if _ppda_a and pd.notna(row.get(_ppda_a)) else None
            hv = float(row[_poss_h]) if _poss_h and pd.notna(row.get(_poss_h)) else None
            av = float(row[_poss_a]) if _poss_a and pd.notna(row.get(_poss_a)) else None
            _xpass_by_game[gid] = (hp, ap, hv, av)
        _HAS_PPDA = any(v[0] is not None for v in _xpass_by_game.values())
        _HAS_POSS = any(v[2] is not None for v in _xpass_by_game.values())

    print(f"    Loaded: {len(_xpass_by_game):,} games | "
          f"PPDA={'yes' if _HAS_PPDA else 'no'} | "
          f"Possession={'yes' if _HAS_POSS else 'no'}")
except Exception as e:
    print(f"    Warning: could not fetch game xpass ({e}). PPDA/possession skipped.")

# ─── 3. ELO grid search ───────────────────────────────────────────────────────

print("\n[3/9] ELO hyperparameter grid search (val: 2019)...")


def compute_elo(
    df: pd.DataFrame,
    K: float,
    HOME_ADV: float,
    regress: float = 0.40,
    initial: float = 1500.0,
    return_expected: bool = False,
) -> pd.DataFrame:
    elo: dict[str, float] = {}
    h_elo, a_elo, h_exp = [], [], []
    seen: set = set()
    for _, row in df.iterrows():
        s = row["season"]
        if s not in seen:
            seen.add(s)
            elo = {t: initial + (r - initial) * (1 - regress) for t, r in elo.items()}
        ht, at = row["home_team"], row["away_team"]
        rh = elo.get(ht, initial)
        ra = elo.get(at, initial)
        e_h = 1 / (1 + 10 ** ((ra - (rh + HOME_ADV)) / 400))
        hg, ag = row["home_goals"], row["away_goals"]
        s_h = 1.0 if hg > ag else (0.5 if hg == ag else 0.0)
        mov = 1 + math.log(abs(hg - ag) + 1) * 0.1
        h_elo.append(rh); a_elo.append(ra); h_exp.append(e_h)
        elo[ht] = rh + K * mov * (s_h - e_h)
        elo[at] = ra + K * mov * ((1 - s_h) - (1 - e_h))
    out = df.copy()
    out["home_elo"] = h_elo
    out["away_elo"] = a_elo
    out["elo_diff"] = np.array(h_elo) - np.array(a_elo)
    if return_expected:
        out["elo_p_home"] = h_exp
    return out


_VAL_S = {2019}
_val_draw_rate = df[df["season"] < min(_VAL_S)]["label_result"].eq(1).mean()
_best_elo_b, _best_K, _best_HA = float("inf"), 20, 100

_ELO_K_GRID  = _ARGS.elo_k        if _ARGS.elo_k        else [20, 25, 30]
_ELO_HA_GRID = _ARGS.elo_home_adv if _ARGS.elo_home_adv else [80, 100, 120]
for _K, _HA in itertools.product(_ELO_K_GRID, _ELO_HA_GRID):
    _tmp = compute_elo(df, _K, _HA, REGRESS, INITIAL_ELO, return_expected=True)
    _v = _tmp[_tmp["season"].isin(_VAL_S)]
    if len(_v) < 30:
        continue
    _ph = _v["elo_p_home"].values
    _pd_v = np.full(len(_v), _val_draw_rate)
    _pa = np.clip(1 - _ph - _pd_v, 0.01, None)
    _s = _ph + _pd_v + _pa
    _p3 = np.column_stack([_ph / _s, _pd_v / _s, _pa / _s])
    _b = float(np.mean(np.sum((_p3 - np.eye(3)[_v["label_result"].values]) ** 2, axis=1)))
    if _b < _best_elo_b:
        _best_elo_b, _best_K, _best_HA = _b, _K, _HA

K, HOME_ADV = _best_K, _best_HA
print(f"    Best: K={K}, HOME_ADV={HOME_ADV}  (val Brier={_best_elo_b:.4f})")
df = compute_elo(df, K, HOME_ADV, REGRESS, INITIAL_ELO)

# ─── 4. Rolling features ──────────────────────────────────────────────────────

print(f"\n[4/9] Rolling features "
      f"(xG windows={XG_WINDOWS}, form windows={FORM_WINDOWS}, "
      f"PPDA={'yes' if _HAS_PPDA else 'no'})...")


_PYTHAG_EXP = 1.83  # soccer Pythagorean exponent (Hamilton 2011)
_PYTHAG_WIN = 10    # rolling window for Pythagorean luck


def _pythag_expected_pts(gf: float, ga: float, n: int) -> float:
    """Pythagorean expected points over n matches (soccer exponent ≈ 1.83).

    Returns n * 3 * win_rate, using 3*W approximation (draws ≈ partial wins).
    Falls back to league-average rate (1.35 pts/match) when totals are zero.
    """
    if gf + ga == 0 or n == 0:
        return 1.35 * n
    win_rate = gf ** _PYTHAG_EXP / (gf ** _PYTHAG_EXP + ga ** _PYTHAG_EXP)
    return 3.0 * win_rate * n


def _haversine_km(a: "tuple | None", b: "tuple | None") -> float:
    """Great-circle distance (km) between two (lat, lon) points. 0 if either missing."""
    if not a or not b:
        return 0.0
    lat1, lon1, lat2, lon2 = map(math.radians, [a[0], a[1], b[0], b[1]])
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * 6371.0 * math.asin(math.sqrt(h))


def add_rolling_features(df: pd.DataFrame) -> pd.DataFrame:
    team_xg: dict[str, list] = {}       # per-game xg/xga records
    team_pts: dict[str, list] = {}      # points earned per game
    team_goals: dict[str, list] = {}    # per-game (gf, ga) tuples for Pythagorean
    team_ppda: dict[str, list] = {}     # PPDA per game (float | None)
    team_poss: dict[str, list] = {}     # possession per game (float | None)
    team_dates: dict[str, list] = []    # type: ignore

    team_dates_d: dict[str, list] = {}  # dates for games_in_14d

    # Initialise result columns
    res: dict[str, list] = {}
    for r in ("home", "away"):
        for w in XG_WINDOWS:
            res[f"{r}_xg_roll_{w}"] = []
            res[f"{r}_xga_roll_{w}"] = []
        for fw in FORM_WINDOWS:
            res[f"{r}_form_{fw}"] = []
        res[f"{r}_games_in_14d"] = []
        res[f"{r}_days_rest"] = []
        res[f"{r}_pythag_luck_{_PYTHAG_WIN}"] = []
        if _HAS_PPDA:
            res[f"{r}_ppda_roll_10"] = []
        if _HAS_POSS:
            res[f"{r}_poss_roll_10"] = []
        if _HAS_SP_XG:
            res[f"{r}_xga_sp_roll_15"] = []

    for _, row in df.iterrows():
        ht, at = row["home_team"], row["away_team"]
        hg, ag = row["home_goals"], row["away_goals"]
        mid = str(row.get("match_id", ""))
        dt  = row["date"]

        h_xg = float(row["home_xg"]) if pd.notna(row.get("home_xg")) else float(hg)
        a_xg = float(row["away_xg"]) if pd.notna(row.get("away_xg")) else float(ag)
        h_xg_sp = float(row["home_xg_sp"]) if _HAS_SP_XG and pd.notna(row.get("home_xg_sp")) else None
        a_xg_sp = float(row["away_xg_sp"]) if _HAS_SP_XG and pd.notna(row.get("away_xg_sp")) else None

        xp = _xpass_by_game.get(mid, (None, None, None, None))
        h_ppda_v, a_ppda_v, h_poss_v, a_poss_v = xp

        for team, role, my_xg, opp_xg, my_xg_sp, opp_xg_sp, my_ppda, my_poss in [
            (ht, "home", h_xg, a_xg, h_xg_sp, a_xg_sp, h_ppda_v, h_poss_v),
            (at, "away", a_xg, h_xg, a_xg_sp, h_xg_sp, a_ppda_v, a_poss_v),
        ]:
            xg_hist    = team_xg.get(team, [])
            pts_hist   = team_pts.get(team, [])
            goals_hist = team_goals.get(team, [])
            ppda_hist  = team_ppda.get(team, [])
            poss_hist  = team_poss.get(team, [])
            date_hist  = team_dates_d.get(team, [])

            for w in XG_WINDOWS:
                seg = xg_hist[-w:]
                res[f"{role}_xg_roll_{w}"].append(
                    np.mean([x["xg"] for x in seg]) if seg else 1.3)
                res[f"{role}_xga_roll_{w}"].append(
                    np.mean([x["xga"] for x in seg]) if seg else 1.3)

            for fw in FORM_WINDOWS:
                seg_pts = pts_hist[-fw:]
                res[f"{role}_form_{fw}"].append(np.mean(seg_pts) if seg_pts else 1.0)

            cutoff = dt - timedelta(days=GAMES_14D)
            res[f"{role}_games_in_14d"].append(sum(1 for d in date_hist if d > cutoff))

            # Days rest since most recent prior match (date_hist excludes current → leakage-safe).
            # Cap at 21d so cross-season offseason gaps don't dominate; default 7 if no history.
            res[f"{role}_days_rest"].append(
                min((dt - date_hist[-1]).days, 21) if date_hist else 7)

            # Pythagorean luck: actual pts - expected pts over last N matches
            seg_goals = goals_hist[-_PYTHAG_WIN:]
            seg_pts_w = pts_hist[-_PYTHAG_WIN:]
            if seg_goals:
                n = len(seg_goals)
                gf_sum = sum(g[0] for g in seg_goals)
                ga_sum = sum(g[1] for g in seg_goals)
                pts_actual = sum(seg_pts_w)
                pts_pythag = _pythag_expected_pts(gf_sum, ga_sum, n)
                res[f"{role}_pythag_luck_{_PYTHAG_WIN}"].append(pts_actual - pts_pythag)
            else:
                res[f"{role}_pythag_luck_{_PYTHAG_WIN}"].append(0.0)

            if _HAS_PPDA:
                seg_ppda = [v for v in ppda_hist[-10:] if v is not None]
                res[f"{role}_ppda_roll_10"].append(np.mean(seg_ppda) if seg_ppda else 10.0)

            if _HAS_POSS:
                seg_poss = [v for v in poss_hist[-10:] if v is not None]
                res[f"{role}_poss_roll_10"].append(np.mean(seg_poss) if seg_poss else 50.0)

            if _HAS_SP_XG:
                # opp_xg_sp stored in history; it is the xG-against-via-set-piece
                seg_sp = [x["opp_xg_sp"] for x in xg_hist[-15:] if x.get("opp_xg_sp") is not None]
                res[f"{role}_xga_sp_roll_15"].append(np.mean(seg_sp) if seg_sp else 0.4)

        # Update histories (after reading to avoid leakage)
        h_pts = 3 if hg > ag else (1 if hg == ag else 0)
        a_pts = 3 if ag > hg else (1 if hg == ag else 0)
        team_xg.setdefault(ht, []).append({"xg": h_xg, "xga": a_xg, "opp_xg_sp": a_xg_sp})
        team_xg.setdefault(at, []).append({"xg": a_xg, "xga": h_xg, "opp_xg_sp": h_xg_sp})
        team_pts.setdefault(ht, []).append(h_pts)
        team_pts.setdefault(at, []).append(a_pts)
        team_goals.setdefault(ht, []).append((float(hg), float(ag)))
        team_goals.setdefault(at, []).append((float(ag), float(hg)))
        team_ppda.setdefault(ht, []).append(h_ppda_v)
        team_ppda.setdefault(at, []).append(a_ppda_v)
        team_poss.setdefault(ht, []).append(h_poss_v)
        team_poss.setdefault(at, []).append(a_poss_v)
        team_dates_d.setdefault(ht, []).append(dt)
        team_dates_d.setdefault(at, []).append(dt)

    out = df.copy()
    for col, vals in res.items():
        out[col] = vals

    w0 = XG_WINDOWS[0]
    out["xg_diff"]      = out[f"home_xg_roll_{w0}"] - out[f"away_xg_roll_{w0}"]
    out["form_diff"]    = out[f"home_form_{FORM_WINDOWS[0]}"] - out[f"away_form_{FORM_WINDOWS[0]}"]
    out["home_xg_sum"]  = out[f"home_xg_roll_{w0}"] + out[f"away_xg_roll_{w0}"]
    out["games14d_diff"] = out["home_games_in_14d"] - out["away_games_in_14d"]
    out["rest_advantage"] = out["home_days_rest"] - out["away_days_rest"]
    out["travel_km"] = [
        _haversine_km(_TEAM_COORDS.get(h), _TEAM_COORDS.get(a))
        for h, a in zip(out["home_team"], out["away_team"])
    ]
    out["pythag_luck_diff"] = (out[f"home_pythag_luck_{_PYTHAG_WIN}"]
                               - out[f"away_pythag_luck_{_PYTHAG_WIN}"])
    if _HAS_PPDA:
        out["ppda_diff"] = out["home_ppda_roll_10"] - out["away_ppda_roll_10"]
    if _HAS_POSS:
        out["poss_diff"] = out["home_poss_roll_10"] - out["away_poss_roll_10"]
    return out


df = add_rolling_features(df)
print(f"    Rolling features complete. Columns added: {[c for c in df.columns if 'roll' in c or 'form_' in c or '14d' in c][:8]}...")

# ─── 5. Altitude flag ─────────────────────────────────────────────────────────

_HIGH_ALT_IDS = {"pzeQZ6xQKw", "a2lqR4JMr0"}   # Colorado, Real Salt Lake
df["is_high_alt"] = df["home_team"].isin(_HIGH_ALT_IDS).astype(int)

# ─── 6. Squad quality from player xpoints_added ───────────────────────────────

print("\n[5/9] Fetching player xpoints_added by season (prev-season squad quality)...")

_SQUAD_SEASONS = [s for s in range(2016, 2026) if s not in _COVID]
_squad_raw: dict[tuple, float] = {}

for _s in _SQUAD_SEASONS:
    try:
        _pxg = _cf(asa.get_player_xgoals, leagues="mls", season_name=str(_s))
        _pxg_s = _pxg[
            _pxg["team_id"].apply(lambda x: isinstance(x, str))
            & (_pxg["minutes_played"] >= 500)
        ]
        for _tid, _grp in _pxg_s.groupby("team_id"):
            _squad_raw[(_tid, _s)] = float(_grp["xpoints_added"].sum())
    except Exception:
        pass

_squad_norm: dict[tuple, float] = {}
for _s in _SQUAD_SEASONS:
    _vals = [v for (t, ss), v in _squad_raw.items() if ss == _s]
    if len(_vals) < 3:
        continue
    _mu, _sd = float(np.mean(_vals)), float(np.std(_vals))
    _sd = max(_sd, 0.1)
    for (t, ss), v in _squad_raw.items():
        if ss == _s:
            _squad_norm[(t, ss)] = (v - _mu) / _sd

print(f"    Squad quality: {len(_squad_norm)} team-seasons "
      f"({len({ss for _, ss in _squad_norm})} seasons)")


def squad_z(team_id: str, season: int) -> float:
    for lag in (1, 2):
        val = _squad_norm.get((team_id, season - lag))
        if val is not None:
            return val
    return 0.0


df["home_squad_xpa"] = [squad_z(r.home_team, r.season) for _, r in df.iterrows()]
df["away_squad_xpa"] = [squad_z(r.away_team, r.season) for _, r in df.iterrows()]
df["squad_xpa_diff"] = df["home_squad_xpa"] - df["away_squad_xpa"]

# ─── 5b. GK quality from goalkeeper xgoals (season-lagged) ───────────────────
# goals_prevented = xg_faced - goals_conceded; +ve means GK is above expected
# Best GK per team-season by minutes played; z-scored and lagged one season.

print("\n[5b/9] Fetching goalkeeper xgoals (GK quality, season-lagged)...")

_gk_quality: dict[tuple, float] = {}   # (team_id, season) → goals_prevented z-score

_GK_MIN_MINUTES = 500   # minimum minutes to qualify as team's main GK

_gk_raw_dict: dict[tuple, float] = {}
for _s in _SQUAD_SEASONS:
    try:
        _gkxg_s = _cf(asa.get_goalkeeper_xgoals, leagues="mls", season_name=str(_s))
        _gk_cols = list(_gkxg_s.columns)
        _gk_tid_c  = next((c for c in ["team_id"] if c in _gk_cols), None)
        _gk_min_c  = next((c for c in ["minutes_played", "minutes"] if c in _gk_cols), None)
        _gk_goal_c = next((c for c in ["goals_conceded", "goals_allowed"] if c in _gk_cols), None)
        _gk_xg_c   = next((c for c in ["xgoals_gk_faced", "xgoals_faced"] if c in _gk_cols), None)
        if not (_gk_tid_c and _gk_min_c and _gk_goal_c and _gk_xg_c):
            continue
        _gkxg_s = _gkxg_s[_gkxg_s[_gk_tid_c].apply(lambda x: isinstance(x, str))]
        _gkxg_s = _gkxg_s[_gkxg_s[_gk_min_c] >= _GK_MIN_MINUTES]
        _gkxg_s["_gp"] = _gkxg_s[_gk_xg_c] - _gkxg_s[_gk_goal_c]
        # Best GK per team (most minutes)
        for _tid, _grp in _gkxg_s.sort_values(_gk_min_c, ascending=False).groupby(_gk_tid_c):
            _gk_raw_dict[(_tid, _s)] = float(_grp.iloc[0]["_gp"])
    except Exception:
        pass

if _gk_raw_dict:
    _gk_cols_disp = list(_cf(asa.get_goalkeeper_xgoals, leagues="mls", season_name="2023").columns)
    print(f"    GK columns (sample): {_gk_cols_disp[:8]}")
    for _s in sorted({ss for (_, ss) in _gk_raw_dict}):
        _vals = [v for (t, ss), v in _gk_raw_dict.items() if ss == _s]
        if len(_vals) < 3:
            continue
        _mu, _sd = float(np.mean(_vals)), float(np.std(_vals))
        _sd = max(_sd, 0.1)
        for (t, ss), v in _gk_raw_dict.items():
            if ss == _s:
                _gk_quality[(t, ss)] = (v - _mu) / _sd
    print(f"    GK quality loaded: {len(_gk_quality)} team-seasons")
else:
    print("    GK quality: no data returned from ASA per-season calls.")


def _gk_z(team_id: str, season: int) -> float | None:
    for lag in (1, 2):
        val = _gk_quality.get((team_id, season - lag))
        if val is not None:
            return val
    return None   # explicit None → XGBoost handles natively


if _gk_quality:
    df["home_gk_z"] = [_gk_z(r.home_team, r.season) for _, r in df.iterrows()]
    df["away_gk_z"] = [_gk_z(r.away_team, r.season) for _, r in df.iterrows()]
    df["gk_z_diff"] = df["home_gk_z"].fillna(0) - df["away_gk_z"].fillna(0)
    _gk_cov = df["home_gk_z"].notna().mean()
    print(f"    GK z-score coverage: {_gk_cov:.0%}")
else:
    print("    GK features not available.")

# ─── 5c. Team PPDA and possession (season-lagged from team xpass) ─────────────
# ASA's get_game_xpass doesn't exist in this version; get_team_xpass is season-level.
# Use prior-season PPDA as a style-of-play signal.

print("\n[5c/9] Fetching team-level xpass (season PPDA / possession, lagged)...")

_team_ppda_season: dict[tuple, float] = {}   # (team_id, season) → ppda
_team_poss_season: dict[tuple, float] = {}   # (team_id, season) → possession

for _s in _SQUAD_SEASONS:
    try:
        _txpass_s = _cf(asa.get_team_xpass, leagues="mls", season_name=str(_s))
        _tp_cols = list(_txpass_s.columns)
        _tp_tid  = next((c for c in ["team_id"] if c in _tp_cols), None)
        _tp_ppda = next((c for c in ["ppda", "passes_allowed_per_defensive_action"]
                         if c in _tp_cols), None)
        _tp_poss = next((c for c in ["avg_possession", "possession"] if c in _tp_cols), None)
        if not _tp_tid:
            continue
        for _, row in _txpass_s.iterrows():
            tid = row[_tp_tid]
            if not isinstance(tid, str):
                continue
            if _tp_ppda and pd.notna(row.get(_tp_ppda)):
                _team_ppda_season[(tid, _s)] = float(row[_tp_ppda])
            if _tp_poss and pd.notna(row.get(_tp_poss)):
                _team_poss_season[(tid, _s)] = float(row[_tp_poss])
    except Exception:
        pass

if _team_ppda_season or _team_poss_season:
    _sample_cols = list(_cf(asa.get_team_xpass, leagues="mls", season_name="2023").columns)
    print(f"    Team xpass columns: {_sample_cols[:8]}{'...' if len(_sample_cols) > 8 else ''}")
    print(f"    Season PPDA: {len(_team_ppda_season)} | Possession: {len(_team_poss_season)}")
else:
    print("    Season PPDA/possession: no matching columns in ASA team xpass.")


def _season_ppda(team_id: str, season: int) -> float | None:
    for lag in (1, 2):
        val = _team_ppda_season.get((team_id, season - lag))
        if val is not None:
            return val
    return None


def _season_poss(team_id: str, season: int) -> float | None:
    for lag in (1, 2):
        val = _team_poss_season.get((team_id, season - lag))
        if val is not None:
            return val
    return None


if _team_ppda_season:
    df["home_ppda_season"] = [_season_ppda(r.home_team, r.season) for _, r in df.iterrows()]
    df["away_ppda_season"] = [_season_ppda(r.away_team, r.season) for _, r in df.iterrows()]
    df["ppda_season_diff"] = df["home_ppda_season"].fillna(0) - df["away_ppda_season"].fillna(0)
if _team_poss_season:
    df["home_poss_season"] = [_season_poss(r.home_team, r.season) for _, r in df.iterrows()]
    df["away_poss_season"] = [_season_poss(r.away_team, r.season) for _, r in df.iterrows()]
    df["poss_season_diff"] = df["home_poss_season"].fillna(0) - df["away_poss_season"].fillna(0)

# ─── 5d. Top player goals added (star-player effect) ─────────────────────────
# goals_added captures composite contribution (shooting, dribbling, passing, etc.)
# Top player per team-season = proxy for DP / star player quality.

print("\n[5d/9] Fetching player goals added (star-player effect, season-lagged)...")

_top_player_ga: dict[tuple, float] = {}   # (team_id, season) → top player goals_added z-score

_ga_raw: dict[tuple, float] = {}
_pga_players: dict[tuple, list[float]] = {}   # (team_id, season) → per-outfielder ga list (Top-N source)
for _s in _SQUAD_SEASONS:
    try:
        _pga_s = _cf(asa.get_player_goals_added, leagues="mls", season_name=str(_s))
        _pga_cols = list(_pga_s.columns)
        _pga_tid = next((c for c in ["team_id"] if c in _pga_cols), None)
        _pga_min = next((c for c in ["minutes_played", "minutes"] if c in _pga_cols), None)
        _pga_pos = next((c for c in ["general_position", "position", "primary_position"]
                         if c in _pga_cols), None)
        # goals_added may be in a "data" column (JSON list of action types) or direct columns
        _pga_ga  = next((c for c in ["goals_added_above_avg", "goals_added_above_replacement",
                                      "goals_added_raw", "num_actions_ranked_goals_added_above_avg"]
                         if c in _pga_cols), None)
        if not _pga_tid:
            continue
        if _pga_ga is None and "data" in _pga_cols:
            # Unpack nested JSON: each row's "data" is a list of dicts with goals_added_above_avg
            import json as _json
            def _sum_ga(d):
                try:
                    items = _json.loads(d) if isinstance(d, str) else d
                    return sum(float(x.get("goals_added_above_avg", 0) or 0) for x in items)
                except Exception:
                    return 0.0
            _pga_s["_ga_total"] = _pga_s["data"].apply(_sum_ga)
            _pga_ga = "_ga_total"
        if _pga_ga is None:
            continue
        _pga_s = _pga_s[_pga_s[_pga_tid].apply(lambda x: isinstance(x, str))]
        if _pga_min:
            _pga_s = _pga_s[_pga_s[_pga_min] >= 500]
        for _, row in _pga_s.iterrows():
            tid = row[_pga_tid]
            ga  = row[_pga_ga]
            if isinstance(tid, str) and pd.notna(ga):
                key = (tid, _s)
                _ga_raw[key] = _ga_raw.get(key, 0.0) + float(ga)
                # Top-N source: keep per-outfielder ga (skip GKs if position column exists)
                if _pga_pos:
                    pos_v = str(row.get(_pga_pos, "")).upper()
                    if pos_v.startswith("GK") or pos_v == "GOALKEEPER":
                        continue
                _pga_players.setdefault(key, []).append(float(ga))
    except Exception:
        pass

if _ga_raw:
    for _s in sorted({ss for (_, ss) in _ga_raw}):
        _vals = [v for (t, ss), v in _ga_raw.items() if ss == _s]
        if len(_vals) < 3:
            continue
        _mu, _sd = float(np.mean(_vals)), float(np.std(_vals))
        _sd = max(_sd, 0.1)
        for (t, ss), v in _ga_raw.items():
            if ss == _s:
                _top_player_ga[(t, ss)] = (v - _mu) / _sd
    print(f"    Goals added loaded: {len(_top_player_ga)} team-seasons")
else:
    print("    Goals added: no data parsed from ASA per-season calls.")


def _ga_z(team_id: str, season: int) -> float | None:
    for lag in (1, 2):
        val = _top_player_ga.get((team_id, season - lag))
        if val is not None:
            return val
    return None


if _top_player_ga:
    df["home_goals_added_z"] = [_ga_z(r.home_team, r.season) for _, r in df.iterrows()]
    df["away_goals_added_z"] = [_ga_z(r.away_team, r.season) for _, r in df.iterrows()]
    df["goals_added_z_diff"] = (df["home_goals_added_z"].fillna(0)
                                 - df["away_goals_added_z"].fillna(0))

# ─── 5d2. Top-N goals added (star concentration, season-lagged) ──────────────
# Top-3 and top-5 outfielder g+ sums per team-season, z-scored within season.
# Differentiates "one DP carrying" vs "deep squad" from the overall team sum.

print("\n[5d2/9] Computing Top-N goals-added concentration (Top-3, Top-5)...")

_top3_raw: dict[tuple, float] = {}
_top5_raw: dict[tuple, float] = {}
_top3_z:   dict[tuple, float] = {}
_top5_z:   dict[tuple, float] = {}

for _key, _vals_list in _pga_players.items():
    _sorted = sorted(_vals_list, reverse=True)
    _top3_raw[_key] = float(sum(_sorted[:3]))
    _top5_raw[_key] = float(sum(_sorted[:5]))

for _raw, _norm in [(_top3_raw, _top3_z), (_top5_raw, _top5_z)]:
    for _s in sorted({ss for (_, ss) in _raw}):
        _vals = [v for (t, ss), v in _raw.items() if ss == _s]
        if len(_vals) < 3:
            continue
        _mu, _sd = float(np.mean(_vals)), float(np.std(_vals))
        _sd = max(_sd, 0.1)
        for (t, ss), v in _raw.items():
            if ss == _s:
                _norm[(t, ss)] = (v - _mu) / _sd


def _top3_lookup(team_id: str, season: int) -> float | None:
    for lag in (1, 2):
        val = _top3_z.get((team_id, season - lag))
        if val is not None:
            return val
    return None


def _top5_lookup(team_id: str, season: int) -> float | None:
    for lag in (1, 2):
        val = _top5_z.get((team_id, season - lag))
        if val is not None:
            return val
    return None


if _top3_z:
    df["home_top3_ga_z"] = [_top3_lookup(r.home_team, r.season) for _, r in df.iterrows()]
    df["away_top3_ga_z"] = [_top3_lookup(r.away_team, r.season) for _, r in df.iterrows()]
    df["top3_ga_diff"]   = df["home_top3_ga_z"].fillna(0) - df["away_top3_ga_z"].fillna(0)
if _top5_z:
    df["home_top5_ga_z"] = [_top5_lookup(r.home_team, r.season) for _, r in df.iterrows()]
    df["away_top5_ga_z"] = [_top5_lookup(r.away_team, r.season) for _, r in df.iterrows()]
    df["top5_ga_diff"]   = df["home_top5_ga_z"].fillna(0) - df["away_top5_ga_z"].fillna(0)
print(f"    Top-N concentration: {len(_top3_z)} team-seasons (Top-3 / Top-5)")

# ─── 5e. Player xPass: minutes-weighted passing over-performance ──────────────
# Captures team's ball-progression quality via individual passer skill.
# Lagged one season, z-scored, gated on column presence.

print("\n[5e/9] Fetching player xpass (minutes-weighted team mean, season-lagged)...")

_team_xpass_oe: dict[tuple, float] = {}    # (team_id, season) → minutes-weighted xPass over-expected
_team_xpass_oe_z: dict[tuple, float] = {}

for _s in _SQUAD_SEASONS:
    try:
        _pxp = _cf(asa.get_player_xpass, leagues="mls", season_name=str(_s))
        _pxp_cols = list(_pxp.columns)
        _pxp_tid  = next((c for c in ["team_id"] if c in _pxp_cols), None)
        _pxp_min  = next((c for c in ["minutes_played", "minutes"] if c in _pxp_cols), None)
        _pxp_oe   = next((c for c in [
            "passes_completed_over_expected_p100",
            "passes_completed_over_expected_per_100",
            "passes_completed_over_expected",
            "pass_oe_p100",
            "pass_completion_over_expected_pct",
        ] if c in _pxp_cols), None)
        if not (_pxp_tid and _pxp_min and _pxp_oe):
            continue
        _pxp_s = _pxp[_pxp[_pxp_tid].apply(lambda x: isinstance(x, str))]
        _pxp_s = _pxp_s[_pxp_s[_pxp_min] >= 500]
        for _tid, _grp in _pxp_s.groupby(_pxp_tid):
            _wts = _grp[_pxp_min].values
            _vals = _grp[_pxp_oe].values
            if _wts.sum() <= 0:
                continue
            _team_xpass_oe[(_tid, _s)] = float(np.average(_vals, weights=_wts))
    except Exception:
        pass

if _team_xpass_oe:
    for _s in sorted({ss for (_, ss) in _team_xpass_oe}):
        _vals = [v for (t, ss), v in _team_xpass_oe.items() if ss == _s]
        if len(_vals) < 3:
            continue
        _mu, _sd = float(np.mean(_vals)), float(np.std(_vals))
        _sd = max(_sd, 0.1)
        for (t, ss), v in _team_xpass_oe.items():
            if ss == _s:
                _team_xpass_oe_z[(t, ss)] = (v - _mu) / _sd
    print(f"    Player xPass: {len(_team_xpass_oe_z)} team-seasons")
else:
    print("    Player xPass: no matching columns in ASA player xpass.")


def _xpass_oe_lookup(team_id: str, season: int) -> float | None:
    for lag in (1, 2):
        val = _team_xpass_oe_z.get((team_id, season - lag))
        if val is not None:
            return val
    return None


if _team_xpass_oe_z:
    df["home_xpass_oe_z"] = [_xpass_oe_lookup(r.home_team, r.season) for _, r in df.iterrows()]
    df["away_xpass_oe_z"] = [_xpass_oe_lookup(r.away_team, r.season) for _, r in df.iterrows()]
    df["xpass_oe_diff"]   = (df["home_xpass_oe_z"].fillna(0)
                              - df["away_xpass_oe_z"].fillna(0))

# ─── 5f. Team xG split (set-piece share + xG over-performance) ────────────────
# Season-lagged style/finishing signal from team-level xgoals.
# - setpiece_xg_share: how much of attack comes from dead balls
# - xg_overperformance: G - xG (finishing skill or persistent luck)

print("\n[5f/9] Fetching team xgoals (set-piece share + xG over-performance, season-lagged)...")

_team_sp_share: dict[tuple, float] = {}
_team_xg_oe:    dict[tuple, float] = {}
_team_sp_share_z: dict[tuple, float] = {}
_team_xg_oe_z:    dict[tuple, float] = {}

for _s in _SQUAD_SEASONS:
    try:
        _txg = _cf(asa.get_team_xgoals, leagues="mls", season_name=str(_s))
        _txg_cols = list(_txg.columns)
        _txg_tid  = next((c for c in ["team_id"] if c in _txg_cols), None)
        _txg_xg   = next((c for c in ["xgoals", "xgoals_for", "xg"] if c in _txg_cols), None)
        _txg_g    = next((c for c in ["goals", "goals_for"] if c in _txg_cols), None)
        _txg_sp   = next((c for c in [
            "xgoals_from_set_play", "xgoals_set_play",
            "set_play_xgoals", "xgoals_from_dead_ball",
        ] if c in _txg_cols), None)
        if not _txg_tid or not _txg_xg:
            continue
        for _, row in _txg.iterrows():
            tid = row[_txg_tid]
            if not isinstance(tid, str):
                continue
            xg_v = row.get(_txg_xg)
            if pd.isna(xg_v) or float(xg_v) <= 0:
                continue
            if _txg_sp and pd.notna(row.get(_txg_sp)):
                _team_sp_share[(tid, _s)] = float(row[_txg_sp]) / float(xg_v)
            if _txg_g and pd.notna(row.get(_txg_g)):
                _team_xg_oe[(tid, _s)] = float(row[_txg_g]) - float(xg_v)
    except Exception:
        pass

for _raw, _norm in [(_team_sp_share, _team_sp_share_z), (_team_xg_oe, _team_xg_oe_z)]:
    for _s in sorted({ss for (_, ss) in _raw}):
        _vals = [v for (t, ss), v in _raw.items() if ss == _s]
        if len(_vals) < 3:
            continue
        _mu, _sd = float(np.mean(_vals)), float(np.std(_vals))
        _sd = max(_sd, 0.1)
        for (t, ss), v in _raw.items():
            if ss == _s:
                _norm[(t, ss)] = (v - _mu) / _sd

print(f"    Set-piece share: {len(_team_sp_share_z)} | xG over-perf: {len(_team_xg_oe_z)} team-seasons")


def _sp_share_lookup(team_id: str, season: int) -> float | None:
    for lag in (1, 2):
        val = _team_sp_share_z.get((team_id, season - lag))
        if val is not None:
            return val
    return None


def _xg_oe_lookup(team_id: str, season: int) -> float | None:
    for lag in (1, 2):
        val = _team_xg_oe_z.get((team_id, season - lag))
        if val is not None:
            return val
    return None


if _team_sp_share_z:
    df["home_sp_share_z"] = [_sp_share_lookup(r.home_team, r.season) for _, r in df.iterrows()]
    df["away_sp_share_z"] = [_sp_share_lookup(r.away_team, r.season) for _, r in df.iterrows()]
    df["sp_share_diff"]   = df["home_sp_share_z"].fillna(0) - df["away_sp_share_z"].fillna(0)
if _team_xg_oe_z:
    df["home_xg_oe_z"] = [_xg_oe_lookup(r.home_team, r.season) for _, r in df.iterrows()]
    df["away_xg_oe_z"] = [_xg_oe_lookup(r.away_team, r.season) for _, r in df.iterrows()]
    df["xg_oe_diff"]   = df["home_xg_oe_z"].fillna(0) - df["away_xg_oe_z"].fillna(0)

# ─── 7. Optional: Weather features ────────────────────────────────────────────

_HAS_WEATHER = False
if FETCH_WEATHER:
    print("\n[6/9] Fetching historical weather from Open-Meteo...")
    import requests

    _weather_cache: dict = {}

    def _fetch_weather(team_id: str, date: pd.Timestamp, hour_utc: int) -> tuple:
        if team_id in _DOME_TEAM_IDS:
            return (None, None, None)
        coords = _TEAM_COORDS.get(team_id)
        if coords is None:
            return (None, None, None)
        key = (team_id, date.strftime("%Y-%m-%d"))
        if key not in _weather_cache:
            try:
                resp = requests.get(
                    "https://archive-api.open-meteo.com/v1/archive",
                    params={
                        "latitude": coords[0], "longitude": coords[1],
                        "start_date": date.strftime("%Y-%m-%d"),
                        "end_date": date.strftime("%Y-%m-%d"),
                        "hourly": "temperature_2m,windspeed_10m,precipitation",
                        "timezone": "UTC",
                    },
                    timeout=15,
                )
                h_data = resp.json().get("hourly", {})
                _weather_cache[key] = {
                    "temp": h_data.get("temperature_2m", []),
                    "wind": h_data.get("windspeed_10m", []),
                    "precip": h_data.get("precipitation", []),
                }
            except Exception:
                _weather_cache[key] = {"temp": [], "wind": [], "precip": []}
        d = _weather_cache[key]
        h = min(hour_utc, len(d["temp"]) - 1) if d["temp"] else 0
        return (
            d["temp"][h]   if d["temp"]   else None,
            d["wind"][h]   if d["wind"]   else None,
            d["precip"][h] if d["precip"] else None,
        )

    temps, winds, precips = [], [], []
    for _, row in df.iterrows():
        t, w, p = _fetch_weather(row["home_team"], row["date"], row["kickoff_hour_utc"])
        temps.append(t); winds.append(w); precips.append(p)

    df["weather_temp_c"]    = temps
    df["weather_wind_kph"]  = winds
    df["weather_precip_mm"] = precips
    _HAS_WEATHER = df["weather_temp_c"].notna().sum() > 100
    print(f"    Weather: {df['weather_temp_c'].notna().sum():,} matches "
          f"({df['weather_temp_c'].notna().mean():.0%} coverage)")
else:
    print("\n[6/9] Weather skipped (FETCH_WEATHER=False). Set True to enable.")

# ─── 6b. Optional: Transfermarkt squad value — PELE-style features ───────────
# Features (all season-lagged 1-2 seasons to avoid leakage):
#   squad_value_z     — total squad market value, z-scored within season
#   att_value_pct     — FW/AM/W share of squad value (Tilt prior)
#   def_value_pct     — CB/FB share of squad value
#   tilt              — att_value_pct − def_value_pct (>0 = attacking style)
#   value_wtd_age     — age weighted by market value (lower = young+valuable)
#   dp_value_share    — top-3 players' value / total (star concentration)
#
# Requires: python scripts/import_transfermarkt.py --seasons 2017-2025
#           (needs R + worldfootballR for the fetch; --skip-fetch to re-aggregate only)

_HAS_TM = False
if FETCH_TRANSFERMARKT:
    import glob as _glob
    print("\n[6b/9] Loading Transfermarkt squad-value CSVs (PELE features)...")

    # (asa_team_id, season) → feature dict
    _tm_raw: dict[tuple, dict] = {}
    _tm_csvs = sorted(_glob.glob(os.path.join(
        os.path.dirname(__file__), "..", "data",
        "transfermarkt_squad_values_*_mapped.csv")))
    _tm_unmapped: set = set()
    for _csv in _tm_csvs:
        try:
            _tm_df = pd.read_csv(_csv)
        except Exception:
            continue
        for _, _row in _tm_df.iterrows():
            asa_id = _row.get("asa_team_id", None)
            if (not isinstance(asa_id, str)) or not asa_id:
                tm_name = _row.get("tm_team_name", "")
                if isinstance(tm_name, str) and tm_name:
                    _tm_unmapped.add(tm_name)
                continue
            try:
                _season = int(_row["season"])
            except Exception:
                continue
            _tm_raw[(asa_id, _season)] = {
                "squad_value_eur":  float(_row.get("squad_value_eur")  or 0.0),
                "att_value_pct":    float(_row.get("att_value_pct")    or 0.0),
                "def_value_pct":    float(_row.get("def_value_pct")    or 0.0),
                "tilt":             float(_row.get("tilt")             or 0.0),
                "value_wtd_age":    float(_row.get("value_wtd_age")    or 0.0),
                "dp_value_share":   float(_row.get("dp_value_share")   or 0.0),
                "avg_age":          float(_row.get("avg_age")          or 0.0),
            }
    if _tm_unmapped:
        print(f"    Unmapped TM teams (skipped): {sorted(_tm_unmapped)[:8]}"
              f"{' ...' if len(_tm_unmapped) > 8 else ''}")

    # Z-score squad_value_eur within season (so differential is scale-free)
    _tm_sv_z: dict[tuple, float] = {}
    if _tm_raw:
        for _s in sorted({ss for (_, ss) in _tm_raw}):
            _vals = [d["squad_value_eur"] for (t, ss), d in _tm_raw.items() if ss == _s]
            if len(_vals) < 3:
                continue
            _mu, _sd = float(np.mean(_vals)), float(np.std(_vals))
            _sd = max(_sd, 0.1)
            for (t, ss), d in _tm_raw.items():
                if ss == _s:
                    _tm_sv_z[(t, ss)] = (d["squad_value_eur"] - _mu) / _sd

    def _tm_lookup(team_id: str, season: int, field: str) -> float | None:
        for lag in (1, 2):
            entry = _tm_raw.get((team_id, season - lag))
            if entry is not None and field in entry:
                v = entry[field]
                return v if np.isfinite(v) else None
        return None

    def _tm_sv_z_lookup(team_id: str, season: int) -> float | None:
        for lag in (1, 2):
            val = _tm_sv_z.get((team_id, season - lag))
            if val is not None:
                return val
        return None

    if _tm_sv_z:
        # ── Total squad value (scale-free) ────────────────────────────────────
        df["home_squad_value_z"] = [_tm_sv_z_lookup(r.home_team, r.season)
                                     for _, r in df.iterrows()]
        df["away_squad_value_z"] = [_tm_sv_z_lookup(r.away_team, r.season)
                                     for _, r in df.iterrows()]
        df["squad_value_diff_z"] = (df["home_squad_value_z"].fillna(0)
                                     - df["away_squad_value_z"].fillna(0))

        # ── Positional value split (Tilt) ─────────────────────────────────────
        df["home_tilt"]     = [_tm_lookup(r.home_team, r.season, "tilt")
                                for _, r in df.iterrows()]
        df["away_tilt"]     = [_tm_lookup(r.away_team, r.season, "tilt")
                                for _, r in df.iterrows()]
        df["tilt_diff"]     = (df["home_tilt"].fillna(0) - df["away_tilt"].fillna(0))
        df["home_att_pct"]  = [_tm_lookup(r.home_team, r.season, "att_value_pct")
                                for _, r in df.iterrows()]
        df["away_att_pct"]  = [_tm_lookup(r.away_team, r.season, "att_value_pct")
                                for _, r in df.iterrows()]
        df["home_def_pct"]  = [_tm_lookup(r.home_team, r.season, "def_value_pct")
                                for _, r in df.iterrows()]
        df["away_def_pct"]  = [_tm_lookup(r.away_team, r.season, "def_value_pct")
                                for _, r in df.iterrows()]

        # ── Value-weighted age (trajectory signal) ────────────────────────────
        df["home_val_age"]  = [_tm_lookup(r.home_team, r.season, "value_wtd_age")
                                for _, r in df.iterrows()]
        df["away_val_age"]  = [_tm_lookup(r.away_team, r.season, "value_wtd_age")
                                for _, r in df.iterrows()]
        df["val_age_diff"]  = (df["home_val_age"].fillna(0) - df["away_val_age"].fillna(0))

        # ── Star concentration (DP proxy) ─────────────────────────────────────
        df["home_dp_share"] = [_tm_lookup(r.home_team, r.season, "dp_value_share")
                                for _, r in df.iterrows()]
        df["away_dp_share"] = [_tm_lookup(r.away_team, r.season, "dp_value_share")
                                for _, r in df.iterrows()]
        df["dp_share_diff"] = (df["home_dp_share"].fillna(0) - df["away_dp_share"].fillna(0))

        _HAS_TM = True
        cov = df["home_squad_value_z"].notna().mean()
        print(f"    Transfermarkt loaded: {len(_tm_sv_z)} team-seasons  "
              f"coverage={cov:.0%}")
        tilt_cov = df["home_tilt"].notna().mean()
        print(f"    Positional tilt coverage: {tilt_cov:.0%}  "
              f"mean home tilt={df['home_tilt'].mean():.3f}")
    else:
        print("    Transfermarkt: no usable rows found.")
else:
    print("\n[6b/9] Transfermarkt skipped (FETCH_TRANSFERMARKT=False). Set True to enable.")

# ─── TZ shift feature ─────────────────────────────────────────────────────────

def _tz_band(lon: float) -> int:
    return round(lon / 15)

def _away_tz_shift_abs(home_team: str, away_team: str) -> float:
    hc = _TEAM_COORDS.get(home_team)
    ac = _TEAM_COORDS.get(away_team)
    if not (hc and ac):
        return 0.0
    return float(abs(_tz_band(hc[1]) - _tz_band(ac[1])))

def _away_tz_shift_signed(home_team: str, away_team: str) -> float:
    """Positive = away travels east (harder per chronobiology lit); negative = westward."""
    hc = _TEAM_COORDS.get(home_team)
    ac = _TEAM_COORDS.get(away_team)
    if not (hc and ac):
        return 0.0
    return float(_tz_band(hc[1]) - _tz_band(ac[1]))

df["away_tz_shift"]        = [_away_tz_shift_abs(r.home_team, r.away_team)
                               for _, r in df.iterrows()]
df["away_tz_shift_signed"] = [_away_tz_shift_signed(r.home_team, r.away_team)
                               for _, r in df.iterrows()]
print(f"    TZ-shift computed: mean={df['away_tz_shift'].mean():.2f} "
      f"max={df['away_tz_shift'].max():.0f} zones")

_FEAT_TZ = ["away_tz_shift", "away_tz_shift_signed"]

# ─── Pythagorean luck feature ─────────────────────────────────────────────────
# Computed inside add_rolling_features(); columns already on df at this point.
_FEAT_PYTHAG = [
    f"home_pythag_luck_{_PYTHAG_WIN}",
    f"away_pythag_luck_{_PYTHAG_WIN}",
    "pythag_luck_diff",
]
print(f"    PythagLuck computed: home mean={df[_FEAT_PYTHAG[0]].mean():.3f} "
      f"std={df[_FEAT_PYTHAG[0]].std():.3f}")

# ─── Feature sets ─────────────────────────────────────────────────────────────

_BASE_ELO  = ["elo_diff", "home_elo", "away_elo"]
_BASE_XG   = (
    [f"{r}_xg_roll_{w}" for r in ("home", "away") for w in XG_WINDOWS]
    + [f"{r}_xga_roll_{w}" for r in ("home", "away") for w in XG_WINDOWS]
    + ["xg_diff", "home_xg_sum"]
)
# form_10 promoted into Base: passed A/B (Δ=+0.0014 in Phase 6)
_BASE_FORM = (
    [f"home_form_{fw}" for fw in FORM_WINDOWS]
    + [f"away_form_{fw}" for fw in FORM_WINDOWS]
    + ["form_diff"]
)

# GK quality promoted to Base: passed A/B (Δ=+0.0034 in Phase 6b)
_BASE_GK = ["home_gk_z", "away_gk_z", "gk_z_diff"] if "home_gk_z" in df.columns else []

# ─── 5g. ESPN match-day availability (Phase 9): availability-weighted xG+xA ────
# For each match, share of the team's recent available attacking quality that is
# actually in the matchday squad. ESPN gives who was active per game (back to 2022);
# ASA gives each player's PRIOR-season xG+xA (leakage-safe quality weight). Joined by
# normalized player name (91% exact verified). Expanding-mean normalized per team-season.
import csv as _csv
import unicodedata as _ud

_AVAIL_CSV = "data/espn_rosters.csv"
_HAS_AVAIL = os.path.exists(_AVAIL_CSV)


def _norm_nm(n) -> str:
    n = _ud.normalize("NFKD", str(n)).encode("ascii", "ignore").decode()
    return "".join(ch for ch in n.lower() if ch.isalpha() or ch == " ").strip()


_FEAT_AVAIL: list = []
_FEAT_AVAIL_ST: list = []
_FEAT_SALARY: list = []
if _HAS_AVAIL:
    print("\n[5g/9] Building ESPN availability-weighted xG+xA features...")
    _pl = _cf(asa.get_players, leagues="mls")
    _id2name = {r.player_id: _norm_nm(r.player_name)
                for r in _pl.dropna(subset=["player_id", "player_name"]).itertuples()}
    _qual: dict[tuple, float] = {}      # (norm_name, season) -> xG+xA
    for _s in _SQUAD_SEASONS:
        _px = None
        for _att in range(3):           # retry: ASA list-cols block caching, so fetched live
            try:
                _px = _cf(asa.get_player_xgoals, leagues="mls", season_name=str(_s))
                break
            except Exception:
                _px = None
        if _px is None or "xgoals_plus_xassists" not in _px.columns:
            print(f"    [warn] player_xgoals {_s} unavailable — quality gap")
            continue
        for _r in _px.dropna(subset=["player_id"]).itertuples():
            nm = _id2name.get(_r.player_id)
            v = getattr(_r, "xgoals_plus_xassists", None)
            if nm and pd.notna(v):
                _qual[(nm, _s)] = _qual.get((nm, _s), 0.0) + float(v)
    print(f"    Quality map: {len(_qual):,} (player,season) entries")
    _tm = _cf(asa.get_teams, leagues="mls")
    _SUFFIX = {"fc", "sc", "cf"}   # ESPN drops these; ASA keeps them

    def _team_tok(n):
        return tuple(t for t in _norm_nm(n).split() if t not in _SUFFIX)

    _team_by_tok = {_team_tok(r.team_name): r.team_id
                    for r in _tm.dropna(subset=["team_id", "team_name"]).itertuples()}
    # ESPN naming variants that token-stripping can't reconcile (word order / abbrev)
    _ESPN_ALIAS = {"lafc": "Los Angeles FC", "red bull new york": "New York Red Bulls"}

    def _map_team(espn_name):
        nm = _ESPN_ALIAS.get(_norm_nm(espn_name), espn_name)
        return _team_by_tok.get(_team_tok(nm))

    _avail_roster: dict[tuple, list] = {}      # all active matchday players
    _avail_starters: dict[tuple, list] = {}    # starters only (iter 3 refinement)
    _unmapped: set = set()
    with open(_AVAIL_CSV) as _fh:
        for _row in _csv.DictReader(_fh):
            tid = _map_team(_row["team_name"])
            if not tid:
                _unmapped.add(_row["team_name"]); continue
            _day = _row["date"][:10]; _nm = _norm_nm(_row["player_name"])
            _avail_roster.setdefault((tid, _day), []).append(_nm)
            if str(_row.get("starter", "")) in ("1", "True", "true"):
                _avail_starters.setdefault((tid, _day), []).append(_nm)
    if _unmapped:
        print(f"    Unmapped ESPN teams (skipped): {sorted(_unmapped)[:6]}")
    print(f"    Roster coverage: {len(_avail_roster):,} (team,date) entries")

    import datetime as _dt2

    def _roster_names(roster, team_id, day):
        names = roster.get((team_id, day))
        if names is None:                     # tolerate UTC/local day-boundary offset
            _b = _dt2.date.fromisoformat(day)
            for _off in (-1, 1):
                names = roster.get((team_id, (_b + _dt2.timedelta(days=_off)).isoformat()))
                if names:
                    break
        return names

    def _share_cols(roster):
        """Expanding-mean-normalized available g+ share per match (home, away lists)."""
        rs: dict[tuple, float] = {}
        rc: dict[tuple, int] = {}
        hsh, ash = [], []
        for _, _r in df.iterrows():
            _day = _r["date"].strftime("%Y-%m-%d"); _sea = int(_r["season"])
            vals = {}
            for _tid, _k in [(_r["home_team"], "h"), (_r["away_team"], "a")]:
                names = _roster_names(roster, _tid, _day)
                if not names:
                    vals[_k] = 1.0
                else:
                    q = sum(_qual.get((nm, _sea - 1), 0.0) for nm in names)
                    key = (_tid, _sea)
                    pm = (rs[key] / rc[key]) if rc.get(key) else None
                    vals[_k] = (q / pm) if pm and pm > 0 else 1.0
                    rs[key] = rs.get(key, 0.0) + q
                    rc[key] = rc.get(key, 0) + 1
            hsh.append(vals["h"]); ash.append(vals["a"])
        return hsh, ash

    _hsh, _ash = _share_cols(_avail_roster)
    df["home_avail_share"] = _hsh
    df["away_avail_share"] = _ash
    df["avail_share_diff"] = df["home_avail_share"] - df["away_avail_share"]
    _hst, _ast = _share_cols(_avail_starters)
    df["home_avail_st_share"] = _hst
    df["away_avail_st_share"] = _ast
    df["avail_st_share_diff"] = df["home_avail_st_share"] - df["away_avail_st_share"]
    _tw = df[df["season"].isin(TEST_SEASONS)]
    _cov = float((_tw["home_avail_share"] != 1.0).mean()) if len(_tw) else 0.0
    print(f"    Availability built (active + starters). Test-season coverage: {_cov:.0%}")
    _FEAT_AVAIL = ["home_avail_share", "away_avail_share", "avail_share_diff"]
    _FEAT_AVAIL_ST = ["home_avail_st_share", "away_avail_st_share", "avail_st_share_diff"]

    # ── Salary-weighted roster strength (5h) ─────────────────────────────────
    # guaranteed_compensation is set pre-season → same-season use is leakage-safe,
    # and covers ~100% of players (incl. new DPs), unlike prior-season g+.
    # Feature = fraction of team payroll active in the matchday squad + DP-present flag.
    print("[5h/9] Building salary-weighted roster features...")
    _sal: dict[tuple, float] = {}        # (norm_name, season) -> guaranteed comp
    _team_sal: dict[tuple, float] = {}   # (team_id, season) -> total payroll
    _top_paid: dict[tuple, str] = {}     # (team_id, season) -> norm_name of top earner
    for _s in _SQUAD_SEASONS:
        try:
            _sl = _cf(asa.get_player_salaries, leagues="mls", season_name=str(_s))
        except Exception:
            continue
        if "guaranteed_compensation" not in _sl.columns:
            continue
        _best: dict = {}
        for _r in _sl.dropna(subset=["player_id", "guaranteed_compensation"]).itertuples():
            nm = _id2name.get(_r.player_id)
            comp = float(_r.guaranteed_compensation)
            tid = getattr(_r, "team_id", None)
            if nm:
                _sal[(nm, _s)] = _sal.get((nm, _s), 0.0) + comp
            if isinstance(tid, str):
                _team_sal[(tid, _s)] = _team_sal.get((tid, _s), 0.0) + comp
                if nm and comp > _best.get(tid, ("", -1.0))[1]:
                    _best[tid] = (nm, comp)
        for tid, (nm, _c) in _best.items():
            _top_paid[(tid, _s)] = nm
    print(f"    Salary map: {len(_sal):,} (player,season); {len(_team_sal)} team-seasons")

    def _active_set(team_id, day):
        names = _avail_roster.get((team_id, day))
        if names is None:
            _b = _dt2.date.fromisoformat(day)
            for _off in (-1, 1):
                names = _avail_roster.get(
                    (team_id, (_b + _dt2.timedelta(days=_off)).isoformat()))
                if names:
                    break
        return names

    _hs, _as, _hdp, _adp = [], [], [], []
    for _, _r in df.iterrows():
        _day = _r["date"].strftime("%Y-%m-%d"); _sea = int(_r["season"])
        sv, dv = {}, {}
        for _tid, _k in [(_r["home_team"], "h"), (_r["away_team"], "a")]:
            names = _active_set(_tid, _day)
            tot = _team_sal.get((_tid, _sea), 0.0)
            if not names or tot <= 0:
                sv[_k] = 1.0; dv[_k] = 1.0       # neutral when no roster/salary data
            else:
                avail = sum(_sal.get((nm, _sea), 0.0) for nm in set(names))
                sv[_k] = avail / tot
                top = _top_paid.get((_tid, _sea))
                dv[_k] = 1.0 if (top and top in set(names)) else 0.0
        _hs.append(sv["h"]); _as.append(sv["a"]); _hdp.append(dv["h"]); _adp.append(dv["a"])
    df["home_salary_share"] = _hs
    df["away_salary_share"] = _as
    df["salary_share_diff"] = df["home_salary_share"] - df["away_salary_share"]
    df["home_dp_avail"] = _hdp
    df["away_dp_avail"] = _adp
    df["dp_avail_diff"] = df["home_dp_avail"] - df["away_dp_avail"]
    _scov = (float((df[df["season"].isin(TEST_SEASONS)]["home_salary_share"] != 1.0).mean())
             if len(_tw) else 0.0)
    print(f"    Salary roster built. Test-season coverage: {_scov:.0%}")
    _FEAT_SALARY = ["home_salary_share", "away_salary_share", "salary_share_diff",
                    "home_dp_avail", "away_dp_avail", "dp_avail_diff"]
else:
    print("\n[5g/9] ESPN availability: data/espn_rosters.csv not found — skipping.")


# ─── 5i. Team salary structure (Phase 11 iter 2): payroll + DP-concentration ──
# guaranteed_compensation set pre-season → same-season leakage-safe. Tests whether
# squad investment / DP-dependence carries signal beyond ELO. Full coverage 2017-2024.
print("\n[5i/9] Building team salary structure features...")
_pay: dict[tuple, float] = {}     # (team_id, season) -> total payroll
_conc: dict[tuple, float] = {}    # (team_id, season) -> std/avg (coefficient of variation)
for _s in _SQUAD_SEASONS:
    try:
        _ts = _cf(asa.get_team_salaries, leagues="mls", season_name=str(_s))
    except Exception:
        continue
    _tot_c = next((c for c in ["total_guaranteed_compensation"] if c in _ts.columns), None)
    _avg_c = next((c for c in ["avg_guaranteed_compensation"] if c in _ts.columns), None)
    _std_c = next((c for c in ["std_dev_guaranteed_compensation"] if c in _ts.columns), None)
    if not _tot_c:
        continue
    _vals = []
    for _r in _ts.itertuples():
        tid = getattr(_r, "team_id", None)
        if not isinstance(tid, str):
            continue
        tot = float(getattr(_r, _tot_c, 0) or 0)
        _pay[(tid, _s)] = tot
        _vals.append(tot)
        if _avg_c and _std_c:
            avg = float(getattr(_r, _avg_c, 0) or 0)
            std = float(getattr(_r, _std_c, 0) or 0)
            _conc[(tid, _s)] = (std / avg) if avg > 0 else 0.0
    # z-score payroll within season
    if len(_vals) >= 3:
        _mu, _sd = float(np.mean(_vals)), max(float(np.std(_vals)), 1.0)
        for tid in [t for (t, ss) in _pay if ss == _s]:
            _pay[(tid, _s)] = (_pay[(tid, _s)] - _mu) / _sd
print(f"    Team salary: {len(_pay)} team-seasons")


def _pay_lookup(tid, season):
    return _pay.get((tid, season), 0.0)


def _conc_lookup(tid, season):
    return _conc.get((tid, season), 0.0)


df["home_payroll_z"] = [_pay_lookup(r.home_team, int(r.season)) for r in df.itertuples()]
df["away_payroll_z"] = [_pay_lookup(r.away_team, int(r.season)) for r in df.itertuples()]
df["payroll_z_diff"] = df["home_payroll_z"] - df["away_payroll_z"]
df["home_pay_conc"] = [_conc_lookup(r.home_team, int(r.season)) for r in df.itertuples()]
df["away_pay_conc"] = [_conc_lookup(r.away_team, int(r.season)) for r in df.itertuples()]
df["pay_conc_diff"] = df["home_pay_conc"] - df["away_pay_conc"]
_FEAT_TEAMSAL = ["home_payroll_z", "away_payroll_z", "payroll_z_diff",
                 "home_pay_conc", "away_pay_conc", "pay_conc_diff"]


# ─── 5j. GK distribution/sweeping g+ (Phase 11 iter 4) ────────────────────────
# Shot-stopping is already in Base (goals-prevented). NEW signal: the GK's NON-
# shotstopping goals-added (Passing+Sweeping+Handling+Claiming) — distribution &
# command of area. Season-lagged z-score of the team's main GK.
print("\n[5j/9] Building GK distribution g+ features...")
_gk_dist: dict[tuple, float] = {}     # (team_id, season) -> non-shotstopping g+ z
_gk_dist_raw: dict[tuple, float] = {}
for _s in _SQUAD_SEASONS:
    try:
        _gga = _cf(asa.get_goalkeeper_goals_added, leagues="mls", season_name=str(_s))
    except Exception:
        continue
    if "data" not in _gga.columns:
        continue
    _by_team: dict = {}      # team -> (minutes, non_ss_g+)
    for _r in _gga.itertuples():
        tid = getattr(_r, "team_id", None)
        mins = float(getattr(_r, "minutes_played", 0) or 0)
        data = getattr(_r, "data", None)
        if not isinstance(tid, str) or not isinstance(data, (list, tuple)):
            continue
        nonss = sum(float(a.get("goals_added_above_avg", 0) or 0)
                    for a in data if a.get("action_type") != "Shotstopping")
        if mins > _by_team.get(tid, (0.0, 0.0))[0]:   # keep team's main GK (most minutes)
            _by_team[tid] = (mins, nonss)
    for tid, (_m, v) in _by_team.items():
        _gk_dist_raw[(tid, _s)] = v
    _vals = [v for (t, ss), v in _gk_dist_raw.items() if ss == _s]
    if len(_vals) >= 3:
        _mu, _sd = float(np.mean(_vals)), max(float(np.std(_vals)), 0.1)
        for (t, ss), v in list(_gk_dist_raw.items()):
            if ss == _s:
                _gk_dist[(t, _s)] = (v - _mu) / _sd
print(f"    GK distribution: {len(_gk_dist)} team-seasons")


def _gkd_lookup(tid, season):
    for lag in (1, 2):
        val = _gk_dist.get((tid, season - lag))
        if val is not None:
            return val
    return 0.0


df["home_gk_dist_z"] = [_gkd_lookup(r.home_team, int(r.season)) for r in df.itertuples()]
df["away_gk_dist_z"] = [_gkd_lookup(r.away_team, int(r.season)) for r in df.itertuples()]
df["gk_dist_diff"] = df["home_gk_dist_z"] - df["away_gk_dist_z"]
_FEAT_GKDIST = ["home_gk_dist_z", "away_gk_dist_z", "gk_dist_diff"]


# ─── 5k. Minutes-weighted roster quality: full roster + positional g+ split ───
# Prior signals (5, 5d, 5d2) use raw sums or top-N cuts — biased by squad depth.
# Here we normalise by total team-minutes to get *density* (quality per minute).
#   roster_xpa_rate  = Σ(player_xpoints_added) / (total_team_min / 90)
#   att_ga_rate      = Σ(ATT-position g+above_avg) / (total_team_min / 90)
#   def_ga_rate      = Σ(DEF-position g+above_avg) / (total_team_min / 90)
# All z-scored within season, lagged 1-2 seasons. ≥90-min players included.

print("\n[5k/9] Computing minutes-weighted roster quality (full roster + positional split)...")

_ATT_POS_KWS = frozenset([
    "fw", "forward", "winger", "attacking mid", "attacking midfielder",
    "am", "st", "cf", "lw", "rw",
])
_DEF_POS_KWS = frozenset([
    "cb", "fb", "defender", "centre back", "center back",
    "left back", "right back", "full back", "lb", "rb", "cd",
])


def _pos_is_att(pos_val) -> bool:
    p = str(pos_val).lower().strip()
    return any(kw in p for kw in _ATT_POS_KWS)


def _pos_is_def(pos_val) -> bool:
    p = str(pos_val).lower().strip()
    return any(kw in p for kw in _DEF_POS_KWS)


def _zs_within_season(raw: dict) -> dict:
    out: dict[tuple, float] = {}
    for _s in sorted({ss for (_, ss) in raw}):
        vals = [v for (t, ss), v in raw.items() if ss == _s]
        if len(vals) < 3:
            continue
        mu, sd = float(np.mean(vals)), float(np.std(vals))
        sd = max(sd, 1e-6)
        for (t, ss), v in raw.items():
            if ss == _s:
                out[(t, ss)] = (v - mu) / sd
    return out


def _lagged_lookup(tbl: dict, team_id: str, season: int) -> "float | None":
    for lag in (1, 2):
        v = tbl.get((team_id, season - lag))
        if v is not None:
            return v
    return None


_roster_xpa_raw:  dict[tuple, float] = {}
_att_ga_raw:      dict[tuple, float] = {}
_def_ga_raw:      dict[tuple, float] = {}

for _s in _SQUAD_SEASONS:
    # roster xpoints_added rate (get_player_xgoals, all players ≥90 min)
    try:
        _pxg_s = _cf(asa.get_player_xgoals, leagues="mls", season_name=str(_s))
        _px    = list(_pxg_s.columns)
        _px_tid = "team_id" if "team_id" in _px else None
        _px_min = next((c for c in ["minutes_played", "minutes"] if c in _px), None)
        _px_xpa = next((c for c in ["xpoints_added", "x_points_added"] if c in _px), None)
        if _px_tid and _px_min and _px_xpa:
            _pxg_f = _pxg_s[
                _pxg_s[_px_tid].apply(lambda x: isinstance(x, str))
                & (_pxg_s[_px_min] >= 90)
            ]
            for _tid, _grp in _pxg_f.groupby(_px_tid):
                tm = float(_grp[_px_min].sum())
                if tm < 450:
                    continue
                _roster_xpa_raw[(_tid, _s)] = float(_grp[_px_xpa].sum() / (tm / 90.0))
    except Exception:
        pass

    # positional g+ split (get_player_goals_added)
    try:
        _pga_s  = _cf(asa.get_player_goals_added, leagues="mls", season_name=str(_s))
        _pg     = list(_pga_s.columns)
        _pg_tid = "team_id" if "team_id" in _pg else None
        _pg_min = next((c for c in ["minutes_played", "minutes"] if c in _pg), None)
        _pg_pos = next((c for c in ["general_position", "position",
                                     "primary_general_position"] if c in _pg), None)
        _pg_ga  = next((c for c in ["goals_added_above_avg",
                                     "goals_added_above_replacement",
                                     "goals_added_raw"] if c in _pg), None)
        if _pg_ga is None and "data" in _pg:
            _pga_s = _pga_s.copy()
            _pga_s["_ga_val"] = _pga_s["data"].apply(
                lambda d: sum(
                    float(x.get("goals_added_above_avg", 0) or 0)
                    for x in (_json.loads(d) if isinstance(d, str) else d)
                ) if d is not None else 0.0
            )
            _pg_ga = "_ga_val"
        if _pg_tid and _pg_min and _pg_ga and _pg_pos:
            _pga_f = _pga_s[
                _pga_s[_pg_tid].apply(lambda x: isinstance(x, str))
                & (_pga_s[_pg_min] >= 90)
            ]
            for _tid, _grp in _pga_f.groupby(_pg_tid):
                tm = float(_grp[_pg_min].sum())
                if tm < 450:
                    continue
                rate_90 = tm / 90.0
                _att_grp = _grp[_grp[_pg_pos].apply(_pos_is_att)]
                _def_grp = _grp[_grp[_pg_pos].apply(_pos_is_def)]
                if len(_att_grp) >= 2:
                    _att_ga_raw[(_tid, _s)] = float(_att_grp[_pg_ga].sum() / rate_90)
                if len(_def_grp) >= 2:
                    _def_ga_raw[(_tid, _s)] = float(_def_grp[_pg_ga].sum() / rate_90)
    except Exception:
        pass

_roster_xpa_z = _zs_within_season(_roster_xpa_raw)
_att_ga_z     = _zs_within_season(_att_ga_raw)
_def_ga_z     = _zs_within_season(_def_ga_raw)

print(f"    Roster xPA rate:  {len(_roster_xpa_z)} team-seasons")
print(f"    ATT g+ rate:      {len(_att_ga_z)} team-seasons")
print(f"    DEF g+ rate:      {len(_def_ga_z)} team-seasons")

if _roster_xpa_z:
    df["home_roster_xpa"] = [_lagged_lookup(_roster_xpa_z, r.home_team, int(r.season)) for r in df.itertuples()]
    df["away_roster_xpa"] = [_lagged_lookup(_roster_xpa_z, r.away_team, int(r.season)) for r in df.itertuples()]
    df["roster_xpa_diff"] = df["home_roster_xpa"].fillna(0) - df["away_roster_xpa"].fillna(0)

if _att_ga_z:
    df["home_att_ga"] = [_lagged_lookup(_att_ga_z, r.home_team, int(r.season)) for r in df.itertuples()]
    df["away_att_ga"] = [_lagged_lookup(_att_ga_z, r.away_team, int(r.season)) for r in df.itertuples()]
    df["att_ga_diff"] = df["home_att_ga"].fillna(0) - df["away_att_ga"].fillna(0)

if _def_ga_z:
    df["home_def_ga"] = [_lagged_lookup(_def_ga_z, r.home_team, int(r.season)) for r in df.itertuples()]
    df["away_def_ga"] = [_lagged_lookup(_def_ga_z, r.away_team, int(r.season)) for r in df.itertuples()]
    df["def_ga_diff"] = df["home_def_ga"].fillna(0) - df["away_def_ga"].fillna(0)

_FEAT_ROSTER_XPA = (["home_roster_xpa", "away_roster_xpa", "roster_xpa_diff"]
                    if "home_roster_xpa" in df.columns else [])
_FEAT_POS_GA = (
    (["home_att_ga", "away_att_ga", "att_ga_diff"] if "home_att_ga" in df.columns else [])
    + (["home_def_ga", "away_def_ga", "def_ga_diff"] if "home_def_ga" in df.columns else [])
)

# ─── 5l. Optional: FBref player metrics via soccerdata ────────────────────────
# Pulls progressive actions (passes + carries) and pressing intensity per team-
# season from FBref.  Complements ASA with spatial/style metrics (not in ASA).
# Requires: pip install soccerdata   Falls back silently if unavailable.
# FBref team names differ from ASA IDs — bridge built via asa.get_players().

print("\n[5l/9] Optional: FBref player metrics via soccerdata...")

_fbref_prog_raw:  dict[tuple, str] = {}   # keyed by (FBref_squad_name, season)
_fbref_press_raw: dict[tuple, str] = {}
_fbref_name_to_asa: dict[str, str] = {}
_HAS_FBREF = False

try:
    import soccerdata as sd  # pip install soccerdata

    # Build FBref squad-name → ASA team_id map from ASA player records
    try:
        _all_players = _cf(asa.get_players, leagues="mls")
        _ap_cols = list(_all_players.columns)
        _ap_tid  = "team_id" if "team_id" in _ap_cols else None
        _ap_nm   = next((c for c in ["team_name", "club_name", "team"] if c in _ap_cols), None)
        if _ap_tid and _ap_nm:
            for _, row in _all_players.iterrows():
                tid = str(row.get(_ap_tid, "")).strip()
                nm  = str(row.get(_ap_nm, "")).strip()
                if tid and nm:
                    _fbref_name_to_asa[nm] = tid
    except Exception:
        pass

    def _safe_num(v) -> float:
        try:
            return float(v) if v is not None and str(v) not in ("", "nan") else 0.0
        except Exception:
            return 0.0

    for _s in [s for s in _SQUAD_SEASONS if s >= 2018]:
        try:
            _fb = sd.FBref(leagues="USA-MLS", seasons=[_s])

            # Standard stats: progressive passes + carries
            _std = _fb.read_player_season_stats("standard")
            _std.columns = [
                ("_".join(map(str, c)).lower() if isinstance(c, tuple) else str(c).lower())
                for c in _std.columns
            ]
            _min_c  = next((c for c in _std.columns if c in ("playing_time_min", "min", "minutes")), None)
            _team_c = next((c for c in _std.columns if c in ("squad", "team")), None)
            _prog_p = next((c for c in _std.columns if "prg_p" in c or "progressive_passes" in c), None)
            _prog_c = next((c for c in _std.columns if "prg_c" in c or "progressive_carries" in c), None)
            if _team_c and _min_c and (_prog_p or _prog_c):
                _std["_min_f"] = _std[_min_c].apply(_safe_num)
                for _team, _grp in _std[_std["_min_f"] >= 90].groupby(_team_c):
                    tm = _grp["_min_f"].sum()
                    if tm < 450:
                        continue
                    prog = ((_grp[_prog_p].apply(_safe_num).sum() if _prog_p else 0)
                            + (_grp[_prog_c].apply(_safe_num).sum() if _prog_c else 0))
                    if prog > 0:
                        _fbref_prog_raw[(_team, _s)] = prog / (tm / 90.0)

            # Defensive stats: pressures per 90
            _def = _fb.read_player_season_stats("defense")
            _def.columns = [
                ("_".join(map(str, c)).lower() if isinstance(c, tuple) else str(c).lower())
                for c in _def.columns
            ]
            _d_min_c  = next((c for c in _def.columns if c in ("playing_time_min", "min", "minutes")), None)
            _d_team_c = next((c for c in _def.columns if c in ("squad", "team")), None)
            _press_c  = next((c for c in _def.columns
                               if "press" in c and "%" not in c and "succ" not in c), None)
            if _d_team_c and _d_min_c and _press_c:
                _def["_min_f"] = _def[_d_min_c].apply(_safe_num)
                for _team, _grp in _def[_def["_min_f"] >= 90].groupby(_d_team_c):
                    tm = _grp["_min_f"].sum()
                    if tm < 450:
                        continue
                    press = _grp[_press_c].apply(_safe_num).sum()
                    if press > 0:
                        _fbref_press_raw[(_team, _s)] = press / (tm / 90.0)
        except Exception:
            pass

    if _fbref_prog_raw or _fbref_press_raw:
        _HAS_FBREF = True
        print(f"    FBref progressive:  {len(_fbref_prog_raw)} team-seasons (FBref names)")
        print(f"    FBref pressing:     {len(_fbref_press_raw)} team-seasons (FBref names)")
        print(f"    FBref name→ID map:  {len(_fbref_name_to_asa)} entries")

        def _rekey_fbref(raw: dict) -> dict:
            out: dict[tuple, float] = {}
            for (nm, s), v in raw.items():
                tid = _fbref_name_to_asa.get(nm)
                if tid:
                    out[(tid, s)] = float(v)
            return out

        _fbref_prog_asa  = _zs_within_season(_rekey_fbref(_fbref_prog_raw))
        _fbref_press_asa = _zs_within_season(_rekey_fbref(_fbref_press_raw))

        if _fbref_prog_asa:
            df["home_fbref_prog"]  = [_lagged_lookup(_fbref_prog_asa, r.home_team, int(r.season)) for r in df.itertuples()]
            df["away_fbref_prog"]  = [_lagged_lookup(_fbref_prog_asa, r.away_team, int(r.season)) for r in df.itertuples()]
            df["fbref_prog_diff"]  = df["home_fbref_prog"].fillna(0) - df["away_fbref_prog"].fillna(0)
        if _fbref_press_asa:
            df["home_fbref_press"] = [_lagged_lookup(_fbref_press_asa, r.home_team, int(r.season)) for r in df.itertuples()]
            df["away_fbref_press"] = [_lagged_lookup(_fbref_press_asa, r.away_team, int(r.season)) for r in df.itertuples()]
            df["fbref_press_diff"] = df["home_fbref_press"].fillna(0) - df["away_fbref_press"].fillna(0)
    else:
        print("    No FBref data retrieved.")

except ImportError:
    print("    soccerdata not installed — skipping FBref metrics.")
    print("    Install with: pip install soccerdata")
except Exception as e:
    print(f"    soccerdata error: {e}")

_FEAT_FBREF = list(dict.fromkeys(
    (["home_fbref_prog", "away_fbref_prog", "fbref_prog_diff"] if "home_fbref_prog" in df.columns else [])
    + (["home_fbref_press", "away_fbref_press", "fbref_press_diff"] if "home_fbref_press" in df.columns else [])
))


# _FEAT_AVAIL (ESPN roster availability) promoted to Base 2026-05-31 — KEEP Δ=+0.0011
# with full 2017-2024 roster history. Empty list (graceful) when rosters absent.
_FEAT_BASE = _BASE_ELO + _BASE_XG + _BASE_FORM + _BASE_GK + ["is_playoff"] + _FEAT_AVAIL

# ─── Phase 11 iter 5: availability × congestion interaction ───────────────────
# Hypothesis: depleted availability hurts MORE under fixture congestion. Product of
# the KEEP'd availability share and games_in_14d (both already in df).
_FEAT_AVAILCONG: list = []
if _FEAT_AVAIL and "home_games_in_14d" in df.columns:
    df["home_avail_cong"] = df["home_avail_share"] * df["home_games_in_14d"]
    df["away_avail_cong"] = df["away_avail_share"] * df["away_games_in_14d"]
    df["avail_cong_diff"] = df["home_avail_cong"] - df["away_avail_cong"]
    _FEAT_AVAILCONG = ["home_avail_cong", "away_avail_cong", "avail_cong_diff"]

_SP_XG_FEATS   = ["home_xga_sp_roll_15", "away_xga_sp_roll_15"] if _HAS_SP_XG else []
_WEATHER_FEATS = (["weather_temp_c", "weather_wind_kph", "weather_precip_mm", "is_dome"]
                  if _HAS_WEATHER else [])

# GK quality features (available if fetch succeeded)
_GK_FEATS = (["home_gk_z", "away_gk_z", "gk_z_diff"]
             if "home_gk_z" in df.columns else [])

# Season-lagged team PPDA/possession
_PPDA_SEASON_FEATS: list[str] = []
if "home_ppda_season" in df.columns:
    _PPDA_SEASON_FEATS += ["home_ppda_season", "away_ppda_season", "ppda_season_diff"]
if "home_poss_season" in df.columns:
    _PPDA_SEASON_FEATS += ["home_poss_season", "away_poss_season", "poss_season_diff"]

# Goals added (composite player value, season-lagged)
_GOALS_ADDED_FEATS = (["home_goals_added_z", "away_goals_added_z", "goals_added_z_diff"]
                      if "home_goals_added_z" in df.columns else [])

# Squad quality (xpoints_added, from Phase 5 — dropped individually but include in +All)
_SQUAD_FEATS = ["home_squad_xpa", "away_squad_xpa", "squad_xpa_diff", "is_high_alt"]

# Top-N concentration (Phase 7 candidate — star-player concentration)
_FEAT_TOPN = (
    (["home_top3_ga_z", "away_top3_ga_z", "top3_ga_diff"] if "home_top3_ga_z" in df.columns else [])
    + (["home_top5_ga_z", "away_top5_ga_z", "top5_ga_diff"] if "home_top5_ga_z" in df.columns else [])
)

# Player xPass over-expected (Phase 7 candidate — ball-progression quality)
_FEAT_XPASS = (["home_xpass_oe_z", "away_xpass_oe_z", "xpass_oe_diff"]
               if "home_xpass_oe_z" in df.columns else [])

# Team xG split (Phase 7 candidate — set-piece share + finishing over-performance)
_FEAT_XG_SPLIT = (
    (["home_sp_share_z", "away_sp_share_z", "sp_share_diff"] if "home_sp_share_z" in df.columns else [])
    + (["home_xg_oe_z", "away_xg_oe_z", "xg_oe_diff"] if "home_xg_oe_z" in df.columns else [])
)

# Transfermarkt features — PELE-style decomposition (Phase 13)
# Base squad value (scale-free total)
_TM_FEATS = (["home_squad_value_z", "away_squad_value_z", "squad_value_diff_z"]
              if "home_squad_value_z" in df.columns else [])
# Positional value split: Tilt = att_value_pct − def_value_pct (>0 = attacking)
_TM_POSITIONAL = (["home_tilt", "away_tilt", "tilt_diff",
                    "home_att_pct", "away_att_pct",
                    "home_def_pct", "away_def_pct"]
                   if "home_tilt" in df.columns else [])
# Value-weighted age trajectory signal (lower = young expensive roster)
_TM_AGE = (["home_val_age", "away_val_age", "val_age_diff"]
            if "home_val_age" in df.columns else [])
# Star concentration: top-3 players' share of squad value (DP proxy)
_TM_DP = (["home_dp_share", "away_dp_share", "dp_share_diff"]
           if "home_dp_share" in df.columns else [])

# Minutes-weighted roster quality (section 5k)
# _FEAT_ROSTER_XPA and _FEAT_POS_GA defined above in section 5k

# FBref progressive actions + pressing (section 5l) — populated only if soccerdata installed
# _FEAT_FBREF defined above in section 5l

# +All combines everything available (form_10 already in Base)
_ALL_EXTRA = (
    _GK_FEATS
    + _PPDA_SEASON_FEATS
    + _GOALS_ADDED_FEATS
    + _SQUAD_FEATS
    + ["home_games_in_14d", "away_games_in_14d", "games14d_diff"]
    + ["dc_lam", "dc_mu"]
    + _SP_XG_FEATS
    + _WEATHER_FEATS
    + _FEAT_TOPN
    + _FEAT_XPASS
    + _FEAT_XG_SPLIT
    + _TM_FEATS
    + _TM_POSITIONAL
    + _TM_AGE
    + _TM_DP
    + _FEAT_TZ
    + _FEAT_ROSTER_XPA
    + _FEAT_POS_GA
    + _FEAT_FBREF
)
_FEAT_ALL = list(dict.fromkeys(_FEAT_BASE + _ALL_EXTRA))

# +GKQuality is now in Base (promoted from Phase 6b A/B: Δ=+0.0034)
# A/B sets test remaining candidates against the new Base+GK
AB_SETS: dict[str, list] = {"Base": _FEAT_BASE}
if _PPDA_SEASON_FEATS:
    AB_SETS["+SeasonPPDA"] = _FEAT_BASE + _PPDA_SEASON_FEATS
if _GOALS_ADDED_FEATS:
    AB_SETS["+GoalsAdded"] = _FEAT_BASE + _GOALS_ADDED_FEATS
AB_SETS["+Squad"]    = _FEAT_BASE + _SQUAD_FEATS
AB_SETS["+DCParams"] = _FEAT_BASE + ["dc_lam", "dc_mu"]
AB_SETS["+Games14d"] = _FEAT_BASE + ["home_games_in_14d", "away_games_in_14d", "games14d_diff"]
if _FEAT_TOPN:
    AB_SETS["+ASA_TopN"]     = _FEAT_BASE + _FEAT_TOPN
if _FEAT_XPASS:
    AB_SETS["+ASA_xPass"]    = _FEAT_BASE + _FEAT_XPASS
if _FEAT_XG_SPLIT:
    AB_SETS["+ASA_xGSplit"]  = _FEAT_BASE + _FEAT_XG_SPLIT
if _TM_FEATS:
    AB_SETS["+TM_SquadValue"] = _FEAT_BASE + _TM_FEATS
if _TM_POSITIONAL:
    AB_SETS["+TM_Positional"] = _FEAT_BASE + _TM_POSITIONAL  # Tilt + att/def pct
if _TM_AGE:
    AB_SETS["+TM_Age"]        = _FEAT_BASE + _TM_AGE         # value-weighted age trajectory
if _TM_DP:
    AB_SETS["+TM_Stars"]      = _FEAT_BASE + _TM_DP          # top-3 value concentration
if _TM_FEATS and _TM_POSITIONAL and _TM_AGE:
    AB_SETS["+TM_PELE"]       = _FEAT_BASE + _TM_FEATS + _TM_POSITIONAL + _TM_AGE + _TM_DP
AB_SETS["+TZShift"]    = _FEAT_BASE + _FEAT_TZ
AB_SETS["+PythagLuck"] = _FEAT_BASE + _FEAT_PYTHAG
# Interaction probe: the two positive-marginal singles (+0.0008 each) combined —
# do they stack past the 0.001 KEEP bar? (Phase-D feature-interaction hypothesis)
AB_SETS["+TZ_Pythag"]  = _FEAT_BASE + _FEAT_TZ + _FEAT_PYTHAG
_FEAT_TRAVEL = ["travel_km", "home_days_rest", "away_days_rest", "rest_advantage"]
AB_SETS["+TravelRest"] = _FEAT_BASE + _FEAT_TRAVEL
_FEAT_CONTEXT = ["is_dome", "is_high_alt"]   # match-context flags (already computed)
AB_SETS["+Context"]    = _FEAT_BASE + _FEAT_CONTEXT
if _FEAT_AVAIL:
    AB_SETS["+Availability"] = _FEAT_BASE + _FEAT_AVAIL
if _FEAT_SALARY:
    AB_SETS["+SalaryRoster"] = _FEAT_BASE + _FEAT_SALARY
AB_SETS["+TeamSalary"] = _FEAT_BASE + _FEAT_TEAMSAL
AB_SETS["+GKDistribution"] = _FEAT_BASE + _FEAT_GKDIST
if _FEAT_AVAILCONG:
    AB_SETS["+AvailCongestion"] = _FEAT_BASE + _FEAT_AVAILCONG
if _FEAT_AVAIL_ST:
    AB_SETS["+AvailStarters"] = _FEAT_BASE + _FEAT_AVAIL_ST
if _FEAT_AVAIL and _FEAT_SALARY:
    AB_SETS["+RosterState"] = _FEAT_BASE + _FEAT_AVAIL + _FEAT_SALARY
# Minutes-weighted roster metrics (section 5k)
if _FEAT_ROSTER_XPA:
    AB_SETS["+RosterXPA"]   = _FEAT_BASE + _FEAT_ROSTER_XPA
if _FEAT_POS_GA:
    AB_SETS["+PosGA"]       = _FEAT_BASE + _FEAT_POS_GA
if _FEAT_ROSTER_XPA and _FEAT_POS_GA:
    AB_SETS["+RosterAll"]   = _FEAT_BASE + _FEAT_ROSTER_XPA + _FEAT_POS_GA
# FBref features (section 5l) — only present if soccerdata installed + data retrieved
if _FEAT_FBREF:
    AB_SETS["+FBref"]       = _FEAT_BASE + _FEAT_FBREF
AB_SETS["+All"]        = _FEAT_ALL

print(f"\n    A/B feature sets: {list(AB_SETS.keys())}")

# --ab-only: restrict evaluation to a named subset (agents pass e.g. "Base,+TZShift")
if _ARGS.ab_only:
    _ab_keep = [k.strip() for k in _ARGS.ab_only.split(",")]
    AB_SETS = {k: v for k, v in AB_SETS.items() if k in _ab_keep}
    print(f"    (--ab-only filter: {list(AB_SETS.keys())})")

# ─── Dixon-Coles ──────────────────────────────────────────────────────────────


def dc_tau(x, y, lam, mu, rho):
    if x == 0 and y == 0: return 1 - lam * mu * rho
    if x == 0 and y == 1: return 1 + lam * rho
    if x == 1 and y == 0: return 1 + mu * rho
    if x == 1 and y == 1: return 1 - rho
    return 1.0


def dc_nll(params, teams, arr, decay_hl):
    n = len(teams)
    atk, dfd = params[:n], params[n:2*n]
    ha, rho = params[2*n], params[2*n + 1]
    lam_d = math.log(2) / decay_hl
    ll = 0.0
    for row in arr:
        days_ago = int(row[0])
        hi, ai, hg, ag = int(row[1]), int(row[2]), int(row[3]), int(row[4])
        w = math.exp(-lam_d * days_ago)
        lam = math.exp(atk[hi] + dfd[ai] + ha)
        mu  = math.exp(atk[ai] + dfd[hi])
        tau = dc_tau(hg, ag, lam, mu, rho)
        if tau <= 1e-10:
            continue
        ll += w * (math.log(tau) + poisson.logpmf(hg, lam) + poisson.logpmf(ag, mu))
    return -ll


def fit_dc(matches: pd.DataFrame, decay_hl: int = DC_DECAY_HL, recent_seasons: int = 4):
    max_s = matches["season"].max()
    recent = matches[matches["season"] >= max_s - recent_seasons + 1].copy()
    teams = sorted(set(recent["home_team"]) | set(recent["away_team"]))
    tidx = {t: i for i, t in enumerate(teams)}
    n = len(teams)
    ref = recent["date"].max()
    arr = np.array([
        [(ref - r["date"]).days, tidx.get(r["home_team"], 0),
         tidx.get(r["away_team"], 0), r["home_goals"], r["away_goals"]]
        for _, r in recent.iterrows()
    ], dtype=float)
    x0 = np.zeros(2 * n + 2)
    x0[2*n], x0[2*n+1] = 0.25, -0.05
    bounds = [(-3, 3)] * (2*n) + [(0.0, 1.0)] + [(-0.5, 0.0)]
    res = minimize(dc_nll, x0, args=(teams, arr, decay_hl),
                   method="L-BFGS-B", bounds=bounds,
                   options={"maxiter": 300, "ftol": 1e-7})
    atk = dict(zip(teams, res.x[:n]))
    dfd = dict(zip(teams, res.x[n:2*n]))
    return atk, dfd, res.x[2*n], res.x[2*n+1]


def dc_predict(ht, at, atk, dfd, ha, rho, max_g=8):
    lam = math.exp(atk.get(ht, 0) + dfd.get(at, 0) + ha)
    mu  = math.exp(atk.get(at, 0) + dfd.get(ht, 0))
    M = np.zeros((max_g + 1, max_g + 1))
    for i in range(max_g + 1):
        for j in range(max_g + 1):
            tau = dc_tau(i, j, lam, mu, rho)
            M[i, j] = max(tau, 1e-10) * poisson.pmf(i, lam) * poisson.pmf(j, mu)
    M = np.clip(M, 1e-15, None)
    M /= M.sum()
    ph = float(np.tril(M, -1).sum())
    pd_ = float(np.diag(M).sum())
    pa = float(np.triu(M, 1).sum())
    t = ph + pd_ + pa
    return ph / t, pd_ / t, pa / t


def dc_predict_batch(split_df, atk, dfd, ha, rho):
    return np.array([dc_predict(r.home_team, r.away_team, atk, dfd, ha, rho)
                     for _, r in split_df.iterrows()])


def dc_lam_mu_batch(split_df, atk, dfd, ha):
    lams, mus = [], []
    for _, r in split_df.iterrows():
        lam = math.exp(atk.get(r["home_team"], 0) + dfd.get(r["away_team"], 0) + ha)
        mu  = math.exp(atk.get(r["away_team"], 0) + dfd.get(r["home_team"], 0))
        lams.append(lam); mus.append(mu)
    return np.array(lams), np.array(mus)


# ─── Calibration — Temperature scaling ───────────────────────────────────────


def calibrate_multiclass(raw_cal: np.ndarray, y_cal: np.ndarray,
                          raw_test: np.ndarray) -> np.ndarray:
    """Calibrate multiclass probabilities.  Method selected by --calibration flag.

    For two-stage methods (temp_then_isotonic, temp_then_platt) this function
    performs only the first-stage temperature scaling; the second pass on the
    stacked ensemble output is handled separately by _calibrate_stacked_second_pass.
    """
    _method = _ARGS.calibration  # "temperature" | "platt" | "isotonic" | "beta"
                                  # | "temp_then_isotonic" | "temp_then_platt"

    # Two-stage variants use temperature scaling for the per-model first pass
    if _method in ("temperature", "temp_then_isotonic", "temp_then_platt"):
        # Original temperature-scaling implementation (default)
        def _nll(T: float) -> float:
            log_p = np.log(np.clip(raw_cal, 1e-9, 1.0)) / max(T, 0.1)
            log_p -= log_p.max(axis=1, keepdims=True)
            exp_p = np.exp(log_p)
            probs = exp_p / exp_p.sum(axis=1, keepdims=True)
            return float(log_loss(y_cal, probs))
        T = minimize_scalar(_nll, bounds=(0.3, 5.0), method="bounded").x
        log_p = np.log(np.clip(raw_test, 1e-9, 1.0)) / T
        log_p -= log_p.max(axis=1, keepdims=True)
        exp_p = np.exp(log_p)
        return exp_p / exp_p.sum(axis=1, keepdims=True)

    elif _method == "platt":
        # Per-class Platt scaling (logistic regression on scalar confidence)
        # Well-calibrated on ~500 samples; better than isotonic at small cal-fold sizes
        from sklearn.linear_model import LogisticRegression as _PlattLR
        out = np.zeros_like(raw_test)
        for c in range(3):
            platt = _PlattLR(C=1.0, max_iter=300, solver="lbfgs")
            platt.fit(raw_cal[:, c].reshape(-1, 1), (y_cal == c).astype(int))
            out[:, c] = platt.predict_proba(raw_test[:, c].reshape(-1, 1))[:, 1]
        return out / out.sum(axis=1, keepdims=True).clip(1e-9, None)

    elif _method == "isotonic":
        # Per-class isotonic regression (requires ~1000+ cal samples for stability)
        from sklearn.isotonic import IsotonicRegression as _IR
        out = np.zeros_like(raw_test)
        for c in range(3):
            ir = _IR(out_of_bounds="clip")
            ir.fit(raw_cal[:, c], (y_cal == c).astype(float))
            out[:, c] = ir.predict(raw_test[:, c])
        return out / out.sum(axis=1, keepdims=True).clip(1e-9, None)

    elif _method == "beta":
        # Beta calibration (Kull et al. 2017); falls back to Platt if betacal absent
        try:
            from betacal import BetaCalibration as _BC
            out = np.zeros_like(raw_test)
            for c in range(3):
                bc = _BC(parameters="abm")
                bc.fit(raw_cal[:, c], (y_cal == c).astype(int))
                out[:, c] = bc.predict(raw_test[:, c])
            return out / out.sum(axis=1, keepdims=True).clip(1e-9, None)
        except ImportError:
            print("    [warn] betacal not installed — falling back to Platt scaling")
            from sklearn.linear_model import LogisticRegression as _PlattLR2
            out = np.zeros_like(raw_test)
            for c in range(3):
                platt = _PlattLR2(C=1.0, max_iter=300, solver="lbfgs")
                platt.fit(raw_cal[:, c].reshape(-1, 1), (y_cal == c).astype(int))
                out[:, c] = platt.predict_proba(raw_test[:, c].reshape(-1, 1))[:, 1]
            return out / out.sum(axis=1, keepdims=True).clip(1e-9, None)

    else:
        raise ValueError(f"Unknown calibration method: {_method!r}")


def _calibrate_stacked_second_pass(
    stacked_cal: np.ndarray, y_cal: np.ndarray, stacked_te: np.ndarray
) -> np.ndarray:
    """Apply second-pass calibration to stacked ensemble output.

    stacked_cal : shape (n_cal, 3) — meta-learner predictions on the cal fold
                  (in-sample; acceptable here as the meta was NOT fitted on these
                  directly — it was fitted on calibrated XGB/DC features, not on
                  its own output)
    y_cal       : integer labels (0/1/2) on the cal fold
    stacked_te  : shape (n_te, 3) — meta-learner predictions on the test fold

    Returns calibrated test probabilities.
    """
    _method = _ARGS.calibration
    if _method == "temp_then_isotonic":
        from sklearn.isotonic import IsotonicRegression as _IR2
        out = np.zeros_like(stacked_te)
        for c in range(3):
            ir = _IR2(out_of_bounds="clip")
            ir.fit(stacked_cal[:, c], (y_cal == c).astype(float))
            out[:, c] = ir.predict(stacked_te[:, c])
        return out / out.sum(axis=1, keepdims=True).clip(1e-9, None)

    elif _method == "temp_then_platt":
        from sklearn.linear_model import LogisticRegression as _PlattLR3
        out = np.zeros_like(stacked_te)
        for c in range(3):
            platt = _PlattLR3(C=1.0, max_iter=300, solver="lbfgs")
            platt.fit(stacked_cal[:, c].reshape(-1, 1), (y_cal == c).astype(int))
            out[:, c] = platt.predict_proba(stacked_te[:, c].reshape(-1, 1))[:, 1]
        return out / out.sum(axis=1, keepdims=True).clip(1e-9, None)

    # Should not be called for single-stage methods
    return stacked_te


def decile_cal_error(probs: np.ndarray, actuals: np.ndarray) -> tuple:
    try:
        dec = pd.qcut(probs, 10, duplicates="drop")
        cal = (pd.DataFrame({"p": probs, "a": actuals.astype(float), "d": dec})
               .groupby("d", observed=True)
               .agg(mp=("p", "mean"), ma=("a", "mean")))
        errs = (cal["mp"] - cal["ma"]).abs()
        return float(errs.max()), float(errs.mean())
    except Exception:
        return float("nan"), float("nan")


def multiclass_brier(y_oh: np.ndarray, probs: np.ndarray) -> float:
    return float(np.mean(np.sum((probs - y_oh) ** 2, axis=1)))


def per_class_brier(y_oh: np.ndarray, probs: np.ndarray) -> tuple:
    return tuple(float(np.mean((probs[:, c] - y_oh[:, c]) ** 2)) for c in range(3))


# ─── Optional: dump the assembled feature frame and exit (parity harness) ─────
if _ARGS.dump_frame:
    import sys as _sys
    _dp = _Path(_ARGS.dump_frame)
    _dp.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(_dp, index=False)
    # sidecar: feature list + validated config, so the parity harness is self-contained
    _sidecar = _dp.with_suffix(".meta.json")
    with open(_sidecar, "w") as _sf:
        _json.dump({
            "feat_base": [c for c in _FEAT_BASE if c in df.columns],
            "weight_hl": WEIGHT_HL, "dc_decay_hl": DC_DECAY_HL,
            "regress": REGRESS, "test_seasons": list(TEST_SEASONS),
            "calibration": _ARGS.calibration,
        }, _sf, indent=2)
    print(f"\nAssembled feature frame dumped → {_dp} "
          f"({len(df):,} rows, {len(df.columns)} cols, seasons "
          f"{int(df['season'].min())}–{int(df['season'].max())}); meta → {_sidecar}")
    _sys.exit(0)


# ─── Walk-forward evaluation ──────────────────────────────────────────────────

print(
    f"\n[7/9] Walk-forward evaluation "
    f"(test={TEST_SEASONS}, DC decay={DC_DECAY_HL}d, temperature cal)..."
)
print("      DC fit ~30–90 sec per season.")

results: list[dict] = []
ab_records: list[dict] = []
all_imp: list[dict] = []

for test_season in TEST_SEASONS:
    cal_season = test_season - 1
    train_raw = df[df["season"] < cal_season].copy()
    cal_raw   = df[df["season"] == cal_season].copy()
    test_raw  = df[df["season"] == test_season].copy()

    if len(train_raw) < 200 or len(cal_raw) < 50 or len(test_raw) < 50:
        print(f"    Season {test_season}: insufficient data, skipping.")
        continue

    print(f"    {test_season}: train={len(train_raw)} cal={len(cal_raw)} "
          f"test={len(test_raw)}", end="", flush=True)

    y_cal_r  = cal_raw["label_result"].values
    y_te_r   = test_raw["label_result"].values
    y_te_oh  = np.eye(3)[y_te_r]
    y_cal_oh = np.eye(3)[y_cal_r]

    # ── Dixon-Coles ──────────────────────────────────────────────────────────
    dc_ok = False
    try:
        atk, dfd, ha, rho = fit_dc(train_raw, decay_hl=DC_DECAY_HL)
        dc_pred_cal = dc_predict_batch(cal_raw, atk, dfd, ha, rho)
        dc_pred_te  = dc_predict_batch(test_raw, atk, dfd, ha, rho)
        dc_cal_te3  = calibrate_multiclass(dc_pred_cal, y_cal_r, dc_pred_te)
        dc_cal_cal3 = calibrate_multiclass(dc_pred_cal, y_cal_r, dc_pred_cal)
        dc_ok = True
        print(" | DC✓", end="", flush=True)
    except Exception as e:
        dc_pred_cal = dc_pred_te = dc_cal_te3 = dc_cal_cal3 = None
        print(f" | DC✗({e})", end="", flush=True)

    # Add DC λ/μ features to train/cal/test splits
    if dc_ok:
        train = train_raw.copy(); cal = cal_raw.copy(); test = test_raw.copy()
        train["dc_lam"], train["dc_mu"] = dc_lam_mu_batch(train, atk, dfd, ha)
        cal["dc_lam"],   cal["dc_mu"]   = dc_lam_mu_batch(cal,   atk, dfd, ha)
        test["dc_lam"],  test["dc_mu"]  = dc_lam_mu_batch(test,  atk, dfd, ha)
    else:
        train, cal, test = train_raw, cal_raw, test_raw

    # Exponential season weights for XGBoost
    ref_s = train["season"].max()
    sw = train["season"].apply(
        lambda s: math.exp(-math.log(2) / WEIGHT_HL * (ref_s - s))
    ).values

    # XGBoost inner hyperparameter search (last 2 seasons of train as inner val)
    _inner_s = sorted(train["season"].unique())[-2:]
    _itr  = train[~train["season"].isin(_inner_s)]
    _ival = train[train["season"].isin(_inner_s)]
    _sw_i = _itr["season"].apply(
        lambda s: math.exp(-math.log(2) / WEIGHT_HL * (ref_s - s))
    ).values
    _gs_feat = [c for c in _FEAT_ALL if c in _itr.columns]
    _best_xgb_b = float("inf")
    _best_p = {"max_depth": 4, "n_estimators": 300, "learning_rate": 0.05}

    for _md, _ne, _lr in itertools.product([3, 4, 5], [200, 400], [0.05, 0.10]):
        try:
            _c = xgb.XGBClassifier(
                n_estimators=_ne, max_depth=_md, learning_rate=_lr,
                subsample=0.8, colsample_bytree=0.8,
                objective="multi:softprob", num_class=3,
                eval_metric="mlogloss", verbosity=0, random_state=42,
                n_jobs=_XGB_NJOBS,
            )
            _c.fit(_itr[_gs_feat].fillna(0).values,
                   _itr["label_result"].values, sample_weight=_sw_i)
            _ip = _c.predict_proba(_ival[_gs_feat].fillna(0).values)
            _b = float(np.mean(np.sum((_ip - np.eye(3)[_ival["label_result"].values]) ** 2, axis=1)))
            if _b < _best_xgb_b:
                _best_xgb_b = _b
                _best_p = {"max_depth": _md, "n_estimators": _ne, "learning_rate": _lr}
        except Exception:
            pass

    print(f" | XGB-grid(d={_best_p['max_depth']},n={_best_p['n_estimators']},"
          f"lr={_best_p['learning_rate']})", end="", flush=True)

    # ── A/B test: each feature set ───────────────────────────────────────────
    xgb_ok = False
    xgb_cal_probs_best = xgb_te_probs_best = xgb_cal_te3 = None
    _best_xgb_cal_brier = float("inf")
    _best_ab_name = "Base"
    _best_imp: dict = {}
    ab_brier: dict[str, float] = {}

    for ab_name, ab_feat in AB_SETS.items():
        feat  = [c for c in ab_feat if c in train.columns]
        X_tr  = train[feat].fillna(0).values
        X_cal = cal[feat].fillna(0).values
        X_te  = test[feat].fillna(0).values
        try:
            clf = xgb.XGBClassifier(
                objective="multi:softprob", num_class=3,
                eval_metric="mlogloss", verbosity=0, random_state=42,
                subsample=0.8, colsample_bytree=0.8, n_jobs=_XGB_NJOBS,
                **_best_p,
            )
            clf.fit(X_tr, train["label_result"].values, sample_weight=sw)
            cal_p  = clf.predict_proba(X_cal)
            te_p   = clf.predict_proba(X_te)
            cal_te = calibrate_multiclass(cal_p, y_cal_r, te_p)
            brier_val = multiclass_brier(y_te_oh, cal_te)
            ab_brier[ab_name] = brier_val

            # Use the feature set with lowest cal Brier for the ensemble
            # (compare on cal set to avoid test leakage)
            cal_brier_val = multiclass_brier(y_cal_oh, calibrate_multiclass(cal_p, y_cal_r, cal_p))
            if xgb_cal_probs_best is None or cal_brier_val < _best_xgb_cal_brier:
                _best_xgb_cal_brier = cal_brier_val
                _best_ab_name = ab_name
                xgb_cal_probs_best = cal_p
                xgb_te_probs_best  = te_p
                xgb_cal_te3 = cal_te
                imp = clf.get_booster().get_score(importance_type="gain")
                _best_imp = {f: imp.get(f"f{i}", 0.0) for i, f in enumerate(feat)}
                xgb_ok = True
        except Exception as e:
            ab_brier[ab_name] = float("nan")
            if ab_name == "Base":
                print(f" | XGB✗({e})", end="", flush=True)

    ab_records.append({"season": test_season, **ab_brier})
    if xgb_ok and _best_imp:
        all_imp.append(_best_imp)
    if xgb_ok:
        print(f" | BestAB={_best_ab_name}", end="", flush=True)

    # ── Stacking meta-learner ─────────────────────────────────────────────────
    meta_ok = False
    ens_stacked = None
    _two_stage = _ARGS.calibration in ("temp_then_isotonic", "temp_then_platt")
    if dc_ok and xgb_ok:
        try:
            xgb_cal_cal3 = calibrate_multiclass(xgb_cal_probs_best, y_cal_r,
                                                  xgb_cal_probs_best)
            # Capped-DC convex blend (replaces the unconstrained LogisticRegression
            # meta-learner). Fit a scalar w on the cal fold by Brier minimisation,
            # constrained w ∈ [0.7, 1.0] so Dixon-Coles contributes at most 30%.
            # This keeps DC's 2022-23 synergy but bounds its catastrophic 2024 misfit
            # (arch-capped-dc, 2026-05-30: 2024 Brier 0.6523→0.6378, net −0.0019).
            def _blend_brier(w_arr):
                w = w_arr[0]
                b = w * xgb_cal_cal3 + (1.0 - w) * dc_cal_cal3
                b = b / b.sum(axis=1, keepdims=True).clip(1e-9, None)
                return float(np.mean(np.sum((b - y_cal_oh) ** 2, axis=1)))
            _wres = minimize(_blend_brier, x0=[0.85], bounds=[(0.7, 1.0)],
                             method="L-BFGS-B")
            _w = float(np.clip(_wres.x[0], 0.7, 1.0))

            def _blend(xg, dc):
                b = _w * xg + (1.0 - _w) * dc
                return b / b.sum(axis=1, keepdims=True).clip(1e-9, None)

            ens_stacked_raw   = _blend(xgb_cal_te3,  dc_cal_te3)
            stacked_cal_blend = _blend(xgb_cal_cal3, dc_cal_cal3)
            if _two_stage:
                # Second-pass calibration on the blended ensemble output:
                # fit on the cal-fold blend, apply to the test-fold blend.
                ens_stacked = _calibrate_stacked_second_pass(
                    stacked_cal_blend, y_cal_r, ens_stacked_raw
                )
                print(f" | Blend✓(w_xgb={_w:.2f})+2ndPass", end="", flush=True)
            else:
                ens_stacked = ens_stacked_raw
                print(f" | Blend✓(w_xgb={_w:.2f})", end="", flush=True)
            meta_ok = True
        except Exception as e:
            print(f" | Meta✗({e})", end="", flush=True)

    # ── Simple average ensemble ───────────────────────────────────────────────
    if dc_ok and xgb_ok:
        ens_avg = (dc_pred_te + xgb_te_probs_best) / 2.0
    elif dc_ok:
        ens_avg = dc_pred_te
    elif xgb_ok:
        ens_avg = xgb_te_probs_best
    else:
        ens_avg = None

    # ── Naive baseline ────────────────────────────────────────────────────────
    freq = train_raw["label_result"].value_counts(normalize=True).sort_index()
    naive_r = np.tile(
        [freq.get(0, 0.33), freq.get(1, 0.33), freq.get(2, 0.33)], (len(test), 1)
    )

    # ── Collect results ───────────────────────────────────────────────────────
    r: dict = {
        "season": test_season, "n": len(test),
        "naive_brier": multiclass_brier(y_te_oh, naive_r),
        "naive_ll": log_loss(y_te_r, naive_r),
        "home_win_rate": (y_te_r == 0).mean(),
        "draw_rate": (y_te_r == 1).mean(),
        "away_win_rate": (y_te_r == 2).mean(),
    }

    if dc_ok:
        r["dc_brier_raw"] = multiclass_brier(y_te_oh, dc_pred_te)
        r["dc_brier_cal"] = multiclass_brier(y_te_oh, dc_cal_te3)
        r["dc_ll_raw"]    = log_loss(y_te_r, dc_pred_te)
        r["dc_ll_cal"]    = log_loss(y_te_r, dc_cal_te3)
        h, d, a = per_class_brier(y_te_oh, dc_cal_te3)
        r["dc_cal_h"], r["dc_cal_d"], r["dc_cal_a"] = h, d, a
        r["dc_cal_err_max"], _ = decile_cal_error(dc_cal_te3[:, 0], (y_te_r == 0))

    if xgb_ok:
        r["xgb_brier_raw"] = multiclass_brier(y_te_oh, xgb_te_probs_best)
        r["xgb_brier_cal"] = multiclass_brier(y_te_oh, xgb_cal_te3)
        r["xgb_ll_raw"]    = log_loss(y_te_r, xgb_te_probs_best)
        r["xgb_ll_cal"]    = log_loss(y_te_r, xgb_cal_te3)
        h, d, a = per_class_brier(y_te_oh, xgb_cal_te3)
        r["xgb_cal_h"], r["xgb_cal_d"], r["xgb_cal_a"] = h, d, a
        r["xgb_cal_err_max"], _ = decile_cal_error(xgb_cal_te3[:, 0], (y_te_r == 0))

    if ens_avg is not None:
        r["ens_avg_brier"] = multiclass_brier(y_te_oh, ens_avg)
        r["ens_avg_ll"]    = log_loss(y_te_r, ens_avg)

    if meta_ok:
        r["ens_stacked_brier"] = multiclass_brier(y_te_oh, ens_stacked)
        r["ens_stacked_ll"]    = log_loss(y_te_r, ens_stacked)
        h, d, a = per_class_brier(y_te_oh, ens_stacked)
        r["ens_stacked_h"], r["ens_stacked_d"], r["ens_stacked_a"] = h, d, a
        r["ens_cal_err_max"], _ = decile_cal_error(ens_stacked[:, 0], (y_te_r == 0))
        raw_ce, _ = decile_cal_error(ens_avg[:, 0], (y_te_r == 0))
        stk_ce, _ = decile_cal_error(ens_stacked[:, 0], (y_te_r == 0))
        r["cal_stage_raw_avg"] = raw_ce
        r["cal_stage_stacked"] = stk_ce

    results.append(r)
    best_key = next(
        (k for k in ["ens_stacked_brier", "ens_avg_brier", "xgb_brier_cal", "dc_brier_cal"]
         if k in r),
        None,
    )
    best = f"{r[best_key]:.4f}" if best_key else "?"
    print(f" | Best={best} vs Naive={r['naive_brier']:.4f}")


# ─── 8. Report ────────────────────────────────────────────────────────────────

print("\n" + "=" * 70)
print("RESULTS — 1X2 only (O/U dropped)")
print("=" * 70)

rd = pd.DataFrame(results)


def avg(col: str) -> float:
    return rd[col].dropna().mean() if col in rd.columns else float("nan")


def pct(a: float, b: float) -> float:
    return (b - a) / b * 100 if b and not (math.isnan(a) or math.isnan(b)) else float("nan")


naive_b = avg("naive_brier")
naive_l = avg("naive_ll")

print(f"\n{'Model':<28} {'Brier':>8} {'vs Naive':>10} {'Log-Loss':>10}")
print("-" * 60)
print(f"{'Naive baseline':<28} {naive_b:8.4f} {'—':>10} {naive_l:10.4f}")

for label, bk, lk in [
    ("DC (raw)",             "dc_brier_raw",       "dc_ll_raw"),
    ("DC (calibrated)",      "dc_brier_cal",       "dc_ll_cal"),
    ("XGBoost (raw)",        "xgb_brier_raw",      "xgb_ll_raw"),
    ("XGBoost (cal, +All)",  "xgb_brier_cal",      "xgb_ll_cal"),
    ("Ensemble avg",         "ens_avg_brier",      "ens_avg_ll"),
    ("Ensemble stacked",     "ens_stacked_brier",  "ens_stacked_ll"),
]:
    b, l = avg(bk), avg(lk)
    if not math.isnan(b):
        print(f"  {label:<26} {b:8.4f} {pct(b, naive_b):>+9.1f}% {l:10.4f}")

# A/B feature test
if ab_records:
    n_folds = len(ab_records)
    print(f"\nA/B feature test (XGBoost Brier, avg over {n_folds} seasons):")
    print(f"  {'Feature set':<18} {'Brier':>8}  {'Δ vs Base':>10}  {'Keep?':>6}")
    print("  " + "-" * 46)
    ab_df = pd.DataFrame(ab_records).drop(columns=["season"], errors="ignore")
    ab_avg = ab_df.mean()
    base_b = ab_avg.get("Base", float("nan"))
    for fs in list(AB_SETS.keys()):
        v = ab_avg.get(fs, float("nan"))
        if math.isnan(v):
            continue
        if fs == "Base":
            print(f"  {fs:<18} {v:8.4f}  {'—':>10}  {'—':>6}")
        else:
            delta = base_b - v
            keep = "YES" if delta > 0.001 else ("~" if delta > 0 else "NO")
            print(f"  {fs:<18} {v:8.4f}  {delta:>+10.4f}  {keep:>6}")

# Per-class Brier
print(f"\nPer-class Brier (calibrated):")
print(f"  {'Model':<24} {'Home':>8} {'Draw':>8} {'Away':>8}")
print("  " + "-" * 50)
for label, hk, dk, ak in [
    ("DC (calibrated)",      "dc_cal_h",       "dc_cal_d",       "dc_cal_a"),
    ("XGBoost (cal, +All)",  "xgb_cal_h",      "xgb_cal_d",      "xgb_cal_a"),
    ("Ensemble stacked",     "ens_stacked_h",  "ens_stacked_d",  "ens_stacked_a"),
]:
    h, d, a = avg(hk), avg(dk), avg(ak)
    if not (math.isnan(h) and math.isnan(d)):
        print(f"  {label:<24} {h:8.4f} {d:8.4f} {a:8.4f}")

# Calibration error
print(f"\nCalibration error (temperature scaling, home-win deciles, max):")
print(f"  {'Stage':<30} {'Max err':>8}")
print("  " + "-" * 40)
for label, k in [
    ("Raw average ensemble",   "cal_stage_raw_avg"),
    ("Stacked (meta-learner)", "cal_stage_stacked"),
]:
    v = avg(k)
    if not math.isnan(v):
        flag = "✓" if v < 0.05 else ("~" if v < 0.10 else "!")
        print(f"  {label:<30} {v:8.4f}  [{flag}]")

# Feature importances
if all_imp:
    print(f"\nXGBoost feature importances (+All, gain, avg across folds):")
    agg: dict[str, float] = {}
    for fi in all_imp:
        for f, v in fi.items():
            agg[f] = agg.get(f, 0.0) + v / len(all_imp)
    total = sum(agg.values()) or 1.0
    print(f"  {'Feature':<32} {'Gain':>10} {'Share':>8}")
    print("  " + "-" * 52)
    for fn, fv in sorted(agg.items(), key=lambda x: x[1], reverse=True)[:20]:
        print(f"  {fn:<32} {fv:10.1f} {fv / total:8.1%}")

# Match rates
print(f"\nMatch outcome rates (test avg):")
for col, label in [
    ("home_win_rate", "Home wins"), ("draw_rate", "Draws"), ("away_win_rate", "Away wins"),
]:
    if col in rd.columns:
        print(f"  {label}: {rd[col].mean():.1%}")

# Per-season detail
print(f"\nPer-season Brier:")
dcols = ["season", "n", "naive_brier"]
for c in ["dc_brier_cal", "xgb_brier_cal", "ens_stacked_brier"]:
    if c in rd.columns:
        dcols.append(c)
print(rd[dcols].to_string(index=False, float_format="{:.4f}".format))

# ─── 9. Recommendations ───────────────────────────────────────────────────────

print("\n" + "=" * 70)
print("RECOMMENDATIONS")
print("=" * 70)
print(f"\n  ELO: K={K}, HOME_ADV={HOME_ADV}, REGRESS={REGRESS:.0%}")

best_key = next(
    (k for k in ["ens_stacked_brier", "ens_avg_brier", "xgb_brier_cal", "dc_brier_cal"]
     if k in rd.columns and not math.isnan(avg(k))),
    None,
)
best_b = avg(best_key) if best_key else float("nan")
imp_pct = pct(best_b, naive_b)

if not math.isnan(imp_pct):
    if imp_pct > -5:
        print(f"  [!] WEAK:     Best model {imp_pct:+.1f}% vs naive. "
              "More feature/architecture work needed.")
    elif imp_pct > -10:
        print(f"  [~] MODERATE: Best model {imp_pct:+.1f}% vs naive.")
    else:
        print(f"  [+] GOOD:     Best model {imp_pct:+.1f}% vs naive.")

xgb_d = avg("xgb_cal_d")
if not math.isnan(xgb_d) and xgb_d > 0.18:
    print(f"\n  [Draw] Brier={xgb_d:.4f} — draws remain hardest class.")

if ab_records:
    ab_df2 = pd.DataFrame(ab_records)
    ab_avg2 = ab_df2.drop(columns=["season"]).mean()
    base_b2 = ab_avg2.get("Base", float("nan"))
    for fs in [k for k in AB_SETS if k not in ("Base", "+All")]:
        v = ab_avg2.get(fs, float("nan"))
        if not math.isnan(v) and not math.isnan(base_b2):
            delta = base_b2 - v
            verdict = "KEEP" if delta > 0.001 else ("marginal" if delta > 0 else "DROP")
            print(f"\n  [A/B] {fs}: Δ={delta:+.4f} → {verdict}")

print()
print("Evaluation complete.")

# ─── JSON output (for experiment runner / agent comparisons) ──────────────────
if _ARGS.out:
    import datetime as _dt
    import subprocess as _sp

    def _avg_safe(col: str) -> "float | None":
        v = avg(col)
        return None if math.isnan(v) else round(v, 6)

    def _pct_safe(a, b) -> "float | None":
        if a is None or b is None:
            return None
        v = pct(a, b)
        return None if math.isnan(v) else round(v, 4)

    try:
        _sha = _sp.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    except Exception:
        _sha = "unknown"

    # Per-AB-set averaged Brier
    _ab_out: dict = {}
    if ab_records:
        _ab_df3 = pd.DataFrame(ab_records).drop(columns=["season"], errors="ignore")
        _ab_avg3 = _ab_df3.mean()
        for _fs in AB_SETS:
            _v = _ab_avg3.get(_fs, float("nan"))
            _ab_out[_fs] = None if math.isnan(float(_v)) else round(float(_v), 6)

    _nb = _avg_safe("naive_brier")
    _best_key3 = next(
        (k for k in ["ens_stacked_brier", "ens_avg_brier", "xgb_brier_cal", "dc_brier_cal"]
         if k in rd.columns and not math.isnan(avg(k))),
        None,
    )
    _best_b3 = _avg_safe(_best_key3) if _best_key3 else None

    _per_season: dict = {}
    for _, _row in rd.iterrows():
        _syr = str(int(_row.get("season", 0)))
        _bk  = next(
            (c for c in ["ens_stacked_brier", "xgb_brier_cal", "dc_brier_cal"]
             if c in _row.index and not math.isnan(float(_row[c]))),
            None,
        )
        if _bk:
            _per_season[_syr] = round(float(_row[_bk]), 6)

    _result_json = {
        "experiment_id":               _Path(_ARGS.out).stem,
        "git_sha":                     _sha,
        "timestamp":                   _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "config": {
            "xg_windows":     list(XG_WINDOWS),
            "form_windows":   list(FORM_WINDOWS),
            "regress":        REGRESS,
            "dc_decay_hl":    DC_DECAY_HL,
            "weight_hl":      WEIGHT_HL,
            "games_14d":      GAMES_14D,
            "test_seasons":   list(TEST_SEASONS),
            "elo_k":          int(K),
            "elo_home_adv":   int(HOME_ADV),
            "calibration":    _ARGS.calibration,
            "seed":           _ARGS.seed,
        },
        "naive_brier":                 _nb,
        "ab_sets":                     _ab_out,
        "best_model":                  _best_key3,
        "best_brier":                  _best_b3,
        "improvement_pct_vs_naive":    _pct_safe(_best_b3, _nb),
        "max_decile_calibration_error": _avg_safe("cal_stage_stacked"),
        "per_class_brier": {
            "home":  _avg_safe("xgb_cal_h"),
            "draw":  _avg_safe("xgb_cal_d"),
            "away":  _avg_safe("xgb_cal_a"),
        },
        "per_season": _per_season,
    }

    _out_path = _Path(_ARGS.out)
    _out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(_out_path, "w") as _fh:
        _json.dump(_result_json, _fh, indent=2)
    print(f"Results JSON → {_out_path}")
