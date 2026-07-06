"""C1: non-round-robin season formats (split leagues, playoff rounds, points halving).

Three C1 leagues do not finish on a plain round-robin table:

- **Scottish Premiership** — 33 rounds, then the table SPLITS top-6/bottom-6 for
  5 more rounds; final positions cannot cross the split line (a bottom-half team
  outscoring 6th still classifies 7th or below). Points carry in full.
- **Belgian Pro League** — regular season, then Champions'/Europe play-off groups
  seeded with regular-season points HALVED (rounded up); group membership caps
  final classification (Champions PO teams are ranks 1–6 regardless of totals).
- **Greek Super League** — championship play-off round (top 6, points carried in
  full) + play-out; group membership constrains final ranks the same way.

A format config is
    {"rr": <regular round-robin count>, "groups": [size, ...], "carry": "full"|"half"}
where regular_games = rr·(n_teams−1), `groups` lists classification-group sizes
from the top of the REGULAR-season table (remaining teams form a final implicit
group), and `carry` transforms regular points at the group boundary.

The classification returned here drives the concluded-season standings and the
bucket columns; when a format league gains forward fixtures the same group
constraint applies to each simulated table (group known only once the regular
phase is complete — pre-split sims carry no constraint).
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

# Per-league format configs (see module docstring). Keys are platform league ids;
# leagues absent here are plain round-robins. `groups` seeds SIMULATED seasons;
# for observed post-phase rows the actual pool memberships are inferred from
# the pairing graph instead (see groups_from_post) — pool seeding tie-breaks
# (e.g. Greek head-to-head) aren't modelled, the data is the ground truth.
FORMATS: dict[str, dict] = {
    "scottish-prem": {"rr": 3, "groups": [6], "carry": "full"},
    "belgian-pro":   {"rr": 2, "groups": [6, 6], "carry": "half"},
    "greek-super":   {"rr": 2, "groups": [4, 4], "carry": "full"},  # 2025-26 pools
}


def regular_phase_mask(season_df: pd.DataFrame, regular_games: int) -> np.ndarray:
    """True for rows in the regular phase (neither side past its allotment).

    Rows must be chronologically sorted. A match is post-regular once EITHER
    side has already completed `regular_games` matches — robust to the exact
    calendar interleaving of split/play-off rounds.
    """
    played: dict[str, int] = {}
    out = []
    for _, r in season_df.iterrows():
        h, a = r["home_team"], r["away_team"]
        out.append(played.get(h, 0) < regular_games and played.get(a, 0) < regular_games)
        played[h] = played.get(h, 0) + 1
        played[a] = played.get(a, 0) + 1
    return np.array(out, dtype=bool)


def _table(rows: pd.DataFrame, teams: list[str]) -> dict[str, dict]:
    t = {x: {"pts": 0, "gd": 0} for x in teams}
    for _, r in rows.iterrows():
        h, a = r["home_team"], r["away_team"]
        hg, ag = int(r["home_goals"]), int(r["away_goals"])
        if h in t:
            t[h]["gd"] += hg - ag
        if a in t:
            t[a]["gd"] += ag - hg
        if hg > ag and h in t:
            t[h]["pts"] += 3
        elif hg < ag and a in t:
            t[a]["pts"] += 3
        else:
            if hg == ag:
                if h in t:
                    t[h]["pts"] += 1
                if a in t:
                    t[a]["pts"] += 1
    return t


def groups_from_post(post: pd.DataFrame, teams: list[str],
                     reg_order: list[str]) -> dict[str, int] | None:
    """Infer classification pools from the observed post-phase pairing graph.

    Split/play-off pools only play within themselves, so connected components
    of the who-played-whom graph ARE the pools. Components are ranked by their
    best regular-season finisher; teams with no post-phase rows trail in a
    final group. Returns None when the graph is degenerate (one component
    spanning most of the league — e.g. a cross-pool barrage merged the pools),
    in which case the caller falls back to table-based seeding.
    """
    if post.empty:
        return None
    parent = {t: t for t in teams}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for _, r in post.iterrows():
        h, a = r["home_team"], r["away_team"]
        if h in parent and a in parent:
            parent[find(h)] = find(a)

    played_post = set(post["home_team"]) | set(post["away_team"])
    comps: dict[str, list[str]] = {}
    for t in teams:
        if t in played_post:
            comps.setdefault(find(t), []).append(t)
    if not comps or max(len(c) for c in comps.values()) > 0.7 * len(teams):
        return None
    rank = {t: i for i, t in enumerate(reg_order)}
    ordered = sorted(comps.values(), key=lambda c: min(rank[t] for t in c))
    out: dict[str, int] = {}
    for gi, comp in enumerate(ordered):
        for t in comp:
            out[t] = gi
    for t in teams:                       # no post rows → trailing group
        out.setdefault(t, len(ordered))
    return out


def format_classification(season_df: pd.DataFrame, fmt: dict,
                          teams: list[str]) -> dict[str, dict]:
    """{team: {group, pts, gd}} — official classification inputs.

    group: 0-based classification-group index (0 = championship group; the
    last implicit group collects teams outside `fmt["groups"]`). Before any
    post-regular rows exist, groups follow the current regular table (which
    equals the plain table — no behavioural change mid-regular-season).
    pts: carry-transformed regular points + post-regular points.
    """
    n = len(teams)
    regular_games = fmt["rr"] * (n - 1)
    df = season_df.sort_values("date", kind="stable")
    mask = regular_phase_mask(df, regular_games)
    reg, post = df[mask], df[~mask]

    reg_t = _table(reg, teams)
    reg_order = sorted(teams, key=lambda x: (-reg_t[x]["pts"], -reg_t[x]["gd"], x))

    group_of = groups_from_post(post, teams, reg_order)
    if group_of is None:                  # no/degenerate post rows → table seeding
        group_of = {}
        start = 0
        for gi, size in enumerate(fmt["groups"]):
            for t in reg_order[start:start + size]:
                group_of[t] = gi
            start += size
        for t in reg_order[start:]:
            group_of[t] = len(fmt["groups"])

    post_t = _table(post, teams)
    out = {}
    for t in teams:
        entry = (math.ceil(reg_t[t]["pts"] / 2) if fmt["carry"] == "half" and len(post)
                 else reg_t[t]["pts"])
        out[t] = {"group": group_of[t],
                  "pts": entry + post_t[t]["pts"],
                  "gd": reg_t[t]["gd"] + post_t[t]["gd"]}
    return out
