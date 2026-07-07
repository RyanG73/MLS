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

**Note — two thresholds, two stages.** The Δ > 0.001 bar above is the *harness A/B screening* rule
(deciding which experiments graduate from `eval_baseline.py`). Champion *promotion* is governed
separately by `scripts/promotion_gate.py`, whose `core_metric` gate requires avg-Brier gain ≥ 0.0005
plus the 2024-robustness, calibration, coverage, slice, and source-health guardrails. A change can
pass screening yet fail the gate (or vice versa); the gate is final.

**Season-outcome gate (user directive 2026-07-06).** Match-level Brier is NOT the only
optimization target: the platform's headline claims are team-level season outcomes (champion,
promotion, relegation, playoffs, top-N). Any change that touches the table-sim path — DC fit,
seeding (ELO regression targets, tier bridges, promoted-team priors), temperature, the ranking
key, format handling, or preseason widening — must ALSO run the season-outcome replay:

    python scripts/eval_season_outcomes.py --out experiments/<name>-outcomes.report.json

and report pooled outcome Briers (per checkpoint × outcome) against
`experiments/season-outcomes-baseline.report.json`. A match-Brier KEEP that regresses pooled
outcome Brier beyond +0.002 at any checkpoint needs an explicit justification in the verdict
(the A10(b) precedent: relegation improved monotonically with σ while title/top-4 flagged the
overshoot — the outcome metrics are what caught it). Regenerate the baseline whenever a
sim-path change lands.

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

---

## 10. Canonical-model promotion gate (Phase 4c)

The KEEP/DROP rule above governs **feature-level A/B experiments on the eval harness**.
A separate, stricter gate governs **promotion of the whole canonical model**
(`models/research_model.py`), which is what actually drives the dashboard and the
production DB. A KEEP'd feature is only a *candidate*; it becomes champion only after
the full model clears the promotion gate.

This operationalizes the codebase-review's "circular review loop": every promotion must
pass a multi-criterion gate, not a single aggregate score.

```bash
# 1. Produce a standardized report for the candidate model (per-match + slices)
python scripts/model_report.py --label challenger --out experiments/<id>.report.json

# 2. Run the gate against the current champion (experiments/champion.json)
python scripts/promotion_gate.py evaluate --challenger experiments/<id>.report.json

# 3. If it PASSES, promote it (updates the champion pointer)
python scripts/promotion_gate.py promote --challenger experiments/<id>.report.json
```

**Gate criteria (all must hold):**

| Class | Criterion | Rule |
|-------|-----------|------|
| Guardrail | coverage | challenger n per season ≥ champion (data not shrunk) |
| Guardrail | robustness_2024 | challenger 2024 Brier ≤ champion + 0.0005 *(CLAUDE.md hard gate)* |
| Guardrail | calibration | challenger cal_err ≤ champion + 0.005 |
| Guardrail | slices | no season/confidence slice regresses by > 0.02 |
| Improvement | core_metric | challenger avg Brier improves by ≥ 0.0005 |

The gate is self-tested (`python scripts/promotion_gate.py self-test`) to confirm it
rejects identical, 2024-regressing, and calibration-blowup challengers while promoting a
genuine improvement. `build_dashboard_data.py` should generate only from the champion.

Market/edge slices (model-vs-market disagreement, edge distribution, CLV) require the
odds DB and are reported as deferred when run on the odds-free parity frame.
