"""
Python bridge that prepares input data for the R Bayesian model,
calls the R script via subprocess, and reads back the output.
Falls back gracefully if R/brms is not available.
"""

import json
import logging
import subprocess
import sys
from pathlib import Path
from typing import Optional

import pandas as pd

from config import SETTINGS

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(SETTINGS["_repo_root"])
_DATA_DIR = _REPO_ROOT / "data"
_R_SCRIPT = _REPO_ROOT / "models" / "r_bridge" / "bayesian_elo.R"
_TRAIN_INPUT = _DATA_DIR / "bayes_input_train.csv"
_PREDICT_INPUT = _DATA_DIR / "bayes_input_predict.csv"
_OUTPUT = _DATA_DIR / "bayes_output.csv"
_PARAMS = _DATA_DIR / "bayes_params.csv"
_CFG_JSON = _REPO_ROOT / "config" / "bayes_config.json"

_BAYES_CFG = SETTINGS["bayesian"]


def _write_bayes_config() -> None:
    """Write Bayesian config as JSON for the R script to read."""
    _CFG_JSON.parent.mkdir(parents=True, exist_ok=True)
    with open(_CFG_JSON, "w") as f:
        json.dump(_BAYES_CFG, f)


def prepare_train_data(train_df: pd.DataFrame) -> None:
    """Write training data CSV for the R script."""
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    required = ["match_id", "date", "season", "home_team", "away_team",
                "home_goals", "away_goals", "home_elo", "away_elo",
                "is_expansion_home", "is_expansion_away"]
    cols = [c for c in required if c in train_df.columns]
    train_df[cols].to_csv(_TRAIN_INPUT, index=False)
    logger.info("Wrote %d training rows to %s.", len(train_df), _TRAIN_INPUT)


def prepare_predict_data(predict_df: pd.DataFrame) -> None:
    """Write upcoming match data CSV for the R script to predict."""
    required = ["match_id", "home_team", "away_team", "home_elo", "away_elo"]
    cols = [c for c in required if c in predict_df.columns]
    predict_df[cols].to_csv(_PREDICT_INPUT, index=False)
    logger.info("Wrote %d predict rows to %s.", len(predict_df), _PREDICT_INPUT)


def run_r_model() -> bool:
    """
    Execute the R script. Returns True on success, False on failure.
    """
    _write_bayes_config()

    r_executable = _find_r()
    if not r_executable:
        logger.error("R executable not found. Bayesian model will be skipped.")
        return False

    cmd = [r_executable, "--vanilla", str(_R_SCRIPT), str(_REPO_ROOT)]
    logger.info("Running R Bayesian model: %s", " ".join(cmd))

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=1800,  # 30-minute timeout for MCMC
        )
        if result.stdout:
            for line in result.stdout.strip().split("\n"):
                logger.info("[R] %s", line)
        if result.returncode != 0:
            logger.error("R script failed (exit %d):\n%s", result.returncode, result.stderr[-2000:])
            return False
        return True
    except subprocess.TimeoutExpired:
        logger.error("R model timed out after 30 minutes.")
        return False
    except Exception as exc:
        logger.error("Failed to run R model: %s", exc)
        return False


def read_predictions() -> Optional[pd.DataFrame]:
    """Read the bayesian output predictions from the R script."""
    if not _OUTPUT.exists():
        logger.warning("Bayesian output file not found: %s", _OUTPUT)
        return None
    return pd.read_csv(_OUTPUT)


def read_team_params() -> Optional[pd.DataFrame]:
    """Read the posterior team attack/defense parameters."""
    if not _PARAMS.exists():
        return None
    return pd.read_csv(_PARAMS)


def run_full_pipeline(
    train_df: pd.DataFrame,
    predict_df: pd.DataFrame,
) -> Optional[pd.DataFrame]:
    """
    Convenience wrapper: prepare data → run R → return predictions.
    Returns None if R is unavailable or fails.
    """
    prepare_train_data(train_df)
    prepare_predict_data(predict_df)
    success = run_r_model()
    if not success:
        return None
    return read_predictions()


def _find_r() -> Optional[str]:
    """Find the Rscript executable on the system."""
    candidates = ["Rscript", "/usr/bin/Rscript", "/usr/local/bin/Rscript"]
    for r in candidates:
        try:
            result = subprocess.run([r, "--version"], capture_output=True, timeout=5)
            if result.returncode == 0:
                return r
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue
    return None
