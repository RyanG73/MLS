# Model Improvement Loop — Running Log

> Autonomous 8-iteration improvement loop driven by the cloud routine
> "MLS model improvement loop (8h)" (`trig_01APrQeuzmV8KjCn8jNvES9y`), one
> iteration per hour. Each cloud run is a fresh checkout — this file IS the
> loop's memory. See `docs/experiment-protocol.md` for the KEEP/DROP contract.
>
> Component rotation by iteration N:
>   1,5 → calibration · 2,6 → hyperparameters · 3,7 → feature · 4,8 → architecture

---

## Best so far

| Field | Value | Source |
|-------|-------|--------|
| best_brier | **0.6385** | merge-confirm-cal2stage (parallel cycle, Base features) |
| max_cal_error | **0.0917–0.1015** | cal-2stage-platt-postack (0.0917 isolated; 0.1015 on re-eval — XGB-seed variance) |
| naive_brier | 0.6406 | reference |
| harness defaults | ELO K=25 HA=80 REGRESS=0.50, DC hl=120, weight_hl=4, **calibration=temp_then_platt** | scripts/eval_baseline.py |

**Status (after parallel /improve-model cycle, 2026-05-30):** New default calibration is **2-stage post-stack Platt** (`temp_then_platt`): per-model temperature scaling, then a Platt re-scaling of the *stacked ensemble* output. This cut max decile cal error from 0.1130 → ~0.0917–0.1015 (the meta-learner introduces systematic miscalibration a light Platt pass corrects), at a negligible Brier cost (+0.0004, within the 0.001 veto). Still above the <0.05 target — that gap is now believed to be a raw-model limit, not a calibration-method choice.

**Resolved this cycle:** REGRESS=0.40 is definitively worse than 0.50 (2024 regresses +0.0007; the earlier partial run was misleading) → **CLAUDE.md's documented "40%" was wrong, corrected to 50%**. weight_hl=2 regresses all 3 seasons → 2024 weakness is NOT stale-data contamination (likely genuine distribution shift). Betting-aware loss is blocked without a real historical odds column (the 1/max_prob proxy just upweights draws). +PythagLuck marginal (Δ+0.0008), registered but not promoted.

---

## Parallel /improve-model cycle — 2026-05-30 — 4 agents in worktrees

Dispatched all four component agents in parallel git worktrees against the frozen ASA cache. Greedy forward-merge applied (feature → calibration); hyperparameter & architecture made no code change.

| Agent | Experiment | best_brier | cal_err | Verdict |
|-------|-----------|-----------|---------|---------|
| calibration | cal-2stage-platt-postack | 0.6387 | 0.0917 | **KEEP** (new default) |
| feature | feat-pythagluck | 0.6385 | 0.1152 | marginal (Δ+0.0008; registered, not promoted) |
| hyperparameters | hyp-regress040 / hyp-whl2 | 0.6384 / 0.6387 | 0.151 / 0.122 | DROP both |
| architecture | arch-betting-loss | 0.6385 | 0.1015 | DROP (no odds column) |
| **post-merge** | merge-confirm-cal2stage | **0.6385** | **0.1015** | cumulative |

- **KEPT:** 2-stage post-stack Platt calibration as the new harness default (`--calibration temp_then_platt`).
- **Net model change:** best_brier 0.6381 → 0.6385 (+0.0004, within veto); cal_err 0.1130 → ~0.0917–0.1015 (materially better, the cycle's real win).
- **Caveat:** cal_err shows ~0.01 XGB-seed variance with the 2-stage method; the improvement direction is robust (both samples < 0.1130) but the exact magnitude is noisy. A seed-locked confirmation is the recommended follow-up.

## Iteration 0 — seeding (pre-loop, 2026-05-30) — local session

- Built the multi-agent workflow + instrumented harness (commit `117640c`).
- Recorded baseline (`experiment.py baseline`): best_brier=0.6392, cal_err=0.1459.
- Ran one calibration probe (`cal-platt`): best_brier=0.6384, cal_err=0.0941 → see "Best so far".
- No harness default changed yet — left for the calibration iteration to confirm + decide.

<!-- cloud iterations 1–8 append below -->

## Iteration 5 — calibration — 2026-05-30T07:20 UTC

- **Experiments run:** (all `--ab-only Base --cache`)
  - `cal-beta` (cal-beta-20260530T071207): best_brier=0.6377, cal_err=0.1544; Δ Brier=−0.0004 (better), Δ CalErr=+0.0414 (worse)
  - `cal-temperature-seed42` (cal-temperature-seed42-20260530T072043): best_brier=0.6381, cal_err=0.1130; identical to unseeded temperature
- **Verdict(s):**
  - cal-beta → **DROP** (primary cal metric regressed +0.0414; KEEP requires cal_err to drop > 0.01; Brier improvement only 0.0004 relative to current best — below 0.001 threshold)
  - cal-temperature-seed42 → **reference** (confirms temperature is stable, not stochastic)
- **Best so far:** UNCHANGED — temperature cal, DC decay=120d, Base features → best_brier=0.6381, cal_err=0.1130
- **Notes:**
  - Beta calibration (Kull 2017, "abm" parameters) produces the **best Brier seen so far** (0.6377 vs 0.6381), but at the cost of much worse decile calibration error. Brier improvement is marginal (0.0004 relative to temperature). By the calibration agent's primary metric protocol, this is a DROP.
  - **Structural finding:** The seed=42 locked temperature run produced *identical* results (best_brier=0.6381, cal_err=0.1130). This confirms that cal_err=0.1130 is a *structural floor* for the current model, not stochastic noise from XGB random seeds. The ~0.02 cal_err variance seen in Iteration 3 (feat-tzshift cal_err=0.0911) was likely a one-off lucky temperature-scaling fit for that particular stochastic XGB realization.
  - **Second full calibration sweep complete.** All four methods have now been tested: temperature, platt, isotonic (Iteration 1), beta (this iteration). Temperature wins on both metrics. No calibration method reaches the < 0.05 target.
  - **Path to < 0.05 cal_err:** Must come from model improvements (better-calibrated raw probabilities), not from post-hoc calibration method choice. REGRESS=0.40 (Iteration 6) and weight_hl=2 are the next candidates. Alternatively, a 2-stage post-stack calibration layer (temperature → second pass isotonic on the stacked output) is unexplored.
  - Highest-priority remaining experiments: (1) REGRESS=0.40 + weight_hl=2 sweep (Iteration 6), (2) +PythagLuck feature (Iteration 7), (3) betting-aware loss (Iteration 8).

## Iteration 4 — architecture — 2026-05-30T06:25 UTC

- **Experiments run:** (all `--ab-only Base --cache`)
  - `arch-xgb-only` (arch-xgb-only-20260530T061344): best_brier=0.6381, cal_err=0.1130; Δ=0.000 vs current best
  - `arch-dynamic-ensemble` (arch-dynamic-ensemble-20260530T062523): best_brier=0.6381, ens_dynamic=0.6397, cal_err=0.1130; dynamic worse than stacked by 0.0016
- **Verdict(s):**
  - arch-xgb-only → **DROP** (Δ=0.000; reporting change only — stacked is still best on average)
  - arch-dynamic-ensemble → **DROP** (dynamic is anti-predictive; cal-fold signal misleads for both 2023 and 2024)
- **Best so far:** UNCHANGED — temperature cal, DC decay=120d, Base features → best_brier=0.6381, cal_err=0.1130
- **Per-season insight (first per-season XGB vs stacked breakdown):**
  - 2022: XGB=0.6398, stacked=0.6296 → stacked +0.010 (DC adds major value)
  - 2023: XGB=0.6386, stacked=0.6338 → stacked +0.005 (DC still helpful)
  - 2024: XGB=0.6376, stacked=0.6511 → XGB +0.013 (DC catastrophically bad)
  - Stacked wins 2022-2023 by enough to offset 2024 loss on the 3-year average
- **Notes:**
  - DC's 2024 failure is structural (Poisson model mis-parameterized for 2024 team dynamics), NOT detectable from the 2023 calibration fold's raw Brier — DC actually wins the 2023 cal fold raw comparison.
  - Dynamic model selection via cal-fold signal is ANTI-predictive in this dataset: correct for 2022 (STK chosen, STK is right), wrong for 2023 (XGB chosen, STK was better), wrong for 2024 (STK chosen, XGB was right).
  - The highest-value remaining architecture questions are: (1) betting-aware loss for XGB (Iteration 8), (2) shorter XGB weight_hl to downweight 2017-2019 data for 2024 test — may help both XGB alone AND the stacked ensemble in 2024. This is a hyperparameter, not architecture.
  - `eval_baseline.py` reverted to HEAD state (no architecture changes adopted).

## Iteration 3 — feature (+TZShift) — 2026-05-30T05:11 UTC

- **Experiments run:** (all `--ab-only Base,+TZShift --cache`)
  - `feat-tzshift` (feat-tzshift-20260530T051118): Base=0.6386, +TZShift=0.6379, Δ=+0.0008; best_brier=0.6382 (stacked ens), cal_err=0.0911
- **Verdict(s):**
  - +TZShift → **marginal** (Δ=+0.0008 < 0.001 KEEP threshold; XGB AB comparison Base→+TZShift)
  - AB set kept registered in `AB_SETS` but NOT promoted to `_FEAT_BASE`
- **Best so far:** UNCHANGED — temperature cal, DC decay=120d, Base features → best_brier=0.6381, cal_err=0.1130
  - Note: feat-tzshift stacked ensemble cal_err=0.0911 is notably better, but Brier (0.6382) is not improved enough to constitute a KEEP.
- **Notes:**
  - TZ-shift mean=0.88 zones, max=3 zones across test set.
  - Per-season breakdown: BestAB=Base in 2022 and 2024; BestAB=+TZShift in 2023 only. Inconsistent cross-season benefit.
  - The signed variant (`away_tz_shift_signed`) lets XGBoost discover eastward vs westward asymmetry, but feature importance was not individually broken out.
  - The good cal_err (0.0911 vs current best 0.1130) may reflect run-to-run variability rather than a genuine improvement from the TZ feature — stochastic XGB fitting and temperature-scaling on ~500 cal matches can vary by ~0.02.
  - Next feature candidate: `+PythagLuck` (rolling Pythagorean over-performance luck residual) — higher novelty, stronger theoretical basis for regression-to-mean signal.

## Iteration 2 — hyperparameters — 2026-05-30T04:46 UTC

- **Experiments run:** (all `--ab-only Base --cache`)
  - `hyp-dc-hl090`: best_brier=0.6381, cal_err=0.1440
  - `hyp-regress-040`: **INCOMPLETE** — process accidentally killed via SIGUSR1 sent during DC fit debugging; 2024 season not captured. Partial: 2022≈0.6293, 2023≈0.6330.
- **Verdict(s):**
  - dc-hl090 → **DROP** (Δ Brier +0.000014 negligible, Δ CalErr +0.031 significant regression; DC decay=90d amplifies DC drag)
  - regress-040 → **INCOMPLETE** (cannot assess; re-run needed in Iteration 6)
- **Best so far:** UNCHANGED — temperature + DC decay=120d → best_brier=0.6381, cal_err=0.1130
- **Notes:**
  - **XGB-beats-stacked for 2024 confirmed:** in both hyp-dc-hl090 and (partially) regress-040, for 2024 the stacked ensemble scored ~0.6509 while XGB alone scored ~0.6376 — a 0.013 Brier gap. DC drag is real and worsens with shorter decay half-life.
  - **Execution bottleneck:** Running both experiments in parallel on this 4-core system caused severe CPU contention. Each process spawned 16 XGB threads (32 total on 4 cores), slowing season evaluation from ~3 min to 30-45 min each. Future iterations MUST run experiments sequentially.
  - **REGRESS discrepancy unresolved:** CLAUDE.md documents REGRESS=40% but code defaults to 50%. Partial data for 2022/2023 favors 40%. This is the highest-priority sweep for Iteration 6 (next hyperparameter iteration).

## Iteration 1 — calibration — 2026-05-30T03:45 UTC

- **Experiments run:** (all `--ab-only Base --cache` on branch ae152d30)
  - `cal-temperature-base`: best_brier=0.6381, cal_err=0.1130
  - `cal-platt-confirm`: best_brier=0.6383, cal_err=0.1561
  - `cal-isotonic`: best_brier=0.6396, cal_err=0.1542
  - beta: skipped (betacal not installed; would duplicate Platt)
- **Verdict(s):**
  - temperature → reference (best on both metrics)
  - Platt → **DROP** (Δ Brier +0.0002, Δ CalErr +0.043 — worse, not better)
  - isotonic → **DROP** (Δ Brier +0.0015 > threshold, Δ CalErr +0.041)
- **Best so far:** temperature default → best_brier=0.6381, cal_err=0.1130
- **Notes:** The seeding session (main@ebedf812) showed Platt cutting cal_err 0.1459→0.0941.
  On this branch's re-instrumented harness the relationship inverts: temperature gives cal_err=0.1130,
  Platt=0.1561. The 117640c harness changes to stacking/meta-learner make temperature's NLL
  optimisation align better with the stacked ensemble than Platt's sigmoid fitting.
  Cal_err=0.1130 is improved vs old baseline (0.1459) but still far from the <0.05 target —
  next best path is via hyperparameter tuning or architecture changes, not calibration method.
