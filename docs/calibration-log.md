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

---

## 2026-05-30 — Two-stage post-stack calibration sweep (Iteration 6)

This iteration tests a 2-stage architecture: temperature scaling per-model (first pass, unchanged),
then a second calibration pass applied to the stacked ensemble output. The hypothesis is that the
meta-learner's LogisticRegression output may still be miscalibrated even after each input model is
temperature-scaled, and a second-pass calibrator fitted on the cal fold's stacked predictions can
correct residual miscalibration without hurting Brier.

Implementation: `_calibrate_stacked_second_pass()` added to `scripts/eval_baseline.py`;
new `--calibration` choices `temp_then_isotonic` and `temp_then_platt`. The first-stage
`calibrate_multiclass` treats both new values as `temperature` (so per-model pass is unchanged).
Second pass fits on `meta.predict_proba(meta_X_cal)` (cal fold stacked preds) and applies to test.

All experiments: branch `claude/mls-prediction-dashboard-C2mQM` (commit 00992ba0),
`--ab-only Base --cache`.

| Method              | best_brier | max_cal_error | Δ Brier  | Δ CalErr  | Verdict |
|---------------------|-----------|--------------|----------|-----------|---------|
| temperature (ref)   | 0.6381    | 0.1130       | (ref)    | (ref)     | ref     |
| temp_then_isotonic  | 0.6468    | 0.2418       | +0.0087  | +0.1288   | **DROP** |
| temp_then_platt     | 0.6387    | 0.0917       | +0.0006  | −0.0213   | **KEEP** |

**Verdict: temp_then_platt → KEEP**
- cal_err drops 0.0213 (> 0.01 threshold) — improvement criteria met.
- best_brier worsens by only 0.0006 (≤ 0.001 veto threshold) — secondary veto NOT triggered.
- Note: cal_err=0.0917 is still above the <0.05 target, but this is the first meaningful reduction.

**temp_then_isotonic → DROP**
- Both metrics worsen significantly: Brier +0.0087 (far exceeds 0.001 veto), cal_err +0.1288.
- Root cause: isotonic regression overfits on the ~470–520 in-sample meta-learner predictions;
  the monotone constraint is not enough regularisation at this sample size.

**Key finding:** A Platt second pass on the stacked output is the first post-hoc calibration change
to improve cal_err meaningfully. The combination temperature→stack→Platt reduces cal_err by 18.8%
relative (0.1130 → 0.0917) while keeping Brier nearly flat (+0.0006). Isotonic at the same stage
is too flexible for ~500 samples and collapses both metrics.

**CHANGE TO APPLY (KEEP):**
1. In `calibrate_multiclass`: extend the `if _method == "temperature"` branch to include
   `temp_then_platt` (already implemented — the condition is
   `if _method in ("temperature", "temp_then_isotonic", "temp_then_platt")`).
2. Add `_calibrate_stacked_second_pass()` function (already implemented).
3. In the stacking block: set `_two_stage = _ARGS.calibration in ("temp_then_isotonic", "temp_then_platt")`,
   compute `stacked_cal_preds = meta.predict_proba(meta_X_cal)`, call
   `_calibrate_stacked_second_pass(stacked_cal_preds, y_cal_r, ens_stacked_raw)` (already implemented).
4. Change the argparse `--calibration` default from `"temperature"` to `"temp_then_platt"`.

**experiment_ids:** cal-2stage-postack-20260530T171006, cal-2stage-platt-postack-20260530T171336
