import pandas as pd

from scripts.build_race_deltas import append_race_delta_history


def test_append_race_delta_history_flattens_rows(tmp_path):
    out = tmp_path / "hist.parquet"
    leagues = {"epl": {"title": {"team": "Alpha", "now": 55.0, "delta": 3.0,
                                  "cause": "result", "from": "2026-07-01",
                                  "to": "2026-07-02"}}}
    added = append_race_delta_history(leagues, out)
    assert added == 1
    df = pd.read_parquet(out)
    row = df.iloc[0]
    assert row["league"] == "epl" and row["metric"] == "title"
    assert row["team"] == "Alpha" and row["delta"] == 3.0 and row["cause"] == "result"


def test_append_race_delta_history_dedups_same_day_rerun(tmp_path):
    out = tmp_path / "hist.parquet"
    leagues = {"epl": {"title": {"team": "Alpha", "now": 55.0, "delta": 3.0,
                                  "cause": "result", "from": "2026-07-01",
                                  "to": "2026-07-02"}}}
    append_race_delta_history(leagues, out)
    added_again = append_race_delta_history(leagues, out)
    assert added_again == 0
    assert len(pd.read_parquet(out)) == 1


def test_append_race_delta_history_multiple_metrics_and_leagues(tmp_path):
    out = tmp_path / "hist.parquet"
    leagues = {
        "epl": {"title": {"team": "Alpha", "now": 55.0, "delta": 3.0,
                           "cause": "result", "from": "2026-07-01", "to": "2026-07-02"},
                "releg": {"team": "Zulu", "now": 40.0, "delta": -2.0,
                          "cause": "refresh", "from": "2026-07-01", "to": "2026-07-02"}},
        "mls": {"playoff": {"team": "Beta", "now": 61.0, "delta": 1.0,
                             "cause": "model", "from": "2026-07-01", "to": "2026-07-02"}},
    }
    added = append_race_delta_history(leagues, out)
    assert added == 3
