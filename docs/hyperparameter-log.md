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

---

## 2026-05-30 — Longer-memory DC decay + XGB weight-hl sweep

Reference: cal-temperature-seed42 (best_brier=0.638135, max_cal_err=0.113035, seed=42, dc_decay_hl=120, weight_hl=4)

Per-season reference: 2022=0.6296, 2023=0.6338, 2024=0.6511 (ens_stacked)

### DC decay half-life — longer direction (150d, 180d)

| Param | Value | best_brier | max_cal_err | Δ Brier | Δ CalErr | Verdict |
|-------|-------|-----------|-------------|---------|----------|---------|
| dc_decay_hl | 120 (ref) | 0.638135 | 0.113035 | (ref) | (ref) | ref |
| dc_decay_hl | 150 | 0.638500 | 0.108800 | +0.000365 (worse) | -0.004235 | **DROP** |
| dc_decay_hl | 180 | 0.638600 | 0.104200 | +0.000465 (worse) | -0.008835 | **DROP** |

Per-season Brier (ens_stacked):

| Season | hl=120 (ref) | hl=150 | hl=180 |
|--------|-------------|--------|--------|
| 2022 | 0.6296 | 0.6297 | 0.6297 |
| 2023 | 0.6338 | 0.6340 | 0.6340 |
| 2024 | 0.6511 | 0.6519 | 0.6521 |

**Notes:**
- Longer DC half-life (150d, 180d) is slightly *worse* on Brier despite better calibration.
- 2024 is marginally worse with longer half-life, not better — more historical smoothing does not reduce the 2024 DC-drag problem.
- Calibration error does improve slightly (0.1130 → 0.1088 → 0.1042) but not enough to offset the Brier regression.
- Direction confirmed: DC decay=120d is already optimal for this range (90d DROP, 150d DROP, 180d DROP).

### XGB season weight half-life — longer direction (6, 8)

| Param | Value | best_brier | max_cal_err | Δ Brier | XGB-only | Verdict |
|-------|-------|-----------|-------------|---------|----------|---------|
| weight_hl | 4 (ref) | 0.638135 | 0.113035 | (ref) | 0.638700 | ref |
| weight_hl | 6 | 0.638600 | 0.099000 | +0.000465 (worse stacked) | 0.637400 | **DROP** |
| weight_hl | 8 | 0.638200 | 0.134800 | +0.000065 (worse) | 0.636900 | **DROP** |

Per-season Brier (ens_stacked):

| Season | whl=4 (ref) | whl=6 | whl=8 |
|--------|-------------|-------|-------|
| 2022 | 0.6296 | 0.6299 | 0.6294 |
| 2023 | 0.6338 | 0.6349 | 0.6344 |
| 2024 | 0.6511 | 0.6510 | 0.6506 |

**Notes:**
- XGB alone improves substantially with longer weight half-life (whl=6: 0.6374, whl=8: 0.6369 vs ref 0.6387) — especially for 2024 (whl=6: 0.6356, whl=8: 0.6345 vs ref 0.6381).
- However the *stacked* ensemble does not capture this improvement — DC drag still dominates at 2024, pulling the ensemble up.
- whl=8 worsens calibration significantly (cal_err=0.1348 vs 0.1130 ref) while only matching stacked Brier.
- The XGB-alone improvement from longer weighting is real, but blocked from lifting best_brier by the stacked ensemble architecture.
- **Conclusion:** If the architecture were XGB-only, whl=6 or 8 might KEEP. Under current stacked architecture, both DROP.

**experiment_ids:** hyp-dc-hl150-20260530T173635, hyp-dc-hl180-20260530T173920, hyp-whl-6-20260530T174242, hyp-whl-8-20260530T174609

**Overall conclusion for longer-memory sweep:** All four experiments DROP vs threshold of Δ > 0.001. Longer memory helps XGB's standalone performance (especially 2024) but the stacked ensemble with DC drag negates the benefit. The 2024 DC-drag problem is architectural, not a hyperparameter problem.
