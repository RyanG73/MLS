#!/usr/bin/env bash
# scripts/run_improvement_cycle.sh
#
# Headless single-component improvement cycle for the MLS prediction harness.
# Designed for autonomous/scheduled operation (cron, /schedule, /loop).
#
# Usage:
#   ./scripts/run_improvement_cycle.sh [--component <name>] [--no-baseline]
#
# Components (default: rotate round-robin based on day-of-week):
#   feature        Run feature-engineer agent on next queued candidate
#   calibration    Sweep calibration methods
#   hyperparameters Sweep ELO / DC / XGB knobs
#   architecture   Test one structural question
#
# Environment:
#   MLS_COMPONENT    Override the component to run (alternative to --component flag)
#   MLS_REPO         Path to the repo root (default: directory containing this script/..)
#
# Examples:
#   # Run today's rotating component
#   ./scripts/run_improvement_cycle.sh
#
#   # Force feature engineering
#   ./scripts/run_improvement_cycle.sh --component feature
#
#   # Scheduled via cron (nightly at 2am)
#   0 2 * * * cd /path/to/MLS && ./scripts/run_improvement_cycle.sh >> logs/improvement.log 2>&1

set -euo pipefail

# ─── Configuration ────────────────────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="${MLS_REPO:-$(dirname "$SCRIPT_DIR")}"
VENV_PYTHON="$REPO_ROOT/venv/bin/python"
PYTHON="${VENV_PYTHON:-python3}"
LOG_DIR="$REPO_ROOT/logs"
TIMESTAMP="$(date -u +%Y%m%dT%H%M%S)"

mkdir -p "$LOG_DIR"

# ─── Argument parsing ─────────────────────────────────────────────────────────

COMPONENT="${MLS_COMPONENT:-}"
SKIP_BASELINE=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --component)
            COMPONENT="$2"
            shift 2
            ;;
        --no-baseline)
            SKIP_BASELINE=true
            shift
            ;;
        *)
            echo "[run_improvement_cycle] Unknown arg: $1" >&2
            exit 1
            ;;
    esac
done

# Rotate by day-of-week if no component specified
if [[ -z "$COMPONENT" ]]; then
    DOW="$(date +%u)"  # 1=Mon ... 7=Sun
    case "$DOW" in
        1) COMPONENT="feature"         ;;
        2) COMPONENT="calibration"     ;;
        3) COMPONENT="hyperparameters" ;;
        4) COMPONENT="architecture"    ;;
        5) COMPONENT="feature"         ;;
        6) COMPONENT="hyperparameters" ;;
        7) COMPONENT="feature"         ;;
        *) COMPONENT="feature"         ;;
    esac
fi

echo "============================================================"
echo "MLS Improvement Cycle — $TIMESTAMP"
echo "Component: $COMPONENT"
echo "Repo: $REPO_ROOT"
echo "Python: $PYTHON"
echo "============================================================"

cd "$REPO_ROOT"

# ─── Preflight checks ─────────────────────────────────────────────────────────

# Confirm we are on the correct branch
CURRENT_BRANCH="$(git branch --show-current)"
if [[ "$CURRENT_BRANCH" != "claude/mls-prediction-dashboard-C2mQM" ]]; then
    echo "[WARN] Not on claude/mls-prediction-dashboard-C2mQM (on '$CURRENT_BRANCH')."
    echo "       Proceeding anyway — results will be recorded with the current SHA."
fi

# Activate venv if available
if [[ -f "$REPO_ROOT/venv/bin/activate" ]]; then
    source "$REPO_ROOT/venv/bin/activate"
    echo "venv activated."
fi

# ─── Step 1: Ensure baseline exists ──────────────────────────────────────────

if [[ "$SKIP_BASELINE" == "false" ]]; then
    # Check if a baseline exists; only record a new one if registry is empty or has none
    REGISTRY="$REPO_ROOT/experiments/registry.jsonl"
    HAS_BASELINE=false
    if [[ -f "$REGISTRY" ]] && grep -q '"role": "baseline"' "$REGISTRY"; then
        HAS_BASELINE=true
    fi

    if [[ "$HAS_BASELINE" == "false" ]]; then
        echo "[Step 1] No baseline found. Recording baseline (this fetches live ASA data)..."
        "$PYTHON" "$REPO_ROOT/scripts/experiment.py" baseline --cache \
            --name "auto-baseline-$TIMESTAMP"
        echo "[Step 1] Baseline recorded."
    else
        echo "[Step 1] Baseline already exists in registry. Skipping re-baseline."
    fi
else
    echo "[Step 1] Skipping baseline (--no-baseline)."
fi

# ─── Step 2: Run the component agent ─────────────────────────────────────────

echo ""
echo "[Step 2] Running $COMPONENT agent..."

EXPERIMENT_FLAGS="--cache --ab-only Base"
EXPERIMENT_NAME=""
EXPERIMENT_NOTES=""

case "$COMPONENT" in

    feature)
        # Feature engineering: run next queued hunt-log candidate
        # Reads docs/feature-hunt-log.md to find the next should-implement: yes entry
        # not already in AB_SETS, then implements + tests it.
        #
        # Because this requires Claude to implement code, the autonomous path here
        # dispatches a Claude subagent with the feature-engineer protocol.
        # In standalone mode (no Claude), it prints instructions and exits.
        echo ""
        echo "Feature engineering agent requires a Claude subagent."
        echo "To run manually:"
        echo "  1. Read docs/feature-hunt-log.md for the next should-implement: yes entry"
        echo "  2. Follow .claude/agents/feature-engineer.md protocol"
        echo "  3. Run: python scripts/experiment.py run --name feat-<slug> --cache -- --ab-only 'Base,+<Set>'"
        echo ""
        echo "For automated dispatch, use '/improve-model --component feature' in Claude Code."
        ;;

    calibration)
        # Sweep all four calibration methods
        echo "Running calibration sweep..."
        for METHOD in temperature platt isotonic; do
            NAME="auto-cal-${METHOD}-${TIMESTAMP}"
            echo "  → Calibration: $METHOD"
            "$PYTHON" "$REPO_ROOT/scripts/experiment.py" run \
                --name "$NAME" \
                --notes "Autonomous calibration sweep: $METHOD" \
                -- --calibration "$METHOD" --ab-only "Base" --cache \
                2>&1 | tee -a "$LOG_DIR/improvement-${TIMESTAMP}.log" || true
        done
        ;;

    hyperparameters)
        # Sweep a subset of hyperparameter combinations
        echo "Running hyperparameter sweep (targeted)..."

        # REGRESS 0.40 vs default 0.50 (documented discrepancy in CLAUDE.md vs script)
        "$PYTHON" "$REPO_ROOT/scripts/experiment.py" run \
            --name "auto-hyp-regress040-${TIMESTAMP}" \
            --notes "Autonomous sweep: REGRESS=0.40 (CLAUDE.md documented value)" \
            -- --regress 0.40 --ab-only "Base" --cache \
            2>&1 | tee -a "$LOG_DIR/improvement-${TIMESTAMP}.log" || true

        # DC half-life 90 vs default 120
        "$PYTHON" "$REPO_ROOT/scripts/experiment.py" run \
            --name "auto-hyp-dchl090-${TIMESTAMP}" \
            --notes "Autonomous sweep: DC decay half-life 90 days" \
            -- --dc-decay-hl 90 --ab-only "Base" --cache \
            2>&1 | tee -a "$LOG_DIR/improvement-${TIMESTAMP}.log" || true
        ;;

    architecture)
        echo ""
        echo "Architecture agent requires manual Claude invocation."
        echo "To run: '/improve-model --component architecture' in Claude Code"
        echo "or follow .claude/agents/model-architect.md protocol directly."
        ;;

    *)
        echo "[ERROR] Unknown component: $COMPONENT" >&2
        echo "Valid: feature, calibration, hyperparameters, architecture" >&2
        exit 1
        ;;
esac

# ─── Step 3: Print comparison table ──────────────────────────────────────────

echo ""
echo "[Step 3] Experiment comparison:"
"$PYTHON" "$REPO_ROOT/scripts/experiment.py" compare \
    2>&1 | tee -a "$LOG_DIR/improvement-${TIMESTAMP}.log" || true

# ─── Step 4: Append cycle summary to log ─────────────────────────────────────

echo ""
echo "[Done] Cycle complete for component: $COMPONENT at $TIMESTAMP"
echo "Logs: $LOG_DIR/improvement-${TIMESTAMP}.log"
echo ""
echo "Next steps:"
echo "  - Review experiments/registry.jsonl for KEEP verdicts"
echo "  - Run '/improve-model' in Claude Code for the full merge + PLAN.md update"
echo "  - Or run 'python scripts/experiment.py compare' to see current standings"
