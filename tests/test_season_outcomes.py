import numpy as np
import pandas as pd

from scripts.eval.season_outcomes import (
    bucket_members,
    replay_league,
    simulate_outcomes,
    summarize,
)


def test_bucket_members_top_bottom_band():
    order = np.array([3, 1, 0, 2])   # best first
    assert list(bucket_members({"top": 1}, order, 4)) == [3]
    assert list(bucket_members({"bottom": 2}, order, 4)) == [0, 2]
    assert list(bucket_members({"band": [2, 3]}, order, 4)) == [1, 0]


def test_simulate_outcomes_dominant_team_wins_title():
    # 3 teams; team 0 wins every fixture with p=0.99 → ~certain title.
    fixtures = [(0, 1), (0, 2), (1, 0), (2, 0), (1, 2), (2, 1)]
    RH = np.array([h for h, a in fixtures])
    RA = np.array([a for h, a in fixtures])
    P = np.array([[0.99, 0.005, 0.005] if 0 in (h,) else
                  ([0.005, 0.005, 0.99] if a == 0 else [0.34, 0.32, 0.34])
                  for h, a in fixtures])
    rng = np.random.default_rng(0)
    probs = simulate_outcomes(P, RH, RA, np.zeros(3), np.zeros(3),
                              [{"key": "title", "top": 1}], rng, n_sims=400)
    assert probs["title"][0] > 0.95
    assert probs["title"][1] < 0.05


def test_replay_league_scores_actual_outcomes():
    # Synthetic 4-team league, 6 seasons of double round-robin where team A
    # always beats everyone → replay must mark A as the actual champion and
    # give it a high predicted title prob by late checkpoints.
    teams = ["A", "B", "C", "D"]
    rows = []
    day = pd.Timestamp("2018-08-01")
    for season in range(2018, 2024):
        for rnd in range(2):
            for i, h in enumerate(teams):
                for a in teams[i + 1:]:
                    h_, a_ = (h, a) if rnd == 0 else (a, h)
                    hg, ag = (2, 0) if h_ == "A" else ((0, 2) if a_ == "A" else (1, 1))
                    rows.append({"date": day, "season": season,
                                 "home_team": h_, "away_team": a_,
                                 "home_goals": hg, "away_goals": ag,
                                 "is_playoff": 0})
                    day += pd.Timedelta(days=2)
        day += pd.Timedelta(days=60)
    frame = pd.DataFrame(rows)

    out = replay_league(frame, [{"key": "title", "top": 1},
                                {"key": "releg", "bottom": 1}],
                        seasons=[2022, 2023], n_sims=300,
                        checkpoints=(0.0, 0.5), preseason_sigma=0.0,
                        min_season_games=10, min_prior_games=20)
    df = pd.DataFrame(out)
    a_title = df[(df.team == "A") & (df.outcome == "title")]
    assert a_title["actual"].all()
    assert (a_title[a_title.checkpoint == 0.5]["pred"] > 0.9).all()

    s = summarize(out)
    assert s["cp0.5"]["title"]["favorite_hit_rate"] == 1.0
    assert s["cp0.5"]["title"]["brier"] < 0.05
