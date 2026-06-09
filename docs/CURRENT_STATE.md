# MLS Prediction System — Current State

Last updated: 2026-06-07

This document is the single source of truth for the canonical model, metric
definitions, data sources, and run commands. Update it when any of these change.

---

## Canonical Model

**File:** `models/research_model.py`

**Pipeline:**
1. Dixon-Coles with 120-day time-decay half-life, fitted on pre-cal-season historical data
2. Season-weighted XGBoost multiclass (weight half-life = 6 seasons), inner 12-combo grid
3. Temperature calibration applied to both DC and XGB outputs on the cal fold
4. Capped-DC convex blend: `w * XGB + (1-w) * DC`, w ∈ [0.7, 1.0], fitted by Brier minimisation on cal fold
5. Second-pass temperature calibration on the blend output (fixes the pre-blend calibration bug that caused cal_err=0.1326)

**Walk-forward evaluation config:**
- Train data: 2017+, 2020 excluded (COVID bubble); 2021 retained in training + as 2022 cal fold (A/B-validated 2026-06-09: excluding it costs +0.0019 Brier)
- Test seasons: 2022–2024 (2022 skips COVID cal fold)
- 2025 in-progress: used for training only, never in test window
- ELO: K=25, HOME_ADV=80, REGRESS=40% (promoted 2026-06-07; synergistic with whl=6)
- DC decay: 120-day half-life
- XGB feature windows: xG and form over (3, 5, 10, 15) matches (all four; eval harness default)
- Edge threshold: 8% before live betting

**Validated metrics (2026-06-07, seed=42, regress=0.40):**

| Season | Brier (sum-form) |
|--------|-----------------|
| 2022   | 0.6305          |
| 2023   | 0.6359          |
| 2024   | 0.6346          |
| **Avg**| **0.6337**      |

Cal error (model_report, post-2nd-pass): 0.0195

Previous champion (regress=0.50): avg 0.6347, cal_err 0.0306.
Previous baseline before calibration fix: avg 0.6381, cal_err 0.1567.

---

## Metric Convention

**Canonical: sum-form Brier** — `sum((p - y)^2)` over 3 classes, no division.
- Range: 0–2; uniform random baseline ≈ 0.6406; naive (always-home) ≈ 0.6667
- All research history, CLAUDE.md decisions, and `models/metrics.py` use this form
- Function: `brier_multiclass_sum(probs, y)` in `models/metrics.py`

**Display-only: half-form Brier** — sum-form ÷ 2.
- Range: 0–1; random baseline ≈ 0.250
- Used in: `dashboard/pages/2_Performance.py`, `scripts/check_drift.py`, `scripts/performance_report.py`
- Labeled explicitly in those files; do not compare directly with research Brier values

When you see "Brier 0.25" in the Streamlit dashboard and "Brier 0.6375" in eval output,
these are the **same metric measured in different conventions** (÷2 vs no-division).

---

## Production Paths

| What | Path | Model |
|------|------|-------|
| Operational Postgres predictions | `scripts/daily_update.py` → step 10 | `models/research_model.predict_upcoming` |
| Public dashboard | `scripts/build_dashboard_data.py` → `webapp/data.js` | `models/research_model` |

Both paths use the same model. The legacy stack (`models/dixon_coles.py`,
`models/gradient_boost.py`, `models/stacking_ensemble.py`) runs for component
predictions only and is not the source of the `ensemble` model in Postgres.

---

## Data Sources

| Source | What it provides | Notes |
|--------|-----------------|-------|
| ASA API (`itscalledsoccer`) | xG, possession, pass stats, referee | Primary features; SSL verify scoped to ASA client only (F6 fixed) |
| ESPN scoreboard | Results, fixtures, injuries | Schedule sync |
| The Odds API (Pinnacle) | Opening + closing lines | CLV only — model stays market-blind |
| FBref / worldfootballR | Referee statistics | Optional refresh |
| Open-Meteo | Weather at kickoff | Phase 2 feature |

**Market-blind constraint:** Betting odds must never be used as model features.
Training on closing lines would collapse the `model_prob − market_prob` edge.
Odds remain CLV-only inputs (used after prediction, not before).

---

## Config (config/settings.yaml)

Validated values that must match CLAUDE.md:

| Parameter | Value | Notes |
|-----------|-------|-------|
| `elo.k_factor` | 25 | Grid winner 2026 |
| `elo.home_advantage_elo` | 80 | Grid winner 2026 |
| `elo.season_regression_pct` | 0.40 | Promoted 2026-06-07 (synergistic with whl=6) |
| `dixon_coles.time_decay_half_life_days` | 120 | Grid winner 2026 |
| `features.xg_windows` | [3, 5, 10, 15] | All four in champion feat_base (parity_frame.meta.json) |
| `features.form_windows` | [3, 5, 10, 15] | All four in champion feat_base |
| `market.default_edge_threshold_pct` | 8.0 | CLAUDE.md: 8% before live betting |

---

## Dependencies & Reproducibility (F7)

- **Python:** 3.11 (pinned in `.python-version`).
- **Spec:** `requirements.txt` — lower bounds (minimum tested) + upper bounds
  (next major) to stop a silent breaking upgrade.
- **Lockfile:** `requirements.lock` is environment-specific and generated on the
  deploy target (the Pi), not committed from a dev machine:
  ```bash
  make lock                          # pip freeze > requirements.lock (on the Pi)
  pip install -r requirements.lock   # reproducible install
  ```
  The dev research-harness env runs newer scientific libs than the Pi, so
  freezing it would pin wrong versions — hence target-side generation.

---

## Run Commands

```bash
# Run daily update (fits model, writes predictions to Postgres)
make daily-update

# Rebuild the web dashboard data file
make build-dashboard-data

# Verify research_model parity with eval harness (|Δ| < 0.0015)
make parity-check

# Run the test suite
make test

# Print performance metrics from Postgres
make performance-report
```

---

## Legacy / Not Canonical

- `models/dixon_coles.py` — old DC wrapper; still runs for component predictions
- `models/gradient_boost.py` — old GB wrapper; still runs for component predictions
- `models/stacking_ensemble.py` — old meta-learner; no longer source of `ensemble` predictions
- `dashboard/pages/6_Backtest.py`, `7_Season_Forecast.py`, `8_Real_Bets.py` — beta, gated behind `dashboard.beta_pages_enabled`
- `docs/PLAN.md` — historical plan; may reference DuckDB (superseded by PostgreSQL)
