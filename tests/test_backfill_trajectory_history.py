import numpy as np
import pandas as pd

from scripts.backfill_trajectory_history import _checkpoints, _generic_sim


def _schedule(future_home_goals: int) -> pd.DataFrame:
    return pd.DataFrame([
        {"date": pd.Timestamp("2026-01-01"), "home_team": "A", "away_team": "B",
         "home_goals": 1, "away_goals": 0, "is_result": True},
        {"date": pd.Timestamp("2026-01-08"), "home_team": "B", "away_team": "A",
         "home_goals": future_home_goals, "away_goals": 0, "is_result": True},
    ])


def test_checkpoints_stop_before_the_live_archive_boundary():
    schedule = _schedule(9)
    points = _checkpoints(schedule, pd.Timestamp("2026-01-02"), step_games=1)
    assert points == [pd.Timestamp("2025-12-31"), pd.Timestamp("2026-01-01")]


def test_future_score_is_not_visible_to_point_in_time_simulation():
    """The later fixture is in the recovered schedule, but its score is ignored."""
    first, second = _schedule(2), _schedule(9)
    played_first = first[first["date"] <= pd.Timestamp("2026-01-01")]
    played_second = second[second["date"] <= pd.Timestamp("2026-01-01")]
    pm = np.zeros((2, 2, 3))
    pm[0, 1] = [0.5, 0.25, 0.25]
    pm[1, 0] = [0.4, 0.3, 0.3]
    buckets = [{"key": "title", "top": 1}]

    a = _generic_sim(first, played_first, ["A", "B"], buckets, pm,
                     n_sims=250, sigma=0, seed=7, lid="test")
    b = _generic_sim(second, played_second, ["A", "B"], buckets, pm,
                     n_sims=250, sigma=0, seed=7, lid="test")

    np.testing.assert_allclose(a[0], b[0])
    np.testing.assert_allclose(a[1]["title"], b[1]["title"])
