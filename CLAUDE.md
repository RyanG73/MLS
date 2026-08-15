# MLS Dashboard — Claude Instructions

## Documentation convention

**Where to look:**
- `docs/STATUS.md` — canonical current truth: production state, blockers, next actions, and proof
- `docs/PLAN.md` — short documentation map and Now/Next/Later roadmap; never a changelog
- `docs/CURRENT_STATE.md` — canonical model config, metrics, run commands (quick reference)
- `docs/PROJECT_HISTORY.md` — narrative history for newcomers; model lineage, key decisions, what failed and why
- `docs/experiment-protocol.md` — shared agent contract for improvement campaigns
- `docs/feature-hunt-log.md` — live record of features tried and rejected
- `docs/superpowers/plans/<active>.md` — the one active execution checklist; completed steps have verdicts appended at top
- Dated strategy, audit, and research documents are evidence only. They never override `STATUS.md`.

**Update rules (apply every iteration, commit with code changes):**
- After any **code or production-state change**: update `docs/STATUS.md` and append a concise verdict to the active `docs/superpowers/plans/` file.
- If model config or metrics changed, update `docs/CURRENT_STATE.md`.
- After a **plan completes**: add 2–3 sentences summarising outcomes to `docs/PROJECT_HISTORY.md` under a dated entry, then delete the plan file.
- After a **milestone or durable decision**: record it once in `docs/PROJECT_HISTORY.md`; do not copy a running changelog into `PLAN.md`.
- Keep `docs/PLAN.md` under 100 lines. It links to the current truth and groups work into Now/Next/Later.
- **Completed plan files are deleted, not archived.** Their story lives in `PROJECT_HISTORY.md`.
  Keep exactly one active plan unless the owner explicitly authorizes a second independent workstream.

**Fact rules (apply to every document, including this one):**
- **This file may state a decision or a threshold. It may not state a measurement.** Club counts,
  league counts, Brier scores and test counts go stale and are then quoted as authoritative from
  here. They belong in `CURRENT_STATE.md` or are measured at build time.
- **A figure on more than one surface has one source, measured rather than typed.** `/global-elo/`
  already does this — it reads its counts from the payloads at build time.
- **When you correct a fact, grep for it before you commit:**
  `rg '<old value>' docs/ CLAUDE.md README.md .claude/ --glob '!**/worktrees/**'`. A correction
  that lands in one file and not its siblings is worse than the original error, because now the
  repository disagrees with itself. Precedent: on 2026-08-01 a Global ELO count was fixed in
  `STATUS.md` and left stale in nine places, including this file.
- **Check which population a figure describes before "correcting" it.** `power_ladder_*` in
  `docs/figures.json` counts the bridged `power.js` ladder; `global_elo_*` counts every club
  carrying a rating, a strictly larger population. Both are right for their own question, and
  quoting one for the other is the mistake to avoid. The values are deliberately not repeated
  here — this file states decisions, not measurements, and the two that used to sit on this line
  were themselves stale by 2026-08-05.
- **When you delete a document, grep for its name** across `docs/`, `.claude/`, and
  `~/.claude/projects/-Users-ryangerda-Development-MLS/memory/`. A session memory outlives a
  deleted file and keeps instructing sessions to update it.
- **Stage explicit paths, not `git add -A`.** Twice on 2026-08-02 an `-A` swept another session's
  uncommitted work and an unread file into a commit whose message described neither.

## Active branch

Development happens on `main` (user decision 2026-06-10, after the bag-5 champion promotion was merged
to main by explicit instruction). The historical dev branch `claude/mls-prediction-dashboard-C2mQM`
is merged and retained for history.

## Eval script

`scripts/eval_baseline.py` is the research harness. Changes here are validated before porting to the production pipeline (`features/`, `models/`, `config/`).

## Key decisions (do not re-litigate without being asked)

- Training data: 2017+ only, 2020 excluded (COVID bubble). 2021 is RETAINED in training and as the
  2022 cal fold — A/B-validated 2026-06-09 (excluding 2021 from training costs +0.0019 Brier on the
  3-seed mean, nearly all on 2023; the earlier "2021 excluded" wording was stale docs)
- Test seasons: 2022–2025 walk-forward (2022 evaluates with the 2021 cal fold). 2025 added as the 4th
  fold 2026-06-09 — the old "2025 in-progress, never in test window" rule lapsed when the season
  completed (540 matches). 2026 in-progress data: training only, never in the test window.
- Champion: experiments/champion.json → challenger-bag5 report (avg **0.6330**, cal 0.0182, 4 folds,
  per-match vectors). Config: **5-member XGB seed bag** (research_model DEFAULT_N_BAGS=5), narrow grid.
  Promoted 2026-06-10 by explicit user override (core short 6e-6 / 2024 over ~0.0001, both sub-noise;
  calibration halved). Gate challengers must be 4-fold reports; wide_grid stays opt-in (gate-rejected
  on calibration 2026-06-09).
- Verification protocol: judge harness experiments on a single bagged run (--xgb-bag 5 --seed 42,
  σ≈0.0002) and confirm gate-bound claims at a second base seed.
- Calibration: temperature scaling (single T parameter, minimise NLL on cal fold)
- ELO: K=25, REGRESS=40% (promoted 2026-06-07: whl=6 + regress=0.40 synergistic; avg Brier 0.6337,
  cal_err 0.0195; prior "50% wins" was measured at whl=4). **HOME_ADV is per competition since
  2026-08-07** — `scripts.eval.elo.home_adv_for`, 80 for MLS and the Brasileirão, 55 everywhere
  else. The old flat 80 was promoted on MLS data and was optimal in ZERO of 19 European leagues
  swept end to end; MLS keeps 80, so the champion config is unchanged. Build paths must call
  `home_adv_for(league_id)` rather than passing a literal.
- DC time-decay: 120-day half-life
- xG windows: (3, 5, 10, 15) matches — eval harness default; champion feat_base includes all four
- Edge threshold: 8% before live betting
- **Paywall boundary — lock the continuity, never the current answer** (2026-08-01). Any number that
  exists today stays visible and free: current forecasts, tables, every published grade. What Club
  Watch sells is that someone watched it — what changed while you were away, the evidence behind it,
  saved scenarios, per-club history. A lock must sit on the continuity layer, never on a figure the
  public site already publishes, or the "free forever" promise printed on the site becomes false.
- **The paywall is OFF for the initial launch, and preserved** (owner decision 2026-08-15). Every
  Club Watch feature is free to anyone with a free account. The switch is `LAUNCH_FREE` in
  `server/open_access.py`; setting it back to `False` and deploying restores the paywall, and that
  must stay the whole operation. **Do not delete, collapse, or route around any paid mechanism**
  while it is off — the plan ranks, `require_entitlement`, the Stripe webhook, the client lock
  chrome and the checkout gate all stay in the path and stay tested. Two rules hold while it is
  off: signing in is still required for anything per-user (open access means "no payment", never
  "no account"), and checkout stays shut whatever Stripe is configured to do. The line above still
  describes where the paywall goes when it returns.
- **Global ELO** is the public name of the shared cross-league strength scale (owner decision
  2026-08-06, replacing "Crossbar", which held the name from 2026-08-01). The internal field was
  always `global_elo`; the public label now matches it, so there is one name to learn instead of
  two. The shortlist's own con column had already predicted the failure — "cute; less
  self-describing, needs the explainer to do more work". The retired `/crossbar/` URL still
  resolves and canonicals to `/global-elo/`; do not remove that redirect, the old URL shipped in
  every club page footer and in the sitemap for the five days the old name was live. It names a *scale*, not an accuracy claim — nothing
  about the name may imply predictive performance, profitability, or betting utility. Coverage is
  a measurement, not a decision — read it from the payloads or `docs/STATUS.md`, never from here.
- **The UEFA match constants are fitted, not typed** (2026-08-06). `_CONF_CONST["UEFA"]` in
  `scripts/eval/cross_league.py` was the last confederation still carrying hand-set "physically
  grounded" priors while every other one had been grid-swept, and it was wrong enough to bend the
  published ladder: it predicted 39.5% home wins against an actual 50.3%, and the league offsets
  were absorbing the difference. Any future change to these constants must be scored on held-out
  1X2 Brier AND constrained so `match_lambdas` still yields a realistic scoreline — `bracket_sim`
  samples goals from them, and the 1X2 objective cannot see goals.
- **Refunds: full refund inside 30 days of first payment** (owner decision 2026-08-01, resolving
  `G0.7`). Not pro-rata, and not pro-rated at the monthly rate the way Rotowire's terms do it. The
  simpler sentence is worth more than the recovered revenue on a launch built on trust.
- Production timing: improve eval first, then port to production
