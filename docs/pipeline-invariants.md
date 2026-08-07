# Pipeline invariants

**Standing constraints on the data and model pipeline. Not a plan, not a checklist — these do
not complete.**

Extracted 2026-08-05 from `CURRENT_STATE.md`, where they sat inside dated expansion narrative and
were at risk of being retired along with it. Several are written as warnings because they record
a failure that already happened once.

Breaking one of these is a decision, not an implementation choice. The technical sibling of
`product-invariants.md`.

---

## Model inputs

1. **Market-blind.** Betting odds must never be used as model features. Training on closing lines
   collapses the `model_prob − market_prob` edge that the product sells. Odds are CLV-only —
   consumed after prediction, never before.

2. **Research-first.** All improvements land in `scripts/eval_baseline.py` first. Porting to
   `features/`, `models/`, or `config/` is a separate, explicitly authorized step.

3. **Two thresholds, two stages.** The harness A/B screening bar (Δ > 0.001) is not the champion
   promotion gate (`scripts/promotion_gate.py`, which adds 2024-robustness, calibration, coverage,
   and slice guardrails). A change can pass one and fail the other. The gate is final.

4. **Match Brier is not the only target.** Any change touching the table-sim path — DC fit,
   seeding, temperature, ranking key, format handling, preseason widening — must also run the
   season-outcome replay (`scripts/eval_season_outcomes.py`) against
   `experiments/season-outcomes-baseline.report.json`. A match-Brier KEEP that regresses pooled
   outcome Brier beyond +0.002 at any checkpoint needs an explicit justification.

## Cross-league calibration

5. **Always scope a league-bridge refit with `--conf`.** Each run's "prior" is the previous run's
   fitted value, so an unscoped re-fit walks every league a little on every run. The run merges
   into `experiments/league_offsets.json` rather than overwriting it.

6. **Resolve club identity by ESPN team id, never by name.** 45 of 408 normalized club names
   collide across the 12 modeled South American leagues, and four are genuinely different clubs:
   River Plate (Argentina vs Uruguay — both play these cups), Guaraní (Paraguay vs Brazil Série
   B), Portuguesa (Brazil vs Venezuela), Llaneros (Colombia vs Venezuela).
   `scripts/eval/continental_resolve.py` owns this; `tests/test_league_bridge.py::TestConmebolResolution`
   guards it.

7. **The ridge penalty has two modes and they are not interchangeable.** `ridge_by_count=True`
   (UEFA/Concacaf, historical) scales with each league's match count, which cancels against the
   NLL and gives every league the same shrinkage regardless of evidence. That is only safe with
   informative priors — with a 0 prior it let a 4-match league reach −2417 ELO. CONMEBOL and AFC
   use `ridge_by_count=False`.

8. **A confederation-wide constant cannot move a within-confederation projection.**
   `match_lambdas` consumes the strength *difference*, so a constant added to every league in a
   group cancels. Asserted in `tests/test_interconf_calibrate.py`. Do not "fix" a projection by
   adjusting a confederation shift.

9. **Adoption requires beating every baseline, not just the prior.** A continental fit must beat
   its prior, a naive base-rate predictor, and the all-zero arm — the prior by more than its own
   SEM. AFC and CAF remain unshipped because the gate says so, not because of judgement.

## Build and registry

10. **A new confederation group must be registered in three places** — `index.html` `GROUP_ORDER`,
    `index.html` `MAST_GROUPS`, and `build_static_pages.py` — or the league renders nowhere.

11. **Follow the strict `fetch_league_teams` ordering when adding a league.** Running it while a
    league is still `soon` clobbers already-built data back to a stub. Flip the registry to `live`
    before any later fetch.

12. **`refresh-leagues.yml` is the only job that flips an off-season league back to `live`.**
    `refresh-daily.yml` rebuilds only leagues already live. Its league list is derived from
    `build_league_data.OUTLOOK` — never hardcode it, which is how it drifted to 21 of 70 and
    stranded every league added after round 3.

13. **Every generated artifact needs an owner in the workflow table.** If one looks stale, check
    it has one. Four artifacts went stale in a single week because nothing rebuilt them after
    their inputs changed — the home news rail, `team_intelligence`, `power.js`, and
    `coefficients.js`, the last because its builder was in no workflow at all.

14. **GitHub Actions owns production. Nothing on the local machine publishes.**
    `scripts/build_all.sh` has no git operations — running it rewrites ~176 tracked files and
    publishes nothing, which is what produced a 208-file merge conflict on 2026-08-01. Use it
    deliberately, to inspect a full local rebuild before CI does its own.

15. **A league-specific helper must be gated on that league.** `liga_mx_label()` was applied to
    every `source="espn"` league's `perf_by_year`, producing labels like `"Ap.3028"` for four
    leagues across two expansion rounds. Gate on `lid == "liga-mx"`.

## Published figures

16. **Cross-surface figures are measured, not typed.** Register them in `docs/figures.json`;
    `scripts/check_docs.py` re-measures and fails on drift. The Global ELO page already reads its
    counts from the payloads at build time — that is the pattern.

17. **Check which population a figure describes before correcting it.** The Global ELO scale (every
    club carrying a `global_elo`) and the bridged Global Power ladder (`power.js`, which also
    requires measured bridge evidence and excludes unbridged and women's competitions) are
    different populations. Both are correct for their own question.

## Betting surface

18. **Outright markets are gated to ≥25% season progress for relegation and promotion.**
    Preseason bottom-table odds carry ~no skill versus base rates (releg +0.06, promo +0.01
    pooled); title and UCL do carry skill (+0.30 / +0.46) and may quote from preseason. Recorded
    before the outright extension exists so it cannot be discovered the hard way.

19. **Goals-only ESPN-sourced leagues are projections-only.** No odds, never on the edge board.

## Related

- `product-invariants.md` — truth, the paid boundary, and security.
- `experiment-protocol.md` — the agent contract and gate mechanics.
- `CURRENT_STATE.md` — the configuration and commands these rules constrain.
