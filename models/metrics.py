"""
Standardized metric functions for the MLS prediction model.

Canonical convention (sum-form, no /2):
    brier_multiclass_sum  -- all research history, CLAUDE.md, eval_baseline.py
    Range: 0.0 (perfect) to 2.0 (worst). For a 3-class uniform naive
    baseline this gives ~0.667; the research-harness naive is ~0.6406.

Half-form (/2) is provided for display in the Streamlit dashboard where
"~0.25" is the familiar random-baseline reference. Do not use half-form
for model comparisons or experiment logging.
"""

import numpy as np
from sklearn.metrics import log_loss as _sklearn_log_loss


def brier_multiclass_sum(probs: np.ndarray, y: np.ndarray) -> float:
    """Multiclass Brier score — SUM form (canonical for this project).

    probs : (n, 3) predicted probabilities
    y     : (n,) integer class labels  OR  (n, 3) one-hot
    Returns mean of sum-of-squared-errors per sample.
    """
    y_oh = _to_onehot(y)
    return float(np.mean(np.sum((probs - y_oh) ** 2, axis=1)))


def brier_multiclass_half(probs: np.ndarray, y: np.ndarray) -> float:
    """Multiclass Brier score — HALF form (= sum / 2).

    Used only for display in the Streamlit performance page where
    the familiar ~0.25 random-baseline reference applies.
    Do NOT use for model comparison or experiment logging.
    """
    return brier_multiclass_sum(probs, y) / 2.0


def brier_binary(probs: np.ndarray, y: np.ndarray) -> float:
    """Binary Brier score: mean((p - y)^2)."""
    return float(np.mean((np.asarray(probs) - np.asarray(y).astype(float)) ** 2))


def per_class_brier(probs: np.ndarray, y: np.ndarray) -> tuple[float, float, float]:
    """Per-class binary Brier (home, draw, away)."""
    y_oh = _to_onehot(y)
    return tuple(
        float(np.mean((probs[:, c] - y_oh[:, c]) ** 2)) for c in range(3)
    )


def log_loss_multiclass(probs: np.ndarray, y: np.ndarray) -> float:
    """Multiclass log-loss (sklearn convention, always 3 classes)."""
    return float(_sklearn_log_loss(y, probs, labels=[0, 1, 2]))


def _to_onehot(y: np.ndarray) -> np.ndarray:
    y = np.asarray(y)
    if y.ndim == 2:
        return y.astype(float)
    return np.eye(3)[y.astype(int)]
