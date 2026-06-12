"""
Closing Line Value (CLV) tracker.

CLV measures whether the model consistently beats the line that the
market converges to at kickoff. Positive CLV is the industry-standard
signal of a genuine edge.

CLV = closing_implied_prob - opening_implied_prob (from our perspective)
If we backed a team at 35% implied (odds: 2.86) and the line closed at 40%,
we got value (CLV = +5pp) because the market moved in our direction.
"""

import hashlib
import logging
from datetime import datetime, timezone
from typing import Optional

import pandas as pd

from config import SETTINGS
from data_pipeline import db_utils
from market.kelly import (
    vig_adjusted_prob,
    edge_pct,
    kelly_stakes,
    decimal_to_implied_prob,
)

logger = logging.getLogger(__name__)

_MKT_CFG = SETTINGS["market"]
_EDGE_THRESHOLD = _MKT_CFG["default_edge_threshold_pct"]
_BANKROLL = _MKT_CFG["starting_bankroll"]
_KELLY_FRACTIONS = _MKT_CFG["kelly_fractions"]


def evaluate_match(
    match_id: str,
    model_probs: dict,
    opening_odds: dict,
    closing_odds: Optional[dict] = None,
    result: Optional[str] = None,
    edge_threshold_pct: float = _EDGE_THRESHOLD,
) -> list[dict]:
    """
    Evaluate model vs market for a match, generating simulated bet records.

    Parameters
    ----------
    match_id : internal match identifier
    model_probs : {prob_home, prob_draw, prob_away} from ensemble
    opening_odds : {home: decimal, draw: decimal, away: decimal} from Pinnacle
    closing_odds : same structure; optional (for CLV calculation)
    result : 'home', 'draw', or 'away' — the actual match result
    edge_threshold_pct : only create bets when edge exceeds this threshold

    Returns list of bet dicts (one per outcome with positive edge above threshold).
    """
    if not opening_odds:
        return []

    open_home = opening_odds.get("home", 0)
    open_draw = opening_odds.get("draw", 0)
    open_away = opening_odds.get("away", 0)

    open_implied = vig_adjusted_prob(open_home, open_draw, open_away)

    bets = []
    for outcome, model_key in [("home", "prob_home"), ("draw", "prob_draw"), ("away", "prob_away")]:
        model_p = model_probs.get(model_key, 0.0)
        market_p = open_implied.get(outcome, 0.0)
        edge = edge_pct(model_p, market_p)

        if edge < edge_threshold_pct:
            continue

        open_dec = opening_odds.get(outcome, 0)
        if open_dec <= 1.0:
            continue

        stakes = kelly_stakes(model_p, open_dec)
        stake_25 = stakes.get("kelly_25", 0.0) * _BANKROLL
        stake_50 = stakes.get("kelly_50", 0.0) * _BANKROLL

        # Determine actual result and P&L
        won = (result == outcome) if result else None
        if won is None:
            pnl_25 = pnl_50 = None
            result_str = None
        elif won:
            pnl_25 = stake_25 * (open_dec - 1.0)
            pnl_50 = stake_50 * (open_dec - 1.0)
            result_str = "won"
        else:
            pnl_25 = -stake_25
            pnl_50 = -stake_50
            result_str = "lost"

        # CLV calculation
        clv = None
        if closing_odds:
            close_implied = vig_adjusted_prob(
                closing_odds.get("home", open_home),
                closing_odds.get("draw", open_draw),
                closing_odds.get("away", open_away),
            )
            open_p = open_implied.get(outcome, 0)
            close_p = close_implied.get(outcome, 0)
            clv = (close_p - open_p) * 100  # Positive = market moved toward our bet

        bet_id = hashlib.md5(f"{match_id}_{outcome}".encode()).hexdigest()[:20]
        bets.append({
            "bet_id": bet_id,
            "match_id": match_id,
            "market": "h2h",
            "outcome_backed": outcome,
            "model_prob": model_p,
            "market_prob": market_p,
            "edge_pct": edge,
            "open_odds": open_dec,
            "close_odds": closing_odds.get(outcome) if closing_odds else None,
            "clv": clv,
            "stake_kelly25": stake_25,
            "stake_kelly50": stake_50,
            "result": result_str,
            "pnl_kelly25": pnl_25,
            "pnl_kelly50": pnl_50,
            "placed_at": datetime.now(timezone.utc).isoformat(),
        })

    return bets


def store_bets(bets: list[dict]) -> None:
    """Upsert simulated bet records."""
    if not bets:
        return
    df = pd.DataFrame(bets)
    db_utils.upsert_dataframe(df, "simulated_bets", ["bet_id"])
    logger.info("Stored %d simulated bets.", len(bets))


def update_bet_results(
    match_id: str,
    result: str,
    close_home: float | None = None,
    close_draw: float | None = None,
    close_away: float | None = None,
) -> None:
    """
    After a match completes, update the P&L and closing line value for bets on that match.
    Call once the match result is known.
    """
    bets_df = db_utils.query(
        "SELECT * FROM simulated_bets WHERE match_id = %s AND result IS NULL",
        [match_id],
    )
    if bets_df.empty:
        return

    if close_home is None or close_away is None:
        from data_pipeline.odds_client import get_pinnacle_odds
        closing = get_pinnacle_odds(match_id, snapshot_type="close") or {}
        close_home = closing.get("home")
        close_draw = closing.get("draw")
        close_away = closing.get("away")

    if close_home is None or close_away is None:
        logger.warning("No closing odds available for %s; settling P&L without CLV.", match_id)

    close_implied = (
        vig_adjusted_prob(close_home, close_draw, close_away)
        if close_home and close_away else {}
    )

    for idx, row in bets_df.iterrows():
        outcome = row["outcome_backed"]
        won = (result == outcome)
        open_dec = row["open_odds"] or 0
        stake_25 = row["stake_kelly25"] or 0
        stake_50 = row["stake_kelly50"] or 0

        pnl_25 = stake_25 * (open_dec - 1.0) if won else -stake_25
        pnl_50 = stake_50 * (open_dec - 1.0) if won else -stake_50

        open_implied_p = row["market_prob"]
        close_p = close_implied.get(outcome, 0)
        clv = (close_p - open_implied_p) * 100 if close_home and close_away else None

        db_utils.execute(
            """
            UPDATE simulated_bets
            SET result = %s, pnl_kelly25 = %s, pnl_kelly50 = %s, clv = %s,
                close_odds = %s
            WHERE bet_id = %s
            """,
            [
                "won" if won else "lost",
                pnl_25, pnl_50, clv,
                {"home": close_home, "draw": close_draw, "away": close_away}.get(outcome),
                row["bet_id"],
            ],
        )

    logger.info("Updated %d bet results for match %s.", len(bets_df), match_id)


def get_performance_summary(
    season: Optional[int] = None,
    edge_threshold: float = 0.0,
) -> dict:
    """
    Return aggregate performance stats from the simulated_bets table.
    """
    where_clauses = ["result IS NOT NULL"]
    params = []
    if season:
        where_clauses.append(
            "match_id IN (SELECT match_id FROM matches WHERE season = %s)"
        )
        params.append(season)
    if edge_threshold > 0:
        where_clauses.append("edge_pct >= %s")
        params.append(edge_threshold)

    where = " AND ".join(where_clauses)
    df = db_utils.query(f"SELECT * FROM simulated_bets WHERE {where}", params)

    if df.empty:
        return {}

    n_bets = len(df)
    n_won = (df["result"] == "won").sum()
    total_staked_25 = df["stake_kelly25"].sum()
    total_staked_50 = df["stake_kelly50"].sum()
    total_pnl_25 = df["pnl_kelly25"].sum()
    total_pnl_50 = df["pnl_kelly50"].sum()
    avg_clv = df["clv"].mean() if "clv" in df.columns else None

    # Max drawdown (Kelly 25)
    cumulative = df["pnl_kelly25"].cumsum()
    roll_max = cumulative.cummax()
    drawdown = cumulative - roll_max
    max_dd = float(drawdown.min()) if not drawdown.empty else 0.0

    return {
        "n_bets": n_bets,
        "win_rate": n_won / n_bets if n_bets > 0 else 0.0,
        "roi_kelly25": total_pnl_25 / total_staked_25 if total_staked_25 > 0 else 0.0,
        "roi_kelly50": total_pnl_50 / total_staked_50 if total_staked_50 > 0 else 0.0,
        "total_pnl_kelly25": float(total_pnl_25),
        "total_pnl_kelly50": float(total_pnl_50),
        "avg_clv_pct": float(avg_clv) if avg_clv is not None else None,
        "max_drawdown_kelly25": max_dd,
    }
