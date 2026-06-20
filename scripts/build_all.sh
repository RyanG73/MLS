#!/bin/bash
# Rebuild ALL live surfaces — MLS, big-5, 5 second-tier European leagues,
# Liga MX, and all 5 continental competitions.
#
# European league builds auto-detect the latest *started* season via
# data_pipeline.understat (_default_seasons), so this picks up 2026-27
# automatically once it begins (~Aug 2026). Idempotent and safe to re-run.
#
# Continental builds:
#   1. Refresh the current-season cache (MERGE — history is never dropped).
#   2. Rebuild the .js (auto-detects concluded vs. in-progress; no manual state needed).
#
# Per-league data is regenerated into webapp/data/<id>.js. The MLS path is
# unchanged (build_dashboard_data.py); European / Liga MX use build_league_data.py;
# continental comps use build_continental_data.py.
set -uo pipefail   # not -e: one surface failing must not abort the rest

REPO_DIR="${MLS_REPO_DIR:-/Users/ryangerda/Development/MLS}"
cd "$REPO_DIR"

PY="$REPO_DIR/venv/bin/python"
[ -x "$PY" ] || PY="$(command -v python3)"

# Current season start year (e.g. 2026).  Used for continental cache refresh.
CUR=$(date +%Y)
PREV=$((CUR - 1))

echo "=== $(date '+%Y-%m-%d %H:%M:%S') build_all start (CUR=$CUR) ==="

# ── 1. MLS ───────────────────────────────────────────────────────────────────
echo "--- MLS: odds log ---"
PYTHONPATH="$REPO_DIR" "$PY" -m data_pipeline.odds_log \
  || echo "  [WARN] odds_log step failed (non-fatal)"
echo "--- MLS: dashboard data ---"
PYTHONPATH="$REPO_DIR" "$PY" scripts/build_dashboard_data.py \
  && echo "  [OK] mls" \
  || echo "  [WARN] MLS build failed (non-fatal)"

# ── 2. Big-5 European leagues ────────────────────────────────────────────────
for L in epl la-liga serie-a bundesliga ligue-1; do
  echo "--- $L ---"
  PYTHONPATH="$REPO_DIR" "$PY" scripts/build_league_data.py --league "$L" \
    && echo "  [OK] $L" \
    || echo "  [WARN] $L build failed (non-fatal)"
done

# ── 3. 5 second-tier European leagues ────────────────────────────────────────
for L in championship league-one league-two bundesliga-2 serie-b; do
  echo "--- $L ---"
  PYTHONPATH="$REPO_DIR" "$PY" scripts/build_league_data.py --league "$L" \
    && echo "  [OK] $L" \
    || echo "  [WARN] $L build failed (non-fatal)"
done

# ── 4. Liga MX ───────────────────────────────────────────────────────────────
echo "--- liga-mx ---"
PYTHONPATH="$REPO_DIR" "$PY" scripts/build_league_data.py --league liga-mx \
  && echo "  [OK] liga-mx" \
  || echo "  [WARN] liga-mx build failed (non-fatal)"

# ── 5. Continental competitions ───────────────────────────────────────────────
# For each comp: (a) merge-refresh the current season's ESPN cache,
#               (b) rebuild the .js (auto-detects concluded vs. in-progress).
for C in ucl europa conference concacaf-champions leagues-cup; do
  echo "--- continental: $C (cache refresh $PREV-$CUR) ---"
  PYTHONPATH="$REPO_DIR" "$PY" -m data_pipeline.espn_continental \
      --comp "$C" --from-year "$PREV" --to-year "$CUR" \
    || echo "  [WARN] $C cache refresh failed (non-fatal)"
  echo "--- continental: $C (rebuild) ---"
  PYTHONPATH="$REPO_DIR" "$PY" scripts/build_continental_data.py --comp "$C" \
    && echo "  [OK] $C" \
    || echo "  [WARN] $C build failed (non-fatal)"
done

echo "=== $(date '+%Y-%m-%d %H:%M:%S') build_all done ==="
