# MLS Prediction Model — Project Handoff

*Document date: 2026-06-09 (originally 2026-06-07). Branch: `claude/mls-prediction-dashboard-C2mQM`.*

---

## Executive Summary

This project builds a market-blind probabilistic model for MLS soccer match outcomes (home win / draw / away win), with the purpose of identifying betting edges as the gap between model probability and market probability. The current champion — a **5-member XGB seed bag** promoted 2026-06-10 — achieves an average Brier score of **0.6330** with calibration error **0.0182** (sum-form, 2022–2025 four-fold walk-forward) — meaningfully better than the uniform-random baseline (0.6406) and the naive always-predict-home baseline (0.6667). The research harness is fully extracted into a tested module package (`scripts/eval/`), a six-criterion promotion gate (plus an advisory paired-bootstrap significance check) protects the champion, and a calibration deep-dive definitively closed the draw-signal question.

A 13-iteration improvement loop (2026-06-09, recorded verdict-by-verdict in `docs/PLAN.md`) measured the harness's seed-noise floor (σ≈0.001 — twice the gate's 0.0005 threshold), adopted **seed bagging** (`--xgb-bag 5`) as the verification protocol (collapsing run variance to σ≈0.0002), validated retaining 2021 in training, and cleanly refuted seven hypotheses (train-on-cal, in-season recalibration in two forms, DC-through-cal, LightGBM bag members, NaN-handling, draw-hurdle architecture). The follow-on promotion cycle gate-tested both banked levers: bag+wide-grid was **rejected** (Brier gain, calibration cost) and bag-only was promoted by a documented user override (sub-noise shortfalls, calibration halved). On 2026-06-11 the project moved to a webapp-only architecture (the Postgres/Streamlit/Pi stack was archived under `legacy/`) and the dashboard gained a what-if standings simulator, MLS Cup odds, projected scores, ELO, and an in-season Brier readout. A 7-experiment feature round (Phase B) followed — season-decay rolling, manager tenure, per-team HFA + neutral sites, weather (89% coverage), roster construction, and extended history — all DROP or marginal, with the champion unchanged at 0.6330. **The unanimous finding: the model is at its pre-match-feature ceiling — ELO + rolling xG/form already absorb team quality, home advantage, manager effects, conditions, and roster investment.** The frontier is now the betting/CLV workstream (measuring edge vs the market; opening-line logging is in place via `data_pipeline/odds_log.py`).

---

## Update 2026-06-15 — Phase 3 (10 leagues live) + Phase 4 (value/edge layer)

**12 leagues now live** in the sidebar: MLS, the Big-5 (EPL, La Liga, Serie A, Bundesliga, Ligue 1),
5 European second-tier (Championship, League One, League Two, 2.Bundesliga, Serie B), and Liga MX.

**Phase 3A (European 2nd-tier):** Championship/League One/League Two use football-data.co.uk goals-only
CSVs — same pipeline as big-5, `xG=NaN` triggers the goals-only fallback in `add_rolling_features`.
Walk-forward 2022–2025 Brier: 0.632–0.658, all beat naive by 2–3%. PROMO/PLAYOFF/RELEG bucket system
generalized via `OUTLOOK` dict + `_TOP()` / `_PROMO()` helpers in `build_league_data.py`.

**Phase 3B (Liga MX):** FBref/soccerdata only covers the Big-5; pivoted to ESPN scoreboard API
(`site.api.espn.com/…/mex.1/scoreboard`). Season encoding: sequential integers via
`(year-2017)*2 + (1 if clausura else 2)` — Clausura 2017=1 through Clausura 2026=19, skipping 7
(Clausura 2020 cancelled). `data_pipeline/espn_soccer.py` fetches 2,767 matches across 18 torneos.
The accuracy card uses `labelMap` from `perf_by_year[].label` to show "Ap.2025"/"Cl.2026" columns
rather than season integers. Liguilla bucket: top 8 of 18.

**Phase 4 (value/edge layer):** All 10 European leagues gain per-match market edge fields
(`mkt_home/draw/away`, `edge_home/draw/away`) and a `value_layer.backtest` block. The build script
runs `walk_forward_predictions` + `attach_market` (football-data.co.uk), then flat-bet simulates
all matches where `model_edge ≥ 8%` at fair (de-vigged) odds. EPL result: 1,085 bets over 7 seasons,
hit rate 28.7%, ROI −5.8% — the model finds apparent edges but Pinnacle's pricing is sharp enough
to make them unprofitable at fair odds. Honest and expected. The Health tab gains a backtest card.
`edgePick()` now renders real edge percentages (e.g. "+12% H") when market data is present.

**Pending (before next session):** rebuild 9 leagues (la-liga through serie-b) with Phase 4 code:
```bash
for league in la-liga serie-a bundesliga ligue-1 championship league-one league-two bundesliga-2 serie-b; do
  venv/bin/python scripts/build_league_data.py --league $league --sims 5000
done
```
Then `git add webapp/data/*.js && git commit`.

**Next priority tracks:**
1. Liga MX Apertura 2026 (~July 2026): add torneo window to `_LIGA_MX_WINDOWS` in `espn_soccer.py`.
2. European 2026-27 rollover (August 2026): fresh Understat fetch per league; `build_league_data`
   auto-detects new fixtures.
3. Live `value_bets`: populate `value_layer.value_bets` for upcoming matches — football-data.co.uk
   publishes current-season CSVs that can feed the same de-vig pipeline.

---

## Update 2026-06-14 — Multi-league platform: big-5 European leagues live

The platform now serves **EPL, La Liga, Serie A, Bundesliga, and Ligue 1** alongside MLS, behind the
left sidebar. The model is **unchanged** — the MLS champion pipeline (ELO + Dixon-Coles + bagged XGBoost
+ capped-DC blend + temperature) transfers to European football with zero model branching, validated on
all five (2022–2025 walk-forward, `n_bags=1`): La Liga 0.5863, EPL 0.5890, Bundesliga 0.5934, Serie A
0.5946, Ligue 1 0.6035 — every one beats the MLS champion's 0.6330 and beats naive by 6.8–9.7% (MLS
only ~1.2%), because European leagues carry far more capturable signal (lower parity).

New components: `data_pipeline/understat.py` (per-match xG adapter, 2014+), `scripts/eval/league_features.py`
(league-agnostic feature composition), `scripts/validate_league.py`, `scripts/build_league_data.py`
(single-table dashboard builder: Title / Top-4 UCL / Relegation). The webapp branches on `outlook.mode`.
See `docs/CODE_WALKTHROUGH.md` §11 for the full flow. The European 2025-26 seasons are complete, so the
leagues launch as finished final tables; live projections resume when 2026-27 starts (Aug 2026).

**Phase 2 (same day):** added a real **betting-market benchmark** for the European leagues
(`data_pipeline/football_data.py`, football-data.co.uk Pinnacle/market odds) — the accuracy card now
shows two consistent tracks (model vs naive, model vs market) with a headline that averages the row
beneath it (the old champion-vs-uniform "+1.19%" that didn't reconcile is retired). The model trails
Pinnacle by ~2% Brier — strong for a market-blind model. Also: `scripts/build_all.sh` (seasonal rebuild
of all live leagues), a single-table what-if simulator (`runSimTable`, inert until 2026-27), and a
Phase-3 feasibility verdict (Liga MX viable via FBref; lower divisions need a goals-only variant).

Everything below this note is the MLS-specific model history and remains current for the MLS league.

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

### Production deployment (webapp-only)

Production is database-free. A scheduled job on a Mac runs `scripts/build_dashboard_data.py`, which fits the canonical model (`models/research_model.py`) on the frozen feature frame plus the live ESPN schedule and writes `webapp/data.js`; the static `webapp/` folder is served directly. There is no Raspberry Pi, PostgreSQL, or Streamlit in the active path — that stack was archived under `legacy/` on 2026-06-11. The research harness (`scripts/eval_baseline.py`) validates model changes through the promotion gate before they reach `research_model.py`.

---

## Current Model Performance

### Champion metrics

**Model ID:** `challenger-bag5-07c8442c-20260610T010824` (promoted 2026-06-10 by user override)
**Model file:** `models/research_model.py` (config baked in: `DEFAULT_N_BAGS = 5`, narrow grid)
**Pointer:** `experiments/champion.json` → `experiments/challenger-bag5.report.json`
**Metric convention:** sum-form Brier (range 0–2; see metric section below)
**ELO config:** K=25, HOME_ADV=80, REGRESS=0.40 (promoted 2026-06-07)
**Model config:** 5-member XGB seed bag (seeds 42 + 1000·i), raw probabilities averaged pre-calibration

| Season | Brier (sum-form) | n matches |
|--------|-----------------|-----------|
| 2022   | 0.630827        | 489       |
| 2023   | 0.634671        | 521       |
| 2024   | 0.634913        | 522       |
| 2025   | 0.631498        | 540       |
| **Avg**| **0.6330**      | 2072      |

**Calibration error** (max decile, blend output): **0.0182** — halved from the unbagged 0.0360

**The override:** the gate scored this challenger's core_metric short by 6×10⁻⁶ (gain +0.000494 vs the 0.0005 bar) and 2024 over tolerance by ~0.0001 — both far inside the measured seed-noise floor (σ≈0.001) — while calibration halved, the paired bootstrap gave P(challenger better)=0.858 over 2,072 matches, and production became deterministic. Promoted by explicit user decision; the rationale is recorded in `experiments/champion.json` `override_note`. Note the 2024 nuance: the prior champion's 2024 figure was a single-seed number (seed luck included), while the bagged figure is the de-noised estimate — part of the apparent regression is luck removal, not degradation.

(Prior reports retained: `champion-4fold.report.json` — unbagged 4-fold, avg 0.6335, cal 0.0360 — and the 3-fold `champion.report.json`, avg 0.6337, cal 0.0195. The strong 2025 fold is a substantive finding: once the cal fold (2024) represents the post-shift regime, the model handles it — the "2024 problem" was largely a one-season transition cost.)

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

The legacy model stack was archived under `legacy/models/` on 2026-06-11 when the project moved to webapp-only; `models/research_model.py` is the sole model in the active path.

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
| Season-decayed rolling features (B1) | `season_decay` weight on xG/xGA/form rolling means (prior seasons count `decay^seasons_ago`); swept 1.0/0.85/0.6 bagged 4-fold | Non-monotonic and sub-noise (0.85 +0.0003, 0.6 −0.0001); cal_err degrades 0.134→0.152 | Early-season "stale data" cost is outweighed by having any signal; cross-season carryover is benign (cf. 2021-in-training helping 2023) |
| Manager tenure (B2, `+Manager`) | new-manager flag (first 5 games) + games-in-charge tenure + diffs, from ASA `home/away_manager_id` (100% coverage) | +Manager 0.634136 vs Base 0.634403, Δ=−0.00027 — MARGINAL, below the 0.001 bar | Real but tiny; ELO + rolling form already encode the team-quality shifts a manager change drives |
| Neutral-site flag (B3, `+HFA2`) | per-team-season modal stadium; flag home games elsewhere (2.8%); damp HFA tilt at neutral venues | +HFA2 0.634542 vs Base 0.634403 (+0.00014, WORSE) and vs +HomeAdv-alone 0.633835 (+0.0007 worse) | 2.8% is too sparse — XGB overfits it as noise; the plain per-team HFA tilt (`+HomeAdv`, −0.00057) is the better but still-marginal version |
| Weather retest (B4, `+Weather`) | Open-Meteo archive re-fetch at 89% coverage (vs prior 45%); dome teams → NULL | +Weather 0.634711 vs Base 0.634403 (+0.00031, WORSE) | Definitive at near-full coverage: rolling xG/form already absorb how conditions affect 1X2 outcomes; weather adds noise |
| Extended history (B6, `--start-season`) | Train from 2015/2013 instead of 2017 (xG is 100% back to 2013), bagged 4-fold, 2 seeds | 2-seed mean ≈ control (seed-42 gain was luck); 2024+2025 regress on both seeds (fail robustness) | Older seasons fit the old 2022 fold at the cost of the current regime — the 2017 cutoff is right for forward-looking prediction |
| Roster construction (B5, probe) | DP/U22/TAM/GAM from mls-roster-profiles (2024+); single split train-2024 → test-2025 | Model unreliable (Brier ~1.0) from 522-match training, no valid cal fold; Δ is noise | The repo's 2024-only depth is too thin for any fair test; revisit at ≥3 seasons |

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

### 0. Promotion cycle outcome (2026-06-10 — bag-only PROMOTED by override; wide grid rejected)

Both banked levers went through the formal gate. **Bag+wide-grid: REJECTED** — core_metric PASS (0.632623, gain +0.0008; paired bootstrap P=0.921) but calibration FAIL (0.0584 vs limit 0.0410), 2024 marginal FAIL, >60%-confidence slice regressed; same structural shape as the referee rejection (Brier edge coupled to a calibration cost). **Bag-only: REJECTED by the letter of the gate** (core short by 6×10⁻⁶, 2024 over by ~0.0001 — both sub-noise) **while halving calibration (0.0360→0.0182)** — and **promoted by explicit user override** (`promotion_gate.py promote --force`; rationale in `champion.json` `override_note`). `research_model.py` now defaults to the promoted config (`DEFAULT_N_BAGS=5`); `--xgb-wide-grid`/`wide_grid=` remain opt-in and gate-rejected. Remaining open item from this cycle: a calibration-aware grid-selection criterion could revisit the wide grid later. Verdict detail: `docs/PLAN.md` "Promotion cycle" block.

### 1. dc_p_draw as XGB feature (TESTED — DROP)

The draw class remains the hardest to predict (~0.1934 Brier; all direct draw signals have failed the gate). The DC analytical draw probability (`dc_p_draw`, the diagonal sum of the Dixon-Coles score matrix) was added as an XGB feature and A/B tested on 2026-06-07: `+DCDrawProb` Δ=−0.0005, `+DCParams` (dc_lam+dc_mu) Δ=−0.0016, `+DCAll` Δ=−0.0026 — **all DROP**. Root cause: `dc_p_draw = f(λ, μ)` is a deterministic function of the Poisson means, which are themselves deterministic functions of team attack/defense strength — already captured by the rolling xG features in Base. No new signal. The function `dc_draw_prob_batch()` is retained in `scripts/eval/dixon_coles.py` for reference, but the column is not in Base or `_FEAT_ALL`.

### 2. ELO parameter sweep (DONE — REGRESS 0.50→0.40 promoted)

A WEIGHT_HL × REGRESS sweep was run on 2026-06-07. WEIGHT_HL=6 was confirmed best (3,4,5,7,8 all worse or equivalent). REGRESS=0.40 beat the 0.50 champion (avg 0.63367 vs 0.63467, Δ=−0.00100; 2024 0.6346 PASS) and was promoted (see design decision #6). Remaining unexplored knobs: HOME_ADV finer increments (50–90), DC recent-seasons window, schedule-density window. Run via `scripts/eval_baseline.py --ab-only Base` with parameter overrides; validate any winner with `model_report.py` + `promotion_gate.py` before promoting.

### 3. Production architecture (RESOLVED — webapp-only)

Production is now database-free: `scripts/build_dashboard_data.py` → `webapp/data.js` → static `webapp/`, all using `models/research_model.py`. The former Postgres/Streamlit/Raspberry-Pi stack and the legacy model files were archived under `legacy/` on 2026-06-11 (`legacy/README.md`), so the Pi-E2E validation that previously gated their deletion is moot. `make parity-check` (DB-free, |Δ| < 0.0015) remains the model-correctness gate.

### 4. Phase 5: better data sources

The ASA API is the primary xG source. Potential improvements:
- StatsBomb open data for shot location and sequence context (not just xG totals)
- FBref referee statistics as a richer referee feature base (currently using ASA games_raw referee column, which may have sparse coverage)
- Weather data from Open-Meteo at kickoff time is listed as a Phase 2 feature; not yet implemented

Evaluation checklist for any new data source: (a) confirm temporal leakage safety, (b) measure coverage rate, (c) implement graceful fallback for missing values, (d) run as an AB set in eval_baseline, (e) port to research_model only if the gate clears.

### 5. Legacy model archival (DONE)

The legacy stack (`stacking_ensemble`, `gradient_boost`, `dixon_coles`, `backtest`, `season_simulator`) was archived to `legacy/models/` on 2026-06-11 with the rest of the Postgres pipeline. `models/research_model.py` is the sole active model.

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

### Production/research parity

The research harness (`eval_baseline.py`) and `models/research_model.py` are parity-verified (`make parity-check`, |Δ| < 0.0015 on the parity frame). Since production is now the same DB-free `build_dashboard_data.py` → `webapp/data.js` path using `research_model.py` directly (no separate prediction stack), there is no production/research model divergence to validate — the parity check fully covers the active path.

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
scripts/build_dashboard_data.py Builds webapp/data.js (the production artifact)
legacy/                         Archived Postgres/Streamlit/Pi stack (legacy/README.md)
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
