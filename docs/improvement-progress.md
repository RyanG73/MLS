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
| best_brier | **0.6381** | cal-temperature-base (Iteration 1, branch harness, Base features) |
| max_cal_error | **0.1130** | cal-temperature-base |
| naive_brier | 0.6406 | reference |
| harness defaults | ELO K=25 HA=80 REGRESS=0.50, DC hl=120, weight_hl=4, calibration=temperature | scripts/eval_baseline.py |

**Status:** Temperature scaling confirmed as best calibration method on this branch's harness.
Platt and isotonic both DROP (higher cal_err AND marginal Brier regression vs temperature).
Cal_err still 0.1130 vs target < 0.05 — more improvement needed via hyperparameter/architecture work.

---

## Iteration 0 — seeding (pre-loop, 2026-05-30) — local session

- Built the multi-agent workflow + instrumented harness (commit `117640c`).
- Recorded baseline (`experiment.py baseline`): best_brier=0.6392, cal_err=0.1459.
- Ran one calibration probe (`cal-platt`): best_brier=0.6384, cal_err=0.0941 → see "Best so far".
- No harness default changed yet — left for the calibration iteration to confirm + decide.

<!-- cloud iterations 1–8 append below -->

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
