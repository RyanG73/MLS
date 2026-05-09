"""
Page 7 — Monte Carlo Season Forecast.
Run 10k simulations of the remaining MLS season to estimate
playoff probability, Supporters Shield odds, and projected points.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import json
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from config import SETTINGS
from data_pipeline import db_utils
from models.season_simulator import run_season_simulation, get_latest_simulation

st.set_page_config(page_title="Season Forecast — MLS Dashboard", layout="wide")
st.title("📅 Monte Carlo Season Forecast")
st.markdown(
    "Simulates the rest of the MLS season 10,000 times using current model "
    "probabilities to estimate playoff and Supporters Shield odds."
)

with st.sidebar:
    st.markdown("### Forecast settings")
    seasons = db_utils.query("SELECT DISTINCT season FROM matches ORDER BY season DESC")
    season_choices = [int(s) for s in seasons["season"]]
    selected_season = st.selectbox("Season", season_choices, index=0)
    n_sims = st.select_slider("Simulations", options=[1000, 5000, 10000, 25000], value=10000)

    if st.button("🎲 Run simulation"):
        with st.spinner(f"Running {n_sims} season simulations..."):
            result = run_season_simulation(selected_season, n_sims)
        if "error" in result:
            st.error(result["error"])
        else:
            st.success(f"Simulation complete ({n_sims} runs).")
            st.session_state["latest_sim"] = result

# Try to load latest stored simulation if no in-session result
result = st.session_state.get("latest_sim")
if not result:
    latest = get_latest_simulation(selected_season)
    if latest:
        result = latest["results"]
        st.caption(f"Last simulated: {latest['simulated_at']}")

if not result:
    st.info("No simulation data yet. Click 'Run simulation' in the sidebar.")
    st.stop()

# ── Build standings table ─────────────────────────────────────────────────────
playoffs = result.get("playoff_probabilities", {})
shield   = result.get("shield_probabilities", {})
points   = result.get("projected_points", {})
finish   = result.get("projected_finish", {})

teams = sorted(playoffs.keys())
df = pd.DataFrame({
    "Team":       teams,
    "Playoff %":  [playoffs.get(t, 0) for t in teams],
    "Shield %":   [shield.get(t, 0) for t in teams],
    "Proj Pts":   [points.get(t, 0) for t in teams],
    "Proj Finish": [finish.get(t, 0) for t in teams],
})

from data_pipeline.asa_client import get_conference
df["Conf"] = df["Team"].apply(get_conference)

# Split by conference
st.markdown("## Eastern Conference")
east = df[df["Conf"] == "E"].sort_values("Proj Pts", ascending=False)
st.dataframe(
    east[["Team", "Proj Pts", "Proj Finish", "Playoff %", "Shield %"]].style.format({
        "Proj Pts": "{:.1f}", "Proj Finish": "{:.1f}",
        "Playoff %": "{:.1%}", "Shield %": "{:.1%}",
    }).background_gradient(subset=["Playoff %"], cmap="Blues"),
    use_container_width=True,
)

st.markdown("## Western Conference")
west = df[df["Conf"] == "W"].sort_values("Proj Pts", ascending=False)
st.dataframe(
    west[["Team", "Proj Pts", "Proj Finish", "Playoff %", "Shield %"]].style.format({
        "Proj Pts": "{:.1f}", "Proj Finish": "{:.1f}",
        "Playoff %": "{:.1%}", "Shield %": "{:.1%}",
    }).background_gradient(subset=["Playoff %"], cmap="Blues"),
    use_container_width=True,
)

# ── Visualizations ───────────────────────────────────────────────────────────
st.markdown("## Playoff Probability by Team")
df_sorted = df.sort_values("Playoff %", ascending=True)
fig = px.bar(
    df_sorted, y="Team", x="Playoff %", color="Conf",
    orientation="h",
    color_discrete_map={"E": "#1a4b8c", "W": "#c0392b"},
    text=df_sorted["Playoff %"].apply(lambda x: f"{x:.0%}"),
    labels={"Playoff %": "Playoff Probability"},
    height=max(400, len(df) * 22),
)
fig.update_layout(margin=dict(t=10), legend_title="Conference")
st.plotly_chart(fig, use_container_width=True)

# ── Shield race ──────────────────────────────────────────────────────────────
st.markdown("## Supporters Shield Race")
shield_df = df.sort_values("Shield %", ascending=False).head(10)
fig_s = px.bar(
    shield_df, x="Team", y="Shield %",
    color="Conf", color_discrete_map={"E": "#1a4b8c", "W": "#c0392b"},
    text=shield_df["Shield %"].apply(lambda x: f"{x:.1%}"),
)
fig_s.update_layout(height=300, yaxis_tickformat=".0%", margin=dict(t=10))
st.plotly_chart(fig_s, use_container_width=True)

# ── CSV export ───────────────────────────────────────────────────────────────
csv = df.to_csv(index=False).encode("utf-8")
st.download_button("📥 Download forecast CSV", csv, "season_forecast.csv", "text/csv")
