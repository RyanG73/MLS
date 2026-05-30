# MLS Experiment Protocol — Shared Agent Contract

> Every component agent (feature-engineer, calibration-tuner, hyperparameter-optimizer, model-architect) must follow this protocol. Read it in full before starting work.

---

## 1. Baseline first

Before running any experiment, confirm a baseline exists in `experiments/registry.jsonl`. If the registry is empty, the **orchestrator** runs this first — but if you need to create one yourself:

```bash
python scripts/experiment.py baseline --cache
```

The baseline must be on the `claude/mls-prediction-dashboard-C2mQM` branch (no uncommitted harness changes) so it reflects the current best-known state.

---

## 2. One change at a time

Each invocation of an agent makes **exactly one isolated change** — one feature group, one calibration method, one set of hyperparameter values, one architectural variant. Do not bundle multiple changes in a single run. This ensures each delta is attributable.

---

## 3. Running an experiment

```bash
python scripts/experiment.py run \
  --name "<component>-<descriptor>" \
  --notes "<one-line hypothesis>" \
  -- <eval_baseline.py flags>
```

Always include `--cache` to use frozen ASA data (consistent dataset across agents). Always include `--ab-only "Base,+YourSet"` (feature agent) or `--ab-only "Base"` (other agents) to minimise runtime.

The runner writes the result to `experiments/<id>.json` and appends a line to `experiments/registry.jsonl`.

---

## 4. KEEP / DROP rule

Compare your experiment's `best_brier` to the baseline's `best_brier` from `experiments/registry.jsonl`:

| Condition | Verdict | Action |
|-----------|---------|--------|
| Δ > +0.001 (lower is better) | **KEEP** | Apply the change; if it's a feature, promote to `_FEAT_BASE` |
| 0 < Δ ≤ +0.001 | **marginal** | Keep the code change but do NOT promote to Base; log as marginal |
| Δ ≤ 0 | **DROP** | Revert the code change (`git checkout scripts/eval_baseline.py`); log the reason |

For the calibration agent, the primary metric is `max_decile_calibration_error` (target < 0.05); a secondary veto applies if `best_brier` regresses by > 0.001.

---

## 5. Scope guard

Each agent owns **exactly one component**. Never cross component boundaries:

| Agent | May edit |
|-------|----------|
| feature-engineer | Feature computation block + `AB_SETS` dict in `scripts/eval_baseline.py` |
| calibration-tuner | CLI flags only — no code edits |
| hyperparameter-optimizer | CLI flags only — no code edits |
| model-architect | Walk-forward loop / ensemble construction in `scripts/eval_baseline.py` |
| All agents | Their own log file (`docs/<component>-log.md`) |

No agent touches `features/`, `models/`, `config/`, `data_pipeline/`, `scripts/daily_update.py`, or any production pipeline file. Research-first rule (from CLAUDE.md): all improvements land in `scripts/eval_baseline.py` first; production port is a separate step.

---

## 6. Logging

Append a structured entry to your component's log file after every run:

**Feature agent → `docs/feature-hunt-log.md`:**
```markdown
## <YYYY-MM-DD> — <Feature name>
**Result:** Δ=<value> → KEEP / marginal / DROP
**experiment_id:** <id>
**Notes:** <observations>
```

**Calibration agent → `docs/calibration-log.md`:**
```markdown
## <YYYY-MM-DD> — <Method sweep description>
| Method | best_brier | max_cal_error | Δ Brier | Δ CalErr | Verdict |
...
```

**Hyperparameter agent → `docs/hyperparameter-log.md`:**
```markdown
## <YYYY-MM-DD> — <Param sweep>
| Param | Value | best_brier | Δ | Verdict |
...
```

**Architecture agent → `docs/architecture-log.md`:**
```markdown
## <YYYY-MM-DD> — <Change>
**Hypothesis:** ...
**Result:** ...
```

---

## 7. Branch and git rules

- All work on `claude/mls-prediction-dashboard-C2mQM` (never push to main — CLAUDE.md rule).
- In a multi-agent cycle, each agent works in its own git worktree (`git worktree add ../mls-<component> <branch>`).
- When reporting back to the orchestrator, provide: experiment_id, verdict, Δ best_brier, Δ cal_error.
- After KEEP decisions, the **orchestrator** merges worktrees one at a time with a re-eval gate (see `docs/improve-model-orchestrator.md`).

---

## 8. Never commit to production without explicit instruction

Even after a KEEP decision, do **not** port the improvement to `features/`, `models/`, or `config/`. The orchestrator decides when to initiate a production port. This is the research-first rule from CLAUDE.md.

---

## 9. Reporting back

When your work is done, output a brief structured summary:

```
AGENT: <component-name>
EXPERIMENT_ID: <id>
VERDICT: KEEP / marginal / DROP
Δ best_brier: <value> (lower = better; KEEP threshold = -0.001)
Δ max_cal_error: <value> (lower = better; target < 0.05)
ONE-LINE SUMMARY: <what changed and why it worked/didn't>
```
