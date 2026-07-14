"""Momentum-chart math (2026-07-14), ported from github.com/JakeBonnici22/
match-momentum's approach: each shot injects "threat energy" for its team,
weighted by xG (goals weighted extra since they're the highest-certainty
threat event), which decays exponentially with a short half-life so the
curve tracks WHO'S ON TOP RIGHT NOW rather than accumulating all game. A
Gaussian kernel then smooths the net (home-minus-away) curve into the
familiar broadcast-style momentum chart.

Swapped NumPy/Matplotlib's static-PNG output for a plain numeric series here
— the webapp renders it as an inline SVG client-side instead.
"""
from __future__ import annotations

import numpy as np
from scipy.ndimage import gaussian_filter1d

HALFLIFE_MIN = 3.0     # threat "energy" decays to half in ~3 match-minutes
GOAL_BONUS = 2.5       # extra weight on top of a goal's own xG
GAUSSIAN_SIGMA = 2.0   # smoothing width, in minutes


def compute_momentum(shots: dict[str, list[dict]]) -> list[dict]:
    """{'h':[...], 'a':[...]} Understat shot dicts -> [{'minute','value'}, ...].

    `value` is net momentum (home minus away) at each minute, smoothed;
    positive = home team on top, negative = away team on top. Not
    normalized to a fixed scale — magnitude is comparable within one match,
    not across matches (a blowout's peak isn't meant to equal a tight game's).
    """
    all_minutes = [float(s.get("minute", 0) or 0)
                   for side in shots.values() for s in side]
    duration = int(max([90.0] + all_minutes)) + 2
    minutes = np.arange(0, duration + 1, dtype=float)
    decay_k = np.log(2) / HALFLIFE_MIN

    energy = {"h": np.zeros_like(minutes), "a": np.zeros_like(minutes)}
    for side in ("h", "a"):
        for s in shots.get(side, []):
            t = float(s.get("minute", 0) or 0)
            xg = float(s.get("xG", 0) or 0)
            weight = max(xg, 0.03) * (1.0 + GOAL_BONUS if s.get("result") == "Goal" else 1.0)
            dt = minutes - t
            decay = np.where(dt >= 0, np.exp(-decay_k * dt), 0.0)
            energy[side] += weight * decay

    net = energy["h"] - energy["a"]
    smoothed = gaussian_filter1d(net, sigma=GAUSSIAN_SIGMA)
    return [{"minute": int(m), "value": round(float(v), 4)}
            for m, v in zip(minutes, smoothed)]
