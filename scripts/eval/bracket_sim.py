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
    # This is the 2026 edition and the default; earlier editions differ, see
    # SEASON_FORMATS below. `no_draws` is now READ (it was decorative before
    # 2026-08-07, and the shootout branch ran unconditionally).
    "leagues-cup": {
        "phase": {"type": "two_table", "teams": 36, "games_each": 3,
                  "advance_per_table": 4, "no_draws": False,
                  # Every edition to date has been played entirely in the United
                  # States and Canada, so a Liga MX club listed as home is at an
                  # MLS or neutral American ground. Measured on the 2024 cache:
                  # a home side won 44.2% of all matches, but a Liga MX side
                  # nominally at home won 28.0% (n=25) — barely above the 24.7%
                  # that away sides managed. Handing it a home advantage it never
                  # had biased every Liga MX projection upward.
                  "host_league": "mls"},
        "ko": [{"round": "QF", "legs": 1}, {"round": "SF", "legs": 1},
               {"round": "Final", "legs": 1, "neutral": True}],
        "extra_time": True, "pens": True,
        "conf": "Concacaf",
    },
    # CONMEBOL (2026-07-24). Both comps: 32 teams, 8 groups of 4, double
    # round-robin, top 2 out, then a two-legged bracket to a one-off final.
    # Qualifying rounds (Libertadores first/second/third stage, Sudamericana
    # first stage) precede the group stage and are NOT modeled — the same
    # treatment UEFA qualifying gets, and stated in each comp's `rules`.
    "libertadores": {
        "phase": {"type": "groups", "teams": 32, "groups": 8, "advance_per_group": 2},
        "ko": [{"round": "R16", "legs": 2}, {"round": "QF", "legs": 2},
               {"round": "SF", "legs": 2}, {"round": "Final", "legs": 1, "neutral": True}],
        "away_goals": False, "extra_time": True, "pens": True,
        "conf": "CONMEBOL",
    },
    # Sudamericana's real R16 also absorbs the eight third-placed Libertadores
    # group teams, who meet the group runners-up in a knockout play-off round.
    # That inflow comes from a DIFFERENT competition's field and cannot be
    # represented inside this comp's team list, so it is not modeled — the
    # group runners-up are advanced directly. Same precedent as the unmodeled
    # cross-league barrages in the domestic second tiers.
    "sudamericana": {
        "phase": {"type": "groups", "teams": 32, "groups": 8, "advance_per_group": 2},
        "ko": [{"round": "R16", "legs": 2}, {"round": "QF", "legs": 2},
               {"round": "SF", "legs": 2}, {"round": "Final", "legs": 1, "neutral": True}],
        "away_goals": False, "extra_time": True, "pens": True,
        "conf": "CONMEBOL",
    },
}


# ── Per-edition overrides ────────────────────────────────────────────────────
# A competition whose rules change between editions cannot be described by one
# spec. FORMATS holds the CURRENT edition; anything here overrides it for a
# given season. Without this, replaying 2024 would run it under 2026's rules and
# report a number about nothing.
#
# Leagues Cup. 2023 and 2024 are established from match data — the ESPN cache
# for 2024 (77 rows) and API-Football league 772 for both seasons — not from
# memory:
#
#   season  fixtures  shape                                    level matches
#   2023    77        15 groups of 3 (45) -> R32/R16/QF/SF/3rd/F   23 to penalties
#   2024    77        identical                                    24 to penalties
#
#   * Both editions decided level matches by SHOOTOUT: 23 of 77 and 24 of 77
#     carry a PEN status, and in the ESPN cache all 24 of 2024's drawn matches
#     record a winner (15 of 15 in the group stage). A draw was worth 0 to the
#     loser, the opposite of the current edition.
#   * Both had a 47-club field: 45 in fifteen three-club groups, each club
#     playing two matches, plus two seeded byes straight to a 32-team knockout.
#   * Clubs faced their OWN league — 29 MLS-v-MLS and 4 LigaMX-v-LigaMX ties in
#     2024, e.g. Orlando City v Houston Dynamo in 2023's group stage. The
#     current rule ("clubs never face and are never ranked against their own
#     league") did not hold, so the two-table shape is wrong for both.
#
# 2025 is deliberately NOT listed. The owner confirmed on 2026-08-07 that it was
# played under the same rules as 2026, so it falls through to FORMATS and the
# current two-table spec governs it. That makes 2025 the earliest season this
# engine can replay — the only thing a backtest needs beyond it is 2025 MATCH
# data, which nothing here has established to be unavailable.
#
# `format_for` raises for any season recorded below, so a caller cannot silently
# replay one under another edition's rules.
_UNSUPPORTED = "unsupported"

SEASON_FORMATS: dict[str, dict[int, dict | str]] = {
    "leagues-cup": {
        # The engine has no phase type for "groups of three with byes into a
        # round of 32", so these are recorded and refused rather than
        # approximated by the two-table sim.
        2023: _UNSUPPORTED,
        2024: _UNSUPPORTED,
    },
}


def format_for(comp_id: str, season: int | None = None) -> dict:
    """The format spec governing `comp_id` in `season`.

    Falls back to FORMATS[comp_id] when a season has no override, which keeps
    every other competition — none of which has changed shape — untouched.
    """
    override = SEASON_FORMATS.get(comp_id, {}).get(season) if season else None
    if override is _UNSUPPORTED:
        raise ValueError(
            f"{comp_id} {season} used a format this engine cannot represent; "
            f"simulating it under {comp_id}'s current rules would be wrong. "
            f"See SEASON_FORMATS in scripts/eval/bracket_sim.py.")
    return override or FORMATS[comp_id]


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


def _run_ko(alive, fmt, strengths, rng, reach, win, conf: str = "UEFA",
            neutral_of=None):
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
                # A round already declared neutral stays neutral. Otherwise a
                # competition may still rule that this particular host is not
                # actually at home — the Leagues Cup plays its whole knockout in
                # the United States, so a Liga MX side hosting a quarter-final
                # is no more at home than it was in the group phase.
                neutral = r.get("neutral", False)
                if not neutral and neutral_of is not None:
                    neutral = neutral_of(a)
                w = sim_single_leg(strengths[a], strengths[b], rng,
                                   neutral=neutral, conf=conf)
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


def _simulate_two_table(comp_id, field, N, seed=0, season=None):
    fmt = format_for(comp_id, season)
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
    # Read, not assumed. The shootout branch used to run unconditionally while
    # the published rules said "1 for a draw" — the sim was playing 2023-24 and
    # the page was describing 2026. (2026-08-07)
    no_draws = bool(fmt["phase"].get("no_draws", False))
    # The league whose grounds host the competition. Every other club is at a
    # neutral venue even when the fixture lists it as home.
    host_league = fmt["phase"].get("host_league")
    # two tables, keyed by league
    tables = {}
    for i, t in enumerate(field):
        tables.setdefault(t.get("league"), []).append(i)
    tkeys = list(tables.keys())
    if len(tkeys) != 2:
        raise ValueError(f"two_table expects exactly 2 leagues, got {tkeys}")
    A, B = tables[tkeys[0]], tables[tkeys[1]]
    league_of = {i: t.get("league") for i, t in enumerate(field)}

    for _ in range(N):
        pts = np.zeros(n); gd = np.zeros(n)
        # Resample the cross-league pairing every simulation. It used to be
        # B[(k + gi) % len(B)] over field-ordered lists, i.e. ALPHABETICAL: a
        # club's opponents were a deterministic function of its name and were
        # identical in all N runs, so no schedule uncertainty reached a single
        # published number. Permuting B and keeping the rotation preserves the
        # property that matters — every club plays `games_each` DISTINCT
        # opponents from the other league — while making which ones a draw.
        Bp = [B[j] for j in rng.permutation(len(B))]
        for gi in range(games_each):
            for k in range(len(A)):
                a = A[k]; b = Bp[(k + gi) % len(Bp)]
                hi, ai = (a, b) if gi % 2 == 0 else (b, a)
                # A nominal host from the visiting league is not actually home.
                neutral = host_league is not None and league_of[hi] != host_league
                hg, ag = _sim_match(strengths[hi], strengths[ai], neutral, rng, conf=conf)
                gd[hi] += hg - ag; gd[ai] += ag - hg
                if hg > ag: pts[hi] += 3
                elif ag > hg: pts[ai] += 3
                elif no_draws:                     # shootout decides, winner +3
                    pts[hi if _pens(strengths[hi], strengths[ai], rng) == 0 else ai] += 3
                else:                              # 3 for a win, 1 for a draw
                    pts[hi] += 1; pts[ai] += 1
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
        _run_ko(alive, fmt, strengths, rng, reach, win, conf=conf,
                neutral_of=(None if host_league is None
                            else lambda i: league_of[i] != host_league))

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


def _simulate_groups(comp_id, field, N, seed=0, groups=None, qualifiers=None):
    """CONMEBOL shape: G groups of K, top `advance_per_group` into a KO bracket.

    Neither `league` (one table) nor `two_table` fits Libertadores/Sudamericana:
    32 teams in 8 groups of 4, double round-robin inside each group, top 2 out.

    `groups` — list of lists of FIELD INDICES. Passed in by the caller, which
    infers the real draw from played group-stage matches rather than inventing
    one (two teams in the same group are exactly the teams that played each
    other in the group stage). Falls back to a seeded random partition when no
    group match has been played yet.

    `qualifiers` — when the group stage is already COMPLETE, the caller passes
    the teams that actually advanced and the group phase is not simulated at
    all. Without this the page would re-roll a group stage whose results are
    already known and print, say, a 30% elimination chance for a team that has
    demonstrably already qualified. The UEFA `league` path has this same
    limitation; it is fixable here because the group structure makes the
    qualifier set unambiguous.
    """
    fmt = FORMATS[comp_id]
    conf = fmt.get("conf", "UEFA")
    n = len(field)
    rng = np.random.default_rng(seed)
    rounds = [r["round"] for r in fmt["ko"]]
    reach = {r: np.zeros(n) for r in rounds}
    win = np.zeros(n)
    advance = np.zeros(n)
    strengths = np.array([t["strength"] for t in field], dtype=float)
    adv_per = fmt["phase"]["advance_per_group"]
    n_groups = fmt["phase"]["groups"]

    if not groups:
        perm = list(rng.permutation(n))
        groups = [perm[i::n_groups] for i in range(n_groups)]

    locked = None
    if qualifiers:
        locked = [i for i in qualifiers if 0 <= i < n]
        # A KO bracket needs a power of two; bail out to simulation if the
        # caller handed us a partial or malformed qualifier set.
        if len(locked) < 2 or (len(locked) & (len(locked) - 1)) != 0:
            locked = None

    for _ in range(N):
        if locked is not None:
            for i in locked:
                advance[i] += 1
            alive = list(locked)
        else:
            pts = np.zeros(n)
            gd = np.zeros(n)
            for g in groups:
                for a_i in range(len(g)):
                    for b_i in range(a_i + 1, len(g)):
                        for hi, ai in ((g[a_i], g[b_i]), (g[b_i], g[a_i])):
                            hg, ag = _sim_match(strengths[hi], strengths[ai], False,
                                                rng, conf=conf)
                            gd[hi] += hg - ag
                            gd[ai] += ag - hg
                            if hg > ag:
                                pts[hi] += 3
                            elif ag > hg:
                                pts[ai] += 3
                            else:
                                pts[hi] += 1
                                pts[ai] += 1
            seeded = []
            for g in groups:
                order = sorted(g, key=lambda i: -(pts[i] * 1000 + gd[i] + rng.random()))
                seeded.append(order[:adv_per])
                for i in order[:adv_per]:
                    advance[i] += 1
            # Cross-pair winners against runners-up from a DIFFERENT group, which
            # is the one hard constraint in the real draw.
            alive = []
            for k in range(len(seeded)):
                alive.append(seeded[k][0])
                alive.append(seeded[(k + 1) % len(seeded)][min(1, adv_per - 1)])
            alive = alive[:2 ** int(np.log2(max(len(alive), 2)))]
        _run_ko(alive, fmt, strengths, rng, reach, win, conf=conf)

    out_field = []
    for i, t in enumerate(field):
        odds = {r: float(reach[r][i] / N) for r in rounds}
        odds["win"] = float(win[i] / N)
        out_field.append({**t, "odds": odds, "advance": float(advance[i] / N)})
    tot = sum(t["odds"]["win"] for t in out_field) or 1.0
    for t in out_field:
        t["odds"]["win"] /= tot
    # `table` is what the webapp groups the standings panels on (the key the
    # Leagues Cup two-table view already uses). Groups are numbered by their
    # alphabetically-first club so the labels are STABLE across rebuilds; they
    # are our own positional numbering, not CONMEBOL's official group letters,
    # which ESPN's feed does not expose (every group match carries the same
    # "group-stage" round slug).
    group_of: dict[int, str] = {}
    for gi, g in enumerate(sorted(groups, key=lambda g: min(field[i]["team"] for i in g))):
        for i in g:
            group_of[i] = f"Group {gi + 1}"
    standings = [{"team": t["team"], "league": t.get("league"),
                  "table": group_of.get(i, "Group 1"),
                  "strength": float(strengths[i]), "advance": float(advance[i] / N)}
                 for i, t in enumerate(field)]
    return {"standings": standings, "field": out_field}


def simulate(comp_id: str, field, N: int, seed: int = 0,
             groups=None, qualifiers=None, season: int | None = None):
    """Full Monte-Carlo: league phase (if any) + knockout -> standings + odds.

    Returns {"standings": [...], "field": [...with odds...]}.
    `field` entries need keys: team, strength (+ any passthrough display keys).

    For "league" phase comps (UCL/Europa/Conference): implements the real
    knockout-playoff structure — top `auto_advance` (8) go straight to R16;
    teams ranked `playoff[0]`..`playoff[1]` (9-24, 16 teams) play a two-leg
    knockout-playoff (8 ties → 8 winners); R16 = 8 auto + 8 playoff winners.
    A "KOplayoff" reach counter is tracked for the 16 playoff teams.
    """
    fmt = format_for(comp_id, season)
    if fmt["phase"]["type"] == "bracket":
        return _simulate_bracket(comp_id, field, N, seed)
    if fmt["phase"]["type"] == "two_table":
        return _simulate_two_table(comp_id, field, N, seed, season=season)
    if fmt["phase"]["type"] == "groups":
        return _simulate_groups(comp_id, field, N, seed,
                                groups=groups, qualifiers=qualifiers)

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
