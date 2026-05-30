# Future Exploration & Subagent Deployment Catalog

> Running backlog of opportunities, populated by the improvement loop and seeded
> from the initial workflow-building session. Each cloud iteration appends new
> ideas it surfaces. This is the next round's roadmap.

---

## Future feature/model exploration

### Calibration (highest-leverage right now)
- **Confirm Platt vs temperature as the harness default.** Seeding probe showed Platt cuts decile cal error 0.146 → 0.094 with no Brier loss. If isotonic/beta don't beat it, switch the default.
- **Per-class calibration methods.** The draw class is the hardest (Brier ~0.194). Try calibrating draw separately (it may need isotonic while home/away use Platt).
- **Calibrate the ensemble output, not just per-model.** Current cal error is measured on the stacked ensemble's home-win deciles; a post-stack calibration layer is untested.
- **Target < 0.05 decile error** — required before probabilities are fit for Kelly sizing (the production gate).

### Features (from docs/feature-hunt-log.md, queued `should-implement: yes`)
- **+TZShift** — timezone/jetlag proxy from `_TEAM_COORDS` (deterministic, no new I/O).
- **+PythagLuck** — rolling Pythagorean over-performance (luck/regression signal; orthogonal to ELO and rolling xG).
- **+MinutesHHI** — squad minutes concentration (starter-dependency / rotation fragility; pairs with games_in_14d).
- **Lineup-aware availability** — deferred (needs DB; eval is DB-free). Revisit if ASA player metrics plateau.
- **FotMob player ratings** — deferred (reverse-engineered API risk). Needs an ADR before revival.

### Model architecture
- **XGB-only ensemble.** PLAN.md flags DC dragging the stack (stacked 0.6437 vs XGB-alone 0.6387). Test dropping DC probs from the meta-learner while keeping dc_lam/dc_mu as XGB features.
- **Simple average vs meta-learner.** The LogisticRegression stack may overfit the ~500-sample cal fold; test whether a plain probability average is more robust.
- **Betting-aware loss.** `betting_logloss()` exists in models/gradient_boost.py but is untested in the eval harness — weights misclassifications by 1/decimal_odds.

### Hyperparameters
- **Settle REGRESS 0.40 vs 0.50** — CLAUDE.md documents 0.40 but the in-file default is 0.50; never A/B'd directly.
- **DC decay half-life sweep** — 120d is assumed; 60/90/150/180 untested under the current feature set.
- **Expand ELO grid** beyond K∈{20,25,30} × HA∈{80,100,120}.

### Data / determinism
- **Persist the ASA cache across cloud runs.** `data/eval_cache/` is gitignored, so each hourly run re-fetches live ASA data (slow, non-deterministic if ASA updates). Consider committing a frozen cache snapshot or a fixed as-of date so all iterations compare against identical data.
- **Per-season robustness, not just averages.** 2024 is consistently the weakest test season (~0.652 vs 0.631 for 2022). Investigate whether a recency-weighted or 2024-specific signal helps.

---

## Future subagent deployment

### Existing agents to keep cycling
- **calibration-tuner** — clearest near-term win (the < 0.05 cal-error target). Deploy first.
- **model-architect** — the XGB-only-ensemble question is high-value and well-defined.
- **feature-engineer** — three candidates already queued; cheap, deterministic.
- **hyperparameter-optimizer** — lowest expected lift but fully automatable.

### New specialised agents worth building
- **data-integrator agent** — owns new ASA / worldfootballR / Transfermarkt source wiring (the Transfermarkt squad-value path is half-built: `scripts/import_transfermarkt.py` exists but `+TM_SquadValue` is unevaluated). Would feed the feature-engineer rather than competing with it.
- **eval-cache / reproducibility agent** — owns freezing ASA data to a fixed as-of date and committing a deterministic cache, so every experiment is exactly comparable. Removes the biggest source of cross-run noise.
- **production-port agent** — once the research harness improves, owns porting KEEP'd changes from `scripts/eval_baseline.py` into `features/`/`models/`/`config/` with the existing tests as the gate (currently a manual, deferred step).
- **regression-watchdog agent** — periodically re-runs the registered best config to detect silent drift when ASA backfills/revises historical data.

### Orchestration improvements
- **Parallel worktree dispatch** — the local `/improve-model` runs agents in parallel git worktrees; the cloud loop currently runs one component per hour serially. A cloud orchestrator that fans out to 4 sub-sessions and greedy-merges would compress 8 hours into ~2.
- **Auto-PR on cumulative KEEP** — when the loop's cumulative Brier beats the start-of-loop baseline by a meaningful margin, open a PR rather than only committing to the branch.

<!-- cloud iterations append new ideas below -->
