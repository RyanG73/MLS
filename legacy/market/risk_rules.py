"""
Risk management rules:
- Drawdown stop-loss (pause new bets after large drawdowns)
- Hard cap on individual stake size
- Real-bet tracking (parallel to simulated_bets)
"""

import hashlib
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

import pandas as pd

from data_pipeline import db_utils

logger = logging.getLogger(__name__)

# ─── Stop-loss ────────────────────────────────────────────────────────────────

DRAWDOWN_LIMIT_PCT = 15.0     # Pause if 30-day drawdown exceeds this %
DRAWDOWN_WINDOW_DAYS = 30
HARD_CAP_PCT = 10.0           # Max single-bet size as % of bankroll


def betting_paused() -> bool:
    """Check if the betting_paused flag is set in system_state."""
    state = db_utils.get_state("betting_paused", "false")
    return str(state).lower() in {"true", "1", "yes"}


def set_betting_paused(reason: str) -> None:
    db_utils.set_state("betting_paused", "true")
    db_utils.set_state("betting_paused_reason", reason)
    db_utils.set_state("betting_paused_at", datetime.now(timezone.utc).isoformat())
    logger.warning("Betting paused: %s", reason)


def clear_betting_paused() -> None:
    db_utils.set_state("betting_paused", "false")
    db_utils.set_state("betting_paused_reason", "")


def check_drawdown_and_pause(starting_bankroll: float = 10000.0) -> Optional[str]:
    """
    Inspect simulated bet P&L over the last DRAWDOWN_WINDOW_DAYS days.
    If cumulative drawdown exceeds DRAWDOWN_LIMIT_PCT, set betting_paused.
    Returns the pause reason (str) if paused, or None.
    """
    df = db_utils.query(
        f"""
        SELECT placed_at, pnl_kelly25
        FROM simulated_bets
        WHERE result IS NOT NULL
          AND placed_at >= NOW() - INTERVAL '{DRAWDOWN_WINDOW_DAYS} days'
        ORDER BY placed_at
        """
    )
    if df.empty or df["pnl_kelly25"].isna().all():
        return None

    cum = df["pnl_kelly25"].cumsum()
    roll_max = cum.cummax()
    drawdown_units = (cum - roll_max).min()
    drawdown_pct = abs(drawdown_units) / starting_bankroll * 100

    if drawdown_pct >= DRAWDOWN_LIMIT_PCT:
        reason = f"30-day drawdown {drawdown_pct:.1f}% >= limit {DRAWDOWN_LIMIT_PCT}%"
        set_betting_paused(reason)
        return reason

    return None


# ─── Hard bet cap ─────────────────────────────────────────────────────────────

def apply_hard_cap(stake: float, bankroll: float) -> float:
    """Cap a stake at HARD_CAP_PCT of the current bankroll."""
    cap = bankroll * (HARD_CAP_PCT / 100.0)
    return min(stake, cap)


# ─── Real-bet tracking ───────────────────────────────────────────────────────

def log_real_bet(
    match_id: str,
    bookmaker: str,
    market: str,
    outcome: str,
    stake: float,
    odds: float,
    notes: str = "",
) -> str:
    """Insert a real bet placed by the user."""
    bet_id = hashlib.md5(
        f"{match_id}_{bookmaker}_{outcome}_{datetime.now().isoformat()}".encode()
    ).hexdigest()[:20]
    db_utils.execute(
        """
        INSERT INTO real_bets
            (bet_id, match_id, bookmaker, market, outcome, stake, odds, placed_at, notes)
        VALUES (%s, %s, %s, %s, %s, %s, %s, NOW(), %s)
        """,
        [bet_id, match_id, bookmaker, market, outcome, stake, odds, notes],
    )
    return bet_id


def settle_real_bet(bet_id: str, won: bool) -> None:
    """Settle a real bet and compute P&L."""
    df = db_utils.query("SELECT stake, odds FROM real_bets WHERE bet_id = %s", [bet_id])
    if df.empty:
        return
    stake = float(df["stake"].iloc[0])
    odds = float(df["odds"].iloc[0])
    pnl = stake * (odds - 1.0) if won else -stake
    db_utils.execute(
        "UPDATE real_bets SET result = %s, pnl = %s WHERE bet_id = %s",
        ["won" if won else "lost", pnl, bet_id],
    )


def get_real_bet_summary() -> dict:
    df = db_utils.query("SELECT * FROM real_bets WHERE result IS NOT NULL")
    if df.empty:
        return {}
    total_stake = df["stake"].sum()
    total_pnl   = df["pnl"].sum()
    wins        = (df["result"] == "won").sum()
    return {
        "n_bets":      len(df),
        "total_stake": float(total_stake),
        "total_pnl":   float(total_pnl),
        "roi":         (total_pnl / total_stake) if total_stake > 0 else 0.0,
        "win_rate":    wins / len(df),
    }
