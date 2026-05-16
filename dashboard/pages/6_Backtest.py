"""
Page 6 — Walk-Forward Backtest.
Run parameterized backtests and visualize Brier, log-loss, ROI, CLV
across historical date ranges.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import streamlit as st
from config import SETTINGS

if not SETTINGS.get("dashboard", {}).get("beta_pages_enabled", False):
    st.set_page_config(page_title="Backtest — MLS Dashboard", layout="wide")
    st.title("Backtest")
    st.info(
        "This page is not yet enabled. Once the model baseline is validated, "
        "set `dashboard.beta_pages_enabled: true` in `config/settings.yaml` to activate."
    )
    st.stop()

import json
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from data_pipeline import db_utils
from models.backtest import run_walk_forward, get_recent_runs

st.set_page_config(page_title="Backtest — MLS Dashboard", layout="wide")
st.title("🔬 Walk-Forward Backtest")
st.markdown(
    "Test the model on historical data with adjustable parameters. "
    "Each run walks weekly through history, refitting models on data "
    "up to week N and evaluating on week N+1."
)

# ── Parameter sidebar ────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### Backtest parameters")
    seasons = db_utils.query("SELECT DISTINCT season FROM matches ORDER BY season DESC")
    season_choices = [int(s) for s in seasons["season"]]

    start_season = st.selectbox("Start season", season_choices, index=min(2, len(season_choices)-1))
    end_season   = st.selectbox("End season",   season_choices, index=0)

    edge_threshold = st.slider("Edge threshold (%)", 0.0, 15.0, 5.0, 0.5)
    half_life      = st.slider("xG decay half-life (days)", 30, 180, 60, 15)
    kelly_frac     = st.select_slider("Kelly fraction", options=[0.10, 0.25, 0.50, 1.0], value=0.25)
    models_subset  = st.multiselect(
        "Models in ensemble", ["dixon_coles", "xgboost"], default=["dixon_coles", "xgboost"]
    )

    if st.button("▶️ Run backtest"):
        start_date = f"{min(start_season, end_season)}-03-01"
        end_date   = f"{max(start_season, end_season)}-11-30"

        with st.spinner(f"Running walk-forward backtest from {start_date} to {end_date}..."):
            result = run_walk_forward(
                start_date=start_date,
                end_date=end_date,
                edge_threshold_pct=edge_threshold,
                half_life_days=half_life,
                kelly_fraction=kelly_frac,
                models_to_use=models_subset,
            )
        if "error" in result:
            st.error(result["error"])
        else:
            st.success(f"Backtest run {result.get('run_id')} complete.")
            st.session_state["latest_backtest"] = result

# ── Latest backtest run summary ──────────────────────────────────────────────
result = st.session_state.get("latest_backtest")

if result:
    st.markdown("## Latest Run")
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Brier",     f"{result.get('brier_mean', 0):.4f}")
    col2.metric("Log-Loss",  f"{result.get('log_loss', 0):.4f}")
    col3.metric("ROI (25%K)", f"{result.get('roi_kelly25', 0):.2%}")
    col4.metric("Avg CLV",   f"{result.get('avg_clv', 0):.2f}%")

    weekly = pd.DataFrame(result.get("weekly_results", []))
    if not weekly.empty:
        weekly["week_start"] = pd.to_datetime(weekly["week_start"])
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=weekly["week_start"], y=weekly.get("brier", 0),
            mode="lines", name="Brier", line=dict(color="#1a4b8c"),
        ))
        fig.add_hline(y=0.25, line_dash="dash", line_color="red",
                       annotation_text="Naive baseline 0.250")
        fig.update_layout(height=350, xaxis_title="Week", yaxis_title="Brier",
                           margin=dict(t=10))
        st.plotly_chart(fig, use_container_width=True)

# ── Historical backtest runs ──────────────────────────────────────────────────
st.markdown("---")
st.markdown("## Past Backtest Runs")
runs = get_recent_runs(50)
if runs.empty:
    st.info("No backtest runs yet. Configure parameters and click 'Run backtest'.")
else:
    runs["params"] = runs["parameters"].apply(lambda x: json.loads(x) if x else {})
    runs["start"]  = runs["params"].apply(lambda p: p.get("start_date", ""))
    runs["end"]    = runs["params"].apply(lambda p: p.get("end_date", ""))
    runs["edge"]   = runs["params"].apply(lambda p: p.get("edge_threshold_pct", 0))
    runs["kelly"]  = runs["params"].apply(lambda p: p.get("kelly_fraction", 0))

    show = runs[[
        "generated_at", "start", "end", "edge", "kelly",
        "brier_mean", "log_loss", "roi_kelly25", "avg_clv", "n_bets",
    ]].copy()

    st.dataframe(
        show.style.format({
            "brier_mean": "{:.4f}", "log_loss": "{:.4f}",
            "roi_kelly25": "{:.2%}", "avg_clv": "{:.2f}%",
            "edge": "{:.1f}", "kelly": "{:.2f}",
        }),
        use_container_width=True,
    )

    csv = show.to_csv(index=False).encode("utf-8")
    st.download_button("📥 Download CSV", csv, "backtest_runs.csv", "text/csv")
