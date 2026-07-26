# Paid Public Launch — 2026-08-17

**Canonical state:** [`../../STATUS.md`](../../STATUS.md)

**Technical reference:** [`../../CURRENT_STATE.md`](../../CURRENT_STATE.md)

This is the repository's single active execution checklist. It contains work and verdicts, not
background narrative. Update `STATUS.md` whenever a verdict changes production truth.

## Goal

A new visitor can sign in, purchase Intel monthly or annually, retain access across sessions,
manage billing, cancel, and receive a refund through the production domain.

## Launch gate

Launch only when all five are proven:

- [x] `api.entenser.com` resolves and serves the production API.
- [ ] Production uses durable KV, strong secrets, and fail-closed configuration.
- [ ] Monthly and annual Stripe prices, webhook, and Customer Portal work.
- [ ] Terms, refund policy, and accurate privacy policy are public.
- [ ] Monthly and annual dress rehearsals complete through refund and entitlement reconciliation.

## Verdict log

Append concise, dated results here, newest first. Include proof such as deployment run, Stripe event,
HTTP response, or test result. Do not copy implementation history from `PROJECT_HISTORY.md`.

- **2026-07-26 — production API domain and CORS verified.** Namecheap CNAME resolves through local,
  Cloudflare, and Google DNS; HTTPS `GET /v1/public/config` returns 200. Browser-origin preflight
  returns 204 with `Access-Control-Allow-Origin: https://entenser.com` and `Vary: Origin`.
- **2026-07-26 — crawlable club pages built; deployment pending.** The static acquisition build
  now emits 1,444 competition-scoped club forecasts plus league-to-club links and a 1,536-URL
  sitemap with no broken club links. Full suite: 1,676 passed, 14 skipped; final static contracts:
  21 passed. Production proof still requires the GitHub Pages deployment.
- **2026-07-26 — documentation reset.** `STATUS.md` is now the canonical current truth; this file
  is the only active execution plan. Completed and overlapping UX plans were retired after their
  open decisions moved to `STATUS.md`.
- **2026-07-26 — product-strategy recommendations shipped.** Durable Intel cursor, followed-team
  stakes/briefings, no-refit live-data refresh, and forecast-first public acquisition are live.
  Fast-refresh run `30205921705` completed successfully.
- **2026-07-26 — global shared ELO shipped.** Global Power is discoverable and shared `global_elo`
  is published across relevant league and team surfaces.
- **2026-07-25 — paid-path code hardened, configuration still absent.** Header normalization,
  fail-closed webhooks, billing lifecycle, pricing tiers, portal, refunds, and funnel events are
  implemented. Production still lists only the three Resend variables.

## Phase 0 — owner setup

These steps require Ryan's external account access or decisions.

### A. Domain and persistence

- [x] Attach `api.entenser.com` to the Vercel project.
- [x] Add the DNS record required by Vercel.
- [ ] Create an Upstash Redis database.
- [ ] Add its REST URL and token to Vercel Production.

**Proof:** custom-domain config endpoint returns 200; a test entitlement survives a new process.

### B. Secrets and runtime mode

- [ ] Generate strong independent values for `ACCESS_TOKEN_SECRET`, `ADMIN_TOKEN`, and
  `UNSUBSCRIBE_SECRET`.
- [ ] Set `PUBLIC_API_URL=https://api.entenser.com/v1`.
- [ ] Set `ENTENSER_ENV=production` only after its dependencies exist.
- [ ] Confirm the Vercel project is on a commercial plan.
- [ ] Confirm Resend has sufficient launch-day magic-link capacity.

**Proof:** production fails closed when a required dependency is intentionally absent, then returns
healthy after restoration.

### C. Stripe

- [ ] Complete Stripe business, bank, and identity activation.
- [ ] Create the four launch/standard monthly/annual Price objects listed in `STATUS.md`.
- [ ] Add all four Price IDs plus `STRIPE_SECRET_KEY` to Vercel Production.
- [ ] Register the production webhook and set `STRIPE_WEBHOOK_SECRET`.
- [ ] Enable cancellation and payment-method updates in the Customer Portal.

**Proof:** `/v1/public/config` exposes the intended launch prices and checkout returns a Stripe URL.

### D. Legal and measurement

- [ ] Decide the open terms in `legal-copy-draft-2026-07-25.md`.
- [ ] Confirm GA4 access and production event receipt.
- [ ] Verify the Google Search Console property and submit `/sitemap.xml`.
- [ ] Confirm the launch support inbox and monitoring window.

## Phase 1 — repository work after setup

- [ ] Publish Terms of Service.
- [ ] Publish the 30-day refund policy.
- [ ] Replace the outdated privacy language.
- [ ] Deploy the API with production configuration.
- [ ] Verify custom-domain CORS and browser authentication.
- [ ] Verify the GA4 funnel: `view_pricing → begin_checkout → purchase`.
- [ ] Audit paid-tier copy against the archive's measured depth.
- [ ] Confirm no raw third-party data is exposed by paid exports.

## Phase 2 — production dress rehearsal

Run on 2026-08-10 using a real device and a cold browser session.

### Monthly

- [ ] Magic-link sign-in succeeds.
- [ ] Checkout displays and charges the intended monthly price.
- [ ] Stripe receipt and webhook succeed.
- [ ] Intel access is available immediately and after a new session.
- [ ] Export and account deletion permissions are correct.
- [ ] Customer Portal opens.
- [ ] Cancellation produces the intended period-end state.
- [ ] Refund produces the intended entitlement state.
- [ ] Webhook replay is a no-op.

### Annual

- [ ] Repeat every monthly step with the annual Price.
- [ ] Confirm annual amount and guarantee exposure explicitly.

Record Stripe event IDs, entitlement state, and any failure in the verdict log.

## Phase 3 — freeze and preflight

### 2026-08-14 — content freeze

- [ ] Legal and pricing copy match production behavior.
- [ ] Every launch URL and UTM is final.
- [ ] Existing waitlist members have an approved launch message.
- [ ] Target communities' commercial self-promotion rules are checked.

### 2026-08-15 — code freeze

- [ ] Main and deployment workflows are green.
- [ ] Only owner-approved money-path fixes merge after this point.

### 2026-08-16 — preflight

- [ ] Verify all required Vercel Production variable names.
- [ ] Verify `GET https://api.entenser.com/v1/public/config`.
- [ ] Run a cold-session sign-in and checkout smoke test.
- [ ] Confirm static site, live-data overlay, API, webhook, and email health.
- [ ] Rehearse disabling new checkout in under five minutes.
- [ ] Confirm Ryan can monitor the first three launch hours.

## Phase 4 — launch

- [ ] Re-run the cold-session purchase smoke test after the final deploy.
- [ ] Post announcements only after the money path is green.
- [ ] Watch checkout/API errors continuously for the first three hours.
- [ ] Check Stripe payments and amounts hourly.
- [ ] Check support at scheduled windows.
- [ ] Review analytics and indexation after operational monitoring.

## Abort rule

> Defects on the money path abort. Defects elsewhere fix forward.

Disable new checkout if:

- the wrong amount or currency is charged;
- payment succeeds but access is absent;
- checkout, webhook, entitlement, or portal endpoints return 5xx;
- duplicate charges or unsafe entitlement behavior appear.

Refund affected customers before attempting a relaunch. Do not revoke existing valid entitlements
when disabling new checkout.

## Post-launch decision

On 2026-09-30, record a keep/change/kill decision for the paid tier using:

- pricing-page to checkout conversion;
- checkout completion;
- refunds and cancellations;
- subscriber retention and Intel use;
- support burden;
- evidence of demand by league and geography.
