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

### Iteration 3 additions (feature: +TZShift marginal)

## Future feature/model exploration

- **+PythagLuck (next priority).** Rolling Pythagorean over-performance is the next `should-implement: yes` candidate. Expected Δ −0.0010 to −0.0030; orthogonal to ELO and rolling xG. Implement as `home_pythag_luck_10`, `away_pythag_luck_10`, `pythag_luck_diff` in `add_rolling_features()` — no new I/O. This is the highest-priority feature for Iteration 7 (next feature round).
- **+TZShift × +Games14d interaction.** TZ shift is inconsistent by season (helps 2023, neutral 2022/2024). The signal may only activate under schedule congestion — test `+TZShift+Games14d` combined set: XGB can learn the cross-term (cross-timezone trip AND tight schedule = compounding fatigue). May surface the latent effect without over-fitting either feature alone.
- **Signed TZ shift deeper analysis.** Eastward vs westward travel may require a non-linear treatment (e.g., dummy for "≥2 zones eastward") rather than a single continuous column. Worth exploring if the combined set above shows promise.
- **+MinutesHHI** — squad minutes concentration (starter-dependency / fatigue amplifier when HHI is high). Third `should-implement: yes` candidate.

## Future subagent deployment

- **Feature-interaction scanner.** A lightweight agent that takes pairs of marginal AB sets (e.g., +TZShift × +Games14d) and tests their combination — often marginal × marginal = synergistic KEEP when the interaction term is what carries signal.

### Iteration 2 additions (hyperparameter sweep findings)

## Future feature/model exploration

- **Re-run REGRESS=0.40 sweep (highest priority).** The Iteration 2 experiment was accidentally killed before capturing the 2024 result. Partial 2022/2023 data both favor REGRESS=0.40 over 0.50 (matching CLAUDE.md). This is the most important unresolved question going into Iteration 6 (next hyperparameter round). Run SEQUENTIALLY (not in parallel).
- **DC decay sweep: test 150d and 180d.** The 90d half-life is clearly worse (calibration degrades). Worth testing longer half-lives (150d, 180d) to see if more history helps — especially given the 2024 DC drag problem. The DC fit weights recent matches more with shorter hl; longer hl might produce more stable probs.
- **weight-hl sweep.** The XGB season sample-weight half-life (currently 4) was not tested in Iteration 2 due to time. Candidates: 2, 6, 8. A shorter weight-hl would give more emphasis to recent seasons (e.g., 2023 over 2019 when training for 2024), which may help the 2024 weakness.
- **XGB-only ensemble (top priority for Iteration 4).** The 2024 per-season table for dc-hl090 clearly shows XGB alone (0.6376) beats stacked (0.6509) by 0.013. DC drag is severe for 2024. The model-architect agent should test removing DC probabilities from the meta-learner, keeping only dc_lam/dc_mu as XGB features (via +DCParams).
- **Sequential experiment execution.** Running experiments in parallel on this 4-core machine causes severe XGB thread contention (16 threads per process × 2 = 32 threads on 4 cores). Each experiment took 30-45 minutes instead of the expected 5-10 minutes. All future iterations MUST run experiments sequentially to stay within the 1-hour budget.

## Future subagent deployment

- **Sequential executor.** The improvement loop should run experiments one at a time (not launch all in parallel) when on a 4-core machine. Consider adding `nthread=2` to XGBoost in eval_baseline.py to cap per-process thread use and enable parallel experiment runs safely.

### Iteration 1 additions (calibration sweep findings)

## Future feature/model exploration

- **Install betacal and re-sweep.** Beta calibration was skipped because the package is absent.
  `pip install betacal` in the venv and re-run once in a future calibration iteration.
  With small ~500-sample cal folds, beta calibration's tighter parametric form may fit
  better than Platt's unconstrained sigmoid.
- **Post-stack calibration layer.** The stacked ensemble's cal_err (0.1130) is still far
  from the <0.05 target. A second calibration pass applied *after* the meta-learner —
  essentially a two-stage approach — is untested. This would not change any model, only
  the final probability transformation.
- **Draw-class separate calibration.** Draw is consistently the hardest class (Brier ~0.194).
  Fitting a separate calibrator (e.g. isotonic) for the draw class while keeping temperature
  for home/away might improve draw probability accuracy without risking overall Brier.
- **Harness version audit.** The seeding session (main@ebedf812) and this branch (ae152d30)
  produce materially different calibration metrics for the same method (Platt on main gave
  cal_err=0.0941; on this branch 0.1561). Before assuming the branch harness is correct,
  diff the calibration and stacking code between the two commits and document what changed.

## Future subagent deployment

- **betacal-installer sub-step.** Before the next calibration agent run, add a requirements.txt
  entry for betacal so that all four calibration methods are available in the cloud env.
- **Harness-diff agent.** One-shot agent to read the diff between main@ebedf812 and this branch
  at ae152d30, specifically in the `calibrate_multiclass`, `decile_cal_error`, and
  meta-learner sections, and explain *why* Platt's cal_err flips direction between branches.
  The finding should inform whether future calibration iteration results can be trusted.
