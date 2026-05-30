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
| best_brier | **0.6392** | baseline `ebedf812` (temperature cal, Base features) |
| max_cal_error | **0.1459** | baseline |
| naive_brier | 0.6406 | reference |
| harness defaults | ELO K=25 HA=80 REGRESS=0.50, DC hl=120, weight_hl=4, calibration=temperature | scripts/eval_baseline.py |

**Candidate not yet promoted:** Platt calibration (`--calibration platt`) measured in the
seeding session gave best_brier=0.6384 (Δ +0.0007, marginal on Brier) but cut
max_cal_error 0.1459 → **0.0941** with no Brier regression. Calibration iterations
should confirm this and try isotonic/beta to chase the < 0.05 target before deciding
whether to switch the harness default from temperature to Platt.

---

## Iteration 0 — seeding (pre-loop, 2026-05-30) — local session

- Built the multi-agent workflow + instrumented harness (commit `117640c`).
- Recorded baseline (`experiment.py baseline`): best_brier=0.6392, cal_err=0.1459.
- Ran one calibration probe (`cal-platt`): best_brier=0.6384, cal_err=0.0941 → see "Best so far".
- No harness default changed yet — left for the calibration iteration to confirm + decide.

<!-- cloud iterations 1–8 append below -->
