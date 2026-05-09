"""
Gradient boosting models for MLS match prediction.
- XGBoost multiclass for 1X2 (home win / draw / away win)
- LightGBM binary for Over/Under 2.5 goals
- Time-series cross-validation (no future leakage)
- Optuna hyperparameter tuning
- SHAP values for interpretability
"""

import logging
import pickle
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
from sklearn.model_selection import TimeSeriesSplit
from sklearn.preprocessing import LabelEncoder

from config import SETTINGS
from features.feature_builder import get_feature_columns

logger = logging.getLogger(__name__)

_GB_CFG = SETTINGS["gradient_boost"]
_CV_FOLDS = _GB_CFG["cv_folds"]
_OPTUNA_TRIALS = _GB_CFG["optuna_trials"]
_EARLY_STOP = _GB_CFG["early_stopping_rounds"]
_OU_LINE = _GB_CFG["ou_threshold"]

_MODEL_DIR = Path(SETTINGS["_repo_root"]) / "data"
_XGB_PATH = _MODEL_DIR / "xgb_model.pkl"
_LGB_PATH = _MODEL_DIR / "lgb_model.pkl"
_FEATURE_COLS_PATH = _MODEL_DIR / "feature_columns.pkl"


class GradientBoostModels:
    def __init__(self):
        self.xgb_model = None
        self.lgb_model = None
        self.feature_cols: list[str] = []
        self.fitted: bool = False

    def _prepare_xy(self, df: pd.DataFrame) -> tuple:
        self.feature_cols = get_feature_columns(df)
        # Encode conference matchup string columns
        cat_cols = [c for c in self.feature_cols if df[c].dtype == object]
        for c in cat_cols:
            df[c] = LabelEncoder().fit_transform(df[c].astype(str))

        X = df[self.feature_cols].fillna(-1).values
        y_result = df["label_result"].values.astype(int)
        y_ou = df["label_over25"].values.astype(int)
        return X, y_result, y_ou

    def _tune_xgb(self, X_tr: np.ndarray, y_tr: np.ndarray, X_val: np.ndarray, y_val: np.ndarray) -> dict:
        import optuna
        import xgboost as xgb
        optuna.logging.set_verbosity(optuna.logging.WARNING)

        def objective(trial):
            params = {
                "n_estimators": trial.suggest_int("n_estimators", 200, 1000),
                "max_depth": trial.suggest_int("max_depth", 3, 8),
                "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.2, log=True),
                "subsample": trial.suggest_float("subsample", 0.6, 1.0),
                "colsample_bytree": trial.suggest_float("colsample_bytree", 0.6, 1.0),
                "min_child_weight": trial.suggest_int("min_child_weight", 1, 10),
                "reg_alpha": trial.suggest_float("reg_alpha", 0, 1),
                "reg_lambda": trial.suggest_float("reg_lambda", 1, 5),
                "objective": "multi:softprob",
                "num_class": 3,
                "tree_method": "hist",
                "use_label_encoder": False,
                "eval_metric": "mlogloss",
                "seed": 42,
            }
            model = xgb.XGBClassifier(**params)
            model.fit(X_tr, y_tr, eval_set=[(X_val, y_val)],
                      early_stopping_rounds=_EARLY_STOP, verbose=False)
            preds = model.predict_proba(X_val)
            from sklearn.metrics import log_loss
            return log_loss(y_val, preds)

        study = optuna.create_study(direction="minimize")
        study.optimize(objective, n_trials=_OPTUNA_TRIALS, show_progress_bar=False)
        return study.best_params

    def _tune_lgb(self, X_tr: np.ndarray, y_tr: np.ndarray, X_val: np.ndarray, y_val: np.ndarray) -> dict:
        import optuna
        import lightgbm as lgb
        optuna.logging.set_verbosity(optuna.logging.WARNING)

        def objective(trial):
            params = {
                "n_estimators": trial.suggest_int("n_estimators", 200, 1000),
                "num_leaves": trial.suggest_int("num_leaves", 20, 100),
                "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.2, log=True),
                "subsample": trial.suggest_float("subsample", 0.6, 1.0),
                "colsample_bytree": trial.suggest_float("colsample_bytree", 0.6, 1.0),
                "min_child_samples": trial.suggest_int("min_child_samples", 5, 50),
                "reg_alpha": trial.suggest_float("reg_alpha", 0, 1),
                "reg_lambda": trial.suggest_float("reg_lambda", 1, 5),
                "objective": "binary",
                "metric": "binary_logloss",
                "verbose": -1,
                "seed": 42,
            }
            model = lgb.LGBMClassifier(**params)
            model.fit(X_tr, y_tr, eval_set=[(X_val, y_val)],
                      callbacks=[lgb.early_stopping(_EARLY_STOP, verbose=False)])
            preds = model.predict_proba(X_val)[:, 1]
            from sklearn.metrics import log_loss
            return log_loss(y_val, preds)

        study = optuna.create_study(direction="minimize")
        study.optimize(objective, n_trials=_OPTUNA_TRIALS, show_progress_bar=False)
        return study.best_params

    def fit(self, df: pd.DataFrame) -> "GradientBoostModels":
        import xgboost as xgb
        import lightgbm as lgb

        X, y_result, y_ou = self._prepare_xy(df)
        tscv = TimeSeriesSplit(n_splits=_CV_FOLDS)
        splits = list(tscv.split(X))
        tr_idx, val_idx = splits[-1]  # Use last fold for hyperparameter tuning

        X_tr, X_val = X[tr_idx], X[val_idx]
        y_tr_r, y_val_r = y_result[tr_idx], y_result[val_idx]
        y_tr_ou, y_val_ou = y_ou[tr_idx], y_ou[val_idx]

        logger.info("Tuning XGBoost 1X2 model (%d trials)...", _OPTUNA_TRIALS)
        xgb_params = self._tune_xgb(X_tr, y_tr_r, X_val, y_val_r)
        xgb_params.update({
            "objective": "multi:softprob",
            "num_class": 3,
            "tree_method": "hist",
            "use_label_encoder": False,
            "eval_metric": "mlogloss",
            "seed": 42,
        })
        self.xgb_model = xgb.XGBClassifier(**xgb_params)
        self.xgb_model.fit(X, y_result, verbose=False)
        logger.info("XGBoost 1X2 model fitted.")

        logger.info("Tuning LightGBM O/U model (%d trials)...", _OPTUNA_TRIALS)
        lgb_params = self._tune_lgb(X_tr, y_tr_ou, X_val, y_val_ou)
        lgb_params.update({
            "objective": "binary",
            "metric": "binary_logloss",
            "verbose": -1,
            "seed": 42,
        })
        self.lgb_model = lgb.LGBMClassifier(**lgb_params)
        self.lgb_model.fit(X, y_ou)
        logger.info("LightGBM O/U model fitted.")

        self.fitted = True
        return self

    def predict(self, features: dict) -> dict:
        """Predict from a single match feature dict."""
        if not self.fitted:
            raise RuntimeError("Models not fitted.")
        X = self._features_to_array(features)
        xgb_probs = self.xgb_model.predict_proba(X)[0]
        lgb_probs = self.lgb_model.predict_proba(X)[0]
        return {
            "prob_home": float(xgb_probs[0]),
            "prob_draw": float(xgb_probs[1]),
            "prob_away": float(xgb_probs[2]),
            "prob_over": float(lgb_probs[1]),
            "prob_under": float(lgb_probs[0]),
        }

    def predict_batch(self, df: pd.DataFrame) -> pd.DataFrame:
        """Predict for a batch DataFrame. Returns df with prediction columns added."""
        if not self.fitted:
            raise RuntimeError("Models not fitted.")
        cat_cols = [c for c in self.feature_cols if c in df.columns and df[c].dtype == object]
        for c in cat_cols:
            df[c] = LabelEncoder().fit_transform(df[c].astype(str))
        X = df[self.feature_cols].fillna(-1).values
        xgb_probs = self.xgb_model.predict_proba(X)
        lgb_probs = self.lgb_model.predict_proba(X)
        df = df.copy()
        df["prob_home"] = xgb_probs[:, 0]
        df["prob_draw"] = xgb_probs[:, 1]
        df["prob_away"] = xgb_probs[:, 2]
        df["prob_over"] = lgb_probs[:, 1]
        df["prob_under"] = lgb_probs[:, 0]
        return df

    def _features_to_array(self, features: dict) -> np.ndarray:
        from sklearn.preprocessing import LabelEncoder
        row = {}
        for c in self.feature_cols:
            val = features.get(c, -1)
            if isinstance(val, str):
                val = hash(val) % 1000
            row[c] = val if val is not None else -1
        return np.array([list(row.values())])

    def compute_shap(self, df: pd.DataFrame, max_rows: int = 500) -> pd.DataFrame:
        """Compute SHAP values for the XGBoost 1X2 model."""
        import shap
        cat_cols = [c for c in self.feature_cols if c in df.columns and df[c].dtype == object]
        for c in cat_cols:
            df[c] = LabelEncoder().fit_transform(df[c].astype(str))
        X = df[self.feature_cols].fillna(-1).values[:max_rows]
        explainer = shap.TreeExplainer(self.xgb_model)
        shap_values = explainer.shap_values(X)
        if isinstance(shap_values, list):
            # Multi-class: take home win class (0)
            shap_values = shap_values[0]
        return pd.DataFrame(shap_values, columns=self.feature_cols)

    def oof_predictions(self, df: pd.DataFrame) -> pd.DataFrame:
        """Generate out-of-fold predictions for stacking."""
        import xgboost as xgb
        import lightgbm as lgb

        X, y_result, y_ou = self._prepare_xy(df)
        tscv = TimeSeriesSplit(n_splits=_CV_FOLDS)

        oof_xgb = np.zeros((len(X), 3))
        oof_lgb = np.zeros(len(X))

        xgb_base = {
            "objective": "multi:softprob", "num_class": 3,
            "tree_method": "hist", "use_label_encoder": False,
            "eval_metric": "mlogloss", "seed": 42, "n_estimators": 300,
            "max_depth": 5, "learning_rate": 0.05,
        }
        lgb_base = {
            "objective": "binary", "metric": "binary_logloss",
            "verbose": -1, "seed": 42, "n_estimators": 300,
            "num_leaves": 31, "learning_rate": 0.05,
        }

        for tr_idx, val_idx in tscv.split(X):
            m_xgb = xgb.XGBClassifier(**xgb_base)
            m_xgb.fit(X[tr_idx], y_result[tr_idx], verbose=False)
            oof_xgb[val_idx] = m_xgb.predict_proba(X[val_idx])

            m_lgb = lgb.LGBMClassifier(**lgb_base)
            m_lgb.fit(X[tr_idx], y_ou[tr_idx])
            oof_lgb[val_idx] = m_lgb.predict_proba(X[val_idx])[:, 1]

        result = df[["match_id", "label_result", "label_over25"]].copy()
        result["xgb_prob_home"] = oof_xgb[:, 0]
        result["xgb_prob_draw"] = oof_xgb[:, 1]
        result["xgb_prob_away"] = oof_xgb[:, 2]
        result["xgb_prob_over"] = oof_lgb
        return result

    def save(self) -> None:
        _MODEL_DIR.mkdir(parents=True, exist_ok=True)
        with open(_XGB_PATH, "wb") as f:
            pickle.dump(self.xgb_model, f)
        with open(_LGB_PATH, "wb") as f:
            pickle.dump(self.lgb_model, f)
        with open(_FEATURE_COLS_PATH, "wb") as f:
            pickle.dump(self.feature_cols, f)
        logger.info("Gradient boost models saved.")

    @classmethod
    def load(cls) -> "GradientBoostModels":
        m = cls()
        with open(_XGB_PATH, "rb") as f:
            m.xgb_model = pickle.load(f)
        with open(_LGB_PATH, "rb") as f:
            m.lgb_model = pickle.load(f)
        with open(_FEATURE_COLS_PATH, "rb") as f:
            m.feature_cols = pickle.load(f)
        m.fitted = True
        return m
