"""
Page 3 — Model Calibration.
Reliability diagrams, sharpness histograms, and Brier score decomposition.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

from config import SETTINGS
from data_pipeline import db_utils

st.set_page_config(page_title="Calibration — MLS Dashboard", layout="wide")
st.title("🎯 Model Calibration")
st.markdown(
    "Calibration measures how closely predicted probabilities match observed frequencies. "
    "A perfectly calibrated model has all points on the diagonal."
)

# ── Controls ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### Settings")
    n_bins = st.slider("Calibration bins", 5, 20, SETTINGS["dashboard"]["calibration_bins"])
    model_compare = st.multiselect(
        "Models to compare",
        ["ensemble", "dixon_coles", "xgboost", "bayesian"],
        default=["ensemble", "dixon_coles"]
    )
    outcome_focus = st.selectbox("Outcome", ["Home Win", "Draw", "Away Win"])
    season_filter = st.selectbox("Season", ["All"] + [str(s) for s in range(2011, 2026)])


@st.cache_data(ttl=300)
def load_calibration_data(season_f: str) -> pd.DataFrame:
    season_clause = f"AND m.season = {season_f}" if season_f != "All" else ""
    return db_utils.query(
        f"""
        SELECT p.model, p.prob_home, p.prob_draw, p.prob_away,
               m.home_goals, m.away_goals, m.date, m.season
        FROM predictions p
        JOIN matches m ON p.match_id = m.match_id
        WHERE m.status='completed' AND m.home_goals IS NOT NULL {season_clause}
        """
    )


def reliability_data(probs: np.ndarray, actuals: np.ndarray, n_bins: int) -> pd.DataFrame:
    """Bin predictions and compute mean predicted vs mean actual per bin."""
    bins = np.linspace(0, 1, n_bins + 1)
    bin_idx = np.digitize(probs, bins, right=True).clip(1, n_bins) - 1
    rows = []
    for b in range(n_bins):
        mask = bin_idx == b
        if mask.sum() == 0:
            continue
        rows.append({
            "bin_center": (bins[b] + bins[b + 1]) / 2,
            "mean_predicted": probs[mask].mean(),
            "mean_actual": actuals[mask].mean(),
            "count": mask.sum(),
        })
    return pd.DataFrame(rows)


def brier_decompose(probs: np.ndarray, actuals: np.ndarray, n_bins: int = 10):
    """Decompose Brier score into reliability, resolution, uncertainty."""
    bs = np.mean((probs - actuals) ** 2)
    mean_actual = actuals.mean()
    uncertainty = mean_actual * (1 - mean_actual)

    bins = np.linspace(0, 1, n_bins + 1)
    bin_idx = np.digitize(probs, bins, right=True).clip(1, n_bins) - 1

    reliability = 0.0
    resolution = 0.0
    for b in range(n_bins):
        mask = bin_idx == b
        if mask.sum() == 0:
            continue
        n_k = mask.sum()
        ok = actuals[mask].mean()
        pk = probs[mask].mean()
        reliability += n_k * (pk - ok) ** 2
        resolution += n_k * (ok - mean_actual) ** 2
    N = len(probs)
    return {
        "brier": float(bs),
        "reliability": float(reliability / N),
        "resolution": float(resolution / N),
        "uncertainty": float(uncertainty),
    }


raw = load_calibration_data(season_filter)
if raw.empty:
    st.info("No prediction data available yet.")
    st.stop()

raw["actual_home"] = (raw["home_goals"] > raw["away_goals"]).astype(float)
raw["actual_draw"] = (raw["home_goals"] == raw["away_goals"]).astype(float)
raw["actual_away"] = (raw["home_goals"] < raw["away_goals"]).astype(float)

outcome_col_map = {
    "Home Win": ("prob_home", "actual_home"),
    "Draw": ("prob_draw", "actual_draw"),
    "Away Win": ("prob_away", "actual_away"),
}
prob_col, actual_col = outcome_col_map[outcome_focus]

# ── Reliability diagram ────────────────────────────────────────────────────────
st.markdown(f"## Reliability Diagram — {outcome_focus}")
fig_rel = go.Figure()
fig_rel.add_trace(go.Scatter(
    x=[0, 1], y=[0, 1],
    mode="lines", line=dict(dash="dash", color="gray"),
    name="Perfect calibration"
))

colors = {"ensemble": "#1a4b8c", "dixon_coles": "#e74c3c", "xgboost": "#27ae60", "bayesian": "#f39c12"}

for model in model_compare:
    sub = raw[raw["model"] == model]
    if sub.empty:
        continue
    probs = sub[prob_col].dropna().values
    acts = sub[actual_col].dropna().values
    if len(probs) == 0:
        continue
    rel = reliability_data(probs, acts, n_bins)
    if rel.empty:
        continue
    fig_rel.add_trace(go.Scatter(
        x=rel["mean_predicted"], y=rel["mean_actual"],
        mode="lines+markers",
        name=model,
        line=dict(color=colors.get(model, "blue"), width=2),
        marker=dict(size=rel["count"] / rel["count"].max() * 15 + 4),
        hovertemplate=f"<b>{model}</b><br>Predicted: %{{x:.2f}}<br>Actual: %{{y:.2f}}<br>Count: %{{customdata}}<extra></extra>",
        customdata=rel["count"],
    ))

fig_rel.update_layout(
    height=450, xaxis_title="Mean Predicted Probability", yaxis_title="Mean Observed Frequency",
    xaxis=dict(range=[0, 1]), yaxis=dict(range=[0, 1]),
    legend=dict(orientation="h", yanchor="bottom", y=1.02),
    margin=dict(t=20)
)
st.plotly_chart(fig_rel, use_container_width=True)

# ── Sharpness histogram ────────────────────────────────────────────────────────
st.markdown(f"## Sharpness — Distribution of {outcome_focus} Predictions")
fig_sharp = go.Figure()
for model in model_compare:
    sub = raw[raw["model"] == model]
    if sub.empty:
        continue
    probs = sub[prob_col].dropna().values
    fig_sharp.add_trace(go.Histogram(
        x=probs, name=model, nbinsx=20, opacity=0.6,
        marker_color=colors.get(model, "blue"),
        histnorm="probability density"
    ))
fig_sharp.update_layout(
    barmode="overlay", height=300, xaxis_title="Predicted Probability",
    yaxis_title="Density", margin=dict(t=10)
)
st.plotly_chart(fig_sharp, use_container_width=True)

# ── Brier decomposition ────────────────────────────────────────────────────────
st.markdown("## Brier Score Decomposition")
st.caption("Reliability ↓ better | Resolution ↑ better | Uncertainty = inherent variance in outcomes")

decomp_rows = []
for model in model_compare:
    sub = raw[raw["model"] == model]
    if sub.empty:
        continue
    probs = sub[prob_col].dropna().values
    acts = sub[actual_col].dropna().values
    if len(probs) < 20:
        continue
    d = brier_decompose(probs, acts, n_bins)
    d["model"] = model
    decomp_rows.append(d)

if decomp_rows:
    decomp_df = pd.DataFrame(decomp_rows).set_index("model")
    st.dataframe(
        decomp_df[["brier", "reliability", "resolution", "uncertainty"]].style.format("{:.4f}"),
        use_container_width=True
    )
    fig_decomp = go.Figure()
    for comp, color in [("reliability", "#e74c3c"), ("resolution", "#27ae60"), ("uncertainty", "#888888")]:
        fig_decomp.add_trace(go.Bar(
            x=decomp_df.index, y=decomp_df[comp], name=comp.capitalize(),
            marker_color=color
        ))
    fig_decomp.update_layout(
        barmode="group", height=300, yaxis_title="Component Value",
        margin=dict(t=10)
    )
    st.plotly_chart(fig_decomp, use_container_width=True)
else:
    st.info("Insufficient data for Brier decomposition.")

# ── Per-class calibration comparison ─────────────────────────────────────────
st.markdown("## Per-Class Calibration")

tabs = st.tabs(["Home Win", "Draw", "Away Win", "Over 2.5"])
for tab, (outcome, prob_c, actual_c) in zip(tabs, [
    ("Home Win", "prob_home", "actual_home"),
    ("Draw", "prob_draw", "actual_draw"),
    ("Away Win", "prob_away", "actual_away"),
    ("Over 2.5", "prob_over", "actual_over"),
]):
    with tab:
        if "actual_over" not in raw.columns:
            raw["actual_over"] = ((raw["home_goals"] + raw["away_goals"]) > 2.5).astype(float)
        sub_ens = raw[raw["model"] == "ensemble"]
        if sub_ens.empty or prob_c not in sub_ens.columns:
            st.info("No ensemble data.")
            continue
        pr = sub_ens[prob_c].dropna().values
        ac = sub_ens[actual_c].dropna().values
        rel = reliability_data(pr, ac, n_bins)
        fig_c = go.Figure()
        fig_c.add_trace(go.Scatter(x=[0,1], y=[0,1], mode="lines",
                                    line=dict(dash="dash", color="gray"), name="Perfect"))
        if not rel.empty:
            fig_c.add_trace(go.Scatter(x=rel["mean_predicted"], y=rel["mean_actual"],
                                        mode="lines+markers", name="Ensemble",
                                        line=dict(color="#1a4b8c", width=2)))
        fig_c.update_layout(height=300, xaxis=dict(range=[0,1]), yaxis=dict(range=[0,1]),
                             margin=dict(t=10))
        st.plotly_chart(fig_c, use_container_width=True)
