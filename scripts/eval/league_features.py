"""
League-agnostic feature builder — canonical match frame → engineered features.

Composes the two already-extracted, pure builders (compute_elo + the rolling
xG/form builder) into the feature matrix the validated model consumes, using
ONLY columns every league has: goals + xG + team + date + season. None of the
MLS-specific signals (goalkeeper z-scores, roster availability, referee, travel,
dome, manager) are computed here — they require data sources that don't exist
for the European leagues.

This is deliberate and safe: `research_model.walk_forward` selects
`feat = [c for c in feat_base if c in df.columns]`, so passing the full MLS
feat_base against a frame that only has these columns transparently uses the
intersection. The model degrades to "what this league can support" with no code
branch. The 6 MLS-only features (home/away_gk_z, gk_z_diff, home/away_avail_
share, avail_share_diff) are simply absent.

Reused by both per-league validation (scripts/validate_league.py) and the
multi-league dashboard build (WS3), so the feature definition lives in exactly
one place across research and production.
"""

from __future__ import annotations

import pandas as pd

from scripts.eval.elo import compute_elo
from scripts.eval.feature_builders import add_rolling_features

# Champion hyperparameters (CLAUDE.md "Key decisions"). ELO regress default is
# already 0.40 in elo.py; K and HOME_ADV are named here so the build is explicit.
ELO_K: float = 25.0
ELO_HOME_ADV: float = 80.0
ELO_REGRESS: float = 0.40
XG_WINDOWS: tuple[int, ...] = (3, 5, 10, 15)
FORM_WINDOWS: tuple[int, ...] = (3, 5, 10, 15)
GAMES_14D_DAYS: int = 14

# The league-agnostic subset of the MLS 37-feature champion feat_base: ELO +
# rolling xG/xGA + form + the two derived diffs + is_playoff. Order mirrors the
# MLS meta.json for readability; order is irrelevant to the model.
LEAGUE_FEAT_BASE: list[str] = [
    "elo_diff", "home_elo", "away_elo",
    "home_xg_roll_3", "home_xg_roll_5", "home_xg_roll_10", "home_xg_roll_15",
    "away_xg_roll_3", "away_xg_roll_5", "away_xg_roll_10", "away_xg_roll_15",
    "home_xga_roll_3", "home_xga_roll_5", "home_xga_roll_10", "home_xga_roll_15",
    "away_xga_roll_3", "away_xga_roll_5", "away_xga_roll_10", "away_xga_roll_15",
    "xg_diff", "home_xg_sum",
    "home_form_3", "home_form_5", "home_form_10", "home_form_15",
    "away_form_3", "away_form_5", "away_form_10", "away_form_15",
    "form_diff", "is_playoff",
]


def build_league_features(played: pd.DataFrame) -> pd.DataFrame:
    """Add ELO + rolling xG/form features to a played-matches canonical frame.

    Args:
        played: Canonical match frame (Understat adapter output) restricted to
                completed matches, with integer home_goals/away_goals and an
                integer label_result. Must be the full history (the rolling
                windows and ELO are walk-forward and need every prior match).

    Returns:
        Copy of ``played`` (sorted by date) with all LEAGUE_FEAT_BASE columns
        present. PPDA/possession/set-piece flags are off (Understat gives none
        of those at match level), so those optional columns are not added.
    """
    df = played.sort_values("date").reset_index(drop=True)
    df = compute_elo(df, K=ELO_K, home_adv=ELO_HOME_ADV, regress=ELO_REGRESS)
    df = add_rolling_features(
        df, XG_WINDOWS, FORM_WINDOWS, GAMES_14D_DAYS,
        xpass_by_game={}, has_ppda=False, has_poss=False, has_sp_xg=False,
    )
    return df
