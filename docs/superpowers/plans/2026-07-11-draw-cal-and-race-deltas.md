# M2 draw calibration + U2 race-delta chips — Plan

> Execute task-by-task; check boxes as you go. Resume anchor for the loop.

**Goal:** (U2) surface per-race "since last build" deltas + a "why changed" cause chip on league race cards, sourced from the existing odds-history snapshots; (M2) diagnose draw miscalibration by league-family × total-goals rigorously and, if material, test a total-goals-aware draw correction through the eval gate.

**Two independent tracks.** U2 is contained product work (new post-build script + client chip, no model risk). M2 is gated model research (diagnose → prototype → harness A/B → gate → maybe port). Ship U2 first; advance M2 as far as the evidence supports without forcing a result.

---

## U2 — Race-delta + "why changed" chips

**Data:** `data/odds_history.parquet` — rows per (league, team, snapshot_date) with metric cols (title/playoff/shield/cup/ucl/europa/releg/promo/conf) + `n_played`, `config_id`, `code_rev`. 6 snapshots and accruing daily.

- [ ] **U2.1** `scripts/build_race_deltas.py` → `webapp/data/race-deltas.js` (`window.RACE_DELTAS`). For each league's two most-recent snapshots: for each metric, find the current leader (max value in latest), compute its delta vs the same team in the prior snapshot, and a cause: `n_played` increased → `result`; else `config_id`/`code_rev` changed → `model`; else → `refresh`. Empty-safe (thin history → `{}`). Model on `build_movers.py`.
- [ ] **U2.2** Wire into `scripts/build_all.sh` (after `build_movers.py`) and both CI finalize steps (`refresh-daily.yml`, `refresh-leagues.yml`), and load `data/race-deltas.js` in `index.html` on league routes (like movers).
- [ ] **U2.3** In `raceCard()` (index.html:1188): if `RACE_DELTAS[LID][card.key]` exists, render a chip after the leader line — signed delta (arrow, color by good/bad direction of that metric), `since {to}`, and a muted cause label ("new result" / "model update" / "refresh").
- [ ] **U2.4** Run `build_race_deltas.py`; verify in browser on a league with ≥2 snapshots (e.g. championship/serie-b/league-one — 3 snapshots each). Confirm chip renders, no console errors, mobile clean.
- [ ] **U2.5** Commit + push (deploys via deploy.yml).

## M2 — Draw calibration (diagnose first, gate before any prod change)

- [ ] **M2.1** Rigorous diagnostic: aggregate draw calibration by family × total-goals bin from all available played payload rows carrying `lam`/`mu` + `pD` + result. Quantify predicted-vs-observed draw rate and sample size per cell. Decide go/no-go (material miscalibration + enough n).
- [ ] **M2.2** If go: design the correction — a total-goals-conditioned draw-temperature applied post-model (raise draw mass when λ+μ low, lower when high), family-scoped. Spec the exact transform.
- [ ] **M2.3** Implement as an opt-in flag in `scripts/eval_baseline.py` (one isolated change, per experiment-protocol §2). Do NOT touch production yet.
- [ ] **M2.4** A/B: single bagged run `--xgb-bag 5 --seed 42` (σ≈0.0002), capture `--out` + full log (memory: capture-eval-run-output). Screen on `max_decile_calibration_error` (<0.05) with Brier-regression veto (>0.001). Confirm at seed 7 if promising.
- [ ] **M2.5** If it clears screening, run `promotion_gate.py` (4-fold) + season-outcome gate. Port to production only if the gate passes. Either way, log the verdict in `docs/feature-hunt-log.md`. Draws stay suppressed until a clear win.

## Out of scope / settled (do not re-litigate)
- Draw hurdle (T3a), per-season rho, dynamic HFA, hybrid bridge-decay (R2 null) — all gate-rejected.
- Market/CLV validation — blocked on odds spend.
