"""
Contract test for the league-agnostic feature builder (scripts/eval/league_features).

Verifies that ELO + rolling-feature composition emits every column the model's
LEAGUE_FEAT_BASE references, from nothing but the canonical goals+xG columns the
Understat adapter produces. Synthetic frame → fast, network-free.
"""

import numpy as np
import pandas as pd

from scripts.eval.league_features import (
    LEAGUE_FEAT_BASE, build_league_features,
)


def _synthetic_frame(n_seasons=3, teams=6):
    """A tiny round-robin-ish league: every team plays every other, each season."""
    names = [f"T{i}" for i in range(teams)]
    rows, mid = [], 0
    rng = np.random.default_rng(0)
    for season in range(2020, 2020 + n_seasons):
        day = pd.Timestamp(f"{season}-08-01")
        for h in names:
            for a in names:
                if h == a:
                    continue
                hg, ag = int(rng.integers(0, 4)), int(rng.integers(0, 4))
                rows.append({
                    "match_id": str(mid), "date": day, "season": season,
                    "home_team": h, "away_team": a,
                    "home_goals": hg, "away_goals": ag,
                    "home_xg": float(hg) + rng.normal(0, 0.3),
                    "away_xg": float(ag) + rng.normal(0, 0.3),
                    "label_result": 0 if hg > ag else (1 if hg == ag else 2),
                    "is_result": True, "is_playoff": 0,
                })
                mid += 1
                day += pd.Timedelta(days=1)
    return pd.DataFrame(rows)


def test_build_emits_every_feat_base_column():
    df = build_league_features(_synthetic_frame())
    missing = [c for c in LEAGUE_FEAT_BASE if c not in df.columns]
    assert not missing, f"feature builder missing columns: {missing}"


def test_features_are_finite_and_leakage_safe():
    df = build_league_features(_synthetic_frame())
    # No NaN/inf in the model-consumed features (rolling builders fall back to priors)
    X = df[LEAGUE_FEAT_BASE].to_numpy(dtype=float)
    assert np.isfinite(X).all()
    # ELO is walk-forward: the very first match must see both teams at the 1500 prior
    assert df.iloc[0]["home_elo"] == 1500.0
    assert df.iloc[0]["away_elo"] == 1500.0
    # is_playoff stays 0 for every European-style row
    assert (df["is_playoff"] == 0).all()
