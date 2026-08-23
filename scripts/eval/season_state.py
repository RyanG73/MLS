"""Shared season-state detection for the league and continental builds."""
from __future__ import annotations

BETWEEN = "between"        # edition not started / not drawn yet (nothing played, nothing scheduled)
PRESEASON = "preseason"    # schedule published but nothing played yet (played==0, upcoming>0)
IN_PROGRESS = "in_progress"
CONCLUDED = "concluded"


def season_state(played_count: int, upcoming_count: int, *,
                 final_played: bool | None = None) -> str:
    """Classify an edition's state from match counts.

    - PRESEASON:   schedule is out but nothing played yet (played_count == 0, upcoming_count > 0).
    - BETWEEN:     nothing played and nothing scheduled (played_count == 0, upcoming_count == 0).
    - IN_PROGRESS: some matches played and there are upcoming fixtures (upcoming_count > 0).
    - CONCLUDED:   played, no upcoming, AND (if final_played is given) the final is done.
                   For competitions with a knockout final (continental), pass
                   final_played; for round-robin leagues leave it None.
    """
    if played_count <= 0:
        if upcoming_count > 0:
            return PRESEASON
        return BETWEEN
    if upcoming_count > 0:
        return IN_PROGRESS
    if final_played is False:        # explicitly not-yet-decided knockout
        return IN_PROGRESS
    return CONCLUDED


# A CONCLUDED verdict from season_state() rests entirely on `upcoming_count == 0`,
# and that number carries two different meanings the classifier cannot separate:
# the league has no more fixtures, or we failed to fetch the ones it has. The
# helpers below let a caller cross-examine the verdict against the league's own
# playing record before publishing "final".
#
# Measured 2026-08-23 over the 94 committed payloads: the eight leagues wrongly
# published as complete had last played 7-20 days before the build, while every
# genuinely finished season had been idle >= 84 days. A recency test alone is
# NOT safe, though — in-season quiet spells reach 63 days (the Conference League
# winter break) and 60 days (Argentina's mid-season gap), so the two bands very
# nearly touch. The games-played test is what carries the decision; the idle
# window only breaks the tie for a season that ended early and stayed ended.
MAX_IDLE_DAYS = 30


def typical_games(per_club_counts) -> int | None:
    """Games the TYPICAL club played, from a season's per-club game counts.

    The median, deliberately, not the maximum. Relegation play-offs and
    qualification rounds live in the same source frames as league fixtures, so
    the busiest club in a 30-round Allsvenskan season shows 32 — and a yardstick
    built from that reads the NEXT completed 30-round season as two games short.
    The median is unmoved by a handful of clubs playing extra, and it also
    absorbs a club-count change that shifts the maximum but not the format.
    """
    counts = sorted(int(c) for c in per_club_counts)
    if not counts:
        return None
    mid = len(counts) // 2
    if len(counts) % 2:
        return counts[mid]
    return (counts[mid - 1] + counts[mid]) // 2


def expected_games_per_team(prior_seasons: dict[int, int], n_teams: int) -> int | None:
    """Games a club plays in a full campaign, MEASURED from this league's history.

    `prior_seasons` maps season → `typical_games` for that season, and must
    contain only seasons that have already finished. The most recent one wins: club
    counts and formats change, and last year's campaign is the closest thing to
    a statement of this year's length.

    Falls back to one round-robin when there is no history, which reproduces the
    original `nT - 1` guard for a league in its first season here. Returns None
    only when neither is available, meaning no verdict can be reached.
    """
    if prior_seasons:
        return prior_seasons[max(prior_seasons)]
    return n_teams - 1 if n_teams > 1 else None


def looks_unfinished(games_played: int, expected_games: int | None,
                     idle_days: int | None, *,
                     max_idle_days: int = MAX_IDLE_DAYS) -> bool:
    """True when a CONCLUDED verdict is contradicted by the league's own record.

    Two conditions, both required. The clubs are short of a full campaign, AND
    the league was playing recently enough that the silence is better explained
    by a dark fixture feed than by a season that is over. Dropping the second
    condition would strand a legitimately shortened season (the 2025-26 Indian
    Super League, cut to three months) in progress forever.
    """
    if expected_games is None or games_played >= expected_games:
        return False
    return idle_days is not None and idle_days <= max_idle_days
