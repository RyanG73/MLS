# Projection Cataloging & Model-Drift Tracking — Design

*2026-07-09 · prepared for UI feedback round 3 ("we should have a system of cataloging projections so that we can track model drift — write a report to plan for that")*

## What already exists (audited 2026-07-09)

| Piece | File | What it captures | Gap |
|---|---|---|---|
| Snapshot archiver | `scripts/archive_odds_snapshot.py` → `data/odds_history.parquet` | One row per (league, team, build): ELO, proj_pts, season-outcome odds, **next match only** (model + market probs). Append-only, deduped on build stamp. | No full match-probability log; no model-config annotation; **doesn't yet capture the new `promoted` column** |
| Movers | `scripts/build_movers.py` → movers strip on the edge board | Biggest odds deltas between each team's last two builds | Two-point delta only — no trajectories, no drift statistics |
| Eval provenance | `experiments/champion.json` + reports | Champion config + walk-forward metrics at promotion time | Not joined to the nightly snapshots |

The foundation is right (append-only parquet keyed by build). Drift tracking is four increments on top, not a new system.

## Definitions — what "drift" means here, concretely

1. **Projection churn** — how much the model's season odds move build-to-build *without new information* (no matches played between builds). Healthy: ≈0. Churn without matches = data-pipeline noise (roster feed flapping, odds-source gaps, name-mapping breaks) or an unintended config change.
2. **Information response** — odds movement *when matches were played*. Healthy: proportional to surprise (a favorite losing moves more than a favorite winning).
3. **Calibration drift** — rolling reliability (predicted vs observed, 90-day window) trending away from the diagonal. The eval harness measures this per fold at promotion time; this tracks it continuously in production.
4. **Config drift** — projections changing because the model changed. Must be *attributable*: every snapshot row should say which champion config produced it.

## Design — four increments

### 1. Widen the snapshot (small, do first)
- Add `promoted` (and any future outcome keys) to the archiver's odds-key list — it currently misses the new column.
- Add per-snapshot provenance columns: `config_hash` (hash of `experiments/champion.json` + `DEFAULT_N_BAGS` + ELO constants), `code_rev` (git short SHA), `n_played` (matches played at build time per league).
- Add a **full match log**: new file `data/match_prob_history.parquet`, one row per (league, match_id, snapshot_date): `pH/pD/pA`, market probs when present, days_to_kickoff. This is what post-hoc calibration studies need — the next-match-only capture can't reconstruct how a probability evolved as kickoff approached.
- Size estimate: ~25 leagues × ~300 upcoming matches × 3 floats × daily ≈ 2–3 MB/month as parquet. Retention: keep everything; annual re-partition by year if it ever matters.

### 2. Drift metrics job (nightly, after the archiver)
`scripts/build_drift_report.py` → `webapp/data/drift.js` + console summary:
- **Churn index** per league: mean |Δ playoff/title/promoted/releg| across teams for build pairs with `n_played` unchanged. Alert threshold: >1.5pp mean churn with zero new matches.
- **Trajectory extract**: per team, the full time series of each outcome key (this powers the UI sparkline — the movers strip already proves the read path).
- **Kickoff funnel**: for settled matches, Brier of the probability quoted at 7/3/1 days out vs the final quote — measures whether late information helps or the model just wobbles.
- **Rolling calibration**: 90-day reliability curve per league family; flag when the mean |predicted−observed| across deciles exceeds 2× its promotion-time value.
- **Config-change markers**: emit a marker row whenever `config_hash` changes, so every dashboard/plot can draw a vertical line — drift after a marker is expected, drift without one is a bug.

### 3. Surface it (Model Health card)
- "Projection stability" card: churn index (7-day), last config change date, a small multiple of the 5 most-moved teams' trajectories, and the kickoff funnel numbers.
- The existing movers strip stays as the "what changed today" view; the health card is the "is change healthy" view.

### 4. Alerting (optional, later)
- launchd nightly job exits non-zero (or `scripts/notify.py`) on: churn alert, calibration alert, archiver wrote 0 rows (pipeline silently broken), or a league's snapshot missing >48h.

## Implementation order & effort

| Step | Effort | Depends on |
|---|---|---|
| 1a. `promoted` + provenance columns in archiver | ~1h | — |
| 1b. `match_prob_history.parquet` writer | ~2h | — |
| 2. `build_drift_report.py` (churn + trajectories + markers) | ~half day | 1a |
| 3. Model Health "Projection stability" card | ~2h | 2 |
| 2b. Kickoff funnel + rolling calibration | ~half day | 1b, needs ~a month of accrual before it's meaningful |
| 4. Alerting | ~1h | 2 |

Recommended: land 1a+1b now (data starts accruing immediately — every week of delay is a week of history that never exists), build 2/3 in the next improvement round, revisit 2b once a month of match-log history exists.
