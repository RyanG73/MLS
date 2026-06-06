"""Tests for models/metrics.py — Brier and log-loss correctness."""

import numpy as np
import pytest
from models.metrics import (
    brier_multiclass_sum,
    brier_multiclass_half,
    brier_binary,
    per_class_brier,
    log_loss_multiclass,
)


# Tiny fixture: 2 samples, 3 classes
_PROBS = np.array([[0.7, 0.2, 0.1], [0.2, 0.3, 0.5]])
_Y_INT = np.array([0, 2])          # home win, then away win
_Y_OH  = np.array([[1, 0, 0], [0, 0, 1]])


def test_brier_sum_perfect():
    p = np.array([[1.0, 0.0, 0.0], [0.0, 0.0, 1.0]])
    assert brier_multiclass_sum(p, _Y_INT) == pytest.approx(0.0)


def test_brier_sum_worst():
    # Predict opposite class with certainty for every sample
    p = np.array([[0.0, 0.5, 0.5], [0.5, 0.5, 0.0]])
    score = brier_multiclass_sum(p, _Y_INT)
    assert score > 0.0


def test_brier_sum_fixture():
    # Manual computation for the tiny fixture
    # Sample 0: label 0, probs [0.7, 0.2, 0.1]
    #   sum sq err = (0.7-1)^2 + (0.2-0)^2 + (0.1-0)^2 = 0.09+0.04+0.01 = 0.14
    # Sample 1: label 2, probs [0.2, 0.3, 0.5]
    #   sum sq err = (0.2-0)^2 + (0.3-0)^2 + (0.5-1)^2 = 0.04+0.09+0.25 = 0.38
    # Mean = (0.14 + 0.38) / 2 = 0.26
    assert brier_multiclass_sum(_PROBS, _Y_INT) == pytest.approx(0.26)


def test_brier_half_is_sum_over_two():
    s = brier_multiclass_sum(_PROBS, _Y_INT)
    h = brier_multiclass_half(_PROBS, _Y_INT)
    assert h == pytest.approx(s / 2.0)


def test_brier_sum_accepts_onehot():
    s_int = brier_multiclass_sum(_PROBS, _Y_INT)
    s_oh  = brier_multiclass_sum(_PROBS, _Y_OH)
    assert s_int == pytest.approx(s_oh)


def test_brier_binary_perfect():
    assert brier_binary(np.ones(5), np.ones(5)) == pytest.approx(0.0)


def test_brier_binary_worst():
    assert brier_binary(np.ones(4), np.zeros(4)) == pytest.approx(1.0)


def test_per_class_brier_shape():
    h, d, a = per_class_brier(_PROBS, _Y_INT)
    assert all(isinstance(x, float) for x in (h, d, a))


def test_log_loss_perfect_clamped():
    perfect = np.array([[1.0, 0.0, 0.0], [0.0, 0.0, 1.0]])
    # sklearn clamps so this should not raise and should be near 0
    ll = log_loss_multiclass(perfect, _Y_INT)
    assert ll < 0.1


def test_brier_convention_comment():
    """Sum-form result for naive uniform predictions: should be ~0.667."""
    uniform = np.full((10, 3), 1.0 / 3.0)
    labels  = np.array([0, 1, 2, 0, 1, 2, 0, 1, 2, 0])
    score = brier_multiclass_sum(uniform, labels)
    assert score == pytest.approx(2.0 / 3.0, abs=0.01)
