# MLS Prediction System — Current State

Last updated: 2026-06-27

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

> **Calibration method validated 2026-06-28:** a full sweep of all 6 `--calibration`
> methods (platt, isotonic, beta, temp_then_platt, temp_then_isotonic vs temperature)
> confirmed temperature is best — every alternative regressed Brier by +0.0026 to
> +0.0063 (≥13× the noise floor). Platt/beta improve decile calibration but at a real
> Brier cost. See `docs/feature-hunt-log.md` 2026-06-28.

**Cross-tier seeding (European leagues — bidirectional as of 2026-06-29):**
- Replaces the flat 15th-pct attack / 85th-pct defense prior with tier-bridge seeding from actual cross-tier ELO, in BOTH directions.
- `scripts/eval/tier_bridge.py` fits one ELO offset δ per league pair per direction via LOSO (ridge-shrunk toward static priors), run with `python3 -m scripts.eval.tier_bridge`:
  - **Forward (tier2→tier1, promoted teams):** all 5 big-5 pairs — Championship→EPL, 2.Bundesliga→Bundesliga, Serie B→Serie A, **Segunda→La Liga, Ligue 2→Ligue 1**. Negative offsets (~−100 to −130).
  - **Reverse (tier1→tier2, relegated teams):** the 5 mirrors (e.g. EPL→Championship) from `_identify_relegations` + `_collect_relegated_matches`. Positive offsets (~+100 to +130). `coefficients.tier1_offset` reads the reverse key.
- `_elo_to_dc_params` (2026-06-28 cliff fix): smooth ELO→DC linear regression + 25th-pct soft floor — a promoted/relegated team below the target-tier ELO floor seeds as a relegation/promotion favourite, never snapped to worst/best-ever.
- 10 offsets stored in `experiments/tier2_offsets.json` (forward + reverse); static priors used as fallback. All LOSO-validated below the naive 0.6667 baseline.
- `build_league_data._TIER1_FOR_BUILD` + generalised `_get_tier_elo_map` drive the reverse seeding path when building a second-tier league in preseason.
- Second-tier dashboard leagues: Championship, League One, League Two, 2.Bundesliga, Serie B, **Segunda (SP2)**, **Ligue 2 (F2)** — football-data goals-only source.
- Power rankings gain a "UEFA Tier 2" group on the EPL=0 scale.

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

| What | Build script | Payload(s) | Model |
|------|------|------|-------|
| MLS dashboard | `scripts/build_dashboard_data.py` | `webapp/data/mls.js` | `models/research_model` |
| European / table leagues | `scripts/build_league_data.py` | `webapp/data/{epl,la-liga,…}.js` | `models/research_model` |
| Continental knockouts | `scripts/build_continental_data.py` | `webapp/data/{ucl,europa,…}.js` | bracket simulator |
| "Coming soon" stubs + registry | `scripts/fetch_league_teams.py` | placeholders + `webapp/leagues.js` | — |
| Contract validation | `scripts/validate_payloads.py` | (checks all `webapp/data/*.js`) | — |

The single active path is database-free: the Mac runs the build scripts to render
per-league payloads under `webapp/data/*.js`, and `webapp/index.html` is served statically. The
former Postgres/Streamlit pipeline and the legacy model stack
(`dixon_coles`/`gradient_boost`/`stacking_ensemble`) were archived under
`legacy/` on 2026-06-11 (see `legacy/README.md`).

---

## Route State Taxonomy

Every `webapp/data/*.js` payload carries a top-level **`status`** field that names
the route/view state. The webapp branches on this to decide which panels, tabs,
and copy are legal for a surface, and `scripts/validate_payloads.py` keys its
required-field checks off it. This distinguishes projections from priors, completed
results, and unavailable surfaces — so users never mistake a placeholder or stale
page for a live projection.

| `status` | Meaning | Produced by | Webapp framing |
|----------|---------|-------------|----------------|
| `live` | Current season in progress: played + upcoming matches | `build_dashboard_data.py` (MLS), `build_league_data.py` (in-progress) | Full projection UI: standings, match probs, sim, health |
| `preseason` | Schedule published, **no matches played yet** — projections are statistical **priors**, not live probabilities | `build_league_data.py` when `season_state == PRESEASON` | "pre-season projection" banner; cards labelled "preseason prior · no matches played"; health shows "no current rows" instead of `NaN%` |
| `completed` | Final results, **no projection framing** | `build_league_data.py` (concluded table league), `build_continental_data.py` (concluded knockout) | Result/standings view; champion shown; no edge/value affordances |
| `knockout_live` | Bracket or league phase active | `build_continental_data.py` (in-progress) | Bracket projection + current path |
| `placeholder` | Model/source not built for this league | `fetch_league_teams.py` | "coming soon" view; carries a human-readable **`reason`** string; team list shown for reference if available |

Notes:
- **`status` is distinct from `league.status`.** `league.status` (`live`/`soon`) drives
  the sidebar "soon" tag and the model-not-built branch; top-level `status` is the
  canonical route state. They will usually agree, but consumers should branch on
  top-level `status`.
- Power rankings (`power.js`) is a cross-league surface with `groups` and no `league`
  key; the webapp selects it via `?league=power` before the normal league render.
- `placeholder` payloads MUST include `reason` (why there are no projections). The
  webapp surfaces this string directly in the "coming soon" view.
- The state is derived from `scripts/eval/season_state.py` (`PRESEASON` /
  `IN_PROGRESS` / `CONCLUDED` / `BETWEEN`) for table leagues, so `status`,
  `in_season`, and `outlook.preseason` stay consistent within one payload.

---

## Model Card Fields

Non-placeholder payloads include a **`model_card`** object — a compact, human-readable
description of the model that produced the projections, surfaced in the dashboard's
model-health tab. It is informational (not consumed by the model); keep it in sync
with the champion config above.

| Field | Type | Meaning |
|-------|------|---------|
| `arch` | `string[]` | Ordered pipeline stages, e.g. `["Dixon-Coles", "Temperature", "XGBoost ×5 bag", "Capped-DC blend", "Temperature"]` |
| `config` | `object` | Headline hyperparameters: `ELO K`, `Home adv`, `Season regress`, `DC decay`, `XGB weight ½-life`, `Seed bag`, `xG / form windows` |
| `per_class` | `object` | Champion per-class Brier `{home, draw, away}` (from `champion.json` → report `overall`) |
| `n_test` | `int \| null` | Number of test matches in the champion report |

The MLS and table-league builds populate `model_card` from `experiments/champion.json`
→ the referenced report. If the champion report is unreadable, the build still emits
`arch` and `config` (static) and leaves `per_class`/`n_test` empty rather than failing.

Companion fields in the same payload:
- `model` — live headline metrics for this surface: `best_brier`, `naive`, `improve_pct`,
  `market`/`edge_pct` (where market history exists), `metric: "brier_sum_form"`.
- `in_season_brier` — running Brier over the current season's played matches.
- `health` — feature-family completeness/non-default over current-season rows
  (see `scripts/payload_utils.py:health_feature_stats`; preseason rows return
  `status: "no_rows"` rather than `NaN`).

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
python3 scripts/build_logo_map.py   # rebuild webapp/data/logos.js (global crest fallback; run after league data rebuilds)
```

### Market Evaluation & CLV

```bash
# Log opening lines before a match day (requires ODDS_API_KEY)
ODDS_API_KEY=<key> python -m data_pipeline.odds_log

# Log closing lines within 3 hours of kickoff
ODDS_API_KEY=<key> python -m data_pipeline.odds_log --closers

# Generate market evaluation report (European Big-5 + MLS) → experiments/market_eval.json
python -m scripts.market_eval

# Attach market_eval.json to a model report
python scripts/model_report.py --frame data/parity_frame.parquet --market-eval experiments/market_eval.json
```

**Key files:**
| File | Purpose |
|------|---------|
| `data_pipeline/market.py` | `devig()`, `edge_pct()`, `clv_pp()` math primitives |
| `data_pipeline/odds_log.py` | Pinnacle h2h fetcher; `log_openers()` / `log_closers()` |
| `scripts/market_eval.py` | Full report builder; importable `brier_vs_market()` / `roi_by_edge_bucket()` |
| `data/odds_log.parquet` | Forward-only opening lines (MLS, Pinnacle) |
| `data/odds_closers.parquet` | Near-kickoff closing lines (MLS, Pinnacle) |
| `experiments/market_eval.json` | Generated market evaluation report |

**European data source:** football-data.co.uk Pinnacle/market-average closing odds, pre-computed in `webapp/data/*.js` payloads — no separate fetch needed for historical seasons.

**MLS data:** forward-only from The Odds API. Historical Brier vs market comparison becomes meaningful once ~100+ fixtures accumulate in `odds_log.parquet`.

---

## Legacy / Archived (under legacy/, not in the active path)

- `legacy/models/{dixon_coles,gradient_boost,stacking_ensemble,backtest,season_simulator}.py` — old model stack, superseded by `models/research_model.py`
- `legacy/dashboard/` — Streamlit multi-page app, superseded by `webapp/`
- `legacy/data_pipeline/`, `legacy/features/`, `legacy/market/`, `legacy/scripts/` — Postgres-backed ingest, feature builders, betting layer, and ops/cron scripts
- `docs/PLAN.md` — historical plan; deep-history sections describe the archived Postgres/Pi architecture
