# Code Walkthrough — MLS Prediction Model

> Written for the project owner who wants to read the code with their own eyes,
> verify the key decisions are implemented as documented, and spot anything that
> looks wrong. Not a developer tutorial — a guided inspection.

---

## 1. The 30-second orientation

```
MLS/
├── scripts/
│   ├── eval_baseline.py          ← THE research harness (~2 500 lines, top-to-bottom script)
│   ├── eval/                     ← Pure-function modules extracted from eval_baseline
│   │   ├── elo.py
│   │   ├── dixon_coles.py
│   │   ├── calibration.py
│   │   ├── feature_builders.py
│   │   └── feature_registry.py
│   ├── model_report.py           ← Produces the JSON report consumed by the gate
│   └── promotion_gate.py         ← Champion/challenger decision logic
├── models/
│   ├── research_model.py         ← Production model (identical math to eval_baseline)
│   └── metrics.py                ← Canonical Brier (sum-form) and log-loss
├── data/
│   ├── parity_frame.parquet      ← Frozen feature matrix used for parity / reporting
│   └── parity_frame.meta.json    ← Feature list, hyperparams that built it
├── experiments/
│   ├── champion.report.json      ← Current champion metrics
│   └── champion.json             ← Pointer to the champion report
└── config/
    └── settings.yaml             ← Authoritative config values
```

**The 5 files that matter most:**

| File | What it is |
|------|-----------|
| `scripts/eval_baseline.py` | Research harness. Run it to reproduce every published metric. The truth-source for model logic. |
| `models/research_model.py` | Production copy of the same math. Used by `daily_update.py` and `model_report.py`. |
| `scripts/eval/` (the package) | Pure-function building blocks extracted from eval_baseline. Unit-testable; eval_baseline delegates to them. |
| `experiments/champion.report.json` | The live performance record. Every number here should match `docs/CURRENT_STATE.md`. |
| `data/parity_frame.meta.json` | Declares exactly which features and hyperparameters the production model was built with. |

**How they connect:**

```
eval_baseline.py ──imports──► scripts/eval/{elo,dixon_coles,calibration,feature_builders,feature_registry}.py
research_model.py ──(same math, no API calls)──► predict_upcoming() used by daily_update.py
model_report.py ──uses──► research_model.walk_forward_predictions() + data/parity_frame.parquet
promotion_gate.py ──reads──► experiments/*.report.json
```

The flow is: research → validated → ported to `research_model.py` → reported via `model_report.py` → gate via `promotion_gate.py`.

---

## 2. Following a prediction end-to-end

### Step 1 — Raw data (eval_baseline.py, lines ~212–306)

**What happens:** The ASA API is called via `itscalledsoccer`. Two endpoints are used: `get_games` (scores, schedule, stage) and `get_game_xgoals` (xG per match). A third call `get_game_xpass` (PPDA, possession) is attempted and gracefully skipped if unavailable.

**Key decisions baked in here:**
- `df = df[(df["season"] >= 2017) & (~df["season"].isin(_COVID))]` — keeps 2017+, drops 2020 only (`_COVID = {2020}`; 2021 retention A/B-validated 2026-06-09).
- Label encoding: 0 = home win, 1 = draw, 2 = away win (`label_result`).
- `is_playoff` is detected from the `stage_name` / `competition_round` column if present; defaults to 0 otherwise.

**What to look for:** The print line at ~line 279 reports how many matches were loaded and how many were excluded as pre-2017/COVID. A normal run shows roughly 2 800–3 200 matches retained. xG coverage should be 95%+.

**What would look wrong:** xG coverage below 80% means the ASA `get_game_xgoals` call partially failed. 2020 appearing in the retained data means the exclusion filter broke (2021 is intentionally retained as of 2026-06-09).

---

### Step 2 — ELO ratings (eval_baseline.py, lines ~344–374 / scripts/eval/elo.py)

**What happens:** A grid search over K ∈ {20, 25, 30} × HOME_ADV ∈ {80, 100, 120} picks the best (K, HOME_ADV) pair on a 2019 validation season. `compute_elo()` then walks forward across all matches in date order, applying 40% season regression at each new season.

**Key function:** `compute_elo(df, K, home_adv, regress=0.40, initial=1500.0)` in `scripts/eval/elo.py`.

**What to look for:** The print line reports `Best: K=25, HOME_ADV=80`. If the grid search finds a different winner, check whether the `--elo-k` or `--elo-home-adv` flags were passed.

**What would look wrong:** `REGRESS` defaults to 0.40 at line 163 of eval_baseline.py (promoted 2026-06-07, synergistic with whl=6). The season-regression line in `elo.py` is: `elo = {t: initial + (r - initial) * (1 - regress) for t, r in elo.items()}`. With `regress=0.40` this pulls each team 40% of the way back to 1500 each season. (Note: an earlier 2026-05-30 sweep at whl=4 favoured 0.50 — the interaction with whl matters; they must be swept together.)

---

### Step 3 — Rolling features (scripts/eval/feature_builders.py)

**What happens:** `add_rolling_features()` walks every match in chronological order and, for each team, maintains running lists of xG, goals, form points, PPDA, possession, and match dates. At match time it slices the last W matches and computes rolling averages. All features are pre-match — no future data leaks in.

**Key function signature:**
```python
add_rolling_features(
    df,
    xg_windows=(3, 5, 10, 15),
    form_windows=(3, 5, 10, 15),
    games_14d_days=16,
    xpass_by_game,
    has_ppda=False,
    has_poss=False,
    has_sp_xg=False,
)
```

**Feature columns produced** (for each window W): `home_xg_roll_W`, `home_xga_roll_W`, `home_form_W`, `away_*` variants, `home_games_in_14d`, `home_days_rest`. Plus derived: `xg_diff`, `home_xg_sum`, `form_diff`.

**What to look for:** The print line around eval_baseline line 401 shows the first 8 rolling column names. The presence of `home_xg_roll_15` confirms the 4-window config is active.

**What would look wrong:** A feature column that is all zeros or all the same value (NaN-fill issue). A rolling window wider than the available history uses whatever history exists (a 15-window with 3 prior matches averages those 3); a team with no history at all gets league-typical priors (xG/xGA → 1.3, form → 1.0 ppg), not zeros. The model-side `fillna(0)` only covers auxiliary features whose neutral value is genuinely 0 (e.g., gk_z z-scores).

---

### Step 4 — Dixon-Coles (scripts/eval/dixon_coles.py / models/research_model.py)

**What happens:** For each test season `ts`, `fit_dc(train, decay_hl=120)` fits a Poisson goal model with the Dixon-Coles low-score correction (the `tau` factor adjusts 0-0, 0-1, 1-0, 1-1 scorelines). Time-decay weighting: matches `d` days before the reference date receive weight `exp(-log(2)/120 * d)`, so a match 120 days ago counts half as much as a match today.

**Key functions:**
- `dc_nll()` — the objective being minimised (negative log-likelihood with decay)
- `fit_dc()` — L-BFGS-B optimiser, returns `(atk, dfd, ha, rho)` dicts
- `dc_predict()` — builds an 8×8 score matrix, sums triangles for P(H), P(D), P(A)

**Parameters fixed by optimisation:** `ha` (home advantage in log-lambda space, bounded 0–1), `rho` (correction magnitude, bounded −0.5–0).

**What to look for:** `DEFAULT_DC_DECAY_HL = 120` in both `scripts/eval/dixon_coles.py` (line 20) and `models/research_model.py` (line 29). The `recent_seasons=4` parameter in `fit_dc` limits fitting to the last 4 seasons of the training window.

---

### Step 5 — XGBoost with season weights (models/research_model.py)

**What happens:** `fit_xgb()` builds multiclass XGBoost models (softprob, 3 classes). An inner grid over `max_depth ∈ {3,4,5}`, `n_estimators ∈ {200,400}`, `learning_rate ∈ {0.05,0.10}` (12 combinations; 48 with `wide_grid=True`, which adds `min_child_weight ∈ {1,5}` × `reg_lambda ∈ {1,5}`) is evaluated on the last 2 seasons of the training window. Sample weights decay exponentially by season: `exp(-log(2)/6 * (ref_season - s))` so a season 6 years old counts half as much. With `n_bags=N`, N models are fitted at seeds `seed + 1000·i` and `bag_proba()` averages their raw probabilities before calibration (variance reduction, harness-validated 2026-06-09). `fit_xgb` returns `(clfs_list, best_params)` — always use `bag_proba(clfs, X)` for predictions. Since the 2026-06-10 promotion, `n_bags` defaults to `DEFAULT_N_BAGS = 5` (the champion config) at every level including `fit_xgb` itself, so all callers — `predict_upcoming`, `build_dashboard_data.py`, the probes — inherit it; pass `n_bags=1` to reproduce the pre-bagging model.

**What to look for:** `subsample=0.8, colsample_bytree=0.8` are fixed. The inner grid winner varies by fold — you will see it printed as `XGB-grid(d=4,n=200,lr=0.05)` or similar.

---

### Step 6 — Calibration and blend (models/research_model.py, lines ~108–179)

**What happens (in order):**

1. Temperature scaling is applied to DC output: fit `T` on the cal fold, apply to the test fold.
2. Temperature scaling is applied to XGB output: same pattern.
3. `fit_capped_blend()` fits a scalar `w ∈ [0.7, 1.0]` on the cal fold by Brier minimisation: `blend = w * XGB + (1-w) * DC`. DC contributes at most 30%.
4. **Second-pass temperature scaling** is applied to the blend output — fit on the cal-fold blend, applied to the test-fold blend. This is the fix for the previous `cal_err=0.1326` bug.

**The blend math (verbatim from research_model.py, line 177):**
```python
def blend(xg, dc, w):
    b = w * xg + (1.0 - w) * dc
    return b / b.sum(axis=1, keepdims=True).clip(1e-9, None)
```

**What to look for:** The champion report shows `w_xgb` per season: `{"2022": 0.7, "2023": 0.93, "2024": 0.7, "2025": 0.871}` (bag-5 champion, 2026-06-10). Values at or near 0.7 mean DC got its maximum allowed 30% weight. Values near 1.0 mean XGB dominated.

**What would look wrong:** `w_xgb` outside [0.7, 1.0] — this is clamped by the bounds and should never happen. A second-pass cal_err well above 0.05 (current champion: 0.0182 max-decile) would indicate the temperature fix is not working.

---

### Step 7 — The champion gate

After a run produces a report, `scripts/promotion_gate.py evaluate --challenger new.report.json` checks the new report against the champion. If all 6 criteria pass, `promote` writes the new champion pointer. Full detail in Section 6.

---

## 3. The eval harness (scripts/eval_baseline.py)

The script is structured as a numbered sequence of sections. Run it as: `python scripts/eval_baseline.py` (full run, ~10–15 min) or `python scripts/eval_baseline.py --smoke-test` (~2 min, 2024 only). Output is printed to stdout; JSON results are written to the `--out` path if provided.

### Sections

**[1/9] Fetch base match data** (~lines 212–306)
Calls ASA API for games + xGoals. Filters to 2017+, excludes COVID years. Encodes labels (0/1/2). Adds `is_playoff`, `kickoff_hour_utc`, cyclic kickoff encoding, `is_post_fifa_break`, `is_dome`.

**[2/9] Fetch game-level xpass** (~lines 308–342)
Tries `asa.get_game_xpass` for PPDA and possession. Sets `_HAS_PPDA` and `_HAS_POSS` flags. This is a graceful-failure fetch — if the endpoint is unavailable the run continues without those features.

**[3/9] ELO grid search** (~lines 344–374)
Validates (K, HOME_ADV) pairs on 2019. Confirmed winners: K=25, HOME_ADV=80. `compute_elo()` is then applied to the full dataset.

**[4/9] Rolling features** (~lines 376–401)
Delegates to `scripts/eval/feature_builders.add_rolling_features()`. Adds all xG, form, congestion, venue-split, Pythagorean luck columns.

**[5/9] Squad quality + auxiliary features** (~lines 403–~865)
Several sub-steps:
- Altitude flag (`is_high_alt` for Colorado, RSL)
- Player xpoints_added (season-lagged squad quality, `home_xpa_rate` / `away_xpa_rate`)
- Positional goals-added split (ATT/DEF)
- Transfermarkt squad values (if CSVs present)
- GK z-score (`home_gk_z`, `away_gk_z`)
- Referee bias features (season-lagged home-win and draw rates per referee)
- Head-to-head draw features
- Weather from Open-Meteo (only if `--weather` flag passed)

**[6/9] Weather / skip** (~line 865 or 918)
If `FETCH_WEATHER=True`, queries Open-Meteo historical API for temperature, precipitation, wind. Dome stadiums get structural NULL. Adds `temp_c`, `precip_mm`, `wind_kph`. Skipped by default.

**[7/9] Walk-forward evaluation** (~lines 2149–2290+)
The main loop. For each `test_season ∈ TEST_SEASONS` (harness default 2021–2024 — 2021 skips because its cal fold 2020 is excluded; the gate's measurement basis is 4-fold 2022–2025 via `--test-seasons 2022 2023 2024 2025`, which `model_report.py` uses by default through `parity_frame.meta.json`):
1. Split: `train = seasons < cal_season`, `cal = cal_season`, `test = test_season`
2. Fit DC on train, calibrate, predict cal + test
3. Grid-search XGB hyperparams, fit on train, calibrate
4. Run A/B sets — each feature-set variant is evaluated independently
5. Pick best A/B set (by cal-fold Brier, not test — no leakage)
6. Fit capped blend weight `w` on cal fold
7. Apply second-pass temperature scaling on blend output
8. Collect `r` dict with all model Brier scores

**[8/9] A/B set summary** (later in script)
Prints a table of Brier by (season, A/B set). Averaged across seasons — positive Δ from Base means that feature set helped.

**[9/9] Feature importances** (final section)
Aggregates XGBoost gain-based importances across all folds. The top features by gain are reported. This is exploratory — do not use for causal inference.

### Key constants (eval_baseline.py lines ~161–187)

```python
XG_WINDOWS   = (3, 5, 10, 15)    # line 161
FORM_WINDOWS = (3, 5, 10, 15)    # line 162
REGRESS      = 0.40               # line 163
DC_DECAY_HL  = 120                # line 165
TEST_SEASONS = [2021,2022,2023,2024] # line 174
WEIGHT_HL    = 6                  # line 176
```

### How to read the output

```
Season 2022: train=1427 cal=543 test=489 | DC✓ | XGB-grid(d=4,n=200,lr=0.05) | BestAB=Base | Blend✓(w_xgb=0.70)+2ndPass
  Naive:   0.6667   DC-raw: 0.6389   XGB(Base): 0.6333   Blend: 0.6305
```

- `DC✓` / `DC✗` — whether Dixon-Coles fitted cleanly
- `XGB-grid(...)` — the inner hyperparameter winner
- `BestAB=Base` — which feature set won on the cal fold
- `Blend✓(w_xgb=N)+2ndPass` — blend succeeded with second-pass calibration
- Brier numbers: lower is better; random baseline ≈ 0.6406

---

## 4. The champion model (models/research_model.py)

This file is a clean, database-free port of the eval_baseline pipeline. It has no print statements and no API calls — it takes DataFrames in, returns DataFrames out.

### `walk_forward(df, feat_base, test_seasons, ...)`

Thin wrapper. Calls `walk_forward_predictions`, then aggregates predictions into `{per_season: {yr: brier}, avg_brier: float, w_xgb: {yr: w}}`. Used by `make parity-check`.

### `walk_forward_predictions(df, feat_base, test_seasons, ...)`

The core eval loop (lines ~184–238). For each test season:

1. Split train / cal / test by season
2. `fit_dc(train, decay_hl=120)` → `(atk, dfd, ha, rho)`
3. Temperature-calibrate DC predictions on cal fold, apply to test fold
4. `fit_xgb(train, feat, weight_hl=6)` → `(clf, best_params)`
5. Temperature-calibrate XGB predictions on cal fold, apply to test fold
6. `fit_capped_blend(xgb_cal, dc_cal, y_cal_oh)` → scalar `w ∈ [0.7, 1.0]`
7. `blend(xgb_te, dc_te, w)` → raw ensemble probabilities
8. **Second-pass** `calibrate_temperature(cal_blend, y_cal, te_blend)` → final `ens_te`
9. Return per-match rows with `prob_home`, `prob_draw`, `prob_away`, `w_xgb`

### The DC+XGB blend math

```python
cal_blend = blend(xgb_cal, dc_cal, w)    # blend on cal fold
te_blend  = blend(xgb_te,  dc_te,  w)    # blend on test fold
ens_te    = calibrate_temperature(cal_blend, y_cal, te_blend)  # 2nd-pass cal
```

The second-pass calibration is the critical fix introduced in Phase 10. Before it, individual temperature scaling was applied to XGB and DC separately, but the convex combination of two calibrated models is not itself calibrated — causing `cal_err=0.1326`. Fitting `T` on the blend output directly reduces this to 0.0360 on the current 4-fold champion report (0.0195 on the prior 3-fold report/snapshot).

### Where calibration happens

- **First pass (DC):** `calibrate_temperature(dc_pred_cal, y_cal, dc_pred_te)` — line ~209
- **First pass (XGB):** `calibrate_temperature(xgb_cal_raw, y_cal, xgb_te_raw)` — line ~218
- **Blend fit:** `fit_capped_blend(xgb_cal, dc_cal, y_cal_oh)` — line ~220
- **Second pass (blend):** `calibrate_temperature(cal_blend, y_cal, te_blend)` — line ~226

### `predict_upcoming(train_df, upcoming_df, current_season, ...)`

Production inference. Mirrors walk_forward_predictions but predicts into `upcoming_df` instead of a held-out test season. The cal fold is `current_season - 1`. Returns a DataFrame with `match_id, prob_home, prob_draw, prob_away, w_xgb`.

---

## 5. The extracted eval package (scripts/eval/)

### elo.py

Single public function: `compute_elo(df, K, home_adv, regress, initial, return_expected)`. Walks the DataFrame row by row in the order provided (must be sorted by date ascending before calling). Applies season regression at the first match of each new season. Includes a margin-of-victory multiplier: `mov = 1 + log(|goal_diff| + 1) * 0.1`. The defaults `initial=1500.0`, `regress=0.40` match the validated config (regress promoted from 0.50 on 2026-06-07). No module-level state — calling it twice with the same input gives identical output.

### dixon_coles.py

Two public functions: `fit_dc(matches, decay_hl, recent_seasons)` and `dc_predict(ht, at, atk, dfd, ha, rho, max_g=8)`. The NLL optimisation uses L-BFGS-B with parameter bounds: attack/defence ∈ (−3, 3), home_advantage ∈ (0, 1), rho ∈ (−0.5, 0). The `recent_seasons=4` default means only the last 4 seasons of the training window are used in the NLL — this is for computational speed; the time-decay handles down-weighting older matches within that window. `dc_predict` builds an 8×8 scoreline matrix (home-score × away-score), normalises it, then sums the lower triangle (home win), diagonal (draw), upper triangle (away win).

### calibration.py

Public function: `calibrate_multiclass(raw_cal, y_cal, raw_test, method="temperature")`. The default temperature method fits a scalar `T ∈ (0.3, 5.0)` by minimising NLL on the cal fold, then applies it to the test fold by dividing log-probabilities by `T` and re-normalising. `T < 1` sharpens probabilities; `T > 1` flattens them toward uniform. The `calibrate_stacked_second_pass` variant (also in this file) is what the walk_forward loop calls for the second-pass blend calibration. Other methods (platt, isotonic, beta, two-stage) are available via `--calibration` but are not the canonical default.

### feature_registry.py

Pure constants and helper functions, no API calls. Key exports: `FIFA_BREAKS` (dates of international windows), `HIGH_ALT_IDS` (Colorado, RSL team IDs), `PYTHAG_EXP=1.83`, `PYTHAG_WIN=10`. Helper functions: `haversine_km`, `pythag_expected_pts`, `is_post_fifa`, `tz_band`, `away_tz_shift_abs`, `away_tz_shift_signed`, `zs_within_season`, `lagged_lookup`, `pos_is_att`, `pos_is_def`. These were extracted from eval_baseline.py's top-level scope during the F4 refactor and verified by the smoke-test gate.

### feature_builders.py

Single main public function: `add_rolling_features(df, xg_windows, form_windows, games_14d_days, xpass_by_game, *, has_ppda, has_poss, has_sp_xg)`. Also exports `add_h2h_draw_features` for head-to-head draw rates. The rolling computation is a single sequential pass through the sorted DataFrame — at each row it reads the team's historical list, computes the window slice, then appends the new result. This guarantees no future leakage: each match only sees matches before it. Venue-split form (`home_pts_last_N`, `away_pts_last_N`), schedule congestion (`games_in_14d`), and rest days are all computed in the same pass.

---

## 6. The promotion gate (scripts/promotion_gate.py + scripts/model_report.py)

### The 6 gate criteria

Defined at the top of `scripts/promotion_gate.py` (lines 45–48):

| Criterion | Rule | Tolerance |
|-----------|------|-----------|
| `coverage` | Challenger has at least as many matches per season as champion | 0 (hard) |
| `robustness_2024` | Challenger 2024 Brier ≤ champion 2024 + 0.0005 | 0.0005 |
| `calibration` | Challenger `max_decile_cal_error` ≤ champion + 0.005 | 0.005 |
| `slices` | No season or confidence slice regresses by > 0.02 | 0.02 |
| `data_source_health` | All sources report `ok=True` if snapshot present | 0 (hard) |
| `core_metric` | Challenger avg Brier beats champion by at least 0.0005 | must gain |

`core_metric` is the only improvement gate — all others are guardrails. A challenger that scores identically to the champion does not pass because gain < MIN_GAIN (0.0005).

A seventh check, **`paired_significance` (advisory, added 2026-06-09)**, runs when both reports embed `per_match` Brier vectors (model_report.py writes them): it bootstraps the mean paired Brier difference on common match_ids and prints `P(challenger better)`. It never blocks — the measured unbagged seed-noise floor (σ≈0.001) makes unpaired gains near 0.0005 ambiguous, so the paired evidence is surfaced for the human decision.

### How to read a model report

The report is a JSON file. Key fields to check:

```json
{
  "avg_brier":       0.633471,       ← must beat champion by 0.0005 to promote
  "per_season": {
    "2022": 0.630402,
    "2023": 0.634451,
    "2024": 0.634305,                ← 2024 hard-gated: no regression > 0.0005 allowed
    "2025": 0.634725                 ← 4th fold added 2026-06-09 (season complete)
  },
  "max_decile_cal_error": 0.036014,  ← calibration quality; lower is better
  "coverage_by_season": {
    "2022": 489, "2023": 521, "2024": 522, "2025": 540
  },
  "w_xgb": {"2022": 0.7, "2023": 0.92, "2024": 0.7, "2025": 0.83},  ← blend weights
  "per_match": {"match_id": [...], "brier": [...]},  ← feeds the gate's paired bootstrap
  "slices": {
    "by_confidence": {
      "<40%": ..., "40-50%": ..., "50-60%": ..., ">60%": ...
    }
  }
}
```

The `by_confidence` slices tell you whether the model is consistent across certainty levels. The `>60%` bucket has n=16 in the champion — too small to be statistically reliable, but good for a sanity check.

### How to run a challenger evaluation

```bash
# 1. Produce a challenger report (uses parity_frame.parquet + research_model.py)
python scripts/model_report.py --label challenger --out experiments/chal.report.json

# 2. Run the gate
python scripts/promotion_gate.py evaluate --challenger experiments/chal.report.json

# 3. If PASS, promote
python scripts/promotion_gate.py promote --challenger experiments/chal.report.json

# Gate self-test (verifies the gate rejects a deliberately worse model)
python scripts/promotion_gate.py self-test
# or
make gate-self-test
```

---

## 7. The parity frame

`data/parity_frame.parquet` is a frozen snapshot of the feature matrix, produced once by:
```bash
python scripts/eval_baseline.py --dump-frame data/parity_frame.parquet
```

Its purpose is reproducibility: `model_report.py` loads this frame rather than re-fetching from the API, so reports are deterministic regardless of what the ASA API returns on any given day.

**Columns** (from `data/parity_frame.meta.json`):

| Group | Columns |
|-------|---------|
| Identity | `match_id`, `season`, `date`, `home_team`, `away_team`, `home_goals`, `away_goals`, `label_result` |
| ELO | `elo_diff`, `home_elo`, `away_elo` |
| xG rolling (×4 windows) | `home_xg_roll_{3,5,10,15}`, `home_xga_roll_{3,5,10,15}`, same for `away_*` |
| Derived xG | `xg_diff`, `home_xg_sum` |
| Form rolling (×4 windows) | `home_form_{3,5,10,15}`, `away_form_{3,5,10,15}`, `form_diff` |
| GK quality | `home_gk_z`, `away_gk_z`, `gk_z_diff` |
| Context | `is_playoff` |

The `feat_base` list in `parity_frame.meta.json` is the exact feature set passed to `walk_forward_predictions` when producing the champion report.

**Inspect it manually:**
```python
import pandas as pd, json

df = pd.read_parquet("data/parity_frame.parquet")
meta = json.load(open("data/parity_frame.meta.json"))

# Shape and season coverage
print(df.shape)                      # expect ~3 000–3 500 rows
print(df["season"].value_counts().sort_index())

# Check no test-season future data leaked into features
# (rolling features for first N matches of a season should be 0 or NaN-filled)
print(df[df["season"] == 2022][meta["feat_base"]].head(3))

# Feature coverage: any column all zeros or all the same?
print(df[meta["feat_base"]].nunique().sort_values().head(10))

# Confirm hyperparams match CLAUDE.md
print(meta["weight_hl"], meta["dc_decay_hl"], meta["regress"])
# Expected: 6, 120, 0.4 (regress promoted 0.50→0.40 on 2026-06-07)

# Quick stats on calibration inputs
print(df[df["season"].isin([2022,2023,2024])]["label_result"].value_counts(normalize=True))
# Expected: roughly 0.46 home / 0.26 draw / 0.28 away
```

---

## 8. Key constants and where they live

| Parameter | Value | eval_baseline.py | models/research_model.py | config/settings.yaml | CLAUDE.md |
|-----------|-------|-----------------|--------------------------|----------------------|-----------|
| ELO K-factor | 25 | Grid default `[20,25,30]`; winner empirical | — | `elo.k_factor: 25` | K=25 |
| ELO HOME_ADV | 80 | Grid default `[80,100,120]`; winner empirical | — | `elo.home_advantage_elo: 80` | HOME_ADV=80 |
| ELO REGRESS | 0.40 | line 163: `REGRESS = 0.40` | `DEFAULT_REGRESS=0.40` in elo.py | `elo.season_regression_pct: 0.40` | REGRESS=40% |
| DC decay half-life | 120 days | line 165: `DC_DECAY_HL = 120` | `DEFAULT_DC_DECAY_HL = 120` (line 29) | `dixon_coles.time_decay_half_life_days: 120` | 120-day half-life |
| XGB season weight half-life | 6 seasons | line 176: `WEIGHT_HL = 6` | `DEFAULT_WEIGHT_HL = 6` (line 30) | — | — |
| xG windows | (3, 5, 10, 15) | line 161: `XG_WINDOWS = (3,5,10,15)` | passed as `feat_base` columns | `features.xg_windows: [3,5,10,15]` | xG windows: (3,5,10,15) |
| Form windows | (3, 5, 10, 15) | line 162: `FORM_WINDOWS = (3,5,10,15)` | passed as `feat_base` columns | `features.form_windows: [3,5,10,15]` | form windows: (3,5,10,15) |
| Blend DC cap | 30% max (w_xgb ≥ 0.7) | lines ~2307–2314: bounds `[(0.7,1.0)]` | `fit_capped_blend(w_min=0.7, w_max=1.0)` | — | — |
| Edge threshold | 8% | — | — | `market.default_edge_threshold_pct: 8.0` | 8% before live betting |
| XGB thread cap | 2 | line 187: `_XGB_NJOBS = int(os.environ.get("EVAL_XGB_NJOBS","2"))` | `DEFAULT_XGB_NJOBS = 2` (line 31) | — | — |
| Smoke-test reference | 0.6346 (2024 Base Brier, regress=0.40) | line 2567: `--smoke-test` asserts within 0.001 | — | — | — |

**To override XGB threads for a single fast run:**
```bash
EVAL_XGB_NJOBS=8 python scripts/eval_baseline.py --smoke-test
```

### Experiment-variant flags (added in the 2026-06-09 loop)

All default OFF; each reports its metric alongside the standard ensemble so runs are self-paired:

| Flag | What it does | Loop verdict |
|------|--------------|--------------|
| `--xgb-bag N` | Bag the BestAB XGB over N seeds, average raw probs pre-calibration | **KEEP (infra)** — `--xgb-bag 5 --seed 42` is the verification protocol |
| `--xgb-wide-grid` | Inner grid + min_child_weight {1,5} × reg_lambda {1,5} (48 combos) | marginal (−0.0003), banked |
| `--lgbm-bag N` | Add N fixed-param LightGBM members to the bag | DROP |
| `--exclude-train-seasons S…` | Drop seasons from training rows only (features/cal untouched) | diagnostic (settled the 2021 question) |
| `--train-on-cal` | Refit DC+XGB on train+cal under frozen calibration constants | DROP |
| `--dc-train-on-cal` | Refit only DC through the cal season, frozen constants | DROP |
| `--inseason-recal` | Per-match 2nd-pass T on cal ∪ completed test matches | DROP |
| `--inseason-prior` | Per-match shrunk class-prior reweighting (α∈{50,150,300}) | DROP |
| `--draw-hurdle` | Binary P(draw) model + conditional H/A renormalisation | DROP |
| `--season-decay F` | Weight xG/xGA/form rolling means by `F**(seasons_ago)`; 1.0 = no-op | DROP (B1) |

---

## 9. Sanity checks to run

### Quick smoke-test (2 min)
```bash
make smoke-test
# Equivalent: python scripts/eval_baseline.py --smoke-test
# Pass condition: 2024 Base Brier within 0.001 of 0.6346 (regress=0.40)
```

### Full test suite
```bash
make test
# Runs pytest across tests/. Includes unit tests for elo.py, dixon_coles.py,
# calibration.py, metrics.py, and the promotion gate self-test.
```

### Parity check (verifies research_model.py matches eval_baseline)
```bash
make parity-check
# Pass condition: |Δ avg_brier| < 0.0015 between eval_baseline and research_model
```

### Inspect parity frame shape and columns
```python
import pandas as pd, json
df = pd.read_parquet("data/parity_frame.parquet")
meta = json.load(open("data/parity_frame.meta.json"))

print(df.shape)                          # rows, cols
print(sorted(df["season"].unique()))     # should include 2017–2024 excl. 2020 (2021 retained)
print(meta["feat_base"])                 # 37 features (incl. availability trio)
print(meta["dc_decay_hl"], meta["regress"], meta["weight_hl"])  # 120, 0.4, 6
```

### Confirm champion report values match CURRENT_STATE.md
```python
import json
r = json.load(open("experiments/champion.report.json"))
print(r["avg_brier"])           # expect 0.632977 (CURRENT_STATE says 0.6330 avg, 4-fold, bag-5)
print(r["per_season"])          # 2022: 0.6308, 2023: 0.6347, 2024: 0.6349, 2025: 0.6315
print(r["max_decile_cal_error"])# expect ~0.0182
print(r["w_xgb"])               # {"2022":0.7, "2023":0.93, "2024":0.7, "2025":0.871}
# Resolve the report path via experiments/champion.json (championed 2026-06-10:
# challenger-bag5.report.json, promoted by user override — see override_note).
```

### Verify champion pointer
```python
import json
ptr = json.load(open("experiments/champion.json"))
print(ptr)   # should point to champion.report.json
```

### Run gate self-test
```bash
make gate-self-test
# or: python scripts/promotion_gate.py self-test
# Should exit 0 (gate correctly REJECTS a worse challenger)
```

### Check A/B set results from a full run
```bash
python scripts/eval_baseline.py \
  --test-seasons 2022 2023 2024 \
  --seed 42 \
  --out /tmp/ab_run.json
python -c "
import json
r = json.load(open('/tmp/ab_run.json'))
# Look for per-season A/B table in output or check avg_brier
print(r.get('avg_brier'))
"
```

### Validate config matches CLAUDE.md
```bash
python -c "
import yaml
c = yaml.safe_load(open('config/settings.yaml'))
assert c['elo']['k_factor'] == 25
assert c['elo']['home_advantage_elo'] == 80
assert c['elo']['season_regression_pct'] == 0.40
assert c['dixon_coles']['time_decay_half_life_days'] == 120
assert c['features']['xg_windows'] == [3, 5, 10, 15]
print('Config OK')
"
```

---

## 10. What "looks wrong" signals

### Metric thresholds

| Signal | What it means |
|--------|--------------|
| Avg Brier > 0.640 | Worse than random baseline (0.6406). Something broke fundamentally — check that COVID seasons are excluded, calibration applied, label encoding correct. |
| Avg Brier > 0.637 | Worse than the pre-blend-fix baseline (0.6381). The second-pass calibration may not be running. |
| 2024 Brier > 0.637 | Hard-gate threshold. The 2024 season is the canary: unconstrained DC blend caused 0.6523 in 2024. If it appears again, check that `w_xgb` bound is `[0.7, 1.0]` not `[0.0, 1.0]`. |
| `max_decile_cal_error` > 0.05 | Poor calibration (model_report measure). The current 4-fold champion is 0.0360. Values well above 0.05 suggest the second-pass temperature scaling is missing or fitting on the wrong target. Pre-fix was 0.1326 → 0.1567. (The harness's own `cal_stage_stacked` is a different, noisier measure that runs 0.13–0.17 — do not compare across the two.) |
| `cal_err` per-class home > 0.10 | The home probability distribution is badly miscalibrated. |

### Data quality signals

| Signal | What it means |
|--------|--------------|
| xG coverage < 80% | ASA `get_game_xgoals` partially failed. Rolling xG features will be mostly NaN-filled (zeroed). Results will be weaker but should not crash. |
| `home_xg_roll_15` all zeros for a season | The rolling feature builder is not receiving xG data for that team. |
| A feature with `nunique() == 1` | NaN-fill collapsed a feature. Check if the relevant data source was available. |
| `coverage_by_season` shrinks vs champion | Data was lost — the API returned fewer matches than the frozen parity frame. This fails the coverage gate. |
| 2020 or 2021 appearing in `test_seasons` | COVID exclusion broke. These seasons have abnormal home-away patterns and inflated draw rates. |

### Leakage signals

| Signal | What it means |
|--------|--------------|
| Brier suspiciously below 0.60 on any single season | Very unlikely with real data; usually means test data leaked into training (e.g. wrong season split boundary). |
| Rolling features for match 1 of a season have non-zero values from that same season | Walk-forward chronological ordering broke. Check `df.sort_values("date")` call. |
| ELO values for a team at the start of a season identical to the end of the previous season (no regression) | `REGRESS` is 0.0 instead of 0.40. |

### Model integrity signals

| Signal | What it means |
|--------|--------------|
| `w_xgb` = 1.0 for all seasons | Blend collapsed to pure XGB (DC contributing nothing). Not necessarily wrong, but worth investigating whether DC fit failed. |
| `w_xgb` outside [0.7, 1.0] | Should never happen — bounds are enforced. If seen, the `fit_capped_blend` function is being called without bounds. |
| XGB `best_p` always `max_depth=3, n_estimators=200` | Inner grid is not running (validation fold too small). Check `len(ival) >= 30` condition in `fit_xgb`. |
| Smoke-test fails by > 0.005 | A breaking change was made to eval_baseline.py. Do not proceed until the source of the divergence is identified. |
| Parity check fails (`|Δ| > 0.0015`) | `research_model.py` has drifted from `eval_baseline.py`. One of the two was changed without updating the other. |
