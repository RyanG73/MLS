# Entenser paid launch and subscription growth to 7,000

**Active from:** 2026-07-27  
**Business owner:** Ryan  
**Repository/analysis owner:** Claude  
**Canonical current state:** [`../../STATUS.md`](../../STATUS.md)  
**Technical reference:** [`../../CURRENT_STATE.md`](../../CURRENT_STATE.md)

This is the repository's single active execution plan. It absorbs the prior public-launch checklist
and gives every recommendation from the subscription audit, competitive analysis, and Club Rate
proposal an owner, dependency, test, and decision gate. `STATUS.md` remains the source of truth for
what is live or blocked.

## Verdict log

Append concise, dated results here, newest first. Include proof such as deployment run, Stripe event,
HTTP response, experiment sample, cohort date, or decision memo.

- **2026-07-31 — Club Watch season forecast history repository-ready.** The existing History view
  now merges leakage-safe early-season replays with exact nightly archives, preserves exact rows on
  same-day conflicts, labels reconstructed and archived chart segments, and chooses a useful
  historical target when the club's current target lacks prior coverage. The complete free sample
  includes a frozen season path; the paid continuation keeps the integrated club-season view current.
  Public league history remains free, so no exclusive-history claim was introduced. Proof: all
  1,719 tests passed with 14 intentional skips; all 79 payloads and the history-growth gate passed;
  Chromium covers the MLS dashed-to-solid path, the free sample, and mobile overflow. Production
  deployment is pending; this changes no paid-launch gate.
- **2026-07-31 — point-in-time season history deployed.** Added leakage-safe Dixon–Coles
  matchday replays for all 71 domestic league race pages, kept them in a provenance-labeled dataset
  separate from the authoritative nightly archive, and merged them with archive precedence. Thirty-
  five leagues received 5,725 reconstructed team-points; 36 needed no replay because their current
  season began after archiving. Movement charts now show dashed reconstructed segments and solid
  archived segments, and expanded history covers continental/premiers/finals outcomes. Proof: all
  1,714 tests passed with 14 intentional skips, all 79 payloads and history-growth checks passed,
  dataset invariants passed, and the MLS Chromium provenance flow passed. Pages run `30637496201`
  deployed commit `871eaa4`; the public MLS payload begins on `2026-02-20` and distinguishes
  reconstructed from archived points. This trust improvement changes no model champion or
  paid-launch gate.
- **2026-07-31 — MLS/home presentation follow-up deployed.** MLS now follows the
  table-first league-page order, team links use the product text palette, the header carries both
  US and Canada flags, and movement sparklines reach Game 1 with an honest dashed hold where saved
  forecasts begin midseason. The desktop Club Watch hero now uses both columns; its duplicate
  next-48-hours/league count moved into the masthead ticker and its one-off biggest-move line was
  removed. Proof: all 1,710 tests passed with 14 intentional skips, all 76 Chromium flows passed,
  the static build emitted 1,543 URLs, and `git diff --check` passed. Production deployment is
  proven by successful Pages run `30629626679` for commit `b468f6e`; the deployment also refreshed
  the live service-worker cache.
- **2026-07-31 — Club Watch foundation and site refresh deployed.** Commit `1d954fa` passed 1,708
  tests with 14 intentional skips, all 79 payload checks, the Intelligence artifact contract,
  history-growth and promotion gates, compilation, JavaScript syntax, and the exact static build.
  GitHub Pages run `30627028178` and Vercel API run `30627028137` completed successfully. The live
  homepage serves the Club Watch promise; the production config serves the new checkout contract
  with `enabled: false` and `reason: owner_disabled`. Deployment and fail-closed safety are proven;
  pricing, legal, transaction, delivery, and customer-evidence gates remain open.
- **2026-07-29 — approved repository tranche completed.** Applied the signed boundary to
  value-triggered conversion moments after a real mover, match-stakes preview, one-match scenario,
  complete sample, and additional-club limit; added consent-aware customer evidence capture,
  canonical cross-surface club contracts, and reviewable delivery outcomes/shadow QA. Checkout
  remains fail closed and the scenario just used remains free. Proof: 1,627 non-browser tests passed
  with 14 intentional skips, all 81 Chromium flows passed, standalone JavaScript syntax and
  `git diff --check` passed. Production evidence and external gates remain pending.
- **2026-07-29 — paid-launch direction approved as written.** Ryan approved the audience, Club Watch
  job and name, free/registered/paid boundary, $5.99/$59.99 ordinary-price baseline, no-trial
  guarantee treatment, eight-club validation shortlist, scope freeze, and August 17 as an earliest
  controlled-beta date. The explicit 7,000-subscriber target date required by `G0.2` remains open;
  the 24-month horizon is only provisional. Approved decisions are recorded in the decision record
  and canonical status; this approval does not pass any commercial, production, customer-evidence,
  or launch gate.
- **2026-07-29 — repository foundation executed; external gates remain.** Added the `G0` decision
  record, measurement contract, experiment/concierge/discovery/incident assets, Club Watch
  sample-first packaging, authenticated Account, production checkout kill switch and four-Price
  fail-closed gate, privacy-limited lifecycle scorecard, Stripe/delivery instrumentation, trust
  repairs, and cross-surface regression coverage. Proof: 1,627 non-browser tests passed with 14
  intentional skips, all 81 Chromium flows passed, JavaScript syntax and `git diff --check` passed,
  and a manual local-browser check found no console error or horizontal overflow in the Club Watch
  entry path. Production pricing/legal/Stripe rehearsal, owner approvals, interviews, concierge
  evidence, two-matchweek shadow evidence, and any paid launch remain incomplete.
- **2026-07-27 — subscription program consolidated.** The launch-only checklist was replaced by this
  owner-versus-Claude plan. No proposition, beta, or Club Rate gate has yet passed.
- **2026-07-26 — durable production auth storage verified.** Production configuration serves through
  Upstash and a production magic-link email arrived.
- **2026-07-26 — production API domain and CORS verified.** `api.entenser.com` resolves, serves the
  config endpoint, and accepts the exact production origin.
- **2026-07-26 — crawlable club pages built; deployment pending.** The static build emits 1,444
  competition-scoped club forecasts and a 1,536-URL sitemap.
- **2026-07-26 — followed-team retention mechanics shipped but unproven.** Durable since-last-visit,
  match stakes, and briefing foundations exist; live customer value remains a hypothesis.
- **2026-07-25 — paid-path code hardened, configuration absent.** Billing lifecycle and funnel code
  exist; production pricing remains empty.

## Current execution state and next-action queue

**As of 2026-07-31, the repository-safe foundation and recommended launch direction are approved
and deployed with checkout disabled, but `G0` still needs an explicit target date and no business,
commercial, customer-evidence, transaction, delivery, or launch gate has passed.** Deployment is
not permission to open checkout.

| Track | Current state | What unlocks the next stage |
|---|---|---|
| `G0` strategy | Direction approved and recorded; exact 7,000-subscriber target date remains open | Ryan supplies the `G0.2` date; then the `G0` exit gate is complete |
| `C1` commercial | Checkout and entitlement code fail closed; production pricing and legal contract remain absent | Entity/bank/vendor setup, four Stripe Prices, approved policies, then monthly and annual transaction rehearsals |
| `M1` measurement | Event dictionary, server ledger, lifecycle joins, categorized feedback/consent capture, and missing-data scorecard exist | Ryan supplies baseline exports and GA4/GSC access; production funnel and Stripe reconciliation pass |
| `T1` trust/claims | Repository trust repairs, canonical cross-surface contract, Club Watch claim cleanup, automated coverage, deployment, and public/API smoke verification are green | Ryan's Account/claim approval and the complete transaction/preflight evidence in `C1.16–C1.23` |
| `D2` discovery | Screener, recent-behavior guide, and provisional club shortlist are ready | Recruit at least 21 participants, conduct interviews, and pass the 10-of-15 job gate |
| `E3` concierge | Operating templates and delivery measurement are ready | `D2` and the commercial gate pass; then obtain at least 10 real full-price buyers |
| `P4/B4` product | Sample-first Club Watch, durable account state, outcome-triggered conversion, stakes, timeline, safe notification controls, delivery outcomes, and shadow-review tooling exist in the repository | Concierge evidence defines the committed loop; delivery then passes two shadow matchweeks, 50 reviews, and one quiet cycle |
| `R5` and later | Not started and deliberately gated | A trustworthy transaction, validated job, paid concierge evidence, and reliable delivery all pass first |

### Immediate queue — execute in this order

| Priority | Owner | Action | Tasks and required evidence |
|---:|---|---|---|
| 1 | Ryan | Supply the explicit 7,000-subscriber target date still required by the approved [`../../paid-launch-decision-record.md`](../../paid-launch-decision-record.md) | Complete `G0.2`; the approved 24-month horizon remains provisional until a calendar date is recorded |
| 2 | Ryan | Complete the business, legal, Stripe, support, vendor-capacity, and source-license decisions | `C1.1–C1.9`; entity/bank proof, four Price IDs, webhook/Portal settings, approved policy versions, and vendor confirmations |
| 3 | Ryan | Supply existing analytics, search, waitlist, support, and customer evidence; confirm GA4/GSC access | `M1.1`, `C1.8`, `D2.1`; exports or explicit “missing” entries plus working production access |
| 4 | Ryan + Claude | Apply the signed decisions to canonical docs and every customer/account surface; publish only the approved legal and pricing contract | `G0.15`, `C1.10–C1.11`, `M1.8`, `T1.3`, `T1.10`, `P4.10–P4.11` |
| 5 | Ryan | Recruit the discovery sample while commercial setup proceeds; do not pitch features during recruitment | `D2.2`; at least 15 primary supporters plus approximately 3 quantitative users and 3 creators |
| 6 | Joint | Run one real monthly transaction, then the complete monthly and annual cold-session rehearsals | `C1.12–C1.22`, `M1.9`; Stripe event IDs, amounts, receipts, durable entitlement, portal, cancel/refund results, webhook replay, GA4 events, and checkout-disable timing |
| 7 | Ryan + Claude | Conduct and synthesize recent-behavior interviews | `D2.3–D2.10`; consented notes, coded evidence, 10-of-15 recurring-job result, and at least 5 paid-pilot acceptances |
| 8 | Ryan + Claude | Only if priorities 1–7 pass, run the full-price concierge and record a go/iterate/kill verdict | `E3.1–E3.8`; at least 10 real buyers plus repeat-consumption and continuation evidence |
| 9 | Claude, then Ryan | Complete delivery-state tracking and shadow Club Watch notifications; Ryan alone approves live sends | `B4.9–B4.11`; two clean matchweeks, one quiet cycle, at least 50 reviewed updates, and the automation thresholds below |
| 10 | Joint | Only after all preceding gates pass, recruit and operate the ordinary-price controlled beta | `R5`; first 100 users, minimum 60-day cohort, support/refund coverage, and retention verdict |

**Do not begin yet:** live notification sends, broad launch, Creator, new paid modules, dynamic
pricing, Run-in/trial tests, Club Rate, paid community acquisition, or scale work. Those actions
remain downstream of evidence—not calendar—gates.

## Outcome and strategic decision

The approved business objective is **7,000 active paid subscribers**. Ryan still needs to set its
explicit target date. The approved definitions are:

- **Active paid:** a subscriber with a current paid entitlement who is not refunded, expired, or in
  an unrecovered failed-payment state. A scheduled cancellation remains active until the paid
  entitlement actually expires.
- **Engaged paid:** an active paid subscriber who consumed at least one core Club Watch value event
  in the last 30 days.

The 7,000 target uses active paid. Engaged paid is the leading indicator that those subscriptions
will survive.

The central paid job is:

> **Tell me what changed in my club's season, why it changed, and what the next match can change—
> without making me remember to check.**

The recommended customer-facing plan name is **Entenser Club Watch**. Backend identifiers may remain
`intel` until a safe migration is worthwhile.

The strategic boundary is:

> **Free lets a fan look up the current answer. Paid keeps watch, explains meaningful changes, and
> prepares the fan for what comes next.**

The Club Rate is an acquisition mechanism, not the reason to subscribe. It is tested only after
ordinary-price customers repeatedly consume and retain the core outcome.

## Facts, hypotheses, and current recommendation

### Observed in the live product or repository

- Production pricing is empty and the paid transaction path is not yet operable.
- Planned launch pricing is $5.99/month or $59.99/year; $7.99/$79.99 exists as a later test.
- Current forecasts, club pages, public grading, open data, RSS, and one-match scenarios are strong
  free discovery and trust assets.
- Production copy now reconciles Home, Account, Support, pricing, and Intel around the approved
  Club Watch direction; final Account behavior and legal/customer claims still need explicit owner
  approval.
- Unapproved live delivery and Creator claims have been removed from the offer; notification
  delivery remains visibly unavailable pending its evidence gate.
- Durable followed-team stakes, briefings, alerts, and since-last-visit mechanics exist in some
  form, but the recurring customer loop has not been proven with paying users.
- Repository fixes and regressions now cover wrong-sport news, reset-like ±100 percentage-point
  movers, honest data states, and core identity/timestamp/probability contracts; the public site and
  API were smoke-verified after deployment, while the paid transaction remains unrehearsed.
- The repository contains no dependable baseline for traffic, registration, paid conversion,
  engagement, cancellation, churn, cohort retention, support themes, or testimonial volume.

### Hypotheses to validate

- Committed supporters of under-covered clubs in consequential season races will pay to understand
  what every result changes.
- One to three meaningful updates per matchweek can create enough recurring value to retain them.
- A club-first sample and outcome-led upgrade will convert better than a generic feature bundle.
- Team identity can create a referral loop, but only if Club Watch is valuable at ordinary price.
- Creators have higher willingness to pay, but they are a later, distinct workflow and tier.

### Recommended treatment of the 2026-08-17 milestone

Ryan approved this treatment in task `G0.10` on 2026-07-29:

> Use 2026-08-17 as the earliest date for a **controlled, full-price Club Watch beta**, not an
> automatic broad public launch. Transaction readiness proves Entenser can take money; it does not
> prove that fans will keep paying.

If Ryan retains a broad public launch, the same commercial, legal, claim-truth, and data-quality
gates still block promotion. Club Rate remains later in either case.

## Ownership and operating protocol

| Owner | Owns |
|---|---|
| **Ryan** | Irreversible product choices; company, legal, tax, banking, and vendor accounts; prices and policies; customer interviews; community and partner relationships; publication and live-send approval; support and refunds; go/iterate/kill decisions |
| **Claude** | Repository changes; copy and prototype drafts; instrumentation; automated QA; data-quality checks; dashboards; experiment assignment; analysis; evidence memos; documentation |
| **Joint** | Ryan approves the brief or customer action; Claude prepares, implements, and analyzes it; Ryan records the resulting decision |

Claude must not form the company, accept legal terms, approve legal advice, impersonate Ryan in a
community, publish outreach, spend money, send customer broadcasts, or make a commercial
go/no-go decision.

Every experiment follows this order:

1. Claude writes a one-page brief with hypothesis, audience, treatment, guardrails, and stopping
   rule.
2. Ryan approves the brief and any customer-facing claim, price, spend, or outreach.
3. Claude implements and verifies the minimum test.
4. Ryan performs the external action; Claude confirms measurement.
5. Claude produces an evidence packet that separates observation from inference.
6. Ryan records **go**, **iterate**, or **kill** in the verdict log.

## Master sequence

Evidence gates control the order; durations are planning estimates, not promises.

| Stage | Timing after `G0` | Primary purpose | Exit gate |
|---|---:|---|---|
| `G0` Strategy and metric lock | 1–2 days | One audience, job, offer, boundary, and target definition | Ryan signs the decision record |
| `C1/M1/T1` Commercial, measurement, and trust foundation | 1–3 weeks, parallel | Become safe to charge and able to learn | Money path passes; offer is truthful; production events are visible |
| `D2` Recent-behavior discovery | 2 weeks, parallel with Stage 1 | Prove the recurring job exists | At least 10 of 15 primary fans demonstrate it; at least 5 accept a paid-pilot invitation |
| `E3` Full-price concierge | 4–6 weeks | Prove real payment and repeat use before automation | At least 10 real buyers plus repeat-consumption and renewal evidence |
| `P4/B4` Repackage and productize the proven loop | 3–6 weeks | Make the paid outcome coherent and reliable | Two matchweeks of clean shadow output; one coherent offer everywhere |
| `R5` Standard-price controlled beta | Minimum 60 days | Establish activation, retention, churn, and support baseline | D60 retention and value-consumption gates pass |
| `O6` Isolated offer tests | 4–6 weeks each | Test a run-in pass or trial without confounding the baseline | Gross margin per qualified visitor improves without worse retention |
| `CR7` Club Rate pilot | 14–21 days | Test team-powered incremental acquisition | Referral lift exceeds discount dilution; retention is not worse |
| `A8` Repeatable club-community distribution | 90 days per replication | Turn a successful campaign into a repeatable unit | At least 7 of 10 clubs hit the subscriber, CAC, and D90 gates |
| `K9` Gated scale to 7,000 | Ongoing | Scale traffic and cohorts without hiding churn | Each subscriber stage passes before the next |
| `S10/Q10` Strategic bets and competitive learning | Gate-dependent | Add new offers only when evidence calls for them | Each bet has its own paid-demand gate |

The clean causal order is:

> **Trustworthy transaction → demonstrated recurring job → full-price payment → reliable recurring
> delivery → retained ordinary-price cohort → isolated offer tests → Club Rate → repeatable
> club-community acquisition → gated scale.**

## Start here — the first 16 actions in strict order

Tasks on the same numbered row may run in parallel. A later row does not start until its named
dependency is satisfied.

| Order | Ryan | Claude | Dependency/output |
|---:|---|---|---|
| 1 | Answer `G0.1–G0.10` | Turn the answers into the `G0.12` decision record | One approved audience, job, boundary, price, target definition, and August decision |
| 2 | Begin/continue `C1.1–C1.9` external setup | Build the paid-claim matrix `T1.9` and measurement dictionary `M1.2` | Can run as soon as `G0` is clear |
| 3 | Supply available analytics, support, waitlist, and customer evidence (`M1.1/D2.1`) | Record known/estimated/missing baselines (`M1.10`) | No missing-data delay |
| 4 | Approve the final legal and price claims | Repair trust defects and reconcile customer-facing claims (`T1.*`) | Claim truth before traffic |
| 5 | Confirm GA4/GSC/vendor access | Implement and verify the funnel and lifecycle events (`M1.4–M1.9`) | Measurement before experiments |
| 6 | Recruit interview participants (`D2.2`) | Prepare screener, interview guide, and shortlist (`D2.6–D2.7`) | Primary segment and pilot clubs selected |
| 7 | Conduct recent-behavior interviews (`D2.3–D2.5`) | Synthesize evidence (`D2.8–D2.10`) | `D2` job gate |
| 8 | Complete Stripe/legal/vendor setup | Populate pricing/legal routes and verify fail-closed behavior | Ready for a real transaction |
| 9 | Operate test accounts and Stripe | Run monthly/annual purchase → portal → cancel → refund rehearsal (`C1.12–C1.15`) | Commercial gate |
| 10 | Approve the honest offer that can be delivered now | Implement the coherent Club Watch copy and free boundary (`P4`) | No unapproved email or archive promise |
| 11 | Recruit 30–50 qualified full-price prospects | Prepare concierge assets and measurement (`E3.5–E3.7`) | `D2` and commercial gates |
| 12 | Sell, onboard, support, and interview the concierge cohort | Generate/review updates and report weekly | Four-to-six-week `E3` test |
| 13 | Record go/iterate/kill | Scope only the loop proven by `E3` | Automation decision |
| 14 | Approve notification controls and live sends | Build and shadow-test `B4` for two matchweeks | Reliability gate |
| 15 | Recruit the first 100 ordinary-price beta users | Operate and report the minimum 60-day `R5` cohort | Normal-price retention baseline |
| 16 | Approve one isolated next test | Run a Run-in/trial test, then Club Rate only after its prerequisite | No confounded offer test |

---

## G0 — Lock the strategy and measurement contract

**Dependency:** none  
**Do not build yet:** new leagues, more Intel modules, Creator tier, localization, dynamic group
billing, rivalry tables, or a mature-vault sales story.

### Customer decision

| Segment | Need and behavior | Current alternatives | Willingness to pay | Role |
|---|---|---|---|---|
| Committed supporters of under-covered clubs in active races | Repeatedly piece together what results mean for title, promotion, playoff, qualification, or relegation outcomes | Standings, FotMob/Sofascore alerts, club forums, local reporters, free forecasts | **Hypothesis:** medium at $5.99/$59.99 if the update is timely, specific, and recurring | **Primary** |
| Quantitative soccer fans | Explore probabilities, methods, trajectories, and scenarios across leagues | Opta, Forebet, ClubElo, open data, spreadsheets | Low to medium because raw analysis is abundant and free | Secondary acquisition/trust audience |
| Podcasters, writers, and newsletter creators | Need fast, defensible, reusable club/race explanations before publishing | Manual research, spreadsheets, score apps, newsroom tools | **Hypothesis:** higher at $19–$29/month if it saves weekly production time | Later separate tier |

Bettors are not the primary audience. Public positioning remains forecasting and season
interpretation, not picks, staking, profit, or affiliate conversion.

### Product portfolio decision

| Proposition | Recurring outcome and mechanism | Free/paid boundary | Value cadence and WTP | Place in plan |
|---|---|---|---|---|
| **Club Watch** | A supporter receives a meaningful movement alert, causal explanation, and next-match W/D/L stakes for the club and relevant rivals | Current answer and one complete sample are free; continuous monitoring, explanation, continuity, and additional clubs are paid | 1–3 meaningful moments per matchweek; test $5.99/month or $59.99/year | Core, `E3`–`R5` |
| **Run-in Navigator** | A supporter sees the routes, rival dependencies, and leverage across the final 6–12 matches | One-match scenario remains free; saved multi-match paths and ongoing run-in monitoring are paid | Match-triggered over a short high-stakes window; test $19–$29 once | Seasonal wedge, `O6/S10` |
| **Forecast Memory and Receipts** | A supporter can revisit what Entenser believed, why it changed, and how accurate it was for this club | Public grading and current season remain free; private continuity starts at paid activation | Weekly/season-long renewal support; not yet a standalone price claim | Retention asset, `R5/S10` after history matures |
| **Creator Briefing Studio** | A creator saves preparation time with defensible, reusable explanations, drafts, and derived exports | Public pages stay citeable; saved workflows, scheduled briefs, and branded derived outputs are paid | Weekly; test $19–$29/month with design partners | Later separate tier, `S10` |

### Experience ladder

| User state | Concrete reason |
|---|---|
| Visit once | Look up a current club forecast, match probability, table, method, or public receipt |
| Return free | See updated forecasts, current movers, current race history, and weekly public accountability |
| Register | Follow one club across devices, receive a personalized home, and see one complete Club Watch sample |
| Subscribe | Stop monitoring manually; receive what changed, why it changed, and what the next match can change |
| Stay subscribed | Accumulate private continuity, get reliable value across match cycles, track rivals, and avoid missing consequential moments |

### Ryan checklist

- [x] `G0.1` Define whether the objective is subscriber count, revenue, or both.
- [ ] `G0.2` Set a target date for 7,000; use 24 months only as a provisional model horizon.
- [x] `G0.3` Approve the primary audience above and keep bettors secondary/non-public.
- [x] `G0.4` Approve the core paid job and Club Watch customer-facing name.
- [x] `G0.5` Approve the free/registered/paid boundary in `P4`.
- [x] `G0.6` Approve $5.99/month and $59.99/year as the clean ordinary-price baseline.
- [x] `G0.7` Confirm no trial at initial launch; keep the 30-day guarantee and test a trial later.
- [x] `G0.8` Select 5–8 validation clubs with consequential races, good data, and reachable fans.
- [x] `G0.9` Freeze new leagues, additional Intel modules, Creator, and dynamic pricing until their gates.
- [x] `G0.10` Decide whether 2026-08-17 becomes the recommended controlled beta or remains a broad
  launch target.

### Claude checklist

- [x] `G0.11` Consolidate the audit, launch plan, competitive analysis, and Club Rate into this one
  active plan.
- [x] `G0.12` Draft the one-page decision record for `G0.1`–`G0.10`.
- [x] `G0.13` Preserve `intel` as an internal entitlement alias if a rename would create migration
  risk.
- [x] `G0.14` Create a growth-experiment ledger separate from the model experiment protocol.
- [x] `G0.15` Add every approved durable decision to the correct canonical documentation.

**Exit gate:** one audience, one job, one ordinary price, one boundary, one target definition, and
one commercialization decision are signed. No downstream experiment may silently change more than
one of them.

---

## C1/M1/T1 — Commercial, measurement, trust, and claim-truth foundation

These tracks run in parallel after `G0`. No broad promotion starts until all four gates pass.

### C1 — Ryan makes the business capable of charging

- [ ] `C1.1` Complete the Ohio single-member LLC, statutory-agent and mailbox setup, EIN, operating
  agreement, business bank account, and tax/compliance review in `STATUS.md`.
- [ ] `C1.2` Decide the final legal name, DBA usage, governing law, refund scope, refund access,
  support address, tax posture, and whether international buyers are accepted initially.
- [ ] `C1.3` Activate Stripe with the legal entity, bank, and identity verification.
- [ ] `C1.4` Create four immutable Stripe Prices:
  - launch monthly: $5.99;
  - launch annual: $59.99;
  - inactive future-test monthly: $7.99;
  - inactive future-test annual: $79.99.
- [ ] `C1.5` Configure the production webhook, Customer Portal, cancellation, payment-method updates,
  receipts, refunds, failed-payment behavior, and launch/standard price variables.
- [ ] `C1.6` Confirm Vercel commercial capacity, Resend capacity, `support@entenser.com`, and the
  support/refund response schedule.
- [ ] `C1.7` Approve Terms, corrected Privacy Policy, 30-day refund policy, auto-renewal disclosure,
  independent-supporter/club-affiliation language, and cancellation terms.
- [ ] `C1.8` Confirm GA4 and Google Search Console ownership and submit the sitemap.
- [ ] `C1.9` Review data-source licenses before historical bulk exports, embeds, creator
  redistribution, or branded exports. Never sell raw third-party data.

### C1 — Claude completes and proves the money path

- [ ] `C1.10` Populate public pricing and show the actual amount before checkout; remove “See price at
  checkout.”
- [ ] `C1.11` Publish Ryan-approved Terms, Privacy, refund, cancellation, and affiliation language
  beside checkout.
- [ ] `C1.12` Verify magic-link sign-in, checkout, durable entitlement, new-session access, Account,
  billing portal, cancellation, refund, account export/deletion, and webhook idempotency.
- [ ] `C1.13` Run both monthly and annual cold-session rehearsals with Ryan and record Stripe event
  IDs and resulting entitlement states.
- [ ] `C1.14` Rehearse disabling new checkout in under five minutes without revoking valid
  entitlements.
- [x] `C1.15` Verify production fails closed if a required pricing, webhook, or entitlement dependency
  is absent.

### M1 — Instrument before experimenting

GA4 is the canonical production analytics implementation. Retire stale Plausible setup instructions
unless Ryan deliberately chooses to add a second tool.

- [ ] `M1.1` Ryan supplies or exports all available traffic, search, waitlist, email, support,
  subscription, refund, cancellation, and engagement data. Missing data is recorded as missing.
- [x] `M1.2` Claude writes a data dictionary for qualified club-intent visitor, newly eligible
  visitor, registration, activation, paid start, active paid, retained paid, voluntary churn,
  involuntary churn, pause, reactivation, and referral acquisition.
- [x] `M1.3` Define activation as: user follows a club and consumes one complete personalized Club
  Watch update.
- [x] `M1.4` Instrument:
  `club_page_view → track_club → registration_start → registration_complete → sample_update_view →
  upgrade_view → checkout_start → purchase`.
- [x] `M1.5` Instrument core value events: material-change explanation viewed, match-stakes viewed,
  since-last-visit viewed, scenario run/saved, alert or briefing sent/delivered/opened/clicked,
  return visit, and notification-setting change.
- [x] `M1.6` Join Stripe lifecycle states: purchase, renewal, cancellation requested, expiration,
  refund, failed payment, recovery, pause, and reactivation.
- [x] `M1.7` Attach club, competition, country, device, landing page, campaign, referrer, creator,
  experiment cell, and Club Rate milestone to relevant events.
- [x] `M1.8` Add cancellation reasons, support taxonomy, and consented testimonial capture.
- [ ] `M1.9` Verify the complete GA4 funnel and Stripe reconciliation in production before reading an
  experiment.
- [x] `M1.10` Create baseline and weekly scorecards with known/estimated/missing labels.

### T1 — Claude repairs trust and product truth before acquisition; Ryan owns incident response

- [x] `T1.1` Fix non-football stories entering league news.
- [x] `T1.2` Fix ±100 percentage-point mover artifacts; label first observations, resets, and missing
  baselines instead of presenting them as real movement.
- [x] `T1.3` Reconcile club numbers, timestamps, names, and competition identity across static,
  interactive, personalized, email, and share-card surfaces.
- [x] `T1.4` Replace a universal “live” claim with honest states such as fully simulated, fixtures
  limited, results only, stale, or unavailable.
- [x] `T1.5` Show freshness, supported depth, and known league limitations before checkout.
- [x] `T1.6` Add cross-surface regression tests for probabilities, trajectories, mover values,
  timestamps, club identity, and competition identity.
- [x] `T1.7` Create an incident checklist for bad data or notifications; Ryan owns customer response
  and Claude owns diagnosis and correction.
- [x] `T1.8` Preserve public methodology, calibration, model health, misses, and model-vs-market
  evidence as free trust assets.

### T1 — Reconcile every paid claim

- [x] `T1.9` Claude creates a claim matrix for Home, pricing, Account, Support, Intel, email capture,
  legal pages, team pages, runbooks, and launch announcements.
- [ ] `T1.10` Ryan approves one behavior for Account, billing management, cancellation, exports,
  notification state, and local-versus-durable favorites; Claude makes every surface match.
- [x] `T1.11` Remove “full team pages” as a paid benefit.
- [x] `T1.12` Keep current/open CSVs free; promise historical or bulk derived exports only after
  license review and implementation.
- [x] `T1.13` Keep one-match/current what-if free; gate only saved or multi-match paths.
- [x] `T1.14` Do not sell “ad-free” as a feature when no ads exist. If retained, frame it only as
  supporter-funded independence.
- [x] `T1.15` Describe history as accumulating private continuity, not a mature “vault.”
- [x] `T1.16` Either pass two matchweeks of shadow email QA plus one quiet-mode cycle and obtain
  Ryan's live-send approval, or remove alerts/briefings from paid claims until approved.
- [x] `T1.17` Replace stale outward-facing “no paywall/no backend/non-commercial” launch copy.
- [x] `T1.18` Update the old Creator/two-price runbook to the one-plan, four-price reality or retire it.
- [x] `T1.19` Unify Account with real authenticated state and put billing self-service where the site
  says it lives.

### August operational gates retained from the prior launch plan

| Date | Gate and owner |
|---|---|
| By 2026-08-02 | Ryan completes business/Stripe/legal choices; Claude records any resulting blocker |
| 2026-08-03–09 | Claude publishes approved legal pages; Joint completes first full transaction |
| 2026-08-10 | Joint rehearses monthly and annual purchase, cancellation, and refund |
| 2026-08-14 | Ryan approves final pricing/legal/customer copy; content freeze |
| 2026-08-15 | Claude confirms green workflows; money-path fixes only after code freeze |
| 2026-08-16 | Joint production preflight and checkout-disable rehearsal |
| 2026-08-17 | Open only if all gates pass and Ryan can monitor for three hours |
| 2026-09-30 | Ryan records an interim keep/change/kill/extend decision from transaction, conversion, concierge, support, league, geography, and available early-retention evidence; set the definitive D60 date |

### Transaction and preflight evidence checklist

- [ ] `C1.16` Joint: monthly cold-session magic link succeeds and checkout displays/charges $5.99.
- [ ] `C1.17` Joint: monthly receipt and webhook succeed; Club Watch access is immediate and survives a new
  session.
- [ ] `C1.18` Joint: monthly Account, export/deletion permissions, portal, cancellation, refund, and final
  entitlement state are correct; webhook replay is a no-op.
- [ ] `C1.19` Joint: repeat `C1.16–C1.18` with the $59.99 annual price and explicit guarantee
  disclosure.
- [ ] `C1.20` Ryan approves all final legal, pricing, support, waitlist, and outreach copy; target
  communities' commercial-post rules are recorded.
- [ ] `C1.21` Claude verifies required production variable names, config endpoint, GA4 events,
  static/live-data/API/webhook/email health, and green deploy workflows.
- [ ] `C1.22` Jointly run the last cold-session sign-in/checkout smoke test and checkout-disable
  rehearsal after the final deploy.
- [ ] `C1.23` Ryan confirms the first-three-hours monitoring and refund/support schedule before
  opening checkout.

**Commercial exit:** both billing intervals complete through refund and entitlement reconciliation.  
**Measurement exit:** production events reconcile to test users and Stripe.  
**Trust exit:** no known serious data inconsistency or false paid promise.  
**Launch safety:** wrong price, paid-without-access, duplicate charge, unsafe entitlement, or a
money-path 5xx disables new checkout and triggers affected-customer refunds.

---

## D2 — Prove the recurring job with recent behavior

This work can start while Ryan finishes external commercial setup.

### Ryan

- [ ] `D2.1` Export or forward existing support feedback, waitlist responses, testimonials, direct
  messages, and cancellation evidence to Claude with personal data minimized.
- [ ] `D2.2` Recruit at least 21 people: at least 15 committed fans from the selected clubs, about 3
  quantitative users, and about 3 creators.
- [ ] `D2.3` Conduct the interviews personally. Ask about the most recent real matchweek, the last
  time they sought a season answer, the tools used, time spent, frustration, and what they paid for.
- [ ] `D2.4` Ask permission separately for recording, product follow-up, pilot invitation, and any
  attributable quote.
- [ ] `D2.5` Invite qualified primary users to a paid concierge pilot; praise without a purchase or
  reservation is not willingness-to-pay evidence.

### Claude

- [x] `D2.6` Create segment screeners and a recent-behavior interview guide that avoids pitching
  features.
- [x] `D2.7` Prepare the club/user shortlist using race stakes, data quality, site traffic if
  available, and community reachability.
- [ ] `D2.8` Code notes into recurring jobs, triggers, alternatives, dissatisfaction, payment
  evidence, objections, offseason behavior, and disconfirming evidence.
- [ ] `D2.9` Separate primary fans, quant fans, and creators; do not average different jobs into one
  false persona.
- [ ] `D2.10` Produce an evidence memo and recommended changes to the proposition, sample, and pilot.

**Go:** at least 10 of the first 15 primary fans independently demonstrate a repeated
monitoring/interpretation job and at least 5 agree to enter a paid pilot.  
**Iterate:** 8–9 demonstrate it, or the job appears only during run-ins. Narrow the segment or test a
Run-in Pass.  
**Refocus:** fewer than 8 demonstrate it. Change audience or job before automating Club Watch.

---

## E3 — Full-price Club Watch concierge

**Dependency:** safe money path, measurement, controlled trust defects, and at least five qualified
pilot commitments.  
**Do not add Club Rate:** a discount here would conceal willingness to pay.

### Experiment brief

| Element | Requirement |
|---|---|
| Hypothesis | Committed fans will pay ordinary price and repeatedly consume “what changed, why, and what next” |
| Audience | 30–50 qualified non-friend prospects across 5–8 clubs |
| Minimum product | Manually reviewed post-result movement explanation, relevant-rival context, and match-morning W/D/L stakes for four to six weeks |
| Price | Real $5.99 monthly purchase, $59.99 annual purchase, or clearly refundable paid reservation |
| Primary metrics | Prospect→paid, updates consumed per buyer, second-month choice/renewal intent, refunds, qualitative replacement value |
| Minimum evidence | At least 10 real buyers, two match cycles per club, and four weeks of behavior |

### Ryan

- [ ] `E3.1` Recruit prospects, disclose the concierge nature, collect payment, onboard them, and own
  support/refunds.
- [ ] `E3.2` Avoid friends-and-family as the primary evidence and record acquisition source.
- [ ] `E3.3` Speak with every buyer and a sample of non-buyers after at least two update cycles.
- [ ] `E3.4` Ask what they would use if Entenser disappeared and whether free lookup is sufficient.

### Claude

- [x] `E3.5` Build club-selection, briefing, evidence-review, delivery, and feedback templates.
- [ ] `E3.6` Generate candidate explanations and stakes; flag low-confidence or trivial changes for
  manual review.
- [x] `E3.7` Track delivered, viewed, clicked, ignored, corrected, and support-triggering updates.
- [ ] `E3.8` Produce weekly evidence and a final go/iterate/kill memo.

**Go:** at least 20% buy, at least 60% consume half or more of updates, and at least 70% of buyers
renew, choose a second month, or make an equivalent binding continuation choice.  
**Iterate:** 10–19% buy with strong repeat use and a clear objection that packaging can address.  
**Kill/refocus:** under 10% buy, fewer than half repeatedly consume, or most buyers say free lookup
solves the job.

---

## P4/B4 — Repackage and productize only the proven loop

Preparation may begin earlier; the automated scope is committed only after `E3`.

### P4 — Approved free/registered/paid boundary

Claude must encode one entitlement matrix used by product, pricing, copy, support, and tests.

| Public without registration | Registered free | Club Watch paid |
|---|---|---|
| All current forecasts, standings, team pages, and match probabilities | One followed club and league synced across devices | Continuous monitoring for the followed club, relevant rivals, or additional clubs |
| Public methodology, grading, model health, receipts, and limitations | Personalized home and durable favorites | Immediate material-movement and threshold monitoring |
| Current trajectories, race history, and top movers | One complete personalized Club Watch sample, including a frozen club-season history path | Integrated updating club-season history plus full causal explanation of the change |
| One-match current what-if | High-level weekly club summary | Match-morning win/draw/loss stakes |
| Current open-data downloads and RSS, subject to licensing | Notification preferences and identity continuity | Since-last-visit feed and private forecast timeline |
| Crawlable club and league discovery pages | Upgrade after demonstrated value | Saved multi-match paths and deeper derived history/exports when available |

### P4 — Claude implements conversion moments after Ryan approves the boundary

- [x] `P4.1` After a fan selects or pins a club: show the personalized home and sample.
- [x] `P4.2` After a meaningful movement: reveal the movement, preview the cause, and offer continuous
  explanation.
- [x] `P4.3` Before a high-leverage match: show one free stake preview and offer ongoing club/rival
  monitoring.
- [x] `P4.4` After a one-match scenario: offer saved paths and automatic monitoring, not access to the
  scenario just used.
- [x] `P4.5` After the first complete personalized update: ask whether Entenser should keep watch.
- [x] `P4.6` At a genuine limit such as additional clubs, private continuity, or delivery frequency;
  never at an arbitrary pageview count.

### P4 — Messaging pack

**Primary value proposition**

> Entenser turns every result into a clear update on your club's season: what changed, why it
> changed, and what the next match can change.

**Homepage**

> **Know what every match means for your club's season.**  
> Follow your club once. Entenser watches the race, explains every meaningful change, and shows what
> the next result can do. Current forecasts remain free.

Primary CTA: **Track my club**  
Secondary CTA: **Explore free forecasts**

**Three paid benefits**

1. **Never miss a season-changing result.** Get an update when your club or a relevant rival
   materially changes the race—not another stream of score alerts.
2. **Understand why the odds moved.** See the result, rival result, schedule change, or new evidence
   behind the movement.
3. **Know what the next match can change.** Compare the win, draw, and loss paths before kickoff.

**Club-specific upgrade**

> **Keep watch on [Club].** You have the new forecast. Club Watch will tell you why it changed,
> alert you at the next meaningful move, and show what [next match] can change.

**Pricing-page narrative**

> Every current forecast remains free. Club Watch is for supporters who do not want to repeatedly
> check tables, apps, and prediction pages to work out what changed. Follow your club once and
> Entenser keeps watch: meaningful movement, the cause, relevant rivals, and the stakes in the next
> match. Start monthly at $5.99 or save with a year at $59.99. The first billing period is protected
> by the published 30-day guarantee.

**Strongest objections**

| Objection | Answer |
|---|---|
| “Scores and notifications are free.” | Yes. Club Watch is not another score alert; it explains what the result changed in the season race and what comes next. |
| “The forecasts are already free.” | They remain free. The subscription replaces repeated monitoring and interpretation, not access to today's number. |
| “Predictions can be wrong.” | They can. Entenser publishes probabilities, limitations, calibration, and misses; paid continuity makes the record more auditable, not less. |
| “I do not want more notifications.” | Defaults are material-change only, with weekly, match-morning, quiet, and unsubscribe controls. No artificial daily movement. |
| “My league has thinner data.” | Coverage and freshness are disclosed before purchase. Unsupported experiences are not sold as equivalent. |
| “My club may have nothing to play for.” | Use pause/offseason controls or a Run-in Pass; do not pretend a year-round plan is right for every fan. |
| “Why not FotMob, Sofascore, or a free model?” | Those are strong substitutes for scores, statistics, alerts, or raw probabilities. Club Watch's testable difference is continuous club-season interpretation. |

### P4 — Claude implementation

- [x] `P4.7` Replace generic forecast/model-first hero copy with the approved outcome and proof.
- [x] `P4.8` Replace the 26-module bundle with the three benefits above.
- [x] `P4.9` Add “Track this club” to every static and interactive club page.
- [x] `P4.10` Rename customer-facing Intel references to Club Watch after Ryan approves.
- [ ] `P4.11` Make prices, guarantee, cancellation, coverage, and free boundary explicit everywhere.
- [x] `P4.12` Add the objection answers to pricing/support and remove any claim not currently
  deliverable.

### B4 — Claude product implementation

- [x] `B4.1` Unify local favorites and authenticated account state around one durable club identity.
- [x] `B4.2` Build club-first registration and migrate existing favorites without silent loss.
- [x] `B4.3` Deliver one complete free personalized sample immediately after club selection.
- [x] `B4.4` Harden material-change detection with percentage-point and target-threshold rules.
- [x] `B4.5` Generate evidence-linked causes: own result, rival result, schedule change, or new model
  evidence; do not invent certainty.
- [x] `B4.6` Deliver match-morning win/draw/loss stakes.
- [x] `B4.7` Deliver a since-last-visit summary and start a private timeline at paid activation.
- [x] `B4.8` Add material-only, weekly-only, match-morning, quiet, pause, and unsubscribe controls
  with frequency caps.
- [x] `B4.9` Track sent, delivered, opened, clicked, failed, corrected, duplicated, and suppressed
  states.
- [ ] `B4.10` Run two matchweeks plus one quiet-mode cycle in shadow; review at least 50
  representative updates before Ryan approves live email.
- [ ] `B4.11` Target roughly 1–3 meaningful moments per matchweek, not manufactured daily contact.

**Automation gate:** zero wrong-team, wrong-outcome, wrong-price, or duplicate messages in the final
shadow cycle; at least 95% successful delivery; at least 80% of reviewed candidates judged worth
sending; every low-data league limitation appears before purchase.

### Experiment 2 — Club-first registration plus one complete sample

| Item | Definition |
|---|---|
| Hypothesis | Showing the full club-specific outcome before asking for money increases activation, return, and paid conversion |
| Audience | New registered users |
| Minimum implementation | Magic link → club selection → synced follow → complete sample → paid continuation |
| Minimum evidence | 300 registrations and four weeks of cohort observation |
| Confirm | At least 70% select a club; D30 return improves at least 25%; at least 5% of activated users pay |
| Invalidate | Registrations rise without return or paid conversion |
| Owners | Ryan approves the boundary; Claude implements and analyzes |

### Experiment 3 — Outcome-led upgrade message

| Item | Definition |
|---|---|
| Hypothesis | Actual club movement, cause preview, and next-match stakes outperform a generic feature bundle |
| Audience | Users who follow a club, view its movement, or run a scenario |
| Control | Generic Intel/feature-led upgrade |
| Variant | Club name, real movement, cause preview, and next-match value |
| Directional minimum | About 1,000 qualified exposures per cell or at least 30 total checkout starts |
| Confirm | At least 50% more checkout starts and 30% more paid conversion without reducing free activation |
| Invalidate | Under 15% lift or more clicks without more purchases |
| Owners | Ryan approves the offer; Claude assigns, implements, and analyzes |

At a 1% paid baseline, thousands of qualified exposures per cell may be required for a confident
conversion conclusion. The directional minimum does not justify overstating statistical certainty.

---

## R5 — Standard-price controlled beta and retention baseline

**Dependency:** `C1/M1/T1`, `E3` go/iterate evidence, and `B4` reliability gate.  
**Minimum duration:** 60 days. Annual cash collection is not retention evidence.

### Ryan

- [ ] `R5.1` Recruit the first 100 ordinary-price users across at least 8 clubs without Club Rate.
- [ ] `R5.2` Monitor support, approve sends, process refunds, and interview every cancellation plus a
  sample of active users.
- [ ] `R5.3` Keep the 30-day guarantee and make pause/cancellation plain before purchase.
- [ ] `R5.4` Record the 2026-09-30 interim keep/change/kill/extend decision even if evidence is
  incomplete, name the missing evidence, and set the definitive D60 decision date; silent drift is
  not valid.

### Claude

- [ ] `R5.5` Report D7, D30, D60, D90, monthly, and annual survival by club, source, plan, activation,
  and core-value consumption.
- [ ] `R5.6` Separate voluntary churn, refunds, failed payment, seasonal pause, and reactivation.
- [ ] `R5.7` Track time to first value and whether a buyer consumes at least two meaningful core
  events per month.
- [ ] `R5.8` Analyze retention by active race, safe mid-table, clinched, eliminated, and offseason.
- [ ] `R5.9` Add dunning, clear grace periods, pause, preseason restart, and value-triggered win-back
  paths only after Ryan approves the policies.
- [ ] `R5.10` Request testimonials only after multiple valuable updates; store explicit publication
  consent.
- [ ] `R5.11` Produce a weekly cohort report and a 60-day baseline memo.

**Go to acquisition testing:** at least 91% D60 paid retention; refunds at or below 5%; at least 50%
of buyers consume two core value events per month; at least 5% activated-user→paid conversion; and
no one club represents more than 30% of paid users.  
**Halt acquisition:** implied monthly churn exceeds 5%, serious trust defects recur, or core-value
consumption falls below 40%.  
**Long-run target:** approximately 3% monthly churn, equivalent to about 94% two-month survival;
at 7,000 subscribers, moving from 5% to 3% avoids roughly 140 replacement acquisitions every
month.

---

## O6 — Isolate price, trial, and seasonal-offer tests

Do not combine a price, trial, onboarding, proposition, and referral change in one experiment.
Ryan approves every price, policy, and customer-facing treatment; Claude implements, assigns, and
analyzes it.

- [ ] `O6.1` Use $5.99/$59.99 as the ordinary-price baseline.
- [ ] `O6.2` Keep $7.99/$79.99 inactive until ordinary-price conversion and D60/D90 retention exist.
- [ ] `O6.3` Compare no trial plus one complete free sample against a two-matchweek, two-meaningful-
  update, or 14-day card-required trial. A seven-day trial may contain no event.
- [ ] `O6.4` Compare monthly and annual cohorts by activation and product use; do not label annual
  prepayment “retained.”
- [ ] `O6.5` Test a $19–$29 Run-in Pass for clubs with 6–12 consequential matches remaining.
- [ ] `O6.6` Model price, fees, taxes, refunds, credits, support, and expected retention before any
  Club Rate floor.
- [ ] `O6.7` Before launch, Claude sets the sample from observed baseline rates. Do not call a winner
  with fewer than 50 paid starts per cell or one successful test plus a replicated cohort. Keep only
  an offer whose D60 gross contribution per qualified visitor is at least 15% above control, whose
  D60 retention is at least 91%, and whose retention is no more than 5 percentage points below
  control. Otherwise label the result inconclusive or reject it.

---

## CR7 — Club Rate: test collective acquisition after ordinary-price value

**Not crazy; not first.** The team identity can create a visible referral loop, but discounts cannot
manufacture a reason to remain subscribed.

### Product rules

1. Use a 14–21 day, season-locked annual campaign or renewal credit—not a continuously floating
   monthly invoice.
2. Prices may fall during the campaign but never rise during the paid season or committed term.
3. Early buyers receive the best final rate, so waiting has no advantage.
4. Count only settled, non-refunded paid subscriptions after the applicable refund/trial window.
5. Show simple milestones and the next threshold; do not show customer-facing algebra.
6. Publish next-season requalification, refund, fraud, club-change, tie, and cancellation rules.
7. State that Entenser is independent and unaffiliated with the club unless a real agreement exists.
8. Match treatment and control clubs on race stakes, league, audience, traffic, and data quality.
9. Test clubs within comparable audience bands before attempting large-versus-small-club rules.

### Entry requirements and read windows

- [ ] `CR7.7` Reach roughly 120–150 ordinary-price subscribers across candidate clubs before
  starting the group test.
- [ ] `CR7.8` Plan for at least 1,000 qualified visits per arm for an initial directional acquisition
  read.
- [ ] `CR7.9` Do not declare a durable winner until roughly 50 paid acquisitions per arm or a
  successful replicated campaign.

The public campaign runs for 14–21 days. Claude may report acquisition and price-confusion signals
at close, but Ryan records the final go/iterate/kill only after the D60/D90 contribution and
retention windows mature.

### Stage CR7A — cheapest manual validation

| Step | Ryan | Claude |
|---|---|---|
| `CR7.1` Select cohorts | Approve six treatment and six matched control clubs | Recommend matches from data quality, traffic, race stakes, and reach |
| `CR7.2` Define rewards | Approve illustrative $10 annual-renewal credit at 25 settled paid and one free month or lower renewal at 50 | Model contribution and document rules |
| `CR7.3` Build campaign | Approve wording, unofficial status, deadline, and community fit | Build team progress page, settled counter, next milestone, invite link, attribution, and QA |
| `CR7.4` Recruit | Build genuine organizer/community relationships and publish/send the outreach | Prepare club-specific outreach drafts, share cards, UTMs, and response sheet |
| `CR7.5` Operate | Handle questions, exceptions, refunds, and public replies | Reconcile payments, referrals, credits, fraud flags, and experiment cells |
| `CR7.6` Decide | Record go/iterate/kill | Report incremental subscribers, contribution, delay, confusion, and D60/D90 retention |

Preferred campaign copy:

> **Join 37 fellow [Club] supporters who get every meaningful season update. Thirteen more unlock
> the next Club Rate for everyone. Join now—you receive the best rate reached.**

### Stage CR7A measures and decision

Measure subscriber share rate, referral visits, referred registration/activation/paid conversion,
paid referral coefficient, time-to-purchase, waiting behavior, net revenue after credits/fees/
refunds, cannibalization, support contacts, and 60/90-day retention versus control.

**Go:** at least 25% of existing subscribers share; each 10 paid subscribers generate at least 3
incremental paid subscribers; treatment growth exceeds the discount break-even lift; 60/90-day
gross contribution per qualified visitor beats control by at least 15%; retention is no worse by
more than 5 percentage points.  
**Kill/redesign:** price questions affect more than 10% of purchasers, prospects delay buying,
referrals mostly create free users, growth does not offset ARPU loss, retention is more than 5
percentage points below control, or absolute retention falls below the ordinary-price scale gate.

### Stage CR7B — season-locked group buy, only after CR7A succeeds

Test a simple annual campaign such as:

- 50 settled supporters unlock $49.99/year.
- 100 settled supporters unlock $44.99/year.
- Everyone receives the lowest threshold reached before the close.
- The rate is locked for the annual term or defined season.

An internal economic illustration is:

`Club Rate = min($5.99, $3.99 + $50 / settled paying supporters)`

| Settled supporters | Illustrative monthly rate | MRR |
|---:|---:|---:|
| 25 | $5.99 | $149.75 |
| 50 | $4.99 | $249.50 |
| 100 | $4.49 | $449.00 |
| 250 | $4.19 | $1,047.50 |

The formula is monotonic after the cap, but it is not a customer message and must not be encoded
before the full contribution model exists.

The acquisition lift needed merely to preserve recurring revenue is:

- $5.99 → $4.99: more than 20% additional subscribers;
- $5.99 → $4.49: more than 33%;
- $5.99 → $3.99: more than 50%.

- [ ] `CR7.10` Automate Stripe credits or locked pricing only after manual economics work.
- [ ] `CR7.11` Add settled-payment validation, anti-abuse controls, counter reconciliation, and
  renewal-price disclosure before automation.

---

## A8 — Build repeatable club-community distribution

Foundational SEO can continue during validation. Large promotion waits for the trust and retention
gates.

### Ryan

- [ ] `A8.1` Build real relationships with podcasters, newsletters, fan sites, supporter groups,
  moderators, and local reporters. Follow each community's commercial-post rules.
- [ ] `A8.2` Approve every outreach campaign and personally publish, send, disclose ownership, and
  answer replies.
- [ ] `A8.3` Treat creators as a distribution channel before commissioning a Creator product.
- [ ] `A8.4` Keep public content betting-free and decline affiliate growth that compromises the
  trust position.

### Claude

- [ ] `A8.5` Deploy and verify crawlable club pages, sitemap, canonical URLs, structured data,
  internal links, unique metadata, and “Track this club.”
- [ ] `A8.6` Create attributable club movement, next-match stakes, receipts, and race share cards.
- [ ] `A8.7` Rework the social calendar around club-specific “what moved and why,” while preserving
  public receipts, methods, current open data, and honest misses.
- [ ] `A8.8` Prepare—but never publish without Ryan—community drafts, creator notes, UTMs, response
  sheets, and support macros.
- [ ] `A8.9` Build a reusable club kit: landing page, organizer brief, share cards, referral links,
  campaign rules, and cohort dashboard.
- [ ] `A8.10` Track subscriber yield, CAC, activation, retention, and concentration by club, partner,
  and content format.
- [ ] `A8.11` Preserve useful current open data and test embeds only after source-license review.

### Channel sequence

1. Selected domestic and English-speaking under-covered clubs with reachable communities.
2. UK lower leagues if the first club playbook works; season forecasting, not betting.
3. Netherlands/Nordics with English-first marketing and localized league names.
4. Germany under an analytics-only public frame.
5. Italy and Spain last, localized and analytics-only, after VAT/consumer-law review.

Women’s leagues, MLS, NWSL, USL, EFL lower tiers, Scotland, and other underserved competitions are
candidate opportunity pools; data quality and community reach decide the actual pilots.

**Replication gate:** in a 10-club replication, at least 7 reach 25 active paid within 60 days.
Observe every cohort through day 90; median CAC must be at most $25, D90 retention at least 86% (the
approximate 5%-monthly-churn floor), paid referral coefficient at least 0.30, and no campaign may
cause material trust or community complaints.

---

## K9 — Work backward from 7,000

### Model

Starting from zero paid subscribers:

`new paid = MAU × newly eligible club-intent share × visitor→registration × registration→paid`

`active paid this month = prior active paid × (1 − monthly churn) + new paid`

Use newly eligible, qualified club-intent visitors rather than counting the same returning free user
as a fresh opportunity every month.

### What is known, estimated, or missing

| Input | Status on 2026-07-27 |
|---|---|
| Goal: 7,000 active paid | Known; target date and exact “active” definition still require `G0` approval |
| Planned $5.99/$59.99 launch price | Known plan; not live |
| Gross ARR at 7,000 | Arithmetic: about $419,930 at $59.99/year or $503,160 at $5.99 × 12, before fees, taxes, refunds, and discounts |
| 25k–100k MAU and 1%–3% paid category/SOM range | Prior repository estimate, not Entenser analytics |
| Actual MAU, qualified share, registration, activation, paid conversion | Missing |
| Actual churn, cohort survival, refunds, cancellations, use, and acquisition source | Missing |
| Scenario growth, conversion, and churn below | Estimated hypotheses |

### Scenarios

| Scenario | Start MAU / monthly growth | Newly eligible | Visitor→register | Register→paid | Monthly churn | Paid month 12 | Paid month 36 | First reaches 7,000 |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| Conservative | 25k / 1% | 25% | 3% | 5% | 7% | 83 | 159 | Not within 120 months |
| Expected | 25k / 3% | 40% | 5% | 8% | 5% | 443 | 1,370 | About month 90 at 347k MAU |
| Aggressive hurdle | 50k / 5% | 50% | 10% | 15% | 3% | 5,166 | 25,583 | About month 16 at 104k MAU |

These are scenario mechanics, not forecasts. The aggressive case requires unusually strong
activation, conversion, retention, and sustained traffic growth.

### Traffic and retention hurdle

| Scenario | Steady MAU to maintain 7,000 | Steady MAU to build 7,000 in 24 months | 12-month cohort survival | Replacements/month at 7,000 |
|---|---:|---:|---:|---:|
| Conservative | 1.31M | 1.58M | 41.9% | 490 |
| Expected | 219k | 309k | 54.0% | 350 |
| Aggressive hurdle | 28k | 54k | 69.4% | 210 |

The prior 25k–100k MAU envelope supports roughly 250–3,000 paid at 1%–3% conversion. Seven thousand
therefore requires either much more qualified traffic, materially stronger conversion/retention, a
repeatable club referral engine, or a mixed higher-ARPU business model.

### Three metrics that govern the goal

1. **Qualified newly eligible club-intent visitors.**
2. **Activated club follower → paid within 30 days.**
3. **D90 and month-12 paid cohort survival.**

- [ ] `K9.1` Claude replaces every scenario input with observed values as soon as measurement exists.
- [ ] `K9.2` Claude reports actual versus model monthly and attributes variance to traffic,
  eligibility, activation, conversion, churn, price, and discounts.
- [ ] `K9.3` Claude includes Club Rate ARPU, fees, credits, refunds, and net contribution.
- [ ] `K9.4` Ryan reviews whether 7,000 consumers remains the right objective versus a mixed model.
  For comparison, 1,500 creators at $25/month is about $450,000 gross ARR.
- [ ] `K9.5` Jointly use `100 club communities × 70 active subscribers` only as a portfolio
  hypothesis, not evidence of demand.

### Scale gates

| Subscriber stage | Question that must be answered before the next stage |
|---:|---|
| 0 → 100 | Will the primary segment pay ordinary price and consume the outcome repeatedly? |
| 100 → 250 | Does D60/D90 retention survive beyond a dramatic result or run-in? |
| 250 → 1,000 | Can multiple comparable clubs repeat the acquisition and retention result? |
| 1,000 → 3,000 | Do multiple channels/markets work without one-club or one-partner concentration? |
| 3,000 → 7,000 | Can churn remain near 3% while adding at least 210 replacement subscribers per month before net growth? |

Do not scale paid acquisition while monthly churn exceeds 5%, D90 is unproven, or Club Rate
contribution is below ordinary-price control.

---

## S10/Q10 — Strategic bets and ongoing competitive learning

Everything below has a place, but none outranks the core proposition and retention gates.

| Order | Bet | Ryan | Claude | Start condition |
|---:|---|---|---|---|
| 1 | Run-in Navigator / $19–$29 pass | Approve clubs, offer, and price | Prototype route/rival view and measure | Concierge or cancellation evidence shows seasonal demand |
| 2 | Forecast Memory and Receipts | Approve packaging | Keep accruing history; build private timeline and renewal test | 6–12 months of meaningful, trustworthy history |
| 3 | Creator Briefing Studio / $19–$29 month | Recruit design partners and take reservations | Prototype scheduled briefs and derived exports | Fan offer works; at least 10 creators show real paid/reservation demand |
| 4 | Offseason pause and restart | Approve policy | Implement pause, preseason restart, and win-back | Churn evidence shows seasonal value loss |
| 5 | Embeds/API | Obtain license review and approve terms | Build minimal derived/attributed version | Meaningful export use and licensing clearance |
| 6 | Localization and regional price | Approve market and legal/tax posture | Localize names/landing pages first, then UI | Non-branded search demand and comparable activation/conversion |
| 7 | Women's-football runway | Approve focus | Build distribution around reliable existing coverage | Selected leagues pass data-quality and audience gates |
| 8 | Standard price increase | Approve a clean test | Implement isolated $7.99/$79.99 cell | Ordinary-price retention and conversion are stable |

Do not build more leagues, a prediction game, mini-leagues, rivalry community, ads, or
betting-affiliate acquisition merely because they are available ideas. More coverage does not solve
the current conversion and retention constraint. A prediction game may be reconsidered only if core
retention fails for lack of personal stake and user research supports it.

### Competitive frame and response

| Substitute | What it makes free or easy | Entenser response |
|---|---|---|
| Forebet, Opta Analyst, ClubElo | Raw forecasts, rankings, and broad search discovery | Keep current answers free; win on continuous, auditable club-season interpretation |
| FotMob and Sofascore | Scores, news, statistics, and generic alerts at massive scale | Do not compete on score alerts; explain material season consequences and relevant rivals |
| Football Data Lab | Paid probability/bettor workflow near Entenser's price | Avoid bettor workflow as the lead; test whether fan interpretation is more recurring and defensible |
| The Athletic | Premium reporting at roughly the same annual spending decision | Sell time-saving, personalized continuity; do not pretend a thin content archive beats reporting |
| Stathead and creator tools | Power-user workflows with higher willingness to pay | Validate Creator Studio separately after the fan loop works |

Audit-era price and boundary anchors, to be reverified before a decision:

| Product | Observed anchor | Strategic meaning |
|---|---|---|
| Forebet, Opta Analyst, ClubElo | Core raw forecast/rating value is largely free | Raw probabilities cannot carry the paid offer |
| FotMob | About $1.99/month or $15.99/year, primarily ad removal | Generic score/news alerts are a cheap or free substitute |
| Sofascore Analyst | Paid match-analysis/prediction layer; exact current price must be rechecked | Incumbents can add analytics to a huge installed base |
| Football Data Lab | About £5.99/month or £57.50/year | Closest direct price anchor, but its job is bettor-oriented |
| Stathead | About $9/month | Power users pay for repeated research workflows |
| The Athletic | Roughly $7.99–$9.99/month or $71.99–$99.99/year by channel | Entenser's annual plan competes with professional reporting for wallet share |

All competitor prices and features age quickly. Reverify from primary sources before using them in
a decision or customer-facing comparison.

- [ ] `Q10.1` Claude rechecks pricing, trials, coverage, free/paid boundaries, and positioning
  quarterly.
- [ ] `Q10.2` Claude monitors Silver Bulletin for a revived club model.
- [ ] `Q10.3` Claude monitors FotMob/Sofascore for native season probabilities or deeper paid
  analysis.
- [ ] `Q10.4` Claude monitors Football Data Lab price and workflow; Forebet localization/SEO; Opta consumer
  experience; ClubElo/open-data; American Soccer Analysis/community; The Athletic, Stathead, and
  creator-tool prices.
- [ ] `Q10.5` Ryan continuously asks active, cancelled, and non-buying users which substitute they
  actually use.
- [ ] `Q10.6` Jointly review competitor changes, support themes, testimonials, experiments, and
  cohorts monthly; react only when the primary job is threatened or strengthened.

---

## Prioritized roadmap scorecard

Scores are 1–5. Higher impact/confidence is better; higher effort means more work.

### Immediate messaging and packaging

| Recommendation | Task IDs | Impact | Confidence | Effort | Time to learn | Primary lever |
|---|---|---:|---:|---:|---|---|
| Make the money/legal path operable | `C1.*` | 5 | 5 | 3 | 1–3 weeks | Foundation |
| Fix trust defects and false paid claims | `T1.*` | 5 | 5 | 3 | Days–3 weeks | Conversion + retention |
| Repackage as Club Watch with visible price | `P4.7–P4.12` | 5 | 4 | 2 | 1–2 weeks | Conversion |
| Add club-specific “Track this club” paths | `P4.1/P4.9` | 4 | 4 | 2 | 2–4 weeks | Registration + conversion |
| Establish GA4/Stripe lifecycle measurement | `M1.*` | 5 | 5 | 3 | 1–3 weeks | Both |

### Low-cost validation

| Recommendation | Task IDs | Impact | Confidence | Effort | Time to learn | Primary lever |
|---|---|---:|---:|---:|---|---|
| Recent-behavior interviews | `D2.*` | 5 | 4 | 2 | 2 weeks | Proposition |
| Full-price concierge | `E3.*` | 5 | 4 | 2 | 4–6 weeks | Conversion + retention |
| Club-first sample | Experiment 2 | 4 | 4 | 3 | 4–8 weeks | Activation + conversion |
| Outcome-led upgrade | Experiment 3 | 4 | 4 | 2 | Traffic-dependent | Conversion |
| Manual Club Rate credits | `CR7.1–CR7.6` | 4 | 3 | 3 | 14–21 days plus retention | Acquisition |

### Product improvements

| Recommendation | Task IDs | Impact | Confidence | Effort | Time to learn | Primary lever |
|---|---|---:|---:|---:|---|---|
| Unified account and club-first onboarding | `B4.1–B4.3` | 5 | 4 | 4 | 4–8 weeks | Activation + conversion |
| Alert → cause → next-match loop | `B4.4–B4.11` | 5 | 4 | 4 | 2 matchweeks + 60 days | Retention |
| Cohort, cancel, pause, dunning, and win-back | `R5.*` | 5 | 4 | 3 | 60–90 days | Retention |
| Referral/campaign attribution | `M1.7/CR7.*` | 4 | 4 | 3 | 1 campaign | Acquisition |

### Larger strategic bets

| Recommendation | Task IDs | Impact | Confidence | Effort | Time to learn | Primary lever |
|---|---|---:|---:|---:|---|---|
| Repeatable club-community engine | `A8.*` | 5 | 3 | 4 | 90 days/replication | Acquisition |
| Run-in Pass | `O6.5/S10` | 3 | 3 | 2 | 4–6 weeks | Seasonal conversion |
| Forecast Memory | `R5/S10` | 3 | 3 | 4 | 6–12 months | Retention |
| Creator Studio | `S10` | 4 | 2 | 4 | 6–10 weeks after interviews | ARPU + acquisition |
| Localization | `A8/S10` | 3 | 2 | 4 | One season/search cycle | Acquisition |
| More leagues | Deferred | 1 | 4 | 5 | Long | Neither current constraint |

---

## Five gaps, strongest bet, and immediate experiment order

### Five most important value-proposition gaps

1. The product gives strong free answers but does not yet prove a recurring paid outcome.
2. The primary paying audience is not explicit enough; the existing offer speaks to everyone.
3. Free, registered, and paid reasons overlap or contradict one another.
4. Alerts, explanations, and stakes are not yet a reliable, measured customer loop.
5. Trust, account, price, email, archive, and benefit claims do not consistently match reality.

### Strongest paid proposition

**Club Watch for committed supporters of under-covered clubs in consequential races:** follow once,
then receive every meaningful season movement, why it happened, and what the next match can change.

### Why users will pay

They are not paying for another probability. They are paying to stop repeatedly assembling the
season story from scores, standings, forums, and free models—and to avoid missing the moments that
change what their club can achieve.

### Recommended boundary

- **Public:** the current answer, public trust, current open data, and a one-match scenario.
- **Registered:** one synced club, personalized home, and one complete Club Watch sample.
- **Paid:** continuous monitoring, causal interpretation, relevant rivals, next-match stakes,
  private continuity, additional clubs, and saved/deeper workflows as they become real.

### First three experiments, in order

1. Full-price Club Watch concierge (`E3`).
2. Club-first registration plus one complete sample (Experiment 2).
3. Outcome-led, club-specific upgrade message (Experiment 3).

Club Rate is fourth and waits for a 60–90-day ordinary-price cohort.

### Assumptions most likely to block 7,000

- The recurring job may be intense only during dramatic run-ins rather than year-round.
- Too few qualified club-intent visitors may exist at the current traffic level.
- Fans may enjoy the explanation but still consider free lookup sufficient.
- Alerts may be too trivial, noisy, delayed, or occasionally wrong to retain trust.
- Monthly churn may remain near or above 5%, requiring at least 350 replacements per month at scale.
- Team referrals may not exceed the revenue dilution caused by the discount.
- Small-club communities may be reachable but too small; large-club fans may have abundant
  substitutes.
- Solo-operator support, editorial QA, email, and community work may not scale.
- Historical depth, offseason relevance, and creator demand may arrive too slowly.
- Legal, tax, licensing, club-affiliation, or data-quality constraints may limit expansion.

---

## Traceability: no recommendation is orphaned

| Analysis area | Task or gate |
|---|---|
| Primary and secondary customers | `G0` customer decision |
| Reasons to visit, return, register, subscribe, and remain | `G0` experience ladder; `P4/B4/R5` |
| Club Watch | `G0`, `E3`, `P4/B4`, `R5` |
| Run-in Navigator | `O6.5`, `S10` |
| Forecast Memory/Receipts | `B4.7`, `R5`, `S10` |
| Creator Briefing Studio | `A8.3`, `S10` |
| Free/account/paid boundary | `G0.5`, `P4` |
| Homepage, pricing, benefits, upgrade, objections | `P4` messaging pack |
| Pricing, guarantee, and trial | `C1`, `O6` |
| Best conversion moments | `P4.1–P4.6` |
| Trust and data defects | `T1.1–T1.8` |
| Conflicting paid claims and account state | `T1.9–T1.19` |
| Traffic, conversion, engagement, cancellation, and retention data | `M1`, `R5`, `K9` |
| User research, support feedback, and testimonials | `D2`, `M1.8`, `R5.10`, `Q10.5` |
| Three core validation experiments | `E3` and the two `P4/B4` experiment cards |
| Club Rate formula, milestones, fairness, fraud, referrals, and economics | `CR7` |
| Retention, offseason, pause, dunning, and win-back | `R5`, `S10` |
| SEO, club pages, social, syndication, community, and creator distribution | `A8` |
| Europe/localization, women's soccer, open data, and embeds | `A8`, `S10` |
| Conservative, expected, and aggressive path to 7,000 | `K9` |
| Priority, confidence, effort, time to learn, and lever scores | Roadmap scorecard |
| Competitors and adjacent willingness-to-pay anchors | `Q10` |
| Quarterly competitive monitoring | `Q10.1–Q10.6` |
| Deliberate non-betting position and no-more-leagues freeze | `G0`, `A8`, `S10` |
