"""
Page 5 — Simulated Betting Tracker.
Fractional Kelly P&L, CLV tracking, drawdown, and edge threshold analysis.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from config import SETTINGS
from data_pipeline import db_utils
from market.clv_tracker import get_performance_summary

st.set_page_config(page_title="Betting Tracker — MLS Dashboard", layout="wide")
st.title("💰 Simulated Betting Tracker")
st.markdown(
    "Track simulated fractional Kelly bets against Pinnacle odds. "
    "No real money involved — this is a model evaluation tool."
)

_MKT_CFG = SETTINGS["market"]

# ── Sidebar controls ──────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### Filters")
    seasons_available = db_utils.query("SELECT DISTINCT season FROM matches ORDER BY season DESC")
    season_opts = ["All"] + [str(s) for s in seasons_available["season"].tolist()]
    selected_season = st.selectbox("Season", season_opts)

    edge_threshold = st.slider(
        "Min edge threshold (%)",
        0.0, 15.0, _MKT_CFG["default_edge_threshold_pct"], 0.5,
        help="Only show bets where model edge exceeded this percentage"
    )
    kelly_display = st.radio("Kelly fraction", ["25% Kelly", "50% Kelly"])
    stake_col = "stake_kelly25" if kelly_display == "25% Kelly" else "stake_kelly50"
    pnl_col = "pnl_kelly25" if kelly_display == "25% Kelly" else "pnl_kelly50"


@st.cache_data(ttl=60)
def load_bets(season_f: str, edge_min: float) -> pd.DataFrame:
    season_clause = f"AND m.season = {season_f}" if season_f != "All" else ""
    edge_clause = f"AND sb.edge_pct >= {edge_min}" if edge_min > 0 else ""
    return db_utils.query(
        f"""
        SELECT sb.*, m.home_team, m.away_team, m.date, m.season
        FROM simulated_bets sb
        JOIN matches m ON sb.match_id = m.match_id
        WHERE 1=1 {season_clause} {edge_clause}
        ORDER BY m.date, sb.placed_at
        """
    )


bets_df = load_bets(selected_season, edge_threshold)

if bets_df.empty:
    st.info(
        "No simulated bets found with current filters. "
        "Bets are created when the model finds edge above threshold against Pinnacle odds, "
        "and settled after match results are recorded."
    )
    st.stop()

bets_df["date"] = pd.to_datetime(bets_df["date"])
settled = bets_df[bets_df["result"].notna()].copy()
pending = bets_df[bets_df["result"].isna()].copy()

# ── Summary KPIs ───────────────────────────────────────────────────────────────
st.markdown("## Summary Statistics")
summary = get_performance_summary(
    season=int(selected_season) if selected_season != "All" else None,
    edge_threshold=edge_threshold,
)

col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("Total Bets", summary.get("n_bets", 0))
col2.metric("Win Rate", f"{summary.get('win_rate', 0):.1%}")
roi_key = "roi_kelly25" if kelly_display == "25% Kelly" else "roi_kelly50"
col3.metric("ROI", f"{summary.get(roi_key, 0):.2%}",
            delta=f"{summary.get(roi_key, 0)*100:.1f}pp vs 0")
col4.metric("Avg CLV", f"{summary.get('avg_clv_pct', 0) or 0:.2f}%",
            help="Average closing line value. Positive = consistently beat closing line")
col5.metric("Max Drawdown", f"{summary.get('max_drawdown_kelly25', 0):.0f} units")

st.markdown("---")

# ── Cumulative P&L chart ───────────────────────────────────────────────────────
st.markdown(f"## Cumulative P&L — {kelly_display}")
settled_sorted = settled.sort_values("date")
settled_sorted["cumulative_pnl"] = settled_sorted[pnl_col].cumsum()
settled_sorted["cumulative_staked"] = settled_sorted[stake_col].cumsum()
settled_sorted["running_roi"] = settled_sorted["cumulative_pnl"] / settled_sorted["cumulative_staked"].replace(0, np.nan)

fig_pnl = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.7, 0.3],
                         vertical_spacing=0.05)

fig_pnl.add_trace(
    go.Scatter(x=settled_sorted["date"], y=settled_sorted["cumulative_pnl"],
               mode="lines", name="Cumulative P&L",
               fill="tozeroy",
               fillcolor="rgba(26,75,140,0.15)",
               line=dict(color="#1a4b8c", width=2)),
    row=1, col=1
)
fig_pnl.add_hline(y=0, line_color="gray", line_dash="dot", row=1, col=1)

# Running ROI
fig_pnl.add_trace(
    go.Scatter(x=settled_sorted["date"], y=settled_sorted["running_roi"] * 100,
               mode="lines", name="Running ROI %",
               line=dict(color="#27ae60", width=1.5)),
    row=2, col=1
)
fig_pnl.add_hline(y=0, line_color="gray", line_dash="dot", row=2, col=1)

fig_pnl.update_layout(height=450, showlegend=True, margin=dict(t=10))
fig_pnl.update_yaxes(title_text="P&L (units)", row=1, col=1)
fig_pnl.update_yaxes(title_text="ROI (%)", row=2, col=1)
st.plotly_chart(fig_pnl, use_container_width=True)

# Drawdown chart
settled_sorted["rolling_max"] = settled_sorted["cumulative_pnl"].cummax()
settled_sorted["drawdown"] = settled_sorted["cumulative_pnl"] - settled_sorted["rolling_max"]

fig_dd = go.Figure(go.Scatter(
    x=settled_sorted["date"], y=settled_sorted["drawdown"],
    fill="tozeroy", fillcolor="rgba(231,76,60,0.2)",
    line=dict(color="#e74c3c"), name="Drawdown"
))
fig_dd.update_layout(height=180, margin=dict(t=5, b=0),
                      yaxis_title="Drawdown (units)")
st.plotly_chart(fig_dd, use_container_width=True)

# ── CLV distribution ──────────────────────────────────────────────────────────
if "clv" in settled.columns and settled["clv"].notna().sum() > 10:
    st.markdown("## Closing Line Value Distribution")
    col_clv1, col_clv2 = st.columns([2, 1])
    with col_clv1:
        fig_clv = go.Figure(go.Histogram(
            x=settled["clv"], nbinsx=25,
            marker_color="#1a4b8c", opacity=0.8
        ))
        fig_clv.add_vline(x=0, line_color="red", line_dash="dash")
        fig_clv.add_vline(x=settled["clv"].mean(), line_color="green", line_dash="dot",
                           annotation_text=f"Mean: {settled['clv'].mean():.2f}%")
        fig_clv.update_layout(height=250, xaxis_title="CLV (%)", margin=dict(t=10))
        st.plotly_chart(fig_clv, use_container_width=True)
    with col_clv2:
        st.metric("Mean CLV", f"{settled['clv'].mean():.2f}%")
        st.metric("Median CLV", f"{settled['clv'].median():.2f}%")
        st.metric("% Positive CLV", f"{(settled['clv'] > 0).mean():.0%}")

st.markdown("---")

# ── Bet log table ─────────────────────────────────────────────────────────────
st.markdown("## Bet Log")
tab_settled, tab_pending = st.tabs([f"Settled ({len(settled)})", f"Pending ({len(pending)})"])

display_cols = ["date", "home_team", "away_team", "outcome_backed", "edge_pct",
                "open_odds", stake_col, "result", pnl_col, "clv"]
display_cols_exist = [c for c in display_cols if c in bets_df.columns]

with tab_settled:
    show = settled[display_cols_exist].sort_values("date", ascending=False).head(200)
    show = show.rename(columns={
        "outcome_backed": "Backed", "edge_pct": "Edge%",
        "open_odds": "Odds", stake_col: "Stake",
        "result": "Result", pnl_col: "P&L", "clv": "CLV%"
    })

    def color_result(val):
        if val == "won":
            return "background-color: #d5f5e3"
        elif val == "lost":
            return "background-color: #fadbd8"
        return ""

    st.dataframe(
        show.style
            .applymap(color_result, subset=["Result"])
            .format({"Edge%": "{:.1f}%", "Odds": "{:.2f}", "Stake": "{:.1f}",
                     "P&L": "{:+.1f}", "CLV%": "{:.2f}%"},
                    na_rep="–"),
        use_container_width=True,
        height=400,
    )

with tab_pending:
    if pending.empty:
        st.info("No pending bets.")
    else:
        show_p = pending[display_cols_exist].sort_values("date", ascending=False).head(50)
        st.dataframe(show_p, use_container_width=True)

# ── Performance by edge bucket ────────────────────────────────────────────────
st.markdown("## ROI by Edge Threshold Bucket")
if not settled.empty:
    buckets = [(0, 3, "0–3%"), (3, 5, "3–5%"), (5, 7, "5–7%"), (7, 10, "7–10%"), (10, 100, ">10%")]
    bucket_rows = []
    for lo, hi, label in buckets:
        sub = settled[(settled["edge_pct"] >= lo) & (settled["edge_pct"] < hi)]
        if sub.empty:
            continue
        total_staked = sub[stake_col].sum()
        roi = sub[pnl_col].sum() / total_staked if total_staked > 0 else 0
        bucket_rows.append({"Edge Bucket": label, "Bets": len(sub),
                             "ROI": roi, "Win Rate": (sub["result"] == "won").mean()})
    if bucket_rows:
        bd = pd.DataFrame(bucket_rows)
        fig_b = px.bar(bd, x="Edge Bucket", y="ROI", text_auto=".1%",
                       color="ROI", color_continuous_scale=["red", "yellow", "green"],
                       hover_data=["Bets", "Win Rate"])
        fig_b.add_hline(y=0, line_color="gray")
        fig_b.update_layout(height=280, margin=dict(t=10), coloraxis_showscale=False)
        st.plotly_chart(fig_b, use_container_width=True)

# ── CSV export ────────────────────────────────────────────────────────────────
if not bets_df.empty:
    csv = bets_df.to_csv(index=False).encode("utf-8")
    st.download_button("📥 Download bets CSV", csv, "simulated_bets.csv", "text/csv")


def make_subplots(*args, **kwargs):
    """Import helper — avoid name collision."""
    from plotly.subplots import make_subplots as _make
    return _make(*args, **kwargs)
