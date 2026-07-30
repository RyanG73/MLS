# Entenser Launch-Readiness & Revenue-Path Audit

> A complete, from-scratch assessment of whether Entenser can go live on **Monday 2026-08-17**
> with **subscriptions flowing from minute one**. Treat every launch claim in `docs/` as
> **unverified**. Prior status docs record what someone believed on the day they wrote it —
> they are leads, not evidence. Confirm every green checkmark yourself against live systems,
> live code, and live config, or downgrade it.
>
> This prompt covers **launch readiness and the revenue path**.
> `docs/site-ux-audit-prompt.md` covers **interface quality**; `docs/league-qa-audit-prompt.md`
> covers **data correctness**. If you find a UX or data defect, log it and hand it to those.

---

## 0. The decision that changed — read this first

`docs/product-roadmap-2026-07.md` §4–5 originally gated the entire paid tier behind an **Oct 31
evidence gate** (waitlist joins ≥ 2% of returning users **AND** ≥ 150 absolute), with Phase 2
(M1–M7) scheduled **Nov 2026 → Feb 2027**. That historical gate was replaced by the paid-launch
decision recorded in `docs/PROJECT_HISTORY.md`; `docs/STATUS.md` carries the current gate.

**The owner has now directed that subscriptions must be live and taking money at go-live on
2026-08-17.** That is a deliberate reversal of a documented decision, made with knowledge of the
gate. Your job is not to re-litigate it — it is to:

1. **Record the reversal explicitly** in `docs/PROJECT_HISTORY.md`,
   `docs/STATUS.md`, and `docs/product-roadmap-2026-07.md`, so the repo
   never again reads as if Oct 31 still governs. State what the gate was *for* (evidence that
   demand exists before spending build effort) and what replaces it now that the effort is
   being spent regardless — most likely a **post-launch conversion read** with an explicit
   kill/keep date, so the discipline survives the schedule change.
2. **Cost the reversal honestly.** Launching paid at Aug 17 pulls forward roughly three months
   of Phase-2 work (M1 at minimum) into a 23-day window, and it moves items previously listed
   as "no deadline" decisions — legal review, tax registration, refund policy — onto the
   critical path. Say so plainly, with dates.
3. **Hold the free-floor ratchet.** `docs/product-roadmap-2026-07.md` §1 rule 4 is
   non-negotiable and was not reversed: *no shipped free feature ever moves behind the
   paywall; paid features are born paid.* Any monetization plan you produce that gates
   something currently free is **wrong** and must be rewritten. The permanent boundary stays:
   **current season free, the vault is paid.**

If you conclude the Aug 17 paid launch is not achievable, say so in one clear paragraph with the
specific blockers and the earliest honest date — then **plan for Aug 17 anyway** with the
scope that *is* achievable, and mark what would be cut. Scaling the launch down is the owner's
call, not yours.

---

## 0b. The trial decision — settled 2026-07-25, do not re-litigate

`docs/product-roadmap-2026-07.md` §1 specifies a **14-day card-required free trial**
(`trial_period_days=14`) as the core M1 acquisition mechanic. **The owner has decided against
shipping a trial at launch.** Aug 17 ships **no trial**, a **hard annual push**, and a
**30-day money-back guarantee**. The 14-day trial becomes a post-launch A/B run against a
measured baseline.

The reasoning, recorded so it is not re-derived:

- **A card-required trial costs the first billing period from everyone who would have bought
  anyway.** Over a fixed 60-day window it must clear `p_start × c = 1.33 × p_buy`; at the
  standard `c ≈ 0.5` for opt-out consumer trials, the trial must lift checkout starts ~2.7×
  just to tie.
- **At $5.99 the card is the friction, not the price.** A trial removes "pay now"; it does not
  remove card entry or the trust decision. Trials earn their multiple when *price* is the
  objection. At this price point it isn't, so the required lift is implausible.
- **A trial destroys the launch's only measurement.** Bypassing the Oct 31 gate (§0) makes
  launch week the demand read. A trial pushes first revenue to Aug 31 and first churn to
  Sept 30, and permanently forecloses ever learning the no-trial conversion rate.
- **A money-back guarantee is a trial with better economics.** Both reverse risk. A trial makes
  cancelling the default path for roughly half of starts; a guarantee costs only actual refunds
  — low single digits at this price. It is a policy plus the Track 9 refund runbook, not code.
- **Trial infrastructure is the wrong thing to build in 23 days** — trial chrome, expiry
  emails, `customer.subscription.trial_will_end`, and the trial-end card-decline dunning path,
  which is the ugliest support case and would land on Aug 31.

**If the A/B later runs, 14 days is the correct length, not 7.** The paid loop is
matchweek-shaped: one matchweek shows state, two show *change*, and "what the model changed its
mind about" is the entire pitch. Seven days is n=1, its quality swings by signup weekday, and
Stripe's `trial_will_end` fires 3 days out — day 4 of 7, before a second matchweek exists. A
14-day trial must also survive **FIFA international breaks**, which pause domestic leagues for
~2 weeks and can render a trial empty; define it in matchweeks or suspend expiry across a break.

**What this obliges you to do in this audit:** record the decision in `docs/PROJECT_HISTORY.md`,
update `docs/STATUS.md`, reconcile
`docs/product-roadmap-2026-07.md` §1 and M1, **keep the `trial` plan rank and webhook mapping
intact** (they cost nothing, they are correct, and the A/B needs them), and instrument the
funnel (Track 8) so the no-trial baseline is measurable from day one.

---

## 0c. The export-scope decision — settled 2026-07-25, do not re-litigate

`docs/data-sources.md` marks raw rows from several suppliers as redistribution-restricted:
ASA game-by-game rows are *"uncertain, treat as local-only"*; ESPN match IDs, team names and
score rows are *"local/model use only"*; ESPN crests need written permission. Derived
probability payloads are explicitly **OK** for every active source.

**The owner has settled the scope: Entenser sells no raw third-party data, ever.** Every paid
export and every vault surface ships **historical aggregated information only** — Entenser's own
model output (probabilities, projections, Elo, projected points, calibration and accuracy
series) and aggregates derived from it. No supplier's raw rows, no scraped tables, no
redistributed match feeds, no third-party crests.

This resolves the M5 licensing question in the safe direction and takes a $500–2,500 legal
review off the critical path for exports specifically. It does **not** waive the broader
compliance review in Track 6 — betting-adjacent positioning, terms, and tax are untouched by it.

**What this obliges you to do in this audit:**

- **Audit the export payload field by field** against `docs/data-sources.md`. `api/intel/export.py`
  is the surface. Any column traceable to a supplier's raw feed — opponent names sourced from
  ESPN, raw xG rows from ASA or Understat, Transfermarkt valuations — comes out or gets replaced
  by a derived aggregate. Team and league *identifiers* need a judgment call: prefer Entenser's
  own stable IDs and public names over supplier-keyed fields.
- **Write the rule down** in `docs/data-sources.md` as a standing constraint, not just here, so
  the next feature that adds an export inherits it.
- **Check attribution obligations still hold.** "We don't redistribute your rows" does not
  cancel "credit American Soccer Analysis for derived public output." Confirm the credits page
  and `/open-data/` attributions are correct and survive the paid launch.
- **Flag any existing free surface that already redistributes restricted raw data.** The ratchet
  forbids removing free features, but it does not authorize a licensing breach — if one exists,
  it is a Track 6 finding regardless of the paywall, and commit `b684e85` (dropping ESPN
  placeholder crests) shows this edge has been touched before.

---

## 1. Role & objective

You are the launch engineer and release manager for Entenser (entenser.com), a market-blind
football forecasting product: a free static site covering 56–78 leagues, plus a login-gated
"Intelligence Hub" (Intel) layer intended to be the paid product.

Answer one question, defensibly: **if we flip the switch on Monday 2026-08-17, does a real
stranger with a real credit card get charged, get access, stay accessible, and get their money
back if they ask — without any human intervention?**

Everything else in this audit exists to support that sentence.

Classify every finding into exactly one of four buckets and handle each differently:

| Class | Definition | What you do |
|---|---|---|
| **Blocker** | Launch-day money or trust breaks. Payments fail, entitlements don't stick, a legal requirement is unmet, or a user is charged with no way to cancel. | **Fix it, or escalate it to the owner with the exact action needed.** Never leave a blocker as a note. |
| **Gap** | Launch works but degrades: no monitoring, no refund path, no funnel instrumentation. | **Fix it if it's yours to fix; schedule it with a date if it isn't.** |
| **Owner action** | Only Ryan can do it — an account, a payment, a signature, a DNS record, a legal decision. | **Write the exact steps, the URL, the time estimate, and what it unblocks.** Never write "set up Stripe." |
| **Deferral** | Genuinely post-launch. | **Name the date it gets reconsidered.** A deferral with no date is a blocker in disguise. |

---

## 2. Ground rules

**Evidence before assertion.** Every "✅ done" in your output carries a proof: a command and its
output, an HTTP status, a Stripe event ID, a dashboard screenshot, a test name that passed. A
claim with no proof is written as **UNVERIFIED** and treated as not done. This applies with
double force to anything `docs/STATUS.md` already marks complete — that file has been wrong
before (bug #2 sat green for five nights while data was being silently discarded).

**Verify against production, not against the repo.** Local code that works proves nothing about
a Vercel deployment with missing env vars. Hit the live endpoints.

**No live money, no live sends, no public posts.** Use Stripe **test mode** for every payment
rehearsal. Use Resend's `delivered@resend.dev` for email tests. Do not send broadcast email, do
not post announcements, do not open the promo switch — all four require explicit owner sign-off
and one of them (broadcast sends) is a standing rule in `docs/STATUS.md` under Owner actions.

**Do not touch production data or secrets destructively.** Read env var *names* and presence;
never print or commit secret *values*. `.env` and `.env.local` exist locally — confirm
`.gitignore` covers them and that no secret has ever been committed (`git log -p -S` on the key
names is cheap insurance).

**Fix vs. propose.** Bugs, missing wiring, missing config, missing tests, wrong copy: **fix
them**. New routes, new pricing, changed product promise, changed information architecture,
anything that costs money monthly: **propose them**, never unilaterally ship.

**Work one track at a time, completely.** Do not skim all eleven tracks and write up at the end
— findings decay and you will conflate them.

---

## 3. What you must produce

Two deliverables, both required.

### 3a. A rewritten `docs/STATUS.md`

Full rewrite, not a patch. It stays the single reconciling hub, keeps its existing shape
(where we are / what YOU act on / bugs / remaining builds / done / dates / the one thing), and
gains a **revenue-path section as §2**, because that is now the launch's spine. Every row
carries a status, an owner (`Ryan` or `Claude`), a date or a gate, and a proof or an
**UNVERIFIED** flag. Strike-through completed items in place rather than deleting them, matching
the file's existing convention. Update the header's **Last updated** and keep **Launch target:
Monday 2026-08-17**.

Also update, per `CLAUDE.md`'s documentation convention:
- `docs/PROJECT_HISTORY.md` — a dated durable-decision entry for the paid-launch reversal.
- `docs/product-roadmap-2026-07.md` — reconcile §4's Oct 31 gate, §5's Nov–Feb schedule, and
  §1's 14-day-trial spec plus M1's trial UX rules (all superseded by §0b).
- `docs/superpowers/plans/2026-08-17-paid-launch-and-subscription-growth.md` — the active launch and
  growth plan; append verdicts.
- `docs/remaining-external-dependencies-2026-07-11.md` — the spend/decision ledger, now that
  legal review and Stripe activation have moved onto the critical path.
- `docs/data-sources.md` — record the §0c export-scope constraint as a standing rule, and refresh
  any supplier row whose redistribution status is stale or blank under a commercial product.

### 3b. A roadmap laid out in chat

Not a copy of the doc — the readable version, for someone deciding what to do this afternoon.
Structure it as a **countdown**, because there are only 23 days:

- **Right now (today, 2026-07-25)** — what unblocks everything else. Ordered, with dependencies.
- **This week (Jul 25–Aug 2)** — build + account setup.
- **Aug 3–9** — integration, dress rehearsal, legal.
- **Aug 10–14** — freeze, QA, final verification. Content freeze is Aug 14 per the launch plan.
- **Aug 15–16** — pre-flight only. No code changes.
- **Aug 17 (launch day)** — hour-by-hour runbook, including who watches what and the rollback trigger.
- **Launch week + first 30 days** — monitoring, first refund, first churn, conversion read.

Two clearly separated columns throughout: **Ryan's actions** and **Claude's actions**. For each
of Ryan's, give the exact destination (URL or dashboard path), the time estimate, and what it
unblocks. Lead the chat output with a **verdict paragraph**: can we launch paid on Aug 17, yes
or no, and the three things that decide it.

---

## 4. The eleven tracks

Work them in this order — later tracks depend on earlier findings.

### Track 1 — The revenue path (highest priority)

**Question:** can money move from a stranger's card into the business, and does access follow it?

Audit the full chain: pricing UI → `POST /v1/billing/checkout` → Stripe Checkout →
`checkout.session.completed` webhook → KV entitlement write → `bearer_user()` plan check →
gated endpoint returns 200.

Files: `server/stripe_checkout.py`, `api/billing/checkout.py`, `server/stripe_webhook.py`,
`api/stripe/webhook.py`, `server/api_support.py` (`PLAN_RANK`, `bearer_user`),
`webapp/intelligence.js:~1090`, `webapp/index.html:~4250` (price display).

Seeded leads — **verify each, do not trust this list**:

- **No Stripe Billing Portal endpoint appears to exist.** `api/billing/` contains only
  `checkout.py`; a grep for `billing_portal` across `server/` and `api/` returns nothing but
  unrelated CSS. The roadmap's M1 spec requires "cancel = one click in the Stripe portal" and
  hosted cancellation configured *before* launch. **A subscription product with no
  self-service cancellation is a launch blocker on legal grounds alone** (see Track 6).
- **No `trial_period_days` is passed at checkout — and per §0b, none should be added.** Launch
  ships without a trial. Confirm checkout creates an immediately-billing subscription, and that
  **no surface anywhere still promises a trial**: the Intel lock screen, upsell copy, waitlist
  confirmation emails, and the `docs/launch-announcements.md` drafts all predate this decision
  and may reference one. A promised trial that doesn't exist is a chargeback.
  **Leave the trial plumbing in place** — `server/stripe_webhook.py` already maps Stripe's
  `trialing` → `trial` and `PLAN_RANK` ranks it between free and intel. It costs nothing, it is
  correct, and the post-launch A/B needs it. Adding the trial later is one parameter plus UX.
- **No monthly/annual split at the API.** `_price_id()` maps only `intel` and `creator` to
  `STRIPE_INTEL_PRICE_ID` / `STRIPE_CREATOR_PRICE_ID`, while the site renders an annual toggle
  at `$59.99`/`€59.99` (`webapp/index.html:4259`). A user who picks "annual" and gets billed
  monthly is a chargeback and a trust failure. Confirm what the toggle actually posts.
- **Currency.** The site shows `€5.99` for EU locales and `$5.99` otherwise, chosen from browser
  locale. Confirm what Stripe actually charges. Displaying euros and charging dollars is a
  consumer-protection problem, not a cosmetic one. Decide: single-currency with honest display,
  or Stripe multi-currency prices.
- **The Stripe Price objects are a one-way door.** Once customers subscribe to a Price, changing
  amount, currency or interval means migrating them — you cannot simply edit it. Force the final
  call on all three, for monthly *and* annual, **before customer #1**, and confirm the created
  Price IDs match what `STRIPE_INTEL_PRICE_ID` / `STRIPE_CREATOR_PRICE_ID` resolve to in
  production. This is distinct from the display-consistency check above: that one asks whether
  the site tells the truth, this one asks whether the truth is one you can live with for a year.
- **The `creator` plan is undocumented.** It ranks above `intel` in `PLAN_RANK` but appears in
  no pricing table, no roadmap tier, and no marketing copy. Either it ships with a defined price
  and value proposition, or it is disabled at the API for launch. Do not ship a purchasable plan
  nobody has defined.
- **Success/cancel URLs** point to `{site}/?league=intel&checkout=success|canceled`. Verify the
  SPA actually handles both params — a successful payment landing on an unchanged page reads as
  a failed payment and generates support load on day one.
- **Webhook coverage.** Currently handles `checkout.session.completed`,
  `customer.subscription.updated`, `customer.subscription.deleted`. **`invoice.payment_failed`
  is the launch-relevant gap** — a card declining on renewal should degrade access gracefully
  and trigger dunning, not silently vanish. `customer.subscription.trial_will_end` is
  **deferred with the trial** (§0b): note it as a prerequisite of the future A/B, do not build
  it now. Idempotency by event ID with a 30-day TTL is already implemented — verify the TTL
  against Stripe's retry window.
- **Signature verification.** Confirm `STRIPE_WEBHOOK_SECRET` is enforced in production and that
  the endpoint **fails closed** when unset. An unverified webhook endpoint is an entitlement
  giveaway.

**Track 1 exit criterion:** a full test-mode purchase completed end-to-end, evidenced by a
Stripe event ID and a `GET /v1/intel/me` response showing the upgraded plan. Nothing else in
this audit matters if this fails.

### Track 2 — Identity & entitlement storage

**Question:** where does "this person paid" actually live, and does it survive?

Files: `server/intel_auth.py`, `api/auth/{request,callback,refresh,logout}.py`,
`server/kv_client.py`, `server/kv_store.py`, `server/upstash_kv.py`, `server/open_access.py`.

- **Upstash appears unprovisioned.** `docs/STATUS.md` bug #2 records that
  `publish_intelligence_artifacts.py` exits 2 because Upstash is missing, and that both refresh
  workflows now pass `--allow-missing-config` to work around it. **If there is no KV, there is
  no entitlement store, and a successful payment writes to nothing.** Verify whether
  `UPSTASH_REDIS_REST_URL` / `UPSTASH_REDIS_REST_TOKEN` exist in the Vercel production
  environment. If they don't, this outranks the custom domain as the single most important
  launch item — and the `--allow-missing-config` flags must come back out once provisioned, so
  a real publish failure is loud again.
- **Magic-link flow end-to-end** on production: request → email arrives → link works → token
  issued → token refreshes → logout revokes. Confirm single-use enforcement and expiry.
  `MAGIC_LINK_BASE_URL` must point at the production site, not localhost.
- **Token security:** `ACCESS_TOKEN_SECRET` must be set in production (`server/config.py`
  falls back to `dev-only-insecure-secret` outside production — confirm `ENTENSER_ENV=production`
  is actually set on Vercel, because that fallback is what makes the guard real).
- **Entitlement durability:** what happens on KV eviction or a free-tier limit? A paying customer
  losing access because a free Redis tier evicted their key is the worst possible launch bug.
  Assess whether Stripe is the source of truth with KV as cache, and whether an entitlement can
  be rebuilt from Stripe if KV is lost.
- **Open-access switch interaction:** `server/open_access.py` bypasses plan checks at the single
  chokepoint `bearer_user()`. Verify a promo window cannot corrupt or overwrite a real paid
  entitlement, and that closing the window restores paid users correctly.

### Track 3 — The paywall surface & what the user sees

**Question:** does the product tell the truth about what costs money?

- **Ratchet compliance audit.** Enumerate every Intel feature currently gated and confirm none of
  it was ever shipped free. Cross-check against the free/paid table in
  `docs/product-roadmap-2026-07.md` §1. Anything currently free that the paid plan would take
  away must stay free — rewrite the plan, not the ratchet.
- **The signed-out experience — this now carries the job the trial would have done (§0b).**
  With no trial, the preview *is* the proof. A stranger must understand what they'd be buying
  before any money moves. Audit the locked Intel preview, the upsell placements (source-tagged,
  Phase 1.6), and whether they now point to checkout rather than a waitlist. **The
  waitlist-to-checkout transition is a whole workstream** — every waitlist CTA on the site
  currently promises a *future* product; on Aug 17 they must either sell or be honestly
  re-labeled.
- **Split the preview by how the value reveals itself.** Roughly half the paid value is
  *instantly* demonstrable — the vault archive, match-level probability history, the CLV ledger
  — and is best sold by showing **real rows, partially revealed**, converting at peak intent
  with no cancel window. The other half (threshold alerts, weekly briefing) is time-revealed and
  can only be described. Audit whether the preview reflects that split or treats every paid
  feature as one undifferentiated locked box. **Show the vault; describe the alerts.** This is
  the highest-leverage conversion work available in the 23 days, precisely because there is no
  trial doing it instead.
- **Existing waitlist members.** People already joined expecting to be told when it launches. They
  are your warmest audience and they were promised something. Decide with the owner: founding
  supporter pricing, early access, or a plain launch email. Note this needs the same broadcast
  sign-off as any other send.
- **Account page truthfulness.** `webapp/index.html:~5043` currently tells users *"Everything
  lives in your browser's localStorage — nothing is sent to a server."* That statement becomes
  **false** the moment accounts and subscriptions exist. There is an `acct-subs` "Subscriptions"
  nav item (`webapp/index.html:~4967`) — verify it reflects real server-side entitlement rather
  than local state, and that it exposes cancel, plan, renewal date, and billing history.
- **Price display consistency** across every surface: masthead upsell, Intel lock screen,
  support page, account page, and any SEO/static page. One stale price is a refund request.

### Track 4 — Infrastructure & environment

- **Env var inventory.** The backend reads exactly these: `ACCESS_TOKEN_SECRET`, `ADMIN_TOKEN`,
  `ENTENSER_ENV`, `INTELLIGENCE_ARTIFACT_ROOT`, `MAGIC_LINK_BASE_URL`, `PUBLIC_SITE_URL`,
  `RESEND_API_KEY`, `RESEND_AUDIENCE_ID`, `RESEND_FROM`, `RESEND_FROM_EMAIL`,
  `RESEND_WEBHOOK_SECRET`, `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`,
  `UNSUBSCRIBE_SECRET`, `UPSTASH_REDIS_REST_URL`, `UPSTASH_REDIS_REST_TOKEN` — plus
  `STRIPE_INTEL_PRICE_ID` and `STRIPE_CREATOR_PRICE_ID` referenced in `stripe_checkout.py`.
  Note `RESEND_FROM` **and** `RESEND_FROM_EMAIL` both appear; determine whether that's a real
  inconsistency. Produce a table: variable → set in Vercel prod? → who sets it → what breaks
  without it. Use `vercel env ls` (names only — never print values).
- **`api.entenser.com` DNS.** `docs/STATUS.md` flags this as the top launch blocker; last recorded state
  was `NXDOMAIN`, with the API answering only on `mls-five.vercel.app`. Verify current state and
  confirm what the webapp actually calls — if the site is hardcoded to the custom domain, the
  API is unreachable in production regardless of it being deployed.
- **CORS** between `entenser.com` (static) and the API host. A cross-origin failure kills
  checkout silently in the browser while every server-side test passes.
- **Deploy pipeline.** Six workflows: `deploy.yml`, `deploy-api.yml`, `refresh-daily.yml`,
  `refresh-leagues.yml`, `refresh-transfermarkt.yml`, `intelligence-delivery.yml`. Confirm each
  is currently green, that the API deploy is reliable after bug #1's five stacked fixes
  (uv, pyproject deps, `.python-version` 3.12, the `api/public` → `api/pub` rename), and that a
  data refresh cannot ship a broken payload to production unattended on launch weekend.
- **Working tree hygiene.** There are currently ~12 modified tracked files and several untracked
  directories (`output/`, `docs/STATUS.html`, `docs/STATUS_files/`, `webapp/docs/`, two new test
  files, `data_pipeline/match_time.py`). Determine what is real work needing commits, what is
  build output needing `.gitignore`, and get the tree clean before freeze. Do not launch from a
  dirty tree.
- **Vercel function limits.** `vercel.json` sets `maxDuration: 30` and an `includeFiles` glob.
  Confirm cold-start behavior on the checkout path — a timeout at checkout is lost revenue.
- **The service worker will hide your launch from returning visitors.** `webapp/sw.js` caches a
  manually-versioned app shell (`entenser-shell-v14`) whose `SHELL` allowlist includes
  **`/index.html`** — the file carrying the pricing UI, the checkout button, and every upsell.
  If the version string is not bumped on launch day, **every returning visitor and every
  installed-PWA user gets the pre-monetization page with no way to pay**, while every
  server-side test passes. This is not hypothetical: the file's own comments record two prior
  incidents, including *"some returning visitors reported seeing the pre-feature page from
  cache."* Verify the bump is part of the launch deploy (Track 11 freeze checklist), and
  **propose deriving `CACHE` from the build** — a content hash or deploy SHA — so a correctness
  requirement stops depending on someone remembering. Confirm too that `webapp/data/*.js`
  payloads remain outside the cache; the file says they are cache-busted per-request, which
  must stay true or paid users will see stale numbers.
- **Free-tier ceilings are a success-failure.** The roadmap budgets ~$10–60/mo assuming free
  tiers hold: Resend 3k emails/mo, Upstash free tier, Vercel free → Pro, GitHub Actions minutes.
  A good launch day is exactly when those break — and because auth is **magic-link, every single
  signup sends an email**, so the email ceiling is coupled directly to the signup spike. Compute
  the headroom at plausible launch volume, identify which ceiling binds first, and write the
  mid-launch upgrade path (what to click, what it costs, how fast it takes effect). Hitting a
  send limit mid-launch means new customers cannot log in **after** they have paid.

### Track 5 — The vault's actual inventory, and data reliability as a paid obligation

Free users tolerate a stale day. Paying users request refunds.

#### 5a. What the vault actually contains — measure it before you sell it

The paid tier's headline is "the vault": the private multi-season archive. **Verify it exists at
the depth the marketing implies.** `docs/product-roadmap-2026-07.md` §2 asserts that
`data/odds_history.parquet` *"already **is** the private multi-season archive."* That claim is
true about the **mechanism** and false about the **contents** — the file accrues indefinitely,
but it has only been accruing since late June 2026.

Baseline measured 2026-07-25 — **re-measure, do not copy these numbers**:

| Archive | Holds | Span | Snapshots | Integrity |
|---|---|---|---|---|
| `data/match_prob_history.parquet` | Match-level W/D/L + market comparison, 47 leagues, ~121k rows | **Jul 7 → Jul 25 (19 days)** | 17 | Jul 8–9 missing. Jul 24 (2,102 rows) and Jul 25 (4,207) are **partial** against a ~8,800 norm |
| `data/odds_history.parquet` | Team-level Elo, projected points, title/playoff/relegation odds, 77 leagues, ~11k rows | **Jun 28 → Jul 25 (28 days)** | 20 | 8 of the first 14 days missing; row counts oscillate 58–981, i.e. partial writes |
| `data/weekly-archive/` | Weekly recap JSON | **Jul 19 → Jul 25** | 7 files | — |
| `webapp/data/drift-traj/` | Per-league trajectories (public, free, current season) | 78 leagues | — | free forever per the ratchet |

CI has only been committing `match_prob_history.parquet` since **2026-07-18** (`5c5906a`,
"commit match_prob_history.parquet in CI (F-1)"). Its Jul 19–23 rows survived bug #2 only
because the parquet accumulates locally and was hand-committed on Jul 23 — **luck, not design.**

What you must produce:

- **The honest depth at launch.** Project each archive to Aug 17 and state it plainly. On the
  measured cadence that is roughly **6 weeks** of match-level history — not multi-season, not
  by an order of magnitude.
- **The accumulation ceiling.** `docs/product-roadmap-2026-07.md` §1 rule 3 states forecast
  history **cannot be backfilled**, and that is correct: a forecast record is what the model
  *said at the time*. So the depth curve is fixed by the start date. Lay out the real timeline —
  when the archive reaches one full season, when "multi-season" becomes honest (earliest **mid-
  2028**), and what that means for how the vault is described in Nov 2026 versus Nov 2027.
- **The backtest question — evaluate it, don't assume it.** The eval harness holds walk-forward
  per-match probability vectors for 2022–2025 (`experiments/champion.json` → challenger-bag5
  report, 4 folds, per-match vectors). That is **backtest, not live record** — what the model
  would have said, not what it did say. Assess whether a clearly-labeled backtest archive is a
  legitimate second product alongside the live record. If it ships, it ships **visibly separated
  and never blended**; a trust-first product that silently mixes reconstructed history with a
  live record has destroyed the only thing it sells. Confirm league and season coverage before
  proposing it — the eval window is far narrower than the 77-league production registry.
- **Partial snapshots are a product defect, not a logging artifact.** A day at 24% coverage is
  a hole in something a customer paid for. Determine the cause, whether affected days can be
  identified programmatically, and whether the archive should record per-snapshot completeness
  so the product can be honest about its own gaps.
- **The launch pitch that survives contact with the data.** With ~6 weeks of history, the
  honest position is *founding member of an archive that starts now and compounds daily*, not
  *access to a deep vault*. Audit every paid-tier claim against the measured depth and rewrite
  anything that oversells. The roadmap's own framing — *"the vault gets more valuable every
  single day"* — is the sellable version; make sure the copy actually says that.

#### 5b. Reliability

- **Re-audit bug #2's class of failure.** Five consecutive nights of successfully-built data were
  discarded because a later step failed and the commit step had no `if: always()`. It was
  invisible because the site looked current from hand-committed local runs. Ask: **what else in
  the pipeline can fail silently?** Every step whose failure does not produce a visible signal is
  the same bug wearing a different hat.
- **Freshness contract.** Decide what the paid product actually promises — "updated daily by
  07:00 UTC" or similar — and whether the site displays a real, honest last-updated timestamp
  derived from the data rather than the deploy.
- **Failure alerting.** Currently, a failed refresh appears to be discovered by accident. Before
  paid launch there must be a signal that reaches a human: workflow failure notification, a
  health endpoint, or a daily digest. Propose the cheapest thing that works.
- **The one failing test.** `test_intelligence_state_replay` fails on a Monte-Carlo tolerance
  breach (3.4pp vs 3.0pp), recorded as pre-existing drift rather than regression. Before paid
  launch, resolve it: re-baseline, widen with justification, or fix. A red suite at launch means
  you cannot tell a real regression from the known one — that is the actual cost.
- **Full suite run.** `pytest` clean, with the count recorded in STATUS.md.

### Track 6 — Legal, tax & consumer-subscription compliance

The external-dependency ledger historically listed legal review as a no-deadline decision at
$500–2,500. **Taking money
on Aug 17 moves it onto the critical path.** This is the track most likely to be underestimated.

Assess and report — clearly labeled as *operational findings, not legal advice*, with a
recommendation on whether a professional review is required before launch:

- **Terms of Service.** No terms page appears to exist. `webapp/index.html:~5128` lists info
  routes: `about`, `support`, `data-sources`, `responsible-gambling`, `privacy`, `contact` —
  no terms, no refund policy. Stripe's own terms require merchants to publish their terms.
- **Refund policy — a launch deliverable now, not boilerplate.** The **30-day money-back
  guarantee** (§0b) is the risk-reversal mechanism replacing the trial, so it must be written,
  published, linked from checkout and every pricing surface, and reflected in the terms. Define
  it precisely: when the window starts (charge date), scope (first period only? monthly *and*
  annual?), whether access ends immediately or at period end, and how it applies to annual — a
  $59.99 refund on day 29 is a materially different exposure than $5.99, and an unbounded
  guarantee on an annual plan is an open liability. Confirm the published wording matches what
  the Track 9 runbook actually does.
- **Cancellation policy.** Written, published, and honored by a self-service path — see the
  missing billing portal in Track 1. A guarantee does not substitute for a cancel button.
- **Auto-renewal disclosure.** Recurring-subscription rules in several jurisdictions (US
  federal negative-option rules and state auto-renewal laws; EU/UK distance-selling and
  withdrawal rights) require clear pre-purchase disclosure of price, renewal cadence, and
  cancellation method, plus a cancellation path no harder than signup. Ties directly to the
  missing billing portal in Track 1.
- **Privacy policy update.** The current page describes a localStorage-only product. Once you
  store emails, payment references, and entitlement records, it needs a rewrite: what's
  collected, why, processors (Stripe, Resend, Upstash, Vercel, Google Analytics), retention,
  deletion rights. There is an `/account/data` endpoint — confirm it satisfies what the policy
  will promise.
- **Sales tax / VAT.** Prices display in EUR for EU locales, implying EU sales. Determine whether
  Stripe Tax should be enabled, and flag registration thresholds as an owner decision. Getting
  this wrong is expensive and retroactive.
- **Data licensing under a paid product.** Giving derived forecasts away free and *selling*
  them are different postures, and `docs/data-sources.md` already draws supplier-by-supplier
  lines. §0c settles the scope (aggregated model output only, no raw third-party rows) — your
  job here is to **verify the shipped product honors it**, confirm attribution obligations still
  hold under a commercial offering, and check whether any supplier's terms restrict commercial
  use of even derived output. `data_pipeline/` carries adapters for ASA, ESPN, Understat,
  football-data, API-Football and Transfermarkt; the register is the authority, and any source
  whose row is blank or stale in it is itself a finding.
- **Betting-adjacent positioning.** The product has an edge board, a paper ledger, model-vs-market
  panels, and a responsible-gambling page. Charging money for betting-adjacent analysis raises
  the compliance bar and may affect payment-processor terms and ad-platform eligibility.
  `docs/competitive-intelligence-2026-07-combined.md` risk #8 already flags the positioning
  question. Confirm the public framing stays utility + trust, and that no paid marketing copy
  promises betting profit.
- **Business entity & Stripe activation.** Confirm with the owner that the Stripe account is
  fully activated (business details, bank account, identity verification) and out of test mode.
  A Checkout Session against an unactivated account fails at the worst possible moment.

### Track 7 — Trust & accuracy at the moment of sale

- **The trust surfaces stay free** — trust tab, model health, weekly receipts, calibration. This
  is both a roadmap rule and the product's core differentiator. Verify none of it is gated.
- **Model claims match reality.** Any accuracy or calibration figure shown near a payment CTA must
  be reproducible from `docs/CURRENT_STATE.md` and the champion report. A stale Brier score next
  to a price is a misrepresentation.
- **Champion config integrity.** `experiments/champion.json` is bundled into the deployed function
  via `includeFiles` — confirm the deployed model config matches the documented champion.

### Track 8 — Measurement & funnel instrumentation

- **GA4** (`G-GVSLY1KBHQ`) is wired but Realtime confirmation was still outstanding. Verify a live
  session registers.
- **Conversion events.** Instrument the funnel end to end: `view_pricing` → `begin_checkout` →
  `purchase` (with value, currency, and **plan interval**, so the monthly/annual split is
  readable) → `refund` → `cancel`. Without this you cannot answer "did launch work?" on Aug 18,
  and you cannot read the conversion gate that replaces Oct 31.
- **The no-trial baseline is a deliverable, not a byproduct (§0b).** Launch week's
  visitor → checkout → paid rate is the control arm of the future trial A/B *and* the only
  demand evidence that will exist. Confirm it is cleanly attributable and segmented by plan
  interval and traffic source **before** Aug 17 — you get exactly one chance to record it.
- **Search Console** sitemap submission (`https://entenser.com/sitemap.xml`) and indexation
  state — this gates the 1.7 OG-cards decision.
- **Attribution.** UTM discipline on launch links per the launch plan's Aug 10–16 window, so
  Reddit vs. HN vs. email is separable.

### Track 9 — Support, refunds & lifecycle ops

- **Support inbox.** A contact route exists — confirm it reaches a monitored address and set an
  expected response time. Launch day generates support volume.
- **Refund runbook — this is the guarantee's implementation (§0b).** Written before launch, not
  during the first request: who approves (state plainly whether any refund inside the window is
  approved automatically — a guarantee with a discretionary approver isn't a guarantee), how
  it's issued in Stripe, whether entitlement revokes automatically or needs a manual KV write,
  and the target turnaround. Because the guarantee replaces the trial as the risk-reversal
  mechanism, **a slow or contested refund is a direct product failure, not a support nuisance.**
  Estimate the exposure at expected launch volume so the owner knows the worst case.
- **Failed payment / dunning.** What a customer sees when their card expires. Ties to the
  `invoice.payment_failed` webhook question in Track 1.
- **Account deletion.** A user who cancels and asks for deletion — confirm `/account/data` and
  the unsubscribe path cover it.
- **Transactional email.** Magic links, receipts, and **refund confirmations**. Determine which
  come from Stripe (configure them in the Stripe dashboard) and which from Resend. Verify
  Stripe's customer emails are enabled — a payment with no receipt is a dispute. Trial-ending
  notices are out of scope at launch (§0b).

### Track 10 — Security & abuse

- **Rate limiting** (`server/rate_limit.py`) on auth request, checkout, and Intel endpoints —
  magic-link request especially, since it sends email on demand and email costs money.
- **`ADMIN_TOKEN`** must be set; `server/open_access.py` is documented to fail closed when unset —
  verify that empirically, don't take the doc's word.
- **Secret hygiene.** Confirm `.env`/`.env.local` are gitignored and no secret was ever committed.
- **Entitlement forgery.** Confirm a forged or expired bearer token cannot reach paid data —
  test it, don't reason about it.
- **Dependency audit** on the deployed runtime (`requirements.txt`, `requirements-api.txt`,
  `pyproject.toml`) — with a payment path live, a known CVE is a different kind of problem.

### Track 11 — Launch execution, freeze & rollback

- **Reconcile the two calendars.** The launch plan's timeline and STATUS §6's key dates must
  agree, and both must now absorb the paid-tier work. Produce one calendar.
- **Freeze discipline.** Content freeze Aug 14 per the launch plan. Propose a **code freeze**
  (recommend Aug 15) with a documented exception process for launch-blocking fixes only.
- **The launch-deploy checklist.** Short, literal, and checked off on the day. It must include
  the **`webapp/sw.js` cache version bump** (Track 4 — without it, returning visitors never see
  the checkout button), the env-var presence check, a live `GET /v1/public/config`, and a
  cold-session purchase smoke test *after* deploy, not before.
- **The distribution plan was written for a free product.** `docs/launch-announcements.md` and
  `docs/social-media-strategy-2026-08-launch.md` sequence Reddit → Show HN → analytics
  communities, drafted when nothing was for sale. Paid changes the reception and, in several
  football subreddits, the *rules* — self-promotion policies frequently distinguish free tools
  from commercial products, and a launch-day removal costs you the channel entirely. **Check the
  actual posting rules of each target community before the Aug 14 content freeze**, and rewrite
  any copy whose framing assumed a free launch.
- **The dress rehearsal.** A full test-mode purchase run by the owner, on a real device, from a
  cold session — sign up, pay, get access, **request a refund under the guarantee**, cancel,
  verify access ends correctly at period end. Run it once monthly and once annual, since the
  guarantee exposure differs. This is the single highest-value hour in the whole plan. Schedule
  it no later than Aug 10 so there is time to fix what it finds.
- **Launch-day runbook.** Hour by hour: who posts what, who watches Stripe, who watches errors,
  who answers replies. `docs/launch-announcements.md` has drafts; the social plan calls for two
  reply windows.
- **Launch day is one person.** The runbook implicitly assumes Ryan watches payments, errors,
  replies and social simultaneously. He cannot. Rank the watch-list explicitly: what must be
  checked within minutes (failed checkouts, 5xx on the API), what can wait for a scheduled
  window (replies, social), and what waits until evening (analytics, indexation). Say what
  happens if he is unavailable for three hours — which, on a Monday, is a normal occurrence and
  not a contingency.
- **Rollback trigger.** Define in advance: what observation makes you turn checkout off, how you
  turn it off in under five minutes, and what users who already paid see. A launch with no
  rollback plan is a launch you cannot safely abort.
- **You cannot roll back a charge.** Code reverts; money does not. A bug that charges the wrong
  amount, double-charges, or grants no access after payment is remediated by refunds and an
  apology, never by a deploy. That asymmetry should decide the trigger above: **defects on the
  money path abort, defects elsewhere fix forward.** Write it in those terms so the decision is
  already made before it has to be made quickly.
- **First-week monitoring.** What gets checked daily, by whom, for the first seven days.

---

## 5. Verification protocol

Nothing in Track 1 may be marked done on reasoning alone. Run the chain:

1. **Local:** full `pytest`. Record pass/fail counts. Pay attention to
   `tests/test_stripe_webhook.py`, `tests/test_api_auth_flow.py`, `tests/test_open_access.py`,
   `tests/test_intelligence_launch.py`.
2. **Production reachability:** `GET /v1/public/config` → 200, from the host the webapp actually
   calls.
3. **Auth:** magic link requested, received, redeemed, token issued.
4. **Gate:** a gated endpoint (`/v1/intel/journal`, `/v1/intel/workspaces`) returns 401 for a free
   user. Prove the lock works before proving the key works.
5. **Checkout:** `POST /v1/billing/checkout` returns a session URL against **Stripe test mode**.
6. **Payment:** complete it with a Stripe test card.
7. **Webhook:** `checkout.session.completed` received, signature verified, entitlement written.
   Capture the event ID.
8. **Access:** the same gated endpoint now returns 200. **This is the moment the product exists.**
9. **Cancel:** cancellation path works self-service; access behaves correctly at period end.
10. **Refund:** issue a test-mode refund end to end and confirm the entitlement outcome matches
    the published 30-day guarantee (§0b) — automatic revocation, or a documented manual step
    someone is on the hook for. An unrehearsed refund path is the guarantee failing the first
    time a real customer uses it, which is the worst moment to discover it.
11. **Idempotency:** replay the webhook; confirm it is a safe no-op.
12. **Browser:** the whole flow in the browser pane on desktop and mobile viewports, watching the
    console and network panels — server-side success plus a client-side CORS failure is still a
    failed launch.

Record each step's evidence in STATUS.md. Where a step cannot be run (needs an owner-only
credential), mark it **BLOCKED ON OWNER** with the exact thing needed — never mark it done.

---

## 6. Rules of engagement

- **Do not spawn subagents.** Do this yourself, in this session.
- **Do not open the open-access promo switch**, send broadcast email, or post announcements.
- **Do not move to live Stripe keys** without explicit owner instruction.
- **Do not commit secrets.** Ever.
- **Do not mark anything done you have not personally verified**, including items already
  marked done by a previous session.
- **Do not quietly re-scope.** If something can't ship by Aug 17, say so, finish everything
  else in full, and state exactly what you left out and why.
- **Do not defer without a date.**

## 7. Tone of the output

Write for someone with 23 days, real money on the line, and no appetite for reassurance. Lead
with the verdict. Put the three things that decide launch above everything else. Be specific
about what is broken and honest about what is unknown. If the answer to "can we take money on
Aug 17" is *not yet*, say *not yet* in the first paragraph — and then lay out precisely what
turns it into *yes*.
