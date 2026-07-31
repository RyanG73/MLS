# Club Watch growth measurement contract

**Prepared:** 2026-07-29  
**Canonical production analytics:** GA4  
**Billing source of truth:** Stripe  
**Entitlement and product-state cache:** Upstash

This document implements `M1.2` and defines the scorecard contract for `M1.4–M1.10`. Missing data
is never replaced with a guess.

## Population definitions

| Term | Operational definition | Source |
|---|---|---|
| Qualified club-intent visitor | A newly eligible visitor who opens a club page, opens a team profile, tracks a club, or arrives through a club/race campaign | GA4 |
| Newly eligible visitor | A qualified visitor with no prior paid entitlement and no qualifying exposure inside the experiment lookback window | GA4 + entitlement export |
| Registration | A unique account whose magic-link callback succeeds | Auth lifecycle ledger |
| Activation | A registered account that follows a club and views one complete personalized sample | Product lifecycle ledger |
| Paid start | First settled subscription purchase that grants a paid entitlement | Stripe webhook |
| Active paid | Current paid entitlement; excludes refund, expiration, and unrecovered `unpaid`; includes scheduled cancellation before entitlement expiry | Stripe + Upstash |
| Engaged paid | Active paid with at least one core value event in the trailing 30 days | Product lifecycle ledger |
| Retained paid | Active paid at the named cohort age (`D7`, `D30`, `D60`, `D90`) | Stripe cohort |
| Voluntary churn | Customer-requested cancellation that reaches paid entitlement expiry | Stripe lifecycle |
| Involuntary churn | Entitlement expires after failed-payment recovery is exhausted | Stripe lifecycle |
| Pause | Owner-approved seasonal pause state; not counted as active paid while access is paused | Stripe/product policy |
| Reactivation | A formerly expired, paused, or unpaid customer returns to a paid entitlement | Stripe lifecycle |
| Referral acquisition | A paid start carrying a settled referral/campaign identifier whose first qualified touch is attributable | GA4 + Stripe metadata |

## Event contract

Names use lower snake case. GA4 receives browser events; the server lifecycle ledger records the
authoritative account, billing, delivery, and entitlement events. No raw email, free-text notes, or
private journal content enters analytics.

### Acquisition and conversion

`club_page_view → track_club → registration_start → registration_complete → sample_update_view →
upgrade_view → checkout_start → purchase`

`begin_checkout` is emitted alongside `checkout_start` only to preserve GA4's standard ecommerce
report. A checkout redirect is not a purchase. `purchase` is emitted only after the Stripe webhook
has granted the entitlement.

### Core value

- `material_change_explanation_viewed`
- `match_stakes_viewed`
- `since_last_visit_viewed`
- `scenario_run`
- `scenario_saved`
- `return_visit`
- `notification_setting_change`

### Delivery

- `alert_sent`, `alert_delivered`, `alert_opened`, `alert_clicked`, `alert_failed`
- `briefing_sent`, `briefing_delivered`, `briefing_opened`, `briefing_clicked`, `briefing_failed`
- `delivery_corrected`, `delivery_duplicated`, `delivery_suppressed`

Shadow candidate reviews are stored in the private delivery ledger with a
bounded worth-sending decision and defect taxonomy. Review notes are not growth
events and never enter GA4 or the privacy-limited lifecycle ledger.

### Customer evidence

- `cancellation_reason_submitted`
- `support_request_categorized`
- `testimonial_consented`

Only the category and consent level enter the measurement ledger. Free-text
messages stay in the authenticated user's exportable and deletable account
record. Testimonials require explicit anonymous-publication consent; attaching
a name or other identifying detail requires a separate permission.

### Billing lifecycle

- `purchase`, `renewal`
- `cancellation_requested`, `expiration`
- `refund`, `failed_payment`, `payment_recovered`
- `pause`, `reactivation`

## Dimensions

Attach only where relevant:

`club_id`, `club_name`, `competition_id`, `competition_name`, `country`, `device`, `landing_page`,
`campaign`, `source`, `medium`, `referrer`, `creator`, `experiment_id`, `experiment_cell`,
`club_rate_milestone`, `plan`, `interval`, `price_tier`, `currency`, `value`.

Club identifiers are stable source IDs, not display names. Unknown values are omitted, never
invented. Experiment exposure is assigned before the treatment renders and remains sticky for the
defined experiment.

## Reconciliation rules

1. GA4 `purchase` count must equal unique settled Stripe purchase events after removing test users,
   duplicate webhook deliveries, refunds, and known internal rehearsals.
2. Stripe is authoritative for money; Upstash is authoritative for the currently served
   entitlement. Any mismatch is an incident.
3. Scheduled cancellation remains active until `current_period_end`.
4. Annual prepayment is a paid start, not retention.
5. A refund is reported separately from voluntary churn.
6. Missing GA4 access or a missing export marks the affected metric **missing**, not zero.

## Baseline as of 2026-07-29

| Input | Label | Value/evidence |
|---|---|---|
| Goal | known | 7,000 active paid; date awaiting `G0.2` |
| Planned ordinary price | known, not live | $5.99 monthly / $59.99 annual |
| Public club pages | built, deployment unverified | 1,444 pages in the last recorded build |
| Actual MAU and qualified club-intent visitors | missing | No GA4 export supplied |
| Registration and activation | missing | No production cohort export supplied |
| Paid starts, active paid, refunds, churn | known empty before launch / production reconciliation pending | Production pricing is empty in the latest verified status |
| Core-value consumption | missing | Lifecycle event code exists; no paying cohort |
| Cancellation and support themes | capture ready; observations missing | Stripe cancellation details and authenticated categorized feedback are implemented; no coded production sample exists |
| Testimonials with publication consent | capture ready; observations missing | Explicit anonymous-publication consent ledger exists; no consented production testimonial has been supplied |

## Weekly scorecard

Every row carries `known`, `estimated`, or `missing`, the observation window, numerator,
denominator, and source timestamp.

| Section | Required measures |
|---|---|
| Reach | MAU, newly eligible club-intent visitors, club page views, campaign/source mix |
| Activation | tracks, registrations, club selection rate, sample views, activation rate, time to first value |
| Revenue | checkout starts, paid starts, visitor→paid, activated→paid, MRR/ARR, interval and club mix |
| Value | explanation/stakes/since-last-visit consumers, events per buyer, engaged paid |
| Survival | D7/D30/D60/D90, voluntary churn, involuntary churn, refunds, pause, reactivation |
| Reliability | delivery success, duplicates, corrections, suppressed sends, trust incidents |
| Support | contacts by taxonomy, cancellation reasons, price confusion, guarantees used |
| Concentration | active paid and contribution by club, league, source, campaign, and experiment |
