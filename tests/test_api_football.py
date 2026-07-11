"""API-Football adapter — env-keyed, parses fixtures into the canonical frame. No network."""
from __future__ import annotations

import pytest


def _sample_payload():
    return {"response": [
        {  # finished match
            "fixture": {"id": 101, "date": "2025-04-05T23:00:00+00:00",
                        "status": {"short": "FT"}},
            "league": {"season": 2025},
            "teams": {"home": {"name": "Forge FC"}, "away": {"name": "Cavalry FC"}},
            "goals": {"home": 2, "away": 1},
        },
        {  # not-started match
            "fixture": {"id": 102, "date": "2026-07-16T23:00:00+00:00",
                        "status": {"short": "NS"}},
            "league": {"season": 2026},
            "teams": {"home": {"name": "Pacific FC"}, "away": {"name": "Forge FC"}},
            "goals": {"home": None, "away": None},
        },
    ]}


def test_missing_key_raises(monkeypatch):
    monkeypatch.delenv("API_FOOTBALL_KEY", raising=False)
    from data_pipeline import api_football
    monkeypatch.setattr(api_football, "_load_dotenv", lambda: None)  # ignore any real .env
    with pytest.raises(RuntimeError, match="API_FOOTBALL_KEY"):
        api_football._require_key()


def test_parse_canonical_schema():
    from data_pipeline import api_football
    from data_pipeline.understat import _COLS
    df = api_football._parse_fixtures(_sample_payload())
    assert list(df.columns) == _COLS
    assert len(df) == 2


def test_parse_result_row():
    from data_pipeline import api_football
    df = api_football._parse_fixtures(_sample_payload())
    fin = df[df["is_result"]]
    assert len(fin) == 1
    row = fin.iloc[0]
    assert row["home_team"] == "Forge FC" and row["away_team"] == "Cavalry FC"
    assert row["home_goals"] == 2.0 and row["away_goals"] == 1.0
    assert row["label_result"] == 0.0        # home win
    assert row["season"] == 2025


def test_parse_upcoming_row_has_nan_goals():
    from data_pipeline import api_football
    df = api_football._parse_fixtures(_sample_payload())
    upc = df[~df["is_result"]]
    assert len(upc) == 1
    assert upc["home_goals"].isna().all() and upc["away_goals"].isna().all()


def test_results_and_upcoming_split(monkeypatch):
    from data_pipeline import api_football
    monkeypatch.setattr(api_football, "_fetch_league",
                        lambda af_id, seasons: api_football._parse_fixtures(_sample_payload()))
    monkeypatch.setitem(api_football.LEAGUE, "canadian-pl", (468, [2025, 2026]))
    up = api_football.upcoming_fixtures("canadian-pl")
    assert (~up["is_result"]).all() and len(up) == 1
