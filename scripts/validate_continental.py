"""Walk-forward Brier-vs-naive backtest for the cross-league continental model.

For each historical continental match, resolve both teams' strengths and score the
Poisson match model's 1X2 Brier against a base-rate naive. Used to calibrate
BASE_GOALS / GOAL_SCALE / HOME_ADV_ELO so the model beats naive.
"""
from __future__ import annotations

import argparse

import numpy as np

from data_pipeline.espn_continental import continental_results
from data_pipeline import coefficients as co
from scripts.eval import cross_league as cl


def _strength_resolver():
    """Coefficient-based strength for every team (isolates match-model constants
    from ELO drift; production team_strength still uses ELO)."""
    def resolve(team):
        return co.club_strength(team)
    return resolve


def _brier(p, outcome):  # outcome: 0 home, 1 draw, 2 away
    y = np.zeros(3); y[outcome] = 1.0
    return float(np.sum((np.array(p) - y) ** 2))


def validate(comp_id: str, seasons: range) -> dict:
    df = continental_results(comp_id, seasons)
    df = df[df["is_result"]].dropna(subset=["home_goals", "away_goals"])
    resolve = _strength_resolver()
    outcomes = np.where(df["home_goals"] > df["away_goals"], 0,
                        np.where(df["home_goals"] == df["away_goals"], 1, 2))
    base = np.array([(outcomes == k).mean() for k in (0, 1, 2)])
    model_b, naive_b = [], []
    for (_, r), oc in zip(df.iterrows(), outcomes):
        sh, sa = resolve(r["home_team"]), resolve(r["away_team"])
        p = cl.match_probs(sh, sa, neutral=bool(r.get("neutral", False)))
        model_b.append(_brier(p, oc))
        naive_b.append(_brier(base, oc))
    return {"comp": comp_id, "n": len(df),
            "model_brier": round(float(np.mean(model_b)), 4),
            "naive_brier": round(float(np.mean(naive_b)), 4)}


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--comp", default="ucl")
    ap.add_argument("--from-year", type=int, default=2018)
    ap.add_argument("--to-year", type=int, default=2024)
    a = ap.parse_args()
    r = validate(a.comp, range(a.from_year, a.to_year + 1))
    print(f"[{r['comp']}] n={r['n']}  model {r['model_brier']:.4f}  "
          f"vs naive {r['naive_brier']:.4f}  "
          f"({'BEATS' if r['model_brier'] < r['naive_brier'] else 'TRAILS'} naive)")
