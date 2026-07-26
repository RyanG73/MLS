"""Tests for the preseason value-informed ELO tilt and its gate.

History, because the reversal matters: the tilt was restricted to clubs at or
below the league median ELO from 2026-07-07, on the strength of an A/B that
measured +0.005 title Brier for an untargeted tilt. That A/B ran on a CORRUPT
squad-value table — the scrape was reading Transfermarkt's per-player average
column, so Manchester City read EUR 44m and Real Madrid EUR 45m, which flattened
the log(value) -> ELO slope and made an untargeted tilt push nonsense at the top
of the table (see tests/test_tm_value_backfill.py).

With the parse fixed (2026-07-26) the season-outcome replay reversed the
verdict — big-5, 2018-2025, 800 team-seasons, preseason checkpoint:

    arm            title      ucl    releg      sum
    no tilt      0.03162  0.09436  0.11426  0.24024
    bottom-half  0.03166  0.09459  0.10305  0.22930   <- old production
    UNTARGETED   0.03224  0.08728  0.10198  0.22150   <- promoted

so the gate was removed. These tests pin the shape of the tilt rather than the
exact numbers (which move as squad values update), plus the gate plumbing that
lets the decision be re-tested.
"""
from __future__ import annotations

import numpy as np
import pytest

from scripts.eval.season_outcomes import replay_league


def _fit_and_delta(elos: dict[str, float], values: dict[str, float],
                   gate: str, beta: float = 0.5, min_gap: float = 0.0):
    """Reproduce the tilt arithmetic for one league-season, honouring `gate`.

    Mirrors the block inside replay_league/build_league_data; kept here so the
    gate semantics are testable without replaying a whole season.
    """
    import math
    xs = [math.log(values[t]) for t in elos if values.get(t, 0) > 0]
    ys = [elos[t] for t in elos if values.get(t, 0) > 0]
    b_, a_ = np.polyfit(np.array(xs), np.array(ys), 1)
    med = float(np.median(list(elos.values())))
    out = {}
    for t, r in elos.items():
        v = values.get(t, 0)
        if v <= 0:
            continue
        delta = beta * ((a_ + b_ * math.log(v)) - r)
        if gate == "bottom" and r > med:
            continue
        if gate in ("up", "up-gap") and delta <= 0:
            continue
        if gate in ("gap", "up-gap") and abs(delta) < beta * min_gap:
            continue
        out[t] = delta
    return out


# A league where one rich club has an ELO well below what its value implies —
# the AC Milan shape.
ELOS = {"rich_fallen": 1635, "rich_top": 1785, "mid": 1560, "poor": 1450,
        "poor2": 1440, "mid2": 1600, "mid3": 1520, "rich_ok": 1690}
VALUES = {"rich_fallen": 583, "rich_top": 689, "mid": 190, "poor": 60,
          "poor2": 55, "mid2": 210, "mid3": 120, "rich_ok": 540}


def test_bottom_gate_ignores_the_fallen_giant():
    """The exact failure the request reported: Milan is above the median."""
    d = _fit_and_delta(ELOS, VALUES, gate="bottom")
    assert "rich_fallen" not in d, (
        "a rich club above the median ELO received a correction under the "
        "bottom-half gate — that gate is supposed to skip it")


def test_untargeted_gate_lifts_the_fallen_giant():
    d = _fit_and_delta(ELOS, VALUES, gate="all")
    assert "rich_fallen" in d
    assert d["rich_fallen"] > 0, "value exceeds ELO, so the tilt must be upward"


def test_up_gate_never_demotes():
    d = _fit_and_delta(ELOS, VALUES, gate="up")
    assert all(v > 0 for v in d.values()), d


def test_gap_gate_filters_small_corrections():
    wide = _fit_and_delta(ELOS, VALUES, gate="all")
    narrow = _fit_and_delta(ELOS, VALUES, gate="gap", min_gap=40.0)
    assert set(narrow) <= set(wide)
    assert len(narrow) < len(wide), "a gap threshold should drop some clubs"
    for v in narrow.values():
        assert abs(v) >= 0.5 * 40.0 - 1e-9


def test_tilt_direction_follows_value_minus_elo():
    """Sign discipline: overrated clubs come down, underrated ones go up."""
    d = _fit_and_delta(ELOS, VALUES, gate="all")
    # rich_fallen has high value for its ELO -> up.
    assert d["rich_fallen"] > 0
    # rich_top has the highest ELO in the league; its value does not justify
    # being that far clear, so the fit pulls it back.
    assert d["rich_top"] < d["rich_fallen"]


def test_replay_accepts_the_gate_argument():
    """Plumbing: the knob must reach replay_league, or the A/B is not runnable."""
    import inspect
    sig = inspect.signature(replay_league)
    assert "value_gate" in sig.parameters
    assert "value_min_gap" in sig.parameters
    # Production default must match what build_league_data actually does.
    assert sig.parameters["value_gate"].default == "all"


def test_production_has_no_median_gate():
    """Guard the reversal: re-introducing the gate should fail loudly here."""
    from pathlib import Path
    src = (Path(__file__).resolve().parents[1]
           / "scripts" / "build_league_data.py").read_text(encoding="utf-8")
    i = src.find("_VALUE_BETA")
    assert i != -1, "value tilt block not found"
    window = src[i - 400:i + 700]
    assert "elo_now[_t] <= _med" not in window, (
        "the bottom-half median gate is back in the production tilt. It was "
        "removed 2026-07-26 because the A/B that justified it ran on a corrupt "
        "value table; re-run scripts/eval_season_outcomes.py --value-gate "
        "before restoring it."
    )
