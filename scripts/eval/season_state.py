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
