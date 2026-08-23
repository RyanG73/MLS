# Entenser — Documentation Map and Roadmap

## Read in this order

| Question | Canonical document |
|---|---|
| **What does Ryan need to do?** | [`STATUS.md` → What I need from you](STATUS.md#what-i-need-from-you--the-owner-queue-re-tiered-2026-08-15) — tier A blocks Claude today |
| What is true and what happens next? | [`STATUS.md`](STATUS.md) |
| What exact work is active, and who owns it? | [`superpowers/plans/2026-08-17-paid-launch-and-subscription-growth.md`](superpowers/plans/2026-08-17-paid-launch-and-subscription-growth.md) |
| What model and pipeline configuration is current? | [`CURRENT_STATE.md`](CURRENT_STATE.md) |
| Why did the project make past decisions? | [`PROJECT_HISTORY.md`](PROJECT_HISTORY.md) |
| How are experiments evaluated, and what was tried? | [`experiment-protocol.md`](experiment-protocol.md) · [`feature-hunt-log.md`](feature-hunt-log.md) · [`research-log.md`](research-log.md) |
| What must never break? | [`product-invariants.md`](product-invariants.md) · [`pipeline-invariants.md`](pipeline-invariants.md) |

## Everything else, and when it retires

Consolidated 2026-08-01, re-filed 2026-08-05. Every file under `docs/` — subdirectories
included — appears in exactly one group below; a file in no group is a bug, and
`scripts/check_docs.py` enforces it.

**Standing contracts — obeyed while building; these never complete.** `product-invariants.md`
(truth, paid boundary, security — breaking one is Ryan's call) · `pipeline-invariants.md` (the
model/data equivalent) · `figures.json` (cross-surface figures, measured not typed) ·
`paid-claim-matrix.md` · `growth-measurement-contract.md` · `paid-launch-decision-record.md` ·
`data-sources.md` · `drift-playbook.md` · `experiment-schema.json`. **Retire:** never, unless superseded.

**Operating kits — opened when the situation arises, not read end to end.**
`customer-discovery-kit.md` · `club-watch-concierge-kit.md` · `intelligence-hub-launch-runbook.md`
· `data-and-notification-incident-checklist.md` · `launch-announcements.md` ·
`growth-experiment-ledger.md` · `social-media-strategy-2026-08-launch.md` ·
`legal-copy-draft-2026-07-25.md`. **Retire:** when its situation is past — the legal draft when
Terms, refund, and privacy publish.

**Reusable prompts — `docs/prompts/`.** Tools, not documents: `competitor-deep-dive.md` ·
`site-ux-audit.md` · `league-qa-audit.md` · `launch-readiness-audit.md` ·
`codebase-unification-review.md`. Each is a slash command of the same name; the wrapper in
`.claude/commands/` frames it and loads the prompt from here, keeping one source. **Retire:** when the surface they audit no longer exists.

**Launch content drafts — `docs/content/`.** `README.md` · `model-explainer.md` ·
`epl-2026-27-priors.md` · `promoted-teams.md` · `relegation-risk.md` · `market-blind-edge.md`.
Owner-gated. **Figures predate the current payloads — re-measure against `figures.json` first.** **Retire:** on publication.

**Built but unwired — documentation for real code that has not shipped.** `postgame-win-expectancy.md` (`scripts/postgame_win_expectancy.py` exists, calibration-validated) · `projection-drift-tracking.md`. **Retire:** on ship; deleting one orphans working code.

**Specs — `docs/superpowers/specs/`.** Designed; mostly unbuilt. `2026-08-07-uefa-competition-forecasting-design.md` · `2026-08-07-leagues-cup-forecasting-design.md` · `2026-08-08-match-data-source-resilience-design.md` · `2026-08-09-platform-reliability-and-api-opportunity-spec.md` — the live one; Phase 1 is merged and partly proven. `2026-08-08-api-football-migration-execution-spec.md` is **the record of a finished migration, not a plan**: stages 0–2 and 4 are complete and the owner has bought the Mega plan, so its purchase checkpoint has passed; stages 3, 5 and 6 are **dead**, superseded by the reliability spec §3.2 (adjudicated 2026-08-15 — two live specs proposing the same Tier-A migration is the contradiction the group existed to prevent). **Retire:** deleted on ship like a plan, with 2–3 sentences into `PROJECT_HISTORY.md`.

**Dated evidence — superseded by `STATUS.md`, kept for its reasoning.** Each opens with an as-of
stamp; figures inside are frozen at that date. `competitive-intelligence-2026-07-combined.md` ·
`competitor-deep-dive-2026-08-01.md` · `product-strategy-2026-07-26.md` ·
`product-roadmap-2026-07.md` · `league-expansion-report.md` ·
`offseason-model-improvement-audit-2026-07-30.md` · `league-qa-audit-findings.md` ·
`remaining-external-dependencies-2026-07-11.md`. **Retire:** once its decisions are in `STATUS.md`
and its reasoning in `PROJECT_HISTORY.md`, and only if it holds no un-acted finding and **nothing
cites it** — an inbound reference is evidence a report is still a load-bearing input, not a
retirable artefact. Re-tested 2026-08-15: all eight hold, six cited by a live prompt or slash
command. `codebase-unification-2026-08-02.md` was the ninth and the only one to clear every
question; retired, in `PROJECT_HISTORY.md`.

## Now — launch free, measure it, and make the data trustworthy

**Re-scoped 2026-08-15: the paywall is off for the initial launch** (`LAUNCH_FREE` in
`server/open_access.py`), so the transaction is deferred and the job becomes evidence. **Owner-
confirmed 2026-08-15; Tier A is clear**, leaving Ryan's two Tier-B items as the critical path.
(1) Ryan supplies GA4/GSC access and recruits `D2` — unmeasured, a free launch produces nothing. (2) Claude makes the forecasts trustworthy:
unstick the daily refresh so the 51 stale payloads rebuild, publish per-league freshness, keep the
matchers refusing rather than guessing. ESPN is no longer dark (2026-08-23: it was refusing our own User-Agent), so that is redundancy work now, not outage response. (3) Ryan completes the business, Stripe, legal and vendor setup on its own
clock — it now gates *charging*, not launching. (4) The transaction path stays built and tested,
untouched, for the day the paywall returns. Live owner queue: [`STATUS.md`](STATUS.md#what-i-need-from-you--the-owner-queue-re-tiered-2026-08-15).

## Next — prove and productize Club Watch

Sell a four-to-six-week ordinary-price concierge to 30–50 qualified prospects, requiring real
payment, repeated consumption, and continuation evidence. Productize only the validated alert →
cause → next-match loop. Establish a 60-day activation and retention baseline. Record an interim
keep/change/kill/extend decision 2026-09-30; set the definitive D60 review when the first cohort
starts.

## Later — acquisition and gated scale

Run-in Pass or trial tested separately from the ordinary-price baseline · Club Rate only after
normal-price retention is credible · a successful team campaign turned into a repeatable
club-community playbook · scale through subscriber gates to 7,000, refreshing the
traffic/conversion/churn model monthly · Forecast Memory, Creator Studio, embeds, and
localization only when their evidence gates pass. More leagues, ads, betting-affiliate
positioning, and unvalidated community features stay deferred.

## Documentation rules

Scope: `STATUS.md` = claims + proof · active plan = decision context, checklists, verdicts ·
`CURRENT_STATE.md` = configuration, measured results, commands · `PROJECT_HISTORY.md` = completed narrative and durable decisions · `PLAN.md` = navigation, under 100 lines.

- Completed plans **and specs** are summarized in history and deleted; Git retains the text. The
  rule covers reports and audits too — that gap is how `docs/` reached 37 files.
- **Before deleting, extract, then check inbound references** (session memories included). A
  finished document can hold a standing rule — a 1,405-line spec wrapped ten (now
  `product-invariants.md`), `CURRENT_STATE.md` hid nineteen (now `pipeline-invariants.md`) — and
  a reference is evidence it is still load-bearing.
- Enforcement is `scripts/check_docs.py` (filing, dangling refs, retired branch names, figure
  drift, this file's budget), in `make test`. **Rules nothing checks are the ones that rot.**
  Editing procedure: the `doc-hygiene` skill.
