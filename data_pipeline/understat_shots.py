"""Per-match shot-level event data from Understat (understatapi), for the
momentum-chart feature (2026-07-14: "this github repo allows us to create
momentum charts for completed matches ... incorporate this into game
results" — github.com/JakeBonnici22/match-momentum).

Big-5 leagues only — Understat's coverage doesn't extend further (see
UNDERSTAT_CODES in data_pipeline/understat.py). Every shot carries a minute,
xG, team side (h/a), and result (Goal/SavedShot/MissedShots/BlockedShot/
OwnGoal), which is exactly the event stream the momentum algorithm needs.

Disk-cached per match_id (shots for a finished match never change), so a
build only ever fetches NEW completed matches, not the whole archive.
"""
from __future__ import annotations

import json
from pathlib import Path

_CACHE_DIR = Path("data/understat_shots")


def match_shots(match_id: str, use_cache: bool = True) -> dict[str, list[dict]] | None:
    """{'h': [...], 'a': [...]} shot dicts for one Understat match, or None on failure."""
    cache_path = _CACHE_DIR / f"{match_id}.json"
    if use_cache and cache_path.exists():
        return json.loads(cache_path.read_text())
    from understatapi import UnderstatClient  # optional dep, same as understat.py
    try:
        with UnderstatClient() as client:
            shots = client.match(match=str(match_id)).get_shot_data()
    except Exception:
        return None
    if not shots or ("h" not in shots and "a" not in shots):
        return None
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(shots))
    return shots
