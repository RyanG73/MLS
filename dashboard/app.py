"""
MLS Prediction Dashboard — Main Streamlit App Entry Point.
Multi-page app; Streamlit discovers pages/ automatically.
"""

import sys
from pathlib import Path

# Ensure repo root is importable regardless of where streamlit is launched from
_REPO_ROOT = Path(__file__).parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import streamlit as st
from dotenv import load_dotenv

load_dotenv(_REPO_ROOT / ".env")

from config import SETTINGS

st.set_page_config(
    page_title=SETTINGS["dashboard"]["page_title"],
    page_icon="⚽",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS for MLS-themed styling
st.markdown(
    f"""
    <style>
    :root {{
        --primary: {SETTINGS["dashboard"]["theme_primary_color"]};
    }}
    .stMetric > div > div > div > div {{ font-size: 1.1rem; }}
    .value-bet-badge {{
        background: #27ae60;
        color: white;
        border-radius: 4px;
        padding: 2px 8px;
        font-size: 0.75rem;
        font-weight: bold;
    }}
    .prediction-card {{
        border: 1px solid #e0e0e0;
        border-radius: 8px;
        padding: 16px;
        margin: 8px 0;
        background: #fafafa;
    }}
    </style>
    """,
    unsafe_allow_html=True,
)

# ── Sidebar navigation info ────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## ⚽ MLS Predictions")
    st.markdown("---")
    st.markdown(
        """
        **Pages**
        - 📋 Predictions — Upcoming matches
        - 📊 Performance — Model metrics
        - 🎯 Calibration — Probability accuracy
        - 📰 News & Overrides — Lineup news
        - 💰 Betting Tracker — Simulated P&L
        """
    )
    st.markdown("---")

    from data_pipeline import db_utils
    try:
        n_matches = db_utils.query("SELECT COUNT(*) AS n FROM matches WHERE status='completed'").iloc[0]["n"]
        n_preds = db_utils.query("SELECT COUNT(*) AS n FROM predictions WHERE model='ensemble'").iloc[0]["n"]
        st.metric("Completed Matches", f"{int(n_matches):,}")
        st.metric("Ensemble Predictions", f"{int(n_preds):,}")
    except Exception:
        st.info("Database loading...")

# ── Home page content ─────────────────────────────────────────────────────
st.title("⚽ MLS Prediction System")
st.markdown(
    """
    Welcome to your production-grade MLS match prediction and market tracking dashboard.

    **Navigate using the sidebar** to explore:
    - **Predictions** — Pre-match win probabilities and value bet alerts for upcoming games
    - **Performance** — Track Brier score, CLV, and ROI over time
    - **Calibration** — See how well-calibrated the model probabilities are
    - **News & Overrides** — Review Claude-analyzed news and adjust predictions manually
    - **Betting Tracker** — Simulated fractional-Kelly P&L tracking vs Pinnacle
    """
)

col1, col2, col3 = st.columns(3)
with col1:
    try:
        pending_news = db_utils.query(
            "SELECT COUNT(*) AS n FROM news_items WHERE confirmed_by_user = FALSE"
        ).iloc[0]["n"]
        st.metric("Pending News Items", int(pending_news), help="Unreviewed news items requiring confirmation")
    except Exception:
        st.metric("Pending News Items", "–")

with col2:
    try:
        from data_pipeline import db_utils as _db
        n_upcoming = _db.query(
            "SELECT COUNT(*) AS n FROM matches WHERE status='scheduled' AND date >= current_date"
        ).iloc[0]["n"]
        st.metric("Upcoming Fixtures", int(n_upcoming), help="Matches in the next 14 days")
    except Exception:
        st.metric("Upcoming Fixtures", "–")

with col3:
    try:
        stats = _db.query(
            "SELECT COUNT(*) AS n FROM simulated_bets WHERE result IS NOT NULL"
        ).iloc[0]["n"]
        st.metric("Simulated Bets Settled", int(stats))
    except Exception:
        st.metric("Simulated Bets Settled", "–")
