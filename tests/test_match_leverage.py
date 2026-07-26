"""Tests for fixture leverage — the "Matches to Watch" feature.

Leverage is the expected L1 movement in a league's outcome probabilities caused
by one match: pin the fixture to home / draw / away, re-simulate the rest of the
season from the payload's own per-fixture probabilities, and weight each
conditional table by P(outcome).

The tests pin the PROPERTIES that make the number meaningful (non-negative,
bounded, zero when nothing is at stake, larger when more is) rather than the
values themselves, which move with every rebuild.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
PAYLOAD = ROOT / "webapp" / "data" / "match-leverage.js"


@pytest.fixture(scope="module")
def payload():
    if not PAYLOAD.exists():
        pytest.skip("match-leverage.js not built")
    m = re.match(r"window\.\w+\s*=\s*(.*?);?\s*$", PAYLOAD.read_text(encoding="utf-8"), re.DOTALL)
    return json.loads(m.group(1))


def test_payload_shape(payload):
    assert payload["status"] == "live"
    assert payload["scope"] in ("all", "pair")
    assert payload["fixtures"], "no fixtures scored"
    assert payload["explainer"], "the UI copy must ship with the data"


def test_every_fixture_has_what_the_rails_need(payload):
    """Missing a field here means a rail silently renders blanks."""
    need = {"league", "league_name", "date", "home", "away",
            "leverage", "pct", "tier", "rank"}
    for r in payload["fixtures"][:50]:
        missing = need - set(r)
        assert not missing, f"{r.get('home')} v {r.get('away')} missing {missing}"


def test_leverage_is_non_negative_and_bounded(payload):
    """It is a sum of |probability deltas| — negative or huge means a bug."""
    for r in payload["fixtures"]:
        assert r["leverage"] >= 0, f"negative leverage: {r}"
        # Weighted L1 over every club and bucket, x100. Even a wild swing in a
        # 24-team table cannot plausibly clear this.
        assert r["leverage"] < 500, f"implausible leverage: {r}"


def test_percentile_is_within_league_and_well_formed(payload):
    by_league: dict[str, list[float]] = {}
    for r in payload["fixtures"]:
        assert 0.0 < r["pct"] <= 1.0, r
        by_league.setdefault(r["league"], []).append(r["pct"])
    for lid, pcts in by_league.items():
        assert max(pcts) == pytest.approx(1.0), (
            f"{lid}: no fixture at percentile 1.0 — the within-league rank is broken")


def test_percentile_ordering_matches_leverage_ordering(payload):
    """pct must be a monotone re-expression of leverage inside a league."""
    by_league: dict[str, list[tuple[float, float]]] = {}
    for r in payload["fixtures"]:
        by_league.setdefault(r["league"], []).append((r["leverage"], r["pct"]))
    for lid, pairs in by_league.items():
        pairs.sort()
        pcts = [p for _, p in pairs]
        assert pcts == sorted(pcts), f"{lid}: pct does not track leverage"


def test_ranks_are_dense_and_ordered(payload):
    fx = payload["fixtures"]
    assert [r["rank"] for r in fx] == list(range(1, len(fx) + 1))
    lev = [r["leverage"] for r in fx]
    assert lev == sorted(lev, reverse=True), "fixtures are not ranked by leverage"


# ── the metric itself ────────────────────────────────────────────────────────

def test_a_decided_league_has_near_zero_leverage():
    """Nothing at stake ⇒ no swing. The sanity floor for the whole metric.

    Two clubs so far apart that one fixture cannot change any bucket should
    score ~0, whatever the result.
    """
    from scripts.match_leverage import _bucket_probs, _sim
    rng = np.random.default_rng(0)
    n = 6
    # A runaway leader and a doomed bottom club, one fixture left between the
    # two MIDDLE clubs — it decides nothing.
    base_pts = np.array([90.0, 40, 39, 38, 37, 5])
    base_gd = np.zeros(n)
    H, A = np.array([2]), np.array([3])
    P = np.array([[0.4, 0.25, 0.35]])
    cols = [{"key": "title", "top": 1}, {"key": "releg", "bottom": 1}]
    base = _bucket_probs(_sim(base_pts, base_gd, H, A, P, n, 3000, rng), cols, n)
    swing = 0.0
    for outcome in (0, 1, 2):
        o = _bucket_probs(
            _sim(base_pts, base_gd, H, A, P, n, 3000,
                 np.random.default_rng(outcome + 1), pin=(0, outcome)), cols, n)
        for k in ("title", "releg"):
            swing += P[0, outcome] * float(np.abs(o[k] - base[k]).sum())
    assert swing < 0.02, f"a dead rubber scored {swing:.4f}"


def test_a_decisive_fixture_scores_higher_than_a_dead_one():
    """Ordering is the product claim: more at stake ⇒ higher leverage."""
    from scripts.match_leverage import _bucket_probs, _sim
    n = 4
    cols = [{"key": "title", "top": 1}]
    base_gd = np.zeros(n)

    def leverage(base_pts, H, A):
        rng = np.random.default_rng(3)
        P = np.array([[0.4, 0.25, 0.35]])
        base = _bucket_probs(_sim(base_pts, base_gd, H, A, P, n, 4000, rng), cols, n)
        s = 0.0
        for outcome in (0, 1, 2):
            o = _bucket_probs(
                _sim(base_pts, base_gd, H, A, P, n, 4000,
                     np.random.default_rng(10 + outcome), pin=(0, outcome)), cols, n)
            s += P[0, outcome] * float(np.abs(o["title"] - base["title"]).sum())
        return s

    # Level at the top, the two leaders meet — the title turns on it.
    decisive = leverage(np.array([50.0, 50, 20, 10]), np.array([0]), np.array([1]))
    # The same fixture list, but the leader is already clear.
    dead = leverage(np.array([90.0, 50, 20, 10]), np.array([2]), np.array([3]))
    assert decisive > dead * 5, f"decisive {decisive:.3f} vs dead {dead:.3f}"
