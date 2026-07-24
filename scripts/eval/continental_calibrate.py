"""Staged calibration of a confederation's cross-league match model.

`league_bridge.fit_offsets` fits per-league ELO offsets while HOLDING the match
model's goal constants fixed. That is fine for UEFA and Concacaf, whose
constants were swept by hand years apart from the offsets. It is not enough for
a confederation being calibrated from scratch: the offsets and the constants
trade off against each other (a wider goal_scale flattens the effect of any
given offset), so picking one with the other frozen at a guess bakes the guess in.

This script runs the two together, in the order that keeps each stage's search
cheap, and validates the result on data no stage was fitted on:

  Stage 0  Collect cross-league matches, then split off a FINAL holdout (20%)
           that no stage below ever sees.
  Stage 1  Ridge sweep. Choose lambda by mean held-out Brier across 10 seeds
           on the remaining 80% (each seed re-splits it 70/30 internally).
  Stage 2  Constants grid (base_goals x goal_scale x home_adv_elo), refitting
           offsets at every grid point with the Stage-1 lambda.
  Stage 3  Refit offsets at the chosen constants, then score the untouched
           Stage-0 holdout against three baselines:
             - prior offsets (what the code does today: 0.0 for a new confederation)
             - a naive home/draw/away base-rate predictor
             - the fitted model
           A confederation is only recommended for adoption if it beats BOTH.

Usage:
    python -m scripts.eval.continental_calibrate --conf CONMEBOL
    python -m scripts.eval.continental_calibrate --conf AFC --json out.json
"""
from __future__ import annotations

import argparse
import itertools
import json
import logging

import numpy as np

from scripts.eval import league_bridge as lb
from scripts.eval.cross_league import _CONF_CONST

_log = logging.getLogger(__name__)

_GROUPS = {
    "CONMEBOL": (lb._CONMEBOL_LEAGUES, lb._CONMEBOL_ANCHOR),
    "AFC": (lb._AFC_LEAGUES, lb._AFC_ANCHOR),
    "UEFA": (lb._UEFA_LEAGUES, lb._UEFA_ANCHOR),
    "Concacaf": (lb._CONCACAF_LEAGUES, lb._CONCACAF_ANCHOR),
}

_LAMBDAS = [3e-3, 1e-3, 3e-4, 1e-4, 3e-5, 1e-5, 3e-6, 0.0]
_BASE_GOALS = [1.05, 1.15, 1.25, 1.35]
_GOAL_SCALES = [2000.0, 2500.0, 3000.0, 3500.0]
_HOME_ADVS = [60.0, 80.0, 100.0]

_HOLDOUT_FRAC = 0.20
_ROBUSTNESS_SEEDS = 10


def _naive_brier(matches) -> float:
    """Base-rate baseline: predict this confederation's overall H/D/A split.

    Fitted on the matches it scores, which makes it the STRONGEST form of the
    naive baseline (it cannot be beaten by luck in the split) — deliberately so.
    """
    if not matches:
        return float("nan")
    outcomes = np.array([m.outcome for m in matches])
    rates = np.array([(outcomes == k).mean() for k in range(3)])
    actuals = np.zeros((len(outcomes), 3))
    actuals[np.arange(len(outcomes)), outcomes] = 1.0
    return float(((rates[None, :] - actuals) ** 2).sum(axis=1).mean())


def _set_consts(conf: str, base_goals: float, goal_scale: float, home_adv: float):
    _CONF_CONST[conf] = {"base_goals": base_goals, "goal_scale": goal_scale,
                         "home_adv_elo": home_adv}


def calibrate(conf: str, seed: int = 42, quick: bool = False) -> dict:
    leagues, anchor = _GROUPS[conf]
    original = dict(_CONF_CONST.get(conf, _CONF_CONST["UEFA"]))

    # ── Stage 0: collect + carve off the final holdout ───────────────────────
    matches = lb._collect_matches(conf)
    print(f"\n{'='*66}\n{conf}: {len(matches)} cross-league matches  (anchor={anchor})\n{'='*66}")
    if len(matches) < 50:
        print("  TOO FEW MATCHES — refusing to calibrate")
        return {"conf": conf, "adopt": False, "reason": "insufficient matches"}

    rng = np.random.default_rng(seed)
    perm = rng.permutation(len(matches))
    n_hold = int(_HOLDOUT_FRAC * len(matches))
    holdout = [matches[i] for i in perm[:n_hold]]
    devset = [matches[i] for i in perm[n_hold:]]
    print(f"Stage 0: dev={len(devset)}  final-holdout={len(holdout)} (never fitted or selected on)")

    def mean_dev_brier(lam, ridge_by_count=False):
        vals = []
        for s in range(_ROBUSTNESS_SEEDS):
            _, _, _, bf = lb._fit_group(devset, leagues, anchor, lam=lam,
                                        seed=seed + s * 100, conf=conf,
                                        ridge_by_count=ridge_by_count)
            vals.append(bf)
        return float(np.mean(vals))

    # ── Stage 1: ridge sweep ─────────────────────────────────────────────────
    print(f"\nStage 1 — ridge sweep ({'constant' if True else 'count'} weighting)")
    lam_rows = []
    for lam in _LAMBDAS:
        b = mean_dev_brier(lam)
        f, _, _, _ = lb._fit_group(devset, leagues, anchor, lam=lam, seed=seed,
                                   conf=conf, ridge_by_count=False)
        spread = max(f.values()) - min(f.values())
        worst = max(abs(v) for v in f.values())
        lam_rows.append((lam, b, spread, worst))
        print(f"   lam={lam:<8.1e} dev_brier={b:.4f}  spread={spread:7.1f}  max|off|={worst:7.1f}")
    # Reject grid points whose offsets are not physically credible: a league
    # more than 1200 ELO from the anchor is not a calibration, it is an
    # unidentified parameter running away (india-isl hit -2417 off 4 matches).
    sane = [r for r in lam_rows if r[3] <= 1200.0] or lam_rows
    best_lam = min(sane, key=lambda r: r[1])[0]
    print(f"   → chose lambda={best_lam:.1e}")

    # ── Stage 2: constants grid ──────────────────────────────────────────────
    grid = list(itertools.product(_BASE_GOALS, _GOAL_SCALES, _HOME_ADVS))
    if quick:
        grid = [g for g in grid if g[2] == 80.0]
    print(f"\nStage 2 — constants grid ({len(grid)} points), offsets refit at each")
    results = []
    for bg, gs, ha in grid:
        _set_consts(conf, bg, gs, ha)
        _, _, _, bf = lb._fit_group(devset, leagues, anchor, lam=best_lam,
                                    seed=seed, conf=conf, ridge_by_count=False)
        results.append((bf, bg, gs, ha))
    results.sort()
    for bf, bg, gs, ha in results[:5]:
        print(f"   dev_brier={bf:.4f}  base_goals={bg}  goal_scale={gs:.0f}  home_adv={ha:.0f}")
    _, bg, gs, ha = results[0]
    print(f"   → chose base_goals={bg} goal_scale={gs:.0f} home_adv_elo={ha:.0f}")

    # ── Stage 3: refit + score the untouched holdout ─────────────────────────
    _set_consts(conf, bg, gs, ha)
    fitted, priors, _, _ = lb._fit_group(devset, leagues, anchor, lam=best_lam,
                                         seed=seed, conf=conf, ridge_by_count=False)
    b_prior = lb._brier_score(holdout, priors, conf=conf)
    b_fit = lb._brier_score(holdout, fitted, conf=conf)
    b_naive = _naive_brier(holdout)

    print(f"\nStage 3 — FINAL holdout (n={len(holdout)}, untouched by stages 1-2)")
    print(f"   prior offsets : {b_prior:.4f}")
    print(f"   naive base-rate: {b_naive:.4f}")
    print(f"   fitted         : {b_fit:.4f}   ({b_fit-b_prior:+.4f} vs prior, "
          f"{b_fit-b_naive:+.4f} vs naive)")

    beats_prior = b_fit < b_prior
    beats_naive = b_fit < b_naive
    adopt = beats_prior and beats_naive
    print(f"\n   beats prior: {beats_prior}   beats naive: {beats_naive}"
          f"   → {'ADOPT' if adopt else 'DO NOT ADOPT'}")

    print(f"\n   Fitted offsets ({conf}, anchor {anchor} = 0):")
    for lid, v in sorted(fitted.items(), key=lambda x: -x[1]):
        print(f"      {lid:24} {v:+8.1f}")

    if not adopt:
        _CONF_CONST[conf] = original
    return {
        "conf": conf, "adopt": adopt, "lambda": best_lam,
        "constants": {"base_goals": bg, "goal_scale": gs, "home_adv_elo": ha},
        "offsets": fitted,
        "holdout": {"n": len(holdout), "prior": b_prior, "naive": b_naive, "fitted": b_fit},
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.ERROR, format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--conf", default="CONMEBOL", choices=list(_GROUPS))
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--quick", action="store_true", help="smaller constants grid")
    ap.add_argument("--json", default=None, help="write the result dict here")
    a = ap.parse_args()
    out = calibrate(a.conf, seed=a.seed, quick=a.quick)
    if a.json:
        with open(a.json, "w") as fh:
            json.dump(out, fh, indent=2, sort_keys=True)
        print(f"\nwrote {a.json}")
