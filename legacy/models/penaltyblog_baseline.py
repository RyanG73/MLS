"""Optional penaltyblog Dixon-Coles benchmark model."""

from __future__ import annotations

import logging
import math
import pickle
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from config import SETTINGS

logger = logging.getLogger(__name__)

_MODEL_PATH = Path(SETTINGS["_repo_root"]) / "data" / "penaltyblog_dc_model.pkl"
_DECAY_HL = SETTINGS["dixon_coles"]["time_decay_half_life_days"]
_XI = math.log(2) / _DECAY_HL


class PenaltyBlogDixonColesModel:
    """Thin wrapper around penaltyblog's Dixon-Coles goal model."""

    def __init__(self):
        self.model = None
        self.fitted = False

    @staticmethod
    def available() -> bool:
        try:
            import penaltyblog  # noqa: F401
            return True
        except Exception:
            return False

    def fit(self, matches_df: pd.DataFrame) -> "PenaltyBlogDixonColesModel":
        import penaltyblog as pb

        df = matches_df.dropna(subset=["home_goals", "away_goals"]).copy()
        df["date"] = pd.to_datetime(df["date"])
        df = df.sort_values("date")
        if df.empty:
            raise ValueError("No completed matches available for penaltyblog fit.")

        model_cls = (
            getattr(pb.models, "DixonColesGoalsModel", None)
            or getattr(pb.models, "DixonColesGoalModel", None)
        )
        if model_cls is None:
            raise RuntimeError("penaltyblog Dixon-Coles model class not found.")

        home_goals = df["home_goals"].astype(int).to_list()
        away_goals = df["away_goals"].astype(int).to_list()
        home_teams = df["home_team"].astype(str).to_list()
        away_teams = df["away_team"].astype(str).to_list()

        try:
            weights = pb.models.dixon_coles_weights(df["date"].to_list(), xi=_XI)
            weights = np.array(weights, dtype=float, copy=True).tolist()
        except Exception:
            weights = None

        if weights is None:
            self.model = model_cls(home_goals, away_goals, home_teams, away_teams)
        else:
            self.model = model_cls(home_goals, away_goals, home_teams, away_teams, weights)

        self.model.fit()
        self.fitted = True
        logger.info("penaltyblog Dixon-Coles fitted on %d matches.", len(df))
        return self

    def predict(self, home_team: str, away_team: str) -> dict:
        if not self.fitted or self.model is None:
            raise RuntimeError("penaltyblog model not fitted.")

        pred = self.model.predict(home_team, away_team)
        hda = getattr(pred, "home_draw_away")
        under, _, over = pred.totals(SETTINGS["dixon_coles"]["ou_threshold"])
        return {
            "prob_home": float(hda[0]),
            "prob_draw": float(hda[1]),
            "prob_away": float(hda[2]),
            "prob_over": float(over),
            "prob_under": float(under),
        }

    def save(self, path: Optional[Path] = None) -> None:
        p = path or _MODEL_PATH
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "wb") as f:
            pickle.dump(self, f)

    @classmethod
    def load(cls, path: Optional[Path] = None) -> "PenaltyBlogDixonColesModel":
        p = path or _MODEL_PATH
        with open(p, "rb") as f:
            return pickle.load(f)
