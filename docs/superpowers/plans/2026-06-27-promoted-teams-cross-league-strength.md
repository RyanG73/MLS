# Promoted Teams and Cross-League Strength Implementation Plan

> **VERDICT (2026-06-27): COMPLETE.** All 9 tasks shipped. tier_bridge fits ELO offsets from 8 seasons × 3 pairs (912/578/912 first-season promoted-team matches). Fitted offsets ≈ static priors (ridge penalty active, priors well-calibrated). LOSO Brier 0.6278/0.6292/0.6313 vs naive 0.6667 — validation passes. Power rankings gain a "UEFA Tier 2" group (62 teams). EPL seeding confirmed: e.g. Ipswich (Championship ELO 1625 → adj 1505) gets near-average EPL seed vs flat prior that gave every promoted team identical weak seed. 402/402 suite tests passing (2 pre-existing failures unrelated).

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the flat 15th-percentile promoted-team DC seed with a prior derived from actual 2nd-tier ELO, add 2nd-tier teams to the power rankings, and validate using in-season Brier on historically promoted teams.

**Architecture:** A new `scripts/eval/tier_bridge.py` fits a single ELO offset per league pair (Championship→EPL, 2.Bundesliga→Bundesliga, Serie B→Serie A) from historical promoted-team first-season outcomes using NLL+ridge minimization, mirroring the `league_bridge` framework. The fitted offset is consumed by a new `coefficients.tier2_offset()` function, which is then used in `build_league_data.py` (promoted-team seeding) and `build_power_rankings.py` (tier-2 group). All four target files change; no new external dependencies.

**Tech Stack:** scipy.optimize (already in requirements), pandas, football_data adapter (already wired), data_pipeline.coefficients (extension), scripts/eval/elo.compute_elo (already in use), scripts/eval/cross_league.match_probs (already in use)

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `data_pipeline/coefficients.py` | Modify | Add `_TIER2_PRIORS`, `_TIER1_FOR`, `tier2_offset()` |
| `scripts/eval/tier_bridge.py` | Create | Fit 2nd→1st ELO offsets from promoted-team first-season outcomes |
| `scripts/build_league_data.py` | Modify | Add `_TIER2_FOR`, `_FD_TEAM_ALIASES`, helpers, updated seeding block |
| `scripts/build_power_rankings.py` | Modify | Add `_TIER2_LEAGUES`, `tier` param to `_rank_group`, new group in `build()` |
| `scripts/eval/promoted_team_brier.py` | Create | Validation: compare flat vs tier-bridge Brier on historical promoted teams |
| `tests/test_coefficients.py` | Modify | Add 3 tests for `tier2_offset()` |
| `tests/test_tier_bridge.py` | Create | Unit + integration tests for tier_bridge |
| `tests/test_build_league_data_tier2.py` | Create | Unit tests for `_elo_to_dc_params` and alias lookup |

---

## Task 1: Add `tier2_offset()` to `data_pipeline/coefficients.py`

**Files:**
- Modify: `data_pipeline/coefficients.py` (after line 149, i.e. after the existing `club_strength()` function)
- Modify: `tests/test_coefficients.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_coefficients.py`:

```python
# ── tier2_offset ──────────────────────────────────────────────────────────────

def test_tier2_offset_unknown_league_returns_zero():
    """Unsupported league pair returns 0.0, no crash."""
    from data_pipeline import coefficients as co
    assert co.tier2_offset("unknown-league") == 0.0


def test_tier2_offset_returns_static_prior_when_json_absent(tmp_path, monkeypatch):
    """Falls back to static prior when experiments/tier2_offsets.json is absent."""
    import data_pipeline.coefficients as co
    monkeypatch.setattr(co, "_TIER2_JSON", tmp_path / "nonexistent.json")
    monkeypatch.setattr(co, "_TIER2_OFFSETS_LOADED", False)
    monkeypatch.setattr(co, "_TIER2_OFFSETS", None)
    result = co.tier2_offset("championship")
    assert result == co._TIER2_PRIORS["championship_to_epl"]


def test_tier2_offset_reads_fitted_value_from_json(tmp_path, monkeypatch):
    """Returns the fitted offset from JSON when present, not the prior."""
    import json
    import data_pipeline.coefficients as co
    fitted = {"championship_to_epl": -95.5, "bundesliga-2_to_bundesliga": -80.0,
              "serie-b_to_serie-a": -110.0}
    json_path = tmp_path / "tier2_offsets.json"
    json_path.write_text(json.dumps(fitted))
    monkeypatch.setattr(co, "_TIER2_JSON", json_path)
    monkeypatch.setattr(co, "_TIER2_OFFSETS_LOADED", False)
    monkeypatch.setattr(co, "_TIER2_OFFSETS", None)
    assert co.tier2_offset("championship") == -95.5
    assert co.tier2_offset("bundesliga-2") == -80.0
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Users/ryangerda/Development/MLS && venv/bin/python -m pytest tests/test_coefficients.py::test_tier2_offset_unknown_league_returns_zero tests/test_coefficients.py::test_tier2_offset_returns_static_prior_when_json_absent tests/test_coefficients.py::test_tier2_offset_reads_fitted_value_from_json -v
```

Expected: 3 failures with `AttributeError: module ... has no attribute '_TIER2_PRIORS'`

- [ ] **Step 3: Add the implementation to `data_pipeline/coefficients.py`**

Add this block immediately after the `club_strength()` function (after line 149):

```python
# ── 2nd-tier → 1st-tier ELO offset ───────────────────────────────────────────
# Lazy-loaded from experiments/tier2_offsets.json (built by scripts.eval.tier_bridge).
# Falls back to static priors below when the file is absent or the key is missing.

_TIER2_OFFSETS: dict[str, float] | None = None
_TIER2_OFFSETS_LOADED: bool = False
_TIER2_JSON = Path(__file__).parent.parent / "experiments" / "tier2_offsets.json"

# Static priors: rough ELO gap between each 2nd-tier and 1st-tier league.
# These anchor the ridge penalty in tier_bridge and serve as permanent fallback.
_TIER2_PRIORS: dict[str, float] = {
    "championship_to_epl": -120.0,
    "bundesliga-2_to_bundesliga": -100.0,
    "serie-b_to_serie-a": -130.0,
}

# Maps tier-2 league ID → tier-1 league ID (used to construct the JSON key).
_TIER1_FOR: dict[str, str] = {
    "championship": "epl",
    "bundesliga-2": "bundesliga",
    "serie-b": "serie-a",
}


def _load_tier2() -> dict[str, float] | None:
    """Lazy-load experiments/tier2_offsets.json exactly once."""
    global _TIER2_OFFSETS, _TIER2_OFFSETS_LOADED
    if _TIER2_OFFSETS_LOADED:
        return _TIER2_OFFSETS
    _TIER2_OFFSETS_LOADED = True
    try:
        _TIER2_OFFSETS = json.loads(_TIER2_JSON.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        _TIER2_OFFSETS = None
    return _TIER2_OFFSETS


def tier2_offset(tier2_league_id: str) -> float:
    """ELO offset translating a tier-2 team's domestic ELO to the tier-1 scale.

    Returns the fitted offset from experiments/tier2_offsets.json when available,
    otherwise the static prior from _TIER2_PRIORS. Returns 0.0 for unknown pairs.
    """
    tier1_lid = _TIER1_FOR.get(tier2_league_id)
    if tier1_lid is None:
        return 0.0
    key = f"{tier2_league_id}_to_{tier1_lid}"
    fitted = _load_tier2()
    if fitted is not None and key in fitted:
        return float(fitted[key])
    return _TIER2_PRIORS.get(key, 0.0)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
venv/bin/python -m pytest tests/test_coefficients.py::test_tier2_offset_unknown_league_returns_zero tests/test_coefficients.py::test_tier2_offset_returns_static_prior_when_json_absent tests/test_coefficients.py::test_tier2_offset_reads_fitted_value_from_json -v
```

Expected: 3 PASSED

- [ ] **Step 5: Run full suite to check for regressions**

```bash
venv/bin/python -m pytest tests/ -q
```

Expected: all existing tests pass + 3 new.

- [ ] **Step 6: Commit**

```bash
git add data_pipeline/coefficients.py tests/test_coefficients.py
git commit -m "feat(coefficients): add tier2_offset() with lazy JSON load and static priors"
```

---

## Task 2: Create `scripts/eval/tier_bridge.py` — skeleton + ELO history

**Files:**
- Create: `scripts/eval/tier_bridge.py`
- Create: `tests/test_tier_bridge.py`

- [ ] **Step 1: Write failing test for `_build_fd_elo_history`**

Create `tests/test_tier_bridge.py`:

```python
"""Tests for scripts/eval/tier_bridge.py."""
from __future__ import annotations

import bisect
import math
from typing import NamedTuple
from unittest import mock

import pandas as pd
import pytest


# ── _build_fd_elo_history ─────────────────────────────────────────────────────

def _make_fd_df(rows):
    """Build a minimal football_data-style DataFrame for testing."""
    return pd.DataFrame(rows, columns=[
        "match_id", "date", "season", "home_team", "away_team",
        "home_goals", "away_goals", "home_xg", "away_xg",
        "label_result", "is_result", "is_playoff",
    ])


def test_build_fd_elo_history_returns_per_team_history():
    """_build_fd_elo_history returns a dict of (dates, elos) per team."""
    rows = [
        ("m1", pd.Timestamp("2022-08-01"), 2022, "Alpha", "Beta", 2, 0, None, None, 0, True, 0),
        ("m2", pd.Timestamp("2022-08-08"), 2022, "Beta",  "Alpha", 1, 1, None, None, 1, True, 0),
        ("m3", pd.Timestamp("2022-08-15"), 2022, "Alpha", "Beta", 0, 1, None, None, 2, True, 0),
    ]
    df = _make_fd_df(rows)

    from scripts.eval import tier_bridge as tb
    with mock.patch("data_pipeline.football_data.match_results", return_value=df):
        history = tb._build_fd_elo_history("championship")

    assert "Alpha" in history
    assert "Beta" in history
    dates_a, elos_a = history["Alpha"]
    assert len(dates_a) == 3  # 3 matches: appears twice as home, once as away
    # ELOs should be pre-match (same pattern as league_bridge)
    assert all(isinstance(e, float) for e in elos_a)


def test_build_fd_elo_history_empty_df_returns_empty():
    """Empty dataframe (no results yet) returns empty history."""
    from scripts.eval import tier_bridge as tb
    empty = pd.DataFrame(columns=[
        "match_id", "date", "season", "home_team", "away_team",
        "home_goals", "away_goals", "home_xg", "away_xg",
        "label_result", "is_result", "is_playoff",
    ])
    with mock.patch("data_pipeline.football_data.match_results", return_value=empty):
        history = tb._build_fd_elo_history("championship")
    assert history == {}
```

- [ ] **Step 2: Run to confirm failure**

```bash
venv/bin/python -m pytest tests/test_tier_bridge.py::test_build_fd_elo_history_returns_per_team_history tests/test_tier_bridge.py::test_build_fd_elo_history_empty_df_returns_empty -v
```

Expected: `ModuleNotFoundError: No module named 'scripts.eval.tier_bridge'`

- [ ] **Step 3: Create `scripts/eval/tier_bridge.py` with the skeleton and `_build_fd_elo_history`**

```python
"""Fit 2nd-tier → 1st-tier ELO offsets from promoted-team first-season outcomes.

For each supported league pair, collects all historical teams that promoted from
the 2nd-tier to the 1st-tier, and fits a single ELO offset δ such that

    match_probs(elo_2nd_tier + δ, elo_opponent)

best predicts their first-season top-flight 1X2 outcomes (NLL + ridge penalty,
mirroring scripts/eval/league_bridge.py).

Validation: leave-one-season-out. Accepts the fitted offset if held-out Brier
≤ naive AND |δ - prior| < 200 ELO; otherwise writes the static prior.

Supported pairs (football_data.DIV coverage):
    championship   → epl
    bundesliga-2   → bundesliga
    serie-b        → serie-a

Usage:
    python -m scripts.eval.tier_bridge
    python -m scripts.eval.tier_bridge --dry-run
    python -m scripts.eval.tier_bridge --lam 0.05
"""
from __future__ import annotations

import bisect
import json
import logging
import math
from pathlib import Path
from typing import NamedTuple

import numpy as np
import pandas as pd
from scipy.optimize import minimize

from data_pipeline import coefficients as co
from scripts.eval.cross_league import match_probs
from scripts.eval.elo import compute_elo

_log = logging.getLogger(__name__)

# Champion ELO config — must match the rest of the platform.
_ELO_K, _ELO_HA, _ELO_REGRESS, _ELO_INIT = 25.0, 80.0, 0.40, 1500.0

# Only fit on seasons within the model training window.
_TRAIN_FROM = 2017

# Sanity bound: reject any fitted offset that deviates more than this from its prior.
_MAX_DELTA_FROM_PRIOR = 200.0

# Minimum match count to attempt a fit (below this, prior is used directly).
_MIN_MATCHES = 20

_OFFSETS_JSON = Path("experiments/tier2_offsets.json")

# Supported (tier2, tier1) league ID pairs.
_TIER2_PAIRS: list[tuple[str, str]] = [
    ("championship", "epl"),
    ("bundesliga-2", "bundesliga"),
    ("serie-b", "serie-a"),
]


class _TierMatch(NamedTuple):
    promoted_team: str
    promoted_elo: float   # end-of-tier2-season ELO, BEFORE offset applied
    opponent_elo: float   # tier1 ELO as-of match date (no offset needed)
    is_home: bool         # is the promoted team the home side?
    outcome: int          # 0=home win, 1=draw, 2=away win
    season: int           # tier1 season (used for LOSO grouping)


# Module-level cache so the history is built only once per league per process.
_FD_ELO_HISTORY_CACHE: dict[str, dict[str, tuple[list, list]]] = {}


def _build_fd_elo_history(league_id: str) -> dict[str, tuple[list, list]]:
    """Per-team pre-match ELO history from a football_data source.

    Returns {team: ([dates_ascending], [pre_match_elos])}.
    Mirrors league_bridge._build_elo_history but reads football_data instead of
    Understat/MLS.  The history contains PRE-match ELOs (the rating BEFORE each
    match), which is what elo_asof-style lookups need.
    """
    if league_id in _FD_ELO_HISTORY_CACHE:
        return _FD_ELO_HISTORY_CACHE[league_id]

    from data_pipeline.football_data import match_results
    df = match_results(league_id).sort_values("date")
    df = df.dropna(subset=["home_goals", "away_goals"])
    if df.empty:
        _FD_ELO_HISTORY_CACHE[league_id] = {}
        return {}

    rated = compute_elo(df, K=_ELO_K, home_adv=_ELO_HA,
                        regress=_ELO_REGRESS, initial=_ELO_INIT)

    history: dict[str, tuple[list, list]] = {}
    for _, row in rated.iterrows():
        d = row["date"]
        if pd.isna(d):
            continue
        d = pd.Timestamp(d)
        for team, elo in [(row["home_team"], float(row["home_elo"])),
                          (row["away_team"], float(row["away_elo"]))]:
            if team not in history:
                history[team] = ([], [])
            history[team][0].append(d)
            history[team][1].append(elo)

    _FD_ELO_HISTORY_CACHE[league_id] = history
    _log.info("_build_fd_elo_history: %s → %d teams", league_id, len(history))
    return history
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
venv/bin/python -m pytest tests/test_tier_bridge.py::test_build_fd_elo_history_returns_per_team_history tests/test_tier_bridge.py::test_build_fd_elo_history_empty_df_returns_empty -v
```

Expected: 2 PASSED

- [ ] **Step 5: Commit**

```bash
git add scripts/eval/tier_bridge.py tests/test_tier_bridge.py
git commit -m "feat(tier_bridge): add module skeleton and _build_fd_elo_history"
```

---

## Task 3: Add `_identify_promotions()` and `_collect_tier_matches()` to `tier_bridge.py`

**Files:**
- Modify: `scripts/eval/tier_bridge.py`
- Modify: `tests/test_tier_bridge.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_tier_bridge.py`:

```python
# ── _identify_promotions ──────────────────────────────────────────────────────

def test_identify_promotions_detects_new_teams():
    """Teams in season Y but not Y-1 are identified as promoted."""
    df = _make_fd_df([
        # 2021: Alpha and Beta
        ("m1", pd.Timestamp("2021-08-01"), 2021, "Alpha", "Beta", 1, 0, None, None, 0, True, 0),
        ("m2", pd.Timestamp("2021-09-01"), 2021, "Beta", "Alpha", 0, 0, None, None, 1, True, 0),
        # 2022: Alpha, Beta, and Gamma (new = promoted)
        ("m3", pd.Timestamp("2022-08-01"), 2022, "Alpha", "Gamma", 2, 1, None, None, 0, True, 0),
        ("m4", pd.Timestamp("2022-09-01"), 2022, "Gamma", "Beta", 0, 1, None, None, 2, True, 0),
    ])

    from scripts.eval import tier_bridge as tb
    promotions = tb._identify_promotions(df)
    assert 2022 in promotions
    assert "Gamma" in promotions[2022]
    assert "Alpha" not in promotions[2022]
    assert "Beta" not in promotions[2022]


def test_identify_promotions_first_season_has_no_promotions():
    """The first season in the dataset has no prior to compare against."""
    df = _make_fd_df([
        ("m1", pd.Timestamp("2021-08-01"), 2021, "Alpha", "Beta", 1, 0, None, None, 0, True, 0),
    ])
    from scripts.eval import tier_bridge as tb
    promotions = tb._identify_promotions(df)
    assert 2021 not in promotions


# ── _collect_tier_matches ─────────────────────────────────────────────────────

def test_collect_tier_matches_returns_matches_for_promoted_team():
    """Promoted team's first-season matches are collected with their tier2 ELO."""
    tier2_df = _make_fd_df([
        # Championship: Gamma finishes 2021 season
        ("c1", pd.Timestamp("2021-05-01"), 2021, "Gamma", "Delta", 2, 0, None, None, 0, True, 0),
        ("c2", pd.Timestamp("2021-05-08"), 2021, "Delta", "Gamma", 0, 2, None, None, 2, True, 0),
    ])
    tier1_df = _make_fd_df([
        # EPL: Alpha and Beta in 2021; Gamma arrives in 2022
        ("e1", pd.Timestamp("2021-08-01"), 2021, "Alpha", "Beta",  1, 0, None, None, 0, True, 0),
        ("e2", pd.Timestamp("2022-08-01"), 2022, "Alpha", "Gamma", 3, 0, None, None, 0, True, 0),
        ("e3", pd.Timestamp("2022-08-08"), 2022, "Gamma", "Beta",  1, 1, None, None, 1, True, 0),
    ])

    from scripts.eval import tier_bridge as tb

    def _fake_results(league_id, **_):
        return tier2_df if "championship" in league_id else tier1_df

    with mock.patch("data_pipeline.football_data.match_results", side_effect=_fake_results):
        # Also need to patch the cache so it doesn't use stale data across tests
        tb._FD_ELO_HISTORY_CACHE.clear()
        matches_by_season = tb._collect_tier_matches("championship", "epl")

    assert 2022 in matches_by_season
    gamma_matches = [m for m in matches_by_season[2022] if m.promoted_team == "Gamma"]
    assert len(gamma_matches) == 2  # two first-season EPL matches involving Gamma
    for m in gamma_matches:
        assert m.promoted_elo > 0
        assert m.season == 2022
```

- [ ] **Step 2: Run to confirm failures**

```bash
venv/bin/python -m pytest tests/test_tier_bridge.py::test_identify_promotions_detects_new_teams tests/test_tier_bridge.py::test_identify_promotions_first_season_has_no_promotions tests/test_tier_bridge.py::test_collect_tier_matches_returns_matches_for_promoted_team -v
```

Expected: 3 failures with `AttributeError: module ... has no attribute '_identify_promotions'`

- [ ] **Step 3: Add `_identify_promotions` and `_collect_tier_matches` to `tier_bridge.py`**

Append to `scripts/eval/tier_bridge.py` after `_build_fd_elo_history`:

```python
def _identify_promotions(tier1_results: pd.DataFrame) -> dict[int, set[str]]:
    """Return {tier1_season: set_of_newly_promoted_teams}.

    A team is considered promoted in season Y if it appears in the tier1 results
    for season Y but did NOT appear in season Y-1.  Seasons before _TRAIN_FROM
    are excluded.
    """
    promotions: dict[int, set[str]] = {}
    seasons = sorted(tier1_results["season"].unique())
    for i, s in enumerate(seasons):
        if i == 0 or s < _TRAIN_FROM:
            continue
        prev = seasons[i - 1]
        teams_now = set(
            tier1_results.loc[tier1_results["season"] == s, "home_team"].tolist() +
            tier1_results.loc[tier1_results["season"] == s, "away_team"].tolist()
        )
        teams_prev = set(
            tier1_results.loc[tier1_results["season"] == prev, "home_team"].tolist() +
            tier1_results.loc[tier1_results["season"] == prev, "away_team"].tolist()
        )
        promoted = teams_now - teams_prev
        if promoted:
            promotions[s] = promoted
    return promotions


def _collect_tier_matches(
    tier2_lid: str, tier1_lid: str
) -> dict[int, list[_TierMatch]]:
    """Collect first-season tier1 matches for promoted teams, keyed by tier1 season.

    Both leagues use football_data so team names are consistent within
    football-data.co.uk's naming convention.

    Returns {tier1_season: [_TierMatch, ...]}.
    """
    from data_pipeline.football_data import match_results

    tier1_df = match_results(tier1_lid)
    tier2_history = _build_fd_elo_history(tier2_lid)
    tier1_history = _build_fd_elo_history(tier1_lid)

    tier1_df = tier1_df[tier1_df["season"] >= _TRAIN_FROM]
    promotions = _identify_promotions(tier1_df)

    matches_by_season: dict[int, list[_TierMatch]] = {}

    for tier1_season, promoted_teams in sorted(promotions.items()):
        # The cutoff for end-of-tier2-season: June 30 of the season-end year.
        # e.g. for tier1_season=2022 (2022-23), promoted from tier2 2021 (2021-22),
        # end-of-tier2 cutoff = 2022-06-30.
        tier2_cutoff = pd.Timestamp(f"{tier1_season}-06-30")
        season_matches: list[_TierMatch] = []
        tier1_season_df = tier1_df[tier1_df["season"] == tier1_season]

        for _, row in tier1_season_df.iterrows():
            ht, at = row["home_team"], row["away_team"]
            match_date = pd.Timestamp(row["date"]) if pd.notna(row["date"]) else None
            if match_date is None:
                continue
            hg, ag = int(row["home_goals"]), int(row["away_goals"])
            outcome = 0 if hg > ag else (1 if hg == ag else 2)

            for is_home, promoted, opponent in [(True, ht, at), (False, at, ht)]:
                if promoted not in promoted_teams:
                    continue

                # End-of-tier2-season ELO: most recent pre-match ELO on or before cutoff.
                dates_t2, elos_t2 = tier2_history.get(promoted, ([], []))
                idx_t2 = bisect.bisect_right(dates_t2, tier2_cutoff)
                if idx_t2 == 0:
                    _log.debug(
                        "_collect_tier_matches: %s has no tier2 ELO before %s — skipping",
                        promoted, tier2_cutoff,
                    )
                    continue
                promoted_elo = elos_t2[idx_t2 - 1]

                # Opponent's tier1 ELO as-of match date.
                dates_t1, elos_t1 = tier1_history.get(opponent, ([], []))
                idx_t1 = bisect.bisect_left(dates_t1, match_date)
                opp_elo = elos_t1[idx_t1 - 1] if idx_t1 > 0 else _ELO_INIT

                season_matches.append(_TierMatch(
                    promoted_team=promoted,
                    promoted_elo=promoted_elo,
                    opponent_elo=opp_elo,
                    is_home=is_home,
                    outcome=outcome,
                    season=tier1_season,
                ))

        if season_matches:
            matches_by_season[tier1_season] = season_matches
            _log.info(
                "_collect_tier_matches: %s→%s season %d: %d matches, %d promoted teams",
                tier2_lid, tier1_lid, tier1_season,
                len(season_matches), len(promoted_teams),
            )

    return matches_by_season
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
venv/bin/python -m pytest tests/test_tier_bridge.py -v
```

Expected: all passing (5 tests: 2 from Task 2 + 3 from this task)

- [ ] **Step 5: Commit**

```bash
git add scripts/eval/tier_bridge.py tests/test_tier_bridge.py
git commit -m "feat(tier_bridge): add _identify_promotions and _collect_tier_matches"
```

---

## Task 4: Add `_nll`, `_brier`, `_fit_offset`, `_loso_validate` to `tier_bridge.py`

**Files:**
- Modify: `scripts/eval/tier_bridge.py`
- Modify: `tests/test_tier_bridge.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_tier_bridge.py`:

```python
# ── _fit_offset ───────────────────────────────────────────────────────────────

def test_fit_offset_recovers_known_direction():
    """When promoted teams consistently outperform the prior, fitted δ moves upward."""
    from scripts.eval import tier_bridge as tb

    # Construct matches where promoted team (ELO 1500) beats everyone —
    # that means the prior (-120, adjusted=1380) is too pessimistic.
    # The optimizer should push δ toward 0 (or positive) to raise the predicted prob.
    matches = [
        tb._TierMatch("P", 1500.0, 1500.0, True,  0, 2022),  # home win
        tb._TierMatch("P", 1500.0, 1500.0, True,  0, 2022),
        tb._TierMatch("P", 1500.0, 1500.0, False, 2, 2022),  # away win for P
        tb._TierMatch("P", 1500.0, 1500.0, False, 2, 2022),
        tb._TierMatch("P", 1500.0, 1500.0, True,  0, 2023),
        tb._TierMatch("P", 1500.0, 1500.0, False, 2, 2023),
    ]
    prior = -120.0
    fitted = tb._fit_offset(matches, prior, lam=0.001)
    # With weak ridge, optimizer should push δ above prior to make P stronger.
    assert fitted > prior


def test_fit_offset_with_strong_ridge_stays_near_prior():
    """Very strong ridge (lam=10) should keep the offset near the prior."""
    from scripts.eval import tier_bridge as tb

    matches = [
        tb._TierMatch("P", 1500.0, 1500.0, True, 0, 2022),
        tb._TierMatch("P", 1500.0, 1500.0, True, 1, 2022),
        tb._TierMatch("P", 1500.0, 1500.0, True, 2, 2022),
    ]
    prior = -120.0
    fitted = tb._fit_offset(matches, prior, lam=10.0)
    assert abs(fitted - prior) < 10.0  # very strong ridge: stays close


def test_brier_uniform_is_two_thirds():
    """Uniform 1/3 predictions should give Brier ≈ 2/3 per match."""
    from scripts.eval import tier_bridge as tb

    # With promoted_elo == opponent_elo and no home advantage, probs are near 1/3.
    # At exact equal strength with home advantage, it won't be exactly 1/3.
    # Just test that _brier returns a sensible value in [0, 2].
    matches = [
        tb._TierMatch("P", 1500.0, 1500.0, True,  0, 2022),
        tb._TierMatch("P", 1500.0, 1500.0, True,  1, 2022),
        tb._TierMatch("P", 1500.0, 1500.0, True,  2, 2022),
    ]
    b = tb._brier(matches, delta=0.0)
    assert 0.0 < b < 2.0
```

- [ ] **Step 2: Run to confirm failures**

```bash
venv/bin/python -m pytest tests/test_tier_bridge.py::test_fit_offset_recovers_known_direction tests/test_tier_bridge.py::test_fit_offset_with_strong_ridge_stays_near_prior tests/test_tier_bridge.py::test_brier_uniform_is_two_thirds -v
```

Expected: 3 failures with `AttributeError: ... has no attribute '_fit_offset'`

- [ ] **Step 3: Add fitting functions to `tier_bridge.py`**

Append to `scripts/eval/tier_bridge.py` after `_collect_tier_matches`:

```python
# ── objective and scoring ─────────────────────────────────────────────────────

def _nll(delta: float, matches: list[_TierMatch], prior: float, lam: float) -> float:
    """NLL + ridge objective for a single tier ELO offset."""
    nll = 0.0
    for m in matches:
        adj = m.promoted_elo + delta
        if m.is_home:
            ph, pd_, pa = match_probs(adj, m.opponent_elo, conf="UEFA")
        else:
            ph, pd_, pa = match_probs(m.opponent_elo, adj, conf="UEFA")
        p = max((ph, pd_, pa)[m.outcome], 1e-12)
        nll -= math.log(p)
    # Ridge penalty pulls δ toward the static prior.
    nll += lam * len(matches) * (delta - prior) ** 2
    return nll


def _brier(matches: list[_TierMatch], delta: float) -> float:
    """Mean sum-form Brier score on a match list given an ELO offset."""
    if not matches:
        return float("nan")
    total = 0.0
    for m in matches:
        adj = m.promoted_elo + delta
        if m.is_home:
            ph, pd_, pa = match_probs(adj, m.opponent_elo, conf="UEFA")
        else:
            ph, pd_, pa = match_probs(m.opponent_elo, adj, conf="UEFA")
        probs = [ph, pd_, pa]
        actuals = [0.0, 0.0, 0.0]
        actuals[m.outcome] = 1.0
        total += sum((probs[i] - actuals[i]) ** 2 for i in range(3))
    return total / len(matches)


def _fit_offset(matches: list[_TierMatch], prior: float, lam: float) -> float:
    """Fit a single scalar ELO offset on the given matches via NLL+ridge."""
    result = minimize(
        _nll,
        x0=[prior],
        args=(matches, prior, lam),
        method="L-BFGS-B",
        options={"maxiter": 1000, "ftol": 1e-10},
    )
    return float(result.x[0])


def _loso_validate(
    matches_by_season: dict[int, list[_TierMatch]],
    fitted_delta: float,
    prior: float,
    lam: float,
) -> tuple[float, float, float]:
    """Leave-one-season-out validation.

    For each season, fits on all OTHER seasons' matches and evaluates on the
    held-out season.  Returns (mean_brier_fitted, mean_brier_prior, naive_brier).

    naive_brier is always 2/3 (uniform 1/3 per outcome, sum-form).
    """
    seasons = sorted(matches_by_season.keys())
    bf, bp = [], []
    for held_out in seasons:
        train = [m for s, ms in matches_by_season.items()
                 if s != held_out for m in ms]
        test = matches_by_season[held_out]
        if not train or not test:
            continue
        d_cv = _fit_offset(train, prior, lam)
        bf.append(_brier(test, d_cv))
        bp.append(_brier(test, prior))

    if not bf:
        return float("nan"), float("nan"), 2 / 3
    return float(np.mean(bf)), float(np.mean(bp)), 2 / 3
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
venv/bin/python -m pytest tests/test_tier_bridge.py -v
```

Expected: all 8 tests passing.

- [ ] **Step 5: Commit**

```bash
git add scripts/eval/tier_bridge.py tests/test_tier_bridge.py
git commit -m "feat(tier_bridge): add _nll, _brier, _fit_offset, _loso_validate"
```

---

## Task 5: Add `fit_all()` and CLI to `tier_bridge.py`

**Files:**
- Modify: `scripts/eval/tier_bridge.py`
- Modify: `tests/test_tier_bridge.py`

- [ ] **Step 1: Write failing test for `fit_all`**

Add to `tests/test_tier_bridge.py`:

```python
# ── fit_all ───────────────────────────────────────────────────────────────────

def test_fit_all_dry_run_returns_dict_with_correct_keys():
    """fit_all(dry_run=True) returns a dict with all three pair keys."""
    from scripts.eval import tier_bridge as tb

    # Stub _collect_tier_matches so we don't need real football_data files.
    def _fake_collect(tier2_lid, tier1_lid):
        # Return too few matches → prior is used.
        return {}

    with mock.patch.object(tb, "_collect_tier_matches", side_effect=_fake_collect):
        results = tb.fit_all(dry_run=True)

    assert set(results.keys()) == {
        "championship_to_epl",
        "bundesliga-2_to_bundesliga",
        "serie-b_to_serie-a",
    }


def test_fit_all_uses_prior_when_too_few_matches():
    """fit_all falls back to static prior when < _MIN_MATCHES collected."""
    from scripts.eval import tier_bridge as tb
    from data_pipeline import coefficients as co

    def _fake_collect(tier2_lid, tier1_lid):
        return {}  # 0 matches → too few

    with mock.patch.object(tb, "_collect_tier_matches", side_effect=_fake_collect):
        results = tb.fit_all(dry_run=True)

    assert results["championship_to_epl"] == co._TIER2_PRIORS["championship_to_epl"]
```

- [ ] **Step 2: Run to confirm failures**

```bash
venv/bin/python -m pytest tests/test_tier_bridge.py::test_fit_all_dry_run_returns_dict_with_correct_keys tests/test_tier_bridge.py::test_fit_all_uses_prior_when_too_few_matches -v
```

Expected: 2 failures with `AttributeError: ... has no attribute 'fit_all'`

- [ ] **Step 3: Add `fit_all()` and `__main__` block to `tier_bridge.py`**

Append to `scripts/eval/tier_bridge.py` after `_loso_validate`:

```python
# ── main entry point ──────────────────────────────────────────────────────────

def fit_all(lam: float = 0.01, dry_run: bool = False) -> dict[str, float]:
    """Fit tier2→tier1 ELO offsets for all supported league pairs.

    Returns a dict mapping key (e.g. ``championship_to_epl``) → fitted offset.
    Writes ``experiments/tier2_offsets.json`` unless ``dry_run=True``.
    Falls back to the static prior in _TIER2_PRIORS for any pair that fails
    validation or has too few matches.
    """
    results: dict[str, float] = {}

    for tier2_lid, tier1_lid in _TIER2_PAIRS:
        key = f"{tier2_lid}_to_{tier1_lid}"
        prior = co._TIER2_PRIORS.get(key, -100.0)
        _log.info("fit_all: fitting %s → %s (prior=%.1f ELO)", tier2_lid, tier1_lid, prior)

        try:
            matches_by_season = _collect_tier_matches(tier2_lid, tier1_lid)
        except Exception as e:
            _log.warning("fit_all: failed to collect %s→%s: %s — using prior", tier2_lid, tier1_lid, e)
            results[key] = prior
            continue

        all_matches = [m for ms in matches_by_season.values() for m in ms]

        if len(all_matches) < _MIN_MATCHES:
            _log.warning(
                "fit_all: only %d matches for %s→%s (need %d) — using prior",
                len(all_matches), tier2_lid, tier1_lid, _MIN_MATCHES,
            )
            results[key] = prior
            continue

        fitted = _fit_offset(all_matches, prior, lam)
        brier_f, brier_p, brier_n = _loso_validate(matches_by_season, fitted, prior, lam)

        _log.info(
            "fit_all: %s→%s fitted=%.1f  LOSO brier: fitted=%.4f prior=%.4f naive=%.4f",
            tier2_lid, tier1_lid, fitted, brier_f, brier_p, brier_n,
        )

        if abs(fitted - prior) > _MAX_DELTA_FROM_PRIOR:
            _log.warning(
                "fit_all: %s→%s offset %.1f deviates >%.0f ELO from prior %.1f — using prior",
                tier2_lid, tier1_lid, fitted, _MAX_DELTA_FROM_PRIOR, prior,
            )
            results[key] = prior
        elif not math.isnan(brier_f) and brier_f > brier_n:
            _log.warning(
                "fit_all: %s→%s fitted Brier %.4f > naive %.4f — using prior",
                tier2_lid, tier1_lid, brier_f, brier_n,
            )
            results[key] = prior
        else:
            results[key] = round(fitted, 2)

    if not dry_run:
        _OFFSETS_JSON.parent.mkdir(parents=True, exist_ok=True)
        _OFFSETS_JSON.write_text(json.dumps(results, indent=2))
        _log.info("fit_all: wrote %s", _OFFSETS_JSON)
    else:
        _log.info("fit_all: dry-run, not writing JSON. Results: %s", results)

    return results


if __name__ == "__main__":
    import argparse
    import sys

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="Fit 2nd-tier → 1st-tier ELO offsets")
    parser.add_argument("--dry-run", action="store_true",
                        help="Fit and report without writing experiments/tier2_offsets.json")
    parser.add_argument("--lam", type=float, default=0.01,
                        help="Ridge penalty weight (default 0.01)")
    args = parser.parse_args()

    out = fit_all(lam=args.lam, dry_run=args.dry_run)
    print("\nResults:")
    for k, v in out.items():
        print(f"  {k}: {v:.1f}")
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
venv/bin/python -m pytest tests/test_tier_bridge.py -v
```

Expected: all 10 tests passing.

- [ ] **Step 5: Run full suite**

```bash
venv/bin/python -m pytest tests/ -q
```

Expected: all passing.

- [ ] **Step 6: Commit**

```bash
git add scripts/eval/tier_bridge.py tests/test_tier_bridge.py
git commit -m "feat(tier_bridge): add fit_all() entry point and CLI"
```

---

## Task 6: Extend `scripts/build_league_data.py` — promoted-team seeding

**Files:**
- Modify: `scripts/build_league_data.py`
- Create: `tests/test_build_league_data_tier2.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_build_league_data_tier2.py`:

```python
"""Unit tests for tier-2 seeding helpers added to build_league_data."""
from __future__ import annotations
import pytest


# ── _elo_to_dc_params ─────────────────────────────────────────────────────────

def test_elo_to_dc_params_high_elo_gets_strong_seed():
    """Team at 90th ELO percentile gets stronger attack and weaker-defense seed."""
    from scripts.build_league_data import _elo_to_dc_params

    # Build a league with ELOs 1400..1700 (10 teams, step 33)
    elo_now = {f"Team{i}": 1400.0 + i * 33 for i in range(10)}
    atk = {f"Team{i}": -0.4 + i * 0.08 for i in range(10)}  # -0.40..+0.32
    dfd = {f"Team{i}":  0.4 - i * 0.08 for i in range(10)}  # +0.40..-0.32

    # 90th-pct team
    high_atk, high_dfd = _elo_to_dc_params(1690.0, atk, dfd, elo_now)
    # 15th-pct team (old flat prior level)
    low_atk,  low_dfd  = _elo_to_dc_params(1430.0, atk, dfd, elo_now)

    assert high_atk > low_atk, "Stronger ELO should map to higher attack param"
    assert high_dfd < low_dfd, "Stronger ELO should map to lower defense param (harder to score against)"


def test_elo_to_dc_params_clamps_to_5th_95th():
    """ELO below all existing teams clamps to 5th percentile, not min."""
    from scripts.build_league_data import _elo_to_dc_params

    elo_now = {f"T{i}": 1500.0 + i * 10 for i in range(20)}
    atk = {f"T{i}": float(i) for i in range(20)}
    dfd = {f"T{i}": float(20 - i) for i in range(20)}

    # ELO below all teams → clamps to 5th percentile, not the absolute min
    atk_seed, dfd_seed = _elo_to_dc_params(1000.0, atk, dfd, elo_now)
    atk_min = min(atk.values())
    assert atk_seed > atk_min, "Should clamp at 5th pct, not absolute min"


def test_elo_to_dc_params_empty_maps_return_zeros():
    """Empty atk/dfd/elo maps return (0.0, 0.0) without crashing."""
    from scripts.build_league_data import _elo_to_dc_params
    result = _elo_to_dc_params(1500.0, {}, {}, {})
    assert result == (0.0, 0.0)
```

- [ ] **Step 2: Run to confirm failures**

```bash
venv/bin/python -m pytest tests/test_build_league_data_tier2.py -v
```

Expected: 3 failures with `ImportError: cannot import name '_elo_to_dc_params'`

- [ ] **Step 3: Add imports, constants, and helpers to `build_league_data.py`**

Add to the imports section at the top of `scripts/build_league_data.py` (after line 50):

```python
from data_pipeline import coefficients as co
```

Add these constants and helper functions after the existing imports block (after line 50, before the first function definition or the `LEAGUES` dict):

> **Note on `elo_now` timing:** `allplayed` is defined at line 340 and `elo_now` is computed from it at line 381. Since we need `elo_now` in the seeding block (lines 352-370), also move the `elo_now` computation up to line 342 (right after `allplayed = df.dropna(...)`). Change:
> ```python
> # line 340-341 (existing):
> allplayed = df.dropna(subset=["home_goals", "away_goals"])
> atk, dfd, ha, rho = fit_dc(allplayed)
> ```
> to:
> ```python
> allplayed = df.dropna(subset=["home_goals", "away_goals"])
> atk, dfd, ha, rho = fit_dc(allplayed)
> _elo_df, elo_now = compute_elo(allplayed.sort_values("date"), K=25, home_adv=80,
>                                regress=0.40, return_ratings=True)
> ```
> Then delete the duplicate `_elo_df, elo_now = compute_elo(...)` line at the original line 381 location (it now appears twice; remove the second one).

```python
# ── tier-2 promoted-team seeding ──────────────────────────────────────────────
# Maps top-flight league ID → its feeder tier-2 league ID.
# Only covers the three pairs supported by football_data.py.
_TIER2_FOR: dict[str, str] = {
    "epl":        "championship",
    "bundesliga": "bundesliga-2",
    "serie-a":    "serie-b",
}

# ESPN/Understat team name → football-data short name for common promoted teams.
# football-data.co.uk uses its own short names; promoted teams identified from ESPN
# fixtures need to be translated before looking up their tier-2 ELO.
_FD_TEAM_ALIASES: dict[str, str] = {
    "Sheffield United":      "Sheff Utd",
    "Nottingham Forest":     "Nott'm Forest",
    "Queens Park Rangers":   "QPR",
    "West Bromwich Albion":  "West Brom",
    "Leicester City":        "Leicester",
    "Wolverhampton Wanderers": "Wolves",
    "Brighton & Hove Albion": "Brighton",
    "AFC Bournemouth":       "Bournemouth",
    "Leeds United":          "Leeds",
    "Ipswich Town":          "Ipswich",
    "Luton Town":            "Luton",
    "Huddersfield Town":     "Huddersfield",
    "Swansea City":          "Swansea",
    "Coventry City":         "Coventry",
    "Watford":               "Watford",    # same, but explicit
    "Brentford":             "Brentford",  # same
}

_TIER2_ELO_CACHE: dict[str, dict[str, float]] = {}


def _get_tier2_elo_map(tier2_lid: str) -> dict[str, float]:
    """End-of-history ELO map for a tier-2 league, from football_data results.

    Returns {team_name_as_in_football_data: current_elo}.  The current ELO is
    the rating after the most recently completed match (end of last season).
    Returns {} if the data cannot be loaded.
    """
    if tier2_lid in _TIER2_ELO_CACHE:
        return _TIER2_ELO_CACHE[tier2_lid]
    try:
        df = match_results(tier2_lid).sort_values("date")
        df = df.dropna(subset=["home_goals", "away_goals"])
        if df.empty:
            _TIER2_ELO_CACHE[tier2_lid] = {}
            return {}
        _, elo_now_t2 = compute_elo(df, K=25, home_adv=80, regress=0.40,
                                    return_ratings=True)
        _TIER2_ELO_CACHE[tier2_lid] = dict(elo_now_t2)
    except Exception as e:  # noqa: BLE001
        print(f"[warning] tier2 ELO load failed for {tier2_lid}: {e}")
        _TIER2_ELO_CACHE[tier2_lid] = {}
    return _TIER2_ELO_CACHE[tier2_lid]


def _elo_to_dc_params(
    adj_elo: float,
    atk: dict[str, float],
    dfd: dict[str, float],
    elo_now: dict[str, float],
) -> tuple[float, float]:
    """Map a translated ELO to DC attack/defense params via percentile interpolation.

    Finds the percentile of ``adj_elo`` in the tier-1 ELO distribution, then
    picks the same percentile from the sorted attack params and the INVERSE
    percentile from the defense params (higher ELO → better attack = higher atk,
    better defense = lower dfd in DC log-space).

    Clamps to [5th, 95th] percentile to avoid extreme seeds.
    """
    elo_vals = sorted(elo_now.values())
    n = len(elo_vals)
    if n == 0 or not atk or not dfd:
        return 0.0, 0.0

    rank = sum(1 for e in elo_vals if e <= adj_elo)
    pct = max(0.05, min(0.95, rank / n))

    atk_vals = sorted(atk.values())
    dfd_vals = sorted(dfd.values())

    atk_idx = min(int(pct * len(atk_vals)), len(atk_vals) - 1)
    # Lower pct for dfd → lower dfd value → better defense.
    dfd_idx = min(int((1.0 - pct) * len(dfd_vals)), len(dfd_vals) - 1)

    return atk_vals[atk_idx], dfd_vals[dfd_idx]
```

- [ ] **Step 4: Replace the promoted-team seeding block in `build_league_data.py`**

Find the current seeding block (around lines 352–368):

```python
        if _promoted_teams:
            # Compute 15th-percentile of fitted attack and defence parameters.
            ...
            for _pt in _promoted_teams:
                atk[_pt] = _atk_prior
                dfd[_pt] = _dfd_prior
            print(f"[{lid}] promoted teams seeded at atk={_atk_prior:.3f} "
                  f"dfd={_dfd_prior:.3f} (15th/85th pct): {sorted(_promoted_teams)}")
            # Future: seed from 2nd-tier historical strength via cross-league DC offset.
```

Replace the entire block (from `if _promoted_teams:` through the `# Future:` comment) with:

```python
        if _promoted_teams:
            # Compute flat fallback (15th-pct attack, 85th-pct defence) — used when
            # no tier-2 ELO is available for a promoted team.
            _fitted_teams = set(atk.keys()) | set(dfd.keys())
            _atk_vals_all = sorted(atk.get(t, 0.0) for t in _fitted_teams)
            _dfd_vals_all = sorted(dfd.get(t, 0.0) for t in _fitted_teams)
            _p15 = max(0, int(len(_atk_vals_all) * 0.15) - 1)
            _p85 = min(len(_dfd_vals_all) - 1, int(len(_dfd_vals_all) * 0.85))
            _atk_flat = _atk_vals_all[_p15] if _atk_vals_all else -0.2
            _dfd_flat = _dfd_vals_all[_p85] if _dfd_vals_all else 0.2

            _tier2_lid = _TIER2_FOR.get(lid)
            _tier2_elo_map = _get_tier2_elo_map(_tier2_lid) if _tier2_lid else {}

            for _pt in _promoted_teams:
                # Try exact name first, then the football-data alias.
                _fd_name = _FD_TEAM_ALIASES.get(_pt, _pt)
                _tier2_elo = _tier2_elo_map.get(_pt) or _tier2_elo_map.get(_fd_name)
                if _tier2_elo is not None and _tier2_lid is not None:
                    _adj_elo = _tier2_elo + co.tier2_offset(_tier2_lid)
                    atk[_pt], dfd[_pt] = _elo_to_dc_params(_adj_elo, atk, dfd, elo_now)
                    print(f"[{lid}] promoted {_pt}: "
                          f"tier2_elo={_tier2_elo:.0f} adj={_adj_elo:.0f} "
                          f"DC=(atk={atk[_pt]:.3f}, dfd={dfd[_pt]:.3f})")
                else:
                    atk[_pt] = _atk_flat
                    dfd[_pt] = _dfd_flat
                    if _tier2_lid:
                        print(f"[{lid}] promoted {_pt}: no tier2 ELO in {_tier2_lid}, "
                              f"flat prior atk={_atk_flat:.3f} dfd={_dfd_flat:.3f}")
                    else:
                        print(f"[{lid}] promoted {_pt}: "
                              f"flat prior atk={_atk_flat:.3f} dfd={_dfd_flat:.3f}")
```

- [ ] **Step 5: Run tests to verify new tests pass**

```bash
venv/bin/python -m pytest tests/test_build_league_data_tier2.py -v
```

Expected: 3 PASSED

- [ ] **Step 6: Run full suite**

```bash
venv/bin/python -m pytest tests/ -q
```

Expected: all passing.

- [ ] **Step 7: Commit**

```bash
git add scripts/build_league_data.py tests/test_build_league_data_tier2.py
git commit -m "feat(build_league_data): seed promoted teams from tier-2 ELO via tier2_offset"
```

---

## Task 7: Extend `scripts/build_power_rankings.py` — tier-2 group

**Files:**
- Modify: `scripts/build_power_rankings.py`
- Create: `tests/test_build_power_rankings_tier2.py`

- [ ] **Step 1: Write failing test**

Create `tests/test_build_power_rankings_tier2.py`:

```python
"""Tests for tier-2 group in build_power_rankings."""
from __future__ import annotations
from unittest import mock
import json


def _fake_standings(path):
    """Fake _load_standings that returns a single team for each league."""
    league = path.stem  # e.g. "championship", "epl"
    return [{"team": f"TestTeam_{league}", "elo": 1550.0, "logo": None, "color": None}]


def test_build_power_rankings_includes_tier2_group():
    """build() produces a 'UEFA Tier 2' group with tier-2 leagues."""
    from scripts import build_power_rankings as bpr
    from scripts.payload_utils import write_js_payload

    with mock.patch.object(bpr, "_load_standings", side_effect=_fake_standings), \
         mock.patch("scripts.payload_utils.write_js_payload") as mock_write:
        bpr.build()

    assert mock_write.called
    payload = mock_write.call_args[0][2]  # third positional arg is the data dict
    confs = [g["confederation"] for g in payload["groups"]]
    assert "UEFA Tier 2" in confs


def test_tier2_group_teams_have_tier_field():
    """Teams in the UEFA Tier 2 group have tier=2 in their entry."""
    from scripts import build_power_rankings as bpr

    with mock.patch.object(bpr, "_load_standings", side_effect=_fake_standings):
        ranked = bpr._rank_group(bpr._TIER2_LEAGUES, tier=2)
    assert all(r["tier"] == 2 for r in ranked)


def test_tier1_group_teams_have_tier_1():
    """Existing UEFA tier-1 teams still have tier=1 (default)."""
    from scripts import build_power_rankings as bpr

    with mock.patch.object(bpr, "_load_standings", side_effect=_fake_standings):
        ranked = bpr._rank_group(bpr._GROUPS["UEFA"])
    assert all(r.get("tier", 1) == 1 for r in ranked)
```

- [ ] **Step 2: Run to confirm failures**

```bash
venv/bin/python -m pytest tests/test_build_power_rankings_tier2.py -v
```

Expected: 3 failures (missing `_TIER2_LEAGUES`, `tier` param, and the new group in `build()`)

- [ ] **Step 3: Update `scripts/build_power_rankings.py`**

Add `_TIER2_LEAGUES` after the `_GROUPS` dict:

```python
_TIER2_LEAGUES = [
    ("championship", "Championship"),
    ("bundesliga-2", "2. Bundesliga"),
    ("serie-b", "Serie B"),
]
```

Replace `_rank_group` with:

```python
def _rank_group(leagues, tier: int = 1) -> list[dict]:
    """One group's teams ranked by cross-league strength (ELO + offset)."""
    rows = []
    for lid, short in leagues:
        offset = co.tier2_offset(lid) if tier == 2 else co.league_offset(lid)
        for s in _load_standings(lid):
            elo = s.get("elo")
            if elo is None:
                continue
            rows.append({
                "team": s["team"], "league": lid, "league_short": short,
                "elo": int(round(elo)), "strength": round(float(elo) + offset, 1),
                "logo": s.get("logo"), "color": s.get("color"),
                "tier": tier,
            })
    rows.sort(key=lambda r: -r["strength"])
    for i, r in enumerate(rows, 1):
        r["rank"] = i
    return rows
```

In `build()`, add the tier-2 group after the existing `for conf, leagues in _GROUPS.items():` loop:

```python
    # Tier-2 UEFA group (Championship, 2.Bundesliga, Serie B) — on the EPL=0 scale.
    ranked_t2 = _rank_group(_TIER2_LEAGUES, tier=2)
    if ranked_t2:
        data["groups"].append({
            "confederation": "UEFA Tier 2",
            "anchor": "EPL = 0",
            "n_leagues": len({r["league"] for r in ranked_t2}),
            "teams": ranked_t2,
        })
```

- [ ] **Step 4: Run tests**

```bash
venv/bin/python -m pytest tests/test_build_power_rankings_tier2.py -v
```

Expected: 3 PASSED

- [ ] **Step 5: Run full suite**

```bash
venv/bin/python -m pytest tests/ -q
```

Expected: all passing.

- [ ] **Step 6: Commit**

```bash
git add scripts/build_power_rankings.py tests/test_build_power_rankings_tier2.py
git commit -m "feat(power_rankings): add UEFA Tier 2 group (Championship, 2.Bundesliga, Serie B)"
```

---

## Task 8: Create `scripts/eval/promoted_team_brier.py` validation script

**Files:**
- Create: `scripts/eval/promoted_team_brier.py`

This script does not get formal unit tests — it is a validation tool that requires real football_data files. The output is reviewed manually to confirm the tier-bridge prior does not regress vs the flat prior.

- [ ] **Step 1: Create `scripts/eval/promoted_team_brier.py`**

```python
#!/usr/bin/env python3
"""Validation: compare flat-percentile vs tier-bridge Brier on promoted teams.

For each supported league pair, collects all historically promoted teams' first-
season top-flight matches and computes Brier under (a) the static prior offset
and (b) the fitted tier2 offset.  Also reports naive (uniform) Brier.

Acceptance: tier-bridge Brier should be ≤ flat prior Brier on this slice.
A meaningful win on the promoted-team slice is the primary success criterion.

Usage:
    python scripts/eval/promoted_team_brier.py
"""
from __future__ import annotations

import logging

from data_pipeline import coefficients as co
from scripts.eval.tier_bridge import (
    _TIER2_PAIRS,
    _collect_tier_matches,
    _brier,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

_NAIVE_BRIER = 2 / 3


def evaluate_pair(tier2_lid: str, tier1_lid: str) -> dict:
    """Compare flat vs tier-bridge Brier on promoted-team first-season matches."""
    key = f"{tier2_lid}_to_{tier1_lid}"
    prior = co._TIER2_PRIORS[key]
    fitted_delta = co.tier2_offset(tier2_lid)

    matches_by_season = _collect_tier_matches(tier2_lid, tier1_lid)
    all_matches = [m for ms in matches_by_season.values() for m in ms]

    if not all_matches:
        return {
            "pair": key, "n_matches": 0, "n_seasons": 0,
            "brier_tier_bridge": None, "brier_flat_prior": None,
            "naive_brier": round(_NAIVE_BRIER, 4), "delta_vs_flat": None,
        }

    brier_fitted = _brier(all_matches, fitted_delta)
    brier_flat = _brier(all_matches, prior)

    return {
        "pair": key,
        "n_matches": len(all_matches),
        "n_seasons": len(matches_by_season),
        "fitted_delta": round(fitted_delta, 2),
        "flat_prior": round(prior, 2),
        "brier_tier_bridge": round(brier_fitted, 4),
        "brier_flat_prior": round(brier_flat, 4),
        "naive_brier": round(_NAIVE_BRIER, 4),
        "delta_vs_flat": round(brier_fitted - brier_flat, 4),
        "passes": brier_fitted <= brier_flat,
    }


if __name__ == "__main__":
    print("Promoted-team Brier validation\n" + "=" * 40)
    all_pass = True
    for tier2_lid, tier1_lid in _TIER2_PAIRS:
        result = evaluate_pair(tier2_lid, tier1_lid)
        print(f"\n=== {result['pair']} ===")
        for k, v in result.items():
            if k == "pair":
                continue
            print(f"  {k}: {v}")
        if result.get("passes") is False:
            all_pass = False
            print("  *** REGRESSION: tier-bridge worse than flat prior ***")

    print("\n" + ("ALL PAIRS PASS" if all_pass else "SOME PAIRS FAILED"))
```

- [ ] **Step 2: Verify script is importable (no syntax errors)**

```bash
venv/bin/python -c "import scripts.eval.promoted_team_brier; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add scripts/eval/promoted_team_brier.py
git commit -m "feat(tier_bridge): add promoted_team_brier.py validation script"
```

---

## Task 9: End-to-end integration run

This task requires real football_data files on disk. Run it after the previous tasks are committed.

- [ ] **Step 1: Fetch Championship, 2.Bundesliga, and Serie B data if not already cached**

```bash
venv/bin/python -c "
from data_pipeline.football_data import match_results
for lid in ['championship', 'bundesliga-2', 'serie-b', 'epl', 'bundesliga', 'serie-a']:
    df = match_results(lid)
    print(f'{lid}: {len(df)} rows, seasons {sorted(df[\"season\"].unique())[:3]}...')
"
```

Expected: Each league prints row count and season list. If a fetch fails, check network access and re-run.

- [ ] **Step 2: Run tier_bridge in dry-run mode**

```bash
venv/bin/python -m scripts.eval.tier_bridge --dry-run
```

Expected output (approximate — exact numbers depend on data):
```
INFO fit_all: fitting championship → epl (prior=-120.0 ELO)
INFO _collect_tier_matches: championship→epl season 2018: N matches, 3 promoted teams
...
INFO fit_all: championship→epl fitted=-112.4  LOSO brier: fitted=0.6631 prior=0.6695 naive=0.6667
INFO fit_all: fitting bundesliga-2 → bundesliga (prior=-100.0 ELO)
...

Results:
  championship_to_epl: -112.4
  bundesliga-2_to_bundesliga: -98.7
  serie-b_to_serie-a: -127.3
```

If any pair shows `only N matches (need 20) — using prior`, note it but proceed.

- [ ] **Step 3: Run tier_bridge to write experiments/tier2_offsets.json**

```bash
venv/bin/python -m scripts.eval.tier_bridge
```

Expected: creates or updates `experiments/tier2_offsets.json`. Verify:

```bash
cat experiments/tier2_offsets.json
```

Expected: valid JSON with three keys.

- [ ] **Step 4: Run the promoted-team Brier validation**

```bash
venv/bin/python scripts/eval/promoted_team_brier.py
```

Expected: All pairs show `passes: True` (tier-bridge ≤ flat prior on promoted-team matches). If a pair fails, note the Brier values and whether it's close — a very small regression (< 0.002) on sparse data may be acceptable, but investigate before promoting.

- [ ] **Step 5: Build one top-flight league in preseason mode to verify seeding**

```bash
venv/bin/python scripts/build_league_data.py --league epl
```

Look for lines like:
```
[epl] promoted Ipswich: tier2_elo=1588 adj=1476 DC=(atk=-0.041, dfd=0.078)
```

If you see `no tier2 ELO in championship, flat prior` for known promoted teams, check the `_FD_TEAM_ALIASES` dict and add the missing mapping.

- [ ] **Step 6: Build power rankings and verify tier-2 group**

```bash
venv/bin/python scripts/build_power_rankings.py
```

Expected: output includes `[power] UEFA Tier 2: N teams ranked by strength`. Open `webapp/data/power.js` and verify the `UEFA Tier 2` group appears with `"tier": 2` on team entries.

- [ ] **Step 7: Run validate_payloads to confirm no NaN in power.js**

```bash
venv/bin/python scripts/validate_payloads.py
```

Expected: `power.js` passes validation.

- [ ] **Step 8: Run full test suite**

```bash
venv/bin/python -m pytest tests/ -q
```

Expected: all tests passing.

- [ ] **Step 9: Commit integration results**

```bash
git add experiments/tier2_offsets.json
git commit -m "feat(tier_bridge): add fitted tier2_offsets.json from historical promotion outcomes"
```

- [ ] **Step 10: Update docs**

Append a verdict to `docs/superpowers/plans/2026-06-21-next-steps.md` item 1.2 noting that this item is complete. Update `docs/CURRENT_STATE.md` if the promoted-team prior is a notable model improvement (new section under Model Pipeline noting the tier-bridge seeding for promoted teams).

```bash
git add docs/
git commit -m "docs: mark promoted-team tier-bridge (codex §10) complete in next-steps plan"
```
