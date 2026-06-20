"""Walk-forward Brier-vs-naive backtest for the cross-league continental model.

Uses real domestic ELO + fitted league offsets (Approach C) to resolve team
strengths, exactly as the production build does via build_continental_data._resolve_one.
For each historical continental match, resolves both teams' strengths and scores
the Poisson match model's 1X2 Brier against a base-rate naive.

Note: a continental market benchmark (e.g. closing odds) is unavailable from
the current data sources (football-data.co.uk is domestic-only); adding a market
track is a future data-acquisition item.
"""
from __future__ import annotations

import argparse

import numpy as np

from data_pipeline.espn_continental import continental_results
from scripts.build_continental_data import (
    META, _resolve_one, _league_elos,
)
from scripts.eval import cross_league as cl

# All live continental competitions.
_ALL_COMPS = ["ucl", "europa", "conference", "concacaf-champions", "leagues-cup"]


def _strength_resolver(comp_id: str):
    """Return a (resolve_fn, modeled_tracker) pair for the given comp.

    resolve_fn(team) -> float strength using real domestic ELO + league offset
    for modeled teams (via build_continental_data._resolve_one), or coefficient
    fallback for unmodeled teams. Concacaf ELO caches are built once per
    validate() call to amortise the cost across all matches in that comp.
    """
    confederation = META[comp_id]["confederation"]
    elos_caches: dict[str, dict[str, float]] | None = None
    if confederation == "Concacaf":
        elos_caches = {
            "mls": _league_elos("mls"),
            "liga-mx": _league_elos("liga-mx"),
        }

    modeled_pairs: list[bool] = []

    def resolve_pair(home_team: str, away_team: str) -> tuple[float, float, bool]:
        h = _resolve_one(home_team, comp_id, elos_caches)
        a = _resolve_one(away_team, comp_id, elos_caches)
        both_modeled = h["modeled"] and a["modeled"]
        return h["strength"], a["strength"], both_modeled

    return resolve_pair, modeled_pairs


def _brier(p, outcome):  # outcome: 0 home, 1 draw, 2 away
    y = np.zeros(3); y[outcome] = 1.0
    return float(np.sum((np.array(p) - y) ** 2))


def validate(comp_id: str, seasons: range) -> dict:
    df = continental_results(comp_id, seasons)
    df = df[df["is_result"]].dropna(subset=["home_goals", "away_goals"])
    resolve_pair, _ = _strength_resolver(comp_id)
    confederation = META[comp_id]["confederation"]
    outcomes = np.where(df["home_goals"] > df["away_goals"], 0,
                        np.where(df["home_goals"] == df["away_goals"], 1, 2))
    base = np.array([(outcomes == k).mean() for k in (0, 1, 2)])
    model_b, naive_b = [], []
    both_modeled_count = 0
    for (_, r), oc in zip(df.iterrows(), outcomes):
        sh, sa, both_modeled = resolve_pair(r["home_team"], r["away_team"])
        if both_modeled:
            both_modeled_count += 1
        p = cl.match_probs(sh, sa, neutral=bool(r.get("neutral", False)),
                           conf=confederation)
        model_b.append(_brier(p, oc))
        naive_b.append(_brier(base, oc))
    n = len(df)
    return {
        "comp": comp_id,
        "n": n,
        "modeled_pct": round(both_modeled_count / n * 100, 1) if n > 0 else 0.0,
        "model_brier": round(float(np.mean(model_b)), 4),
        "naive_brier": round(float(np.mean(naive_b)), 4),
    }


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--comp", default="ucl")
    ap.add_argument("--from-year", type=int, default=2018)
    ap.add_argument("--to-year", type=int, default=2024)
    ap.add_argument("--all", dest="all_comps", action="store_true",
                    help="run every live continental comp and print a summary table")
    a = ap.parse_args()

    if a.all_comps:
        print(f"{'comp':<24} {'n':>5}  {'modeled%':>9}  {'model':>7}  {'naive':>7}  {'result':>8}")
        print("-" * 72)
        for comp_id in _ALL_COMPS:
            r = validate(comp_id, range(a.from_year, a.to_year + 1))
            verdict = "BEATS" if r["model_brier"] < r["naive_brier"] else "TRAILS"
            print(
                f"{r['comp']:<24} {r['n']:>5}  {r['modeled_pct']:>8.1f}%  "
                f"{r['model_brier']:>7.4f}  {r['naive_brier']:>7.4f}  {verdict:>8}"
            )
    else:
        r = validate(a.comp, range(a.from_year, a.to_year + 1))
        print(f"[{r['comp']}] n={r['n']}  modeled%={r['modeled_pct']:.1f}%  "
              f"model {r['model_brier']:.4f}  "
              f"vs naive {r['naive_brier']:.4f}  "
              f"({'BEATS' if r['model_brier'] < r['naive_brier'] else 'TRAILS'} naive)")
