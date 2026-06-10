# MLS Prediction Model — Project Handoff

*Document date: 2026-06-09 (originally 2026-06-07). Branch: `claude/mls-prediction-dashboard-C2mQM`.*

---

## Executive Summary

This project builds a market-blind probabilistic model for MLS soccer match outcomes (home win / draw / away win), with the purpose of identifying betting edges as the gap between model probability and market probability. The current champion achieves an average Brier score of **0.6335** (sum-form, 2022–2025 four-fold walk-forward; re-baselined 2026-06-09 when the completed 2025 season was added as a fourth test fold) — meaningfully better than the uniform-random baseline (0.6406) and the naive always-predict-home baseline (0.6667). The research harness is fully extracted into a tested module package (`scripts/eval/`), a six-criterion promotion gate (plus an advisory paired-bootstrap significance check) protects the champion, and a calibration deep-dive definitively closed the draw-signal question.

A 13-iteration improvement loop (2026-06-09, recorded verdict-by-verdict in `docs/PLAN.md`) measured the harness's seed-noise floor (σ≈0.001 — twice the gate's 0.0005 threshold), adopted **seed bagging** (`--xgb-bag 5`) as the verification protocol (collapsing run variance to σ≈0.0002), validated retaining 2021 in training, and cleanly refuted seven hypotheses (train-on-cal, in-season recalibration in two forms, DC-through-cal, LightGBM bag members, NaN-handling, draw-hurdle architecture). Two marginal-positive levers are banked unpromoted: the wide hyperparameter grid (`--xgb-wide-grid`, ~−0.0003) and production bagging (~−0.0004 + determinism). The next priorities are the bag+wide-grid combined promotion attempt and Pi end-to-end validation.

---

## Project Goal and Context

### What the system predicts

Every MLS regular-season match is a three-way classification: home win (1), draw (X), away win (2). The model outputs calibrated probabilities for all three outcomes. The primary edge signal is:

```
edge = model_prob − market_prob
```

A positive edge on a given outcome means the model believes the market is underpricing that outcome. The **edge threshold for live betting is 8%** — matches below this threshold are not acted upon.

### Why it exists

Soccer betting markets are efficient enough that naive statistical models cannot consistently find edge. The hypothesis is that a carefully constructed structural-plus-machine-learning model, trained on xG and form rather than on historical odds, can identify persistent inefficiencies — particularly around draws and away wins, which bookmakers historically overprice in favor of liquidity on the home side.

### The market-blind constraint

Betting odds are **never used as model features**. If closing lines were used in training, the model would learn to reproduce the market's own assessment, collapsing `model_prob − market_prob` toward zero by construction. Odds enter only as the denominator of the edge calculation — after prediction, never before.

Pinnacle opening and closing lines are stored for CLV (Closing Line Value) analysis only.

### Production deployment

The production system runs on a Raspberry Pi. It executes `scripts/daily_update.py` on a schedule: this script fetches fresh data from ASA (xG, form, referee), ESPN (schedule), and The Odds API (lines), fits the model, and writes predictions to a PostgreSQL database. A Streamlit dashboard reads from that database. The research harness (`scripts/eval_baseline.py`) runs on a development machine and is never the source of production predictions.

---

## Current Model Performance

### Champion metrics

**Model ID:** `champion-4fold-229bac79-20260609T235515` (re-baseline of `challenger-regress-0.40`: identical model config, measurement extended to 4 folds + per-match vectors)
**Model file:** `models/research_model.py`
**Pointer:** `experiments/champion.json` → `experiments/champion-4fold.report.json`
**Metric convention:** sum-form Brier (range 0–2; see metric section below)
**ELO config:** K=25, HOME_ADV=80, REGRESS=0.40 (promoted 2026-06-07)

| Season | Brier (sum-form) | n matches |
|--------|-----------------|-----------|
| 2022   | 0.630402        | 489       |
| 2023   | 0.634451        | 521       |
| 2024   | 0.634305        | 522       |
| 2025   | 0.634725        | 540       |
| **Avg**| **0.6335**      | 2072      |

**Calibration error** (max decile, blend output): **0.0360**

(The prior 3-fold report — avg 0.6337, cal 0.0195 — is retained at `experiments/champion.report.json`; per-season differences vs that report reflect the data snapshot, not a model change. The strong 2025 fold is a substantive finding: once the cal fold (2024) represents the post-shift regime, the model handles it — the "2024 problem" was largely a one-season transition cost.)

**Per-class Brier breakdown:**
- Home: 0.2470 (best-predicted class — home dominance most predictable)
- Away: 0.1933 (second)
- Draw: 0.1934 (hardest class; structural weakness)

**Per-class calibration error:**
- Home: 0.0652
- Away: 0.0280
- Draw: 0.0741

**Prior champion (regress=0.50):** avg 0.63465, cal_err 0.0306 — superseded 2026-06-07.

### What these numbers mean

The sum-form Brier score sums squared errors over all three probability outputs per match without dividing by 2 (the "half-form" convention). Reference points:
- **Uniform random baseline:** 0.6406 (predict 1/3 each outcome always)
- **Naive home-always baseline:** ~0.6667
- **Champion: 0.6337** — 1.1% better than random, 4.9% better than naive

MLS soccer is close to a random process from the perspective of any model, so differences at the third decimal place represent real predictive value. The model's 0.6337 is well-established over three seasons and 1,532 test matches.

### Promotion gate

Any challenger must clear all six criteria in `scripts/promotion_gate.py` before replacing the champion:
1. **Core metric:** avg Brier gain ≥ 0.0005 vs champion
2. **2024 robustness:** 2024 Brier within +0.0005 of champion (i.e., does not regress the regime-shift season)
3. **Calibration:** max decile cal error within +0.005 of champion
4. **Coverage:** at least as many matches per season as the champion report
5. **Slices:** no season or confidence slice regresses by > 0.02
6. **Data source health:** all sources `ok=True` when a snapshot is present

A seventh, **advisory** check (`paired_significance`, added 2026-06-09) bootstraps the per-match Brier differences on common match_ids and reports P(challenger better); it never blocks, because the measured seed-noise floor (σ≈0.001 on avg Brier) means unpaired gains near 0.0005 are ambiguous — the paired evidence is printed for the human decision. Reports built by `model_report.py` embed the required `per_match` vectors.

The 2024 gate exists because 2024 was a regime shift (see The 2024 Problem below). The 2025 fold (added 2026-06-09) confirms the shift was largely a one-season transition cost. **Verification protocol (2026-06-09):** judge harness experiments on a single `--xgb-bag 5 --seed 42` run (bagging collapses seed noise to σ≈0.0002), and confirm any would-be gate claim at a second base seed — the hyperparameter-grid *selection* remains seed-sensitive even when fits are bagged.

---

## Architecture

### Pipeline (in execution order)

```
1. Dixon-Coles (DC) → raw 1X2 Poisson probabilities
2. Temperature scaling → calibrated DC probs
3. XGBoost multiclass (XGB) → raw 1X2 gradient-boosted probabilities
4. Temperature scaling → calibrated XGB probs
5. Capped convex blend: p = w * XGB + (1-w) * DC, w ∈ [0.7, 1.0]
   w fitted by Brier minimisation on the calibration fold
6. Second-pass temperature scaling on blend output
```

### Why each component

**Dixon-Coles (DC)** models each team's attack and defense strength as latent Poisson parameters. It includes the Dixon-Coles low-score correction (matches ending 0-0, 1-0, 0-1, 1-1 are structurally different from the Poisson baseline). This gives the model a well-principled structural prior over match outcomes, particularly for teams with few recent matches. DC uses a 120-day time-decay half-life so that recent matches are weighted more heavily.

**XGBoost (XGB)** handles nonlinear feature interactions that a Poisson model cannot capture: combinations of xG differential, form trends across multiple windows, keeper performance, altitude, timezone stress, and playoff context. It uses season-weighted training (weight half-life = 6 seasons) so that 2017 data contributes much less than 2024 data. An inner 12-combo grid search fits hyperparameters on the last two seasons of the training window each season (the calibration fold is reserved for calibration and blend fitting).

**Temperature scaling** converts raw logit outputs to calibrated probabilities. It fits a single parameter T (minimizing NLL on the calibration fold) that stretches or compresses the probability distribution. It is preferred over Platt scaling and isotonic regression because (a) it won the calibration sweep across all tested methods, and (b) its single degree of freedom cannot overfit the calibration fold's class distribution — a critical property given the 2024 regime shift.

**Capped-DC blend** combines DC and XGB probabilities using a convex weight. The XGB floor of 0.7 (DC ceiling of 0.30) is not arbitrary: DC failed catastrophically in 2024, and higher DC weights regress the 2024 Brier. At w=0.7, DC still contributes structural Poisson priors for low-data teams; at w=1.0, the model relies entirely on XGB. The blend weight is re-fitted each test year on the prior-year calibration fold.

**Second-pass temperature scaling** was added to fix a pre-blend calibration bug. The first calibration passes were applied to DC and XGB separately before blending. The blended output was itself miscalibrated (cal_err 0.1326 before the fix). Adding a second temperature scaling pass directly on the blended output brought cal_err down to 0.1490 (harness max-decile) and then to 0.0306 on the gated production model — and to **0.0195** under the current REGRESS=0.40 champion.

### Walk-forward validation design

**Test seasons: 2022, 2023, 2024, 2025** (four independent test folds; 2025 added 2026-06-09 when the season completed — 540 matches, cal fold 2024)

For each test season T:
- Train: all seasons in 2017–(T-2), COVID-bubble 2020 excluded (2021 retained — see below)
- Calibration fold: season T-1 (the most recent completed season before test)
- Test: season T (held out entirely — no leakage)

**Why walk-forward (not random split):** A random train/test split would leak future information into training — XGB would learn from 2024 matches while predicting 2022 matches. Walk-forward preserves the temporal structure and tests the model under the same conditions it faces in production: predict a future season using only past seasons.

**2021's status (corrected 2026-06-09):** Earlier versions of this document claimed 2021 was excluded and that test-2022 used a 2019 cal fold. The code has in fact retained 2021 since 2026-05-29 (`_COVID = {2020}` in eval_baseline.py): 2021 is the calibration fold for test 2022 and a training season for tests 2023/2024. A 3-seed A/B (2026-06-09, `--exclude-train-seasons 2021`) validated this: removing 2021 from training costs +0.0019 avg Brier, almost entirely on 2023 (+0.0055), where 2021 is the most recent training season. The retention is now the documented decision.

**Why 2020 is excluded:** The bubble season produced systematically different match dynamics: no crowds (eliminating home advantage), a condensed tournament format, roster disruptions. Including it in training contaminates the model's estimate of normal home advantage and form patterns. 2021 (partial attendance, full home-and-away schedule) empirically helps more than it contaminates — plausibly *because* its compressed home advantage resembles the post-2024 regime.

---

## What Was Built (Phase Summary)

### Metric standardization (F2)

Early in the project, Brier scores in the research harness and the Streamlit dashboard were computed on different conventions. The research harness uses **sum-form Brier** (`sum((p_i - y_i)^2)` across all three classes, no division; range 0–2). The dashboard displays **half-form Brier** (sum-form ÷ 2; range 0–1). Before this was documented, comparisons between harness output and dashboard metrics were silently wrong.

Resolution: `models/metrics.py` defines `brier_multiclass_sum()` as the single canonical implementation. `CURRENT_STATE.md` documents both conventions with explicit cross-reference. The dashboard pages that display half-form are labeled explicitly.

### Canonical model path (F1)

The legacy stack (`models/dixon_coles.py`, `models/gradient_boost.py`, `models/stacking_ensemble.py`) was the original production path. It has been superseded by `models/research_model.py`, which implements the DC + XGB + temperature + capped blend pipeline described above and is the sole source of predictions in Postgres.

The legacy files remain in the repo with deprecation banners because deletion is gated on Pi E2E validation — removing them before confirming the Pi can run the new path would leave production without a fallback.

### Data quality accounting (F5)

`data_pipeline/source_health.py` implements:
- `record_source_run()`: records raw_count, parsed_count, matched_count, and errors for each data source fetch into a `source_runs` Postgres table
- `coverage_gate_status()`: consumed by the promotion gate — a challenger is rejected if the data sources are degraded
- `odds_matching_report()`: verifies that upcoming matches have complete 1X2 odds coverage; missing draw odds are logged as WARNING (callers must not infer draw_prob=0 from absence)

All three primary data clients (ASA, ESPN schedule, Odds API) now call `record_source_run()` on each sync.

### Team metadata consolidation (F3/3b)

Previously, team name maps, conference assignments, expansion flags, coordinates, and dome flags were defined inline in three separate files (`asa_client.py`, `schedule_client.py`, `eval_baseline.py`), leading to drift. `data_pipeline/team_metadata.py` is now the single source of truth. Each consumer imports from there; the ~100 lines of duplicated inline definitions have been removed.

An accompanying critical config fix: the champion `parity_frame.meta.json` showed four xG windows (3, 5, 10, 15) but `CLAUDE.md`, `config/settings.yaml`, and `CURRENT_STATE.md` all said "5 and 15". The production `feature_builder` was therefore generating only 2 xG windows while the champion model expected 4. All documentation and config are now consistent with the actual champion.

### Monolith extraction (F4)

`scripts/eval_baseline.py` began as a ~2000-line monolith. The following have been extracted into tested modules under `scripts/eval/`:

| Module | Contents | Tests |
|--------|----------|-------|
| `dixon_coles.py` | Pure DC engine | 13 unit tests |
| `calibration.py` | Temperature/Platt/isotonic + cal-error metrics | — |
| `elo.py` | ELO update, season regression, home advantage | 14 unit tests |
| `feature_registry.py` | Constants (FIFA breaks, altitude IDs), geometry (haversine), feature helpers | 31 unit tests |
| `feature_builders.py` | `add_rolling_features()`, `add_h2h_draw_features()` | 34 unit tests |

Total: 98 non-DB passing tests. The two largest functions (ELO computation and rolling xG/form features) are extracted. The inline feature-builder sections (5a–5n) are lower priority since they depend on live ASA fetches and are harder to unit-test in isolation.

### Circular review loop (Phase 4/E)

The promotion gate (`scripts/promotion_gate.py`) enforces all three criteria (core metric, 2024 robustness, calibration) before a challenger can replace the champion. `model_report.py` produces a structured JSON report (e.g., `experiments/champion.report.json`) that captures per-season Brier, per-class calibration errors, confidence slices, and a data source health snapshot. The champion registry lives in `experiments/champion.report.json`. `make validate` runs a DB-free CI gate that verifies the champion report is reproducible.

### Feature hunt results

The following features were investigated and rejected through the gate:

- **Referee features (`ref_draw_rate`, `ref_hw_rate`):** The raw referee draw rate gave a Brier gain of +0.0010 in eval_baseline and passed the 2024 robustness gate, but failed on calibration (cal_err +0.0088 above tolerance). A calibration deep-dive proved this is a structural trilemma — see the dedicated section below. After exhausting all calibration approaches, the detrended version (`ref_draw_rate_rel`) fixed calibration but lost the Brier edge entirely. The question is definitively closed.

- **Standings leverage:** `season_pts`, `pts_vs_median`, and `ppg` features added −0.0015 Brier. ELO is collinear with cumulative season points; standings add noise, not signal.

- **H2H draw rate:** Prior-meeting draw fraction for each team pair (walk-forward safe) added −0.0027 Brier. Too sparse — most team pairs meet 3–6 times, insufficient to estimate a stable draw propensity.

- **Per-class (vector) calibration:** Helps 2023 (+0.0045) but catastrophically regresses 2024 (−0.0135). Net avg −0.0033. Root cause: the vector calibrator overfits the cal-fold class priors (2023 home rate 0.48) and amplifies miscalibration when the regime shifts (2024 home rate 0.45).

---

## Key Technical Decisions and Rationale

### 1. Sum-form Brier as canonical metric

The research harness always uses `sum((p_i - y_i)^2)` across three classes without division. This form makes per-season Brier values directly additive across classes (brier_home + brier_draw + brier_away = brier_sum). The half-form (÷2) is only used in the Streamlit dashboard for display. Mixing the two conventions was a historical source of confusion; the current convention is explicit in `models/metrics.py` and `CURRENT_STATE.md`.

### 2. COVID exclusion (2020 only; 2021 retained — corrected 2026-06-09)

2020 is excluded from training and from the calibration/test window entirely: it was played in a bubble without fans, home advantage effectively disappeared, and including it would pollute the ELO/DC home-advantage estimates. 2021 (partial attendance, normal home-and-away schedule) is retained — it serves as the cal fold for test 2022 and as training data for tests 2023/2024. A 3-seed A/B confirmed retention is worth +0.0019 avg Brier (the cost of excluding it lands almost entirely on 2023, which would otherwise lose its most recent training season).

### 3. Walk-forward validation

A temporal holdout is the only valid validation design for a time-series prediction task. Random splits leak future form, ELO ratings, and DC parameter estimates backward in time, producing optimistic bias in all reported metrics. Walk-forward also mimics the actual deployment scenario: each year, the model is trained on all prior years and evaluated on the next year. Four test seasons (2022–2025, n=2,072) provide a realistic variance estimate.

### 4. Temperature scaling over Platt/isotonic

Temperature scaling (fitting a single T parameter to minimize NLL on the cal fold) won the 2026-05-30 calibration sweep across all tested methods (temperature, Platt, isotonic, beta). The key structural advantage: a single degree of freedom cannot overfit the calibration fold's class distribution. This is essential given the 2024 regime shift — a calibrator with more degrees of freedom (e.g., vector/per-class scaling) would overfit the 2023 cal fold and amplify miscalibration in 2024.

### 5. DC cap at ≤30% blend weight

The XGB floor of 0.70 (DC ceiling of 0.30) was empirically determined: at higher DC weights, 2024 Brier regresses. The root cause is DC's static home field advantage parameter embedded in its Poisson means — DC cannot dynamically adapt to the 2024 HFA collapse. The cap means DC contributes structural priors (particularly for small-sample teams) without dominating a season where its core assumption failed. The blend weight w is re-fitted each test year on its own cal fold, so w=0.70 for both 2022 and 2024, w=0.841 for 2023.

### 6. ELO K=25, HOME_ADV=80, REGRESS=40%

K=25 and HOME_ADV=80 were grid-searched and locked. REGRESS was changed from 0.50 to **0.40 on 2026-06-07**: a sweep found that with the current 6-season XGB weight half-life (whl=6), regress=0.40 improves all three test seasons (avg 0.63465→0.6337, 2024 0.6354→0.6346) and sharply improves calibration (cal_err 0.0306→0.0195). This *reverses* the 2026-05-30 finding that "0.50 wins" — that earlier sweep was run at whl=4, where the interaction does not hold. The lesson: REGRESS and WEIGHT_HL interact, so they must be swept together, not independently. HOME_ADV=80 ELO points represents the typical MLS home advantage; K=25 (update step size) balances responsiveness against noise. The full validation went through `promotion_gate.py` (all 6 criteria PASS).

### 7. 2024 hard robustness gate

The promotion gate requires that any challenger's 2024 Brier stay within +0.0005 of the champion's 0.634633. This is stricter than a simple average improvement requirement. The rationale: 2024 represents the current operating regime (home win rate 0.45, not the historical 0.51). A model that recovers 2022/2023 performance at the cost of 2024 is a worse real-world model even if its average looks better. Every challenger must demonstrate it can handle the current regime.

### 8. Market-blind model

Betting odds are explicitly excluded from features. The edge signal `model_prob − market_prob` only exists if the two probabilities are generated from independent information sources. Using closing lines as features would cause the model to approximate the market, collapsing edge to near-zero by construction. The Odds API integration is for CLV measurement only.

### 9. xG windows (3, 5, 10, 15) — all four

The champion feature set includes rolling xG for/against at four window lengths: 3, 5, 10, and 15 matches. The short windows (3, 5) capture current form; the long windows (10, 15) capture season-level profile. XGBoost selects which windows to weight most heavily per match through the tree structure — having all four available allows the model to blend short-term and long-term signals. This was a critical config fix: the production `feature_builder` was generating only [5, 15] while the champion was trained on [3, 5, 10, 15].

---

## The 2024 Problem

### The regime shift

Home win rate in MLS:

| Period | Home win rate |
|--------|--------------|
| 2017–2023 historical | ~0.51 |
| 2024 | 0.45 |
| 2025 (in-progress) | ~0.45 (confirmed persistent) |

This is not noise. The home advantage appears to have structurally compressed — likely due to expansion clubs diluting the home crowd effect, rule changes, or the international player market equalizing across clubs. Whatever the cause, the shift is real and persistent.

### Why DC fails on this

Dixon-Coles models home advantage through an additive constant in the Poisson mean for home team goals. This constant is estimated from the full training history (2017 onward) and does not change within-season. When 2024's true HFA falls below the historical average, DC's static parameter systematically overestimates home win probability and underestimates draw and away win probabilities. In 2024, uncapped DC would produce significantly miscalibrated predictions.

### Why the capped blend is the right response

Capping DC's contribution at 30% limits the damage from DC's static HFA assumption. XGB, with its form-based features and season-weighted training, is better positioned to capture the shift because:
1. Its training weights recent seasons more heavily (weight half-life = 6 seasons)
2. Its features (rolling xG, form, ELO differential) directly encode recent team performance without relying on a static HFA constant

The blend weight w=0.70 for 2024 (vs 0.85 for 2023) reflects the automatic re-fitting on the cal fold — the optimization found that XGB needed a larger share in 2024 than in 2023.

### Why calibration cannot fix this

A per-class (vector) calibrator fitted on the 2023 cal fold would learn to adjust probabilities toward 2023 class frequencies (home rate ~0.48). Applied to 2024 (home rate 0.45), it would amplify the miscalibration rather than correct it. This was directly tested and confirmed: vector calibration regressed 2024 Brier by 0.0135. Scalar temperature, with one degree of freedom, cannot overfit the class distribution and is therefore more robust.

This same structural constraint applies to referee features: `ref_draw_rate` shifts the draw distribution in a way that the scalar calibrator cannot recalibrate, and any per-class calibrator that corrects the draw shift will overfit the 2023 draw rate and amplify the 2024 error. The 2024 regime shift is the single root cause of multiple seemingly unrelated calibration failures.

---

## What Didn't Work (and Why)

| Feature / Approach | What was tried | Result | Root cause |
|--------------------|---------------|--------|------------|
| Referee draw rate (`ref_draw_rate`) | Season-lagged per-referee draw rate from ASA games; 86% coverage | Gain +0.0010 Brier, PASS 2024, FAIL calibration (+0.0088 above tolerance) | The draw-rate feature shifts the draw class distribution; scalar temperature cannot recalibrate it |
| Referee home-win rate only (`ref_hw_rate`) | Dropped `ref_draw_rate`, kept `ref_hw_rate` only | avg 0.634537 (gain +0.0001, FAILS core_metric), 2024 0.63812 (FAILS robustness) | The Brier value lives in `ref_draw_rate`, not `ref_hw_rate` |
| Detrended referee (`ref_hw_rate_rel`, `ref_draw_rate_rel`) | Referee rate minus league prior-season average | Calibration PASS (0.0394→0.0332), 2024 PASS, avg 0.63499 (FAILS core_metric, −0.00034 vs champion) | Detrending removes the regime-sensitive component that was producing the gain; edge and fragility are the same signal |
| Per-class (vector) calibration | Per-class temperature scaling (3 free parameters fitted on cal fold) | avg 0.6379, 2024 0.6489 (catastrophic −0.0135 regression) | Overfits 2023 cal fold class priors; amplifies HFA-shift miscalibration in 2024 |
| Calibration variant sweep (14 variants) | `tempbias λ` and `vshrink λ` interpolating between scalar and vector | Every gain in draw calibration worsens 2024 monotonically | Hard trilemma: a cal-fold-fit calibrator cannot anticipate a same-year regime change |
| Standings features (`+Standings`, `+StandingsCore`) | Cumulative season points, ppg, pts-vs-median | −0.0015 to −0.0004 Brier | ELO collinearity — season points are a noisy proxy for what ELO already encodes |
| H2H draw rate | Prior-meeting draw fraction, walk-forward safe, min 3 meetings | −0.0027 Brier | Too sparse — typical MLS team pair meets 3–6 times; insufficient to estimate stable draw propensity |
| DC shorter time-decay window | (Earlier experiment; exact result merged into blend design) | No leverage | The capped blend already floors DC's contribution; DC window changes are dominated by XGB |
| 2-season cal fold pooling | Pool test−1 and test−2 for calibration (N=2) | avg cal_err WORSE despite larger fold | COVID exclusions mean only 2/4 seasons benefit from true pooling; 2021 (COVID-adjacent) degrades the average |
| Isotonic regression calibration | Applied at first-pass and second-pass stages | Consistently regresses Brier due to overfitting at ~470–520 sample size | Monotone constraint insufficient regularisation; too flexible for this dataset size |

---

### The 2026-06-09 improvement loop (13 iterations)

Run verdict-by-verdict against a pre-registered queue (full detail in the `docs/PLAN.md` top blocks):

| Item | Verdict | One-line takeaway |
|------|---------|-------------------|
| Parity/doc integrity (I3) | FIXED | Frame rebuilt at regress=0.40; parity target now follows `champion.json` |
| Seed wiring + noise floor (I2) | MEASURED | `--seed` now reaches XGB; σ≈0.001 across seeds — the 0.0005 gate bar is sub-noise unbagged |
| 2021 retention (I1) | VALIDATED | Excluding 2021 from training costs +0.0019 (all on 2023); docs corrected, code kept |
| Train-on-cal refit (T1a) | DROP | +0.0027 — the cal-season holdout is load-bearing, not waste |
| In-season scalar-T recal (T1b) | DROP | +0.0005 uniform — scalar T cannot move class priors |
| In-season prior correction (T1b′) | DROP | Real 2024 gain at α=300, offset ~1:1 by non-regime years |
| XGB seed bagging (T1c) | **KEEP (infra)** | `--xgb-bag 5`: σ 0.0011→0.0002; now the verification protocol; ~−0.0004 expected |
| LightGBM bag members (T1c) | DROP | +0.0021 — untuned members dilute the bag |
| NaN-vs-0 features (T2b) | CLOSED | Premise false — builders already impute league-typical priors |
| DC-through-cal (T2a) | DROP | +0.0004 — same lesson as T1a |
| Wide XGB grid (T2c) | MARGINAL | −0.0003 two-seed mean; flag banked, unpromoted |
| 2025 fold + re-baseline (gate) | DONE | Champion 0.6335 on 4 folds; 2025 = best harness season (0.6315 bagged) |
| Paired bootstrap (gate) | DONE | Advisory significance check in `promotion_gate.py` |
| Draw hurdle (T3a) | DROP | First architecture to beat the draw column (0.1925), but H/A renorm costs more |

---

## Open Questions / What's Next

### 0. Bag + wide-grid combined promotion (IN FLIGHT, 2026-06-09 evening — screening PASSED, port DONE)

The two banked marginals cleared the screening rule combined: 4-fold bagged harness, two base seeds, combo mean 0.63262 (−0.00085 vs the champion's 0.633471). The port landed in `models/research_model.py`: `fit_xgb(wide_grid=, n_bags=)` returns a list of classifiers, predictions go through `bag_proba()`, and defaults are exact no-ops. `model_report.py --n-bags 5 --wide-grid` builds the challenger report; `promotion_gate.py` decides (auto-promote on PASS per user decision). Status lives in the `docs/PLAN.md` "Promotion cycle" block.

### 1. dc_p_draw as XGB feature (TESTED — DROP)

The draw class remains the hardest to predict (~0.1934 Brier; all direct draw signals have failed the gate). The DC analytical draw probability (`dc_p_draw`, the diagonal sum of the Dixon-Coles score matrix) was added as an XGB feature and A/B tested on 2026-06-07: `+DCDrawProb` Δ=−0.0005, `+DCParams` (dc_lam+dc_mu) Δ=−0.0016, `+DCAll` Δ=−0.0026 — **all DROP**. Root cause: `dc_p_draw = f(λ, μ)` is a deterministic function of the Poisson means, which are themselves deterministic functions of team attack/defense strength — already captured by the rolling xG features in Base. No new signal. The function `dc_draw_prob_batch()` is retained in `scripts/eval/dixon_coles.py` for reference, but the column is not in Base or `_FEAT_ALL`.

### 2. ELO parameter sweep (DONE — REGRESS 0.50→0.40 promoted)

A WEIGHT_HL × REGRESS sweep was run on 2026-06-07. WEIGHT_HL=6 was confirmed best (3,4,5,7,8 all worse or equivalent). REGRESS=0.40 beat the 0.50 champion (avg 0.63367 vs 0.63467, Δ=−0.00100; 2024 0.6346 PASS) and was promoted (see design decision #6). Remaining unexplored knobs: HOME_ADV finer increments (50–90), DC recent-seasons window, schedule-density window. Run via `scripts/eval_baseline.py --ab-only Base` with parameter overrides; validate any winner with `model_report.py` + `promotion_gate.py` before promoting.

### 3. Pi E2E validation

**Current status:** The research harness (`eval_baseline.py`) and `models/research_model.py` are confirmed to produce identical outputs (`make parity-check`, |Δ| < 0.0015). The parity check is DB-free (frame-based). What has NOT been confirmed: that `scripts/daily_update.py` running on the Pi produces predictions that match the research model's expected probabilities for the same matches.

**Blocking issue:** No Pi-side test run has been executed in this session. The runbook is at `docs/PI_VALIDATION.md`. The gate is `make validate` (DB-free CI).

**What Pi E2E validation means:** Run `make daily-update` on the Pi, then compare its written predictions against `research_model.predict_upcoming()` called with the same input features. Both should agree within a tolerance.

**After Pi E2E passes:** The legacy model files (`models/stacking_ensemble.py`, `models/gradient_boost.py`, `models/dixon_coles.py`) can be deleted. They currently carry deprecation banners. Deletion is the unlock for cleaner production imports.

### 4. Phase 5: better data sources

The ASA API is the primary xG source. Potential improvements:
- StatsBomb open data for shot location and sequence context (not just xG totals)
- FBref referee statistics as a richer referee feature base (currently using ASA games_raw referee column, which may have sparse coverage)
- Weather data from Open-Meteo at kickoff time is listed as a Phase 2 feature; not yet implemented

Evaluation checklist for any new data source: (a) confirm temporal leakage safety, (b) measure coverage rate, (c) implement graceful fallback for missing values, (d) run as an AB set in eval_baseline, (e) port to research_model only if the gate clears.

### 5. Legacy model deletion

Waiting on Pi E2E validation. After that passes, `models/stacking_ensemble.py`, `models/gradient_boost.py`, and `models/dixon_coles.py` can be deleted or archived. These files currently run only for "component predictions" in daily_update.py — a leftover from the old stacking architecture — but are not the source of the ensemble predictions that go into Postgres.

---

## Known Limitations

### Draw class

The draw class has a Brier of ~0.1934 — the hardest class to predict. Every systematic attempt to improve draw prediction has been closed:
- H2H draw rate: −0.0027 Brier (DROP)
- Referee draw rate: genuine Brier gain, gated on calibration (hard trilemma proved)
- Vector calibration: catastrophic 2024 regression (DROP)
- dc_p_draw: −0.0005 Brier (DROP — deterministic function of λ/μ, no new signal)

The draw class weakness may be structural for MLS: draws occur in roughly 28% of matches but are the outcome most sensitive to in-game dynamics that are not predictable from pre-match features.

### Referee feature

`ref_draw_rate` is the first independent draw signal found in the entire project. It is real (XGB importance 2.8%; improves draw Brier 0.1943→0.1936 in harness). It is correctly gated out of production today. The path to promotion requires either: (a) a calibration method that does not overfit the 2023 cal fold's draw distribution — impossible with any cal-fold-fit calibrator while the 2024 regime shift persists; or (b) additional training seasons (2025, 2026) that normalize the regime, allowing the calibration fold to represent the current draw-rate distribution. This is an open research item, not a known bug.

### Production/research gap

The research harness (`eval_baseline.py`) and `models/research_model.py` are parity-verified (|Δ| < 0.0015 on the parity frame). However, Pi-side E2E has not been run in this session. There may be environment differences (Python version on Pi, package versions, Postgres schema) that cause silent divergence. The parity check is the guard rail, but it only confirms the model code; it does not confirm the full daily pipeline.

### SSL / ASA certificate

The ASA client (`itscalledsoccer`) has a certificate issue. This is handled with scoped `session.verify = False` on the ASA HTTP session object only. Three global SSL bypass environment variables (`PYTHONHTTPSVERIFY=0`, `CURL_CA_BUNDLE=""`, `REQUESTS_CA_BUNDLE=""`) that were previously in eval_baseline.py have been removed (F6 fix) — those disabled TLS for the entire Python process. The scoped approach is the correct fix. If the ASA certificate is resolved upstream, the `verify=False` line should be removed from `data_pipeline/asa_client.py`.

---

## How to Continue This Work

### Repository layout

```
scripts/eval_baseline.py       Research harness — add/test new features here first
scripts/eval/                  Extracted modules: dc, elo, calibration, feature_registry, feature_builders
models/research_model.py       Canonical production model — port features here after gate passes
models/metrics.py              brier_multiclass_sum() — the canonical metric function
data_pipeline/source_health.py Data quality accounting + coverage gate
data_pipeline/team_metadata.py Team name/conference/coordinate single source of truth
experiments/champion.report.json Current champion's signed metrics (do not hand-edit)
data/parity_frame.parquet       Shared feature frame for research_model ↔ harness parity check
data/parity_frame.meta.json     Describes feat_base, window config, ELO params of the champion frame
docs/CURRENT_STATE.md           Single source of truth for canonical config and metric definitions
docs/PI_VALIDATION.md          Runbook for Pi E2E validation
```

### Adding a new feature

1. Add a new section (e.g., `# 5p — my feature`) to `scripts/eval_baseline.py`
2. Add a new AB set key (e.g., `"myfeature": [...feature list...]`) to the `AB_SETS` dict
3. Run: `python scripts/eval_baseline.py --ab-only Base,+MyFeature --seed 42`
4. If avg Brier gain ≥ 0.0005 and 2024 does not regress, proceed
5. Port the feature computation to `models/research_model.py` (matching the walk-forward safe pattern)
6. Rebuild `data/parity_frame.parquet` with the new feature included
7. Run: `python scripts/model_report.py` to produce a challenger report
8. Run: `python scripts/promotion_gate.py --challenger <report.json> --champion experiments/champion.report.json`
9. If all six gate criteria PASS, promote (`promotion_gate.py promote`) — this updates `experiments/champion.json` — and update `docs/CURRENT_STATE.md`

### Running the eval harness

```bash
# Full walk-forward eval, all AB sets
python scripts/eval_baseline.py --seed 42

# Smoke-test only (fast, verifies 2024 Base Brier ≈ 0.6346 ± 0.001, regress=0.40)
make smoke-test

# Run just the Base config + one challenger AB set
python scripts/eval_baseline.py --ab-only Base,+Referee --seed 42

# Parity check: verify research_model matches eval harness (|Δ| < 0.0015)
make parity-check

# Full DB-free CI gate
make validate
```

### Interpreting a model report

The `experiments/champion.report.json` file structure:
- `avg_brier`: the headline metric (lower is better; champion is 0.6337)
- `per_season`: per-year breakdown (2022/2023/2024); watch for 2024 regression
- `max_decile_cal_error`: calibration quality (champion is 0.0195; gate tolerance is +0.005)
- `overall.brier_draw`: the structurally hardest class (champion 0.1934)
- `w_xgb`: the blend weights fit per test season (confirms whether DC got capped)
- `per_class_calibration_error`: home/draw/away calibration; home and draw are the concern

Against the current 4-fold champion a challenger report must show: (a) `avg_brier` < 0.633471 − 0.0005 = 0.632971, (b) `per_season.2024` < 0.634305 + 0.0005 = 0.634805, and (c) `max_decile_cal_error` < 0.0360 + 0.005 = 0.0410 — plus the coverage, slice, and source-health guardrails. Challenger reports must be built on the same 4-fold basis (`model_report.py` defaults to it via `parity_frame.meta.json`).

### Git conventions

All work goes on branch `claude/mls-prediction-dashboard-C2mQM`. Never push to main without explicit instruction. The `docs/PLAN.md` must be updated in the same commit as any eval result change or feature add/drop.
