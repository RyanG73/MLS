# Entenser — Documentation Map and Roadmap

This file is navigation, not a changelog.

## Read in this order

| Question | Canonical document |
|---|---|
| What is true and what happens next? | [`STATUS.md`](STATUS.md) |
| What exact work is active? | [`superpowers/plans/2026-08-17-public-launch.md`](superpowers/plans/2026-08-17-public-launch.md) |
| What model and pipeline configuration is current? | [`CURRENT_STATE.md`](CURRENT_STATE.md) |
| Why did the project make past decisions? | [`PROJECT_HISTORY.md`](PROJECT_HISTORY.md) |
| How are experiments evaluated? | [`experiment-protocol.md`](experiment-protocol.md) |
| Which model ideas were tried or rejected? | [`feature-hunt-log.md`](feature-hunt-log.md) |

Dated strategy, audit, and research documents are evidence. They do not override `STATUS.md`.

## Now — paid transaction milestone

Make the complete production customer path work:

1. Connect `api.entenser.com`.
2. Provision Upstash and production secrets.
3. Activate Stripe prices, webhook, and Customer Portal.
4. Publish Terms, refund, and corrected privacy policies.
5. Complete monthly and annual sign-in → payment → access → cancellation → refund rehearsals.

Success means the evidence is recorded in `STATUS.md` and the launch plan, not merely that the
code exists.

## Next — launch readiness

1. Verify GA4, Search Console, sitemap submission, and the purchase funnel.
2. Audit every paid-tier claim against the archive's actual depth.
3. Freeze content on 2026-08-14 and code on 2026-08-15.
4. Launch on 2026-08-17 only with a green money path and an available monitor.
5. Make a paid-tier keep/change/kill decision on 2026-09-30.

## Later — after the transaction path is proven

- Resolve the UX decisions preserved in `STATUS.md`.
- Complete championship-playoff simulation coverage.
- Re-check Matches to Watch ranking once European seasons are active.
- Revisit inter-confederation ELO calibration when more cross-confederation matches exist.
- Evaluate retention work from `product-strategy-2026-07-26.md` against observed subscriber use.

## Documentation rules

- `STATUS.md` contains current claims, blockers, next actions, and proof only.
- The active plan contains checklists and verdicts only.
- `CURRENT_STATE.md` contains technical configuration and commands only.
- `PROJECT_HISTORY.md` contains completed narrative and durable decisions only.
- Completed plans are summarized in history and deleted; Git retains their full text.
- `PLAN.md` stays under 100 lines.
