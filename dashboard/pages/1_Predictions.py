"""
Page 1 — Upcoming Match Predictions.
Shows prediction cards for all matches in the next N days with:
- Win/Draw/Loss probabilities (ensemble vs components)
- xG estimates
- Top scorelines
- Value bet alerts vs Pinnacle
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from config import SETTINGS
from data_pipeline import db_utils
from market.kelly import vig_adjusted_prob

st.set_page_config(page_title="Predictions — MLS Dashboard", layout="wide")
st.title("📋 Upcoming Match Predictions")

_DASH_CFG = SETTINGS["dashboard"]
_MKT_CFG = SETTINGS["market"]

# ── Sidebar controls ──────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### Filters")
    days_ahead = st.slider("Days ahead", 1, 14, _DASH_CFG["prediction_horizon_days"])
    edge_threshold = st.slider(
        "Value bet edge threshold (%)",
        0.0, 20.0, _MKT_CFG["default_edge_threshold_pct"], 0.5,
        help="Only flag as value bet when model edge exceeds this %"
    )
    show_components = st.toggle("Show component model breakdown", False)
    conf_filter = st.multiselect("Conference matchup", ["EE", "WW", "EW"], default=["EE", "WW", "EW"])


@st.cache_data(ttl=300)
def load_upcoming_predictions(days: int) -> pd.DataFrame:
    return db_utils.query(
        f"""
        SELECT
            m.match_id, m.date, m.home_team, m.away_team,
            m.conference_h, m.conference_a, m.is_playoff, m.season,
            p.prob_home, p.prob_draw, p.prob_away,
            p.prob_over, p.prob_under,
            p.model,
            o.open_odds AS pinnacle_home_odds
        FROM matches m
        LEFT JOIN predictions p ON m.match_id = p.match_id
        LEFT JOIN odds o ON (m.match_id = o.match_id AND o.bookmaker='pinnacle'
                             AND o.market='h2h' AND o.outcome='Home')
        WHERE m.status = 'scheduled'
          AND m.date BETWEEN current_date AND current_date + INTERVAL {days} DAY
        ORDER BY m.date, m.match_id
        """
    )


def conference_matchup(ch, ca):
    if ch == ca:
        return ch + ch
    return "EW"


def render_prob_bar(home_p: float, draw_p: float, away_p: float, home: str, away: str):
    """Render a horizontal stacked bar of outcome probabilities."""
    fig = go.Figure(go.Bar(
        x=[home_p * 100], name=home, orientation="h",
        marker_color="#1a4b8c", text=f"{home_p:.0%}", textposition="inside",
        hovertemplate=f"{home}: {home_p:.1%}<extra></extra>"
    ))
    fig.add_trace(go.Bar(
        x=[draw_p * 100], name="Draw", orientation="h",
        marker_color="#888888", text=f"{draw_p:.0%}", textposition="inside",
        hovertemplate=f"Draw: {draw_p:.1%}<extra></extra>"
    ))
    fig.add_trace(go.Bar(
        x=[away_p * 100], name=away, orientation="h",
        marker_color="#c0392b", text=f"{away_p:.0%}", textposition="inside",
        hovertemplate=f"{away}: {away_p:.1%}<extra></extra>"
    ))
    fig.update_layout(
        barmode="stack", height=55, margin=dict(l=0, r=0, t=0, b=0),
        showlegend=False, xaxis=dict(showticklabels=False, range=[0, 100]),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
    )
    return fig


def render_scoreline_heatmap(match_id: str, home: str, away: str) -> go.Figure | None:
    """Generate top-5 scoreline bar chart for a match."""
    try:
        from models.dixon_coles import DixonColesModel
        dc = DixonColesModel.load()
        result = dc.predict(home, away)
        top5 = result["top_scorelines"]
        labels = [f"{hg}–{ag}" for hg, ag, _ in top5]
        values = [p * 100 for _, _, p in top5]
        fig = go.Figure(go.Bar(
            x=labels, y=values, marker_color="#1a4b8c",
            text=[f"{v:.1f}%" for v in values], textposition="outside"
        ))
        fig.update_layout(
            height=200, margin=dict(l=0, r=0, t=20, b=0),
            yaxis_title="Probability (%)", title="Top Scorelines",
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        )
        return fig
    except Exception:
        return None


# ── Load and filter data ──────────────────────────────────────────────────────
all_preds = load_upcoming_predictions(days_ahead)

if all_preds.empty:
    st.info("No upcoming predictions found. Run the daily update script to populate data.")
    st.stop()

# Separate ensemble from component predictions
ensemble_preds = all_preds[all_preds["model"] == "ensemble"].copy()
component_preds = all_preds[all_preds["model"] != "ensemble"].copy()

ensemble_preds["matchup_type"] = ensemble_preds.apply(
    lambda r: conference_matchup(r.get("conference_h", "E"), r.get("conference_a", "E")), axis=1
)
ensemble_preds = ensemble_preds[ensemble_preds["matchup_type"].isin(conf_filter)]

if ensemble_preds.empty:
    st.warning("No predictions match your current filters.")
    st.stop()

# ── Match cards ───────────────────────────────────────────────────────────────
dates = sorted(ensemble_preds["date"].unique())

for match_date in dates:
    st.markdown(f"### {pd.Timestamp(match_date).strftime('%A, %B %d %Y')}")
    day_matches = ensemble_preds[ensemble_preds["date"] == match_date]

    cols = st.columns(min(len(day_matches), 2))
    for i, (_, row) in enumerate(day_matches.iterrows()):
        col = cols[i % 2]
        with col:
            home = row["home_team"]
            away = row["away_team"]
            prob_h = row["prob_home"] or 0.0
            prob_d = row["prob_draw"] or 0.0
            prob_a = row["prob_away"] or 0.0
            prob_over = row["prob_over"] or 0.0

            # Compute market edge
            pinnacle_raw = row.get("pinnacle_home_odds")
            edge_str = ""
            market_home_p = None
            if pinnacle_raw and pinnacle_raw > 1:
                market_implied = db_utils.query(
                    """
                    SELECT outcome, open_odds FROM odds
                    WHERE match_id=? AND bookmaker='pinnacle' AND market='h2h'
                    ORDER BY fetched_at DESC LIMIT 3
                    """,
                    [row["match_id"]]
                )
                if not market_implied.empty:
                    od = {r["outcome"]: r["open_odds"] for _, r in market_implied.iterrows()}
                    adj = vig_adjusted_prob(
                        od.get("Home", 0), od.get("Draw", 0), od.get("Away", 0)
                    )
                    market_home_p = adj.get("home", 0)
                    best_edge = max(
                        prob_h - adj.get("home", 0),
                        prob_d - adj.get("draw", 0),
                        prob_a - adj.get("away", 0),
                    ) * 100
                    if best_edge >= edge_threshold:
                        edge_str = f"<span class='value-bet-badge'>VALUE +{best_edge:.1f}%</span>"

            playoff_badge = " 🏆" if row.get("is_playoff") else ""

            st.markdown(
                f"""
                <div class='prediction-card'>
                <h4>{home} vs {away}{playoff_badge} {edge_str}</h4>
                </div>
                """,
                unsafe_allow_html=True,
            )

            with st.container():
                c1, c2, c3 = st.columns([2, 1, 1])
                with c1:
                    st.plotly_chart(
                        render_prob_bar(prob_h, prob_d, prob_a, home, away),
                        use_container_width=True, config={"displayModeBar": False}
                    )
                with c2:
                    st.metric("Over 2.5", f"{prob_over:.0%}")
                with c3:
                    st.metric("Under 2.5", f"{1-prob_over:.0%}")

                if show_components:
                    comp_rows = component_preds[component_preds["match_id"] == row["match_id"]]
                    if not comp_rows.empty:
                        with st.expander("Component models"):
                            comp_df = comp_rows[["model", "prob_home", "prob_draw", "prob_away"]].copy()
                            comp_df.columns = ["Model", f"{home} Win", "Draw", f"{away} Win"]
                            comp_df = comp_df.set_index("Model")
                            st.dataframe(comp_df.style.format("{:.1%}"), use_container_width=True)

                # Scoreline heatmap (on demand)
                with st.expander("Top scorelines"):
                    hm = render_scoreline_heatmap(row["match_id"], home, away)
                    if hm:
                        st.plotly_chart(hm, use_container_width=True, config={"displayModeBar": False})
                    else:
                        st.info("Scoreline data unavailable.")

    st.markdown("---")

# ── CSV export ────────────────────────────────────────────────────────────────
if not ensemble_preds.empty:
    csv = ensemble_preds.to_csv(index=False).encode("utf-8")
    st.download_button("📥 Download predictions CSV", csv, "upcoming_predictions.csv", "text/csv")
