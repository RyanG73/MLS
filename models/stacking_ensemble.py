"""
Stacking ensemble meta-learner.

Level 0: Dixon-Coles, XGBoost/LightGBM, Bayesian model probabilities
Level 1: Isotonic-calibrated logistic regression trained on OOF predictions

Time-series cross-validation is used to generate OOF predictions,
ensuring no future data leakage in the stacking training.
"""

import logging
import os
import pickle
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import TimeSeriesSplit
from sklearn.preprocessing import LabelEncoder

from config import SETTINGS
from data_pipeline import db_utils

logger = logging.getLogger(__name__)

_ENS_CFG = SETTINGS["ensemble"]
_CV_FOLDS = _ENS_CFG["cv_folds"]
_MODEL_PATH = Path(SETTINGS["_repo_root"]) / "data" / "ensemble_model.pkl"
_VERSIONS_DIR = Path(SETTINGS["_repo_root"]) / "data" / "model_versions"


def current_model_version() -> str:
    """Generate a version stamp for the active set of models (YYYYMMDD)."""
    return datetime.now(timezone.utc).strftime("%Y%m%d")


def snapshot_model_version(ensemble, dc_model=None, gb_models=None) -> str:
    """Save snapshot of all models under data/model_versions/<YYYYMMDD>/."""
    version = current_model_version()
    target = _VERSIONS_DIR / version
    target.mkdir(parents=True, exist_ok=True)
    try:
        with open(target / "ensemble.pkl", "wb") as f:
            pickle.dump(ensemble, f)
        if dc_model is not None:
            with open(target / "dixon_coles.pkl", "wb") as f:
                pickle.dump(dc_model, f)
        if gb_models is not None:
            with open(target / "gradient_boost.pkl", "wb") as f:
                pickle.dump(gb_models, f)
        logger.info("Snapshotted model version %s.", version)
    except Exception as exc:
        logger.warning("Failed to snapshot model version %s: %s", version, exc)
    return version

# Level 0 model output columns — with and without Bayesian
_L0_RESULT_COLS_3 = [
    "dc_prob_home",   "dc_prob_draw",   "dc_prob_away",
    "xgb_prob_home",  "xgb_prob_draw",  "xgb_prob_away",
    "bayes_prob_home","bayes_prob_draw", "bayes_prob_away",
]
_L0_RESULT_COLS_2 = [
    "dc_prob_home",  "dc_prob_draw",  "dc_prob_away",
    "xgb_prob_home", "xgb_prob_draw", "xgb_prob_away",
]
_L0_OU_COLS_3 = ["dc_prob_over", "xgb_prob_over", "bayes_prob_over"]
_L0_OU_COLS_2 = ["dc_prob_over", "xgb_prob_over"]

# Keep legacy alias so external code importing _L0_RESULT_COLS still works
_L0_RESULT_COLS = _L0_RESULT_COLS_3
_L0_OU_COLS = _L0_OU_COLS_3


class StackingEnsemble:
    def __init__(self):
        self.meta_result: Optional[CalibratedClassifierCV] = None  # 1X2
        self.meta_ou: Optional[CalibratedClassifierCV] = None      # O/U
        self.fitted: bool = False
        self._with_bayesian: bool = True  # determined at fit() time; persisted in pickle
        self._result_cols = _L0_RESULT_COLS_3
        self._ou_cols = _L0_OU_COLS_3

    def fit(self, oof_df: pd.DataFrame) -> "StackingEnsemble":
        """
        Train stacking meta-learners on OOF level-0 predictions.
        oof_df must contain: match_id, label_result, label_over25, + DC and XGB L0 cols.
        If Bayesian columns are absent, fits a 2-model ensemble (DC + XGB only).
        """
        df = oof_df.copy()

        # Detect whether Bayesian columns are present
        self._with_bayesian = "bayes_prob_home" in df.columns and df["bayes_prob_home"].notna().any()
        if self._with_bayesian:
            self._result_cols = _L0_RESULT_COLS_3
            self._ou_cols = _L0_OU_COLS_3
            df = self._fill_missing_bayes(df)
        else:
            self._result_cols = _L0_RESULT_COLS_2
            self._ou_cols = _L0_OU_COLS_2
            logger.info("Fitting 2-model ensemble (DC + XGB); no Bayesian columns in OOF data.")

        df = df.dropna(subset=self._result_cols + ["label_result"])

        X_result = df[self._result_cols].values
        y_result = df["label_result"].values.astype(int)

        X_ou = df[[c for c in self._ou_cols if c in df.columns]].values
        y_ou = df["label_over25"].values.astype(int)

        base_lr = LogisticRegression(
            multi_class="multinomial",
            solver="lbfgs",
            max_iter=500,
            C=1.0,
            random_state=42,
        )
        self.meta_result = CalibratedClassifierCV(base_lr, method="isotonic", cv=3)
        self.meta_result.fit(X_result, y_result)

        base_lr_ou = LogisticRegression(solver="lbfgs", max_iter=500, C=1.0, random_state=42)
        self.meta_ou = CalibratedClassifierCV(base_lr_ou, method="isotonic", cv=3)
        self.meta_ou.fit(X_ou, y_ou)

        self.fitted = True
        logger.info("Stacking ensemble fitted on %d OOF rows.", len(df))
        return self

    def predict(
        self,
        dc_probs: dict,
        xgb_probs: dict,
        bayes_probs: Optional[dict] = None,
        home_strength_adj: float = 0.0,
        away_strength_adj: float = 0.0,
    ) -> dict:
        """
        Generate ensemble prediction from individual model outputs.
        All input dicts must have keys: prob_home, prob_draw, prob_away, prob_over.
        """
        if not self.fitted:
            raise RuntimeError("Ensemble not fitted.")

        # Apply manual strength adjustments by nudging DC probs
        if home_strength_adj != 0.0 or away_strength_adj != 0.0:
            dc_probs = _adjust_probs(dc_probs, home_strength_adj, away_strength_adj)

        if self._with_bayesian:
            bayes_probs = bayes_probs or dc_probs
            X_result = np.array([[
                dc_probs["prob_home"],    dc_probs["prob_draw"],    dc_probs["prob_away"],
                xgb_probs["prob_home"],   xgb_probs["prob_draw"],   xgb_probs["prob_away"],
                bayes_probs["prob_home"], bayes_probs["prob_draw"], bayes_probs["prob_away"],
            ]])
            X_ou = np.array([[
                dc_probs["prob_over"],
                xgb_probs.get("prob_over", dc_probs["prob_over"]),
                bayes_probs.get("prob_over", dc_probs["prob_over"]),
            ]])
        else:
            X_result = np.array([[
                dc_probs["prob_home"],  dc_probs["prob_draw"],  dc_probs["prob_away"],
                xgb_probs["prob_home"], xgb_probs["prob_draw"], xgb_probs["prob_away"],
            ]])
            X_ou = np.array([[
                dc_probs["prob_over"],
                xgb_probs.get("prob_over", dc_probs["prob_over"]),
            ]])

        result_probs = self.meta_result.predict_proba(X_result)[0]
        ou_probs = self.meta_ou.predict_proba(X_ou)[0]

        out = {
            "prob_home":  float(result_probs[0]),
            "prob_draw":  float(result_probs[1]),
            "prob_away":  float(result_probs[2]),
            "prob_over":  float(ou_probs[1]),
            "prob_under": float(ou_probs[0]),
            "component_dc":  dc_probs,
            "component_xgb": xgb_probs,
        }
        if self._with_bayesian:
            out["component_bayes"] = bayes_probs
        return out

    def store_predictions(
        self,
        match_id: str,
        model_name: str,
        probs: dict,
        features_hash: Optional[str] = None,
    ) -> None:
        """Write a prediction row to the predictions table."""
        pred_id = hashlib.md5(f"{match_id}_{model_name}".encode()).hexdigest()[:20]
        version = current_model_version()
        db_utils.execute(
            """
            INSERT INTO predictions
                (prediction_id, match_id, model, model_version, prob_home, prob_draw, prob_away,
                 prob_over, prob_under, features_hash, claude_rationale)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (prediction_id) DO UPDATE SET
                prob_home = EXCLUDED.prob_home,
                prob_draw = EXCLUDED.prob_draw,
                prob_away = EXCLUDED.prob_away,
                prob_over = EXCLUDED.prob_over,
                prob_under = EXCLUDED.prob_under,
                predicted_at = NOW(),
                features_hash = EXCLUDED.features_hash,
                claude_rationale = EXCLUDED.claude_rationale
            """,
            [
                pred_id, match_id, model_name, version,
                probs.get("prob_home"), probs.get("prob_draw"), probs.get("prob_away"),
                probs.get("prob_over"), probs.get("prob_under"),
                features_hash, probs.get("claude_rationale"),
            ],
        )

    def _fill_missing_bayes(self, df: pd.DataFrame) -> pd.DataFrame:
        """Fill missing Bayesian OOF predictions with Dixon-Coles as fallback."""
        for dc_col, bayes_col in [
            ("dc_prob_home", "bayes_prob_home"),
            ("dc_prob_draw", "bayes_prob_draw"),
            ("dc_prob_away", "bayes_prob_away"),
            ("dc_prob_over", "bayes_prob_over"),
        ]:
            if bayes_col not in df.columns:
                df[bayes_col] = df.get(dc_col, 0.33)
            else:
                df[bayes_col] = df[bayes_col].fillna(df.get(dc_col, 0.33))
        return df

    def compute_brier_score(self, predictions_df: pd.DataFrame, results_df: pd.DataFrame) -> dict:
        """
        Compute Brier scores for ensemble predictions against actual outcomes.
        Returns dict of {model: brier_score} for each component and ensemble.
        """
        merged = predictions_df.merge(results_df[["match_id", "home_goals", "away_goals"]], on="match_id")
        merged["actual_home"] = (merged["home_goals"] > merged["away_goals"]).astype(int)
        merged["actual_draw"] = (merged["home_goals"] == merged["away_goals"]).astype(int)
        merged["actual_away"] = (merged["home_goals"] < merged["away_goals"]).astype(int)

        scores = {}
        for model in merged["model"].unique():
            sub = merged[merged["model"] == model]
            brier = (
                (sub["prob_home"] - sub["actual_home"]) ** 2 +
                (sub["prob_draw"] - sub["actual_draw"]) ** 2 +
                (sub["prob_away"] - sub["actual_away"]) ** 2
            ).mean() / 2  # Divide by 2 for multi-class Brier
            scores[model] = float(brier)

        return scores

    def save(self) -> None:
        _MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(_MODEL_PATH, "wb") as f:
            pickle.dump(self, f)
        logger.info("Ensemble model saved to %s.", _MODEL_PATH)

    @classmethod
    def load(cls) -> "StackingEnsemble":
        if not _MODEL_PATH.exists():
            raise FileNotFoundError(f"No saved ensemble at {_MODEL_PATH}")
        with open(_MODEL_PATH, "rb") as f:
            return pickle.load(f)


def _adjust_probs(probs: dict, home_adj: float, away_adj: float) -> dict:
    """
    Nudge raw probabilities based on manual strength adjustments.
    Uses a simple logit-scale shift proportional to adjustment magnitude.
    """
    import math
    ph = probs["prob_home"]
    pd_ = probs["prob_draw"]
    pa = probs["prob_away"]

    def logit(p):
        p = max(min(p, 0.999), 0.001)
        return math.log(p / (1 - p))

    lh = logit(ph) + home_adj * 2 - away_adj
    la = logit(pa) + away_adj * 2 - home_adj

    def sigmoid(x):
        return 1 / (1 + math.exp(-x))

    ph_new = sigmoid(lh)
    pa_new = sigmoid(la)
    pd_new = max(0.001, 1.0 - ph_new - pa_new)
    total = ph_new + pd_new + pa_new
    return {
        "prob_home": ph_new / total,
        "prob_draw": pd_new / total,
        "prob_away": pa_new / total,
        "prob_over": probs.get("prob_over", 0.5),
        "prob_under": probs.get("prob_under", 0.5),
    }
