#!/bin/bash
# Rebuild ALL live leagues — MLS + the big-5 European leagues.
#
# The seasonal / scheduled entry point for the multi-league platform. European
# builds auto-detect the latest *started* season (data_pipeline.understat
# _default_seasons), so this picks up 2026-27 automatically once it begins
# (~Aug 2026); until then the European leagues correctly show completed 2025-26
# final tables. Idempotent and safe to re-run.
#
# Per-league data is regenerated into webapp/data/<id>.js. The MLS path is
# unchanged (build_dashboard_data.py); the European path uses build_league_data.py
# (Understat matches+xG + football-data.co.uk market odds).
set -uo pipefail   # not -e: one league failing must not abort the rest

REPO_DIR="${MLS_REPO_DIR:-/Users/ryangerda/Development/MLS}"
cd "$REPO_DIR"

PY="$REPO_DIR/venv/bin/python"
[ -x "$PY" ] || PY="$(command -v python3)"

echo "=== $(date '+%Y-%m-%d %H:%M:%S') build_all start ==="

# 1. MLS — opening-line odds log (non-fatal) + dashboard data
"$PY" -m data_pipeline.odds_log || echo "odds_log step failed (non-fatal)"
"$PY" scripts/build_dashboard_data.py || echo "MLS build failed"

# 2. Big-5 European leagues (Understat cache + football-data market refresh
#    happen inside each build via the adapters)
for L in epl la-liga serie-a bundesliga ligue-1; do
  echo "--- building $L ---"
  "$PY" scripts/build_league_data.py --league "$L" || echo "$L build failed (non-fatal)"
done

echo "=== $(date '+%Y-%m-%d %H:%M:%S') build_all done ==="
