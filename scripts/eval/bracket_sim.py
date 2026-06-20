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
        "conf": "UEFA",
    },
    # Europa League — same 2024-25 format as UCL (36-team league phase, 8 games each).
    "europa": {
        "phase": {"type": "league", "teams": 36, "matches_each": 8,
                  "auto_advance": 8, "playoff": (9, 24)},
        "ko": [{"round": "R16", "legs": 2}, {"round": "QF", "legs": 2},
               {"round": "SF", "legs": 2}, {"round": "Final", "legs": 1, "neutral": True}],
        "away_goals": False, "extra_time": True, "pens": True,
        "conf": "UEFA",
    },
    # Conference League — same structure but each side plays only 6 league-phase games.
    "conference": {
        "phase": {"type": "league", "teams": 36, "matches_each": 6,
                  "auto_advance": 8, "playoff": (9, 24)},
        "ko": [{"round": "R16", "legs": 2}, {"round": "QF", "legs": 2},
               {"round": "SF", "legs": 2}, {"round": "Final", "legs": 1, "neutral": True}],
        "away_goals": False, "extra_time": True, "pens": True,
        "conf": "UEFA",
    },
    # Concacaf Champions Cup — 27-team pure-knockout; top-5 seeds bye to R16.
    "concacaf-champions": {
        "phase": {"type": "bracket", "teams": 27, "byes": 5, "round_one": "RoundOne"},
        "ko": [{"round": "R16", "legs": 2}, {"round": "QF", "legs": 2},
               {"round": "SF", "legs": 2}, {"round": "Final", "legs": 1, "neutral": True}],
        "away_goals": False, "extra_time": True, "pens": True,
        "conf": "Concacaf",
    },
    # Leagues Cup — 18 MLS + 18 Liga MX; two parallel tables; top 4 per table -> 8-team KO.
    "leagues-cup": {
        "phase": {"type": "two_table", "teams": 36, "games_each": 3,
                  "advance_per_table": 4, "no_draws": True},
        "ko": [{"round": "QF", "legs": 1}, {"round": "SF", "legs": 1},
               {"round": "Final", "legs": 1, "neutral": True}],
        "extra_time": True, "pens": True,
        "conf": "Concacaf",
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


def _sim_match(sh, sa, neutral, rng, conf: str = "UEFA"):
    lam_h, lam_a = match_lambdas(sh, sa, neutral, conf=conf)
    return int(rng.poisson(lam_h)), int(rng.poisson(lam_a))


def _sim_league_vectorized(schedule, strengths, N, rng, conf: str = "UEFA"):
    """Vectorize the league/group phase across all N simulations at once.

    Returns:
        pts:   (N, n) int array — points earned by each team in each sim.
        gd:    (N, n) int array — goal difference for each team in each sim.
        order: (N, n) int array — team indices sorted best-to-worst per sim.
    """
    n = len(strengths)
    n_matches = len(schedule)

    # Precompute lambda arrays for each scheduled match (fixed across sims).
    lam_h = np.empty(n_matches)
    lam_a = np.empty(n_matches)
    home_idx = np.empty(n_matches, dtype=int)
    away_idx = np.empty(n_matches, dtype=int)
    for m, (hi, ai, neutral) in enumerate(schedule):
        lam_h[m], lam_a[m] = match_lambdas(strengths[hi], strengths[ai], neutral, conf=conf)
        home_idx[m] = hi
        away_idx[m] = ai

    # Draw all goals at once: shape (N, n_matches).
    hg = rng.poisson(lam_h, size=(N, n_matches))  # home goals
    ag = rng.poisson(lam_a, size=(N, n_matches))  # away goals

    # Goal difference contributions per match.
    delta = hg - ag  # (N, n_matches); positive = home advantage

    # Scatter into per-team pts and gd arrays.
    pts = np.zeros((N, n), dtype=int)
    gd  = np.zeros((N, n), dtype=int)

    home_win = hg > ag   # (N, n_matches) bool
    away_win = ag > hg
    draw     = ~home_win & ~away_win

    # Points: vectorized scatter using np.add.at over the match axis.
    # We iterate over matches (n_matches ~144) rather than N, so this is fast.
    for m in range(n_matches):
        hi = home_idx[m]; ai = away_idx[m]
        pts[:, hi] += home_win[:, m] * 3 + draw[:, m]
        pts[:, ai] += away_win[:, m] * 3 + draw[:, m]
        gd[:, hi]  +=  delta[:, m]
        gd[:, ai]  += -delta[:, m]

    # Per-sim tiebreaker: points dominate, then GD, then random noise.
    key = -(pts * 1000 + gd).astype(float) + rng.random((N, n))
    order = np.argsort(key, axis=1)  # (N, n) — best team first in each row

    return pts, gd, order


def simulate_league_phase(field, schedule, fmt, N: int, seed: int = 0):
    """Monte-Carlo the league phase -> standings rows with bucket probabilities."""
    n = len(field)
    strengths = np.array([t["strength"] for t in field], dtype=float)
    auto_n = fmt["phase"]["auto_advance"]
    playoff_lo, playoff_hi = fmt["phase"]["playoff"]
    rng = np.random.default_rng(seed)

    # Vectorized: simulate all N reps at once.
    _, _, order = _sim_league_vectorized(schedule, strengths, N, rng)

    # order[:, r] gives the team index at rank r+1 for each sim.
    # rank[s, i] = 1-based rank of team i in sim s.
    rank = np.empty((N, n), dtype=int)
    row_idx = np.arange(N)[:, None]
    rank[row_idx, order] = np.arange(1, n + 1)[None, :]

    auto_mask    = rank <= auto_n                           # (N, n)
    playoff_mask = (rank >= playoff_lo) & (rank <= playoff_hi)

    auto    = auto_mask.sum(axis=0).astype(float)
    playoff = playoff_mask.sum(axis=0).astype(float)
    elim    = (~(auto_mask | playoff_mask)).sum(axis=0).astype(float)

    return [
        {"team": field[i]["team"], "strength": float(strengths[i]),
         "auto_advance": float(auto[i] / N), "playoff": float(playoff[i] / N),
         "eliminated": float(elim[i] / N)}
        for i in range(n)
    ]


def sim_single_leg(sh, sa, rng, neutral=False, conf: str = "UEFA"):
    """One match -> winner index (0=home/sh, 1=away/sa); ties broken by penalties."""
    hg, ag = _sim_match(sh, sa, neutral, rng, conf=conf)
    if hg > ag: return 0
    if ag > hg: return 1
    return _pens(sh, sa, rng)


def sim_two_leg(sa_strength, sb_strength, rng, fmt, conf: str = "UEFA"):
    """Two-leg tie (A home leg 1, B home leg 2) -> winner index (0=A, 1=B)."""
    a_h, b_a = _sim_match(sa_strength, sb_strength, False, rng, conf=conf)   # leg 1: A home
    b_h, a_a = _sim_match(sb_strength, sa_strength, False, rng, conf=conf)   # leg 2: B home
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


def _run_ko(alive, fmt, strengths, rng, reach, win, conf: str = "UEFA"):
    """Run the knockout rounds over `alive` (the entry field, a power of two).
    Mutates reach[round] (teams alive at the start of each round) and win[champion].
    Returns the champion index."""
    for r in fmt["ko"]:
        for t in alive:
            reach[r["round"]][t] += 1
        nxt = []
        if r.get("legs", 1) == 2:
            for k in range(0, len(alive), 2):
                a, b = alive[k], alive[k + 1]
                w = sim_two_leg(strengths[a], strengths[b], rng, fmt, conf=conf)
                nxt.append(a if w == 0 else b)
        else:  # single-leg round(s) — loop pairs (a 2-team final is the degenerate case)
            for k in range(0, len(alive), 2):
                a, b = alive[k], alive[k + 1]
                w = sim_single_leg(strengths[a], strengths[b], rng,
                                   neutral=r.get("neutral", False), conf=conf)
                nxt.append(a if w == 0 else b)
        alive = nxt
    win[alive[0]] += 1
    return alive[0]


def _simulate_bracket(comp_id, field, N, seed=0):
    fmt = FORMATS[comp_id]
    conf = fmt.get("conf", "UEFA")
    n = len(field)
    rng = np.random.default_rng(seed)
    rounds = [r["round"] for r in fmt["ko"]]
    byes = fmt["phase"]["byes"]
    ro = fmt["phase"].get("round_one", "RoundOne")
    reach = {r: np.zeros(n) for r in rounds}
    reach[ro] = np.zeros(n)
    win = np.zeros(n)
    strengths = np.array([t["strength"] for t in field], dtype=float)
    # Fixed seeding by strength: top `byes` skip Round One; the rest are paired
    # strongest-vs-weakest (standard bracket seeding). Seeding is fixed across runs;
    # only match outcomes vary.
    seed_order = list(np.argsort(-strengths))
    bye_set = set(int(x) for x in seed_order[:byes])
    r1 = seed_order[byes:]
    for _ in range(N):
        for t in r1:
            reach[ro][t] += 1
        winners = []
        lo, hi = 0, len(r1) - 1
        while lo < hi:
            a, b = r1[lo], r1[hi]
            w = sim_two_leg(strengths[a], strengths[b], rng, fmt, conf=conf)
            winners.append(a if w == 0 else b)
            lo += 1; hi -= 1
        if lo == hi:                      # odd leftover -> free pass
            winners.append(r1[lo])
        r16 = list(seed_order[:byes]) + winners
        size = 1 << (len(r16).bit_length() - 1)   # truncate to power of two (16)
        _run_ko(r16[:size], fmt, strengths, rng, reach, win, conf=conf)
    all_rounds = [ro] + rounds
    out_field = []
    for i, t in enumerate(field):
        odds = {r: float(reach[r][i] / N) for r in all_rounds}
        odds["win"] = float(win[i] / N)
        out_field.append({**t, "odds": odds, "bye": i in bye_set})
    tot = sum(t["odds"]["win"] for t in out_field) or 1.0
    for t in out_field:
        t["odds"]["win"] /= tot
    return {"standings": [], "field": out_field}


def _simulate_two_table(comp_id, field, N, seed=0):
    fmt = FORMATS[comp_id]
    conf = fmt.get("conf", "UEFA")
    n = len(field)
    rng = np.random.default_rng(seed)
    rounds = [r["round"] for r in fmt["ko"]]
    reach = {r: np.zeros(n) for r in rounds}
    win = np.zeros(n)
    advance = np.zeros(n)                       # P(top-`adv_per` in own table)
    strengths = np.array([t["strength"] for t in field], dtype=float)
    adv_per = fmt["phase"]["advance_per_table"]
    games_each = fmt["phase"]["games_each"]
    # two tables, keyed by league
    tables = {}
    for i, t in enumerate(field):
        tables.setdefault(t.get("league"), []).append(i)
    tkeys = list(tables.keys())
    if len(tkeys) != 2:
        raise ValueError(f"two_table expects exactly 2 leagues, got {tkeys}")
    A, B = tables[tkeys[0]], tables[tkeys[1]]

    for _ in range(N):
        pts = np.zeros(n); gd = np.zeros(n)
        # each club plays `games_each` cross-league games (rotated pairing, alt home)
        for gi in range(games_each):
            for k in range(len(A)):
                a = A[k]; b = B[(k + gi) % len(B)]
                hi, ai = (a, b) if gi % 2 == 0 else (b, a)
                hg, ag = _sim_match(strengths[hi], strengths[ai], False, rng, conf=conf)
                gd[hi] += hg - ag; gd[ai] += ag - hg
                if hg > ag: pts[hi] += 3
                elif ag > hg: pts[ai] += 3
                else:                              # no draws -> PK decides, winner +3
                    pts[hi if _pens(strengths[hi], strengths[ai], rng) == 0 else ai] += 3
        # rank each table; top adv_per advance
        seeded = {}
        for tk in tkeys:
            order = sorted(tables[tk], key=lambda i: -(pts[i]*1000 + gd[i] + rng.random()))
            seeded[tk] = order[:adv_per]
            for i in order[:adv_per]:
                advance[i] += 1
        # cross-seed the 8-team bracket: A1 vs B4, A2 vs B3, ... so _run_ko pairs them
        sa, sb = seeded[tkeys[0]], seeded[tkeys[1]]
        alive = []
        for k in range(adv_per):
            alive.append(sa[k]); alive.append(sb[adv_per - 1 - k])
        _run_ko(alive, fmt, strengths, rng, reach, win, conf=conf)

    out_field = []
    for i, t in enumerate(field):
        odds = {r: float(reach[r][i] / N) for r in rounds}
        odds["win"] = float(win[i] / N)
        out_field.append({**t, "odds": odds, "advance": float(advance[i] / N)})
    tot = sum(t["odds"]["win"] for t in out_field) or 1.0
    for t in out_field:
        t["odds"]["win"] /= tot
    standings = [{"team": t["team"], "league": t.get("league"), "table": t.get("league"),
                  "strength": float(strengths[i]), "advance": float(advance[i] / N)}
                 for i, t in enumerate(field)]
    return {"standings": standings, "field": out_field}


def simulate(comp_id: str, field, N: int, seed: int = 0):
    """Full Monte-Carlo: league phase (if any) + knockout -> standings + odds.

    Returns {"standings": [...], "field": [...with odds...]}.
    `field` entries need keys: team, strength (+ any passthrough display keys).

    For "league" phase comps (UCL/Europa/Conference): implements the real
    knockout-playoff structure — top `auto_advance` (8) go straight to R16;
    teams ranked `playoff[0]`..`playoff[1]` (9-24, 16 teams) play a two-leg
    knockout-playoff (8 ties → 8 winners); R16 = 8 auto + 8 playoff winners.
    A "KOplayoff" reach counter is tracked for the 16 playoff teams.
    """
    fmt = FORMATS[comp_id]
    if fmt["phase"]["type"] == "bracket":
        return _simulate_bracket(comp_id, field, N, seed)
    if fmt["phase"]["type"] == "two_table":
        return _simulate_two_table(comp_id, field, N, seed)

    conf = fmt.get("conf", "UEFA")
    n = len(field)
    rng = np.random.default_rng(seed)
    rounds = [r["round"] for r in fmt["ko"]]
    # KOplayoff is a pre-R16 round for the 9-24 ranked teams.
    reach = {"KOplayoff": np.zeros(n)}
    reach.update({r: np.zeros(n) for r in rounds})
    win = np.zeros(n)

    schedule = make_league_schedule(field, fmt["phase"]["matches_each"], seed)
    strengths = np.array([t["strength"] for t in field], dtype=float)
    auto_n = fmt["phase"]["auto_advance"]
    playoff_lo, playoff_hi = fmt["phase"]["playoff"]

    # --- Vectorized league phase: draw all goals for all N sims at once ---
    _, _, order_arr = _sim_league_vectorized(schedule, strengths, N, rng, conf=conf)
    # order_arr: (N, n) — team indices sorted best-to-worst per sim row.

    # Standings: reuse simulate_league_phase logic but from the order array.
    rank_arr = np.empty((N, n), dtype=int)
    row_idx = np.arange(N)[:, None]
    rank_arr[row_idx, order_arr] = np.arange(1, n + 1)[None, :]

    auto_mask    = rank_arr <= auto_n
    playoff_mask = (rank_arr >= playoff_lo) & (rank_arr <= playoff_hi)
    auto_counts    = auto_mask.sum(axis=0).astype(float)
    playoff_counts = playoff_mask.sum(axis=0).astype(float)
    elim_counts    = (~(auto_mask | playoff_mask)).sum(axis=0).astype(float)

    standings = [
        {"team": field[i]["team"], "strength": float(strengths[i]),
         "auto_advance": float(auto_counts[i] / N),
         "playoff": float(playoff_counts[i] / N),
         "eliminated": float(elim_counts[i] / N)}
        for i in range(n)
    ]

    # --- Per-sim knockout: explicit KO-playoff then R16→Final ---
    for s in range(N):
        order = list(order_arr[s])
        # top auto_n (rank 1-8) go straight to R16
        auto_slots = order[:auto_n]
        # rank 9-24 (playoff_lo-1 to playoff_hi-1 in 0-based) play KO-playoff
        ko_playoff_teams = order[auto_n:playoff_hi]  # 16 teams

        # Record KOplayoff reach for these 16 teams (auto-advancers skip it).
        for t in ko_playoff_teams:
            reach["KOplayoff"][t] += 1

        # Pair them: seed 9 vs seed 24, seed 10 vs seed 23, ..., seed 16 vs seed 17
        # (best vs worst in the playoff pool — standard seeding).
        ko_lo, ko_hi = 0, len(ko_playoff_teams) - 1
        ko_winners = []
        while ko_lo < ko_hi:
            a, b = ko_playoff_teams[ko_lo], ko_playoff_teams[ko_hi]
            w = sim_two_leg(strengths[a], strengths[b], rng, fmt, conf=conf)
            ko_winners.append(a if w == 0 else b)
            ko_lo += 1; ko_hi -= 1

        # R16 field: 8 auto-advancers + 8 KO-playoff winners = 16 teams
        r16_field = auto_slots + ko_winners
        _run_ko(r16_field, fmt, strengths, rng, reach, win, conf=conf)

    by_team = {s["team"]: s for s in standings}
    out_field = []
    all_rounds = ["KOplayoff"] + rounds
    for i, t in enumerate(field):
        odds = {r: float(reach[r][i] / N) for r in all_rounds}
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
