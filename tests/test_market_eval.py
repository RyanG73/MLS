"""Tests for data_pipeline.market math primitives."""
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


def test_edge_pct_positive_when_model_higher():
    assert edge_pct(0.50, 0.40) == pytest.approx(10.0)


def test_edge_pct_negative_when_model_lower():
    assert edge_pct(0.30, 0.40) == pytest.approx(-10.0)


def test_edge_pct_zero_when_equal():
    assert edge_pct(0.45, 0.45) == pytest.approx(0.0)


def test_clv_pp_positive_when_line_moved_our_way():
    assert clv_pp(open_implied=0.40, close_implied=0.45) == pytest.approx(5.0)


def test_clv_pp_negative_when_line_moved_against():
    assert clv_pp(open_implied=0.40, close_implied=0.35) == pytest.approx(-5.0)


def test_clv_pp_zero_when_unchanged():
    assert clv_pp(0.40, 0.40) == pytest.approx(0.0)
