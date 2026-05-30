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
