# Hyperparameter Log

> Results from the hyperparameter-optimizer agent. Populated by the multi-agent improvement workflow.
> See `docs/experiment-protocol.md` for the protocol.
>
> Current state (from PLAN.md / CLAUDE.md):
>   ELO: K=25, HOME_ADV=80, REGRESS=50% (SETTLED: 0.50 empirically confirmed over 0.40)
>   DC decay: 120-day half-life
>   XGB season weight half-life: 4 seasons
>   Resolved (2026-05-30): REGRESS 0.40 vs 0.50 — 0.50 wins (0.638135 vs 0.638389)

---

<!-- hyperparameter-optimizer agent appends entries here -->

## 2026-05-30 — REGRESS sweep (partial) + DC decay half-life sweep

### Experiment: hyp-dc-hl090 (DC decay hl=90d vs 120d default)

| Param | Value | best_brier | max_cal_error | Δ Brier | Δ CalErr | Verdict |
|-------|-------|-----------|---------------|---------|----------|---------|
| dc_decay_hl | 120 (ref) | 0.638135 | 0.113035 | (ref) | (ref) | ref |
| dc_decay_hl | 90 | 0.638149 | 0.144036 | +0.000014 | +0.031001 | **DROP** |

Per-season (dc_decay_hl=90d vs 120d):

| Season | DC=90d | DC=120d (ref) | Δ |
|--------|--------|---------------|---|
| 2022 | 0.629698 | 0.629588 | +0.000110 |
| 2023 | 0.633828 | 0.633762 | +0.000066 |
| 2024 | 0.650920 | 0.651056 | -0.000136 |

Per-model Brier for dc-hl090 (DC decay=90d):
- 2022: dc_cal=0.6411, xgb_cal=0.6398, stacked=0.6297 → stacked wins
- 2023: dc_cal=0.6511, xgb_cal=0.6386, stacked=0.6338 → stacked wins
- 2024: dc_cal=0.6493, xgb_cal=0.6376, stacked=0.6509 → **XGB alone wins (DC drag confirmed)**

**Notes:**
- Shorter DC half-life (90d vs 120d) has negligible Brier impact (+0.000014) but worsens calibration substantially (+0.031).
- `ab_sets.Base` is identical (0.638644) — DC decay change does not affect XGB Base feature predictions (expected: Base excludes dc_lam/dc_mu).
- The 2024 DC-drag pattern is stark: XGB alone (0.6376) beats the stacked ensemble (0.6509) by 0.013. This is worse under 90d than 120d, confirming DC drag is real and 90d amplifies it.
- **Decision: Keep DC decay=120d (default unchanged).**

**experiment_id:** hyp-dc-hl090-20260530T041607

---

### Experiment: hyp-regress040 (REGRESS=0.40 vs 0.50 default) — COMPLETE

| Param | Value | best_brier | max_decile_cal_error | Δ Brier | Δ CalErr | Verdict |
|-------|-------|-----------|----------------------|---------|----------|---------|
| regress | 0.50 (ref) | 0.638135 | 0.113035 | (ref) | (ref) | ref |
| regress | 0.40 | 0.638389 | 0.151457 | +0.000254 | +0.038422 | **DROP** |

Per-season (REGRESS=0.40 vs 0.50):

| Season | REGRESS=0.40 | REGRESS=0.50 (ref) | Δ |
|--------|-------------|---------------------|---|
| 2022 | 0.629638 | 0.629588 | +0.000050 |
| 2023 | 0.633737 | 0.633762 | -0.000025 |
| 2024 | 0.651792 | 0.651056 | +0.000736 |

**Notes:**
- REGRESS=0.40 is worse on both Brier (+0.000254) and calibration (+0.038). The key driver is 2024 (+0.000736 Brier), which more than offsets the negligible 2023 gain.
- Earlier partial run (Iteration 5) showed 2022/2023 improvements for 0.40 — those were noise; 2024 tells the full story.
- CLAUDE.md's documented "40%" was aspirational/incorrect — 0.50 is empirically the better default.
- **Decision: Keep REGRESS=0.50 (in-file default confirmed).**

**experiment_id:** hyp-regress040-20260530T170859

---

### Experiment: hyp-whl2 (weight_hl=2 vs 4 default)

| Param | Value | best_brier | max_decile_cal_error | Δ Brier | Δ CalErr | Verdict |
|-------|-------|-----------|----------------------|---------|----------|---------|
| weight_hl | 4 (ref) | 0.638135 | 0.113035 | (ref) | (ref) | ref |
| weight_hl | 2 | 0.638700 | 0.122403 | +0.000565 | +0.009368 | **DROP** |

Per-season (weight_hl=2 vs 4):

| Season | whl=2 | whl=4 (ref) | Δ |
|--------|-------|-------------|---|
| 2022 | 0.630427 | 0.629588 | +0.000839 |
| 2023 | 0.633783 | 0.633762 | +0.000021 |
| 2024 | 0.651891 | 0.651056 | +0.000835 |

**Notes:**
- Halving the weight half-life (downweighting 2017-2019 more aggressively) makes Brier worse across all three seasons.
- whl=2 means matches 4 seasons ago get weight 0.25x vs current; this strips too much signal from early seasons.
- 2024 Brier still high (0.6519) — the 2024 weakness is not a training data recency problem.
- **Decision: Keep weight_hl=4 (default unchanged).**

**experiment_id:** hyp-whl2-20260530T171142
