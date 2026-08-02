# Entenser — Documentation Map and Roadmap

This file is navigation, not a changelog.

## Read in this order

| Question | Canonical document |
|---|---|
| What is true and what happens next? | [`STATUS.md`](STATUS.md) |
| What exact work is active, and who owns it? | [`superpowers/plans/2026-08-17-paid-launch-and-subscription-growth.md`](superpowers/plans/2026-08-17-paid-launch-and-subscription-growth.md) |
| What model and pipeline configuration is current? | [`CURRENT_STATE.md`](CURRENT_STATE.md) |
| Why did the project make past decisions? | [`PROJECT_HISTORY.md`](PROJECT_HISTORY.md) |
| How are experiments evaluated? | [`experiment-protocol.md`](experiment-protocol.md) |
| Which model ideas were tried or rejected? | [`feature-hunt-log.md`](feature-hunt-log.md) |

Dated strategy, audit, and research documents are evidence. They do not override `STATUS.md`.

## Everything else, and when it retires

Consolidated 2026-08-01. Every file in `docs/` appears in exactly one group below. A file that
belongs to no group is a bug — either index it or delete it.

**Standing contracts — obeyed while building; these never complete.**
`product-invariants.md` (truth, paid boundary, security — breaking one is Ryan's call, not an
implementation choice) · `paid-claim-matrix.md` · `growth-measurement-contract.md` ·
`paid-launch-decision-record.md` · `data-sources.md` · `drift-playbook.md` ·
`experiment-schema.json`. **Retire:** never, unless superseded by a newer contract.

**Operating kits — opened when the situation arises, not read end to end.**
`customer-discovery-kit.md` · `club-watch-concierge-kit.md` · `intelligence-hub-launch-runbook.md` ·
`data-and-notification-incident-checklist.md` · `launch-announcements.md` ·
`growth-experiment-ledger.md` · `social-media-strategy-2026-08-launch.md` ·
`legal-copy-draft-2026-07-25.md`. **Retire:** when the situation it serves is permanently past —
the legal draft when Terms, refund, and privacy publish.

**Reusable prompts — `docs/prompts/`.** Tools, not documents: `competitor-deep-dive.md` ·
`site-ux-audit.md` · `league-qa-audit.md` · `launch-readiness-audit.md`. **Retire:** when the
surface they audit no longer exists.

**Built but unwired — documentation for real code that has not shipped.**
`postgame-win-expectancy.md` (`scripts/postgame_win_expectancy.py` exists and is calibration-
validated) · `projection-drift-tracking.md`. **Retire:** on ship, folded into `CURRENT_STATE.md`;
deleting one of these orphans working code.

**Dated evidence — superseded by `STATUS.md`, kept only for its reasoning.**
`competitive-intelligence-2026-07-combined.md` · `competitor-deep-dive-2026-08-01.md` ·
`product-strategy-2026-07-26.md` · `product-roadmap-2026-07.md` ·
`offseason-model-improvement-audit-2026-07-30.md` · `league-expansion-report.md` ·
`league-qa-audit-findings.md` · `feature-backlog-report-2026-07-13.md` · `qa-pass-2026-07-17.md` ·
`remaining-external-dependencies-2026-07-11.md`.
**Retire:** once its decisions are in `STATUS.md` and its durable reasoning is in
`PROJECT_HISTORY.md`. Findings not yet acted on are the only reason to keep one.

## Now — strategy, transaction, measurement, and trust

The immediate program has four parallel foundations:

1. Ryan approves the primary customer, Club Watch outcome, free/paid boundary, ordinary price, and
   whether August 17 is a controlled beta or broad launch.
2. Ryan completes the business, Stripe, legal, vendor, analytics, and support setup.
3. Claude reconciles paid claims, repairs trust defects, instruments the funnel, and proves monthly
   and annual sign-in → payment → access → cancellation → refund.
4. Ryan interviews committed fans while Claude synthesizes recent behavior and prepares the
   full-price concierge test.

Success means Entenser can charge safely, the offer matches reality, and the recurring customer job
is demonstrated—not merely that checkout code exists.

## Next — prove and productize Club Watch

1. Sell a four-to-six-week, ordinary-price concierge to 30–50 qualified prospects.
2. Require real payment, repeated update consumption, and continuation evidence.
3. Productize only the validated alert → cause → next-match loop.
4. Establish a minimum 60-day ordinary-price activation and retention baseline.
5. Record an interim paid-tier keep/change/kill/extend decision on 2026-09-30 using the evidence then
   available; schedule the definitive D60 decision when the first controlled cohort starts.

## Later — acquisition and gated scale

- Test a fixed Run-in Pass or trial separately from the ordinary-price baseline.
- Test Club Rate with matched clubs only after normal-price retention is credible.
- Turn a successful team campaign into a repeatable club-community playbook.
- Scale through subscriber gates to 7,000; refresh the traffic/conversion/churn model monthly.
- Add Forecast Memory, Creator Studio, embeds, or localization only when their evidence gates pass.
- Keep more leagues, ads, betting-affiliate positioning, and unvalidated community features
  deliberately deferred.

## Documentation rules

- `STATUS.md` contains current claims, blockers, next actions, and proof only.
- The active plan contains the minimum approved decision context, ordered checklists, evidence
  gates, and verdicts needed to execute without reopening old strategy documents.
- `CURRENT_STATE.md` contains technical configuration and commands only.
- `PROJECT_HISTORY.md` contains completed narrative and durable decisions only.
- Completed plans are summarized in history and deleted; Git retains their full text.
- **The deletion rule covers reports and audits too, not only `superpowers/plans/`.** That gap is
  how `docs/` reached 37 files: nothing entering as a "report" had a retirement trigger.
- **Before deleting, extract.** A finished document can still hold a standing rule — the 1,405-line
  Intelligence Hub spec wrapped ten invariants nothing else recorded (now `product-invariants.md`).
- `PLAN.md` stays under 100 lines.
