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
| best_brier | **0.6344** | p11-base-avail-confirm (availability promoted to Base, seed=42) |
| max_cal_error | **0.1314** | same run |
| naive_brier | 0.6406 | reference (**~+0.97% over naive**, up from +0.67%) |
| harness defaults | ELO K=25 HA=80 REGRESS=0.50, DC hl=120, weight_hl=6, calibration=temperature, capped-DC blend, **+ availability (ESPN roster g+ share) in Base** | scripts/eval_baseline.py |

### Phase 11 loop — Iteration 1 (2026-05-31): roster availability KEEP
Backfilled ESPN rosters to full 2017-2024 history (3,227 matches). FAIR roster A/B (full training history):
`+Availability` Δ=**+0.0011 → KEEP** (g+ availability share, expanding-mean normalized); `+SalaryRoster` Δ=−0.0006 DROP; `+RosterState` (g++salary) Δ=−0.0006 DROP. Salary-share is noisier than the normalized g+ share. **Promoted +Availability to Base → best_brier 0.6363→0.6344 (+0.97% over naive).** Validates the lineup hypothesis once given training history (the prior DROP was a 3-season-history confound). Goal 0.6086 still distant; +4% to go.

> **Calibration note (corrected cycle #3):** the committed `--calibration` default has always been `temperature`; the `temp_then_platt` 2-stage option exists but is a **no-op on the capped-DC blend** (it calibrated the old LR meta-learner). Earlier docs that listed `temp_then_platt` as the default and `cal_err≈0.1015` were referencing the pre-capped-DC LR-meta architecture and are obsolete. Current calibration = `temperature`, cal_err = 0.1326.

**Status (after 2nd parallel /improve-model cycle, 2026-05-30):** Two compounding KEEPs.
(1) **Capped-DC convex blend** replaces the unconstrained LogisticRegression meta-learner: fit scalar w on the cal fold (w ∈ [0.7,1.0]) so Dixon-Coles contributes ≤30%. This fixes the 2024 catastrophe (DC stacked 0.6523 → 0.6378) at small 2022/2023 cost; net best_brier 0.6388 → 0.6372.
(2) **weight_hl 4 → 6**: a DROP in isolation last cycle ("swallowed by DC drag"), but with the drag now capped it became a KEEP — best_brier 0.6372 → **0.6363**. The greedy re-eval-after-merge surfaced this second-order interaction.
Calibration regressed (0.1015 → 0.1326): the temp_then_platt second-pass corrected the *LR meta* output but is a no-op on the *blended* output. Brier is the stated primary target (PLAN.md), so the trade was accepted; recovering calibration on the blend is a top open item.

**Also this cycle (all DROP):** +MinutesHHI hurt all seasons (exhausts the should-implement queue); larger calibration fold (pool 2 seasons) defeated by COVID gap; longer DC decay (150/180) slightly worse. **Crash fix:** XGBoost now thread-capped (`n_jobs=2`, env `EVAL_XGB_NJOBS`) after 4 parallel all-cores evals OOM-crashed the 16 GB machine.

---

## /improve-model cycle #3 — 2026-05-30 — local-sequential (no KEEP; plateau)

Run local-sequential (post-crash-fix default), one eval at a time, `EVAL_XGB_NJOBS=2`, `--seed 42 --ab-only Base`.

| Experiment | best_brier | cal_err | Verdict |
|-----------|-----------|---------|---------|
| c3-whl8 (weight_hl=8 on capped-DC) | 0.6359 | 0.1723 | marginal Brier (Δ+0.0004 <0.001), cal much worse → **DROP** (keep whl=6) |
| c3-cal-temp (temperature on blend) | 0.6363 | 0.1326 | identical to temp_then_platt default → 2nd-pass is a **no-op** on the blend |
| c3-cal-iso (temp_then_isotonic on blend) | 0.6409 | 0.1722 | worse both → **DROP** (isotonic overfits) |

**No harness change.** Best remains capped-DC blend + weight_hl=6 + temp_then_platt → **0.6363 / 0.1326**.

**Conclusions:**
- **Plateau reached on the current architecture/feature set.** whl 4→6→8 trades Brier (0.6388→0.6363→0.6359) for calibration (0.1015→0.1326→0.1723) monotonically; whl=6 is the knee. No post-hoc calibrator recovers the blend's cal_err (temperature = temp_then_platt; isotonic worse).
- **Known no-op:** the `temp_then_platt` 2nd-pass (cycle-1 KEEP) was neutralized by the cycle-2 capped-DC blend (which replaced the LR meta-learner it calibrated). Default could be simplified to `temperature` (identical output). Left in place as reversible.
- **Next gains require NEW signal, not knob-tuning:** historical odds column (unblocks betting loss), 2024-regime/distribution-shift features, or a calibrator re-targeted at the blended output. See `docs/future-exploration.md`.

## Parallel /improve-model cycle #2 — 2026-05-30 — structural leads

Targeted the structural problems the prior cycle exposed. Greedy forward-merge: architecture KEEP merged, then weight_hl=6 re-tested on top and also KEPT.

| Agent | Experiment | best_brier | cal_err | Verdict |
|-------|-----------|-----------|---------|---------|
| architecture | arch-capped-dc (DC weight ≤30%) | 0.6372 | 0.1411 | **KEEP** (fixes 2024) |
| hyperparameters | weight_hl=6 *on capped-DC* | **0.6363** | 0.1326 | **KEEP** (unlocked by the arch fix) |
| feature | feat-minuteshhi | 0.6385→worse | — | DROP (hurts all seasons) |
| calibration | cal-pool2 (larger cal fold) | — | 0.1487 | DROP (COVID gap defeats pooling) |
| hyperparameters | dc-hl 150/180, whl 8 | — | — | DROP (longer DC decay slightly worse) |
| **post-merge** | merge-final-confirm | **0.6363** | **0.1326** | cumulative, new default |

- Best Brier across all cycles: **0.6363** (naive 0.6406, ~+0.67% over naive, up from +0.3%).
- Per-season (capped-DC): 2024 fixed (0.6523→0.6378); small 2022/2023 cost; net win.
- Infra: added `--cal-pool-seasons` flag (kept, default 1); XGBoost `n_jobs` cap added (crash fix).

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

### Phase 11 loop — Iteration 2 (2026-05-31): team salary structure DROP
`+TeamSalary` (payroll z-score + DP-concentration std/avg, same-season, full coverage): Δ=−0.0045 → **DROP** (Base-with-avail 0.6351 → 0.6396). Team payroll is strongly redundant with ELO; 6 features add noise. With iter-1's salary-share DROP, talent-investment proxies are confirmed redundant with ELO. Default unchanged at best_brier 0.6344 (+0.97%). experiment_id: p11-teamsalary-20260531T043838

### Phase 11 loop — Iteration 3 (2026-05-31): starter-weighted availability DROP
`+AvailStarters` (g+ share of STARTERS only, on top of active-squad availability already in Base): Δ=−0.0013 → **DROP**. The active-matchday-squad availability already captures the lineup signal; starter-only granularity is redundant + adds 3 noisy features. The availability vein is a single feature (active-squad g+ share), not deepenable. Default unchanged 0.6344. experiment_id: p11-avail-starters-20260531T053820

### Phase 11 loop — Iteration 4 (2026-05-31): GK distribution g+ DROP
`+GKDistribution` (non-shotstopping GK goals-added: Passing+Sweeping+Handling+Claiming, season-lagged z): Δ=−0.0014 → **DROP**. Redundant with the GK shot-stopping quality already in Base; adds noise. Default unchanged 0.6344. experiment_id: p11-gkdist-20260531T063804

### Phase 11 loop — Iteration 5 (2026-05-31): availability×congestion marginal — LOOP COMPLETE
`+AvailCongestion` (avail_share × games_in_14d): Δ=+0.0005 → **marginal** (directionally right — depletion hurts more under congestion — but below 0.001 KEEP bar; registered, not promoted).

**PHASE 11 LOOP COMPLETE (5/5 iterations).** Scoreboard:
| Iter | Experiment | Δ vs Base | Verdict |
|------|-----------|-----------|---------|
| 1 | +Availability (full history) | +0.0011 | **KEEP** → 0.6344 |
| 2 | +TeamSalary | −0.0045 | DROP |
| 3 | +AvailStarters | −0.0013 | DROP |
| 4 | +GKDistribution | −0.0014 | DROP |
| 5 | +AvailCongestion | +0.0005 | marginal |

**Final best_brier 0.6344 (+0.97% over naive), up from 0.6363 (+0.67%) at loop start.** Goal 0.6086 (+5%) NOT reached. The one real new signal was roster **availability** (+0.3%); all talent-investment proxies (salary, payroll) and GK-detail signals were redundant with ELO/xG/GK-quality. This matches the benchmark literature: market-blind MLS 1X2 tops out ~+1-3% over naive (the bookmaker market itself scores ~0.59 in an easier league). +5% is below the market's own Brier and beyond a market-blind model's reach. Cron `a9fd1c3f` deleted.

---

## Overnight loop (2026-06-06) — goal: lower Brier · KEEP threshold loosened to +0.0005

Branch: `claude/mls-prediction-dashboard-C2mQM`. Eval-harness reference: ensemble stacked **0.6381** (naive 0.6406), per-season 2022=0.6382 / 2023=0.6371 / 2024=0.6389. (Note: the production/published `webapp/data.js` figure is 0.6344 from `models/research_model.py`, a separate pipeline — not directly comparable to the research harness.)

### Iteration 1 — ensemble blend-cap sweep — **DROP (within noise)**
Focus: ensemble blend weights. Tested an env-configurable capped-DC convex blend (`MLS_ENS_MODE`/`MLS_DC_CAP`/`MLS_ENS_SWEEP`) over DC caps {0.0, 0.10, 0.20, 0.30, 0.40}.

The branch **already** runs a 30%-cap convex blend (`arch-capped-dc`, KEPT 2026-05-30 — it is the current default, not the LR meta-learner). Re-measured on the **final calibrated ensemble output**, cap=0.20 gives per-season 2022=0.6384 / 2023=0.6371 / 2024=0.6385 → **0.6380**, vs the existing 30%-cap **0.6381** → Δ=**+0.0001**, below the +0.0005 bar → **DROP**. Cap is insensitive between 0.20–0.30; the existing blend is already near-optimal on this axis.

**Methodology correction:** the subagent first reported "+0.0020 KEEP," but that (a) benchmarked cap=0.20 against an `MLS_ENS_MODE=lr` baseline that has not been the branch default since 2026-05-30, and (b) scored **raw blended probabilities** (its in-run sweep accumulator) rather than the calibrated ensemble the harness actually reports. On the real metric the gain evaporates. Change reverted; default unchanged. **Lesson logged:** verify subagent KEEPs against the *current branch default* and the *reported* metric, not a stale baseline or an intermediate quantity.

### Iteration 2 — hyperparameter sweep (REGRESS / DC decay) — **DROP (defaults confirmed robust)**
Focus: hyperparameters. The delegated agent malfunctioned (returned no usable result), so the sweep was run **directly** via the harness CLI for reliability. ELO K/HOME_ADV and the XGB grid are already auto-searched per fold internally, leaving REGRESS and DC-decay-half-life as the open knobs.

| Config | Ensemble | 2022 | 2023 | 2024 | Verdict |
|--------|----------|------|------|------|---------|
| **default** (REGRESS=0.5, decay=120) | **0.6381** | 0.6382 | 0.6371 | **0.6389** | reference |
| REGRESS=0.4 | 0.6382 | 0.6382 | 0.6362 | 0.6400 | DROP (worse, 2024↓) |
| DC decay=90 | 0.6381 | 0.6365 | 0.6371 | 0.6406 | DROP (2024↓) |
| DC decay=150 | 0.6379 | 0.6358 | 0.6371 | 0.6408 | DROP (Δ+0.0002 but 2024↓0.0019) |

No config clears +0.0005, and every one that lowers the average does so by regressing 2024 — failing the robustness gate. DC-decay=150 is textbook distribution shift: longer memory helps stable seasons (2022 −0.0024) but hurts the shift season (2024 +0.0019). **Confirms REGRESS=0.5 and DC-decay=120 as the 2024-robust optimum** (matches CLAUDE.md). Defaults unchanged; best_brier stays 0.6381.

### Iteration 3 — stack the marginal keepers — **SOFT KEEP, best_brier 0.6381 → 0.6375 (+0.0006)**
Focus: features. Added two combined A/B sets: `+Marginals` (TZShift+PythagLuck+TM_Age+ASA_xGSplit+GKDistribution) and `+MargCore` (TZShift+PythagLuck+TM_Age).

**Feature-level (XGB A/B, 3-season avg): stacking interferes, it does NOT sum.**
| Set | Δ vs Base | note |
|-----|-----------|------|
| +TZ_Pythag (existing) | +0.0013 | still the best single set |
| +MargCore | +0.0007 | worse than TZ_Pythag — TM_Age dilutes |
| +Marginals (all 5) | −0.0003 | xGSplit+GKDist make it negative |

**Ensemble-level: +0.0006 (reproducible, deterministic across 2 runs).** Ensemble stacked 0.6381 → **0.6375**; per-season 2022=0.6382 (=), 2023=**0.6352** (was 0.6371), 2024=0.6389 (=). No season regresses. The gain is entirely 2023, because the per-season BestAB selector picks `+MargCore` on the 2022 cal fold and it generalizes to 2023 test (proper walk-forward, no leakage).

**Verdict: SOFT KEEP.** Meets the loop's bar (+0.0006 > +0.0005, no 2024/2022 regression, reproducible) so `+MargCore` is retained as a selectable candidate set. But flagged **fragile**: the win is single-season and rides on the cal-fold BestAB selection the architecture-log distrusts for inter-year shift — not a robust feature discovery (the A/B average says the marginals don't truly stack). Low risk to keep: if it stops generalizing, the selector simply won't pick it. `+Marginals` is a confirmed DROP (kept only as a diagnostic). **New best_brier 0.6375.**

### Iteration 4 — new features (venue-split form + goal-diff form) — **REGISTERED, no ensemble gain**
Focus: two new feature groups computed inside `add_rolling_features()`:
- **VenueForm**: home team's pts specifically in last 5/10 home games; away team's in last 5/10 away games. ELO uses a fixed HOME_ADV for all teams; this captures per-team venue tendencies.
- **GoalDiffForm**: rolling avg of (goals_scored − goals_against) per game in last 5/10 matches — captures finishing quality beyond pts (1-0 vs 3-0 are the same pts, very different xG/goal story).

| AB Set | Δ vs Base | note |
|--------|-----------|------|
| +VenueForm | +0.0000 | marginal alone |
| +GoalDiffForm | +0.0001 | marginal alone |
| **+VenueGoalDiff** | **+0.0013** | **KEEP — genuine interaction** |
| +MargCore | +0.0007 | same as iter 3 |
| +MargCoreVG | −0.0003 | DROP — too many features, interference |

**Ensemble: 0.6375 (unchanged).** BestAB selections: 2022=+All, 2023=+MargCore, 2024=+All — same as iter 3. `+VenueGoalDiff` never beats `+All` in the per-fold cal-fold BestAB contest.

**Key findings:**
- VenueGoalDiff is a real A/B signal (+0.0013 = same as +TZ_Pythag) but can't unseat +All in BestAB selection.
- Adding VenueGoalDiff features to +All regresses 2024 by 0.0005 (violates robustness gate) — so NOT added to `_ALL_EXTRA`; kept as standalone AB candidate only.
- Combining with MargCore (→ +MargCoreVG) causes interference (DROP −0.0003). Two confirmed-KEEP sets don't stack.
- The interaction between venue-specific record and goal-differential form is genuine (0+0 → +0.0013 combined) but the XGB cannot exploit it further when competing against +All's rich feature landscape.

**Verdict: SOFT KEEP (registered).** `+VenueGoalDiff`, `+VenueForm`, `+GoalDiffForm` retained in AB_SETS as diagnostic candidates. **best_brier unchanged at 0.6375.**

### Iteration 5 — CuratedAll (positive-signal features only) — **DROP**
Focus: test whether XGBoost is diluted by DROP-scoring features in `+All`. Constructed `+CuratedAll` = Base + only features with non-negative A/B delta: TZ, Pythag, VenueGoalDiff, ASA_xGSplit, TM_Age, TravelRest, GKDistribution (~20 features vs +All's 60+).

| AB Set | Δ vs Base | note |
|--------|-----------|------|
| +TZ_Pythag | +0.0013 | KEEP (consistent across all evals) |
| +VenueGoalDiff | +0.0013 | KEEP (consistent) |
| +CuratedAll | +0.0007 | marginal — worse than either individual KEEP |
| +MargCore | +0.0007 | same as before |

**Ensemble: 0.6375 (unchanged).** BestAB selections: 2022=+All, 2023=+MargCore, 2024=+All. `+CuratedAll` is marginal (+0.0007) and does not beat `+All` in BestAB selection.

**Key finding:** XGB's internal feature selection (colsample, tree pruning) handles DROP features effectively — they add no signal and are simply not split on. Removing them from the feature set makes `+CuratedAll` score *worse* than the individual best sets (+TZ_Pythag, +VenueGoalDiff), suggesting those sets succeed not because they exclude DROP features but because they have the right combination of positive features in the right proportions for XGB.

**Verdict: DROP.** best_brier unchanged at **0.6375**.

---

## Overnight loop — final scorecard (2026-06-06, 5/5 iterations complete)

| Iter | Focus | Verdict | Ensemble |
|------|-------|---------|----------|
| 1 | Blend cap sweep (20–40%) | DROP | 0.6381 |
| 2 | REGRESS / DC decay | DROP | 0.6381 |
| 3 | Stack marginals (+MargCore) | **SOFT KEEP** | **0.6375** |
| 4 | Venue-split form + goal-diff (+VenueGoalDiff) | REGISTERED | 0.6375 |
| 5 | Curated positive features (+CuratedAll) | DROP | 0.6375 |

**Net gain: 0.6381 → 0.6375 (+0.0006). Single source: iter 3 MargCore selection for 2023 fold.**

New registered A/B candidates (available for future loops): `+VenueGoalDiff` (Δ=+0.0013), `+VenueForm`, `+GoalDiffForm`, `+MargCoreVG`, `+CuratedAll`, `+MargCore`.

Structural insight from the loop: both confirmed KEEP feature sets (+TZ_Pythag, +VenueGoalDiff) score +0.0013 in A/B but never unseat `+All` in BestAB selection. XGB's internal noise-handling means a large feature set is self-curating. Future gains likely require new *independent* signal sources (e.g. injury reports, real-time lineup data, betting market odds) or a fundamentally different architecture rather than more feature engineering on the existing data.
