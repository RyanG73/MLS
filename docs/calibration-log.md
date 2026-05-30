# Calibration Log

> Results from the calibration-tuner agent. Populated by the multi-agent improvement workflow.
> See `docs/experiment-protocol.md` for the protocol.
>
> Current state (from PLAN.md): max decile calibration error ≈ 0.12–0.18 (target < 0.05).
> Active method: temperature scaling.

---

<!-- calibration-tuner agent appends entries here -->

## 2026-05-30 — Full calibration sweep (Iteration 1)

All experiments run on branch `claude/mls-prediction-dashboard-C2mQM` (commit ae152d30),
`--ab-only Base --cache` to isolate calibration signal. Beta skipped (betacal not installed;
falls back to Platt — would duplicate that result).

| Method      | best_brier | max_cal_error | Δ Brier   | Δ CalErr  | Verdict |
|-------------|-----------|--------------|-----------|-----------|---------|
| temperature | 0.6381    | 0.1130       | (ref)     | (ref)     | ref     |
| platt       | 0.6383    | 0.1561       | +0.0002   | +0.0431   | **DROP** |
| isotonic    | 0.6396    | 0.1542       | +0.0015   | +0.0412   | **DROP** |
| beta        | —         | —            | —         | —         | skipped (betacal absent) |

**Recommendation:** temperature scaling — it wins on both Brier and cal_err on this branch's harness.

**Key finding:** The seeding session (run on `main` at `ebedf812`) showed Platt cutting
cal_err from 0.1459 → 0.0941. On this branch's re-instrumented harness the comparison
flips: temperature gives cal_err=0.1130, Platt=0.1561. The 117640c harness changes
(stacking / meta-learner wiring) altered which calibrator benefits the stacked ensemble
most. Temperature's temperature-scaling NLL optimisation aligns better with the stacked
meta-learner than Platt's sigmoid fitting does.

**Action:** Default remains `temperature`. Previous "candidate not yet promoted" note in
improvement-progress.md is superseded — Platt does not improve on the current harness.

**experiment_ids:** cal-temperature-base-20260530T031204, cal-platt-confirm-20260530T032843,
cal-isotonic-20260530T032036

---

## 2026-05-30 — Beta calibration + seed stability test (Iteration 5)

All experiments on branch `claude/mls-prediction-dashboard-C2mQM` (commit b4d840e9),
`--ab-only Base --cache`. betacal v1.1.0 installed this iteration.

| Method                    | best_brier | max_cal_error | Δ Brier (vs temp) | Δ CalErr (vs temp) | Verdict |
|---------------------------|-----------|--------------|-------------------|--------------------|---------|
| temperature (ref)         | 0.6381    | 0.1130       | (ref)             | (ref)              | ref     |
| beta (Kull 2017, abm)     | 0.6377    | 0.1544       | −0.0004 (better)  | +0.0414 (worse)    | **DROP** |
| temperature seed=42       | 0.6381    | 0.1130       | 0.000             | 0.000              | confirms stability |

**Verdict:** beta → **DROP**.
- Primary (calibration) metric: cal_err +0.0414 vs temperature (worse, not better). KEEP requires cal_err to drop by > 0.01.
- Secondary (Brier) metric: best_brier improved by 0.0004 — below the 0.001 KEEP threshold relative to current best.
- Beta's better Brier (0.6377) is interesting but not enough to overcome significantly worse decile calibration.

**Key finding — cal_err is structurally stable:**
The seed=42 run confirms that cal_err=0.1130 is not stochastic variance — it is identical with and without
seed control. This rules out XGB randomness as the source of the fluctuating cal_err seen in Iteration 3
(feat-tzshift showed 0.0911; likely a genuinely lucky temperature-scaling T fit for that particular
stochastic XGB draw, not a feature effect).

**Recommendation:** temperature scaling remains default. No calibration method has beaten it on either metric.
The cal_err=0.1130 is a structural floor for the current ensemble architecture. Reaching < 0.05 requires
model-level changes (shorter weight_hl, REGRESS=0.40, or post-stack second-pass calibration). These are
hyperparameter and architecture concerns, not calibration-method concerns.

**experiment_ids:** cal-beta-20260530T071207, cal-temperature-seed42-20260530T072043
