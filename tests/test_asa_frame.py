import pandas as pd

import data_pipeline.asa_frame as asa_frame


def test_asa_frame_uses_nwsl_matchday_not_utc_date(monkeypatch):
    games = pd.DataFrame(
        [
            {
                "game_id": "nwsl-friday-night",
                "date_time_utc": "2026-07-25 00:00:00 UTC",
                "home_score": 1,
                "away_score": 0,
                "home_team_id": "orlando",
                "away_team_id": "chicago",
                "season_name": "2026",
                "knockout_game": False,
                "status": "FullTime",
            }
        ]
    )
    teams = pd.DataFrame(
        [
            {"team_id": "orlando", "team_name": "Orlando Pride"},
            {"team_id": "chicago", "team_name": "Chicago Stars FC"},
        ]
    )
    xgoals = pd.DataFrame(
        [
            {
                "game_id": "nwsl-friday-night",
                "home_team_xgoals": 1.4,
                "away_team_xgoals": 0.6,
            }
        ]
    )
    monkeypatch.setattr(asa_frame, "get_games", lambda league: games)
    monkeypatch.setattr(asa_frame, "get_teams", lambda league: teams)
    monkeypatch.setattr(asa_frame, "get_game_xgoals", lambda league: xgoals)

    frame = asa_frame.asa_canonical_frame("nwsl")

    assert frame.iloc[0]["date"] == pd.Timestamp("2026-07-24 20:00:00")
    assert frame.iloc[0]["season"] == 2026
