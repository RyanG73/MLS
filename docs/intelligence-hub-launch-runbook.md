# Club Watch Launch Runbook

**Date:** 2026-07-18
**Status:** Pre-launch; authenticated web implementation ready, live email disabled
**Owner:** Product/engineering owner with access to Vercel, Upstash, Stripe,
Resend, DNS, and the GitHub production environments

## 1. Launch boundary

There are three independent launch decisions:

1. **Registered sample launch:** one followed club and one frozen sample may
   proceed after production auth/storage setup and the web smoke tests.
2. **Paid Club Watch launch:** remains disabled until pricing, approved policy
   versions, Stripe lifecycle, Account, and checkout-kill-switch checks pass.
3. **Live notification launch:** must remain disabled until S8 has accrued at least two
   complete matchweeks, one quiet-mode cycle has been reviewed, and the owner
   explicitly approves delivery.

All 26 features may appear in paid Club Watch before live delivery is approved. Features
without sufficient source evidence must stay in thin_history or unavailable
state. Do not replace those states with samples.

## 2. Hard gates

Do not announce production availability until all applicable boxes are true:

- [ ] Launch validator passes for exactly the artifact-backed team catalog.
- [ ] API is deployed with production-only secrets and fails closed without them.
- [ ] Private team artifacts are present in Upstash and absent from the Vercel
      public/static bundle.
- [ ] Magic-link request, callback, refresh, logout, account export, and account
      deletion pass against production.
- [ ] All four immutable Stripe Prices exist and `/v1/public/config` exposes the
      exact active monthly and annual amounts.
- [ ] Approved Terms, Privacy, and Refund policy versions are configured.
- [ ] Checkout is owner-enabled and its disable rehearsal completes in under
      five minutes without revoking current entitlements.
- [ ] Stripe test-mode Checkout and lifecycle webhooks update entitlement,
      dunning, cancellation, renewal, recovery, expiration, and refund state.
- [ ] Resend test delivery and signed webhook status update pass.
- [ ] Public card HTML and PNG verification URLs work without authentication.
- [ ] Desktop and 375px mobile authenticated smoke checks pass.
- [ ] `INTELLIGENCE_SENDS_ENABLED` and
      `INTELLIGENCE_SENDS_OWNER_APPROVED` remain false until S8 approval.
- [ ] The intelligence-production GitHub environment has a required reviewer.

## 3. Required configuration

### Vercel project environment

Set these as production secrets or environment values on the API project:

| Name | Requirement |
|---|---|
| ENTENSER_ENV | production |
| ACCESS_TOKEN_SECRET | At least 32 random bytes; rotate only with a planned token invalidation |
| UPSTASH_REDIS_REST_URL | Production Upstash REST URL |
| UPSTASH_REDIS_REST_TOKEN | Production Upstash REST token |
| RESEND_API_KEY | Production sending key |
| RESEND_FROM_EMAIL | Verified sender on the Entenser domain |
| RESEND_WEBHOOK_SECRET | Svix signing secret from the Resend webhook |
| STRIPE_SECRET_KEY | Production Stripe restricted/secret key |
| STRIPE_WEBHOOK_SECRET | Signing secret for the Stripe production endpoint |
| STRIPE_PRICE_INTEL_MONTHLY_LAUNCH | Immutable $5.99 launch monthly Price |
| STRIPE_PRICE_INTEL_ANNUAL_LAUNCH | Immutable $59.99 launch annual Price |
| STRIPE_PRICE_INTEL_MONTHLY_STANDARD | Immutable inactive $7.99 monthly Price |
| STRIPE_PRICE_INTEL_ANNUAL_STANDARD | Immutable inactive $79.99 annual Price |
| CHECKOUT_ENABLED | `true` requests checkout; production readiness can still block it |
| ADMIN_TOKEN | Owner token for checkout state and growth scorecard endpoints |
| CUSTOMER_TERMS_APPROVED_VERSION | Exact owner-approved Terms version |
| PRIVACY_POLICY_APPROVED_VERSION | Exact owner-approved Privacy version |
| REFUND_POLICY_APPROVED_VERSION | Exact owner-approved Refund policy version |
| UNSUBSCRIBE_SECRET | At least 32 random bytes; also used by delivery jobs |
| PUBLIC_SITE_URL | https://entenser.com |
| PUBLIC_API_URL | https://api.entenser.com/v1 |
| ALLOWED_ORIGINS | Comma-separated exact frontend origins, including https://entenser.com |

Do not expose any value above in webapp files. The frontend may cache a signed
access token for presentation, but every paid API call rechecks the current plan.

### GitHub repository and environment configuration

Repository secrets:

- VERCEL_TOKEN, VERCEL_ORG_ID, VERCEL_PROJECT_ID
- UPSTASH_REDIS_REST_URL, UPSTASH_REDIS_REST_TOKEN
- RESEND_API_KEY, RESEND_FROM_EMAIL
- UNSUBSCRIBE_SECRET
- Existing data-provider secrets used by refresh workflows

Repository/environment variables:

- PUBLIC_API_URL=https://api.entenser.com/v1
- INTELLIGENCE_SENDS_ENABLED=false
- INTELLIGENCE_SENDS_OWNER_APPROVED=false

Protected environments:

- intelligence-api-production controls API deployments.
- intelligence-production controls delivery and must require owner review during
  shadow mode.

The scheduled delivery workflow runs daily, but both send switches are
required, and the delivery scripts still apply deduplication, entitlement,
unsubscribe, bounce, retry, and cadence checks.

## 4. Provisioning order

1. Create the production Upstash database and set the REST credentials in both
   Vercel and GitHub.
2. Create the Vercel API project, attach api.entenser.com, configure all Vercel
   environment values, and protect the intelligence-api-production environment.
3. Verify the Resend sending domain and sender. Create a webhook at
   https://api.entenser.com/v1/resend/webhook and subscribe to delivered,
   bounced, complained, and failed email events.
4. Create the four immutable Club Watch prices above. Sell only the internal
   `intel` entitlement; Creator remains unavailable. Register
   https://api.entenser.com/v1/stripe/webhook for:
   checkout.session.completed, customer.subscription.updated,
   customer.subscription.deleted, invoice.paid, invoice.payment_failed, and
   charge.refunded.
5. Put the Stripe price IDs and webhook secret in Vercel. Never accept a price ID
   or entitlement from the browser.
6. Keep both notification send switches false.
7. Deploy the API through the Deploy Intelligence API workflow.
8. Run a full refresh so private artifacts are built, validated, and published
   to Upstash.
9. Deploy the static site and verify that its production API base resolves to
   https://api.entenser.com/v1.

## 5. Local and CI verification

Use the repository virtual environment:

```bash
PYTHONPATH=. venv/bin/python scripts/build_team_intelligence.py --leverage-sims 80
PYTHONPATH=. venv/bin/python scripts/build_team_catalog.py
PYTHONPATH=. venv/bin/python scripts/validate_intelligence_launch.py
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 venv/bin/python -m pytest -q --ignore=tests/test_browser_smoke.py --ignore=tests/test_intelligence_browser.py
venv/bin/python -m pytest -q tests/test_browser_smoke.py tests/test_intelligence_browser.py
```

Expected current launch-validator boundary:

```text
leagues=47 teams=836
live=14369 thin_history=4014 unavailable=3353
```

Private artifacts live under data/team_intelligence only during the build. They
are gitignored and excluded from Vercel. Publish them with:

```bash
PYTHONPATH=. venv/bin/python scripts/publish_intelligence_artifacts.py
```

The command must report 836 compressed team artifacts. Missing Upstash
configuration is a failure in launch/CI usage.

## 6. Production smoke checks

### Authentication and account

1. Request a magic link for a test address.
2. Confirm the link preserves the selected club, opens Club Watch, is
   single-use, and expires after 15 minutes.
3. Refresh the page after the access-token lifetime and verify refresh succeeds.
4. Log out and confirm the refresh token is revoked.
5. Confirm an active paid account cannot be deleted; cancel and expire a
   disposable account, export/delete it, and verify its refresh tokens and
   private ledgers are removed.

### Entitlement and billing

1. Use Stripe test mode first.
2. Start monthly and annual Club Watch Checkout from authenticated accounts.
3. Confirm success redirects do not grant access before the webhook arrives.
4. Verify checkout completion grants the correct plan.
5. Send past_due, recovered invoice, cancellation-requested, deleted, and full
   refund lifecycle events; verify the correct access and scorecard state.
6. Disable checkout through `/v1/admin/checkout`; confirm new sessions stop and
   current Club Watch access remains valid.
7. Repeat the exact flow in production with an owner-controlled account before
   opening sales.

### Club Watch and evidence

1. Open Arsenal in the Premier League plus one live, one preseason, and one
   completed competition.
2. Visit Today, Explore, History, and Studio and confirm feature IDs 1-26 appear.
3. Run and save a scenario; reload and verify its snapshot/seed/version receipt.
4. Create, view, and delete a Forecast Journal checkpoint.
5. Create each conversation-card template and open both HTML and PNG public URLs.
6. Confirm Creator cannot be purchased. Existing Creator entitlements may still
   exercise their legacy workspace/export paths.
7. Confirm unavailable features contain no mock percentage.
8. Confirm the browser cannot fetch private artifact keys or private journal data
   without a valid entitled token.

### Notification safety

1. Run both send scripts without --send and confirm only shadow ledger records.
2. Render a representative alert and briefing for every calendar mode.
3. Follow each unsubscribe link and confirm only its category is suppressed.
4. Replay Resend webhook payloads and confirm signature checking and deduplication.
5. Confirm bounced accounts are suppressed.
6. Confirm shadow records do not suppress the first approved live delivery.

## 7. S8 shadow review

Daily and weekly refresh workflows already generate shadow alert/briefing
records and upload output/intelligence-shadow-report.json.

For each representative candidate, post a bounded review to the owner-only
`POST /v1/admin/delivery` route with:

```json
{
  "action": "review_shadow",
  "user_id": "reviewed-user-id",
  "template_version": "material-alert-v1",
  "event_ids": ["reviewed-event-id"],
  "worth_sending": true,
  "defects": [],
  "notes": "Supported movement, correct club and outcome."
}
```

Allowed defect codes are `wrong_team`, `wrong_outcome`, `wrong_price`,
`duplicate`, `unsupported_cause`, `not_worth_sending`, and `other`. The report
then calculates reviewed volume, worth-sending rate, critical defects, observed
ISO weeks, and quiet-mode suppression evidence. Review notes stay in the
private delivery ledger and never enter growth analytics.

Review at least:

- two complete matchweeks across active competitions;
- one short-lull, scheduled-break, preseason, or offseason composition cycle;
- every refresh/model event with fan-facing language;
- all residuals over 0.5 percentage points;
- duplicate event/template/user combinations;
- cap, retry, bounce, and unsubscribe behavior;
- empty or low-value briefings that should have been skipped;
- representative rendering on desktop, mobile, HTML email, and plain text.

The report intentionally keeps `owner_signoff_ready` false even when its
automated thresholds pass. ISO-week and quiet-suppression counters help collect
evidence, but Ryan still confirms that they represent two *complete*
matchweeks and one real quiet-mode cycle. Approval is a human decision recorded
in the release issue/change record; do not edit generated history to
manufacture a pass.

## 8. Enable live delivery

After S8 approval:

1. Set `INTELLIGENCE_SENDS_ENABLED=true` and
   `INTELLIGENCE_SENDS_OWNER_APPROVED=true` in the protected production environment.
2. Run Intelligence Live Delivery manually with the exact confirmation phrase
   ENABLE LIVE INTELLIGENCE.
3. Review provider IDs and delivery status for that first cohort.
4. Leave the scheduled workflow enabled only after the first cohort is healthy.
5. Watch the first 72 hours for bounce, complaint, duplicate, cap, and webhook
   anomalies.

Authenticated web access does not depend on this switch.

## 9. Rollback

### Stop email immediately

Set `INTELLIGENCE_SENDS_ENABLED=false`. Do not remove ledger records. If a manual job
is currently awaiting environment approval, reject it.

### Pause a bad artifact build

1. Leave sends disabled.
2. Prevent the failing refresh artifact from being published.
3. Restore/rebuild from the last healthy input snapshot.
4. Append correction events; never rewrite old receipts silently.
5. Re-run launch validation and smoke checks before republishing.

### Revoke compromised credentials

Rotate the affected provider secret in its provider, Vercel, and GitHub. Rotate
ACCESS_TOKEN_SECRET only when prepared to invalidate every access token. Revoke
refresh tokens or delete affected users as needed.

### Billing incident

POST `{"enabled":false}` to `/v1/admin/checkout`, leave webhook processing active,
and reconcile Stripe subscriptions against the authoritative user records.
Browser redirects must never be used to repair entitlement.

## 10. Launch evidence record

For each release, retain:

- commit SHA and API deployment URL;
- launch-validator output and pytest summaries;
- artifact manifest counts and generated timestamp;
- Stripe and Resend webhook smoke-event IDs;
- S8 report artifacts and owner approval;
- first live delivery ledger summary;
- any unavailable-feature coverage exceptions accepted for launch.
