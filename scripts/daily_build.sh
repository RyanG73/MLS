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

echo "=== $(date '+%Y-%m-%d %H:%M:%S') daily_build done ==="
