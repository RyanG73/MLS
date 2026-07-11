#!/bin/bash
# Rebuild ALL live surfaces — MLS, big-5, 5 original second-tier European
# leagues, Liga MX, the Tier-1 expansion batch (Brazil/Japan/Sweden/Norway/
# Denmark/Poland/Argentina/England National League), the C1 batch (LaLiga2,
# Ligue 2, Eredivisie, Primeira, Süper Lig, Scottish Prem, Belgian Pro, Greek
# Super League, NWSL, USL Championship), and all 5 continental competitions.
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

# ── 4b. League expansion, 2026-07-10 (Tier-1 + England tier 5) ───────────────
for L in brazil-serie-a japan-j1 sweden-allsvenskan norway-eliteserien \
        denmark-superliga poland-ekstraklasa argentina-primera national-league; do
  echo "--- $L ---"
  PYTHONPATH="$REPO_DIR" "$PY" scripts/build_league_data.py --league "$L" \
    && echo "  [OK] $L" \
    || echo "  [WARN] $L build failed (non-fatal)"
done

# ── 4c. C1 batch, 2026-07-10: non-big-5 top flights + missing 2nd tiers ──────
# Audit found these live leagues had payloads only updated by manual runs —
# never wired into the scheduled nightly build. nwsl/usl-championship share
# the same --league entrypoint (source="asa" internally, see build_league_data.py).
for L in segunda ligue-2 eredivisie primeira super-lig scottish-prem \
        belgian-pro greek-super nwsl usl-championship; do
  echo "--- $L ---"
  PYTHONPATH="$REPO_DIR" "$PY" scripts/build_league_data.py --league "$L" \
    && echo "  [OK] $L" \
    || echo "  [WARN] $L build failed (non-fatal)"
done

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

# Cross-league power rankings (aggregates the freshly-built league .js files)
"$PY" scripts/build_power_rankings.py || echo "power rankings build failed (non-fatal)"

# ── Payload contract gate ─────────────────────────────────────────────────────
# Runs after all builds so failures are reported together.  Non-zero exit
# means one or more payloads contain NaN / missing required fields.
echo "--- payload validation ---"
PYTHONPATH="$REPO_DIR" "$PY" scripts/validate_payloads.py \
  && echo "  [OK] all payloads valid" \
  || echo "  [WARN] payload validation failed — review output above before publishing"

# ── Drift-tracking accrual (docs/drift-playbook.md) ───────────────────────────
# Must run AFTER every league is rebuilt above — these three scripts read the
# just-written webapp/data/*.js payloads, not the model directly. Found
# 2026-07-10: this whole chain was never wired into either scheduled build, so
# odds_history.parquet had only accrued on ad hoc manual runs since B10 shipped.
echo "--- odds/projection history archive ---"
PYTHONPATH="$REPO_DIR" "$PY" scripts/archive_odds_snapshot.py \
  || echo "  [WARN] archive_odds_snapshot failed (non-fatal)"
echo "--- model-odds movers ---"
PYTHONPATH="$REPO_DIR" "$PY" scripts/build_movers.py \
  || echo "  [WARN] build_movers failed (non-fatal)"
echo "--- drift report ---"
PYTHONPATH="$REPO_DIR" "$PY" scripts/build_drift_report.py \
  || echo "  [WARN] build_drift_report failed (non-fatal)"
echo "--- model slice report ---"
PYTHONPATH="$REPO_DIR" "$PY" scripts/build_slice_report.py \
  || echo "  [WARN] build_slice_report failed (non-fatal)"
