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
