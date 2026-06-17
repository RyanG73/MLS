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
    # Europa League — same 2024-25 format as UCL (36-team league phase, 8 games each).
    "europa": {
        "phase": {"type": "league", "teams": 36, "matches_each": 8,
                  "auto_advance": 8, "playoff": (9, 24)},
        "ko": [{"round": "R16", "legs": 2}, {"round": "QF", "legs": 2},
               {"round": "SF", "legs": 2}, {"round": "Final", "legs": 1, "neutral": True}],
        "away_goals": False, "extra_time": True, "pens": True,
    },
    # Conference League — same structure but each side plays only 6 league-phase games.
    "conference": {
        "phase": {"type": "league", "teams": 36, "matches_each": 6,
                  "auto_advance": 8, "playoff": (9, 24)},
        "ko": [{"round": "R16", "legs": 2}, {"round": "QF", "legs": 2},
               {"round": "SF", "legs": 2}, {"round": "Final", "legs": 1, "neutral": True}],
        "away_goals": False, "extra_time": True, "pens": True,
    },
}


def make_league_schedule(field, matches_each: int, seed: int = 0):
    """Build a (home_idx, away_idx, neutral) schedule where every team plays exactly
    `matches_each` games — half home, half away — against distinct opponents.

    Teams are placed on a randomized circle (seed-controlled); each team hosts the
    next `matches_each//2` teams clockwise and visits the previous `matches_each//2`.
    This is a balanced approximation of the real draw (not the actual UEFA pairing),
    which is what the standings odds need. Requires matches_each < len(field).
    """
    rng = np.random.default_rng(seed)
    n = len(field)
    half = matches_each // 2
    perm = rng.permutation(n)
    games = []
    for pos in range(n):
        i = int(perm[pos])
        for d in range(1, half + 1):
            j = int(perm[(pos + d) % n])
            games.append((i, j, False))  # i home vs j; j thereby gets an away game
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
        # 1000 >> max plausible GD over the phase, so points dominate, GD breaks ties.
        order = np.argsort(-(pts * 1000 + gd + rng.random(n)))
        rank = np.empty(n, dtype=int); rank[order] = np.arange(1, n + 1)
        auto_mask = rank <= auto_n
        playoff_mask = (rank >= playoff_lo) & (rank <= playoff_hi)
        auto += auto_mask
        playoff += playoff_mask
        elim += ~(auto_mask | playoff_mask)  # exactly one bucket per team per sim

    return [
        {"team": field[i]["team"], "strength": float(strengths[i]),
         "auto_advance": float(auto[i] / N), "playoff": float(playoff[i] / N),
         "eliminated": float(elim[i] / N)}
        for i in range(n)
    ]


def sim_single_leg(sh, sa, rng, neutral=False):
    """One match -> winner index (0=home/sh, 1=away/sa); ties broken by penalties."""
    hg, ag = _sim_match(sh, sa, neutral, rng)
    if hg > ag: return 0
    if ag > hg: return 1
    return _pens(sh, sa, rng)


def sim_two_leg(sa_strength, sb_strength, rng, fmt):
    """Two-leg tie (A home leg 1, B home leg 2) -> winner index (0=A, 1=B)."""
    a_h, b_a = _sim_match(sa_strength, sb_strength, False, rng)   # leg 1: A home
    b_h, a_a = _sim_match(sb_strength, sa_strength, False, rng)   # leg 2: B home
    agg_a, agg_b = a_h + a_a, b_a + b_h
    if agg_a > agg_b: return 0
    if agg_b > agg_a: return 1
    if fmt.get("away_goals"):
        if a_a > b_a: return 0
        if b_a > a_a: return 1
    return _pens(sa_strength, sb_strength, rng)  # ET folded into the pens coin-flip


def _pens(sh, sa, rng):
    """Penalty shootout -> winner index; slight edge to the stronger side."""
    p_home = 1.0 / (1.0 + 10.0 ** (-(sh - sa) / 2000.0))  # near 0.5, mild tilt
    return 0 if rng.random() < p_home else 1


def simulate(comp_id: str, field, N: int, seed: int = 0):
    """Full Monte-Carlo: league phase (if any) + knockout -> standings + odds.

    Returns {"standings": [...], "field": [...with odds...]}.
    `field` entries need keys: team, strength (+ any passthrough display keys).
    """
    fmt = FORMATS[comp_id]
    n = len(field)
    rng = np.random.default_rng(seed)
    rounds = [r["round"] for r in fmt["ko"]]
    reach = {r: np.zeros(n) for r in rounds}
    win = np.zeros(n)

    schedule = make_league_schedule(field, fmt["phase"]["matches_each"], seed)
    standings = simulate_league_phase(field, schedule, fmt, N, seed)
    strengths = np.array([t["strength"] for t in field], dtype=float)
    auto_n = fmt["phase"]["auto_advance"]
    playoff_hi = fmt["phase"]["playoff"][1]

    for _ in range(N):
        # League phase (re-simulated so the bracket field varies run to run)
        pts = np.zeros(n); gd = np.zeros(n)
        for hi, ai, neutral in schedule:
            hg, ag = _sim_match(strengths[hi], strengths[ai], neutral, rng)
            gd[hi] += hg - ag; gd[ai] += ag - hg
            if hg > ag: pts[hi] += 3
            elif hg == ag: pts[hi] += 1; pts[ai] += 1
            else: pts[ai] += 3
        order = list(np.argsort(-(pts * 1000 + gd + rng.random(n))))
        bracket = order[:auto_n] + order[auto_n:playoff_hi]  # top-24 enter KO
        # Pad/truncate to a power of two for a clean single-elimination bracket.
        size = 1 << (len(bracket).bit_length() - 1)
        alive = bracket[:size]
        for r in fmt["ko"]:
            for t in alive:
                reach[r["round"]][t] += 1
            nxt = []
            if r.get("legs", 1) == 2:
                for k in range(0, len(alive), 2):
                    a, b = alive[k], alive[k + 1]
                    w = sim_two_leg(strengths[a], strengths[b], rng, fmt)
                    nxt.append(a if w == 0 else b)
            else:  # single-leg final
                a, b = alive[0], alive[1]
                w = sim_single_leg(strengths[a], strengths[b], rng,
                                   neutral=r.get("neutral", False))
                nxt.append(a if w == 0 else b)
            alive = nxt
        win[alive[0]] += 1

    by_team = {s["team"]: s for s in standings}
    out_field = []
    for i, t in enumerate(field):
        odds = {r: float(reach[r][i] / N) for r in rounds}
        odds["win"] = float(win[i] / N)
        row = {**t, "odds": odds}
        s = by_team[t["team"]]
        row.update({"auto_advance": s["auto_advance"], "playoff": s["playoff"],
                    "eliminated": s["eliminated"]})
        out_field.append(row)
    # normalize champion odds (rounding drift)
    tot = sum(t["odds"]["win"] for t in out_field) or 1.0
    for t in out_field:
        t["odds"]["win"] = t["odds"]["win"] / tot
    return {"standings": standings, "field": out_field}
