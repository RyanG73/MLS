"""Tests for data_pipeline.market math primitives and market_eval aggregations."""
import json
import math
import pytest
from data_pipeline.market import devig, edge_pct, clv_pp


def test_devig_sums_to_one():
    r = devig(2.10, 3.40, 3.60)
    assert abs(r["home"] + r["draw"] + r["away"] - 1.0) < 1e-9


def test_devig_home_favourite_has_highest_prob():
    r = devig(1.80, 3.50, 4.50)
    assert r["home"] > r["draw"] > r["away"]


def test_devig_known_values():
    r = devig(3.0, 3.0, 3.0)
    assert abs(r["home"] - 1 / 3) < 1e-9
    assert abs(r["draw"] - 1 / 3) < 1e-9


def test_devig_rejects_invalid_odds():
    with pytest.raises(ValueError):
        devig(0.0, 3.0, 3.0)
    with pytest.raises(ValueError):
        devig(2.0, -1.0, 3.0)
    with pytest.raises(ValueError):
        devig(0.9, 3.0, 3.0)
    with pytest.raises(ValueError):
        devig(2.0, 3.0, 0.5)
    with pytest.raises(ValueError):
        devig(2.0, 3.0, 0.0)


def test_devig_rejects_nan():
    with pytest.raises(ValueError):
        devig(float('nan'), 3.0, 3.0)
    with pytest.raises(ValueError):
        devig(2.0, float('nan'), 3.0)
    with pytest.raises(ValueError):
        devig(2.0, 3.0, float('nan'))


def test_edge_pct_positive_when_model_higher():
    assert edge_pct(0.50, 0.40) == pytest.approx(10.0)


def test_edge_pct_negative_when_model_lower():
    assert edge_pct(0.30, 0.40) == pytest.approx(-10.0)


def test_edge_pct_zero_when_equal():
    assert edge_pct(0.45, 0.45) == pytest.approx(0.0)


def test_edge_pct_rejects_nan():
    with pytest.raises(ValueError):
        edge_pct(float('nan'), 0.4)
    with pytest.raises(ValueError):
        edge_pct(0.4, float('nan'))


def test_edge_pct_rejects_infinity():
    with pytest.raises(ValueError):
        edge_pct(float('inf'), 0.4)
    with pytest.raises(ValueError):
        edge_pct(0.4, float('inf'))


def test_clv_pp_positive_when_line_moved_our_way():
    assert clv_pp(open_implied=0.40, close_implied=0.45) == pytest.approx(5.0)


def test_clv_pp_negative_when_line_moved_against():
    assert clv_pp(open_implied=0.40, close_implied=0.35) == pytest.approx(-5.0)


def test_clv_pp_zero_when_unchanged():
    assert clv_pp(0.40, 0.40) == pytest.approx(0.0)


def test_clv_pp_rejects_nan():
    with pytest.raises(ValueError):
        clv_pp(float('nan'), 0.4)
    with pytest.raises(ValueError):
        clv_pp(0.4, float('nan'))


def test_clv_pp_rejects_infinity():
    with pytest.raises(ValueError):
        clv_pp(float('inf'), 0.4)
    with pytest.raises(ValueError):
        clv_pp(0.4, float('inf'))


def test_log_closers_returns_zero_without_api_key(tmp_path, monkeypatch):
    """log_closers is a no-op when ODDS_API_KEY is missing."""
    monkeypatch.delenv("ODDS_API_KEY", raising=False)
    from data_pipeline.odds_log import log_closers
    n = log_closers(dry_run=True, closers_path=tmp_path / "closers.parquet")
    assert n == 0


# ── Aggregation tests for scripts/market_eval.py ─────────────────────────────

import numpy as np
import pandas as pd


def _synthetic_matched_df():
    """12-match synthetic frame with model probs and de-vigged market probs."""
    rng = np.random.default_rng(42)
    n = 12
    labels = rng.integers(0, 3, size=n)
    model = rng.dirichlet([2.0, 1.0, 1.0], size=n)
    market = model + rng.normal(0, 0.03, size=(n, 3))
    market = np.clip(market, 0.01, 0.98)
    market = market / market.sum(axis=1, keepdims=True)
    rows = []
    for i in range(n):
        rows.append({
            "label_result": int(labels[i]),
            "prob_home": float(model[i, 0]),
            "prob_draw": float(model[i, 1]),
            "prob_away": float(model[i, 2]),
            "mkt_home": float(market[i, 0]),
            "mkt_draw": float(market[i, 1]),
            "mkt_away": float(market[i, 2]),
            "season": 2024,
            "league": "epl",
        })
    return pd.DataFrame(rows)


def test_brier_vs_market_returns_model_and_market():
    from scripts.market_eval import brier_vs_market
    df = _synthetic_matched_df()
    result = brier_vs_market(df)
    assert "2024" in result
    assert "model" in result["2024"]
    assert "market" in result["2024"]
    assert 0.0 < result["2024"]["model"] < 2.0
    assert 0.0 < result["2024"]["market"] < 2.0
    assert result["2024"]["n"] == 12


def test_brier_vs_market_finite_only():
    from scripts.market_eval import brier_vs_market
    df = _synthetic_matched_df()
    result = brier_vs_market(df)
    for season_data in result.values():
        assert not np.isnan(season_data["model"])
        assert not np.isnan(season_data["market"])


def test_roi_by_edge_bucket_structure():
    from scripts.market_eval import roi_by_edge_bucket
    df = _synthetic_matched_df()
    outcome_map = {0: "home", 1: "draw", 2: "away"}
    df["edge"] = df.apply(
        lambda r: (
            r[f"prob_{outcome_map[r['label_result']]}"]
            - r[f"mkt_{outcome_map[r['label_result']]}"]
        ) * 100.0,
        axis=1,
    )
    result = roi_by_edge_bucket(df, thresholds=[0, 4, 8])
    assert isinstance(result, dict)
    for bucket, stats in result.items():
        assert "n" in stats
        assert "roi" in stats
        assert "win_rate" in stats


def test_roi_by_edge_bucket_empty_bucket_is_null():
    from scripts.market_eval import roi_by_edge_bucket
    df = _synthetic_matched_df()
    df["edge"] = -20.0  # all negative — no eligible rows
    result = roi_by_edge_bucket(df, thresholds=[0, 4, 8])
    assert result.get("8%+", {}).get("n", 0) == 0


def test_market_disagreement_buckets_home_away_by_default():
    from scripts.market_eval import market_disagreement_buckets
    df = _synthetic_matched_df()
    result = market_disagreement_buckets(df)

    assert result["status"] == "ok"
    assert result["n"] == len(df) * 2
    assert result["include_draw"] is False
    assert result["by_edge"]
    assert "market_underdogs" in result


def test_market_disagreement_buckets_can_include_draw():
    from scripts.market_eval import market_disagreement_buckets
    df = _synthetic_matched_df()
    result = market_disagreement_buckets(df, include_draw=True)

    assert result["status"] == "ok"
    assert result["n"] == len(df) * 3
    assert result["include_draw"] is True


def test_model_report_market_slices_loads_from_json(tmp_path):
    """model_report._load_market_slices fills from market_eval.json when present."""
    fake_eval = {
        "generated": "2026-06-27T00:00:00Z",
        "mls": {"status": "no_odds_data", "n_with_odds": 0},
        "european": {"epl": {"n_seasons_with_market": 4,
                             "brier_vs_market": {"2024": {"model": 0.59,
                                                          "market": 0.57}}}},
    }
    eval_path = tmp_path / "market_eval.json"
    eval_path.write_text(json.dumps(fake_eval))

    from scripts.model_report import _load_market_slices
    result = _load_market_slices(str(eval_path))
    assert result["mls"]["status"] == "no_odds_data"
    assert result["european"]["epl"]["n_seasons_with_market"] == 4


def test_model_report_market_slices_deferred_when_missing(tmp_path):
    """_load_market_slices returns a deferred string when no file exists."""
    from scripts.model_report import _load_market_slices
    result = _load_market_slices(str(tmp_path / "nonexistent.json"))
    assert isinstance(result, str)
    assert "deferred" in result.lower()
