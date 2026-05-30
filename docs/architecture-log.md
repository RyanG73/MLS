# Model Architecture Log

> Results from the model-architect agent. Populated by the multi-agent improvement workflow.
> See `docs/experiment-protocol.md` for the protocol.
>
> Open questions (from PLAN.md):
>   - DC drag: stacked ensemble (0.6437) worse than XGB alone (0.6387)
>     → consider XGB-only ensemble (removing DC probs from the meta-learner)
>   - DC as feature only: dc_lam/dc_mu already in +DCParams set (Δ=+0.0002, marginal)
>   - Meta-learner: LogisticRegression over [DC_probs, XGB_probs] — worth testing simple average
>   - Betting-aware loss: betting_logloss() in models/gradient_boost.py — not yet tested in harness

---

<!-- model-architect agent appends entries here -->

## 2026-05-30 — True-minimum best_key selection (arch-xgb-only)
**Hypothesis:** The harness always reports `ens_stacked_brier` as `best_brier` even if XGB alone scores lower. Changing `best_key` selection to `argmin` across all models should reveal the true best.
**Result:** Δ=0.000 → **DROP**
**experiment_id:** arch-xgb-only-20260530T061344
**Per-season breakdown:**
| Season | XGB cal | Stacked | Winner |
|--------|---------|---------|--------|
| 2022   | 0.6398  | 0.6296  | Stacked +0.010 |
| 2023   | 0.6386  | 0.6338  | Stacked +0.005 |
| 2024   | 0.6376  | 0.6511  | XGB +0.013 |
| **avg**| **0.6387** | **0.6381** | Stacked wins on average |
**Notes:** XGB dominates 2024 by 0.013 Brier, but stacked wins 2022 (+0.010) and 2023 (+0.005). The average favours stacked (0.6381 vs 0.6387). Changing the reporting function to argmin made no difference because stacked is still the global best-average model. DC drag in 2024 is confirmed but does not overcome DC's synergy value for 2022-2023.

## 2026-05-30 — Betting-aware XGB loss (arch-betting-loss)
**Hypothesis:** Weighting training samples by 1/max_prob (inverse model confidence — a proxy for 1/decimal_odds since no odds column exists in the harness) will penalise being wrong on uncertain matches more than on confident ones, better aligning training with betting profit objectives. Expected: modest Brier improvement on matches where the model is least confident.
**Result:** xgb_bet_brier=0.6403 vs xgb_brier_cal=0.6387 (avg) — betting-loss XGB is WORSE on average. best_brier=0.6385 (still stacked), Δ=+0.0007 vs baseline → **DROP** (marginal improvement is entirely from stacked, not from betting-loss)
**experiment_id:** arch-betting-loss-20260530T171119
**Per-season breakdown:**
| Season | XGB cal | XGB bet-loss | Stacked | Bet-loss vs XGB-cal |
|--------|---------|--------------|---------|---------------------|
| 2022   | 0.6390  | 0.6434       | 0.6297  | −0.0044 (worse)     |
| 2023   | 0.6388  | 0.6418       | 0.6340  | −0.0030 (worse)     |
| 2024   | 0.6381  | 0.6357       | 0.6518  | +0.0024 (better)    |
| avg    | 0.6387  | 0.6403       | 0.6385  | −0.0016 (worse)     |
**Notes:** Inverse-confidence weighting helps only in 2024 (the season where DC drags the ensemble). In 2022 and 2023 it hurts significantly. Pattern: the proxy weight amplifies noise rather than signal in earlier seasons where XGB is already well-calibrated. The fundamental limitation is that 1/max_prob is NOT a good proxy for 1/decimal_odds — it is highest for draws (model always uncertain about draws) and lowest for decisive matches, which is not how bookmaker odds distribute. Real odds weight long-shot outcomes (rare results at high odds), not just model-uncertain predictions. A true test would require actual odds columns. Reverted.

## 2026-05-30 — Dynamic per-season ensemble selection (arch-dynamic-ensemble)
**Hypothesis:** Use raw (uncalibrated) DC vs XGB Brier on the calibration fold as a signal to pick which model to use for the test fold: if XGB beats DC on the cal fold, use XGB alone; else use stacked. Should avoid DC drag in 2024 while preserving the stacking benefit for 2022-2023.
**Result:** ens_dynamic=0.6397, Δ=−0.0016 vs stacked 0.6381 → **DROP** (dynamic is WORSE)
**experiment_id:** arch-dynamic-ensemble-20260530T062523
**Per-season dynamic choices:**
| Season | Cal fold | DC vs XGB raw | DYN selection | Dynamic Brier | Stacked |
|--------|----------|---------------|---------------|---------------|---------|
| 2022   | 2021 cal | DC wins cal   | STK           | 0.6296        | 0.6296 |
| 2023   | 2022 cal | XGB wins cal  | XGB           | 0.6386        | 0.6338 (cost: +0.005) |
| 2024   | 2023 cal | DC wins cal   | STK           | 0.6511        | 0.6511 (cost: +0.013) |
**Notes:** The raw cal-fold Brier is NOT a reliable predictor of test-fold model quality. In 2023, XGB won the cal fold (2022 data), but stacked was better on 2023 test (+0.005 cost from wrong choice). In 2024, DC won the cal fold (2023 data), but XGB was far better on 2024 test (+0.013 cost from wrong choice). The dynamic selection was ANTI-predictive. DC's failures are structural (Poisson model misfit for different team dynamics in certain seasons) and manifest between years, not within the prior calibration year. The cal-fold signal cannot detect inter-year distribution shift.
## 2026-05-30 — Constrained convex blend with DC weight cap (arch-capped-dc)
**Hypothesis:** Replacing the unconstrained LogisticRegression meta-learner with a scalar convex blend w*XGB + (1-w)*DC (w fitted on cal fold, constrained w >= 0.7) will limit DC's contribution to at most 30%, eliminating the 2024 catastrophe while retaining DC's 2022-23 synergy.
**Result:** best_brier=0.6372 vs baseline 0.6392, Δ=−0.0019 → **KEEP** (exceeds 0.001 threshold)
**experiment_id:** arch-capped-dc-20260530T173659
**Per-season breakdown:**
| Season | Baseline stacked | Capped blend | Fitted w_xgb | Delta |
|--------|-----------------|-------------|-------------|-------|
| 2022   | 0.6314          | 0.6359      | 0.70 (at bound) | +0.0045 (worse) |
| 2023   | 0.6338          | 0.6380      | 0.76        | +0.0042 (worse) |
| 2024   | 0.6523          | 0.6378      | 0.70 (at bound) | -0.0145 (much better) |
| **avg**| **0.6392**      | **0.6372**  | —           | **-0.0019** |
**Notes:** The 2024 catastrophe (DC inflating Brier by +0.013 vs XGB) is fixed: capped blend now matches XGB-alone quality in 2024. Trade-off: 2022 and 2023 regress ~+0.004 each because DC's positive contribution is limited. The net average is still a clear win (-0.0019). The fitted w_xgb hits the lower bound (0.70) in both 2022 and 2024, suggesting the optimizer finds DC helpful only when the constraint allows it (2023: w=0.76 uses 24% DC). Cal error also improves: 0.1411 vs baseline 0.1459. This is the best architecture found to date.

