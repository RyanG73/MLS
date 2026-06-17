"""Generic group/knockout Monte-Carlo engine for continental competitions.

Driven by a declarative per-comp format spec (FORMATS). simulate() returns
league-phase standings (bucket probabilities) and knockout advance/champion odds.
"""
from __future__ import annotations

import numpy as np

from scripts.eval.cross_league import match_lambdas

# Per-comp format specs. UCL = 36-team league phase + two-leg KO + neutral final.
FORMATS: dict[str, dict] = {
    "ucl": {
        "phase": {"type": "league", "teams": 36, "matches_each": 8,
                  "auto_advance": 8, "playoff": (9, 24)},
        "ko": [{"round": "R16", "legs": 2}, {"round": "QF", "legs": 2},
               {"round": "SF", "legs": 2}, {"round": "Final", "legs": 1, "neutral": True}],
        "away_goals": False, "extra_time": True, "pens": True,
    },
}


def make_league_schedule(field, matches_each: int, seed: int = 0):
    """Build a (home_idx, away_idx, neutral) schedule: each team plays `matches_each`.

    A simple round-robin-style pairing (not the real UEFA draw — sufficient for odds).
    """
    rng = np.random.default_rng(seed)
    n = len(field)
    games = []
    for i in range(n):
        opps = [j for j in range(n) if j != i]
        rng.shuffle(opps)
        for j in opps[: matches_each // 2]:
            games.append((i, j, False))  # i home, j away
    return games


def _sim_match(sh, sa, neutral, rng):
    lam_h, lam_a = match_lambdas(sh, sa, neutral)
    return int(rng.poisson(lam_h)), int(rng.poisson(lam_a))


def simulate_league_phase(field, schedule, fmt, N: int, seed: int = 0):
    """Monte-Carlo the league phase -> standings rows with bucket probabilities."""
    n = len(field)
    strengths = np.array([t["strength"] for t in field], dtype=float)
    auto_n = fmt["phase"]["auto_advance"]
    playoff_lo, playoff_hi = fmt["phase"]["playoff"]
    rng = np.random.default_rng(seed)

    auto = np.zeros(n); playoff = np.zeros(n); elim = np.zeros(n)
    for _ in range(N):
        pts = np.zeros(n); gd = np.zeros(n)
        for hi, ai, neutral in schedule:
            hg, ag = _sim_match(strengths[hi], strengths[ai], neutral, rng)
            gd[hi] += hg - ag; gd[ai] += ag - hg
            if hg > ag: pts[hi] += 3
            elif hg == ag: pts[hi] += 1; pts[ai] += 1
            else: pts[ai] += 3
        order = np.argsort(-(pts * 1000 + gd + rng.random(n)))  # rank, tie jitter
        rank = np.empty(n, dtype=int); rank[order] = np.arange(1, n + 1)
        auto += rank <= auto_n
        playoff += (rank > auto_n) & (rank <= playoff_hi)
        elim += rank > playoff_hi

    return [
        {"team": field[i]["team"], "strength": float(strengths[i]),
         "auto_advance": float(auto[i] / N), "playoff": float(playoff[i] / N),
         "eliminated": float(elim[i] / N)}
        for i in range(n)
    ]
