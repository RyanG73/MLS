"""The ESPN goals-only source frame is slug-generic (Saudi/A-League/WSL), while
liga-mx keeps its torneo-specific frame."""
from __future__ import annotations


def test_espn_results_frame_exists_and_empty_seasons():
    from data_pipeline import espn_fixtures
    # empty season list → empty canonical frame, no network
    df = espn_fixtures.espn_results_frame("saudi-pro", seasons=[])
    assert df.empty
    for col in ("date", "season", "home_team", "away_team", "is_result"):
        assert col in df.columns


def test_espn_results_frame_loops_european_fixtures(monkeypatch):
    import pandas as pd
    from data_pipeline import espn_fixtures

    calls = []

    def fake_ef(league_id, season, use_cache=True):
        calls.append((league_id, season))
        return pd.DataFrame({
            "date": [pd.Timestamp(f"{season}-05-01")],
            "season": [season], "home_team": ["A"], "away_team": ["B"],
            "home_goals": [1.0], "away_goals": [0.0], "is_result": [True],
        })

    monkeypatch.setattr(espn_fixtures, "european_fixtures", fake_ef)
    df = espn_fixtures.espn_results_frame("saudi-pro", seasons=[2023, 2024])
    assert calls == [("saudi-pro", 2023), ("saudi-pro", 2024)]
    assert len(df) == 2
    assert df["date"].is_monotonic_increasing
