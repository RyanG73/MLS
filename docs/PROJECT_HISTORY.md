# MLS Prediction Dashboard — Project History

> Newcomer reference. Covers what this project is, how it evolved, and the key decisions that
> shaped it. For current model state and run commands, see `docs/CURRENT_STATE.md`. For what's
> in progress, see the active `docs/superpowers/plans/` file and the top of `docs/PLAN.md`.

---

## What this project is

A **market-blind probabilistic model** for soccer match outcomes (home win / draw / away win),
built to identify betting edges as the gap between model probability and market probability:

```
edge = model_prob − market_prob
```

The central constraint: **betting odds are never used as model features**. Using closing lines
in training would teach the model to replicate the market, collapsing `edge` to near-zero by
construction. Pinnacle lines are stored only for CLV (Closing Line Value) analysis after the
fact. The 8% threshold on edge is the live-betting gate.

The platform now covers **17 leagues + 5 continental competitions** — the multi-league
expansion happened between 2026-06-14 and 2026-06-17.

---

## Architecture evolution

### Original architecture (archived 2026-06-11)
- **Postgres DB** on a Mac → **Raspberry Pi 4** running scheduled ingest jobs → **Streamlit**
  multi-page dashboard (`legacy/dashboard/`)
- Model stack: `dixon_coles.py` + `gradient_boost.py` + `stacking_ensemble.py` (LR meta-learner)
- All archived to `legacy/` on 2026-06-11. `legacy/README.md` covers the full stack.

### Current architecture (webapp-only)
- A Mac runs `scripts/build_dashboard_data.py` → writes `webapp/data.js`
- `webapp/index.html` is served statically (no server, no DB)
- Research model: `models/research_model.py` (the sole active model)
- Research harness: `scripts/eval_baseline.py` + `scripts/eval/` modules
- Gate before production: `scripts/promotion_gate.py` (6 criteria)
- No Raspberry Pi, no Postgres, no Streamlit in the active path

---

## Model lineage

### Baseline (pre-2026-05-30)
Dixon-Coles + unconstrained LR stacking ensemble. avg Brier ≈ 0.6392. Cal error ≈ 0.146.

### Capped-DC convex blend (KEEP 2026-05-30)
Replaced the LR meta-learner with a scalar convex blend `w·XGB + (1-w)·DC`, w ∈ [0.7, 1.0],
fitted by Brier minimisation on the cal fold. Rationale: Dixon-Coles was catastrophically
bad in 2024 (Brier ~0.6523) because its static `home_adv` parameter overestimates home wins
after the 2024 HFA collapse. The 30% DC cap limits the damage while retaining DC's structural
Poisson priors for low-data teams. avg Brier 0.6392 → 0.6372.

### Weight_hl 4 → 6 (KEEP 2026-05-30, synergistic with capped blend)
XGB season-weight half-life increase was a DROP in isolation (earlier cycle) but a KEEP once
the DC cap was in place — the DC drag had been masking the gain. avg Brier 0.6372 → 0.6363.

### ELO REGRESS 0.50 → 0.40 (promoted 2026-06-07)
Swept WEIGHT_HL × REGRESS together (not independently — they interact). At whl=6, REGRESS=0.40
beats 0.50 by ~0.0010 avg Brier, sharpens calibration (0.0306→0.0195). At whl=4 the old
sweep, REGRESS=0.50 won — different operating point. K=25, HOME_ADV=80 were grid-locked first.

### Second-pass temperature scaling (fixes calibration bug)
The initial calibration applied temperature scaling to DC and XGB separately before blending.
The blended output was itself miscalibrated (cal_err 0.1326). Adding a second temperature pass
directly on the blend output brought cal_err down to 0.0306 (champion). Temperature won the
calibration sweep (vs Platt, isotonic, beta) because its single degree of freedom cannot
overfit the cal fold's class distribution — critical during 2024 regime shift.

### Seed bagging (KEEP 2026-06-09, verification protocol)
`--xgb-bag 5` averages 5 XGB seeds (42, 1042, 2042, 3042, 4042) pre-calibration. Collapses
run variance from σ≈0.001 to σ≈0.0002. Adopted as the standard verification protocol —
judgements near the 0.0005 gate bar require bagged runs. Wide-grid was gate-rejected on
calibration.

### Champion (promoted 2026-06-10 by user override)
- avg Brier **0.6330** (sum-form, 2022–2025 four-fold), cal_err **0.0182**
- Sub-noise gate shortfalls (6×10⁻⁶ core, ~0.0001 on 2024) while calibration halved
- `experiments/champion.json` → `experiments/challenger-bag5.report.json`
- Config baked into `models/research_model.py`: `DEFAULT_N_BAGS = 5`, narrow grid

---

## The 2024 regime shift

**Finding (diagnosed 2026-06-06 using `scripts/diagnose_2024.py`):** an outcome regime shift,
not a feature shift.

| Period | Home win rate |
|--------|--------------|
| 2017–2023 | ~0.51 |
| 2024 | 0.45 |
| 2025 | 0.443 (confirmed persistent) |

Feature distributions did NOT move (Jensen-Shannon divergence: train→2024 was *lower* than
train→2023). The model's inputs were on-distribution; the mapping from inputs to outcomes changed.

Dixon-Coles breaks because its `home_adv` is fit on 2017–2023 data (avg home rate ~0.51) and
cannot track a mid-stream collapse. XGB degrades far less because ELO and recent-form features
adapt within-season. The capped blend automatically down-weights DC to w_xgb=0.70 (maximum)
in 2024, and is the correct structural response — not a patch.

**What was tried and failed:**
- Per-class (vector) calibration: helps 2023 (+0.0045) but catastrophically regresses 2024
  (−0.0135). Extra calibration degrees of freedom overfit the 2023 cal-fold class priors and
  amplify the home→away shift when the regime flips. This hard trilemma applies to referee
  features too — the draw-rate gain is real but cannot be released while the regime shift persists.
- Shorter DC `recent_seasons` window (2/3/4/5): 2024 Brier identical to 4 decimals across all
  windows. The blend already floors DC at w_xgb=0.70 in 2024; DC's fit window has no leverage.
- ELO HOME_ADV re-sweep on 2024–2025 specifically: deferred (lower expected value).

---

## What has been tried and doesn't work

The following features were formally tested through the promotion gate and rejected:

| Feature/Approach | Key finding |
|-----------------|-------------|
| Referee draw rate (`ref_draw_rate`) | Real Brier gain (+0.0010) but FAILS calibration gate — hard trilemma proven across 14 calibration variants |
| Referee hw-rate only (`ref_hw_rate`) | The gain lives in `ref_draw_rate`, not `ref_hw_rate`; fails both core metric and 2024 robustness |
| Detrended referee (`ref_draw_rate_rel`) | Detrending removes the very component that carries the gain; edge and calibration fragility are the same signal |
| Per-class (vector) calibration | −0.0135 on 2024; root cause: 2024 regime shift (see above) |
| DC draw probability as XGB feature | Deterministic function of λ/μ, which are deterministic functions of rolling xG — no new signal |
| Standings features | Collinear with ELO; season points are a noisy proxy for what ELO already encodes |
| H2H draw rate | Too sparse — MLS teams typically meet 3–6 times; insufficient to estimate stable draw propensity |
| Manager tenure (`+Manager`) | Real but tiny (Δ=−0.00027); ELO + rolling form already encode the quality shifts a manager change drives |
| Neutral-site flag (`+HFA2`) | 2.8% is too sparse — XGB overfits it as noise |
| Weather (`+Weather`, 89% coverage) | Definitive DROP at near-full coverage: rolling xG/form already absorb conditions |
| Extended training history (2015/2013) | Older seasons fit the old 2022 fold at the cost of the current regime; 2017 cutoff is right |
| Season-decayed rolling features | Non-monotonic and sub-noise; cross-season carryover is benign (cf. 2021 retention) |
| Roster construction (2024+ only) | Data-limited single-split; model unreliable at 522-match training depth |
| Dynamic per-season model selection | Anti-predictive: cal-fold signal consistently picks the wrong model for the test season |
| LightGBM bag members | Untuned members dilute the bag (+0.0021 Brier) |
| Train-on-cal refit | Cal-season holdout is load-bearing, not waste |
| DC-through-cal | Same lesson as train-on-cal |
| In-season scalar recalibration | Scalar T cannot move class priors |
| Wide XGB grid | Brier win coupled to calibration regression — gate-rejected; same pattern as referee feature |

**Structural conclusion:** the model is at its pre-match-feature ceiling. ELO + rolling xG/form
already absorb team quality, home advantage, manager effects, conditions, and roster investment.
The frontier is the betting/CLV workstream (edge against the market).

---

## Multi-league and continental expansion

### League expansion (2026-06-14)
The MLS champion pipeline (ELO + DC + bagged XGB + capped-DC blend + temperature) transfers
to European football with zero model branching — validated on big-5 walk-forward 2022–2025:

| League | avg Brier | vs naive |
|--------|-----------|---------|
| La Liga | 0.5863 | +8.5% |
| EPL | 0.5890 | +8.8% |
| Bundesliga | 0.5934 | +8.7% |
| Serie A | 0.5946 | +9.7% |
| Ligue 1 | 0.6035 | +6.8% |
| *MLS (ref)* | *0.6330* | *+1.2%* |

European leagues carry far more capturable signal (lower parity). Data sources: Understat
(big-5 xG, 2014+), ESPN scoreboard (Liga MX), football-data.co.uk (European 2nd-tier
goals-only + market odds).

The model trails Pinnacle by ~2% Brier — strong for a market-blind model. The value/edge
backtest (8% threshold, fair de-vigged odds) shows apparent edges but they don't clear the bar
vs. Pinnacle's sharp line — honest and expected.

### Continental competitions (2026-06-17)
The cross-league strength problem: a UCL tie pits teams from different leagues whose domestic
ELOs are each anchored to 1500 independently and so aren't comparable.

**Solution (Approach A):** common ELO-point cross-league scale. Modeled big-5 teams = domestic
ELO + per-league UEFA-coefficient offset. Unmodeled entrants = UEFA club coefficient mapped to
the same scale. `scripts/eval/cross_league.team_strength()` is the seam where a future
bridge-regression (Approach C) drops in.

**Approach C (implemented 2026-06-19, honest null):** fitted per-league ELO offsets from
continental results via ridge regression toward coefficient priors. UEFA: offsets barely moved
from priors (max 0.5 ELO points), adopted. Concacaf: rejected (4/10 seeds, small-sample
constraint — n=51 CC matches is the binding limit). UEFA 5-yr coefficient priors are already
optimal; historical-ELO-as-of-date is the next potential lever.

**Five active comps:** UCL, Europa, Conference (UEFA), Concacaf Champions Cup (pure-knockout),
Leagues Cup (two-table group, no draws/PK). Each has a different `bracket_sim` path.

**Known limits:** Concacaf trails naive (structural small-sample bound); no continental odds
source (football-data.co.uk is domestic-only); Europa/Conference modeled coverage is low (~28%
and ~11%) because most entrants are non-big-5 leagues.

---

## Improvement campaign summary (2026-05-29 through 2026-06-10)

The multi-agent parallel improvement loop ran across ~15+ iterations across multiple cycles.
Key scoreboard:

| Cycle | Net change | Source |
|-------|-----------|--------|
| 2026-05-30 (parallel) | 0.6392 → 0.6363 | capped-DC blend + whl=6 |
| 2026-05-30 (overnight) | 0.6363 → 0.6375 | +MargCore (soft KEEP, 2023 only) |
| Phase 11 / 2026-05-31 | 0.6363 → 0.6344 | +Availability (ESPN roster g+ share) |
| 2026-06-07 (ELO grid) | → 0.6337 (3-fold) | REGRESS=0.40, second-pass cal fix |
| 2026-06-09 (13-iter) | bagging adopted | seed noise floor confirmed σ≈0.001 |
| 2026-06-10 (promotion) | 0.6330 (4-fold) | bag-only promoted by override |

Note: the Phase 11 Availability KEEP (+0.0011) used a preliminary harness state and the
2021-excluded config; after 2021 was re-validated and REGRESS moved to 0.40, the champion
was rebuilt on a clean 4-fold basis. The champion's 0.6330 is the authoritative number.

---

## Permanent constraints (do not re-litigate without explicit instruction)

See `CLAUDE.md` for the full decision list with dates. Key ones with rationale:

- **Market-blind model:** using closing lines in training collapses `model_prob - market_prob`
  to zero. Odds are CLV-only, never features.
- **2020 excluded, 2021 retained:** COVID bubble (no crowds, no real HFA). 2021 A/B-validated:
  removing it costs +0.0019 avg Brier (mostly 2023, where 2021 is the most recent training season).
- **Test seasons 2022–2025:** 2025 added 2026-06-09 once the season completed (540 matches).
  2026 is training-only; never in the test window while in-progress.
- **4-fold reports for gate candidates:** challengers must use the same 4-fold basis
  (`model_report.py` defaults). 3-fold reports are not comparable.
- **Verification protocol:** judge harness experiments on a single `--xgb-bag 5 --seed 42`
  run (σ≈0.0002), confirm gate-bound claims at a second base seed.
- **Edge threshold 8%:** established across all leagues (MLS + European).
