"""ASA canonical-frame adapter (C2: NWSL / USL Championship).

Builds the same canonical match frame as `data_pipeline.understat.canonical_frame`
from American Soccer Analysis data (via the parquet-cached `asa_cache` layer):
goals AND xG, so these leagues run the xG feature path, not the goals-only one.

Team keys are ASA display names (`team_name`), mirroring how Understat leagues
key on Understat titles — the dashboard build maps names to ESPN crests via its
FD_ESPN-style alias table.

ASA serves PLAYED games only (status FullTime); scheduled fixtures come from
ESPN (`data_pipeline.espn_fixtures`) exactly as for European preseason builds.
`knockout_game` marks playoff rows (excluded from regular-season tables by the
builder's is_playoff handling).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from data_pipeline.asa_cache import get_game_xgoals, get_games, get_teams
from data_pipeline.understat import _COLS, _coerce


def asa_canonical_frame(league: str) -> pd.DataFrame:
    """Canonical played-match frame for an ASA league ("nwsl", "uslc", ...)."""
    games = get_games(league)
    teams = get_teams(league)
    id2name = dict(zip(teams["team_id"], teams["team_name"]))

    # FullTime + real scores only: USL has occasional FullTime rows with NaN
    # scores (forfeits/data gaps) that would poison the goals-int cast.
    g = games[(games["status"] == "FullTime")
              & games["home_score"].notna() & games["away_score"].notna()].copy()
    g["date"] = pd.to_datetime(g["date_time_utc"]).dt.tz_localize(None)
    g["season"] = g["season_name"].astype(int)

    xg = get_game_xgoals(league)
    xg_map = (xg.set_index("game_id")[["home_team_xgoals", "away_team_xgoals"]]
              if not xg.empty and "home_team_xgoals" in xg.columns else None)

    out = pd.DataFrame({
        "match_id": g["game_id"],
        "date": g["date"],
        "season": g["season"],
        "home_team": g["home_team_id"].map(id2name),
        "away_team": g["away_team_id"].map(id2name),
        "home_goals": g["home_score"].astype(float),
        "away_goals": g["away_score"].astype(float),
        "home_xg": (g["game_id"].map(xg_map["home_team_xgoals"])
                    if xg_map is not None else np.nan),
        "away_xg": (g["game_id"].map(xg_map["away_team_xgoals"])
                    if xg_map is not None else np.nan),
        "is_result": True,
        "is_playoff": g.get("knockout_game", pd.Series(False, index=g.index))
                       .fillna(False).astype(int),
    })
    out["label_result"] = np.where(
        out["home_goals"] > out["away_goals"], 0,
        np.where(out["home_goals"] == out["away_goals"], 1, 2)).astype(float)
    out = out.dropna(subset=["home_team", "away_team"])
    return _coerce(out[_COLS]).sort_values("date").reset_index(drop=True)
