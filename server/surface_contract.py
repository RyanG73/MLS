"""Canonical club forecast fields shared by every customer-facing surface."""
from __future__ import annotations


def club_surface_contract(record: dict) -> dict:
    """Project one team artifact into the cross-surface identity contract."""
    features = record.get("features") or {}
    brief = (features.get("1") or {}).get("data") or {}
    value = {
        "league_id": record.get("league_id"),
        "league_name": record.get("league_name"),
        "team_id": record.get("team_id"),
        "team": record.get("team"),
        "season_id": str(record.get("season_id") or ""),
        "generated": record.get("generated"),
        "snapshot_id": record.get("snapshot_id"),
        "target_metric": record.get("target_metric"),
        "current_probability_pct": brief.get("current_pct"),
    }
    required = {
        "league_id", "league_name", "team_id", "team", "season_id",
        "generated", "snapshot_id", "target_metric",
    }
    missing = sorted(key for key in required if not value.get(key))
    if missing:
        raise ValueError(f"surface contract missing fields: {missing}")
    probability = value["current_probability_pct"]
    if probability is not None and not 0 <= float(probability) <= 100:
        raise ValueError(
            "surface contract current_probability_pct must be 0 to 100")
    return value
