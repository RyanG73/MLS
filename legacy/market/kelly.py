"""
Fractional Kelly criterion stake sizing.

Kelly formula: f = (b * p - q) / b
  where b = decimal_odds - 1
        p = model probability
        q = 1 - p

Fractional Kelly: f_k = fraction * f
Stakes are expressed as a proportion of the current bankroll.
"""

from config import SETTINGS
from market.implied import vig_adjusted_prob

_MKT_CFG = SETTINGS["market"]
_STARTING_BANKROLL = _MKT_CFG["starting_bankroll"]
_KELLY_FRACTIONS = _MKT_CFG["kelly_fractions"]


def full_kelly(prob: float, decimal_odds: float) -> float:
    """
    Full Kelly stake as a fraction of bankroll.
    Returns 0 if the bet has no positive expected value.
    """
    if decimal_odds <= 1.0 or prob <= 0.0 or prob >= 1.0:
        return 0.0
    b = decimal_odds - 1.0
    q = 1.0 - prob
    f = (b * prob - q) / b
    return max(f, 0.0)


def fractional_kelly(prob: float, decimal_odds: float, fraction: float) -> float:
    """Fractional Kelly stake as a fraction of bankroll."""
    return fraction * full_kelly(prob, decimal_odds)


def kelly_stakes(prob: float, decimal_odds: float) -> dict[str, float]:
    """
    Return stake fractions for all configured Kelly fractions.
    E.g., kelly_fractions = [0.25, 0.50] returns {'kelly_25': f1, 'kelly_50': f2}.
    Also returns 'kelly_full' for reference.
    """
    fk = full_kelly(prob, decimal_odds)
    result: dict[str, float] = {"kelly_full": fk}
    for frac in _KELLY_FRACTIONS:
        label = f"kelly_{int(frac * 100)}"
        result[label] = frac * fk
    return result


def units_staked(prob: float, decimal_odds: float, bankroll: float) -> dict[str, float]:
    """Return actual unit amounts (not fractions) for each Kelly fraction."""
    fractions = kelly_stakes(prob, decimal_odds)
    return {k: v * bankroll for k, v in fractions.items()}


def edge_pct(model_prob: float, market_prob: float) -> float:
    """
    Model edge in percentage points over the market's implied probability.
    Positive = model thinks outcome is more likely than market.
    """
    return (model_prob - market_prob) * 100.0


def expected_value(model_prob: float, decimal_odds: float) -> float:
    """Expected value per unit staked. Positive = value bet."""
    return model_prob * decimal_odds - 1.0


def decimal_to_implied_prob(decimal_odds: float) -> float:
    """Raw (non-vig-adjusted) implied probability from decimal odds."""
    if decimal_odds <= 0:
        return 0.0
    return 1.0 / decimal_odds

