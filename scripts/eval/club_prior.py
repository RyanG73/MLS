"""Club-prior gap: how far below (or above) its own recent history a team seeds.

`club_prior_gap_t = mean(end-of-season ELO, prior 3 seasons) − seed ELO_t`

A large positive gap marks a "fallen giant" (Spurs 2026-27: history says top-6,
seed says bottom-quartile); a negative gap marks an overachiever seeding above
its history. Teams with fewer than 2 prior seasons get gap 0 — promoted teams
are handled by the tier bridge, not this mechanism.

Pure functions over the ELO series the pipeline already computes: either a tidy
per-team-season history, or derived from a match frame's pre-match
home_elo/away_elo columns via `elo_history_from_matches`.
"""

from __future__ import annotations

import pandas as pd


def elo_history_from_matches(df: pd.DataFrame) -> pd.DataFrame:
    """Tidy (team, season, seed_elo, end_elo) from a match frame.

    Uses the pre-match `home_elo`/`away_elo` columns: a team's seed is its first
    observed pre-match rating of the season, its end value the last observed —
    a close proxy for end-of-season rating without needing post-match state.
    """
    long = pd.concat([
        df[["date", "season", "home_team", "home_elo"]].rename(
            columns={"home_team": "team", "home_elo": "elo"}),
        df[["date", "season", "away_team", "away_elo"]].rename(
            columns={"away_team": "team", "away_elo": "elo"}),
    ]).dropna(subset=["elo"]).sort_values("date", kind="stable")
    g = long.groupby(["team", "season"])["elo"]
    return pd.DataFrame({"seed_elo": g.first(), "end_elo": g.last()}).reset_index()


def club_prior_gap(elo_history: pd.DataFrame, n_prior: int = 3,
                   min_prior: int = 2) -> dict[tuple[str, int], float]:
    """{(team, season): gap} for every team-season in the history.

    gap = mean(end_elo over up to `n_prior` immediately preceding seasons the
    team appears in) − seed_elo. Fewer than `min_prior` prior seasons → 0.0.
    """
    hist = elo_history.sort_values(["team", "season"])
    out: dict[tuple[str, int], float] = {}
    for team, grp in hist.groupby("team"):
        grp = grp.reset_index(drop=True)
        for i, row in grp.iterrows():
            prior = grp.iloc[max(0, i - n_prior):i]
            if len(prior) < min_prior:
                out[(team, int(row["season"]))] = 0.0
            else:
                out[(team, int(row["season"]))] = float(
                    prior["end_elo"].mean() - row["seed_elo"])
    return out
