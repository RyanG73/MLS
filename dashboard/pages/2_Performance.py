"""
Page 2 — Model Performance Tracker.
Brier score, log-loss, CLV, and ROI tracking over time
with segmentation by team, season, and edge threshold.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from sklearn.metrics import log_loss, brier_score_loss

from config import SETTINGS
from data_pipeline import db_utils

st.set_page_config(page_title="Performance — MLS Dashboard", layout="wide")
st.title("📊 Model Performance Tracker")

# ── Sidebar filters ────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### Filters")
    seasons = db_utils.query("SELECT DISTINCT season FROM matches ORDER BY season DESC")
    season_list = ["All"] + [str(s) for s in seasons["season"].tolist()]
    selected_season = st.selectbox("Season", season_list)
    selected_model = st.selectbox("Model", ["ensemble", "dixon_coles", "xgboost", "bayesian"])
    home_away = st.radio("Home/Away filter", ["All", "Home only", "Away only"])
    edge_threshold = st.slider("Min edge threshold (%)", 0.0, 15.0, 0.0, 0.5)


@st.cache_data(ttl=300)
def load_performance_data(season_filter, model_filter) -> pd.DataFrame:
    season_clause = f"AND m.season = {season_filter}" if season_filter != "All" else ""
    return db_utils.query(
        f"""
        SELECT
            p.match_id, p.model, p.prob_home, p.prob_draw, p.prob_away,
            p.prob_over, p.prob_under, p.predicted_at,
            m.home_goals, m.away_goals, m.date, m.season,
            m.home_team, m.away_team
        FROM predictions p
        JOIN matches m ON p.match_id = m.match_id
        WHERE m.status = 'completed'
          AND m.home_goals IS NOT NULL
          AND p.model = '{model_filter}'
          {season_clause}
        ORDER BY m.date
        """
    )


def compute_outcomes(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["actual_home"] = (df["home_goals"] > df["away_goals"]).astype(int)
    df["actual_draw"] = (df["home_goals"] == df["away_goals"]).astype(int)
    df["actual_away"] = (df["home_goals"] < df["away_goals"]).astype(int)
    df["actual_over"] = ((df["home_goals"] + df["away_goals"]) > 2.5).astype(int)
    df["brier_result"] = (
        (df["prob_home"] - df["actual_home"]) ** 2 +
        (df["prob_draw"] - df["actual_draw"]) ** 2 +
        (df["prob_away"] - df["actual_away"]) ** 2
    ) / 2
    df["brier_ou"] = (df["prob_over"] - df["actual_over"]) ** 2
    return df


perf_df = load_performance_data(selected_season, selected_model)

if perf_df.empty:
    st.info("No performance data available. Run the daily update to generate predictions against completed matches.")
    st.stop()

perf_df = compute_outcomes(perf_df)
perf_df["date"] = pd.to_datetime(perf_df["date"])
perf_df["week"] = perf_df["date"].dt.to_period("W").dt.start_time

# ── Summary KPIs ───────────────────────────────────────────────────────────────
st.markdown("## Summary")
col1, col2, col3, col4 = st.columns(4)

avg_brier = perf_df["brier_result"].mean()
try:
    y_true = perf_df[["actual_home", "actual_draw", "actual_away"]].values
    y_pred = perf_df[["prob_home", "prob_draw", "prob_away"]].clip(1e-6, 1 - 1e-6).values
    avg_logloss = float(np.mean(-np.sum(y_true * np.log(y_pred), axis=1)))
except Exception:
    avg_logloss = float("nan")

col1.metric("Avg Brier Score", f"{avg_brier:.4f}", help="Lower is better; random baseline ~0.250")
col2.metric("Avg Log-Loss", f"{avg_logloss:.4f}", help="Lower is better")
col3.metric("Predictions", f"{len(perf_df):,}")
col4.metric("Date Range",
            f"{perf_df['date'].min().strftime('%b %Y')} – {perf_df['date'].max().strftime('%b %Y')}")

st.markdown("---")

# ── Rolling Brier score over time ─────────────────────────────────────────────
st.markdown("## Brier Score Over Time")
weekly = perf_df.groupby("week").agg(
    brier_mean=("brier_result", "mean"),
    n=("brier_result", "count")
).reset_index()
weekly["rolling_brier"] = weekly["brier_mean"].rolling(4, min_periods=1).mean()

fig_brier = go.Figure()
fig_brier.add_trace(go.Scatter(
    x=weekly["week"], y=weekly["brier_mean"],
    mode="lines", name="Weekly Brier",
    line=dict(color="lightblue", width=1), opacity=0.6
))
fig_brier.add_trace(go.Scatter(
    x=weekly["week"], y=weekly["rolling_brier"],
    mode="lines", name="4-week rolling avg",
    line=dict(color="#1a4b8c", width=2)
))
fig_brier.add_hline(y=0.25, line_dash="dash", line_color="red",
                    annotation_text="Naive baseline (0.250)")
fig_brier.update_layout(height=350, xaxis_title="Date", yaxis_title="Brier Score",
                         legend=dict(orientation="h"), margin=dict(t=20))
st.plotly_chart(fig_brier, use_container_width=True)

# ── CLV and ROI ──────────────────────────────────────────────────────────────
st.markdown("## Market Performance (CLV & ROI)")

bets_df = db_utils.query(
    """
    SELECT sb.*, m.season, m.home_team, m.away_team, m.date
    FROM simulated_bets sb
    JOIN matches m ON sb.match_id = m.match_id
    WHERE sb.result IS NOT NULL
    """
    + (f" AND m.season = {selected_season}" if selected_season != "All" else "")
    + (f" AND sb.edge_pct >= {edge_threshold}" if edge_threshold > 0 else "")
)

if not bets_df.empty:
    bets_df["date"] = pd.to_datetime(bets_df["date"])
    bets_df = bets_df.sort_values("date")
    bets_df["cum_pnl_25"] = bets_df["pnl_kelly25"].cumsum()
    bets_df["cum_pnl_50"] = bets_df["pnl_kelly50"].cumsum()

    col_a, col_b, col_c, col_d = st.columns(4)
    col_a.metric("Total Bets", len(bets_df))
    col_b.metric("Win Rate", f"{(bets_df['result']=='won').mean():.1%}")
    roi_25 = bets_df["pnl_kelly25"].sum() / bets_df["stake_kelly25"].sum() if bets_df["stake_kelly25"].sum() > 0 else 0
    col_c.metric("ROI (25% Kelly)", f"{roi_25:.2%}")
    avg_clv = bets_df["clv"].mean() if "clv" in bets_df.columns else None
    col_d.metric("Avg CLV", f"{avg_clv:.2f}%" if avg_clv is not None else "–")

    fig_pnl = go.Figure()
    fig_pnl.add_trace(go.Scatter(x=bets_df["date"], y=bets_df["cum_pnl_25"],
                                  name="25% Kelly", line=dict(color="#1a4b8c")))
    fig_pnl.add_trace(go.Scatter(x=bets_df["date"], y=bets_df["cum_pnl_50"],
                                  name="50% Kelly", line=dict(color="#e74c3c", dash="dash")))
    fig_pnl.add_hline(y=0, line_color="gray", line_dash="dot")
    fig_pnl.update_layout(height=300, xaxis_title="Date", yaxis_title="Cumulative P&L (units)",
                           margin=dict(t=10))
    st.plotly_chart(fig_pnl, use_container_width=True)

    # ROI by season
    st.markdown("### ROI by Season")
    season_roi = bets_df.groupby("season").apply(
        lambda g: pd.Series({
            "Bets": len(g),
            "Win Rate": (g["result"] == "won").mean(),
            "ROI (25% Kelly)": g["pnl_kelly25"].sum() / g["stake_kelly25"].sum() if g["stake_kelly25"].sum() > 0 else 0,
            "Avg CLV": g["clv"].mean() if "clv" in g.columns else None,
        })
    ).reset_index()
    st.dataframe(
        season_roi.style.format({
            "Win Rate": "{:.1%}", "ROI (25% Kelly)": "{:.2%}", "Avg CLV": "{:.2f}%"
        }),
        use_container_width=True
    )
else:
    st.info("No settled bets found with current filters. Market data populates as matches complete.")

# ── By-team performance ────────────────────────────────────────────────────────
st.markdown("## Performance by Team")
st.caption("Identifies systematic model biases toward or against specific clubs.")

team_perf = perf_df.groupby("home_team").agg(
    n=("brier_result", "count"),
    brier=("brier_result", "mean"),
).reset_index().rename(columns={"home_team": "team"})

fig_team = px.bar(
    team_perf.sort_values("brier"),
    x="brier", y="team", orientation="h",
    color="brier", color_continuous_scale=["green", "yellow", "red"],
    labels={"brier": "Avg Brier Score", "team": "Team"},
    height=max(300, len(team_perf) * 22),
)
fig_team.add_vline(x=0.25, line_dash="dash", line_color="gray",
                   annotation_text="Baseline")
fig_team.update_layout(margin=dict(l=0, r=0, t=20, b=0), coloraxis_showscale=False)
st.plotly_chart(fig_team, use_container_width=True)

# ── Edge threshold bucket analysis ────────────────────────────────────────────
if not bets_df.empty:
    st.markdown("## ROI by Edge Threshold Bucket")
    bets_df["edge_bucket"] = pd.cut(
        bets_df["edge_pct"],
        bins=[0, 3, 5, 7, 10, 100],
        labels=["0–3%", "3–5%", "5–7%", "7–10%", ">10%"]
    )
    bucket_roi = bets_df.groupby("edge_bucket", observed=True).apply(
        lambda g: pd.Series({
            "Bets": len(g),
            "ROI": g["pnl_kelly25"].sum() / g["stake_kelly25"].sum() if g["stake_kelly25"].sum() > 0 else 0,
        })
    ).reset_index()
    fig_edge = px.bar(bucket_roi, x="edge_bucket", y="ROI", color="ROI",
                      color_continuous_scale=["red", "yellow", "green"],
                      labels={"edge_bucket": "Edge Bucket", "ROI": "ROI"},
                      text_auto=".1%")
    fig_edge.add_hline(y=0, line_color="gray")
    fig_edge.update_layout(height=300, margin=dict(t=10), coloraxis_showscale=False)
    st.plotly_chart(fig_edge, use_container_width=True)

# ── CSV exports ──────────────────────────────────────────────────────────────
st.markdown("---")
st.markdown("## Export")
col_e1, col_e2 = st.columns(2)
with col_e1:
    if not perf_df.empty:
        csv = perf_df.to_csv(index=False).encode("utf-8")
        st.download_button("📥 Predictions + outcomes CSV", csv, "performance.csv", "text/csv")
with col_e2:
    if not bets_df.empty:
        csv = bets_df.to_csv(index=False).encode("utf-8")
        st.download_button("📥 Settled bets CSV", csv, "settled_bets.csv", "text/csv")
