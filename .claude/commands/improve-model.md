# /improve-model — Multi-Agent Model Improvement Orchestrator

Run one full improvement cycle: pin a baseline, dispatch all four component agents in parallel git worktrees, collect results, rank them, and greedily forward-merge winners with a re-eval gate.

## What this does (full cycle)

```
1. Pin baseline  ──►  2. Dispatch 4 agents in parallel worktrees
                           ├── feature-engineer    (one feature candidate)
                           ├── calibration-tuner   (sweep cal methods)
                           ├── hyperparameter-optimizer (sweep knobs)
                           └── model-architect     (one structural test)
                       ↓
3. Collect results from each agent's worktree
4. Compare via scripts/experiment.py compare
5. Greedy forward-merge (merge best winner → re-eval → merge next → ...)
6. Update docs/PLAN.md + commit on dev branch
```

## Usage

```bash
/improve-model              # full 4-agent cycle
/improve-model --component feature    # single-component run (feature-engineer only)
/improve-model --component calibration
/improve-model --component hyperparameters
/improve-model --component architecture
/improve-model --dry-run    # only pin baseline + show what would run; no agents dispatched
```

---

## Step-by-step orchestration

### Step 1 — Preflight checks

Before dispatching agents, verify:
1. Working directory is `claude/mls-prediction-dashboard-C2mQM` branch (per CLAUDE.md — never work on main).
2. No uncommitted harness changes to `scripts/eval_baseline.py` (agent baselines must be reproducible).
3. Python env is active: `source venv/bin/activate`.
4. ASA API reachable (or `--cache` pre-warmed — see Step 2).

```bash
git branch --show-current
git status scripts/eval_baseline.py
```

### Step 2 — Pin baseline + pre-warm cache

Pre-warming ensures all agents run against identical frozen data:

```bash
# Pre-warm the ASA cache (one live fetch; all subsequent --cache runs are instant)
python scripts/experiment.py baseline --cache
```

Record the baseline `experiment_id` from the output. This becomes the comparison anchor for the whole cycle.

### Step 3 — Dispatch agents in parallel worktrees

Use `git worktree add` so each agent works on an isolated copy of the repo:

```bash
# Create one worktree per component
git worktree add ../mls-feature    claude/mls-prediction-dashboard-C2mQM
git worktree add ../mls-calib      claude/mls-prediction-dashboard-C2mQM
git worktree add ../mls-hyperparam claude/mls-prediction-dashboard-C2mQM
git worktree add ../mls-arch       claude/mls-prediction-dashboard-C2mQM
```

Then dispatch each agent (these can be Claude Code subagents or manual runs):

```bash
# Feature engineering agent (in ../mls-feature)
# Reads: docs/feature-hunt-log.md, scripts/eval_baseline.py
# Protocol: .claude/agents/feature-engineer.md

# Calibration agent (in ../mls-calib)
# No code edits — uses CLI flags only
# Protocol: .claude/agents/calibration-tuner.md

# Hyperparameter agent (in ../mls-hyperparam)
# No code edits — uses CLI flags only
# Protocol: .claude/agents/hyperparameter-optimizer.md

# Architecture agent (in ../mls-arch)
# Protocol: .claude/agents/model-architect.md
```

Each agent will report back:
```
AGENT: <name>
EXPERIMENT_ID: <id>
VERDICT: KEEP / marginal / DROP
Δ best_brier: <value>
Δ max_cal_error: <value>
ONE-LINE SUMMARY: ...
```

### Step 4 — Collect and compare

Once all agents report, run the comparison:

```bash
python scripts/experiment.py compare
```

This ranks all registered experiments vs the baseline and shows the KEEP/DROP verdict for each.

### Step 5 — Greedy forward-merge

> **Why greedy, not simultaneous?** The four agents edit overlapping regions of `scripts/eval_baseline.py` (calibration and architecture both modify the walk-forward loop; hyperparameters interact with calibration). Merging all at once risks conflicts and non-additive interactions. Merging one at a time with a re-eval gate prevents this.

**Merge order:**
1. **Feature agent first** — the `AB_SETS` addition is low-conflict with other changes; just promote the new columns.
2. **Hyperparameter agent second** — pure config changes, no code conflict.
3. **Calibration agent third** — modifies `calibrate_multiclass`, potentially interacts with hyperparameters.
4. **Architecture agent last** — modifies the ensemble loop, highest conflict risk.

For each agent's KEEP result:

```bash
# Example: merge feature worktree changes back to main worktree
cd /path/to/main/repo
git diff ../mls-feature/scripts/eval_baseline.py scripts/eval_baseline.py

# If the diff looks correct (only the feature's additions):
git checkout ../mls-feature/scripts/eval_baseline.py -- scripts/eval_baseline.py

# Re-evaluate to confirm cumulative improvement
python scripts/experiment.py run \
  --name "merge-after-<component>" \
  --notes "Post-merge re-eval after accepting <component> changes" \
  -- --ab-only "Base" --cache

# Check python scripts/experiment.py compare — is cumulative Brier still better than baseline?
# If yes: proceed to next merge. If no: revert this merge.
```

Skip an agent's changes if the cumulative re-eval shows regression.

### Step 6 — Update PLAN.md and commit

After all greedy merges are settled:

1. Update `docs/PLAN.md` "Live eval results" block with the new best Brier, cal error, and the winning features/configs from this cycle.
2. Clean up worktrees: `git worktree remove ../mls-feature` etc.
3. Commit on the dev branch (never main):

```bash
git add scripts/eval_baseline.py docs/PLAN.md docs/feature-hunt-log.md \
        docs/calibration-log.md docs/hyperparameter-log.md docs/architecture-log.md \
        experiments/registry.jsonl
git commit -m "Improvement cycle: <brief summary of what was KEPT>

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Decision tree

```
For each KEEP experiment:
  Is cumulative Brier after merge < baseline Brier?
    YES → accept merge, proceed
    NO  → revert merge, skip this agent's contribution this cycle

Is final cumulative Brier improvement > 0.001?
  YES → commit + update PLAN.md
  NO  → commit logs only; no harness change; note in PLAN.md
```

---

## Key constraints (from CLAUDE.md)

- Branch: `claude/mls-prediction-dashboard-C2mQM` only. Never main.
- Production port (`features/`, `models/`, `config/`) is a separate step. `/improve-model` only updates the research harness.
- Update `docs/PLAN.md` "Live eval results" in the same commit as harness changes.

---

## Autonomous mode (scheduled)

For unattended operation, `scripts/run_improvement_cycle.sh` runs a single-component cycle per tick and appends to the logs. See that script for the cron invocation.
