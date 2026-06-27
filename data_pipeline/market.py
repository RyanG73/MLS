"""Market math primitives: de-vig, edge computation, CLV.

Note: edge_pct() is duplicated in legacy/market/kelly.py — the canonical version is here.
"""
import math


def devig(home_odds: float, draw_odds: float, away_odds: float) -> dict:
    """Proportional de-vig: decimal odds → fair implied probabilities.

    Args:
        home_odds: Decimal odds for home win (must be > 1.0)
        draw_odds: Decimal odds for draw (must be > 1.0)
        away_odds: Decimal odds for away win (must be > 1.0)

    Returns:
        Dict with keys 'home', 'draw', 'away' containing fair probabilities summing to 1.0

    Raises:
        ValueError: If any odds ≤ 1.0 or is NaN/None
    """
    if not home_odds or home_odds <= 1.0 or math.isnan(home_odds):
        raise ValueError(f"Invalid home_odds: {home_odds}")
    if not draw_odds or draw_odds <= 1.0 or math.isnan(draw_odds):
        raise ValueError(f"Invalid draw_odds: {draw_odds}")
    if not away_odds or away_odds <= 1.0 or math.isnan(away_odds):
        raise ValueError(f"Invalid away_odds: {away_odds}")

    # Proportional vig removal: convert odds to implied probabilities, then normalize
    inv_home = 1.0 / home_odds
    inv_draw = 1.0 / draw_odds
    inv_away = 1.0 / away_odds

    total = inv_home + inv_draw + inv_away

    return {
        "home": inv_home / total,
        "draw": inv_draw / total,
        "away": inv_away / total,
    }


def edge_pct(model_prob: float, market_implied: float) -> float:
    """Model edge in percentage points.

    Positive when model probability exceeds market implied probability,
    indicating perceived value.

    Args:
        model_prob: Model's estimated probability; must be finite and in [0.0-1.0]
        market_implied: Market's implied probability; must be finite and in [0.0-1.0]

    Returns:
        Edge in percentage points (positive = model sees value)

    Raises:
        ValueError: If either argument is NaN or not finite
    """
    if not math.isfinite(model_prob) or not math.isfinite(market_implied):
        raise ValueError(f"Invalid inputs: model_prob={model_prob}, market_implied={market_implied}")
    return (model_prob - market_implied) * 100.0


def clv_pp(open_implied: float, close_implied: float) -> float:
    """Closing line value in percentage points from bettor's perspective.

    Positive when closing line moved toward our position (implied prob increased),
    meaning we got better odds.

    Args:
        open_implied: Implied probability when bet was placed; must be finite and in [0.0-1.0]
        close_implied: Implied probability at close (when we settled/cashed); must be finite and in [0.0-1.0]

    Returns:
        CLV in percentage points (positive = favorable line movement)

    Raises:
        ValueError: If either argument is NaN or not finite
    """
    if not math.isfinite(open_implied) or not math.isfinite(close_implied):
        raise ValueError(f"Invalid inputs: open_implied={open_implied}, close_implied={close_implied}")
    return (close_implied - open_implied) * 100.0
