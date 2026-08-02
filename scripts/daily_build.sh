#!/bin/bash
# Daily webapp build (DB-free, webapp-only production).
# Rebuilds webapp/data/mls.js from the canonical research model and logs any new
# Pinnacle opening lines. Intended to run on a schedule via launchd
# (see scripts/com.mls.dashboard.plist). Idempotent and safe to re-run.
set -euo pipefail

REPO_DIR="${MLS_REPO_DIR:-/Users/ryangerda/Development/MLS}"
cd "$REPO_DIR"

PY="$REPO_DIR/venv/bin/python"
[ -x "$PY" ] || PY="$(command -v python3)"

echo "=== $(date '+%Y-%m-%d %H:%M:%S') daily_build start ==="

# 1. Opening-line odds log (no-ops cleanly without ODDS_API_KEY)
"$PY" -m data_pipeline.odds_log || echo "odds_log step failed (non-fatal)"

# 2. Rebuild the dashboard data file (the production artifact)
"$PY" scripts/build_dashboard_data.py

# 3. Curated multi-source news feeds (per-feed failures are non-fatal inside)
"$PY" scripts/build_news.py || echo "build_news step failed (non-fatal)"

# 4. Re-aggregate the home payload from the news files step 3 just rewrote.
#    Without this the home rail keeps serving whatever news/*.js held the last
#    time some *other* job (build_all.sh, refresh-fast.yml) happened to run
#    build_home.py — which is how darts and cricket sat under "EFL League One"
#    and "Premier League" on the live home page for a full day after
#    route_item() had already learned to reject them.
PYTHONPATH="$REPO_DIR" "$PY" scripts/build_home.py \
  || echo "build_home step failed (non-fatal)"

echo "=== $(date '+%Y-%m-%d %H:%M:%S') daily_build done ==="
