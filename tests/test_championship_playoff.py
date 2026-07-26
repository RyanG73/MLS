"""Tests for the championship-playoff bracket (build_league_data).

Added 2026-07-25. Before this, no domestic championship playoff was simulated
anywhere except MLS: leagues whose title is decided in a post-season published
only *qualification* odds — Liga MX could say who would reach the Liguilla but
never who would win it, which is the number a reader actually wants.

Two things are checked: that the bracket itself is a sane tournament (exactly
one winner, always a seed, better seeds win more), and that the payloads it
feeds stay probabilistically coherent (title sums to 100, and a club can never
be more likely to win the title than to qualify for the playoff at all).
"""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

import numpy as np
import pytest

from scripts.build_league_data import _championship_winner

ROOT = Path(__file__).resolve().parents[1]


def _pmatrix(n: int, edge: float = 0.0) -> np.ndarray:
    """(n, n, 3) home/draw/away matrix. `edge` tilts toward the lower index."""
    pm = np.zeros((n, n, 3))
    for i in range(n):
        for j in range(n):
            adv = edge * (j - i)          # i beats j more often when i < j
            ph = min(max(0.40 + adv, 0.02), 0.96)
            pd_ = min(0.25, 1.0 - ph - 0.02)
            pm[i, j] = (ph, pd_, max(1.0 - ph - pd_, 0.0))
    return pm


@pytest.mark.parametrize("n", [1, 2, 3, 4, 5, 6, 7, 8])
def test_winner_is_always_one_of_the_seeds(n):
    rng = np.random.default_rng(7)
    pm = _pmatrix(n)
    seeds = list(range(n))
    for _ in range(200):
        w = _championship_winner(seeds, pm, rng)
        assert w in seeds, f"{n}-team bracket returned {w!r}, not a seed"


def test_larger_field_is_truncated_not_crashed():
    """A field bigger than any modelled shape must degrade, not explode."""
    rng = np.random.default_rng(1)
    seeds = list(range(12))
    w = _championship_winner(seeds, _pmatrix(12), rng)
    assert w in seeds[:8], "fields over 8 should resolve among the top 8 seeds"


def test_better_seeds_win_more_often():
    """With a real strength gradient the top seed must lead the win counts."""
    rng = np.random.default_rng(42)
    pm = _pmatrix(8, edge=0.05)
    seeds = list(range(8))
    wins = Counter(_championship_winner(seeds, pm, rng) for _ in range(4000))
    assert wins[0] > wins[7], f"top seed {wins[0]} did not beat bottom seed {wins[7]}"
    assert wins[0] == max(wins.values()), f"top seed was not the most frequent winner: {wins}"


def test_even_strengths_stay_near_uniform_but_favour_hosting():
    """With equal strengths, the seeding/hosting bias is the only edge."""
    rng = np.random.default_rng(3)
    pm = _pmatrix(8, edge=0.0)
    wins = Counter(_championship_winner(list(range(8)), pm, rng) for _ in range(8000))
    share = {k: v / 8000 for k, v in wins.items()}
    assert all(0.02 < s < 0.35 for s in share.values()), share
    assert share[0] >= share[7], "hosting the whole way should not be a disadvantage"


# ── payload coherence ────────────────────────────────────────────────────────

def _payload(lid: str):
    p = ROOT / "webapp" / "data" / f"{lid}.js"
    if not p.exists():
        pytest.skip(f"{lid} payload not built")
    m = re.match(r"window\.\w+\s*=\s*(.*?);?\s*$", p.read_text(encoding="utf-8"), re.DOTALL)
    return json.loads(m.group(1))


CHAMP_LEAGUES = ["liga-mx", "liga-expansion-mx", "nwsl",
                 "usl-league-one", "usl-super-league",
                 "northern-super-league", "india-isl"]


@pytest.mark.parametrize("lid", CHAMP_LEAGUES)
def test_title_probabilities_are_coherent(lid):
    d = _payload(lid)
    rows = d.get("standings") or []
    if not rows or "title" not in rows[0]:
        pytest.skip(f"{lid} has no title column (not rebuilt since the bracket landed)")
    total = sum(r["title"] for r in rows)
    assert 99.0 <= total <= 101.0, f"{lid} title probabilities sum to {total}, not ~100"

    # A club cannot win a playoff it did not reach.
    gate = next((k for k in ("liguilla", "playoffs") if k in rows[0]), None)
    if gate:
        bad = [(r["team"], r["title"], r[gate]) for r in rows
               if r["title"] > r[gate] + 0.15]     # 0.15 = Monte-Carlo rounding
        assert not bad, f"{lid}: title exceeds {gate} qualification for {bad}"
