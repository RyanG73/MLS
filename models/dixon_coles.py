"""
[LEGACY — not the canonical model] DEPRECATED (F1, 2026-06-07): the canonical
DC lives in models/research_model.py (production) and scripts/eval/dixon_coles.py
(research harness). This wrapper is retained for legacy component predictions in
daily_update.py only; removal deferred until that path is migrated + validated on
the Pi. See docs/CURRENT_STATE.md.

Dixon-Coles Poisson model for MLS match outcome prediction.

Key features:
- Per-team attack (α) and defense (β) parameters
- Global home advantage (γ) and baseline scoring rate (μ)
- Dixon-Coles low-score correction (ρ) for 0-0, 1-0, 0-1, 1-1
- Exponential time-decay weights on training matches
- MLE via scipy.optimize.minimize (L-BFGS-B)
- Outputs: full score matrix → P(H), P(D), P(A), P(Over 2.5), P(Under 2.5)
"""

import logging
import math
import pickle
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.stats import poisson

from config import SETTINGS

logger = logging.getLogger(__name__)

_DC_CFG = SETTINGS["dixon_coles"]
_MAX_GOALS = _DC_CFG["max_goals"]
_DECAY_HL = _DC_CFG["time_decay_half_life_days"]
_USE_RHO = _DC_CFG["rho_correction"]
_OU_LINE = _DC_CFG["ou_threshold"]
_LAMBDA = math.log(2) / _DECAY_HL

_MODEL_PATH = Path(SETTINGS["_repo_root"]) / "data" / "dixon_coles_model.pkl"


def _decay_weight(days_ago: float) -> float:
    return math.exp(-_LAMBDA * days_ago)


def _tau(hg: int, ag: int, lam_h: float, mu_a: float, rho: float) -> float:
    """Dixon-Coles correction factor for low-scoring matches."""
    if hg == 0 and ag == 0:
        return 1 - lam_h * mu_a * rho
    elif hg == 1 and ag == 0:
        return 1 + mu_a * rho
    elif hg == 0 and ag == 1:
        return 1 + lam_h * rho
    elif hg == 1 and ag == 1:
        return 1 - rho
    return 1.0


def _neg_log_likelihood(params: np.ndarray, matches: list[dict], teams: list[str]) -> float:
    """Negative log-likelihood objective for MLE fitting."""
    n_teams = len(teams)
    # params layout: [alpha_0..n, beta_0..n, log_home_adv, log_baseline, rho]
    alphas = params[:n_teams]
    betas = params[n_teams:2 * n_teams]
    home_adv = math.exp(params[2 * n_teams])
    baseline = math.exp(params[2 * n_teams + 1])
    rho = params[2 * n_teams + 2] if _USE_RHO else 0.0

    team_idx = {t: i for i, t in enumerate(teams)}
    total_ll = 0.0

    for m in matches:
        h_idx = team_idx.get(m["home_team"])
        a_idx = team_idx.get(m["away_team"])
        if h_idx is None or a_idx is None:
            continue

        lam_h = baseline * math.exp(alphas[h_idx] - betas[a_idx] + math.log(home_adv))
        lam_a = baseline * math.exp(alphas[a_idx] - betas[h_idx])

        hg, ag = int(m["home_goals"]), int(m["away_goals"])
        weight = m.get("weight", 1.0)

        ll = (
            poisson.logpmf(hg, lam_h)
            + poisson.logpmf(ag, lam_a)
            + math.log(max(_tau(hg, ag, lam_h, lam_a, rho), 1e-10))
        )
        total_ll += weight * ll

    return -total_ll


class DixonColesModel:
    def __init__(self):
        self.teams: list[str] = []
        self.alphas: np.ndarray = np.array([])
        self.betas: np.ndarray = np.array([])
        self.home_adv: float = 1.3
        self.baseline: float = 1.3
        self.rho: float = -0.1
        self.fitted: bool = False

    def fit(self, df: pd.DataFrame) -> "DixonColesModel":
        """
        Fit the model on historical match data.
        df must have: home_team, away_team, home_goals, away_goals, date columns.
        """
        df = df.dropna(subset=["home_goals", "away_goals"]).copy()
        df["date"] = pd.to_datetime(df["date"])
        max_date = df["date"].max()

        self.teams = sorted(set(df["home_team"].tolist() + df["away_team"].tolist()))
        n = len(self.teams)

        matches = []
        for _, row in df.iterrows():
            days_ago = (max_date - row["date"]).days
            matches.append({
                "home_team": row["home_team"],
                "away_team": row["away_team"],
                "home_goals": int(row["home_goals"]),
                "away_goals": int(row["away_goals"]),
                "weight": _decay_weight(days_ago),
            })

        # Initial parameters: zero attack/defense, home_adv=1.3, baseline=1.3, rho=0
        x0 = np.zeros(2 * n + 3)
        x0[2 * n] = math.log(1.3)   # home_adv
        x0[2 * n + 1] = math.log(1.3)  # baseline
        x0[2 * n + 2] = -0.1  # rho

        # Constraint: sum(alpha) = 0 (identifiability)
        constraints = [{"type": "eq", "fun": lambda p: p[:n].sum()}]

        result = minimize(
            _neg_log_likelihood,
            x0,
            args=(matches, self.teams),
            method="L-BFGS-B",
            options={"maxiter": 500, "ftol": 1e-10},
        )

        if not result.success:
            logger.warning("Dixon-Coles optimization did not fully converge: %s", result.message)

        self.alphas = result.x[:n]
        self.betas = result.x[n:2 * n]
        self.home_adv = math.exp(result.x[2 * n])
        self.baseline = math.exp(result.x[2 * n + 1])
        self.rho = result.x[2 * n + 2] if _USE_RHO else 0.0
        self.fitted = True

        logger.info("Dixon-Coles fitted on %d matches. LL=%.2f", len(matches), -result.fun)
        return self

    def predict_score_matrix(
        self, home_team: str, away_team: str
    ) -> np.ndarray:
        """
        Return [MAX_GOALS+1 x MAX_GOALS+1] score probability matrix.
        Entry [i,j] = P(home_goals=i, away_goals=j).
        """
        if not self.fitted:
            raise RuntimeError("Model not fitted.")

        team_idx = {t: i for i, t in enumerate(self.teams)}

        h_idx = team_idx.get(home_team)
        a_idx = team_idx.get(away_team)

        if h_idx is None or a_idx is None:
            # Unknown team: use league-average parameters
            lam_h = self.baseline * self.home_adv
            lam_a = self.baseline
        else:
            lam_h = self.baseline * math.exp(
                self.alphas[h_idx] - self.betas[a_idx] + math.log(self.home_adv)
            )
            lam_a = self.baseline * math.exp(
                self.alphas[a_idx] - self.betas[h_idx]
            )

        matrix = np.zeros((_MAX_GOALS + 1, _MAX_GOALS + 1))
        for hg in range(_MAX_GOALS + 1):
            for ag in range(_MAX_GOALS + 1):
                p = poisson.pmf(hg, lam_h) * poisson.pmf(ag, lam_a)
                if _USE_RHO:
                    p *= _tau(hg, ag, lam_h, lam_a, self.rho)
                matrix[hg, ag] = max(p, 0.0)

        matrix /= matrix.sum()
        return matrix

    def predict(self, home_team: str, away_team: str, home_strength_adj: float = 0.0, away_strength_adj: float = 0.0) -> dict:
        """
        Predict match outcome probabilities with optional strength adjustments.
        Adjustments are fractional (e.g., +0.1 = home team 10% stronger).
        """
        matrix = self.predict_score_matrix(home_team, away_team)

        # Apply strength adjustments by scaling lambda estimates
        if home_strength_adj != 0.0 or away_strength_adj != 0.0:
            team_idx = {t: i for i, t in enumerate(self.teams)}
            h_idx = team_idx.get(home_team)
            a_idx = team_idx.get(away_team)
            if h_idx is not None and a_idx is not None:
                lam_h = self.baseline * math.exp(
                    self.alphas[h_idx] - self.betas[a_idx] + math.log(self.home_adv)
                ) * (1 + home_strength_adj)
                lam_a = self.baseline * math.exp(
                    self.alphas[a_idx] - self.betas[h_idx]
                ) * (1 + away_strength_adj)
                matrix = np.zeros((_MAX_GOALS + 1, _MAX_GOALS + 1))
                for hg in range(_MAX_GOALS + 1):
                    for ag in range(_MAX_GOALS + 1):
                        p = poisson.pmf(hg, lam_h) * poisson.pmf(ag, lam_a)
                        if _USE_RHO:
                            p *= _tau(hg, ag, lam_h, lam_a, self.rho)
                        matrix[hg, ag] = max(p, 0.0)
                matrix /= matrix.sum()

        prob_home = float(np.sum(np.tril(matrix, -1)))
        prob_draw = float(np.sum(np.diag(matrix)))
        prob_away = float(np.sum(np.triu(matrix, 1)))

        prob_over = 0.0
        prob_under = 0.0
        for hg in range(_MAX_GOALS + 1):
            for ag in range(_MAX_GOALS + 1):
                if hg + ag > _OU_LINE:
                    prob_over += matrix[hg, ag]
                else:
                    prob_under += matrix[hg, ag]

        # Top 5 most likely scorelines
        flat = [(matrix[hg, ag], hg, ag) for hg in range(_MAX_GOALS + 1) for ag in range(_MAX_GOALS + 1)]
        top5 = sorted(flat, reverse=True)[:5]

        return {
            "prob_home": prob_home,
            "prob_draw": prob_draw,
            "prob_away": prob_away,
            "prob_over": prob_over,
            "prob_under": prob_under,
            "score_matrix": matrix,
            "top_scorelines": [(hg, ag, p) for p, hg, ag in top5],
        }

    def save(self, path: Optional[Path] = None) -> None:
        p = path or _MODEL_PATH
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "wb") as f:
            pickle.dump(self, f)
        logger.info("Dixon-Coles model saved to %s.", p)

    @classmethod
    def load(cls, path: Optional[Path] = None) -> "DixonColesModel":
        p = path or _MODEL_PATH
        if not p.exists():
            raise FileNotFoundError(f"No saved model at {p}")
        with open(p, "rb") as f:
            return pickle.load(f)
