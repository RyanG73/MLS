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
