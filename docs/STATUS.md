# Entenser — Current Status

**Last verified:** 2026-07-26 · **Owner:** Ryan · **Target:** paid public launch on 2026-08-17

This is the canonical answer to four questions:

1. What is live?
2. What is broken or unverified?
3. What happens next?
4. What evidence supports those claims?

Historical narrative belongs in `PROJECT_HISTORY.md`. Detailed execution belongs in the single
active plan, `superpowers/plans/2026-08-17-public-launch.md`.

---

## Current objective

Complete one production transaction through the real customer path:

> A new visitor signs in at `entenser.com`, pays through `api.entenser.com`, receives Intel
> access, manages billing, cancels, and receives a refund with the entitlement updated correctly.

No new feature outranks that milestone.

## Production state

| Surface | State | Proof |
|---|---|---|
| Public site | ✅ Live | `https://entenser.com/` returns 200 |
| Forecast landing page and RSS | ✅ Live | `/football-forecasts/` and `/forecast-feed.xml` return 200 |
| Crawlable club forecast pages | 🟡 Built, not yet live | Static build emits 1,444 competition-scoped club pages and a 1,536-URL sitemap; deployment pending |
| Global Power and shared ELO | ✅ Live | 892 clubs across 50 leagues; shared `global_elo` displayed throughout relevant public surfaces |
| Fast result/projection refresh | ✅ Live | Final workflow run `30205921705` published `live-data` successfully on 2026-07-26 |
| Intelligence API on Vercel host | ✅ Reachable | `https://mls-five.vercel.app/v1/public/config` returns 200 |
| `api.entenser.com` | ✅ Live | HTTPS GET returns 200; CORS preflight from `https://entenser.com` returns 204 |
| Production application configuration | ❌ Incomplete | Vercel lists only `RESEND_API_KEY`, `RESEND_AUDIENCE_ID`, and `RESEND_FROM_EMAIL` |
| Public pricing configuration | ❌ Empty | Production `/v1/public/config` returns `"pricing": {}` |
| Paid transaction path | ❌ Not operable | Blocked by DNS, persistence, secrets, Stripe configuration, and legal publication |

## Launch blockers, in order

### 1. Connect the production API domain — completed 2026-07-26

`api.entenser.com` is attached to the Vercel production environment through the Namecheap CNAME
`3b4876572083db00.vercel-dns-017.com`. Cloudflare and Google public DNS resolve it, HTTPS is active,
`GET /v1/public/config` returns 200, and a preflight from `https://entenser.com` returns 204 with
the exact allowed origin.

**Exit test:** ✅ passed.

### 2. Provision durable storage and production secrets

Create the Upstash Redis database and configure these Vercel Production variables together:

- `ENTENSER_ENV=production`
- `UPSTASH_REDIS_REST_URL`
- `UPSTASH_REDIS_REST_TOKEN`
- `ACCESS_TOKEN_SECRET`
- `ADMIN_TOKEN`
- `UNSUBSCRIBE_SECRET`
- `PUBLIC_API_URL=https://api.entenser.com/v1`

Do not set `ENTENSER_ENV=production` by itself: production mode correctly fails closed when its
required services are missing.

### 3. Activate and configure Stripe

- Finish Stripe business, bank, and identity activation.
- Create four immutable Prices:
  - `STRIPE_PRICE_INTEL_MONTHLY_LAUNCH` — $5.99/month
  - `STRIPE_PRICE_INTEL_ANNUAL_LAUNCH` — $59.99/year
  - `STRIPE_PRICE_INTEL_MONTHLY_STANDARD` — $7.99/month
  - `STRIPE_PRICE_INTEL_ANNUAL_STANDARD` — $79.99/year
- Set `STRIPE_SECRET_KEY` and `STRIPE_WEBHOOK_SECRET`.
- Point the Stripe webhook at the production API.
- Enable cancellation and payment-method updates in the Stripe Customer Portal.

**Exit test:** `/v1/public/config` exposes monthly and annual launch prices, and a test Checkout
Session returns a Stripe URL.

### 4. Publish the legal contract

Resolve the owner decisions in `legal-copy-draft-2026-07-25.md`, then publish:

- Terms of Service
- 30-day refund policy
- Corrected privacy policy

The current privacy language predates accounts and paid subscriptions and cannot remain the
customer contract.

### 5. Run the production dress rehearsal

On a real device and cold browser session, run both monthly and annual:

1. Sign in by magic link.
2. Start checkout and pay in the intended Stripe mode.
3. Confirm the entitlement is durable across a new session.
4. Open the Customer Portal.
5. Cancel.
6. Request and process a refund.
7. Confirm webhook idempotency and the resulting entitlement state.

Record Stripe event IDs and API responses in the active launch plan. Any failure on this path
blocks launch.

## Owner actions

These require account access or business decisions and cannot be completed from the repository:

1. Upstash account/database creation.
2. Stripe activation, Price creation, webhook registration, and Customer Portal settings.
3. Confirm Vercel Pro rather than Hobby.
4. Confirm Resend capacity for launch-day magic links.
5. Decide the legal draft's open terms.
6. Create or confirm GA4 and Google Search Console access; submit the sitemap.
7. Approve any broadcast email. No broadcast is sent without explicit approval.

## Agent work immediately after owner setup

1. Publish Terms, refund, and corrected privacy routes.
2. Deploy the API with production configuration and verify fail-closed behavior.
3. Execute the monthly and annual dress rehearsals with Ryan.
4. Verify the GA4 funnel: `view_pricing → begin_checkout → purchase`.
5. Confirm the custom domain, CORS, auth, checkout, webhook, portal, export, cancellation, and
   deletion paths in production.

## Recently completed

- Competition-scoped club acquisition pages: 1,444 self-canonical club forecasts with unique
  metadata, `SportsTeam`/dataset schema, match and season outlooks, league-table links, interactive
  dashboard handoff, and sitemap coverage. Repository verification is green; production deployment
  is still pending.
- Durable league-qualified “since your last visit” Intel cursor.
- Followed-team win/draw/loss stakes cards and timezone-aware match-morning briefings.
- No-refit fast refresh: results and kickoff changes re-simulate tables every 15 minutes in match
  windows and hourly otherwise; fitted-model and market-price clocks remain separate.
- Forecast-first acquisition layer, European breadth landing page, local league aliases, RSS, and
  authenticated opt-in market comparison mode.
- Global Power restored as one ladder, with shared cross-league ELO applied to league tables,
  projection context, team pages, selectors, run-in difficulty, and history charts.
- Paid-path code hardening: case-insensitive headers, fail-closed webhooks, durable webhook retries,
  billing portal support, refund handling, pricing tiers, checkout return handling, and funnel events.

## Non-blocking backlog

These are preserved from the retired UX plans and should not interrupt the transaction milestone:

- Decide whether desktop Home should place volatile content above reference tables.
- Repair the 768–900px tablet layout.
- Ratify the type floor and remaining sub-11px exceptions.
- Update the interface contract for the shipped Georgia serif, overlay shadows, and horizontal
  fixture strip—or change the product to match the contract.
- Complete production QA for signed-in Intel, Account, Rankings, PWA-installed mode, landscape,
  and iPad WebKit.
- Add domestic championship-playoff simulation where the published competition format requires it.
- Re-check the South-America-heavy Matches to Watch rail after European seasons begin.
- Revisit the inter-confederation ELO shifts after the next Club World Cup adds evidence.

## Launch calendar

| Date | Gate |
|---|---|
| By 2026-08-02 | DNS, Upstash, Stripe, production secrets, and legal decisions complete |
| 2026-08-03–09 | Legal pages shipped; first full production transaction |
| 2026-08-10 | Monthly and annual dress rehearsal, including cancellation and refund |
| 2026-08-14 | Content freeze |
| 2026-08-15 | Code freeze; money-path fixes only |
| 2026-08-16 | Production preflight and checkout-disable rehearsal |
| 2026-08-17 | Launch only if the transaction path is green and Ryan can monitor for three hours |
| 2026-09-30 | Paid-tier keep/change/kill decision using observed conversion and retention |

## Launch safety rule

> Defects on the money path abort. Defects elsewhere fix forward.

Checkout must be disabled if the wrong amount is charged, payment succeeds without access, or a
money-path endpoint returns 5xx. Existing entitlements remain in durable storage; disabling new
checkout must not revoke existing access.
