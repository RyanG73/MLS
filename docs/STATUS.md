# Entenser — Consolidated Status

**Last updated:** 2026-07-25 · **Owner:** Ryan · **Launch target:** Monday **2026-08-17** (paid)

This is the single hub that reconciles the planning docs so you don't have to. It answers: *where
are we, what do I act on, what's broken, what's left to build.* Each row points back to the
canonical doc — this page is a dashboard, not a replacement.

> **Committed to `main` 2026-07-25** — `f260df6` headers · `5092f66` billing lifecycle ·
> `955862e` webapp/pricing · `1660442` CI reliability · `40160fb` coverage manifest.
> Pushing triggers `deploy.yml` (webapp) and `deploy-api.yml` (`api/**`, `server/**` both changed),
> so the header fix reaches production on this push. **Nothing becomes purchasable** — there are
> still no Stripe keys, and the webhook now fails closed rather than open, so the deployed state is
> strictly safer than before. Post-deploy verification is recorded in §2d.

**Every claim below carries a proof or is marked `UNVERIFIED`.** This file has been wrong before:
bug #2 sat green for five nights while data was being silently discarded, and the 2026-07-24 edition
described the paid stack as "essentially ready" when no authenticated request could succeed in
production. Rows marked ✅ were re-verified on 2026-07-25 by the launch-readiness audit.

**Source docs:** [product-roadmap-2026-07.md](product-roadmap-2026-07.md) (feature roadmap — **partly
superseded, see its banner**) · [superpowers/plans/2026-08-17-public-launch.md](superpowers/plans/2026-08-17-public-launch.md) (launch plan) ·
[legal-copy-draft-2026-07-25.md](legal-copy-draft-2026-07-25.md) (ToS/refund/privacy drafts) ·
[social-media-strategy-2026-08-launch.md](social-media-strategy-2026-08-launch.md) (social) ·
[remaining-external-dependencies-2026-07-11.md](remaining-external-dependencies-2026-07-11.md) (spend ledger) ·
[data-sources.md](data-sources.md) (supplier register + export-scope rule) ·
[CURRENT_STATE.md](CURRENT_STATE.md) (model config) · [PROJECT_HISTORY.md](PROJECT_HISTORY.md).

---

## 1. Where we are — one paragraph

The **free static product is live and healthy** on entenser.com (GitHub Pages, HTTP 200 verified):
77 leagues, forecasts, tables, trust pages, all Phase-1 features. The **Intelligence API is deployed
and answering** on `mls-five.vercel.app` (`/v1/public/config` → 200). Everything else about the paid
tier that the previous edition called ready **was not**. The audit found the money path severed at
both ends in production: a header-case bug meant **no authenticated request could ever succeed and
no Stripe webhook could ever be verified**, and Vercel production holds **exactly three environment
variables**, none of them Stripe, Upstash, or the token secret. Both are now fixed,
committed and deployed (1414 tests green) — but **the production config is still absent**. The honest position:
**we cannot take money today, and Aug 17 is achievable but only if §2's blockers clear this week.**

---

## 2. 💰 The revenue path — can a stranger's card be charged? (NEW — this is the launch's spine)

**Verdict: not yet.** Three things decide it: **DNS**, **environment variables**, and a
**deployed API**. Everything else in this section is downstream of those three.

### 2a. Blockers — launch-day money or trust breaks

| # | Blocker | Owner | Status / proof | Action |
|---|---|---|---|---|
| **B1** | **`api.entenser.com` does not resolve.** `webapp/intelligence.js:13` hardcodes `https://api.entenser.com/v1` as the production API base, so *every* Intel call and checkout fails in the browser. | Ryan | ❌ **CONFIRMED 2026-07-25**: `dig api.entenser.com` → empty; `curl` → `http=000`. API answers only on `mls-five.vercel.app` (200). | Attach the domain in Vercel → Domains, add the CNAME at Namecheap. **~15 min. Unblocks everything.** |
| **B2** | **Production has no application secrets.** `vercel env ls production` returns exactly `RESEND_API_KEY`, `RESEND_AUDIENCE_ID`, `RESEND_FROM_EMAIL`. Missing: `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `STRIPE_INTEL_PRICE_ID`, `UPSTASH_REDIS_REST_URL`, `UPSTASH_REDIS_REST_TOKEN`, `ACCESS_TOKEN_SECRET`, `ADMIN_TOKEN`, `ENTENSER_ENV`, `UNSUBSCRIBE_SECRET`, `PUBLIC_API_URL`, and the four `STRIPE_PRICE_INTEL_*` ids (§2e). | Ryan | ❌ **CONFIRMED live 2026-07-25** via `vercel env ls production` (names only). | See §2c. **~45 min total.** |
| **B3** | **`ENTENSER_ENV` unset disarms every production guard.** `server/config.py` returns dev defaults instead of raising: `ACCESS_TOKEN_SECRET` becomes `dev-only-insecure-secret` (**anyone can forge a paid token**) and `get_kv()` silently falls back to an **in-memory dict that dies on every cold start** — a paid entitlement would evaporate within minutes. | Ryan | ❌ **CONFIRMED**: absent from `vercel env ls`; `/v1/public/config` returns 200 (not the 503 a production-mode missing-KV would raise), proving the silent fallback is active. | Set `ENTENSER_ENV=production` **together with** B2's secrets — setting it alone will 503 the whole API. |
| **B4** | ~~**Header case broke all auth and all webhooks in production.**~~ ✅ **FIXED 2026-07-25.** Vercel delivers header names lowercased; `api/index.py` built a plain dict from raw items, so `headers.get("Authorization")` and `headers.get("Stripe-Signature")` always missed. | Claude | ✅ Proof: prod `/intel/me` + valid bearer → `missing bearer token`; prod webhook → `malformed Stripe-Signature header`; local reproduces **only** with lowercase headers. Fixed via `server/http_headers.Headers`; verified through the real router (lowercase → 200, forged → 401, none → 401). 9 regression tests. | ✅ **Deployed 2026-07-25** (`f260df6`, via `deploy-api.yml`). |
| **B5** | ~~**Stripe webhook failed OPEN with the secret unset.**~~ ✅ **FIXED 2026-07-25.** HMAC over an empty key verifies, so a forged `checkout.session.completed` signed with `b""` was **accepted** — a free `creator` entitlement for anyone who knew. Masked by B4; **B4's fix would have unmasked it.** | Claude | ✅ Proof: demonstrated accepted pre-fix; endpoint now returns 503 when unset. Test: `test_stripe_webhook_fails_closed_when_secret_is_unset`. | Set `STRIPE_WEBHOOK_SECRET` (B2). |
| **B6** | ~~**No self-service cancellation existed.**~~ ✅ **FIXED 2026-07-25.** No billing-portal endpoint, and **no Stripe customer id was stored anywhere**, so cancellation, refund reconciliation and rebuild-from-Stripe were all impossible. | Claude | ✅ Built `server/stripe_portal.py`, `api/billing/portal.py`, route `/v1/billing/portal`, "Manage billing" button. Customer id now persisted + reverse-indexed. 15 tests. | Enable the Billing Portal in Stripe → Settings → Billing → Customer portal (**~10 min**, §2c S5). |
| **B7** | **No Terms of Service and no published refund policy.** Stripe's merchant terms require published terms; the 30-day guarantee is the risk-reversal mechanism replacing the trial and must be published, linked and honoured. | Ryan | ❌ **CONFIRMED**: `_INFO_PAGES` = about, support, data-sources, responsible-gambling, privacy, contact. No terms, no refunds. | Review [legal-copy-draft-2026-07-25.md](legal-copy-draft-2026-07-25.md), decide L1–L6, hand back → Claude ships the routes. **Blocking. Start now.** |
| **B8** | **Privacy policy is now false.** It states Entenser *"does not require an account and does not collect personal information"* and preferences are *"never sent to us"*. | Ryan → Claude | ❌ CONFIRMED at `?league=privacy`. (The account page's version of this claim ✅ **fixed** 2026-07-25.) | Rewrite per draft D3 once L1/L2 are decided. |
| **B9** | **Vercel Hobby is non-commercial.** Taking subscription payments from a Hobby-hosted API violates Vercel's fair-use terms and risks suspension — mid-launch. | Ryan | ⚠️ **UNVERIFIED which plan the project is on.** Flagged on policy grounds. | Confirm plan; upgrade to **Pro, $20/mo** before Aug 17. |
| **B10** | **Resend free tier is 100 emails/day.** Auth is magic-link, so **every signup *and* every sign-in sends an email**. A good launch day breaks this, and the failure mode is *new customers cannot log in after they have paid*. | Ryan | ⚠️ **UNVERIFIED headroom** — 3,000/mo is comfortable, **100/day is not**. 100 signups exhausts it. | Upgrade to Resend Pro (**$20/mo, 50k/mo**) **before** Aug 17, not during. This is the ceiling that binds first. |

### 2b. Gaps — launch works but degrades

| # | Gap | Owner | Status | Date |
|---|---|---|---|---|
| G1 | ~~Webhook dedup key written **before** the entitlement — a KV failure mid-apply turned Stripe's retry into a silent no-op (paid customer, no access, no second chance).~~ ✅ **FIXED**, reordered + regression test. | Claude | ✅ | done |
| G2 | ~~`past_due` revoked access on the **first** decline, though Stripe retries ~3 weeks.~~ ✅ **FIXED** — `past_due` is now a grace state, `unpaid` is where access ends. **Owner-reversible policy call**; say so if you disagree. | Claude | ✅ | done |
| G3 | ~~`invoice.payment_failed` unhandled.~~ ✅ **FIXED** — flags `dunning:<user>` without revoking. | Claude | ✅ | done |
| G4 | ~~A **cancelled user could not export or delete their own data** (`PLAN_RANK["canceled"] = -1 < free`). GDPR access/erasure, for exactly the population that uses it.~~ ✅ **FIXED** via `account_user()`. | Claude | ✅ | done |
| G5 | ~~`/intel/export` required `creator`, but "CSV downloads of every projection" is **advertised on the Intel tier**. Every launch customer would have been sold a 401.~~ ✅ **FIXED** to `intel`. | Claude | ✅ | done |
| G6 | ~~`creator` was **purchasable but undefined** — no price, no tier, no copy.~~ ✅ **FIXED**: `PURCHASABLE_PLANS = {"intel"}`; UI button removed. Rank + webhook mapping retained. | Claude | ✅ | done |
| G7 | ~~`checkout=success\|canceled` handled **nowhere** — a successful payment landed on an unchanged page and read as a failure.~~ ✅ **FIXED**: both handled, URL cleaned, plus a bounded poll for the webhook race. Browser-verified. | Claude | ✅ | done |
| G8b | ~~**No monthly/annual split at the API** — the site rendered an annual toggle while `_price_id()` could only bill the single monthly Price. A customer picking annual would have been billed monthly.~~ ✅ **FIXED**: interval is a first-class checkout parameter, annual is preselected (hard annual push), and the chooser renders only when both Prices exist. | Claude | ✅ | done |
| G8 | ~~Price was guessed from `navigator.language` (**three** currencies) and hardcoded on each surface — €5.99 displayed, $ charged. Also **two different prices**: $5.99 supporter vs **$7.99 Intel**.~~ ✅ **FIXED**: price/currency/interval now read from the **live Stripe Price object** via `/v1/public/config`. | Claude | ✅ | done |
| G9 | ~~No refund→entitlement revocation — the guarantee's revocation step was manual.~~ ✅ **FIXED**: `charge.refunded` → revoke, via the customer reverse-index (refund events carry no metadata). **Partial refunds deliberately do not revoke.** Built on the L4 default (access ends immediately); `REVOKE_ACCESS_ON_REFUND` is a one-line flip if you decide otherwise — **the published wording and that constant must always agree.** | Claude | ✅ | done |
| G10 | ~~No rate limit on `POST /billing/checkout`.~~ ✅ **FIXED**: 10/hour/user — generous enough that a genuine card retry never notices, tight enough that session-spray can't pollute the funnel the Sept 30 gate is read from. | Claude | ✅ | done |
| G11 | ~~Funnel partly instrumented.~~ ✅ **FIXED**: `view_pricing` → `begin_checkout` → `purchase` complete, GA4 ecommerce shape, `interval` on every event so the monthly/annual split is readable. **`purchase` fires only once the server confirms the entitlement**, never on Stripe's redirect — otherwise launch week's number is inflated by abandoned payments. Delegates to the host page's consent-gated `track()`. **`refund`/`cancel` are read from Stripe, which is authoritative for money events** — not mirrored into GA4. | Claude | ✅ | done |
| G12 | Support inbox is `entenser@gmail.com`, a personal address, unmonitored on a Monday. | Ryan | ❌ Open | **Aug 10** |
| G13 | ~~Exported PNG cards embedded a hardcoded `api.entenser.com` verification URL.~~ ✅ **FIXED**: both hardcoded sites now honour the existing `PUBLIC_API_URL` convention. **Add `PUBLIC_API_URL` to the §2c env list.** | Claude | ✅ | done |

### 2c. Owner runbook — exact steps, in order

| # | Step | Where | Time | Unblocks |
|---|---|---|---|---|
| **S1** | Attach `api.entenser.com`; add the CNAME Vercel shows you | vercel.com → project `mls` → Settings → Domains; DNS at Namecheap | 15 min | **Everything.** B1 |
| **S2** | Create an Upstash Redis DB (free tier), copy REST URL + token | console.upstash.com | 10 min | B2, B3 — the entitlement store |
| **S3** | Generate a token secret: `openssl rand -base64 48` (also one for `ADMIN_TOKEN`, one for `UNSUBSCRIBE_SECRET`) | terminal | 2 min | B2 |
| **S4** | Activate Stripe fully (business details, bank account, identity). **A Checkout Session against an unactivated account fails at the worst moment.** | dashboard.stripe.com | 20–30 min | B2, all payments |
| **S5** | Create the **Price objects** — monthly and annual — then **enable the Customer Portal** (Settings → Billing → Customer portal: allow cancel, allow payment-method update) | dashboard.stripe.com | 20 min | B6. ⚠️ **One-way door — see the note below** |
| **S6** | Add all env vars to Vercel **Production**, including `ENTENSER_ENV=production` | `vercel env add <NAME> production` | 15 min | B2, B3 |
| **S7** | Confirm the Vercel plan is **Pro**, not Hobby | vercel.com → Settings → Billing | 5 min | B9 |
| **S8** | Upgrade Resend to Pro | resend.com → Settings → Billing | 5 min | B10 |
| **S9** | Decide L1–L6 in [legal-copy-draft-2026-07-25.md](legal-copy-draft-2026-07-25.md) and hand back | — | 45 min | B7, B8 |

### 2e. Pricing — decided 2026-07-25

**Launch at $5.99/mo · $59.99/yr (USD only). $7.99/mo · $79.99/yr is pre-built and one API call away.**

The roadmap §1 already decided $5.99 with competitive anchors (Football Data Lab, the closest direct
competitor, is £5.99/mo; The Athletic at ~$8 is called "the content **ceiling**"). The $7.99 that
appeared on the Intel surface on 2026-07-18 carried **no recorded rationale** — it was drift, not a
revision. USD-only because three currencies means six immutable Price objects and an implied EU/UK
VAT position; add currencies later, you cannot remove them.

A Stripe Price is **immutable** in amount, currency and interval, so a price change is never an edit
— it points new checkouts at a different, pre-created Price while Stripe keeps existing subscribers
on the one they bought. That is what makes a lift safe *and* what makes "founding rate locked for
life" a promise you can actually keep.

**Create four Prices at S5** and set all four ids:

| Env var | Price | Tier |
|---|---|---|
| `STRIPE_PRICE_INTEL_MONTHLY_LAUNCH` | **$5.99 / month** | launch (active) |
| `STRIPE_PRICE_INTEL_ANNUAL_LAUNCH` | **$59.99 / year** | launch (active) |
| `STRIPE_PRICE_INTEL_MONTHLY_STANDARD` | **$7.99 / month** | standard (idle) |
| `STRIPE_PRICE_INTEL_ANNUAL_STANDARD` | **$79.99 / year** | standard (idle) |

Lift the price — no redeploy, works during code freeze, reversible in seconds:

```bash
curl -X POST https://api.entenser.com/v1/admin/pricing \
  -H "X-Admin-Token: $ADMIN_TOKEN" -H 'Content-Type: application/json' \
  -d '{"tier":"standard","note":"post-launch lift"}'
```

`GET` the same URL to read the current tier. **Safety properties, tested:** the switch fails **low**
— an unset, unknown, or newly-unconfigured tier resolves to `launch`, so a config mistake
undercharges rather than overcharges; a tier with no Price **cannot be selected** (400, not a broken
checkout button); and the **client cannot name its own tier**. `/v1/public/config` quotes the active
tier's Price and checkout charges the active tier's Price **through the same resolver**, so the
number on the page and the number on the card cannot drift.

**Founding rate:** at $5.99 list there is no discount left to give waitlist members, so the offer is
*"your $5.99 rate is locked for life"* — honours "first in at the launch price", costs nothing today,
and preserves your freedom to lift list price as the vault deepens. `allow_promotion_codes` is
already enabled, so this needs a Stripe promo code, not engineering.

### 2d. Verification protocol — what is proven, what is not

| Step | State | Evidence |
|---|---|---|
| 1. Full `pytest` | ✅ | **1414 passed, 7 skipped, 0 failed** (2026-07-25, after the pricing-switch pass). Browser tests excluded — `playwright` not installed locally. |
| 2. Production reachable | ⚠️ Partial | `mls-five.vercel.app/v1/public/config` → **200**, now returning `"pricing":{}` (honest fallback, no 503). `api.entenser.com` → **NXDOMAIN** — still not reachable at the host the webapp calls. |
| 2b. **Header fix confirmed in production** | ✅ | **Post-deploy 2026-07-25 (`7bf77fe`).** `GET /v1/intel/me` with a forged bearer now returns **`{"error":"bad signature"}`** — pre-deploy the identical request returned `{"error":"missing bearer token"}`. The header now *arrives and is parsed*; the token is verified and correctly rejected. This is the single most important verification in the file. |
| 2c. **Webhook fails closed in production** | ✅ | `POST /v1/stripe/webhook` with a `Stripe-Signature` header → **503 `webhook signing secret is not configured`**. Two facts at once: the header arrived (it reached the secret check rather than dying at header parse), and an unset secret is refused rather than accepted. |
| 2d. Billing portal route live | ✅ | `POST /v1/billing/portal` → **401** unauthenticated. Route deployed and protected. |
| 2e. Lock still holds post-deploy | ✅ | `/v1/intel/journal` with no token → **401**. The key works and the lock still works. |
| 3. CORS | ✅ | Preflight from `Origin: https://entenser.com` → **204**, `access-control-allow-origin: https://entenser.com`. |
| 4. Gate returns 401 for free users | ✅ | `/intel/journal`, `/intel/workspaces`, `/intel/me`, `/account/data` → **401**. Admin endpoint fails closed → 401. |
| 5. Magic link end-to-end on prod | ❌ **BLOCKED ON OWNER** | Needs B1+B2. Untestable until deployed. |
| 6. `POST /billing/checkout` → session URL | ❌ **BLOCKED ON OWNER** | Needs `STRIPE_SECRET_KEY` + `STRIPE_INTEL_PRICE_ID`. |
| 7. Test-mode payment | ❌ **BLOCKED ON OWNER** | Dress rehearsal, **Aug 10**. |
| 8. Webhook → entitlement written | ❌ **BLOCKED ON OWNER** | Capture the Stripe event ID when run. |
| 9. Gated endpoint → 200 after payment | ❌ **BLOCKED ON OWNER** | **This is the moment the product exists.** |
| 10. Cancel self-service | ⚠️ Code ✅, live ❌ | Endpoint + tests done; needs S5 + deploy. |
| 11. Refund end-to-end | ❌ Open | Blocked on G9 + L4. |
| 12. Idempotency replay | ✅ (unit) | `test_duplicate_event_id_is_a_no_op` + `test_a_failed_apply_leaves_the_event_retryable`. TTL 30d vs Stripe's ~3d retry window — ample. |
| 13. Browser, desktop + mobile | ⚠️ Partial | Checkout-return + disclosure verified locally, no console errors. **Not yet run against production.** |

---

## 3. 🐛 Outstanding bugs

| # | Issue | Severity | Status |
|---|---|---|---|
| 1 | ~~Intelligence API deploy fails~~ | — | ✅ Fixed 2026-07-24. Re-verified: `/v1/public/config` → 200. |
| 2 | ~~Nightly refresh discarded 5 nights of data~~ | — | ✅ **Root cause fixed properly 2026-07-25.** The July fix (`--allow-missing-config`) treated the *symptom*; the commit step was still fail-fast behind four more scripts, so any *other* failure would have done the same thing. Delivery is now a separate `continue-on-error` step. A **build** failure still correctly skips the commit. |
| 3 | ~~Dated `/weekly/<date>/` 404s~~ | — | ✅ Resolved 2026-07-23. |
| 4 | ~~`test_intelligence_state_replay` fails~~ | — | ✅ **No longer reproduces.** Passes **5/5** consecutive runs and in the full suite (2026-07-25). The suite is genuinely green; a red suite at launch would mean you cannot tell a real regression from the known one. |
| 5 | **No failure alerting existed** — a failed refresh was found by accident. | Medium | ✅ **FIXED**: both refresh workflows open (or comment on) a labelled `refresh-failure` issue on failure. |
| 6 | Vercel CLI outdated (54.4.1 → 57.0.0) | Trivial | `npm i -g vercel@latest` |

---

## 4. 🔨 Remaining builds

| Build | Gated on | Notes |
|---|---|---|
| **Terms + refund routes** | **B7 / L1–L6** | Copy drafted; ~2h to ship once decided. **Launch-blocking.** |
| **Privacy rewrite** | **B8 / L1–L2** | Draft D3 ready. **Launch-blocking.** |
| **Refund → revocation (`charge.refunded`)** | L4 | G9. Aug 3. |
| **Funnel completion** | — | G11. Aug 7. **You get exactly one chance to record the launch-week baseline.** |
| **Signed-out preview split** | — | Highest-leverage conversion work in the 23 days, precisely because no trial is doing it. **Show the vault, describe the alerts** — see §5. |
| **Waitlist → checkout transition** | B7 | Every waitlist CTA currently promises a *future* product ("Nothing is for sale yet", "launching soon", "planned"). On Aug 17 they must sell or be honestly relabelled. A whole workstream, not a copy tweak. |
| **1.7 OG cards + team pages** | GSC indexation | Unchanged, post-launch. |
| **Weekly digest *sends*** | Your sign-off | Standing rule: no broadcast sends without it. |

---

## 5. 🗄️ What the vault actually contains — measured, not asserted

Re-measured 2026-07-25. **Do not copy these numbers forward; re-measure.**

| Archive | Span | Snapshots | Integrity |
|---|---|---|---|
| `match_prob_history.parquet` (47 leagues, 121,104 rows) | **Jul 7 → Jul 25 (19 days)** | 17 | **Jul 8–9 missing.** Jul 24 (2,102) and Jul 25 (4,207) **partial** vs an 8,458 median |
| `odds_history.parquet` (77 leagues, 11,038 rows) | **Jun 28 → Jul 25 (28 days)** | 20 | 8 of the first 14 days missing; counts oscillate 58–981 |
| `data/weekly-archive/` | Jul 19 → Jul 25 | 7 files | — |

**Honest depth at launch:** projecting the measured cadence to Aug 17 gives **~6 weeks** of
match-level history and ~7 weeks of team-level. That is **not multi-season, by an order of
magnitude.** The roadmap's claim that `odds_history.parquet` *"already **is** the private
multi-season archive"* is true about the **mechanism** and false about the **contents**.

**The ceiling is fixed and cannot be bought.** Roadmap §1 rule 3 is right: a forecast record is what
the model *said at the time*, so it cannot be backfilled. One full season lands **mid-2027**;
"multi-season" becomes honest **mid-2028** at the earliest.

**Therefore the only launch pitch that survives contact with the data** is *founding member of an
archive that starts now and compounds daily* — not *access to a deep vault*. The roadmap's own
phrase, *"the vault gets more valuable every single day"*, is the sellable version. **Audit every
paid-tier claim against ~6 weeks before Aug 14's content freeze.**

**Partial snapshots — diagnosed, and it is not what it looked like.** Rows-per-league is *stable*
(~275–295 across healthy days), so the row-count swings are mostly **league-count** swings: days on
which fewer leagues were rebuilt, not partial writes. `snapshot_date` comes from each payload's own
`generated` stamp, so a league rebuilt ad-hoc lands in its own bucket. Jul 25 is simply today,
mid-accumulation. **The real defect is that the archive had no record of what it *should* have
contained**, so it could not distinguish "this league had no fixtures" from "this league wasn't
built". ✅ **FIXED**: `scripts/archive_odds_snapshot.py` now writes `data/snapshot_coverage.json` —
leagues captured, leagues live, and which are missing, per day. Re-running can only improve a day,
never erase it. **On its first real run it flagged `romania-liga1`: status `live`, rebuilt today,
**zero upcoming fixtures**, contributing nothing to the vault while the site advertises it as live.
Logged for `docs/league-qa-audit-prompt.md` — a data-correctness defect, not a launch blocker.**

**The backtest question:** the eval harness holds walk-forward per-match vectors for 2022–2025
(`experiments/champion.json`, avg Brier **0.632977**, matching CURRENT_STATE). That is **backtest,
not live record** — what the model *would have* said. A clearly-labelled backtest archive is a
legitimate *second* product, but its league coverage is far narrower than the 77-league registry.
**If it ships it ships visibly separated and never blended.** A trust-first product that silently
mixes reconstructed history with a live record has destroyed the only thing it sells. **Decision
owed: Aug 3.**

---

## 6. 📅 One calendar

| Date | Milestone |
|---|---|
| **Jul 25 (today)** | S1–S3 (DNS, Upstash, secrets). Start S9 (legal decisions). Deploy the audit fixes. |
| **Jul 26 – Aug 2** | S4–S8. First real end-to-end test-mode purchase. Terms/refund/privacy shipped. Social warm-up continues. |
| **Aug 3 – 9** | G9 refund revocation, G10 rate limit, G11 funnel. Preview split. Waitlist→checkout rewrite. Backtest decision. |
| **Aug 10** | **Dress rehearsal — the single highest-value hour in the plan.** Owner, real device, cold session: sign up → pay → access → **request a refund** → cancel → verify period-end behaviour. **Once monthly, once annual** (the guarantee exposure differs). |
| **Aug 11 – 13** | Fix what the rehearsal finds. Check each target community's self-promotion rules — several distinguish free tools from commercial products, and a launch-day removal costs the channel entirely. |
| **Aug 14** | **Content freeze.** All copy final, UTMs applied. |
| **Aug 15** | **Code freeze.** Launch-blocking fixes only, owner-approved, one at a time. |
| **Aug 16** | Pre-flight only. No code. Final env-var check, `GET /v1/public/config`, cold-session smoke test. |
| **Aug 17 (Mon)** | **LAUNCH.** Runbook in §7. |
| **Aug 18** | First conversion read. |
| **Sept 30** | **Conversion gate** — replaces Oct 31. Explicit keep/kill on the paid tier. |
| **Oct–Nov** | Trial A/B against the launch-week baseline, if the gate passes. |

---

## 7. 🚀 Launch day — and the rollback trigger

**You cannot roll back a charge.** Code reverts; money does not. A bug that charges the wrong amount,
double-charges, or grants no access after payment is remediated by refunds and an apology, never by
a deploy. That asymmetry decides the trigger:

> **Defects on the money path abort. Defects elsewhere fix forward.**

**Abort = turn checkout off in under 5 minutes.** Fastest lever: `vercel env rm STRIPE_SECRET_KEY production`
→ checkout returns a clean 503 and the button stops working, while **everyone who already paid keeps
their access** (entitlements live in KV, not in Stripe's availability). Rehearse this on Aug 16.

**Launch day is one person, and one person cannot watch four things.** Ranked:

| Priority | Watch | Cadence | Trigger |
|---|---|---|---|
| **1** | Failed checkouts, 5xx on `/v1/*` | Every few minutes, first 3 hours | Any money-path 5xx → **abort** |
| **2** | Stripe dashboard: payments succeeding, receipts sending | Hourly | Wrong amount/currency → **abort** |
| **3** | Support inbox | Two scheduled windows | — |
| **4** | Reddit/HN replies | Two scheduled windows (social plan §6) | — |
| **5** | GA4, indexation | Evening only | — |

**If Ryan is unavailable for three hours** — a normal Monday occurrence, not a contingency — priority
1–2 go unwatched. **Mitigation: do not post the announcements until you can watch for three
uninterrupted hours.** The posts are the only thing that generates load; delaying them costs nothing
and removes the entire risk.

### Launch-deploy checklist (Aug 17, in order)

1. ~~Bump `webapp/sw.js` cache version~~ — ✅ **now automatic.** `deploy.yml` stamps `CACHE` from the
   commit SHA. This was a live trap: `sw.js` caches `/index.html` — the file carrying the pricing UI
   and checkout button — so a forgotten bump would have served **every returning visitor and every
   installed-PWA user the pre-monetization page**, with no way to pay, while every server-side test
   passed. The file's own comments record two prior incidents.
2. Confirm `webapp/data/*.js` payloads remain **outside** the SW cache (they must stay cache-busted per request).
3. `vercel env ls production` — every §2c var present.
4. Deploy API; `GET /v1/public/config` → 200 **on `api.entenser.com`**.
5. **Cold-session purchase smoke test, in a private window, *after* deploy.**
6. Only then: post announcements.

---

## 8. The single most important thing

**Attach `api.entenser.com` and set the production environment variables — today.** They are the
same 60 minutes of work they were last week, but the audit changed what they mean: the previous
edition treated DNS as the last cosmetic step on a finished system. It is not. Until B1 and B2 land,
**the deployed paid product cannot authenticate a single user, cannot verify a single webhook, and
stores entitlements in a dictionary that is erased every time the function goes cold.** Everything
else in this file — the portal, the guarantee, the funnel, the vault's honest depth — is downstream
of those two rows.

**Can we launch paid on Aug 17?** Yes, if S1–S9 clear this week. The engineering blockers are fixed
and tested; what remains is configuration you own and one legal decision set. If S9 slips past
**Aug 8**, ship the launch **free** on Aug 17 with checkout dark and open payments when terms
publish — a launch without terms is the one failure mode that is worse than a delay.
