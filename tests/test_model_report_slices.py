import numpy as np
import pandas as pd
from scripts.model_report import _slice_table

def _fake_preds(n=400, seed=0):
    rng = np.random.default_rng(seed)
    p = rng.dirichlet([4, 2, 3], size=n)
    y = np.array([rng.choice(3, p=row) for row in p])
    dates = pd.date_range("2024-02-20", periods=n, freq="D")
    return pd.DataFrame({
        "prob_home": p[:, 0], "prob_draw": p[:, 1], "prob_away": p[:, 2],
        "label_result": y, "season": 2024, "date": dates,
        "home_team": "h", "away_team": "a",
    })

def test_favorite_decile_slice_present():
    out = _slice_table(_fake_preds())
    fav = out["by_favorite_prob"]
    assert len(fav) >= 3                      # deciles with enough support
    for k, m in fav.items():
        assert {"n", "brier", "fav_prob_mean", "fav_hit_rate"} <= set(m)

def test_season_phase_slice_present():
    out = _slice_table(_fake_preds())
    assert {"first_60d", "mid", "late"} <= set(out["by_season_phase"])

def test_draw_reliability_curve_present():
    out = _slice_table(_fake_preds())
    curve = out["draw_reliability"]           # list of {bin, n, p_mean, freq}
    assert all({"n", "p_mean", "freq"} <= set(b) for b in curve)
