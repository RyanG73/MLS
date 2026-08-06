# Research log — calibration, hyperparameter, and architecture experiments

Shared log for the calibration-tuner, hyperparameter-optimizer, and model-architect agents.
Newest entry first. Feature experiments have their own log: `feature-hunt-log.md`.

Format and thresholds are defined in `experiment-protocol.md` §4 and §6. A run with no entry
here did not happen.

```markdown
## <YYYY-MM-DD> — <component> — <one-line description>
**experiment_id:** <id> · **Verdict:** KEEP / marginal / DROP
**Δ best_brier:** <value> · **Δ max_cal_error:** <value>
**Notes:** <what changed, why it did or did not work>
```

---

## 2026-08-05 — cross-league bridge — UEFA ridge loosened 2e-5 → 5e-7
**experiment_id:** uefa-ridge-5e7 · **Verdict:** KEEP
**Δ held-out 1X2 Brier (continental):** −0.0090 mean over 10 seeds (0.6096 prior → 0.6006 fitted);
seed-42 split −0.0121 (0.6139 → 0.6018) · **robustness:** fitted beats prior 10/10 seeds
**Notes:** Owner reported the ladder as wrong — "PSV is simply not a top ten team in europe",
Netherlands and Belgium listed too high. The cause was not the coefficient table (fixed
2026-07-31) but the ridge on top of it. At λ=2e-5 every fitted UEFA offset landed within ~15 ELO
of its prior, so `league_bridge` was decorative: the published ladder was
`_K_COEFF * (coeff − 94)` and the 743 continental matches were barely consulted.

λ swept on **mean** held-out Brier across all 10 robustness seeds, not one split:

| λ | mean Brier | Δ vs prior | seeds won |
|---|---|---|---|
| 2e-5 (was live) | 0.6088 | −0.0008 | 10/10 |
| 5e-6 | 0.6070 | −0.0027 | 10/10 |
| 2e-6 | 0.6045 | −0.0051 | 10/10 |
| 1e-6 | 0.6023 | −0.0073 | 10/10 |
| **5e-7 (adopted)** | **0.6006** | **−0.0090** | **10/10** |
| 2e-7 | 0.5994 | −0.0102 | 8/10 — fails robustness |

5e-7 is the loosest setting that still wins on every seed. Below it thin leagues separate toward
−∞ (unregularised, Finland reaches −1427) and seed agreement breaks.

**The adaptive ridge was tested and rejected for UEFA.** `ridge_by_count=False` is the correct
shrinkage shape in principle and is what CONMEBOL/AFC use, but measured here it is worse: at a
matched Brier of 0.6008 it wins only 8/10 seeds and sends Sweden 684 ELO from its prior, against
10/10 and 431 for the count-weighted fit at 5e-7. UEFA keeps `ridge_by_count=True`.

`_MAX_DELTA_BY_CONF["UEFA"]` raised 150 → 450 in the same change, because ±150 was calibrated
when nothing moved more than ~15 ELO and it now binds hardest on the fifteen leagues whose prior
is a typed estimate rather than a captured coefficient. 450 still catches a runaway.

**Ladder effect** (`power.js` rebuilt, 965 clubs / 55 leagues unchanged): PSV 7th → **27th**,
Club Brugge 10th → **54th**, Union SG 12th → **61st**, Feyenoord 31st → **106th**, Benfica 16th →
**31st**. Top nine is now nine big-five clubs: Bayern, Barcelona, Arsenal, Real Madrid, Man City,
PSG, Inter, Dortmund, Man Utd. Crossbar range moved 770–1770 → **697–1797** (`docs/figures.json`).

**Caveat to carry forward:** the fit is generous to Ligue 1 (−18, from a −81 prior), putting Lens
10th and Lille 12th. That is what 116 Ligue 1 continental matches say, but it is the least
intuitive part of the result and the first thing to re-examine at the next refit.

## 2026-08-05 — log created

`experiment-protocol.md` §6 specified `calibration-log.md`, `hyperparameter-log.md`, and
`architecture-log.md` from 2026-05-29. None was ever created, so three of the four agents ran
without a durable evidence trail — their results survived only if an orchestrator happened to
write them into `PLAN.md`, and `PLAN.md` became navigation-only on 2026-08-01.

The three were collapsed into this single log rather than recreated separately: the fleet runs
as one cycle, and four logs for four components was the over-partitioning that caused three of
them never to exist.

**Prior results are not lost** — they are recorded per campaign in `PROJECT_HISTORY.md` and in
`experiments/registry.jsonl`. This log starts clean and is authoritative from today forward.
