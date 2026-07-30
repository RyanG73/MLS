# Data and notification incident checklist

Ryan owns customer response, refunds, publication, and commercial decisions. The repository owner
owns diagnosis, containment, correction, tests, and evidence.

## Trigger

Use this checklist for a wrong team, competition, outcome, price, entitlement, duplicate message,
reset-like movement, stale/unavailable data sold as current, or a serious cross-surface mismatch.

## Contain

1. Stop new checkout for any wrong-price, paid-without-access, unsafe-entitlement, or money-path 5xx
   incident. Do not revoke valid existing entitlements.
2. Keep live email disabled, or disable it immediately if already approved.
3. Preserve Stripe/webhook, send-ledger, snapshot, deployment, and analytics evidence.
4. Identify affected customer, club, competition, event IDs, time window, and surfaces.

## Diagnose

- Reproduce from the exact snapshot and deployment SHA.
- Compare static, interactive, personalized, email, and share-card values.
- Check season, competition, stable club ID, generated timestamp, fixture ID, and config ID.
- Classify root cause: source data, name/identity mapping, season reset, model build, artifact
  publication, client rendering, notification selection, webhook order, or configuration.

## Correct

1. Add a failing regression test before or with the fix.
2. Fix forward; never rewrite an old receipt silently.
3. Emit a correction record for customer-visible forecast or notification errors.
4. Reconcile every affected entitlement and payment from Stripe.
5. Ryan refunds affected customers when the launch-safety rule requires it.

## Verify and close

- Relevant unit, cross-surface, browser, and production smoke checks pass.
- No duplicate or stale cached artifact remains.
- Checkout/email is re-enabled only after the applicable owner decision.
- Record dates, event IDs, deployment proof, affected count, refunds, root cause, and prevention in
  the active plan verdict log.

