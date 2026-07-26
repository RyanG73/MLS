"""Link the four confederation-relative ELO scales into one comparable ladder.

The problem
-----------
`league_bridge.fit_offsets` fits per-league offsets INSIDE a confederation, each
group anchored at its own reference league (UEFA→epl, CONMEBOL→brazil-serie-a,
Concacaf→mls, AFC→japan-j1), every anchor pinned at 0.0. Within a confederation
that is sound and validated. Across confederations it is meaningless: MLS and
EPL both sit at 0.0, which does not claim they are equal — it claims nothing at
all, because no match in the fitting data ever connected them.

`coefficients.league_offset` says so outright ("Concacaf and UEFA teams never
meet ... these values are not comparable"), and the webapp's power-rankings page
carries the same caveat to readers. As continental coverage grows that stops
being acceptable: a Club World Cup or an intercontinental play-off needs one
ladder, not four.

The fix
-------
Add ONE free parameter per confederation — a whole-scale shift — and fit it on
the only matches in the dataset where confederations actually meet:

    strength(team) = domestic_elo + league_offset(league) + C[confederation]

`league_offset` stays exactly as fitted (this never re-litigates validated
within-confederation work); `C[UEFA] = 0` pins the ladder for identifiability.

Evidence
--------
The FIFA Club World Cup, 2015-2025 — 133 completed matches, 64 of them from the
expanded 32-club 2025 edition. After resolving both clubs to a modeled domestic
league by ESPN team id, 60 are genuinely inter-confederation:

    CONMEBOL-UEFA 17 · Concacaf-UEFA 12 · AFC-UEFA 9 · AFC-CONMEBOL 7
    CONMEBOL-Concacaf 7 · AFC-Concacaf 5 · CAF-anything 3

Sixty matches for three or four parameters is thin, and CAF's three is nothing
at all. So the fit is ridge-regularised toward an explicit prior (below) rather
than left to overfit: where the data speaks it dominates, and where it does not
the estimate stays at conventional wisdom instead of chasing noise.

Usage:
    python -m scripts.eval.interconf_calibrate
    python -m scripts.eval.interconf_calibrate --lam 0.02 --json out.json
"""
from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import minimize

from data_pipeline.coefficients import league_offset
from data_pipeline.espn_continental import continental_results
from scripts.eval import league_bridge as lb
from scripts.eval.continental_resolve import league_rosters

_log = logging.getLogger(__name__)

OUT = Path("experiments/confederation_offsets.json")
ANCHOR_CONF = "UEFA"

# Prior shift per confederation, in ELO points relative to UEFA. These encode
# conventional wisdom and the historical shape of intercontinental results; the
# ridge pulls the fit toward them in proportion to how little data a
# confederation has.
#
#   CONMEBOL  -80  Brazilian and Argentine champions are competitive with mid-
#                  tier UEFA sides and occasionally beat elite ones (Flamengo
#                  over Chelsea, Botafogo over PSG in the 2025 group stage), but
#                  lose the tie more often than not.
#   Concacaf -210  Liga MX and MLS clubs are consistently second best against
#                  both UEFA and CONMEBOL opposition in this competition.
#   AFC      -210  Saudi/Japanese/Korean champions sit at roughly the Concacaf
#                  level; Al Hilal's 2025 run is the exception that the data
#                  will argue for if it is real.
#   CAF      -250  Al Ahly, Wydad, Espérance and Mazembe have historically
#                  troubled Concacaf sides and lost heavily to UEFA ones.
#   OFC      -450  Auckland City are semi-professional; included for
#                  completeness, never fitted (no modeled OFC league).
PRIOR: dict[str, float] = {
    "UEFA": 0.0, "CONMEBOL": -80.0, "Concacaf": -210.0,
    "AFC": -210.0, "CAF": -250.0, "OFC": -450.0,
}

# Which league ids belong to which confederation, taken from the registry so a
# new league is picked up without editing this file.
def _registry() -> dict[str, dict]:
    txt = Path("webapp/leagues.js").read_text(encoding="utf-8")
    return {r["id"]: r for r in json.loads(txt.split("=", 1)[1].rstrip().rstrip(";"))}


def _modeled_leagues() -> tuple[list[str], dict[str, str]]:
    """(league ids we can resolve into, {league_id: confederation})."""
    reg = _registry()
    rosters = league_rosters()
    lids = [lid for lid in rosters if lid in reg]
    return lids, {lid: reg[lid]["confederation"] for lid in lids}


def collect() -> list[tuple[lb._Match, str, str]]:
    """Inter-confederation Club World Cup matches, both clubs resolved."""
    lids, conf_of = _modeled_leagues()
    df = continental_results("club-world-cup", range(2015, 2027))
    df = df[df["is_result"].astype(bool)] if "is_result" in df else df
    out = []
    for m in lb._collect_by_id(df, lids):
        hc, ac = conf_of.get(m.home_league), conf_of.get(m.away_league)
        if not hc or not ac or hc == ac:
            continue           # same-confederation pairs carry no shift signal
        out.append((m, hc, ac))
    return out


def _pack(rows: list[tuple[lb._Match, str, str]], confs: list[str]):
    """Arrays for the objective. Base strength already includes league_offset."""
    idx = {c: i for i, c in enumerate(confs)}
    n = len(rows)
    sh = np.zeros(n); sa = np.zeros(n)
    Dh = np.zeros((n, len(confs))); Da = np.zeros((n, len(confs)))
    neutral = np.zeros(n, dtype=bool); y = np.zeros(n, dtype=int)
    for i, (m, hc, ac) in enumerate(rows):
        sh[i] = m.home_elo + league_offset(m.home_league)
        sa[i] = m.away_elo + league_offset(m.away_league)
        if hc in idx:
            Dh[i, idx[hc]] = 1.0
        if ac in idx:
            Da[i, idx[ac]] = 1.0
        neutral[i] = bool(m.neutral)
        y[i] = m.outcome
    return sh, sa, Dh, Da, neutral, y


def _nll(vec, sh, sa, Dh, Da, neutral, y, confs, lam):
    P = lb._probs_vec(sh + Dh @ vec, sa + Da @ vec, neutral, ANCHOR_CONF)
    ll = -np.log(np.clip(P[np.arange(len(y)), y], 1e-12, None)).mean()
    prior = np.array([PRIOR.get(c, 0.0) for c in confs])
    # Ridge toward the PRIOR, not toward zero: with 60 matches and a
    # three-match CAF, shrinking to zero would assert every confederation is
    # UEFA-strength, which is a worse default than conventional wisdom.
    return ll + lam * float(np.mean(((vec - prior) / 100.0) ** 2))


def fit(rows, confs: list[str], lam: float) -> dict[str, float]:
    sh, sa, Dh, Da, neutral, y = _pack(rows, confs)
    x0 = np.array([PRIOR.get(c, 0.0) for c in confs])
    res = minimize(_nll, x0, args=(sh, sa, Dh, Da, neutral, y, confs, lam),
                   method="L-BFGS-B", bounds=[(-600, 300)] * len(confs))
    return {c: float(v) for c, v in zip(confs, res.x)}


def _brier(rows, shifts: dict[str, float]) -> float:
    if not rows:
        return float("nan")
    confs = sorted(shifts)
    sh, sa, Dh, Da, neutral, y = _pack(rows, confs)
    vec = np.array([shifts[c] for c in confs])
    P = lb._probs_vec(sh + Dh @ vec, sa + Da @ vec, neutral, ANCHOR_CONF)
    Y = np.eye(3)[y]
    return float(((P - Y) ** 2).sum(axis=1).mean())


def _naive_brier(rows) -> float:
    """Base-rate predictor fitted on the same rows (the bar to clear)."""
    if not rows:
        return float("nan")
    y = np.array([m.outcome for m, _, _ in rows])
    p = np.array([(y == k).mean() for k in range(3)])
    Y = np.eye(3)[y]
    return float(((p[None, :] - Y) ** 2).sum(axis=1).mean())


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--lam", type=float, default=0.05, help="ridge toward PRIOR")
    ap.add_argument("--holdout", type=float, default=0.25)
    ap.add_argument("--splits", type=int, default=200,
                    help="random train/holdout splits to average over")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--json", default=str(OUT))
    a = ap.parse_args()

    rows = collect()
    print(f"\ninter-confederation matches usable: {len(rows)}")
    seen = {}
    for _, hc, ac in rows:
        seen[tuple(sorted((hc, ac)))] = seen.get(tuple(sorted((hc, ac))), 0) + 1
    for k, v in sorted(seen.items(), key=lambda kv: -kv[1]):
        print(f"   {k[0]:9} vs {k[1]:9} {v:3}")

    confs = sorted({c for _, hc, ac in rows for c in (hc, ac)} - {ANCHOR_CONF})
    print(f"\nfitting shifts for {confs} (anchor {ANCHOR_CONF} = 0)")

    # Repeated random splits, not one. A single 15-match holdout has enormous
    # variance — the first run of this script reported "ADOPT" off a split where
    # the fitted shifts were in fact WORSE than the prior alone. With 60 matches
    # total, only the mean over many splits says anything.
    counts = {c: sum(1 for _, hc, ac in rows if c in (hc, ac)) for c in [*confs, ANCHOR_CONF]}
    n_hold = max(6, int(len(rows) * a.holdout))
    acc = {"fitted": [], "prior_only": [], "zero": [], "naive": []}
    for s in range(a.splits):
        rng = np.random.default_rng(a.seed + s)
        order = rng.permutation(len(rows))
        hold = [rows[i] for i in order[:n_hold]]
        train = [rows[i] for i in order[n_hold:]]
        sh_s = fit(train, confs, a.lam)
        sh_s[ANCHOR_CONF] = 0.0
        acc["fitted"].append(_brier(hold, sh_s))
        acc["prior_only"].append(_brier(hold, {c: PRIOR.get(c, 0.0) for c in sh_s}))
        acc["zero"].append(_brier(hold, {c: 0.0 for c in sh_s}))
        acc["naive"].append(_naive_brier(hold))
    means = {k: float(np.mean(v)) for k, v in acc.items()}
    sems = {k: float(np.std(v) / np.sqrt(len(v))) for k, v in acc.items()}

    # Final coefficients: fit on everything once the comparison is made.
    shifts = fit(rows, confs, a.lam)
    shifts[ANCHOR_CONF] = 0.0

    print(f"\n{'confederation':14} {'prior':>8} {'fitted':>8} {'moved':>8}   n_matches")
    for c in sorted(shifts, key=lambda k: -shifts[k]):
        pr = PRIOR.get(c, 0.0)
        print(f"{c:14} {pr:8.0f} {shifts[c]:8.0f} {shifts[c]-pr:+8.0f}   {counts.get(c,0)}")

    print(f"\nheld-out Brier — mean of {a.splits} random {int(a.holdout*100)}% splits "
          f"({n_hold} matches each), lower is better")
    for k in ("fitted", "prior_only", "zero", "naive"):
        print(f"   {k:14} {means[k]:.4f} ± {sems[k]:.4f}")

    # The bar is all three baselines, INCLUDING the prior: if conventional
    # wisdom alone does as well, the 60 matches have taught us nothing and the
    # honest move is to ship the prior rather than a fit dressed up as evidence.
    beats = {k: means["fitted"] < means[k] for k in ("prior_only", "zero", "naive")}
    margin = means["prior_only"] - means["fitted"]
    if all(beats.values()) and margin > sems["fitted"]:
        verdict = "ADOPT fitted shifts"
    elif means["prior_only"] < means["zero"]:
        verdict = ("ADOPT PRIOR ONLY — the fit does not beat conventional wisdom "
                   "by more than its own noise, but both beat today's all-zero")
    else:
        verdict = "DO NOT ADOPT — no configuration beats today's behaviour"
    print(f"\n   verdict: {verdict}")
    b_fit, b_prior = means["fitted"], means["prior_only"]
    b_zero, b_naive = means["zero"], means["naive"]

    payload = {
        "shifts": shifts, "anchor": ANCHOR_CONF, "prior": PRIOR,
        "lam": a.lam, "n_matches": len(rows), "n_holdout": n_hold, "splits": a.splits,
        "holdout_brier_mean": means, "holdout_brier_sem": sems,
        "source": "FIFA Club World Cup 2015-2025 (ESPN fifa.cwc)",
        "verdict": verdict,
    }
    Path(a.json).parent.mkdir(parents=True, exist_ok=True)
    Path(a.json).write_text(json.dumps(payload, indent=2, sort_keys=True))
    print(f"   wrote {a.json}")


if __name__ == "__main__":
    main()
