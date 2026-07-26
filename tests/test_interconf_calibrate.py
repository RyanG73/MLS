"""Tests for the inter-confederation ELO link (scripts/eval/interconf_calibrate).

Context: `league_bridge` fits league offsets INSIDE a confederation, each group
anchored at its own reference league pinned to 0.0. MLS and EPL therefore both
read 0.0 without that meaning anything — no match in the fitting data ever
connected them. This module adds one whole-scale shift per confederation, fitted
on the FIFA Club World Cup, the only competition in the dataset where
confederations actually meet.

The invariant that matters most is NOT the fitted numbers (60 matches, they will
move as editions are played) but that the shift is a pure re-basing: it must be
incapable of changing a within-confederation projection.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

import data_pipeline.coefficients as co

ROOT = Path(__file__).resolve().parents[1]
FITTED = ROOT / "experiments" / "confederation_offsets.json"


@pytest.fixture(scope="module")
def fitted():
    if not FITTED.exists():
        pytest.skip("confederation_offsets.json not built")
    return json.loads(FITTED.read_text())


# ── the safety property ──────────────────────────────────────────────────────

@pytest.mark.parametrize("a,b", [
    ("epl", "la-liga"), ("epl", "primeira"), ("mls", "liga-mx"),
    ("brazil-serie-a", "argentina-primera"), ("japan-j1", "saudi-pro"),
])
def test_shift_cancels_within_a_confederation(a, b):
    """A constant added to every league in a confederation must cancel.

    `cross_league.match_lambdas` consumes the strength DIFFERENCE, so this is
    exactly the condition under which no domestic or same-confederation
    continental projection can move.
    """
    delta_after = co.league_offset(a) - co.league_offset(b)
    delta_within = ((co.league_offset(a) - co.confederation_shift(a))
                    - (co.league_offset(b) - co.confederation_shift(b)))
    assert abs(delta_after - delta_within) < 1e-9


def test_anchor_confederation_is_unshifted(fitted):
    assert fitted["anchor"] == "UEFA"
    assert fitted["shifts"]["UEFA"] == 0.0
    assert co.confederation_shift("epl") == 0.0


def test_unknown_league_shifts_by_zero():
    assert co.confederation_shift("not-a-real-league") == 0.0
    assert co.league_offset("not-a-real-league") == 0.0


# ── the fitted result ────────────────────────────────────────────────────────

def test_every_confederation_rates_at_or_below_uefa(fitted):
    """No confederation should come out stronger than UEFA on this evidence."""
    for conf, v in fitted["shifts"].items():
        assert v <= 0.0, f"{conf} fitted above UEFA at {v:.0f}"


def test_conmebol_is_the_closest_to_uefa(fitted):
    """The ordering both the data and conventional wisdom agree on."""
    s = fitted["shifts"]
    others = [v for k, v in s.items() if k not in ("UEFA", "CONMEBOL")]
    assert s["CONMEBOL"] > max(others), (
        f"CONMEBOL {s['CONMEBOL']:.0f} should sit above {others}")


def test_shifts_are_in_a_plausible_range(fitted):
    """A confederation gap beyond ~500 ELO would be a fitting artefact."""
    for conf, v in fitted["shifts"].items():
        assert -500.0 <= v <= 0.0, f"{conf} implausible at {v:.0f}"


def test_fit_beats_the_baselines_it_must(fitted):
    """Recorded verdict: the fit has to beat today's all-zero and naive.

    Guards against a future re-run silently promoting a worse model — the first
    run of this calibration reported ADOPT off a single 15-match split where the
    fitted shifts were in fact worse than the prior alone.
    """
    m = fitted["holdout_brier_mean"]
    assert m["fitted"] < m["zero"], "fit does not beat today's uncalibrated scale"
    assert m["fitted"] < m["naive"], "fit does not beat base rates"
    assert fitted["splits"] >= 50, "verdict must rest on many splits, not one"


def test_thinly_evidenced_confederations_stay_near_their_prior(fitted):
    """CAF has three matches; the ridge must keep it from wandering.

    This is the honest-uncertainty guarantee: where the data cannot speak, the
    published number is conventional wisdom, not noise dressed as evidence.
    """
    caf_prior = fitted["prior"]["CAF"]
    caf_fit = fitted["shifts"]["CAF"]
    assert abs(caf_fit - caf_prior) < 100.0, (
        f"CAF moved {caf_fit - caf_prior:+.0f} from prior on ~3 matches")


# ── the collector ────────────────────────────────────────────────────────────

def test_collector_returns_only_inter_confederation_pairs():
    """Same-confederation pairs carry no signal about a between-conf shift."""
    pytest.importorskip("scipy")
    from scripts.eval.interconf_calibrate import collect
    try:
        rows = collect()
    except Exception as e:                       # noqa: BLE001 — network/cache
        pytest.skip(f"club-world-cup data unavailable: {e}")
    if not rows:
        pytest.skip("no club-world-cup matches cached")
    assert all(hc != ac for _, hc, ac in rows)
    assert len(rows) >= 30, f"only {len(rows)} inter-conf matches — check resolution"
