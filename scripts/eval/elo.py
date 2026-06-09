"""
ELO rating model extracted from eval_baseline.py (F4 extraction).

Pure function: takes a sorted DataFrame and returns it with ELO columns added.
No API calls, no module-level state.  eval_baseline.py imports compute_elo from
here; behavior is preserved — verified by eval_baseline.py --smoke-test.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

DEFAULT_INITIAL_ELO: float = 1500.0
DEFAULT_REGRESS:     float = 0.40   # promoted 2026-06-07 (synergistic with whl=6)


def compute_elo(
    df: pd.DataFrame,
    K: float,
    home_adv: float,
    regress: float = DEFAULT_REGRESS,
    initial: float = DEFAULT_INITIAL_ELO,
    return_expected: bool = False,
) -> pd.DataFrame:
    """Walk-forward ELO ratings with margin-of-victory multiplier and season regression.

    Args:
        df:             Match DataFrame sorted by date ascending.  Must have columns:
                        season, home_team, away_team, home_goals, away_goals.
        K:              ELO K-factor (controls how fast ratings update).
        home_adv:       Home-field advantage in ELO points added to home rating.
        regress:        Fraction of each team's deviation from ``initial`` to remove
                        at the start of each new season (0 = no regression, 1 = full reset).
        initial:        Starting ELO for any team that has not been seen yet.
        return_expected: If True, also writes ``elo_p_home`` (pre-match expected home
                        win probability from the ELO formula).

    Returns:
        Copy of ``df`` with columns added:
        ``home_elo``, ``away_elo``, ``elo_diff`` (home − away *before* the match),
        and optionally ``elo_p_home``.
    """
    elo: dict[str, float] = {}
    h_elo, a_elo, h_exp = [], [], []
    seen: set[object] = set()

    for _, row in df.iterrows():
        s = row["season"]
        if s not in seen:
            seen.add(s)
            elo = {t: initial + (r - initial) * (1 - regress) for t, r in elo.items()}
        ht, at = row["home_team"], row["away_team"]
        rh = elo.get(ht, initial)
        ra = elo.get(at, initial)
        e_h = 1.0 / (1.0 + 10.0 ** ((ra - (rh + home_adv)) / 400.0))
        hg, ag = row["home_goals"], row["away_goals"]
        s_h = 1.0 if hg > ag else (0.5 if hg == ag else 0.0)
        mov = 1.0 + math.log(abs(hg - ag) + 1) * 0.1
        h_elo.append(rh)
        a_elo.append(ra)
        h_exp.append(e_h)
        elo[ht] = rh + K * mov * (s_h - e_h)
        elo[at] = ra + K * mov * ((1.0 - s_h) - (1.0 - e_h))

    out = df.copy()
    out["home_elo"] = h_elo
    out["away_elo"] = a_elo
    out["elo_diff"] = np.array(h_elo) - np.array(a_elo)
    if return_expected:
        out["elo_p_home"] = h_exp
    return out
