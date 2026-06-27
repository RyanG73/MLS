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
- Test seasons: 2022–2025 (2022 evaluates with the 2021 cal fold; 2025 added 2026-06-09 once the
  season completed — 540 matches, cal fold 2024)
- 2026 in-progress: used for training only, never in test window
- ELO: K=25, HOME_ADV=80, REGRESS=40% (promoted 2026-06-07; synergistic with whl=6)
- DC decay: 120-day half-life
- XGB feature windows: xG and form over (3, 5, 10, 15) matches (all four; eval harness default)
- Edge threshold: 8% before live betting

**Validated metrics (2026-06-10 champion: 5-member XGB seed bag, promoted by user override):**

| Season | Brier (sum-form) |
|--------|-----------------|
| 2022   | 0.6308          |
| 2023   | 0.6347          |
| 2024   | 0.6349          |
| 2025   | 0.6315          |
| **Avg**| **0.6330**      |

Cal error (model_report, post-2nd-pass): **0.0182** (halved from 0.0360)
Champion pointer: `experiments/champion.json` → `challenger-bag5.report.json`
(`model_config: n_bags=5, wide_grid=false`; per-match Brier vectors included).
**Override note:** the gate scored core_metric short by 6e-6 and 2024 over tolerance by
~0.0001 — both far inside seed noise (σ≈0.001) — while calibration halved and production
became deterministic; promoted by explicit user decision (see champion.json override_note).
`models/research_model.py` defaults now bake the config in (`DEFAULT_N_BAGS = 5`).
Prior reports retained: `champion-4fold.report.json` (unbagged 4-fold, avg 0.6335,
cal 0.0360) and `champion.report.json` (3-fold 2026-06-07, avg 0.6337, cal 0.0195).

Previous champion (regress=0.50): avg 0.6347, cal_err 0.0306.
Previous baseline before calibration fix: avg 0.6381, cal_err 0.1567.

---

## Metric Convention

**Canonical: sum-form Brier** — `sum((p - y)^2)` over 3 classes, no division.
- Range: 0–2; uniform random baseline ≈ 0.6406; naive (always-home) ≈ 0.6667
- All research history, CLAUDE.md decisions, and `models/metrics.py` use this form
- Function: `brier_multiclass_sum(probs, y)` in `models/metrics.py`

**Display-only: half-form Brier** — sum-form ÷ 2 (range 0–1; random ≈ 0.250). Only
the archived Streamlit pages used this; the active webapp shows sum-form. Do not
compare half-form values directly with research Brier.

---

## Production Path (webapp-only)

| What | Path | Model |
|------|------|-------|
| Static web dashboard | `scripts/build_dashboard_data.py` → `webapp/data.js` → `webapp/` | `models/research_model` |

The single active path is database-free: the Mac runs `build_dashboard_data.py`
to render `webapp/data.js`, and `webapp/index.html` is served statically. The
former Postgres/Streamlit pipeline and the legacy model stack
(`dixon_coles`/`gradient_boost`/`stacking_ensemble`) were archived under
`legacy/` on 2026-06-11 (see `legacy/README.md`).

---

## Data Sources

| Source | What it provides | Notes |
|--------|-----------------|-------|
| ASA API (`itscalledsoccer`) | xG, possession, pass stats, referee | Primary features; SSL verify scoped to ASA client only (F6 fixed) |
| ESPN scoreboard | Results, fixtures, injuries | Schedule sync |
| The Odds API (Pinnacle) | Opening lines | Logged to `data/odds_log.parquet` via `data_pipeline/odds_log.py`; CLV-only — model stays market-blind |
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

- **Python:** 3.13 (pinned in `.python-version`; venv runs 3.13.1).
- **Dependency files:**
  - `requirements.txt` — active build/model only (lower + upper bounds).
  - `requirements-dev.txt` — test runners + research tools; includes `-r requirements.txt`.
  - `requirements-legacy.txt` — archived Pi/Postgres/Streamlit stack; includes `-r requirements.txt`.
- **Install:**
  ```bash
  make install        # active build deps only
  make install-dev    # active + test/research deps
  make install-editable  # once per checkout: make scripts/, data_pipeline/, models/ importable
  ```
- **Lockfile:** `requirements.lock` is environment-specific — regenerate on the target machine:
  ```bash
  make lock                          # pip freeze > requirements.lock
  pip install -r requirements.lock   # reproducible install
  ```

---

## Run Commands

```bash
make build-dashboard-data   # rebuild webapp/data.js (the production artifact)
make parity-check           # research_model reproduces the champion (|Δ| < 0.0015)
make test                   # DB-free unit suite
make odds-log               # append Pinnacle opening lines to data/odds_log.parquet
```

---

## Legacy / Archived (under legacy/, not in the active path)

- `legacy/models/{dixon_coles,gradient_boost,stacking_ensemble,backtest,season_simulator}.py` — old model stack, superseded by `models/research_model.py`
- `legacy/dashboard/` — Streamlit multi-page app, superseded by `webapp/`
- `legacy/data_pipeline/`, `legacy/features/`, `legacy/market/`, `legacy/scripts/` — Postgres-backed ingest, feature builders, betting layer, and ops/cron scripts
- `docs/PLAN.md` — historical plan; deep-history sections describe the archived Postgres/Pi architecture
