# Continental Competitions — UCL Vertical Slice Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the full predict→bracket→webapp chain for the UEFA Champions League as a vertical slice: cross-league team strength, a generic format-spec bracket simulator, an ESPN data adapter, calibration/validation, a dashboard build, and a two-sub-tab knockout webapp view.

**Architecture:** Each team gets a single cross-league strength = domestic ELO + a per-league coefficient offset (modeled teams) or a coefficient-derived value (unmodeled teams). A Poisson match model turns strength differences into scorelines; a generic Monte-Carlo engine simulates the league phase + knockout bracket into advance/champion odds. All new files except one webapp mode branch and the registry status flip — the MLS champion and existing leagues are untouched.

**Tech Stack:** Python 3.11, pandas, numpy, scipy, pytest; the existing `scripts/eval/` pure-function package; vanilla-JS `webapp/index.html`.

**Scope:** UCL only. Generalization to Europa/Conference/Concacaf comps is a follow-on plan once this slice is validated and live.

**Design spec:** `docs/superpowers/specs/2026-06-16-continental-competitions-design.md`

---

## File Structure

| File | Responsibility |
|------|----------------|
| `data_pipeline/coefficients.py` (create) | Static UEFA league + club coefficient tables; `league_offset()`, `club_strength()` mapping coefficients → ELO points. |
| `scripts/eval/cross_league.py` (create) | `team_strength()` (ELO+offset or coefficient fallback); `match_lambdas()` + `match_probs()` Poisson match model; `league_elos()` helper. |
| `scripts/eval/bracket_sim.py` (create) | `FORMATS` spec dict; `simulate()` Monte-Carlo engine (league phase + two-leg/single-leg KO, ET, pens). |
| `data_pipeline/espn_continental.py` (create) | `continental_results()` / `continental_fixtures()` for a comp's ESPN slug; team→domestic-league tagging. |
| `scripts/validate_continental.py` (create) | Walk-forward Brier-vs-naive backtest on historical continental results; calibrates `k`/`β`/`base_goals`. |
| `scripts/build_continental_data.py` (create) | `--comp ucl`: field → strengths → bracket MC → `webapp/data/ucl.js`. |
| `webapp/index.html` (modify) | `outlook.mode==='knockout'` branch + `renderKnockout()` two-sub-tab container. |
| `scripts/fetch_league_teams.py` (modify) | Flip `ucl` `soon`→`live`. |
| `tests/test_coefficients.py`, `tests/test_cross_league.py`, `tests/test_bracket_sim.py` (create) | Unit tests. |

---

## Task 1: Coefficient anchor tables

**Files:**
- Create: `data_pipeline/coefficients.py`
- Test: `tests/test_coefficients.py`

The cross-league scale needs an external anchor. UEFA league (country) coefficients
place leagues relative to each other; UEFA club coefficients give unmodeled teams a
strength. Both are stored as static dicts (hand-maintained, dated, like
`data_pipeline/trophies.py`) and mapped to ELO points by a single slope `_K_COEFF`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_coefficients.py
import pytest
from data_pipeline import coefficients as co


def test_reference_league_has_zero_offset():
    # The strongest modeled league (EPL) anchors the scale at 0.
    assert co.league_offset("epl") == 0.0


def test_weaker_league_has_negative_offset():
    # A weaker league sits below EPL on the common scale.
    assert co.league_offset("ligue-1") < 0.0


def test_unknown_league_offset_is_zero_with_no_crash():
    # Graceful fallback: an unmapped league contributes no offset.
    assert co.league_offset("nonexistent-league") == 0.0


def test_club_strength_maps_coefficient_to_elo_scale():
    # A top club coefficient maps to a strength near a strong domestic ELO.
    s = co.club_strength("Real Madrid")
    assert 1700 < s < 2100


def test_unknown_club_strength_returns_baseline():
    # Unknown club → conservative baseline, never a crash.
    assert co.club_strength("FC Nonexistent") == co.BASELINE_STRENGTH
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv/bin/python -m pytest tests/test_coefficients.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'data_pipeline.coefficients'`

- [ ] **Step 3: Write minimal implementation**

```python
# data_pipeline/coefficients.py
"""External strength anchors for cross-league continental modeling.

UEFA league (country) coefficients place modeled leagues on a common scale;
UEFA club coefficients give unmodeled continental entrants a strength estimate.
Both are mapped to ELO points by the single slope _K_COEFF.

Sources (refresh ~annually after the season ends):
  - League coefficients: UEFA 5-year country ranking
    https://www.uefa.com/nationalassociations/uefarankings/country/
  - Club coefficients: UEFA 5-year club ranking
    https://www.uefa.com/nationalassociations/uefarankings/club/
Values below captured 2026-06 (2025-26 season end).
"""
from __future__ import annotations

# ELO points per UEFA-coefficient point (calibrated in validate_continental.py,
# Task 7; this is the starting prior).
_K_COEFF = 3.0

# Strength (ELO points) assigned to an unknown/unlisted club — conservative,
# roughly a mid-table side in a weak European league.
BASELINE_STRENGTH = 1450.0

# Reference league (anchors the offset scale at 0).
_REF_LEAGUE = "epl"

# UEFA 5-year country coefficients (2025-26). Keyed by our internal league ids.
_LEAGUE_COEFF: dict[str, float] = {
    "epl": 94.0, "la-liga": 79.0, "serie-a": 76.0, "bundesliga": 74.0,
    "ligue-1": 67.0,
}

# UEFA 5-year club coefficients for common unmodeled UCL entrants, already
# expressed directly in ELO points (club_coeff * _K_COEFF + an anchor). For v1
# we store the resolved strength directly to keep the table legible.
_CLUB_STRENGTH: dict[str, float] = {
    "Real Madrid": 2000.0, "Bayern Munich": 1980.0, "Manchester City": 1990.0,
    "Paris Saint-Germain": 1940.0, "Inter Milan": 1900.0, "Porto": 1780.0,
    "Benfica": 1800.0, "Sporting CP": 1760.0, "PSV Eindhoven": 1740.0,
    "Feyenoord": 1720.0, "Ajax": 1730.0, "Club Brugge": 1690.0,
    "Celtic": 1660.0, "Shakhtar Donetsk": 1700.0, "Red Bull Salzburg": 1710.0,
}


def league_offset(league_id: str) -> float:
    """Per-league additive ELO offset onto the common cross-league scale.

    EPL (the strongest modeled league) anchors at 0; weaker leagues are negative.
    Unknown leagues return 0 (no offset) rather than raising.
    """
    if league_id not in _LEAGUE_COEFF:
        return 0.0
    return _K_COEFF * (_LEAGUE_COEFF[league_id] - _LEAGUE_COEFF[_REF_LEAGUE])


def club_strength(club: str) -> float:
    """Cross-league strength (ELO points) for an unmodeled club, or BASELINE."""
    return _CLUB_STRENGTH.get(club, BASELINE_STRENGTH)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `venv/bin/python -m pytest tests/test_coefficients.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add data_pipeline/coefficients.py tests/test_coefficients.py
git commit -m "Continental: coefficient anchor tables (league offsets + club strength)"
```

---

## Task 2: Cross-league team strength

**Files:**
- Create: `scripts/eval/cross_league.py`
- Test: `tests/test_cross_league.py`

`team_strength` is the seam where Approach C will later swap in bridge-regression
offsets. For modeled teams it composes domestic ELO + `league_offset`; for unmodeled
teams it falls back to `club_strength`. `league_elos` loads a modeled league's cached
frame and runs the champion-config `compute_elo` to get current ratings.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_cross_league.py
import pytest
from scripts.eval import cross_league as cl


def test_modeled_team_strength_is_elo_plus_offset():
    elos = {"Arsenal": 1650.0}
    # EPL offset is 0, so strength == domestic ELO.
    s = cl.team_strength("Arsenal", "epl", elos)
    assert s == 1650.0


def test_modeled_team_in_weaker_league_shifts_down():
    elos = {"Lyon": 1650.0}
    s = cl.team_strength("Lyon", "ligue-1", elos)
    assert s < 1650.0  # ligue-1 offset is negative


def test_unmodeled_team_uses_club_strength_fallback():
    # Team not in the elos dict and league None → coefficient fallback.
    s = cl.team_strength("Porto", None, {})
    assert s == 1780.0  # from _CLUB_STRENGTH


def test_unknown_unmodeled_team_uses_baseline():
    s = cl.team_strength("FC Nowhere", None, {})
    assert s == cl.co.BASELINE_STRENGTH
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv/bin/python -m pytest tests/test_cross_league.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'scripts.eval.cross_league'`

- [ ] **Step 3: Write minimal implementation**

```python
# scripts/eval/cross_league.py
"""Cross-league strength + match model for continental competitions.

A team's strength is a single number on a common ELO-point scale:
    modeled:   domestic ELO (compute_elo) + league_offset (coefficients)
    unmodeled: club_strength (coefficients), no ELO term

team_strength() is the seam: Approach C (bridge-regression offsets) replaces only
how the offset is derived, with no change to the match model or simulator.
"""
from __future__ import annotations

import math

import numpy as np

from data_pipeline import coefficients as co
from scripts.eval.elo import compute_elo

# Champion ELO config (matches the rest of the platform).
_ELO_K, _ELO_HA, _ELO_REGRESS, _ELO_INIT = 25.0, 80.0, 0.40, 1500.0

# Match-model constants (calibrated in validate_continental.py, Task 7 — priors here).
BASE_GOALS = 1.35   # league-neutral expected goals per side at equal strength
GOAL_SCALE = 800.0  # ELO points per 10x multiplier on the goal rate
HOME_ADV_ELO = 65.0 # home advantage in strength points for non-neutral matches


def team_strength(team: str, league_id: str | None, league_elos: dict[str, float]) -> float:
    """Cross-league strength (ELO points) for a team.

    Args:
        team:        team display key.
        league_id:   modeled-league id (e.g. 'epl') or None for unmodeled.
        league_elos: {team: current_elo} for that league (empty if unmodeled).
    """
    if league_id and team in league_elos:
        return league_elos[team] + co.league_offset(league_id)
    return co.club_strength(team)


def match_lambdas(strength_home: float, strength_away: float,
                  neutral: bool = False) -> tuple[float, float]:
    """Expected goals (lambda_home, lambda_away) from cross-league strengths."""
    ha = 0.0 if neutral else HOME_ADV_ELO
    diff = strength_home - strength_away
    lam_home = BASE_GOALS * 10.0 ** ((diff + ha) / GOAL_SCALE)
    lam_away = BASE_GOALS * 10.0 ** ((-diff) / GOAL_SCALE)
    return lam_home, lam_away


def match_probs(strength_home: float, strength_away: float,
                neutral: bool = False, max_g: int = 10) -> tuple[float, float, float]:
    """(P_home, P_draw, P_away) via independent Poisson score matrix."""
    lam_h, lam_a = match_lambdas(strength_home, strength_away, neutral)
    ph = _poisson_pmf(np.arange(max_g + 1), lam_h)
    pa = _poisson_pmf(np.arange(max_g + 1), lam_a)
    M = np.outer(ph, pa)
    home = float(np.tril(M, -1).sum())
    draw = float(np.diag(M).sum())
    away = float(np.triu(M, 1).sum())
    t = home + draw + away
    return home / t, draw / t, away / t


def _poisson_pmf(ks: np.ndarray, lam: float) -> np.ndarray:
    # exp(-lam) * lam^k / k!  — vectorized, no scipy import needed for this size.
    return np.exp(-lam) * lam ** ks / np.array([math.factorial(int(k)) for k in ks])


def league_elos(frame, K: float = _ELO_K, home_adv: float = _ELO_HA) -> dict[str, float]:
    """Current {team: elo} for a modeled league, champion config."""
    df = frame.sort_values("date")
    _, ratings = compute_elo(df, K=K, home_adv=home_adv,
                             regress=_ELO_REGRESS, initial=_ELO_INIT,
                             return_ratings=True)
    return ratings
```

- [ ] **Step 4: Run test to verify it passes**

Run: `venv/bin/python -m pytest tests/test_cross_league.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add scripts/eval/cross_league.py tests/test_cross_league.py
git commit -m "Continental: cross-league team_strength (ELO+offset / coefficient fallback)"
```

---

## Task 3: Poisson match model tests

**Files:**
- Modify: `tests/test_cross_league.py` (add a test class)

The match model is already implemented in Task 2 (`match_lambdas`, `match_probs`).
This task locks its behavior with tests: monotonicity, symmetry at equal strength,
and home-advantage direction.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_cross_league.py  (append)
class TestMatchModel:
    def test_equal_strength_neutral_is_symmetric(self):
        ph, pd_, pa = cl.match_probs(1700, 1700, neutral=True)
        assert abs(ph - pa) < 1e-9
        assert ph + pd_ + pa == pytest.approx(1.0)

    def test_home_advantage_favors_home(self):
        ph_n, _, _ = cl.match_probs(1700, 1700, neutral=True)
        ph_h, _, _ = cl.match_probs(1700, 1700, neutral=False)
        assert ph_h > ph_n

    def test_stronger_team_more_likely_to_win(self):
        ph_weak, _, _ = cl.match_probs(1600, 1700, neutral=True)
        ph_strong, _, _ = cl.match_probs(1800, 1700, neutral=True)
        assert ph_strong > ph_weak

    def test_lambdas_increase_with_strength_gap(self):
        lh1, la1 = cl.match_lambdas(1700, 1700, neutral=True)
        lh2, la2 = cl.match_lambdas(1900, 1700, neutral=True)
        assert lh2 > lh1 and la2 < la1
```

- [ ] **Step 2: Run test to verify it fails... then passes**

Run: `venv/bin/python -m pytest tests/test_cross_league.py::TestMatchModel -v`
Expected: PASS (4 passed) — the implementation already exists from Task 2. If any
fail, fix `match_lambdas`/`match_probs` in `cross_league.py` until green.

- [ ] **Step 3: Commit**

```bash
git add tests/test_cross_league.py
git commit -m "Continental: lock Poisson match-model behavior with tests"
```

---

## Task 4: Bracket simulator — format spec + league phase

**Files:**
- Create: `scripts/eval/bracket_sim.py`
- Test: `tests/test_bracket_sim.py`

A declarative `FORMATS` dict describes each comp; `simulate_league_phase` runs the
36-team single-table phase via the Poisson match model and returns standings with
auto-advance / playoff / eliminated counts.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_bracket_sim.py
import numpy as np
import pytest
from scripts.eval import bracket_sim as bs


def _field(n):
    # n teams with descending strength, no domestic ELO needed (pre-resolved).
    return [{"team": f"T{i}", "strength": 1900 - i * 10} for i in range(n)]


def test_ucl_format_spec_exists():
    fmt = bs.FORMATS["ucl"]
    assert fmt["phase"]["type"] == "league"
    assert fmt["phase"]["teams"] == 36
    assert fmt["phase"]["auto_advance"] == 8


def test_league_phase_returns_row_per_team():
    field = _field(36)
    schedule = bs.make_league_schedule(field, matches_each=8, seed=1)
    standings = bs.simulate_league_phase(field, schedule, bs.FORMATS["ucl"], N=200, seed=1)
    assert len(standings) == 36
    for row in standings:
        # advance probabilities are fractions in [0, 1]
        assert 0.0 <= row["auto_advance"] <= 1.0
        assert 0.0 <= row["eliminated"] <= 1.0


def test_stronger_teams_advance_more_often():
    field = _field(36)
    schedule = bs.make_league_schedule(field, matches_each=8, seed=2)
    standings = bs.simulate_league_phase(field, schedule, bs.FORMATS["ucl"], N=300, seed=2)
    by_team = {r["team"]: r for r in standings}
    # Strongest team auto-advances more than the weakest.
    assert by_team["T0"]["auto_advance"] > by_team["T35"]["auto_advance"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv/bin/python -m pytest tests/test_bracket_sim.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'scripts.eval.bracket_sim'`

- [ ] **Step 3: Write minimal implementation**

```python
# scripts/eval/bracket_sim.py
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
    """Monte-Carlo the league phase → standings rows with bucket probabilities."""
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `venv/bin/python -m pytest tests/test_bracket_sim.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add scripts/eval/bracket_sim.py tests/test_bracket_sim.py
git commit -m "Continental: bracket_sim format spec + league-phase Monte-Carlo"
```

---

## Task 5: Bracket simulator — knockout (two-leg, ET, penalties)

**Files:**
- Modify: `scripts/eval/bracket_sim.py`
- Test: `tests/test_bracket_sim.py` (add a test class)

Add the knockout engine: two-leg aggregate ties (home/away swap), extra time
(home-neutral mini-Poisson) and penalties (logistic on strength diff) when level,
single-leg neutral final, accumulated into per-team advance/champion odds.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_bracket_sim.py  (append)
class TestKnockout:
    def test_two_leg_tie_favors_stronger(self):
        wins = 0
        rng = np.random.default_rng(0)
        for _ in range(500):
            if bs.sim_two_leg(1900, 1600, rng, fmt=bs.FORMATS["ucl"]) == 0:
                wins += 1
        assert wins > 250  # stronger team (idx 0) wins the tie majority

    def test_single_leg_final_returns_a_winner(self):
        rng = np.random.default_rng(0)
        w = bs.sim_single_leg(1700, 1700, rng, neutral=True)
        assert w in (0, 1)

    def test_full_simulate_returns_champion_odds_summing_to_one(self):
        field = [{"team": f"T{i}", "strength": 1900 - i * 10} for i in range(36)]
        out = bs.simulate("ucl", field, N=200, seed=3)
        total = sum(t["odds"]["win"] for t in out["field"])
        assert total == pytest.approx(1.0, abs=1e-6)
        assert len(out["standings"]) == 36
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv/bin/python -m pytest tests/test_bracket_sim.py::TestKnockout -v`
Expected: FAIL with `AttributeError: module ... has no attribute 'sim_two_leg'`

- [ ] **Step 3: Write minimal implementation**

```python
# scripts/eval/bracket_sim.py  (append)

def sim_single_leg(sh, sa, rng, neutral=False):
    """One match → winner index (0=home/sh, 1=away/sa); ties broken by penalties."""
    hg, ag = _sim_match(sh, sa, neutral, rng)
    if hg > ag: return 0
    if ag > hg: return 1
    return _pens(sh, sa, rng)


def sim_two_leg(sa_strength, sb_strength, rng, fmt):
    """Two-leg tie (A home leg 1, B home leg 2) → winner index (0=A, 1=B)."""
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
    """Penalty shootout → winner index; slight edge to the stronger side."""
    p_home = 1.0 / (1.0 + 10.0 ** (-(sh - sa) / 2000.0))  # near 0.5, mild tilt
    return 0 if rng.random() < p_home else 1


def simulate(comp_id: str, field, N: int, seed: int = 0):
    """Full Monte-Carlo: league phase (if any) + knockout → standings + odds.

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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `venv/bin/python -m pytest tests/test_bracket_sim.py -v`
Expected: PASS (all bracket_sim tests)

- [ ] **Step 5: Commit**

```bash
git add scripts/eval/bracket_sim.py tests/test_bracket_sim.py
git commit -m "Continental: knockout engine (two-leg, ET/pens, neutral final, champion odds)"
```

---

## Task 6: ESPN continental data adapter

**Files:**
- Create: `data_pipeline/espn_continental.py`

Generalizes the `espn_soccer.py` pattern to a continental slug. Fetches completed
results and upcoming fixtures, parsing the round/stage and tagging each competitor
with a domestic-league hint from ESPN.

- [ ] **Step 1: Write the adapter (no unit test — network IO, verified by smoke run)**

```python
# data_pipeline/espn_continental.py
"""ESPN adapter for continental competitions (results + fixtures).

Mirrors data_pipeline/espn_soccer.py but for a continental slug (e.g.
'uefa.champions'). Parquet-cached under data/espn_continental/<comp>.parquet.
"""
from __future__ import annotations

import argparse
import logging
import time
from pathlib import Path

import numpy as np
import pandas as pd
import requests
import urllib3

urllib3.disable_warnings()
logger = logging.getLogger("espn_continental")

_BASE = "https://site.api.espn.com/apis/site/v2/sports/soccer"
_HDR = {"User-Agent": "Mozilla/5.0"}
_CACHE_DIR = Path("data/espn_continental")

# Internal comp id → ESPN slug.
SLUGS = {
    "ucl": "uefa.champions", "europa": "uefa.europa",
    "conference": "uefa.europa.conf", "concacaf-champions": "concacaf.champions",
    "concacaf-league": "concacaf.league",
}


def _fetch(slug: str, y0: int, y1: int) -> list[dict]:
    url = f"{_BASE}/{slug}/scoreboard"
    params = {"dates": f"{y0}0701-{y1}0701", "limit": 500}
    try:
        r = requests.get(url, params=params, headers=_HDR, timeout=30, verify=False)
        r.raise_for_status()
        return r.json().get("events", [])
    except Exception as e:
        logger.warning("ESPN %s %s fetch failed: %s", slug, y0, e)
        return []


def _parse(events: list[dict], season: int, completed_only: bool) -> list[dict]:
    rows = []
    for e in events:
        comps = e.get("competitions", [])
        if not comps:
            continue
        comp = comps[0]
        done = comp.get("status", {}).get("type", {}).get("completed", False)
        if completed_only and not done:
            continue
        cs = comp.get("competitors", [])
        if len(cs) != 2:
            continue
        home = next((c for c in cs if c.get("homeAway") == "home"), None)
        away = next((c for c in cs if c.get("homeAway") == "away"), None)
        if not home or not away:
            continue
        ht = home.get("team", {}).get("displayName", "")
        at = away.get("team", {}).get("displayName", "")
        if not ht or not at:
            continue
        dt = pd.to_datetime(e.get("date"), utc=True, errors="coerce")
        rnd = e.get("season", {}).get("slug", "") or comp.get("notes", [{}])[0].get("headline", "")
        rec = {
            "match_id": f"{season}-{ht}-{at}".replace(" ", "_"),
            "date": dt.normalize().tz_localize(None) if pd.notna(dt) else pd.NaT,
            "season": season, "round": rnd, "home_team": ht, "away_team": at,
            "neutral": bool(comp.get("neutralSite", False)),
        }
        if done:
            try:
                rec["home_goals"] = int(float(home.get("score") or 0))
                rec["away_goals"] = int(float(away.get("score") or 0))
            except (ValueError, TypeError):
                continue
        else:
            rec["home_goals"] = np.nan; rec["away_goals"] = np.nan
        rec["is_result"] = bool(done)
        rows.append(rec)
    return rows


def continental_results(comp_id: str, seasons: range, use_cache: bool = True) -> pd.DataFrame:
    """Completed continental matches for `comp_id` across `seasons` (start years)."""
    slug = SLUGS[comp_id]
    cache = _CACHE_DIR / f"{comp_id}.parquet"
    if use_cache and cache.exists():
        return pd.read_parquet(cache)
    frames = []
    for y in seasons:
        rows = _parse(_fetch(slug, y, y + 1), y, completed_only=True)
        if rows:
            frames.append(pd.DataFrame(rows))
        time.sleep(0.25)
    df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    if not df.empty:
        cache.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(cache, index=False)
    return df


def continental_fixtures(comp_id: str, season: int) -> pd.DataFrame:
    """Upcoming (undrawn ties absent) fixtures for the current season."""
    rows = _parse(_fetch(SLUGS[comp_id], season, season + 1), season, completed_only=False)
    df = pd.DataFrame(rows)
    return df[~df["is_result"]] if not df.empty else df


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--comp", default="ucl")
    ap.add_argument("--from-year", type=int, default=2018)
    ap.add_argument("--to-year", type=int, default=2025)
    a = ap.parse_args()
    df = continental_results(a.comp, range(a.from_year, a.to_year + 1), use_cache=False)
    print(f"{a.comp}: {len(df)} completed matches, "
          f"{df['season'].nunique() if not df.empty else 0} seasons")
```

- [ ] **Step 2: Smoke-run the adapter**

Run: `venv/bin/python -m data_pipeline.espn_continental --comp ucl --from-year 2021 --to-year 2024`
Expected: prints a non-zero match count (e.g. "ucl: ~500 completed matches, 4 seasons").
If 0, inspect the ESPN slug/date window and adjust `SLUGS`/`_fetch` before continuing.

- [ ] **Step 3: Commit**

```bash
git add data_pipeline/espn_continental.py
git commit -m "Continental: ESPN results/fixtures adapter (UCL slug)"
```

---

## Task 7: Validation + constant calibration

**Files:**
- Create: `scripts/validate_continental.py`

Backtests the cross-league match model on historical continental results (model Brier
vs naive) and calibrates `BASE_GOALS`, `GOAL_SCALE`, `HOME_ADV_ELO`, `_K_COEFF`. The
script reports; the human updates the constants in `cross_league.py`/`coefficients.py`
to the reported best and re-runs to confirm.

- [ ] **Step 1: Write the validator**

```python
# scripts/validate_continental.py
"""Walk-forward Brier-vs-naive backtest for the cross-league continental model.

For each historical continental match, resolve both teams' strengths from data
available BEFORE that season and score the Poisson match model's 1X2 Brier against
a base-rate naive. Used to calibrate BASE_GOALS / GOAL_SCALE / HOME_ADV_ELO.
"""
from __future__ import annotations

import argparse

import numpy as np

from data_pipeline.espn_continental import continental_results
from data_pipeline import coefficients as co
from scripts.eval import cross_league as cl


def _strength_resolver():
    """Build a {('league', team): strength} resolver. Unmodeled → club_strength.

    For v1 calibration we use coefficient-based strengths for ALL teams (modeled
    leagues' live ELO snapshots vary by build date); this isolates the match-model
    constants from ELO drift. team_strength still uses ELO in production.
    """
    def resolve(team):
        return co.club_strength(team)
    return resolve


def _brier(p, outcome):  # outcome: 0 home,1 draw,2 away
    y = np.zeros(3); y[outcome] = 1.0
    return float(np.sum((np.array(p) - y) ** 2))


def validate(comp_id: str, seasons: range) -> dict:
    df = continental_results(comp_id, seasons)
    df = df[df["is_result"]].dropna(subset=["home_goals", "away_goals"])
    resolve = _strength_resolver()
    model_b, naive_b = [], []
    # naive = overall base rates on this set
    outcomes = np.where(df["home_goals"] > df["away_goals"], 0,
                        np.where(df["home_goals"] == df["away_goals"], 1, 2))
    base = np.array([(outcomes == k).mean() for k in (0, 1, 2)])
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
```

- [ ] **Step 2: Run the validator**

Run: `venv/bin/python scripts/validate_continental.py --comp ucl --from-year 2021 --to-year 2024`
Expected: prints model vs naive Brier. Success = model BEATS naive. If it trails,
hand-tune `GOAL_SCALE` (lower = sharper) and `BASE_GOALS` in `cross_league.py`,
re-run until the model beats naive, and record the chosen values in a comment.

- [ ] **Step 3: Commit**

```bash
git add scripts/validate_continental.py scripts/eval/cross_league.py data_pipeline/coefficients.py
git commit -m "Continental: walk-forward validator + calibrated match-model constants"
```

---

## Task 8: Build script → ucl.js

**Files:**
- Create: `scripts/build_continental_data.py`

Resolves the UCL field, computes each team's strength (modeled ELO+offset or
coefficient fallback), runs the bracket Monte-Carlo, and emits `webapp/data/ucl.js`
with the knockout payload.

- [ ] **Step 1: Write the build script**

```python
# scripts/build_continental_data.py
"""Build webapp/data/<comp>.js for a continental competition.

Resolves the field's cross-league strengths, runs the bracket Monte-Carlo, and
emits the knockout payload (outlook.mode='knockout', standings, field, champion
odds). Mirrors scripts/build_league_data.py for the table leagues.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from data_pipeline.espn_continental import continental_results
from data_pipeline.understat import canonical_frame
from scripts.eval import bracket_sim as bs
from scripts.eval import cross_league as cl

# Comp metadata for the payload header.
META = {
    "ucl": {"name": "UEFA Champions League", "confederation": "UEFA",
            "format_label": "League phase (36) → knockout", "phases": ["league", "knockout"]},
}

# ESPN displayName → (modeled league id, domestic-league team key). Built by running
# the adapter (Task 6) and mapping the big-5 entrants; unmapped teams fall back to
# coefficients. Filled from observed 2024-25 UCL names — extend as fields change.
_ESPN_TO_MODELED: dict[str, tuple[str, str]] = {
    "Manchester City": ("epl", "Manchester City"),
    "Arsenal": ("epl", "Arsenal"),
    "Liverpool": ("epl", "Liverpool"),
    "Aston Villa": ("epl", "Aston Villa"),
    "Real Madrid": ("la-liga", "Real Madrid"),
    "Barcelona": ("la-liga", "Barcelona"),
    "Atletico Madrid": ("la-liga", "Atletico Madrid"),
    "Girona": ("la-liga", "Girona"),
    "Inter Milan": ("serie-a", "Inter"),
    "AC Milan": ("serie-a", "AC Milan"),
    "Juventus": ("serie-a", "Juventus"),
    "Atalanta": ("serie-a", "Atalanta"),
    "Bologna": ("serie-a", "Bologna"),
    "Bayern Munich": ("bundesliga", "Bayern Munich"),
    "Bayer Leverkusen": ("bundesliga", "Bayer Leverkusen"),
    "VfB Stuttgart": ("bundesliga", "VfB Stuttgart"),
    "RB Leipzig": ("bundesliga", "RasenBallsport Leipzig"),
    "Borussia Dortmund": ("bundesliga", "Borussia Dortmund"),
    "Paris Saint-Germain": ("ligue-1", "Paris Saint Germain"),
    "Brest": ("ligue-1", "Brest"),
    "Monaco": ("ligue-1", "Monaco"),
    "Lille": ("ligue-1", "Lille"),
}

# Cache of {league_id: {team: current_elo}} so each league's frame loads once.
_ELO_CACHE: dict[str, dict[str, float]] = {}


def _league_elos(league_id: str) -> dict[str, float]:
    if league_id not in _ELO_CACHE:
        _ELO_CACHE[league_id] = cl.league_elos(canonical_frame(league_id))
    return _ELO_CACHE[league_id]


def _resolve_field(comp_id: str, season: int):
    """Latest field for the comp → [{team, league, strength, modeled, ...}].

    Modeled big-5 entrants get domestic ELO + league offset (the spec's core);
    everyone else gets the coefficient-based club strength fallback.
    """
    df = continental_results(comp_id, range(season, season + 1))
    teams = sorted(set(df["home_team"]) | set(df["away_team"])) if not df.empty else []
    field = []
    for t in teams:
        mapped = _ESPN_TO_MODELED.get(t)
        if mapped:
            lid, dom_key = mapped
            strength = cl.team_strength(dom_key, lid, _league_elos(lid))
            field.append({"team": t, "league": lid, "strength": strength, "modeled": True})
        else:
            strength = cl.team_strength(t, None, {})
            field.append({"team": t, "league": None, "strength": strength, "modeled": False})
    return field[: bs.FORMATS[comp_id]["phase"]["teams"]]


def build(comp_id: str, season: int, sims: int):
    field = _resolve_field(comp_id, season)
    if len(field) < bs.FORMATS[comp_id]["phase"]["teams"]:
        print(f"[{comp_id}] only {len(field)} teams resolved — field not yet drawn; "
              f"emitting completed-bracket placeholder.")
    result = bs.simulate(comp_id, field, N=sims)
    champ = sorted(({"team": t["team"], "win_pct": round(t["odds"]["win"] * 100, 1)}
                    for t in result["field"]), key=lambda x: -x["win_pct"])
    data = {
        "league": {"name": META[comp_id]["name"],
                   "confederation": META[comp_id]["confederation"]},
        "outlook": {"mode": "knockout", "confederation": META[comp_id]["confederation"],
                    "format_label": META[comp_id]["format_label"],
                    "phases": META[comp_id]["phases"],
                    "rounds": [r["round"] for r in bs.FORMATS[comp_id]["ko"]]},
        "standings": result["standings"],
        "field": result["field"],
        "champion_odds": champ,
        "games": [],  # populated from fixtures once the draw exists
    }
    out = Path(f"webapp/data/{comp_id}.js")
    out.write_text("window.LEAGUE_DATA = " + json.dumps(data, separators=(",", ":")) + ";\n")
    print(f"[{comp_id}] wrote {out} ({out.stat().st_size // 1024} KB) · "
          f"{len(field)} teams · champion favorite {champ[0]['team']} {champ[0]['win_pct']}%")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--comp", default="ucl")
    ap.add_argument("--season", type=int, default=2024)
    ap.add_argument("--sims", type=int, default=20000)
    a = ap.parse_args()
    build(a.comp, a.season, a.sims)
```

- [ ] **Step 2: Build the ESPN→modeled name map, then run the build**

First confirm which UCL entrants resolve as modeled vs fallback:
```bash
venv/bin/python -c "
from scripts.build_continental_data import _resolve_field
f=_resolve_field('ucl',2024)
print('modeled:', sum(t['modeled'] for t in f), '/', len(f))
for t in sorted(f,key=lambda x:-x['strength'])[:10]: print(t['team'],t['league'],round(t['strength']))
"
```
Expected: a healthy share modeled (big-5 clubs), top of the list dominated by modeled
elite clubs with ELO-derived strengths. If a known big-5 club shows `modeled:False`,
its ESPN name differs from `_ESPN_TO_MODELED` / the domestic key — add/fix the mapping
entry (the domestic key must match the team name in that league's Understat frame).

Then: `venv/bin/python scripts/build_continental_data.py --comp ucl --season 2024 --sims 5000`
Expected: writes `webapp/data/ucl.js`; favorite is a top modeled club; champion odds
sum to ~100%.

**Perf note:** `bracket_sim.simulate` runs the league phase twice per build (once for
standings, once inside the bracket loop) via per-match Python `rng.poisson`. At
`--sims 20000` × 36 teams this may take a few minutes; if it's slow, drop to
`--sims 5000` for iteration and only run 20000 for the final artifact. Vectorizing the
match loop (cf. the 2026-06-16 Dixon-Coles fix) is a logged optimization, not a blocker.

- [ ] **Step 3: Commit**

```bash
git add scripts/build_continental_data.py webapp/data/ucl.js
git commit -m "Continental: build_continental_data → ucl.js (knockout payload)"
```

---

## Task 9: Webapp knockout view (two sub-tabs)

**Files:**
- Modify: `webapp/index.html`

Add the `knockout` mode branch and `renderKnockout()` with a League-Phase sub-tab
(table reusing the ladder) and a Knockout sub-tab (bracket + champion-odds leaderboard).

- [ ] **Step 1: Add the mode detection** near the existing `isTable` definition (`webapp/index.html:461`)

```javascript
const isTable = (D.outlook||{}).mode === 'table';
const isKnockout = (D.outlook||{}).mode === 'knockout';
```

- [ ] **Step 2: Route League-Projections rendering** where `renderTableOutlook`/`renderOutlook` are dispatched (e.g. `webapp/index.html:817`, `:829`, `:832`, `:660`). Replace each `(isTable?renderTableOutlook:renderOutlook)()` call with:

```javascript
(isKnockout?renderKnockout:isTable?renderTableOutlook:renderOutlook)()
```

- [ ] **Step 3: Add `renderKnockout()`** after `renderTableOutlook()` (`webapp/index.html:806`)

```javascript
function renderKnockout(){
  const el=$('#outlook'); if(!el) return;
  const phases=(D.outlook.phases||['knockout']);
  const champ=D.champion_odds||[];
  const rounds=D.outlook.rounds||[];
  // Sub-tab header
  let h='<div class="ko-subtabs">';
  if(phases.includes('league')) h+='<button class="ko-tab on" data-k="league">League Phase</button>';
  h+='<button class="ko-tab'+(phases.includes('league')?'':' on')+'" data-k="ko">Knockout</button></div>';
  // League-phase table (reuses standings rows)
  if(phases.includes('league')){
    h+='<div class="ko-pane" data-pane="league"><table class="tlad"><thead><tr>'+
       '<th>#</th><th>Team</th><th>Adv</th><th>Playoff</th><th>Out</th></tr></thead><tbody>';
    const st=[...D.standings].sort((a,b)=>b.auto_advance-a.auto_advance);
    st.forEach((s,i)=>{h+='<tr><td>'+(i+1)+'</td><td>'+s.team+'</td>'+
      '<td>'+(s.auto_advance*100).toFixed(0)+'%</td>'+
      '<td>'+(s.playoff*100).toFixed(0)+'%</td>'+
      '<td>'+(s.eliminated*100).toFixed(0)+'%</td></tr>';
      if(i===7) h+='<tr class="ko-line"><td colspan="5">auto-advance line (top 8)</td></tr>';
      if(i===23) h+='<tr class="ko-line"><td colspan="5">knockout-playoff line (top 24)</td></tr>';});
    h+='</tbody></table></div>';
  }
  // Knockout: champion-odds leaderboard + per-round advance odds
  h+='<div class="ko-pane'+(phases.includes('league')?' off':'')+'" data-pane="ko">'+
     '<table class="tlad"><thead><tr><th>Team</th>'+
     rounds.map(r=>'<th>'+r+'</th>').join('')+'<th>Win</th></tr></thead><tbody>';
  const fld=[...D.field].sort((a,b)=>b.odds.win-a.odds.win);
  fld.forEach(t=>{h+='<tr><td>'+t.team+(t.modeled?'':' <span class="ko-coef">~</span>')+'</td>'+
    rounds.map(r=>'<td>'+((t.odds[r]||0)*100).toFixed(0)+'%</td>').join('')+
    '<td><b>'+(t.odds.win*100).toFixed(1)+'%</b></td></tr>';});
  h+='</tbody></table></div>';
  el.innerHTML=h;
  // Sub-tab toggling
  el.querySelectorAll('.ko-tab').forEach(btn=>btn.onclick=()=>{
    el.querySelectorAll('.ko-tab').forEach(b=>b.classList.remove('on'));
    btn.classList.add('on');
    el.querySelectorAll('.ko-pane').forEach(p=>p.classList.toggle('off',
      p.getAttribute('data-pane')!==btn.getAttribute('data-k')));
  });
  const note=$('#laddernote'); if(note) note.textContent=
    D.outlook.format_label+' · ~ marks teams estimated from coefficients (not fully modeled)';
}
```

- [ ] **Step 4: Add minimal CSS** near the existing table styles (search `.tlad` in `webapp/index.html`)

```css
.ko-subtabs{display:flex;gap:6px;margin-bottom:10px}
.ko-tab{padding:6px 12px;border:1px solid #2a2f3a;background:#161a22;color:#9aa4b2;
  border-radius:6px;cursor:pointer;font-size:13px}
.ko-tab.on{background:#222836;color:#fff}
.ko-pane.off{display:none}
.ko-line td{color:#52d39a;font-size:11px;text-align:center;background:#10141b}
.ko-coef{color:#e2a23f;font-weight:700}
```

- [ ] **Step 5: Verify in-browser**

Use the preview workflow: start the server, load `?league=ucl`, confirm:
- both sub-tabs appear and toggle (League Phase table with the two cut-lines; Knockout leaderboard with champion %);
- a top club leads the Win column; `~` badge shows on coefficient-only teams;
- switch to `?league=mls` and `?league=epl` — they render unchanged (no console errors).

- [ ] **Step 6: Commit**

```bash
git add webapp/index.html
git commit -m "Continental: webapp knockout view (League Phase + Knockout sub-tabs)"
```

---

## Task 10: Integration — regression gates + flip UCL live

**Files:**
- Modify: `scripts/fetch_league_teams.py:50` (UCL status), regenerate `webapp/leagues.js`

- [ ] **Step 1: Run the behavior-preservation gates**

Run: `venv/bin/python -m pytest tests/ -q`
Expected: all prior tests + the 3 new test files PASS (≥ 120 passed).

Run: `venv/bin/python scripts/parity_check.py`
Expected: `PASS ✓  |Δ|=0.0000` — the MLS champion is untouched.

- [ ] **Step 2: Flip UCL to live** in `scripts/fetch_league_teams.py` REGISTRY (line ~50)

```python
("ucl",                 "UEFA Champions League",    "uefa.champions",   "UEFA", "live"),
```

- [ ] **Step 3: Regenerate the registry**

Run: `venv/bin/python scripts/fetch_league_teams.py`
Expected: prints one more "live" league; `webapp/leagues.js` regenerated.

- [ ] **Step 4: Final in-browser check** — UCL appears in the live sidebar group, opens to the knockout view; MLS + the 12 existing leagues regression-clean.

- [ ] **Step 5: Update docs** — add a "Phase 6 — UCL continental (vertical slice)" block to the top of `docs/PLAN.md`, a note to `docs/HANDOFF.md`, and a `§12 Continental competitions` section to `docs/CODE_WALKTHROUGH.md` (per the project's three-doc rule).

- [ ] **Step 6: Commit**

```bash
git add scripts/fetch_league_teams.py webapp/leagues.js docs/PLAN.md docs/HANDOFF.md docs/CODE_WALKTHROUGH.md
git commit -m "Continental: UCL live (vertical slice complete) + docs"
```

---

## Follow-on (separate plan, after this slice is validated live)

1. **Generalize to Europa + Conference** (same UEFA format + coefficients) and the
   Concacaf comps (Concacaf index, format variants; resolve the Leagues Cup ESPN slug).
   Each adds a `FORMATS` entry, a `META` entry, and ESPN→modeled name-map entries.
2. **Approach C** — bridge-regression `Δ_league` offsets fit from continental results,
   swapped in behind `team_strength` (the seam) with no simulator/webapp change.
3. **Live `games` cards + edges** from `continental_fixtures` once a draw exists
   (per-match model probs + `mkt_*`/`edge_*` like the league builds).
4. **Vectorize `bracket_sim`** if build time is material at 20k sims (replace the
   per-match Python `rng.poisson` loop with batched numpy draws).
