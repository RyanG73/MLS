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

def test_club_prior_gap_terciles_present_when_column_attached():
    preds = _fake_preds()
    rng = np.random.default_rng(1)
    preds["club_prior_gap"] = rng.normal(0, 80, len(preds))
    out = _slice_table(preds)
    assert {"overachiever", "neutral", "fallen"} == set(out["by_club_prior_gap"])

def test_club_prior_gap_slice_absent_without_column():
    out = _slice_table(_fake_preds())
    assert "by_club_prior_gap" not in out

def test_draw_reliability_curve_present():
    out = _slice_table(_fake_preds())
    curve = out["draw_reliability"]           # list of {bin, n, p_mean, freq}
    assert all({"n", "p_mean", "freq"} <= set(b) for b in curve)

def test_underdog_calibration_slice_present():
    out = _slice_table(_fake_preds(n=500, seed=2))
    under = out["underdog_calibration"]
    assert {"by_probability", "by_side", "significant"} <= set(under)
    assert under["by_probability"]
    assert {"n", "mean_prob", "hit_rate", "binary_brier"} <= set(
        next(iter(under["by_probability"].values()))
    )

def test_market_disagreement_slice_present_when_market_columns_exist():
    preds = _fake_preds(n=500, seed=3)
    model = preds[["prob_home", "prob_draw", "prob_away"]].to_numpy()
    market = model.copy()
    market[:, 0] = np.clip(market[:, 0] - 0.08, 0.01, 0.98)
    market[:, 2] = np.clip(market[:, 2] + 0.08, 0.01, 0.98)
    market = market / market.sum(axis=1, keepdims=True)
    preds["mkt_home"] = market[:, 0]
    preds["mkt_draw"] = market[:, 1]
    preds["mkt_away"] = market[:, 2]

    out = _slice_table(preds)
    market_slice = out["market_disagreement"]

    assert market_slice["status"] == "ok"
    assert market_slice["n"] == len(preds) * 2
    assert market_slice["by_edge"]
    assert "disagreement_underdogs" in market_slice
