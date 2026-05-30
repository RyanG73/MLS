# Hyperparameter Log

> Results from the hyperparameter-optimizer agent. Populated by the multi-agent improvement workflow.
> See `docs/experiment-protocol.md` for the protocol.
>
> Current state (from PLAN.md / CLAUDE.md):
>   ELO: K=25, HOME_ADV=80, REGRESS=40% (CLAUDE.md) vs REGRESS=50% (in-file default)
>   DC decay: 120-day half-life
>   XGB season weight half-life: 4 seasons
>   Unresolved: REGRESS 0.40 vs 0.50 discrepancy needs empirical settlement.

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

### Experiment: hyp-regress-040 (REGRESS=0.40 vs 0.50 default) — INCOMPLETE

**Status:** Process accidentally terminated (SIGUSR1 sent during debug investigation). Partial per-season data:

| Season | REGRESS=0.40 (partial) | ref (0.50) | Δ |
|--------|------------------------|------------|---|
| 2022 | 0.6293 (estimate) | 0.629588 | ~-0.0003 |
| 2023 | 0.6330 (estimate) | 0.633762 | ~-0.0008 |
| 2024 | NOT CAPTURED | 0.651056 | unknown |

**Notes:**
- Partial results for 2022 and 2023 both show improvement for REGRESS=0.40 — consistent with CLAUDE.md's documented 40% value.
- Cannot determine KEEP/DROP without the 2024 result.
- **Action: Re-run in Iteration 6 (next hyperparameter iteration) as highest-priority sweep.**
- **Recommendation: Run experiments sequentially (not in parallel) on this 4-core system.** Both experiments spawned 16+ XGB threads each, saturating all 4 cores and slowing each season from ~3 min to 30-45 min.

**experiment_id:** hyp-regress-040-20260530T041104 — incomplete (no registry entry, process killed at 2024 season)
