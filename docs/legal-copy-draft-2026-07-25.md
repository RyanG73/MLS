# Legal & policy copy — DRAFTS FOR OWNER REVIEW (2026-07-25)

**Status: NOT PUBLISHED. NOT LEGAL ADVICE.** These are operational drafts produced by the launch
readiness audit. They are deliberately *not* wired into the site, because publishing terms that bind
the business — with an entity name, a governing law and a refund liability — is the owner's decision,
not an engineering one.

Three of them are **launch blockers**: taking a card payment on 2026-08-17 without published terms,
a published refund policy and an accurate privacy policy is a consumer-protection and
payment-processor-terms problem, independent of whether any customer ever complains.

## What the owner must decide before these can ship

| # | Decision | Why it blocks | Suggested default |
|---|---|---|---|
| L1 | **Legal entity name and country** | Every document names the contracting party. "Entenser" is a product name; a sole trader trades under a personal name unless registered. | — |
| L2 | **Governing law / jurisdiction** | Terms are unenforceable-ish without it and EU/UK consumers keep local rights regardless. | Owner's country of residence |
| L3 | **Refund window scope** — first billing period only, or any period? | A $59.99 annual refunded on day 29 is a materially different exposure than $5.99 monthly. An unbounded guarantee on annual is an open liability. | **First billing period only**, monthly *and* annual |
| L4 | **Access on refund** — ends immediately, or at period end? | Determines whether the Track 9 runbook needs a manual KV write. | **Ends immediately** (revoke on refund) |
| L5 | **Support address** | `entenser@gmail.com` is a personal Gmail. Fine legally, weak for a paid product and unmonitored on a Monday. | `support@entenser.com` via Resend |
| L6 | **Stripe Tax on/off + registration thresholds** | Prices display in EUR/GBP for EU/UK locales, implying EU/UK sales. Getting this wrong is expensive and retroactive. | Enable Stripe Tax; keep single-currency until registered |

---

## D1 — Refund policy (the 30-day money-back guarantee)

> **30-day money-back guarantee**
>
> If Entenser Intel isn't for you, email [SUPPORT ADDRESS] within **30 days of your first charge**
> and we'll refund it in full. No form, no questions, no "tell us why".
>
> - The guarantee covers your **first billing period**, monthly or annual.
> - Refunds are issued to the original payment method, normally within one business day of your
>   email; your bank may take a further 5–10 days to show it.
> - Your Intel access ends when the refund is issued. Your public forecasts — every league, every
>   match probability, every published grade — stay free, as they always are.
> - Renewals after the first period are not covered by the guarantee, but you can cancel any time
>   in one click and keep access until the end of the period you've paid for.

**Implementation contract (must match the words above exactly):**
- Any refund request inside the window is **approved automatically**. A guarantee with a
  discretionary approver is not a guarantee. No owner judgement call in the loop.
- Issued in Stripe → `charge.refunded` → entitlement revoked. **Note:** revocation on refund is
  *not yet wired* — `server/stripe_webhook.py` handles no refund event. Either add
  `charge.refunded` → `set_plan(canceled)`, or the runbook carries a manual step someone is on
  the hook for. **Decide before Aug 10's dress rehearsal, and rehearse whichever you pick.**

## D2 — Terms of service (skeleton — needs L1/L2)

Sections required, in this order: who we are (L1) · what the service is · **what it is not** ·
accounts · subscription, price, renewal and cancellation · the 30-day guarantee (link D1) ·
acceptable use · data and IP · disclaimers · liability · changes to terms · governing law (L2) ·
contact.

The two clauses that matter most for this product:

> **What Entenser is not.** Entenser publishes statistical forecasts produced by a market-blind
> model. It is not betting advice, tipping, or a prediction of any individual outcome. Forecasts are
> probabilities, they are frequently wrong about single matches, and we publish our own accuracy
> record precisely so you can judge them. Nothing on Entenser is a recommendation to place a bet.

> **Subscription and renewal.** Entenser Intel is a recurring subscription. You will be charged the
> price shown at checkout, in the currency shown at checkout, at the start of each billing period,
> automatically, until you cancel. You can cancel at any time in one click from your account; access
> continues to the end of the period you have paid for. We will email you before any price change.

## D3 — Privacy policy (REWRITE — the current page is now false)

The live page at `?league=privacy` says Entenser *"does not require an account and does not collect
personal information"* and that preferences are *"never sent to us"*. Both become false the moment
accounts and subscriptions exist. The account page's own "Data & privacy" line has already been
corrected in this audit; **the policy page itself still needs the rewrite below.**

Must now disclose:

- **Collected:** email address (account + magic-link sign-in), subscription status and Stripe
  customer id, Intel preferences (followed teams/leagues, thresholds, timezone), saved Intel work
  (journal, workspaces, scenarios), and aggregate analytics.
- **Processors**, each with a link to their policy: **Stripe** (payments — card details never reach
  Entenser), **Resend** (transactional and digest email), **Upstash** (account and entitlement
  storage), **Vercel** (API hosting), **GitHub Pages** (static site), **Google Analytics 4**
  (aggregate usage).
- **Legal basis** (GDPR): contract for account/billing data; consent for marketing email;
  legitimate interest for aggregate analytics.
- **Retention:** account data for the life of the account; Stripe retains payment records per its
  own legal obligations; deletion removes the Entenser record.
- **Your rights:** access, export, correction, erasure, objection, portability, complaint to a
  supervisory authority. **Export and erasure are self-service** at `GET`/`DELETE /v1/account/data`
  — and as of this audit they work for cancelled users too, who previously could not reach them.

## D4 — Auto-renewal pre-purchase disclosure ✅ SHIPPED

Already implemented in `webapp/intelligence.js` `freeView()`: price, currency, renewal cadence, the
one-click cancellation method and the guarantee all render adjacent to the Subscribe button, before
any commitment. Price and currency are read from the **live Stripe Price object** via
`/v1/public/config`, so the quoted figure cannot drift from what is charged; when Stripe is
unconfigured the copy says the price is shown at checkout rather than inventing one.

**Remaining:** link Terms and Refund policy from that block once D1/D2 publish. The exact insertion
point is marked with a `NOTE (launch audit 2026-07-25)` comment in `freeView()`.
