# Entenser — Current Status

**Repository verified:** 2026-07-31 · **Production last verified:** 2026-07-31 ·
**Owner:** Ryan · **Approved direction:** controlled Club Watch beta no earlier than 2026-08-17,
pending every commercial, production, customer-evidence, and launch gate

This is the canonical answer to four questions:

1. What is live?
2. What is broken or unverified?
3. What happens next?
4. What evidence supports those claims?

Historical narrative belongs in `PROJECT_HISTORY.md`. Detailed execution belongs in the single
active plan, `superpowers/plans/2026-08-17-paid-launch-and-subscription-growth.md`.

---

## Current objective

Complete one production transaction through the real Club Watch customer path:

> A supporter selects a club, signs in at `entenser.com`, receives one complete
> frozen sample, sees the exact Club Watch amount, pays through
> `api.entenser.com`, receives durable access, manages billing, cancels, and
> receives a refund with the entitlement updated correctly.

No new feature, live notification claim, Club Rate test, or broad promotion
outranks that milestone.

## Production state

| Surface | State | Proof |
|---|---|---|
| Public site | ✅ Live | `https://entenser.com/` returns 200 |
| MLS/home presentation follow-up | ✅ Live | MLS uses table-first movement placement, neutral team links, dual-country flags, and a horizontal desktop home hero. Pages run `30629626679` deployed commit `b468f6e`. |
| Point-in-time season history | ✅ Live | The 71 domestic race pages now merge provenance-labeled historical replays with authoritative archived forecasts. Thirty-five leagues received 5,725 reconstructed team-points; the other 36 were already archived before their current season began. Replays exclude later scores and undated roster/injury/value inputs; dashed chart segments are reconstructed and solid segments are archived. Pages run `30637496201` deployed commit `871eaa4`. |
| Forecast landing page and RSS | ✅ Live | `/football-forecasts/` and `/forecast-feed.xml` return 200 |
| Crawlable club forecast pages | ✅ Live | Static build emits 1,446 competition-scoped club pages and a 1,543-URL sitemap; Pages run `30627028178` deployed them successfully |
| Global Power and shared ELO | ✅ Live | 892 clubs across 50 leagues; shared `global_elo` displayed throughout relevant public surfaces |
| Fast result/projection refresh | ✅ Live | Final workflow run `30205921705` published `live-data` successfully on 2026-07-26 |
| Intelligence API on Vercel host | ✅ Reachable | `https://mls-five.vercel.app/v1/public/config` returns 200 |
| `api.entenser.com` | ✅ Live | HTTPS GET returns 200; CORS preflight from `https://entenser.com` returns 204 |
| Production application configuration | ✅ Core runtime configured | Upstash, token, admin, unsubscribe, API URL, and production-mode variables are Production-only |
| Legal business entity | 🟡 Formation chosen | Owner chose an Ohio single-member LLC; legal name remains open |
| Public pricing configuration | ❌ Empty | Production `/v1/public/config` returns `"pricing": {}` |
| Paid transaction path | ❌ Not operable | Durable auth is working; blocked by Stripe configuration and legal publication |
| Club Watch repository packaging | ✅ Deployed and smoke-verified | Club-first intent, one durable free sample, outcome-triggered conversion moments, coherent free/paid boundary, authenticated Account, and customer-facing naming shipped in commit `1d954fa` |
| Club Watch season forecast history | ✅ Live and published | Club Watch merges current-season point-in-time replays with the exact nightly archive, labels dashed reconstructed versus solid archived checkpoints, lets members inspect available historical targets, and includes a frozen history chart in the complete free sample. Exact archives win same-day conflicts; public league history remains free. Commit `4beee51` deployed in Pages run `30646510561` and API run `30646510217`; the latter rebuilt 66 competitions/1,108 club records with zero failures and published all 1,108 through the scoped authenticated relay. The live feature copy is present, the public API is healthy, the relay returns `401` without its publisher credential, and the final suite passed 1,729 tests with 14 intentional skips. |
| Checkout safety | ✅ Deployed, not production-rehearsed | Production requires four immutable Prices, Stripe/webhook/auth/KV dependencies, three approved policy versions, and an owner switch; live config reports checkout disabled without exposing missing secret names |
| Growth measurement | ✅ Deployed foundation | Canonical funnel/lifecycle dictionaries, privacy-limited server ledger, cancellation/support/testimonial capture, Stripe/delivery events, shadow-review evidence, and owner scorecard shipped; GA4/GSC production inputs remain missing |
| Live alerts and briefings | ❌ Not offered | UI labels delivery unavailable; live scripts require both protected send switches, two matchweeks of shadow QA, one quiet cycle, and owner approval |

**Repository verification proof (2026-07-31):** the integrated release passed
1,719 tests with 14 intentional skips; all 79 public payloads, the Intelligence
artifact contract, history-growth gate, promotion-gate self-test, Python
compilation, JavaScript syntax, and `git diff --check` passed. The static build
emitted 78 league pages, 1,446 club pages, and a 1,543-URL sitemap.

**Historical replay proof (2026-07-31):** the replay coverage manifest reports all 71 domestic
league race pages covered: 35 reconstructed and 36 whose exact archive predates the current season.
The committed reconstructed dataset has 5,725 unique `(league, team, date)` rows, stays strictly
before each league's first authoritative archive date, contains only current standings members,
and keeps every probability in `[0,100]`. Regression coverage proves future fixture scores do not
affect an earlier replay and that archived rows win every same-day merge.

**Historical replay deployment proof (2026-07-31):** GitHub Pages run `30637496201` completed
successfully for commit `871eaa4`. The live MLS payload begins on `2026-02-20` with
`kind: reconstructed`, and the live page labels dashed segments as reconstructed and solid segments
as archived. This is a point-in-time model replay, not a claim that those forecasts were published
on those historical dates.

**Production verification proof (2026-07-31):** GitHub Pages run `30627028178`
and Vercel API run `30627028137` completed successfully for commit `1d954fa`.
The live homepage serves the Club Watch promise, and
`https://api.entenser.com/v1/public/config` returns the deployed checkout
contract with `enabled: false` and `reason: owner_disabled`. This proves the
release and kill switch are live; it does not pass pricing, legal, transaction,
delivery, or customer-evidence gates.

**Presentation follow-up proof (2026-07-31):** GitHub Pages run `30629626679`
completed successfully for commit `b468f6e`. The live index contains the MLS
dual flags, table-first movement placement, neutral link styling, honest
season-start baseline, horizontal desktop hero, and consolidated masthead
ticker; the deployment also refreshed the live service-worker cache.

**Owner decision recorded (2026-07-29):** Ryan approved the paid-launch decision record as written:
7,000 active paid is the objective; Club Watch, its primary audience, boundary, launch pricing,
no-trial guarantee treatment, validation shortlist, scope freeze, and earliest controlled-beta
milestone are approved. The exact target date for reaching 7,000 remains open; 24 months is only a
provisional planning horizon.

## Launch blockers, in order

### 1. Connect the production API domain — completed 2026-07-26

`api.entenser.com` is attached to the Vercel production environment through the Namecheap CNAME
`3b4876572083db00.vercel-dns-017.com`. Cloudflare and Google public DNS resolve it, HTTPS is active,
`GET /v1/public/config` returns 200, and a preflight from `https://entenser.com` returns 204 with
the exact allowed origin.

**Exit test:** ✅ passed.

### 2. Provision durable storage and production secrets — completed 2026-07-26

The Upstash database is live and the required variables are configured Production-only:

- `ENTENSER_ENV=production`
- `UPSTASH_REDIS_REST_URL`
- `UPSTASH_REDIS_REST_TOKEN`
- `ACCESS_TOKEN_SECRET`
- `ADMIN_TOKEN`
- `UNSUBSCRIBE_SECRET`
- `PUBLIC_API_URL=https://api.entenser.com/v1`

The latest Production deployment is Ready. With `ENTENSER_ENV=production`, the custom-domain
`GET /v1/public/config` returns 200 through Upstash; a production magic-link request completed and
its email arrived, proving the deployed application can write durable auth state as well as read it.

**Exit test:** ✅ passed.

### 3. Form the Ohio single-member LLC without publishing the home address

The owner decision is an Ohio single-member LLC with its default federal tax treatment. Do not elect
S-corporation taxation during formation unless a CPA later recommends it based on sustained profit.
Ryan lives and operates in Ohio, so use Ohio rather than adding the fees and filings required to form
elsewhere and then qualify the foreign LLC in Ohio.

#### Address-privacy setup — complete before filing

1. Choose a reputable Ohio statutory-agent service. “Statutory agent” is Ohio's term for a
   registered agent.
   - The service receives lawsuits and official state documents; it is not automatically the
     company's ordinary mailing address.
   - The agent must accept the appointment and provide an Ohio street address where an authorized
     person is normally present during business hours.
   - The agent's name and address appear in the public Ohio business record. Using a professional
     service keeps Ryan's home address out of that required public field.
2. Obtain a separate business mailbox from a Commercial Mail Receiving Agency (CMRA) or
   privacy-oriented virtual-mail provider.
   - Prefer a real street-style address with a unique PMB or suite number, mail scanning, check
     deposit or forwarding if needed, and preferably an Ohio location.
   - Complete USPS Form 1583 and its identity check. A CMRA receives ordinary business mail; it is
     not a valid Ohio statutory-agent address. A provider offering both services must use its actual
     staffed Ohio office—not the rented private-mailbox address—for the statutory-agent role.
3. Ask both providers exactly which filing fields their addresses may be used for. Some registered
   agents also sell a permitted business-address service; do not assume the basic agent plan includes
   it.
4. Preview Ohio Articles of Organization Form 610 and identify which entered fields will become
   public. Ohio law requires the LLC name plus the statutory agent's name, Ohio street address, and
   signed acceptance; avoid adding optional personal information to the Articles.
5. Use the CMRA address for public business/mailing fields only where the state permits it, and use
   the registered-agent address only in fields the agent authorizes.
6. Do not put the home address, personal phone number, or personal email in an optional public field.
   Create an LLC-specific email and use the Entenser support email or business mailbox where accepted.
7. Never provide a false address. The IRS, bank, Stripe, and other identity checks may privately
   require Ryan's real residential or physical address. Give it to them when required; the goal is
   to keep it out of public records and marketing lists, not to conceal the owner from regulators or
   financial institutions. The IRS permits a separate mailing address but requires a physical street
   address when it differs and does not allow a P.O. box in that physical-address field.

#### Formation checklist

1. Use the [Ohio Secretary of State filing page](https://www.ohiosos.gov/business/business-filing-forms)
   and Ohio Business Central. File domestic LLC Articles of Organization, Form 610; the current
   standard filing fee is $99. Avoid third-party formation sites unless deliberately hiring one.
2. Choose the exact LLC name, search the state database, and search the
   [USPTO trademark database](https://www.uspto.gov/trademarks/search) for confusingly similar
   names. Decide whether the legal name will include `Entenser`; record the final spelling exactly.
3. Confirm whether `Entenser` needs a state or local DBA/assumed-name filing if it differs from the
   LLC's legal name.
4. Hire the registered agent and open the CMRA/virtual mailbox before submitting the state filing.
5. File the Articles of Organization directly through the official state site. Use the approved
   privacy addresses in the correct fields, select member-managed unless counsel recommends
   otherwise, save the submitted form and receipt, and decline unnecessary third-party upsells.
6. After approval, download and securely store the stamped Articles/Certificate of Organization and
   state entity ID.
7. Sign a single-member operating agreement naming Ryan as the sole member and documenting initial
   ownership, management authority, and the tax year. Keep it internally; do not publish it unless
   the state requires filing.
8. Apply for the EIN free through the [official IRS EIN application](https://www.irs.gov/businesses/employer-identification-number)
   only after the LLC is approved. Use the LLC's exact legal name, save the EIN confirmation
   immediately, use the business mailbox for IRS correspondence where allowed, and provide the real
   physical address where the application requires it.
9. Open a business checking account in the LLC's legal name using the approved formation document,
   EIN confirmation, operating agreement, and Ryan's identity documents. Fund it with a documented
   owner contribution and do not mix personal and LLC transactions.
10. Register or verify requirements with the Ohio Department of Taxation and the relevant city or
    municipality. Ask a CPA about Ohio's Commercial Activity Tax, municipal net-profits tax,
    whether Entenser subscriptions are taxable, and when multistate or international sales-tax/VAT
    registration could be triggered.
11. Check the current [FinCEN BOI page](https://www.fincen.gov/boi). As verified 2026-07-27,
    U.S.-created entities are currently exempt from federal BOI reporting, but recheck because this
    rule can change.
12. Create a compliance calendar for the statutory-agent renewal, mailbox renewal, federal and Ohio
    tax deadlines, municipal filings, license renewals, and domain renewals. The Ohio Secretary of
    State's current LLC guide says Ohio LLCs do not file annual or biennial reports, but recheck this
    each year because the rule can change.
13. Ignore official-looking formation solicitations until independently verified on the relevant
    government website. State filings commonly trigger private mail selling certificates, posters,
    filing services, or other items that may not be required.
14. Update Stripe, the business bank account, Terms, Privacy Policy, refund policy, invoices, support
    footer, and tax records with the exact LLC name and business mailing address. Keep residential
    information in private verification fields only.

Official references: the
[Ohio LLC guide](https://www.ohiosos.gov/assets/business-start-a-llc.pdf) and
[Ohio business FAQ](https://www.ohiosos.gov/business/ohio-business-roadmap/frequently-asked-questions)
define the statutory-agent and filing requirements; the
[SBA registration guide](https://www.sba.gov/business-guide/launch-your-business/register-your-business)
explains state filing and registered-agent basics; the
[USPS CMRA guide](https://faq.usps.com/articles/Knowledge/Commercial-Mail-Receiving-Agency-CMRA)
explains private mailboxes and Form 1583; and the
[IRS SS-4 instructions](https://www.irs.gov/instructions/iss4) distinguish mailing and physical
addresses.

**Exit test:** the Ohio business database shows the LLC active; the formation approval,
operating agreement, and EIN notice are securely saved; the LLC bank account is open; the registered
agent and business mailbox both work; and a review of the public state record confirms the home
address does not appear except where the state expressly requires it.

### 4. Activate and configure Stripe

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

### 5. Publish the legal contract

Resolve the owner decisions in `legal-copy-draft-2026-07-25.md`, then publish:

- Terms of Service
- 30-day refund policy
- Corrected privacy policy

The current privacy language predates accounts and paid subscriptions and cannot remain the
customer contract.

### 6. Run the production dress rehearsal

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

1. Supply the explicit target date for reaching 7,000 active paid subscribers. All other
   `G0.1–G0.10` decisions are approved and recorded.
2. Form the single-member LLC, establish its private mailing setup, obtain its EIN, and open its bank
   account.
3. Activate Stripe; create the four immutable Prices; register the webhook; configure the Customer
   Portal, receipts, refunds, and failed-payment behavior.
4. Decide the legal draft's remaining open terms using the LLC's final legal name and jurisdiction,
   then approve the Terms, Privacy, refund, cancellation, renewal, and affiliation language.
5. Confirm Vercel Pro, Resend capacity, `support@entenser.com`, and the support/refund schedule.
6. Create or confirm GA4 and Google Search Console access; submit the sitemap; export all available
   analytics, search, waitlist, support, and customer evidence or explicitly mark it missing.
7. Recruit the `D2` discovery sample using `docs/customer-discovery-kit.md`: at least 15 primary
   supporters plus approximately 3 quantitative users and 3 creators.
8. Approve any broadcast email. No broadcast is sent without explicit approval.

## Agent work immediately after owner decisions and access

1. Record approved `G0` decisions in canonical documentation and reconcile final Account, claim,
   cancellation-reason, support-taxonomy, testimonial-consent, and local-versus-durable behavior.
2. Populate public pricing and publish the approved Terms, refund, and corrected privacy routes.
3. Verify the remaining authenticated production paths and fail-closed error behavior.
4. Execute the monthly and annual dress rehearsals with Ryan, including the checkout-disable test.
5. Verify the complete GA4 funnel and Stripe reconciliation.
6. Confirm the custom domain, CORS, auth, checkout, webhook, portal, export, cancellation, refund,
   deletion, and entitlement paths in production.
7. Code the discovery evidence and issue the `D2` go/iterate/kill recommendation before any
   concierge or automated-delivery expansion.

## Recently completed

- Club Watch season history: the existing History view now consumes the reconstructed early-season
  dataset, preserves exact-archive precedence and point provenance, selects a useful historical
  target when the current target lacks prior coverage, and includes the frozen path in the free
  sample. The public current-season history remains free; Club Watch adds the integrated,
  continuously updated club-season view.
- Approved outcome conversion: meaningful movers, high-leverage match previews,
  one-match scenarios, complete samples, and a real additional-club boundary now
  route into club-specific Club Watch continuation copy without paywalling the
  value just consumed.
- Customer evidence and delivery review: categorized cancellation/support
  reasons, explicit anonymous-testimonial consent, corrected/duplicated/
  suppressed delivery states, bounded shadow-candidate reviews, and automated
  threshold reporting are implemented. Live sends still require the complete
  manual evidence gate and Ryan's separate approval.
- Cross-surface contract: static, interactive, personalized, email, and share
  card paths use tested club, competition, probability, timestamp, generated,
  and snapshot identity fields.
- Club Watch packaging and durable activation: club-first magic-link intent,
  one server-backed free club, one frozen sample, sample-first upgrade, up to ten
  paid clubs, and explicit import of browser favorites.
- Production checkout fail-closed control: owner kill switch, four-Price
  requirement, approved-policy version gates, public readiness state, and
  owner-only lifecycle scorecard.
- Account truth: server-authoritative plan/email/followed clubs/notification
  preferences, billing portal, export, active-paid deletion protection, and
  refresh/private-ledger cleanup on erasure.
- Measurement and lifecycle foundation: canonical funnel and core-value events,
  Stripe purchase/renewal/cancellation/expiration/refund/dunning/recovery state,
  and notification provider delivery events.
- Trust repair: explicit non-football news rejection, word-boundary routing,
  reset/bootstrap diagnostics that suppress ±100pp movers, honest forecast-state
  badges, canonical club-page events, and cross-surface claim tests.
- Operating assets: paid-launch decision record, growth measurement contract,
  experiment ledger, claim matrix, discovery kit, concierge kit, and data/
  notification incident checklist.
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
| By 2026-08-02 | LLC, business bank account, DNS, Upstash, Stripe, production secrets, and legal decisions complete |
| 2026-08-03–09 | Legal pages shipped; first full production transaction |
| 2026-08-10 | Monthly and annual dress rehearsal, including cancellation and refund |
| 2026-08-14 | Content freeze |
| 2026-08-15 | Code freeze; money-path fixes only |
| 2026-08-16 | Production preflight and checkout-disable rehearsal |
| 2026-08-17 | Earliest controlled full-price Club Watch beta; broad launch requires a separate Ryan decision |
| 2026-09-30 | Interim paid-tier keep/change/kill/extend decision using observed transaction, conversion, concierge, and available early-retention evidence; set the definitive D60 review date |

## Launch safety rule

> Defects on the money path abort. Defects elsewhere fix forward.

Checkout must be disabled if the wrong amount is charged, payment succeeds without access, or a
money-path endpoint returns 5xx. Existing entitlements remain in durable storage; disabling new
checkout must not revoke existing access.
