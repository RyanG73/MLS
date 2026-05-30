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

### Iteration 5 additions (calibration: beta DROP, temperature stability confirmed)

## Future feature/model exploration

- **Add betacal to requirements.txt.** Beta calibration is now known to work (betacal 1.1.0 installed this iteration) but requires `pip install betacal` each cloud run. Adding it to requirements.txt would make it available immediately in future cloud sessions.
- **Two-stage post-stack calibration.** Apply temperature scaling first (as currently) then a second lightweight pass (isotonic or beta) on the stacked ensemble's output residuals. The hypothesis: temperature scales the raw confidence globally; a second pass could correct the per-bin systematic offsets. This is a code change but a small one (edit the calibration step in the walk-forward loop to call `calibrate_multiclass` twice). May move cal_err from 0.1130 toward < 0.05 without regressing Brier.
- **Per-class calibration method mixing.** Temperature for home/away, beta for draw. Draw is consistently the hardest class (Brier ~0.194) and may benefit from beta's asymmetric shape. The current `calibrate_multiclass` applies one method to all three classes simultaneously; adding a `--calibration-draw` flag for a separate draw calibrator is a targeted extension.
- **Calibration oracle study.** Sample-weight the cal fold toward recent matches (e.g., exponential decay within the ~500-match cal fold) before fitting temperature T. This might produce a T that better reflects the current season's confidence regime, rather than a T averaged over all cal-fold seasons. One-line change in `calibrate_multiclass` — fits within calibration tuner scope.
- **Beta Brier note.** Beta at 0.6377 is the lowest Brier achieved so far (vs 0.6381 temperature), despite worse calibration. This hints that beta's probability shapes may be a better match for the data-generating process even if decile calibration error is higher. Worth revisiting after REGRESS / weight_hl tuning — if those reduce the systematic mismatch, beta may then also improve cal_err.

## Future subagent deployment

- **Two-stage calibration agent.** Extends the calibration-tuner scope: after applying the primary calibration method (temperature), fits a second-pass corrector (isotonic) on the residual calibration error of the stacked ensemble. This is a one-method-at-a-time code change that stays within the calibration tuner's file scope.

### Iteration 4 additions (architecture: XGB-only / dynamic ensemble — both DROP)

## Future feature/model exploration

- **Betting-aware XGB loss (top architecture priority for Iteration 8).** The `betting_logloss()` function in `models/gradient_boost.py` weights XGB training by `1/decimal_odds`. This was not tested in Iteration 4 and is the last major architectural question. Implement by porting the custom objective to the inline XGB training block in the A/B loop in `eval_baseline.py`. Key question: are odds data available per-match via ASA or a secondary source?
- **Shorter XGB weight_hl to downweight historical data for 2024 test.** The current weight_hl=4 gives seasons 4 years ago about 50% of the weight of the current season. For the 2024 test fold, seasons 2017-2019 may be harmful noise. Test weight_hl=2 or even weight_hl=1 (only last 1-2 seasons matter) — this is a hyperparameter change but directly addresses the 2024 weakness. Should be Iteration 6 first experiment.
- **Longer DC decay (180d or 240d) to smooth DC inter-season volatility.** In Iteration 4, DC won the 2023 cal fold (raw) but failed catastrophically on 2024 test. Longer decay (less recency bias) may produce more stable DC probs across years. Combine with weight_hl sweep.
- **Capped ensemble mixing weight.** Instead of an unconstrained LogisticRegression meta-learner, fit a constrained meta-learner where DC weight ∈ [0, 0.3] — keeps DC's structural information but prevents DC from dominating in any season. This limits the downside when DC is systematically wrong.
- **Test seasons 2022-2024 leave-one-out to understand DC seasonality.** The DC failures are season-specific (2024 worst). A diagnostic run that evaluates DC alone, XGB alone, and stacked for each season separately — and logs which seasons see DC regression vs improvement — would inform whether DC's bad 2024 is a one-off or a trend.

## Future subagent deployment

- **Distribution-shift detector.** A lightweight diagnostic agent that, for each test season, computes Jensen-Shannon divergence between the training-year and test-year feature distributions. High divergence (particularly for DC λ/μ features) would flag years where DC structural mismatch is likely — and could activate XGB-only mode for those seasons without relying on the unreliable cal-fold signal.
- **Constrained ensemble agent.** Extends the model-architect scope to test bounded meta-learner weights (DC contribution capped at 30%), which may retain DC's synergy while limiting its catastrophic 2024 failure mode.

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

### Parallel /improve-model cycle additions (2026-05-30)

> The "Post-stack calibration layer" idea above was **implemented and KEPT** this cycle —
> 2-stage post-stack Platt is now the default (cal_err 0.1130 → ~0.0917–0.1015).

## Future feature/model exploration

- **~~Historical close-odds column / betting-aware loss~~ — REMOVED from the model backlog (2026-05-30).**
  Category error: the prediction model should optimise probability accuracy (Brier) only. Odds belong in the
  *downstream betting layer* (`market/clv_tracker.py`, `market/kelly.py`), which compares model probabilities to
  the market at bet time. Baking market odds into training (even as a loss weight) teaches the model to agree with
  the market — the opposite of finding edge. The `betting_logloss` experiment already hurt Brier; do not revisit.
  Odds are needed only for **evaluation** (ROI/CLV backtest), a separate workstream that can use *live forward* odds
  on the free tier — **no paid historical backfill required**, and not a `/improve-model` concern.
- **Crack the 2024 distribution shift (the real free next step).** Confirmed across 3 experiments: DC catastrophic in 2024, great in 2022;
  +PythagLuck/+TZShift help 2022-23 but go neutral in 2024; weight_hl=2 does NOT fix it → genuine league-level
  shift, not stale data. Try a regime/era indicator feature or a 2024-specific recalibration.
- **Seed-lock cal_err.** 2-stage Platt shows ~0.01 XGB-seed variance in cal_err. Make `--seed` standard so
  calibration deltas use a fixed XGB realization.
- **Resolved:** REGRESS=0.40 is definitively worse than 0.50 (2024 regresses). Isotonic post-stack overfits
  (cal_err 0.242) — do not revisit. Path to <0.05 must come from raw-model changes, not calibration method.

## Future subagent deployment

- **data-integrator agent** — owns new *model-relevant* free data sources (the unevaluated Transfermarkt squad-value path; ASA/worldfootballR). NOT odds — odds are an eval/betting-layer concern, not a model feature.
- **drift/regime agent** — owns the 2024 distribution-shift investigation (era indicators, per-season recalibration). The highest-value FREE modeling lever now that knob-tuning has plateaued.
- **betting/CLV agent (separate workstream, not /improve-model)** — if/when live betting starts, owns edge detection + Kelly + CLV tracking using *live forward* odds (free tier). Historical-odds backtest is paid and optional.
- **Process:** the parallel 4-worktree cycle compressed 5 hourly cloud iterations into one pass — prefer it; consider
  a cloud orchestrator that fans out to 4 sub-sessions rather than rotating one component per hour.
