"""Bookmaker implied probability helpers.

Uses penaltyblog when available and falls back to proportional vig removal.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def _fallback_vig_adjusted_prob(
    home_odds: float,
    draw_odds: float,
    away_odds: float,
) -> dict:
    raw_h = 1.0 / home_odds if home_odds and home_odds > 0 else 0.0
    raw_d = 1.0 / draw_odds if draw_odds and draw_odds > 0 else 0.0
    raw_a = 1.0 / away_odds if away_odds and away_odds > 0 else 0.0
    total = raw_h + raw_d + raw_a
    if total <= 0:
        return {"home": 1 / 3, "draw": 1 / 3, "away": 1 / 3, "overround": 0.0, "method": "fallback"}
    return {
        "home": raw_h / total,
        "draw": raw_d / total,
        "away": raw_a / total,
        "overround": total - 1.0,
        "method": "proportional",
    }


def vig_adjusted_prob(
    home_odds: float,
    draw_odds: float,
    away_odds: float,
    method: str = "multiplicative",
) -> dict:
    """Return vig-adjusted implied probabilities for h2h odds."""
    odds = [home_odds, draw_odds, away_odds]
    if any(o is None or o <= 0 for o in odds):
        return _fallback_vig_adjusted_prob(home_odds, draw_odds, away_odds)

    try:
        import penaltyblog as pb

        if hasattr(pb.implied, "calculate_implied"):
            result = pb.implied.calculate_implied(
                odds,
                method=method,
                odds_format="decimal",
                market_names=["home", "draw", "away"],
            )
            probs = getattr(result, "probabilities_dict", None)
            if probs is None:
                probs = dict(zip(["home", "draw", "away"], result.probabilities))
            return {
                "home": float(probs["home"]),
                "draw": float(probs["draw"]),
                "away": float(probs["away"]),
                "overround": float(getattr(result, "margin", 0.0)),
                "method": str(getattr(getattr(result, "method", method), "value", method)),
            }

        legacy = getattr(pb.implied, method)(odds)
        probs = legacy.get("implied_probabilities", legacy.get("probabilities"))
        return {
            "home": float(probs[0]),
            "draw": float(probs[1]),
            "away": float(probs[2]),
            "overround": float(legacy.get("margin", 0.0)),
            "method": str(legacy.get("method", method)),
        }
    except Exception as exc:
        logger.debug("penaltyblog implied probability fallback: %s", exc)
        return _fallback_vig_adjusted_prob(home_odds, draw_odds, away_odds)
