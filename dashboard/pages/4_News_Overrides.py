"""
Page 4 — News & Overrides.
- Live feed of Claude-processed news items
- User confirmation and impact adjustment sliders
- Manual override form
- Applied overrides management
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pandas as pd
import streamlit as st

from data_pipeline import db_utils
from data_pipeline.news_monitor import apply_news_override, get_pending_items, run_pipeline

st.set_page_config(page_title="News & Overrides — MLS Dashboard", layout="wide")
st.title("📰 News & Overrides")
st.markdown(
    "Claude automatically analyzes MLS news for lineup impacts. "
    "Review items below and apply adjustments to upcoming match predictions."
)

# ── News pipeline controls ────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### Actions")
    if st.button("🔄 Poll news feeds now"):
        with st.spinner("Polling RSS feeds and running Claude analysis..."):
            n = run_pipeline()
        st.success(f"Processed {n} new news items.")
    st.markdown("---")
    st.markdown("### Impact Scale Guide")
    st.markdown("""
    - **±20%**: Star DP injured/returns
    - **±10%**: Important starter out/back
    - **±5%**: Rotation player news
    - **0%**: No material impact
    """)

# ── Upcoming matches (for override target selection) ─────────────────────────
@st.cache_data(ttl=60)
def load_upcoming_matches() -> pd.DataFrame:
    return db_utils.query(
        """
        SELECT match_id, date, home_team, away_team
        FROM matches
        WHERE status = 'scheduled' AND date >= current_date
        ORDER BY date LIMIT 50
        """
    )


upcoming = load_upcoming_matches()
match_options = {
    f"{row['home_team']} vs {row['away_team']} ({row['date']})": row["match_id"]
    for _, row in upcoming.iterrows()
}

# ── Pending news items ────────────────────────────────────────────────────────
st.markdown("## Pending News Items")
st.caption("Items below have been flagged by Claude as potentially impacting match predictions.")

pending = get_pending_items()

if pending.empty:
    st.info("No pending news items. Check back after the next news poll, or click 'Poll news feeds now'.")
else:
    for _, item in pending.iterrows():
        with st.expander(f"📰 {item['headline'][:100]}", expanded=False):
            col1, col2 = st.columns([2, 1])

            with col1:
                st.markdown(f"**Source:** {item['source']}  |  **Published:** {item.get('published_at', '–')[:16]}")
                if item.get("url"):
                    st.markdown(f"[Read article]({item['url']})")
                st.markdown(f"**Claude Summary:** {item.get('claude_summary', 'N/A')}")
                teams = item.get("teams_mentioned", [])
                if teams:
                    st.markdown(f"**Teams mentioned:** {', '.join(teams) if isinstance(teams, list) else teams}")
                confidence = item.get("impact_confidence", "low")
                conf_color = {"high": "🟢", "medium": "🟡", "low": "🔴"}.get(confidence, "⚪")
                st.markdown(f"**Impact confidence:** {conf_color} {confidence.capitalize()}")

            with col2:
                st.markdown("**Claude's estimated impact:**")
                h_atk = st.slider(
                    "Home attack adj", -0.20, 0.20,
                    float(item.get("estimated_impact_home_atk", 0.0)), 0.01,
                    key=f"h_atk_{item['item_id']}", format="%.2f"
                )
                h_def = st.slider(
                    "Home defense adj", -0.20, 0.20,
                    float(item.get("estimated_impact_home_def", 0.0)), 0.01,
                    key=f"h_def_{item['item_id']}", format="%.2f"
                )
                a_atk = st.slider(
                    "Away attack adj", -0.20, 0.20,
                    float(item.get("estimated_impact_away_atk", 0.0)), 0.01,
                    key=f"a_atk_{item['item_id']}", format="%.2f"
                )
                a_def = st.slider(
                    "Away defense adj", -0.20, 0.20,
                    float(item.get("estimated_impact_away_def", 0.0)), 0.01,
                    key=f"a_def_{item['item_id']}", format="%.2f"
                )

                match_selection = st.selectbox(
                    "Apply to match",
                    ["— select —"] + list(match_options.keys()),
                    key=f"match_{item['item_id']}"
                )

                if st.button("✅ Apply Override", key=f"apply_{item['item_id']}"):
                    if match_selection == "— select —":
                        st.warning("Please select a match first.")
                    else:
                        mid = match_options[match_selection]
                        home_adj = (h_atk - a_def) / 2  # net home strength adjustment
                        away_adj = (a_atk - h_def) / 2  # net away strength adjustment
                        apply_news_override(item["item_id"], mid, home_adj, away_adj)
                        st.success(f"Override applied to {match_selection}!")
                        st.rerun()

                if st.button("🚫 Dismiss", key=f"dismiss_{item['item_id']}"):
                    db_utils.execute(
                        "UPDATE news_items SET confirmed_by_user=TRUE WHERE item_id=?",
                        [item["item_id"]]
                    )
                    st.rerun()

st.markdown("---")

# ── Manual override form ──────────────────────────────────────────────────────
st.markdown("## Manual Override")
st.caption("Add a strength adjustment for any upcoming match without a news item.")

with st.form("manual_override"):
    match_sel = st.selectbox("Select match", list(match_options.keys()))
    description = st.text_input("Description (e.g., 'Key striker listed as doubtful')")
    col_m1, col_m2 = st.columns(2)
    home_manual = col_m1.slider("Home team strength adj", -0.30, 0.30, 0.0, 0.01, format="%.2f")
    away_manual = col_m2.slider("Away team strength adj", -0.30, 0.30, 0.0, 0.01, format="%.2f")

    submitted = st.form_submit_button("Apply Manual Override")
    if submitted and match_sel:
        import uuid
        from datetime import datetime, timezone
        mid = match_options.get(match_sel, "")
        if mid:
            db_utils.execute(
                """
                INSERT INTO overrides (override_id, match_id, applied_at, description,
                                       home_strength_adj, away_strength_adj, source)
                VALUES (%s, %s, %s, %s, %s, %s, 'manual')
                """,
                [str(uuid.uuid4())[:16], mid, datetime.now(timezone.utc).isoformat(),
                 description, home_manual, away_manual]
            )
            st.success(f"Manual override applied: home {home_manual:+.0%}, away {away_manual:+.0%}")

st.markdown("---")

# ── Applied overrides ─────────────────────────────────────────────────────────
st.markdown("## Applied Overrides")

overrides_df = db_utils.query(
    """
    SELECT o.override_id, o.match_id, o.applied_at, o.description,
           o.home_strength_adj, o.away_strength_adj, o.source,
           m.home_team, m.away_team, m.date
    FROM overrides o
    LEFT JOIN matches m ON o.match_id = m.match_id
    ORDER BY o.applied_at DESC
    LIMIT 50
    """
)

if overrides_df.empty:
    st.info("No overrides applied yet.")
else:
    for _, ov in overrides_df.iterrows():
        col_ov1, col_ov2, col_ov3 = st.columns([3, 2, 1])
        with col_ov1:
            match_str = f"{ov.get('home_team','?')} vs {ov.get('away_team','?')} ({ov.get('date','?')})"
            st.markdown(f"**{match_str}**")
            st.caption(ov.get("description", "") or "No description")
        with col_ov2:
            st.metric("Home adj", f"{ov['home_strength_adj']:+.1%}")
            st.metric("Away adj", f"{ov['away_strength_adj']:+.1%}")
        with col_ov3:
            if st.button("Remove", key=f"rm_{ov['override_id']}"):
                db_utils.execute(
                    "DELETE FROM overrides WHERE override_id = %s",
                    [ov["override_id"]]
                )
                st.rerun()
