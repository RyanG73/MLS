# Calibration Log

> Results from the calibration-tuner agent. Populated by the multi-agent improvement workflow.
> See `docs/experiment-protocol.md` for the protocol.
>
> Current state (from PLAN.md): max decile calibration error ≈ 0.12–0.18 (target < 0.05).
> Active method: temperature scaling.

---

## 2026-06-07 — Referee draw-shift calibration: a proven TRILEMMA (probe)

Goal: find a calibration that absorbs the +Referee (`ref_draw_rate`) draw-shift
without the vector-cal 2024 penalty, to unlock the gated Brier win (0.63465 →
0.63397) and F9. Tool: `scripts/probe_referee_calibration.py` — runs the
research_model walk-forward ONCE per season (gate-faithful), caches the
pre-final-calibration blend probs, then sweeps calibration families instantly.
Metrics match `model_report.py` exactly. Champion ref: avg 0.63465 · 2024
0.635364 · cal 0.0306. Gate: gain≥0.0005, 2024≤0.635864, cal≤0.0356.

Families swept (14 variants): `scalar` (current), `vector` (per-class T),
`tempbias λ` (shared T + L2-regularised per-class bias `b`), `vshrink λ`
(per-class T shrunk toward a common temp). λ→∞ ≡ scalar; λ→0 ≡ vector.

| method | avg | 2024 | cal_err | blocker |
|--------|-----|------|---------|---------|
| scalar (current) | 0.63397 | 0.63566 ✓ | 0.03945 | cal |
| vector | 0.63633 | 0.64612 | 0.04879 | all three |
| tempbias λ=2.0 | 0.63399 ✓ | 0.63594 | 0.03894 | 2024 (+0.00004), cal |
| tempbias λ=0.5 | 0.63408 | 0.63673 | **0.03451 ✓** | 2024 |
| vshrink λ=1.0 | 0.63420 | 0.63644 | **0.03535 ✓** | 2024 (+0.0006), core (+0.00005) |
| vshrink λ=0.5 | 0.63439 | 0.63713 | **0.02825 ✓** (beats champ!) | 2024, core |

**Finding — a hard trilemma.** The relationship is monotonic across the full
scalar↔vector spectrum: every increment of class-specific flexibility that
recovers the draw calibration *simultaneously* worsens 2024 Brier. Root cause
(same as the 2024 diagnosis): the draw correction is fit on the 2023 cal fold and
misapplied to the 2024 HFA-collapse regime. The Brier gain, the calibration fix,
and 2024 robustness are mutually exclusive in pairs — **no cal-fold-fit
calibration clears all three gates.** This generalises the earlier vector-cal
DROP: it is not a tuning problem, it is structural.

**Consequences / paths (none are "just a calibration method"):**
  1. Make the draw signal regime-robust — e.g. season-detrended `ref_draw_rate`
     (relative to league draw rate) so its calibration correction generalises
     across the HFA shift. This is a FEATURE change, the most promising next step.
  2. Multi-regime held-out cal fold — structurally impossible without sacrificing
     recent training data (cal must stay = test−1; train can't see the future).
  3. Governance: the referee model's absolute cal_err (0.0394) is still under the
     historical <0.05 target; the gate REJECTS on a *relative* +0.005 regression
     vs an unusually-good champion (0.0306). Widening the relative tol is a
     policy decision for the owner, not a calibration fix — flagged, not taken.

**RESOLUTION (same day) — the trilemma is dissolved by a regime-robust feature,
which also dissolves the gain.** Since no post-hoc calibration works, the root
cause was attacked at the feature: season-detrended referee rates
(`ref_hw_rate_rel`, `ref_draw_rate_rel` = ref prior-season rate − league
prior-season rate; eval_baseline `+RefereeRel`). Re-dumped the parity frame and
gated via research_model:

| variant | avg (gain vs champ) | 2024 | cal_err | gate verdict |
|---------|---------------------|------|---------|--------------|
| raw referee | 0.63397 (+0.00068) | 0.63566 | 0.03945 | REJECT — **calibration** |
| detrended referee | 0.63499 (−0.00034) | 0.63551 | **0.03320** | REJECT — **core (no gain)** |

Detrending **fixed both calibration (0.0394→0.0332, PASS) and 2024 (PASS)** — but
the Brier edge vanished (now −0.0003 vs champion). **Conclusion: the referee
"edge" and its calibration/2024 fragility were the SAME thing** — both lived in
the regime-sensitive season-draw-rate component. The pure ref-deviation signal is
calibration-clean but not predictive of individual matches. **There is no robust,
promotable referee Brier improvement; the question is now definitively closed.**
Both `+Referee` and `+RefereeRel` remain eval_baseline AB sets (DROP); neither
promoted. The earlier "first Brier win" (harness 0.6327) was a non-robust artifact.

Reproduce: `python scripts/probe_referee_calibration.py`;
`python scripts/model_report.py --extra-feats ref_hw_rate_rel,ref_draw_rate_rel ...`

**experiment_id:** probe-referee-cal-20260607, chal-referel-20260607

---

<!-- calibration-tuner agent appends entries here -->

## 2026-06-06 — Per-class (vector) calibration on the blend output (Phase 4d)

Motivated by `docs/2024-diagnosis.md`: 2024 is a directional home→away outcome shift
that a scalar temperature cannot correct. Tested whether per-class **vector scaling**
on the blend output (`z'_c = w_c·log(p_c) + b_c`, 6 params fit on the cal fold by NLL)
beats the canonical scalar temperature. Probe: `scripts/probe_vector_calibration.py`
on `data/parity_frame` (walk-forward folds identical to production).

| Season | scalar Brier | vector Brier | Δ (scalar−vector) |
|--------|-------------|--------------|-------------------|
| 2022   | 0.6317      | 0.6325       | −0.0008           |
| 2023   | 0.6369      | **0.6324**   | **+0.0045**       |
| 2024   | 0.6354      | **0.6489**   | **−0.0135**       |
| **avg**| **0.6347**  | 0.6379       | **−0.0033**       |

**Verdict: DROP — KEEP SCALAR.** Vector calibration helps 2023 (+0.0045, cal fold 2022
matches the test regime) but catastrophically regresses 2024 (−0.0135) and fails the
2024 robustness gate.

**Key finding (confirms the 2024 diagnosis):** the 2024 shift is *unforecastable from
the prior-season cal fold*. Extra calibration degrees of freedom overfit the cal-fold
class priors (2023 home-rate 0.48) and *amplify* miscalibration when the regime flips
(2024 home-rate 0.45). Scalar temperature is robust precisely because its single degree
of freedom cannot overfit the cal-fold outcome distribution. This is structural, not
tunable: no cal-fold-fit calibrator can anticipate a same-year regime change.

**Action:** Default remains scalar `temperature` on the blend output. Reproduce:
`python scripts/probe_vector_calibration.py --frame data/parity_frame.parquet`

---

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

---

## 2026-05-30 — Cal-fold pooling + 2-stage calibration sweep (Iteration 6)

All experiments on branch `claude/mls-prediction-dashboard-C2mQM`, `--ab-only Base --cache --seed 42`.

**Structural change implemented:** Added `--cal-pool-seasons N` flag to `eval_baseline.py` (default=1,
reversible). When N=2, the calibration fold pools `test_season-1` AND `test_season-2` (~1000 matches
vs ~470 for N=1). Also added `temp_then_platt` and `temp_then_isotonic` 2-stage calibration methods.

**COVID interaction:** Pooling 2 prior seasons is limited by COVID exclusions (2020, 2021 both excluded).
- test_season=2021 → pool=[2019] only (2020 excluded) — same ~420 matches as pool=1
- test_season=2022 → pool=[2021] only (2020 excluded) — same ~470 matches as pool=1
- test_season=2023 → pool=[2021,2022] = ~961 matches — true doubling
- test_season=2024 → pool=[2022,2023] = ~1010 matches — true doubling

Only 2 of 4 test seasons actually benefit from pooling; 2021 is uniquely worse (tiny cal fold).

| Method                        | best_brier | max_cal_error | Δ Brier      | Δ CalErr     | Verdict |
|-------------------------------|-----------|--------------|--------------|--------------|---------|
| temp_then_platt (pool=1, ref) | 0.6388    | 0.1147       | (ref)        | (ref)        | ref     |
| temp_then_platt (pool=2)      | 0.6382    | 0.1487       | +0.0006      | −0.0340      | **DROP** |
| temp_then_isotonic (pool=2)   | 0.6408    | 0.2003       | −0.0020      | −0.0856      | **DROP** |

**Verdict:** Both pool=2 variants → **DROP**.

- `temp_then_platt pool=2`: cal_err is *worse* (0.1487 vs 0.1147) despite doubling the cal fold for 2023/2024.
  The 2021 test season (with only ~420 cal matches) is included in pool=2 but not pool=1, dragging the
  average cal_err up. Brier marginal improvement (+0.0006) does not compensate.
  
- `temp_then_isotonic pool=2`: Brier regression (−0.0020 < −0.001 threshold) → DROP regardless of
  calibration. Isotonic remains unstable even at ~1000 matches for 2023/2024 seasons.

**Key finding — the 2-season cal pool hypothesis is falsified:**
The COVID gap (2020, 2021 both excluded) means that pooling 2 prior seasons only helps 2023 and 2024.
The 2021 season is forced to use an even smaller cal fold (2019 only, skipping 2020) which introduces
a new worst-case fold not present in pool=1. The structural constraint is not just fold size but also
data density in the COVID-adjacent years.

**cal_err floor diagnosis:** The per-season cal_err would need to be tracked individually to confirm
whether 2023/2024 show improvement with pool=2. The averaged metric is contaminated by 2021.
A future experiment with `--test-seasons 2023 2024 --cal-pool-seasons 2` would isolate the signal.

**Recommendation:** Keep current `temp_then_platt pool=1` as default. Pool=2 does not improve the
overall cal_err metric due to COVID-era data gaps. Structural fix requires either more non-COVID
seasons (future data) or targeted architecture changes.

**experiment_ids:** cal-pool1-temp-platt-ref-20260530T174202, cal-pool2-temp-platt-20260530T174207,
cal-pool2-temp-isotonic-20260530T174211

---

## 2026-05-30 — Calibration on the capped-DC blend (cycle #3)

Post cycle-2, the ensemble is a capped-DC convex blend (not the LR meta-learner). Re-tested calibrators:

| Method | best_brier | cal_err | Verdict |
|--------|-----------|---------|---------|
| temp_then_platt (default) | 0.6363 | 0.1326 | ref |
| temperature (no 2nd pass) | 0.6363 | 0.1326 | **identical** — temp_then_platt is a NO-OP on the blend |
| temp_then_isotonic | 0.6409 | 0.1722 | **DROP** (isotonic overfits) |

**Finding:** the cycle-1 Platt 2nd-pass was neutralized by the cycle-2 blend (it calibrated the LR meta-learner output, which no longer exists). No post-hoc calibrator recovers the blend's cal_err (0.1326). Reaching <0.05 needs a calibrator re-targeted at the blended output, or raw-model changes — not method choice. Default left as temp_then_platt (≡ temperature here) pending that work.
**experiment_ids:** c3-cal-temp-20260530T222153, c3-cal-iso-20260530T222417
