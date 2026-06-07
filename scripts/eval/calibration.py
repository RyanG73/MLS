"""
Probability calibration + calibration-error metrics — extracted from
eval_baseline.py (F4).

The harness reads the calibration method from --calibration; here it is an
explicit `method` parameter so the functions are pure and unit-testable.
Behavior-preserving extraction — verified by `eval_baseline.py --smoke-test`.

Methods:
  temperature        single-T scaling (canonical default; fit on blend output)
  platt              per-class logistic on scalar confidence
  isotonic           per-class isotonic regression
  beta               beta calibration (falls back to Platt if betacal absent)
  temp_then_isotonic two-stage: temperature then isotonic on the blend
  temp_then_platt    two-stage: temperature then Platt on the blend
"""

import numpy as np
import pandas as pd
from sklearn.metrics import log_loss
from scipy.optimize import minimize_scalar

# Canonical Brier delegates to the single authoritative implementation.
from models.metrics import (
    brier_multiclass_sum as _brier_sum,
    per_class_brier as _per_class_brier,
)


def _temp_scale(raw_cal, y_cal, raw_target):
    """Fit temperature T on (raw_cal, y_cal); apply to raw_target. Returns probs."""
    def _nll(T: float) -> float:
        log_p = np.log(np.clip(raw_cal, 1e-9, 1.0)) / max(T, 0.1)
        log_p -= log_p.max(axis=1, keepdims=True)
        exp_p = np.exp(log_p)
        probs = exp_p / exp_p.sum(axis=1, keepdims=True)
        return float(log_loss(y_cal, probs))
    T = minimize_scalar(_nll, bounds=(0.3, 5.0), method="bounded").x
    log_p = np.log(np.clip(raw_target, 1e-9, 1.0)) / T
    log_p -= log_p.max(axis=1, keepdims=True)
    exp_p = np.exp(log_p)
    return exp_p / exp_p.sum(axis=1, keepdims=True)


def calibrate_multiclass(raw_cal: np.ndarray, y_cal: np.ndarray,
                         raw_test: np.ndarray, method: str = "temperature") -> np.ndarray:
    """Calibrate multiclass probabilities by the named method.

    For two-stage methods (temp_then_isotonic, temp_then_platt) this performs
    only the first-stage temperature scaling; the second pass on the stacked
    ensemble output is handled by calibrate_stacked_second_pass.
    """
    if method in ("temperature", "temp_then_isotonic", "temp_then_platt"):
        return _temp_scale(raw_cal, y_cal, raw_test)

    elif method == "platt":
        from sklearn.linear_model import LogisticRegression as _PlattLR
        out = np.zeros_like(raw_test)
        for c in range(3):
            platt = _PlattLR(C=1.0, max_iter=300, solver="lbfgs")
            platt.fit(raw_cal[:, c].reshape(-1, 1), (y_cal == c).astype(int))
            out[:, c] = platt.predict_proba(raw_test[:, c].reshape(-1, 1))[:, 1]
        return out / out.sum(axis=1, keepdims=True).clip(1e-9, None)

    elif method == "isotonic":
        from sklearn.isotonic import IsotonicRegression as _IR
        out = np.zeros_like(raw_test)
        for c in range(3):
            ir = _IR(out_of_bounds="clip")
            ir.fit(raw_cal[:, c], (y_cal == c).astype(float))
            out[:, c] = ir.predict(raw_test[:, c])
        return out / out.sum(axis=1, keepdims=True).clip(1e-9, None)

    elif method == "beta":
        try:
            from betacal import BetaCalibration as _BC
            out = np.zeros_like(raw_test)
            for c in range(3):
                bc = _BC(parameters="abm")
                bc.fit(raw_cal[:, c], (y_cal == c).astype(int))
                out[:, c] = bc.predict(raw_test[:, c])
            return out / out.sum(axis=1, keepdims=True).clip(1e-9, None)
        except ImportError:
            print("    [warn] betacal not installed — falling back to Platt scaling")
            from sklearn.linear_model import LogisticRegression as _PlattLR2
            out = np.zeros_like(raw_test)
            for c in range(3):
                platt = _PlattLR2(C=1.0, max_iter=300, solver="lbfgs")
                platt.fit(raw_cal[:, c].reshape(-1, 1), (y_cal == c).astype(int))
                out[:, c] = platt.predict_proba(raw_test[:, c].reshape(-1, 1))[:, 1]
            return out / out.sum(axis=1, keepdims=True).clip(1e-9, None)

    else:
        raise ValueError(f"Unknown calibration method: {method!r}")


def calibrate_stacked_second_pass(
    stacked_cal: np.ndarray, y_cal: np.ndarray, stacked_te: np.ndarray,
    method: str = "temperature",
) -> np.ndarray:
    """Apply calibration to the final blend output (second pass).

    For the default "temperature" method this IS the primary calibration —
    temperature is fit on the blend output, not on XGB alone (fixes the cal_err
    root cause: a blend of two calibrated distributions is not itself calibrated).
    """
    if method in ("temperature", "temp_then_isotonic", "temp_then_platt"):
        cal = _temp_scale(stacked_cal, y_cal, stacked_te)
        if method == "temperature":
            return cal
        stacked_te = cal  # temperature-scaled output feeds the second pass

    if method == "temp_then_isotonic":
        from sklearn.isotonic import IsotonicRegression as _IR2
        stacked_cal_t = _temp_scale(stacked_cal, y_cal, stacked_cal)
        out = np.zeros_like(stacked_te)
        for c in range(3):
            ir = _IR2(out_of_bounds="clip")
            ir.fit(stacked_cal_t[:, c], (y_cal == c).astype(float))
            out[:, c] = ir.predict(stacked_te[:, c])
        return out / out.sum(axis=1, keepdims=True).clip(1e-9, None)

    elif method == "temp_then_platt":
        from sklearn.linear_model import LogisticRegression as _PlattLR3
        stacked_cal_t2 = _temp_scale(stacked_cal, y_cal, stacked_cal)
        out = np.zeros_like(stacked_te)
        for c in range(3):
            platt = _PlattLR3(C=1.0, max_iter=300, solver="lbfgs")
            platt.fit(stacked_cal_t2[:, c].reshape(-1, 1), (y_cal == c).astype(int))
            out[:, c] = platt.predict_proba(stacked_te[:, c].reshape(-1, 1))[:, 1]
        return out / out.sum(axis=1, keepdims=True).clip(1e-9, None)

    return stacked_te  # fallback: unchanged


def decile_cal_error(probs: np.ndarray, actuals: np.ndarray) -> tuple:
    """Max and mean absolute calibration error across probability deciles."""
    try:
        dec = pd.qcut(probs, 10, duplicates="drop")
        cal = (pd.DataFrame({"p": probs, "a": actuals.astype(float), "d": dec})
               .groupby("d", observed=True)
               .agg(mp=("p", "mean"), ma=("a", "mean")))
        errs = (cal["mp"] - cal["ma"]).abs()
        return float(errs.max()), float(errs.mean())
    except Exception:
        return float("nan"), float("nan")


def multiclass_brier(y_oh: np.ndarray, probs: np.ndarray) -> float:
    """Sum-form multiclass Brier (canonical — delegates to models/metrics.py)."""
    return _brier_sum(probs, y_oh)


def per_class_brier(y_oh: np.ndarray, probs: np.ndarray) -> tuple:
    """Per-class (home/draw/away) Brier — delegates to models/metrics.py."""
    return _per_class_brier(probs, y_oh)
