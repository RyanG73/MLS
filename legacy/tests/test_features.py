import pandas as pd

from features.referee_features import update_referee_stats_from_r
from features.xg_features import compute_rolling_features, compute_team_xg_history


def test_xg_rolling_features_exclude_match_on_as_of_date():
    matches = pd.DataFrame([
        {
            "match_id": "m1",
            "date": "2026-03-01",
            "status": "completed",
            "home_team": "ATL",
            "away_team": "MIA",
            "home_xg": 1.0,
            "away_xg": 0.5,
            "home_goals": 1,
            "away_goals": 0,
        },
        {
            "match_id": "m2",
            "date": "2026-03-08",
            "status": "completed",
            "home_team": "ATL",
            "away_team": "MIA",
            "home_xg": 5.0,
            "away_xg": 0.1,
            "home_goals": 5,
            "away_goals": 0,
        },
        {
            "match_id": "m3",
            "date": "2026-03-15",
            "status": "completed",
            "home_team": "ATL",
            "away_team": "MIA",
            "home_xg": 1.5,
            "away_xg": 0.4,
            "home_goals": 2,
            "away_goals": 0,
        },
        {
            "match_id": "m4",
            "date": "2026-03-22",
            "status": "completed",
            "home_team": "ATL",
            "away_team": "MIA",
            "home_xg": 9.0,
            "away_xg": 0.1,
            "home_goals": 9,
            "away_goals": 0,
        },
    ])

    history = compute_team_xg_history(matches, "ATL")
    features = compute_rolling_features(history, "2026-03-22", [3])

    assert features["xg_rolling_3"] < 5.0


def test_referee_import_fills_missing_metric_values(tmp_path, monkeypatch):
    csv_path = tmp_path / "refs.csv"
    pd.DataFrame(
        [
            {
                "referee_id": "ref_1",
                "name": "Ref One",
                "card_rate_per90": None,
                "penalty_rate_per90": None,
                "home_win_rate": None,
                "matches_officiated": 12,
            }
        ]
    ).to_csv(csv_path, index=False)

    captured = {}

    def fake_upsert(df, table, primary_keys):
        captured["df"] = df
        captured["table"] = table
        captured["primary_keys"] = primary_keys
        return len(df)

    monkeypatch.setattr("features.referee_features.db_utils.upsert_dataframe", fake_upsert)

    update_referee_stats_from_r(str(csv_path))

    row = captured["df"].iloc[0]
    assert captured["table"] == "referee_stats"
    assert captured["primary_keys"] == ["referee_id"]
    assert row["card_rate_per90"] == 3.8
    assert row["penalty_rate_per90"] == 0.22
    assert row["home_win_rate"] == 0.44
