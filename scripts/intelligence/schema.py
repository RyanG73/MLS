"""Versioned contracts shared by Intelligence Hub builders and endpoints."""
from __future__ import annotations

SCHEMA_VERSION = 1
SIMULATION_VERSION = "v1"
FEATURE_STATES = {"live", "thin_history", "unavailable"}
FEATURES = {
    1: "Team Intelligence Brief",
    2: "Since You Last Checked",
    3: "Why It Changed",
    4: "Match Leverage Radar",
    5: "Scenario Explorer",
    6: "Path to the Goal",
    7: "Smart Alerts",
    8: "Personalized Briefing",
    9: "Race Context",
    10: "Expectation Versus Performance",
    11: "Forecast Time Machine",
    12: "Consensus Disagreement",
    13: "Schedule Difficulty Outlook",
    14: "Critical Date Calendar",
    15: "Model Confidence and Fragility",
    16: "Ask Entenser",
    17: "Turning-Point Detection",
    18: "Prediction Receipts",
    19: "Rival Comparison Mode",
    20: "Conversation Cards",
    21: "Creator Mode",
    22: "Team Thesis",
    23: "What Would Change the Model's Mind?",
    24: "Historical Analogs and Club Baselines",
    25: "Break and Offseason Intelligence Mode",
    26: "Personal Forecast Journal",
}
TARGET_LABELS = {
    "title": "title", "playoff": "playoffs", "playoffs": "playoffs",
    "shield": "Shield", "cup": "MLS Cup", "hfa": "home-field advantage",
    "spoon": "last place", "conf_win": "conference title",
    "ucl": "Champions League qualification", "europa": "Europa League qualification",
    "conf": "Conference League qualification", "releg": "relegation",
    "promo": "automatic promotion", "promoted": "promotion",
    "liguilla": "Liguilla qualification", "premiers": "Premiers Plate",
    "finals": "Finals Series", "continental": "continental qualification",
}


def state(status: str, data=None, reason: str | None = None, **meta) -> dict:
    result = {"status": status, "data": data}
    if reason:
        result["reason"] = reason
    result.update(meta)
    return result


def feature(feature_id: int, status: str, data=None,
            reason: str | None = None, **meta) -> dict:
    return {
        "feature_id": feature_id,
        "name": FEATURES[feature_id],
        **state(status, data, reason, **meta),
    }
