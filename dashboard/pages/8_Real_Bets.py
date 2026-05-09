"""
Page 8 — Real Bet Tracker.
Log actual real-money bets you've placed to track real performance
alongside simulated performance.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from data_pipeline import db_utils
from market.risk_rules import (
    log_real_bet,
    settle_real_bet,
    get_real_bet_summary,
    betting_paused,
)

st.set_page_config(page_title="Real Bets — MLS Dashboard", layout="wide")
st.title("💵 Real Bet Tracker")
st.markdown(
    "Log actual real-money bets you've placed. Compare your real ROI "
    "to the simulated model to validate that you're capturing the model's edge."
)

if betting_paused():
    paused_reason = db_utils.get_state("betting_paused_reason", "Stop-loss triggered")
    st.warning(f"⛔ **Betting paused** — {paused_reason}")
    if st.button("Clear pause"):
        from market.risk_rules import clear_betting_paused
        clear_betting_paused()
        st.rerun()

# ── Summary ──────────────────────────────────────────────────────────────────
summary = get_real_bet_summary()
if summary:
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Bets Settled",   summary.get("n_bets", 0))
    c2.metric("Total Staked",   f"{summary.get('total_stake', 0):,.2f}")
    c3.metric("Total P&L",      f"{summary.get('total_pnl', 0):+,.2f}")
    c4.metric("ROI",            f"{summary.get('roi', 0):.2%}")
else:
    st.info("No settled real bets yet. Log your first bet below.")

# ── Log a new bet ────────────────────────────────────────────────────────────
st.markdown("---")
st.markdown("## Log New Bet")

upcoming = db_utils.query(
    """
    SELECT match_id, date, home_team, away_team
    FROM matches
    WHERE status = 'scheduled' AND date >= current_date
    ORDER BY date LIMIT 50
    """
)
match_options = {
    f"{r['home_team']} vs {r['away_team']} ({r['date']})": r["match_id"]
    for _, r in upcoming.iterrows()
}

with st.form("log_real_bet"):
    col1, col2 = st.columns(2)
    with col1:
        match_choice = st.selectbox("Match", list(match_options.keys()))
        bookmaker    = st.text_input("Bookmaker", placeholder="DraftKings / FanDuel / Pinnacle")
        market       = st.selectbox("Market", ["h2h", "totals"])
        outcome      = st.selectbox("Outcome", ["home", "draw", "away", "over", "under"])
    with col2:
        stake = st.number_input("Stake (units)", min_value=0.0, step=1.0)
        odds  = st.number_input("Decimal odds", min_value=1.01, step=0.01)
        notes = st.text_area("Notes (optional)", height=80)

    submitted = st.form_submit_button("Log Bet")
    if submitted and match_choice and stake > 0 and odds > 1:
        bet_id = log_real_bet(
            match_options[match_choice],
            bookmaker, market, outcome, stake, odds, notes,
        )
        st.success(f"Bet logged: {bet_id}")

# ── Pending settlement ───────────────────────────────────────────────────────
st.markdown("---")
st.markdown("## Pending Bets (need settlement)")

pending = db_utils.query(
    """
    SELECT rb.*, m.home_team, m.away_team, m.date,
           m.home_goals, m.away_goals, m.status
    FROM real_bets rb
    JOIN matches m ON rb.match_id = m.match_id
    WHERE rb.result IS NULL
    ORDER BY m.date
    """
)

if pending.empty:
    st.info("No pending real bets.")
else:
    for _, row in pending.iterrows():
        col1, col2, col3 = st.columns([3, 2, 2])
        with col1:
            st.markdown(f"**{row['home_team']} vs {row['away_team']}** ({row['date']})")
            st.caption(f"{row['outcome']} @ {row['odds']:.2f} stake {row['stake']:.1f} on {row['bookmaker']}")
        with col2:
            if row["status"] == "completed" and row.get("home_goals") is not None:
                hg, ag = int(row["home_goals"]), int(row["away_goals"])
                actual = "home" if hg > ag else ("draw" if hg == ag else "away")
                won = (row["outcome"] == actual)
                if row["market"] == "totals":
                    total = hg + ag
                    won = (row["outcome"] == "over" and total > 2.5) or \
                          (row["outcome"] == "under" and total <= 2.5)
                st.markdown(f"Result: **{hg}-{ag}** → {'✅ won' if won else '❌ lost'}")
                if st.button("Settle as " + ("Won" if won else "Lost"), key=f"settle_{row['bet_id']}"):
                    settle_real_bet(row["bet_id"], won)
                    st.rerun()
            else:
                st.caption("Match not yet completed")
        with col3:
            if st.button("Manual settle: Won", key=f"won_{row['bet_id']}"):
                settle_real_bet(row["bet_id"], True)
                st.rerun()
            if st.button("Manual settle: Lost", key=f"lost_{row['bet_id']}"):
                settle_real_bet(row["bet_id"], False)
                st.rerun()

# ── Settled history ──────────────────────────────────────────────────────────
st.markdown("---")
st.markdown("## Settled Bet History")

settled = db_utils.query(
    """
    SELECT rb.*, m.home_team, m.away_team, m.date
    FROM real_bets rb
    JOIN matches m ON rb.match_id = m.match_id
    WHERE rb.result IS NOT NULL
    ORDER BY m.date DESC
    """
)
if not settled.empty:
    settled["date"] = pd.to_datetime(settled["date"])
    settled_sorted = settled.sort_values("date")
    settled_sorted["cum_pnl"] = settled_sorted["pnl"].cumsum()

    fig = go.Figure(go.Scatter(
        x=settled_sorted["date"], y=settled_sorted["cum_pnl"],
        mode="lines", fill="tozeroy",
        line=dict(color="#27ae60", width=2),
    ))
    fig.add_hline(y=0, line_color="gray", line_dash="dot")
    fig.update_layout(height=300, xaxis_title="Date",
                       yaxis_title="Cumulative P&L (units)", margin=dict(t=10))
    st.plotly_chart(fig, use_container_width=True)

    show = settled[["date", "home_team", "away_team", "outcome",
                     "stake", "odds", "result", "pnl", "bookmaker"]].copy()
    show.columns = ["Date", "Home", "Away", "Outcome", "Stake",
                     "Odds", "Result", "P&L", "Book"]

    st.dataframe(
        show.style.format({"Stake": "{:.1f}", "Odds": "{:.2f}", "P&L": "{:+.2f}"}),
        use_container_width=True, height=400,
    )

    csv = show.to_csv(index=False).encode("utf-8")
    st.download_button("📥 Download CSV", csv, "real_bets.csv", "text/csv")
else:
    st.info("No settled bets yet.")
