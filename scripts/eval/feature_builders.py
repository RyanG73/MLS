"""
Rolling feature builders extracted from eval_baseline.py (F4 extraction).

All functions here are pure in the sense that they depend only on their explicit
parameters — no module-level state, no live API calls.  eval_baseline.py passes
the flags (HAS_PPDA, etc.) and lookup dicts (_xpass_by_game) that were formerly
script-level globals, making the functions unit-testable.

Functions:
  add_rolling_features  — core per-team rolling xG / form / venue / congestion
  add_h2h_draw_features — head-to-head draw rate (draw-signal, section 5o)
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import numpy as np
import pandas as pd

from data_pipeline.team_metadata import TEAM_COORDS as _TEAM_COORDS
from scripts.eval.feature_registry import (
    PYTHAG_WIN,
    haversine_km,
    pythag_expected_pts,
)


def add_rolling_features(
    df: pd.DataFrame,
    xg_windows: tuple[int, ...],
    form_windows: tuple[int, ...],
    games_14d_days: int,
    xpass_by_game: dict[str, tuple[Any, Any, Any, Any]],
    *,
    has_ppda: bool = False,
    has_poss: bool = False,
    has_sp_xg: bool = False,
) -> pd.DataFrame:
    """Walk-forward rolling features (xG, form, venue split, Pythagorean luck, congestion).

    Args:
        df:             Match frame sorted by date ascending.  Must have columns:
                        home_team, away_team, home_goals, away_goals, home_xg,
                        away_xg, date, match_id.
        xg_windows:     Rolling window sizes for xG features (e.g. (3, 5, 10, 15)).
        form_windows:   Rolling window sizes for form-points features.
        games_14d_days: Number of days defining the "congestion" window.
        xpass_by_game:  Dict mapping match_id → (ppda_h, ppda_a, poss_h, poss_a).
                        Values may be None when the stat is unavailable.
        has_ppda:       Whether PPDA stats are present in xpass_by_game.
        has_poss:       Whether possession stats are present in xpass_by_game.
        has_sp_xg:      Whether set-piece xG split columns exist in df.

    Returns:
        Copy of ``df`` with all rolling feature columns added.
    """
    _VENUE_WINDOWS = (5, 10)
    _HA_WINDOW = 20

    team_xg:       dict[str, list] = {}
    team_pts:      dict[str, list] = {}
    team_goals:    dict[str, list] = {}
    team_ppda:     dict[str, list] = {}
    team_poss:     dict[str, list] = {}
    team_dates_d:  dict[str, list] = {}
    team_home_pts: dict[str, list] = {}
    team_away_pts: dict[str, list] = {}
    team_goal_diff: dict[str, list] = {}

    res: dict[str, list] = {}
    for role in ("home", "away"):
        for w in xg_windows:
            res[f"{role}_xg_roll_{w}"] = []
            res[f"{role}_xga_roll_{w}"] = []
        for fw in form_windows:
            res[f"{role}_form_{fw}"] = []
        res[f"{role}_games_in_14d"] = []
        res[f"{role}_days_rest"] = []
        res[f"{role}_pythag_luck_{PYTHAG_WIN}"] = []
    for fw in _VENUE_WINDOWS:
        res[f"home_home_form_{fw}"] = []
        res[f"away_away_form_{fw}"] = []
    for fw in _VENUE_WINDOWS:
        res[f"home_goal_diff_roll_{fw}"] = []
        res[f"away_goal_diff_roll_{fw}"] = []
    res["home_ha_tilt"] = []
    res["away_ha_tilt"] = []
    if has_ppda:
        res["home_ppda_roll_10"] = []
        res["away_ppda_roll_10"] = []
    if has_poss:
        res["home_poss_roll_10"] = []
        res["away_poss_roll_10"] = []
    if has_sp_xg:
        res["home_xga_sp_roll_15"] = []
        res["away_xga_sp_roll_15"] = []

    for _, row in df.iterrows():
        ht, at = row["home_team"], row["away_team"]
        hg, ag = row["home_goals"], row["away_goals"]
        mid = str(row.get("match_id", ""))
        dt  = row["date"]

        h_xg = float(row["home_xg"]) if pd.notna(row.get("home_xg")) else float(hg)
        a_xg = float(row["away_xg"]) if pd.notna(row.get("away_xg")) else float(ag)
        h_xg_sp = float(row["home_xg_sp"]) if has_sp_xg and pd.notna(row.get("home_xg_sp")) else None
        a_xg_sp = float(row["away_xg_sp"]) if has_sp_xg and pd.notna(row.get("away_xg_sp")) else None

        xp = xpass_by_game.get(mid, (None, None, None, None))
        h_ppda_v, a_ppda_v, h_poss_v, a_poss_v = xp

        for team, role, my_xg, opp_xg, my_xg_sp, opp_xg_sp, my_ppda, my_poss in [
            (ht, "home", h_xg, a_xg, h_xg_sp, a_xg_sp, h_ppda_v, h_poss_v),
            (at, "away", a_xg, h_xg, a_xg_sp, h_xg_sp, a_ppda_v, a_poss_v),
        ]:
            xg_hist   = team_xg.get(team, [])
            pts_hist  = team_pts.get(team, [])
            goals_hist = team_goals.get(team, [])
            ppda_hist = team_ppda.get(team, [])
            poss_hist = team_poss.get(team, [])
            date_hist = team_dates_d.get(team, [])

            for w in xg_windows:
                seg = xg_hist[-w:]
                res[f"{role}_xg_roll_{w}"].append(
                    np.mean([x["xg"] for x in seg]) if seg else 1.3)
                res[f"{role}_xga_roll_{w}"].append(
                    np.mean([x["xga"] for x in seg]) if seg else 1.3)

            for fw in form_windows:
                seg_pts = pts_hist[-fw:]
                res[f"{role}_form_{fw}"].append(np.mean(seg_pts) if seg_pts else 1.0)

            cutoff = dt - timedelta(days=games_14d_days)
            res[f"{role}_games_in_14d"].append(sum(1 for d in date_hist if d > cutoff))

            res[f"{role}_days_rest"].append(
                min((dt - date_hist[-1]).days, 21) if date_hist else 7)

            seg_goals = goals_hist[-PYTHAG_WIN:]
            seg_pts_w = pts_hist[-PYTHAG_WIN:]
            if seg_goals:
                n       = len(seg_goals)
                gf_sum  = sum(g[0] for g in seg_goals)
                ga_sum  = sum(g[1] for g in seg_goals)
                pts_actual = sum(seg_pts_w)
                pts_pythag = pythag_expected_pts(gf_sum, ga_sum, n)
                res[f"{role}_pythag_luck_{PYTHAG_WIN}"].append(pts_actual - pts_pythag)
            else:
                res[f"{role}_pythag_luck_{PYTHAG_WIN}"].append(0.0)

            if has_ppda:
                seg_ppda = [v for v in ppda_hist[-10:] if v is not None]
                res[f"{role}_ppda_roll_10"].append(np.mean(seg_ppda) if seg_ppda else 10.0)

            if has_poss:
                seg_poss = [v for v in poss_hist[-10:] if v is not None]
                res[f"{role}_poss_roll_10"].append(np.mean(seg_poss) if seg_poss else 50.0)

            if has_sp_xg:
                seg_sp = [x["opp_xg_sp"] for x in xg_hist[-15:]
                          if x.get("opp_xg_sp") is not None]
                res[f"{role}_xga_sp_roll_15"].append(np.mean(seg_sp) if seg_sp else 0.4)

        # Venue-split form and goal-diff (read before updating to avoid leakage)
        h_home_hist  = team_home_pts.get(ht, [])
        a_away_hist  = team_away_pts.get(at, [])
        h_gdiff_hist = team_goal_diff.get(ht, [])
        a_gdiff_hist = team_goal_diff.get(at, [])
        for fw in _VENUE_WINDOWS:
            seg_h = h_home_hist[-fw:]
            res[f"home_home_form_{fw}"].append(np.mean(seg_h) if seg_h else 1.0)
            seg_a = a_away_hist[-fw:]
            res[f"away_away_form_{fw}"].append(np.mean(seg_a) if seg_a else 1.0)
            seg_hg = h_gdiff_hist[-fw:]
            res[f"home_goal_diff_roll_{fw}"].append(np.mean(seg_hg) if seg_hg else 0.0)
            seg_ag = a_gdiff_hist[-fw:]
            res[f"away_goal_diff_roll_{fw}"].append(np.mean(seg_ag) if seg_ag else 0.0)

        # Per-team home-advantage tilt (home pts-rate minus away pts-rate)
        h_away_hist = team_away_pts.get(ht, [])
        a_home_hist = team_home_pts.get(at, [])
        hh, hawy = h_home_hist[-_HA_WINDOW:], h_away_hist[-_HA_WINDOW:]
        res["home_ha_tilt"].append(float(np.mean(hh) - np.mean(hawy)) if hh and hawy else 0.0)
        ahm, aa2 = a_home_hist[-_HA_WINDOW:], a_away_hist[-_HA_WINDOW:]
        res["away_ha_tilt"].append(float(np.mean(ahm) - np.mean(aa2)) if ahm and aa2 else 0.0)

        # Update histories (after reading — walk-forward safe)
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
        team_home_pts.setdefault(ht, []).append(h_pts)
        team_away_pts.setdefault(at, []).append(a_pts)
        team_goal_diff.setdefault(ht, []).append(float(hg) - float(ag))
        team_goal_diff.setdefault(at, []).append(float(ag) - float(hg))

    out = df.copy()
    for col, vals in res.items():
        out[col] = vals

    w0 = xg_windows[0]
    out["xg_diff"]       = out[f"home_xg_roll_{w0}"] - out[f"away_xg_roll_{w0}"]
    out["form_diff"]     = out[f"home_form_{form_windows[0]}"] - out[f"away_form_{form_windows[0]}"]
    out["home_xg_sum"]   = out[f"home_xg_roll_{w0}"] + out[f"away_xg_roll_{w0}"]
    out["games14d_diff"] = out["home_games_in_14d"] - out["away_games_in_14d"]
    out["rest_advantage"] = out["home_days_rest"] - out["away_days_rest"]
    out["venue_form_diff_5"]  = out["home_home_form_5"]  - out["away_away_form_5"]
    out["venue_form_diff_10"] = out["home_home_form_10"] - out["away_away_form_10"]
    out["goal_diff_diff_5"]   = out["home_goal_diff_roll_5"]  - out["away_goal_diff_roll_5"]
    out["goal_diff_diff_10"]  = out["home_goal_diff_roll_10"] - out["away_goal_diff_roll_10"]
    out["ha_tilt_sum"]        = out["home_ha_tilt"] + out["away_ha_tilt"]
    out["travel_km"] = [
        haversine_km(_TEAM_COORDS.get(h), _TEAM_COORDS.get(a))
        for h, a in zip(out["home_team"], out["away_team"])
    ]
    out[f"pythag_luck_diff"] = (
        out[f"home_pythag_luck_{PYTHAG_WIN}"] - out[f"away_pythag_luck_{PYTHAG_WIN}"]
    )
    if has_ppda:
        out["ppda_diff"] = out["home_ppda_roll_10"] - out["away_ppda_roll_10"]
    if has_poss:
        out["poss_diff"] = out["home_poss_roll_10"] - out["away_poss_roll_10"]
    return out


def add_h2h_draw_features(df: pd.DataFrame, min_games: int = 3) -> pd.DataFrame:
    """Head-to-head draw rate and game count for each matchup (section 5o).

    Walk-forward safe: each game only uses results from prior meetings between the
    same two teams (regardless of home/away ordering).  Falls back to 0.0 when the
    pair has fewer than ``min_games`` prior meetings.

    Args:
        df:         Match frame sorted by date ascending.  Must have columns:
                    home_team, away_team, home_goals, away_goals.
        min_games:  Minimum prior matchups before h2h_draw_rate is non-zero.

    Returns:
        Copy of ``df`` with columns added:
        ``h2h_draw_rate``   — fraction of prior meetings that ended in a draw
        ``h2h_n_games``     — count of prior meetings (0 if no history)
    """
    # History: canonical pair key = frozenset({ht, at}) — ignores home/away assignment
    h2h_wins:   dict[frozenset, int] = {}   # wins by either side
    h2h_draws:  dict[frozenset, int] = {}
    h2h_total:  dict[frozenset, int] = {}

    draw_rate_col: list[float] = []
    n_games_col:   list[int]   = []

    for _, row in df.iterrows():
        ht, at = row["home_team"], row["away_team"]
        hg, ag = row["home_goals"], row["away_goals"]
        key = frozenset({ht, at})

        n   = h2h_total.get(key, 0)
        nd  = h2h_draws.get(key, 0)

        if n >= min_games:
            draw_rate_col.append(nd / n)
        else:
            draw_rate_col.append(0.0)
        n_games_col.append(n)

        # Update (after reading — leakage-safe)
        h2h_total[key]  = n + 1
        h2h_draws[key]  = nd + (1 if hg == ag else 0)

    out = df.copy()
    out["h2h_draw_rate"] = draw_rate_col
    out["h2h_n_games"]   = n_games_col
    return out
