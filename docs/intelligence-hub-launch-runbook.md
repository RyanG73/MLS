# Intelligence Hub Launch Runbook

**Date:** 2026-07-18
**Status:** Pre-launch; authenticated web implementation ready, live email disabled
**Owner:** Product/engineering owner with access to Vercel, Upstash, Stripe,
Resend, DNS, and the GitHub production environments

## 1. Launch boundary

There are two independent launch decisions:

1. **Authenticated web launch:** may proceed after production provider setup,
   deployment, artifact publication, and the web smoke tests in this document.
2. **Live email launch:** must remain disabled until S8 has accrued at least two
   complete matchweeks, one quiet-mode cycle has been reviewed, and the owner
   explicitly approves delivery.

All 26 features may appear in the web Hub before live email is approved. Features
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
- [ ] Stripe test-mode Checkout and lifecycle webhooks update entitlement.
- [ ] Resend test delivery and signed webhook status update pass.
- [ ] Public card HTML and PNG verification URLs work without authentication.
- [ ] Desktop and 375px mobile authenticated smoke checks pass.
- [ ] INTELLIGENCE_LIVE_SENDS remains false until S8 approval.
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
| STRIPE_INTEL_PRICE_ID | Server-selected recurring Intel price |
| STRIPE_CREATOR_PRICE_ID | Server-selected recurring Creator price |
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
- INTELLIGENCE_LIVE_SENDS=false

Protected environments:

- intelligence-api-production controls API deployments.
- intelligence-production controls delivery and must require owner review during
  shadow mode.

The scheduled delivery workflow runs daily, but it sends only when
INTELLIGENCE_LIVE_SENDS is exactly true. Both process-level send switches are
also required, and the delivery scripts still apply deduplication, entitlement,
unsubscribe, bounce, retry, and cadence checks.

## 4. Provisioning order

1. Create the production Upstash database and set the REST credentials in both
   Vercel and GitHub.
2. Create the Vercel API project, attach api.entenser.com, configure all Vercel
   environment values, and protect the intelligence-api-production environment.
3. Verify the Resend sending domain and sender. Create a webhook at
   https://api.entenser.com/v1/resend/webhook and subscribe to delivered,
   bounced, complained, and failed email events.
4. Create recurring Stripe products/prices for Intel and Creator. Register
   https://api.entenser.com/v1/stripe/webhook for:
   checkout.session.completed, customer.subscription.updated, and
   customer.subscription.deleted.
5. Put the Stripe price IDs and webhook secret in Vercel. Never accept a price ID
   or entitlement from the browser.
6. Keep INTELLIGENCE_LIVE_SENDS=false.
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
2. Confirm the link opens the Hub, is single-use, and expires after 15 minutes.
3. Refresh the page after the access-token lifetime and verify refresh succeeds.
4. Log out and confirm the refresh token is revoked.
5. Export account data, then delete a disposable account and verify paid
   endpoints reject its old token.

### Entitlement and billing

1. Use Stripe test mode first.
2. Start Intel and Creator Checkout from authenticated accounts.
3. Confirm success redirects do not grant access before the webhook arrives.
4. Verify checkout completion grants the correct plan.
5. Send past_due/canceled/deleted lifecycle events and verify access is revoked.
6. Repeat the exact flow in production with an owner-controlled account before
   opening sales.

### Hub and evidence

1. Open Arsenal in the Premier League plus one live, one preseason, and one
   completed competition.
2. Visit Today, Explore, History, and Studio and confirm feature IDs 1-26 appear.
3. Run and save a scenario; reload and verify its snapshot/seed/version receipt.
4. Create, view, and delete a Forecast Journal checkpoint.
5. Create each conversation-card template and open both HTML and PNG public URLs.
6. Save/delete a Creator workspace and export PNG, CSV, and JSON.
7. Confirm unavailable features contain no mock percentage.
8. Confirm the browser cannot fetch private artifact keys or private journal data
   without a valid entitled token.

### Email safety

1. Run both send scripts without --send and confirm only shadow ledger records.
2. Render a representative alert and briefing for every calendar mode.
3. Follow each unsubscribe link and confirm only its category is suppressed.
4. Replay Resend webhook payloads and confirm signature checking and deduplication.
5. Confirm bounced accounts are suppressed.
6. Confirm shadow records do not suppress the first approved live delivery.

## 7. S8 shadow review

Daily and weekly refresh workflows already generate shadow alert/briefing
records and upload output/intelligence-shadow-report.json.

Review at least:

- two complete matchweeks across active competitions;
- one short-lull, scheduled-break, preseason, or offseason composition cycle;
- every refresh/model event with fan-facing language;
- all residuals over 0.5 percentage points;
- duplicate event/template/user combinations;
- cap, retry, bounce, and unsubscribe behavior;
- empty or low-value briefings that should have been skipped;
- representative rendering on desktop, mobile, HTML email, and plain text.

The report intentionally keeps owner_signoff_ready false. Approval is a human
decision recorded in the release issue/change record; do not edit generated
history to manufacture a pass.

## 8. Enable live delivery

After S8 approval:

1. Set INTELLIGENCE_LIVE_SENDS=true in the protected production environment.
2. Run Intelligence Live Delivery manually with the exact confirmation phrase
   ENABLE LIVE INTELLIGENCE.
3. Review provider IDs and delivery status for that first cohort.
4. Leave the scheduled workflow enabled only after the first cohort is healthy.
5. Watch the first 72 hours for bounce, complaint, duplicate, cap, and webhook
   anomalies.

Authenticated web access does not depend on this switch.

## 9. Rollback

### Stop email immediately

Set INTELLIGENCE_LIVE_SENDS=false. Do not remove ledger records. If a manual job
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

Disable Checkout at the API/environment level, leave webhook processing active,
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
