# Entenser Competitor Deep Dive — Product, Subscription Traction, and Repeat Visits

> A from-scratch, hands-on teardown of seven successful sports-data businesses, mined for
> mechanisms Entenser can adopt. This is **not** a market-sizing or positioning exercise —
> `docs/competitive-intelligence-2026-07-combined.md` already did that on 2026-07-16 and remains the
> strategic evidence base. This prompt goes one level down: **how these products are actually
> built, packaged, priced, billed, and made habitual**, screen by screen.
>
> Two targets (American Soccer Analysis, FotMob) appear in that earlier report at §3.6 and §3.7.
> Do not restate their positioning. Go below it: flows, pricing pages, notification settings,
> onboarding, paywall placement, billing screens. If a finding could have been written without
> opening the site, it does not belong in this report.

---

## Role & objective

You are doing competitive product research for **Entenser** (`entenser.com`), a market-blind
football forecasting site with a paid tier, **Club Watch**, approaching a controlled beta.

Every finding must serve one of four jobs. Tag each with its job — untagged findings are noise:

| Tag | Job | The question it answers |
|---|---|---|
| **ACQ** | Acquisition | How do strangers arrive, and what makes them stay past the first screen? |
| **CONV** | Subscription traction | What converts a free reader into a payer, and at what price/packaging? |
| **RET** | Repeat visits | What brings someone back tomorrow without being reminded? |
| **BILL** | Billing mechanics | What happens between "subscribe" and "cancelled," concretely? |

A fifth category exists and is valuable: **ANTI** — things a target does that Entenser should
deliberately *not* copy, with the reason. Rotowire and PFF will generate several. Record them; a
teardown that only finds virtues is not a teardown.

---

## Ground truth — load this before you open a competitor

You cannot judge a borrowed mechanism without knowing what it would be borrowed *into*. Read these
first, in this order. Budget an hour; it pays for itself.

| Source | What you need from it |
|---|---|
| `docs/STATUS.md` | What is live, what is blocked, the launch calendar, the money-path rule |
| `docs/paid-launch-decision-record.md` | The ten locked `G0` decisions — price, boundary, audience, scope freeze |
| `docs/growth-measurement-contract.md` | Population definitions, the event dictionary, the weekly scorecard |
| `docs/paid-claim-matrix.md` | What Entenser is permitted to claim, and with what evidence |
| `docs/competitive-intelligence-2026-07-combined.md` | The 2026-07-16 landscape — so you don't repeat it |
| `docs/product-strategy-2026-07-26.md` §2 | The existing retention thinking, including what was already rejected |
| `.interface-design/system.md` | The design contract any borrowed pattern must survive |

Then **use the live product as a stranger would**, before you look at anyone else:

1. `preview_start {url: "https://entenser.com"}` — Home, a league page, a club page, Rankings.
2. A generated club page, e.g. `/leagues/epl/` and one club forecast page, to see the acquisition layer.
3. `./scripts/intel_preview.sh free` on localhost for the **gated** Club Watch view, and
   `./scripts/intel_preview.sh` for the paid view. Magic links are single-use; a lost session needs
   a fresh run.

### The shape you are comparing against

- **78 leagues live**, 1,446 generated club pages, a 1,543-URL sitemap, dark quant-terminal PWA.
- **Free:** the public current answer, one-match scenarios, league race history, plus one registered
  synced club and one complete frozen Club Watch sample.
- **Paid (Club Watch):** continuous monitoring, change explanation, next-match stakes, continuity
  across visits, and up to ten clubs. **$5.99/mo · $59.99/yr** launch; **$7.99 · $79.99** standard.
- **No trial.** A published 30-day first-billing-period guarantee instead.
- **Auth is magic-link only** — no passwords. Billing runs through Stripe Checkout and the Stripe
  Customer Portal.
- **Live alerts and email briefings are not yet offered** — the UI says so. This is the single
  biggest structural gap versus FotMob, and the reason the RET findings matter most.
- **Market-blind invariant:** bookmaker odds are never a model input. Displaying model-vs-market
  *edge* is allowed and separate. No mechanism you recommend may breach this.
- **Operating reality:** one person, plus agents. Every recommendation carries a daily-cost estimate.

---

## Evidence discipline

Match the labeling convention already used in the combined intelligence report. Every factual claim
carries one:

- **Verified** — you observed it on a cited public URL, on a date you state. Include the URL.
- **Self-reported** — the company says it about itself. Not audited. Say so.
- **Observed** — the result of a test you ran (a search, a page load, a flow you walked).
- **Inference** — your analytical conclusion. Label it and give the reasoning.

Rules:

- **Date-stamp everything.** Pricing and packaging change; a claim without a date is worthless in
  three months.
- **Screenshot pricing, paywall, checkout, and account screens.** Save to the scratchpad and
  reference by filename. Text descriptions of a pricing table lose the thing that matters.
- **Never cite from memory.** If you believe Fangraphs Membership is $x, open the page. Your
  training data is older than these price points and several of these companies re-priced recently.
- **Use the Wayback Machine on every pricing page.** The *history* of a price is more informative
  than its current value: when they raised, what they bundled or unbundled, when a tier appeared or
  vanished, when annual-first appeared. Capture at least three points per target where available:
  earliest available, ~2 years ago, current.
- **App Store and Google Play listings are public billing disclosures.** In-app subscription SKUs
  and prices are listed without an account. Use them for FotMob, PFF, and Rotowire.
- **Store review text is churn evidence.** Filter to 1–2 star reviews and search for "cancel,"
  "refund," "charged," "auto-renew," "trial." This is the cheapest customer-evidence source you
  will find, and it maps directly onto the `BILL` job.

---

## Hard constraints

These are not negotiable and they bound the whole engagement:

- **Do not create accounts.** Not free accounts, not trial accounts, not throwaway ones.
- **Do not enter payment details anywhere, ever.** Not real, not test.
- **Do not purchase a subscription.** Where a paywall genuinely blocks a required observation, stop
  and file an escalation packet (below) — do not work around it.
- **Do not accept terms, consent banners beyond declining non-essential cookies, or any agreement.**
- **Walk checkout only to the point where payment details would be entered, then stop and back out.**
  Reaching a pricing or plan-selection screen is fine. Submitting anything is not.
- **No bulk scraping.** Read pages as a person would. Respect `robots.txt`. This is qualitative
  research; you need dozens of pages, not thousands.
- **No credentials from anywhere.** If a target's content is behind a login, it is out of scope
  unless the owner supplies access through the escalation path.

### Escalation packet — when a paywall blocks something material

Do not guess and do not skip silently. Write this, and continue with everything else:

```
BLOCKED: <target> — <what is behind the wall>
Why it matters: <which of ACQ/CONV/RET/BILL it answers, and what decision it would inform>
Cheapest unlock: <free account | $x one month | app-store IAP | nothing — genuinely unobtainable>
If unlocked, capture exactly: <3–6 specific screens or answers — a bounded shopping list>
Public substitutes already tried: <Wayback, help centre, ToS, store listing, reviews, forums>
Residual uncertainty if never unlocked: <what the report will not be able to say>
```

Collect these into one section of the final report so Ryan can make a single batched decision about
whether any subscription is worth buying — that is an owner decision, not yours.

---

## The common checklist — run on every target

Work one target at a time, completely, before starting the next. Findings decay and you will
conflate sites.

### A. First-visit value

- [ ] What is on screen **above the fold**, cold, logged out, on mobile and desktop?
- [ ] How many seconds to the first genuinely useful number or answer?
- [ ] Is there an onboarding step? Does it ask for a team/player/interest **before** an account?
- [ ] What is the site's atomic unit — a page type that is the reason people come? (Club page?
      Player page? Leaderboard? Match page?) Entenser's is arguably the league race page; test that.
- [ ] What does the empty/cold state do to earn a second click?

### B. Information architecture and entity pages

- [ ] Map the URL structure. Which entities get their own permanent, crawlable page?
- [ ] How deep does entity coverage go, and how is it interlinked? Sample five entity pages and
      count outbound internal links to sibling entities.
- [ ] What is on an entity page *besides* the primary table — history, context, related entities,
      user-generated content, embeds, exports?
- [ ] Search: does it work across entity types, and does it appear above the fold?
- [ ] Structured data present? (`view-source`, check JSON-LD.) What entity types?

### C. Free / paid boundary

- [ ] Draw the boundary precisely. What is free, forever, no account?
- [ ] What does a **free account** unlock that anonymous browsing does not?
- [ ] Where exactly is the paywall placed — before value, after a taste, or metered?
- [ ] Is the paywall hard, soft, metered, or feature-gated? Does it show you what you're missing?
- [ ] What is the upgrade prompt's copy and trigger? Screenshot it. **Note the emotional moment it
      fires at** — this is the transferable part, not the wording.
- [ ] Does the free tier get *better* over time, or is it frozen to protect the paid tier?

### D. Pricing and packaging

- [ ] Every tier, every price, monthly and annual, with the annual discount as a percentage.
- [ ] Is annual default-selected or pre-highlighted? Is monthly hidden or de-emphasised?
- [ ] Trial? Length, card-required or not, what happens at the end.
- [ ] Multi-product bundling — is there a discount for taking more than one thing?
- [ ] Any lifetime, founder, student, gift, or group pricing?
- [ ] Price history from Wayback: when did it change, and in which direction?
- [ ] What is the *pitch* — utility, patronage, ad removal, exclusivity, identity? Quote the headline.

### E. Checkout and billing mechanics — walk it to the payment wall, then stop

- [ ] How many screens from "subscribe" to the payment field?
- [ ] Is an account required first, or does account creation happen inside checkout?
- [ ] Is the total, the renewal date, and the renewal amount stated before payment?
- [ ] Auto-renew: opt-in or opt-out? Stated plainly or buried?
- [ ] Self-service cancellation — findable from the account page, or only by email/support?
      Count the clicks from logged-in home to the cancel control, using help docs and screenshots
      where you cannot log in.
- [ ] Refund policy: read the actual ToS/refund page. Pro-rata? Window? Discretionary?
- [ ] Dunning: what does the help centre say happens on a failed payment?
- [ ] Retention offers on cancel — pause, downgrade, discount? Help-centre and review text will
      reveal these.
- [ ] Renewal reminders — are they sent? Required by any jurisdiction the target operates in?

### F. Repeat-visit machinery — the core of this engagement

- [ ] **What changes daily?** Identify every element that is different on a second visit 24h later.
      Actually load the page twice, a day apart, and diff what you see.
- [ ] Is there a **daily ritual object** — a game, a puzzle, a standing "today" page, a leaderboard
      that resets?
- [ ] Notification design: what can you subscribe to, at what granularity? Screenshot the settings
      panel (public help docs cover this where an account is required).
- [ ] Email: cadence, format, personalization. Subscribe **only** where it costs no account and no
      personal data beyond an address you control — otherwise read the archive or a public sample.
- [ ] RSS, widgets, app widgets, live activities, calendar feeds — the surfaces that live *outside*
      the site.
- [ ] Personalization: following, favourites, watchlists. What does following actually *do*?
- [ ] Content cadence: how many editorial items per week, by whom, and how is that staffed?
- [ ] Community: forum, comments, Discord, Patreon. Volume, moderation model, and whether it
      generates content the operator doesn't have to write.
- [ ] Season/offseason: what does the product do when nothing is being played? Entenser has a real
      offseason problem across 78 leagues; steal any answer you find.

### G. Credibility and data provenance display

- [ ] How does the target prove its numbers are good? Public accuracy tracking, methodology pages,
      glossaries, changelogs, "how this is calculated" tooltips?
- [ ] Is there a **named, ownable metric** (a proprietary number with a brand)? How is it explained
      to a non-technical reader, and how does it travel into other people's writing?
- [ ] Where does the number's uncertainty get shown, if at all?
- [ ] Data export, embedding, and citation affordances — CSV, share-this-table, embed codes, an API.
- [ ] Attribution requirements, and whether they generate inbound links.

### H. Monetization beyond subscription

- [ ] Ads: present? Density, placement, network, and whether the paid tier removes them.
- [ ] Sponsorship: page-level sponsorship, newsletter sponsors, podcast reads.
- [ ] Affiliate/betting: present? How is it disclosed, and is it segregated from editorial?
- [ ] B2B, data licensing, API tiers, consulting, jobs board, merch.
- [ ] **For each: does it conflict with the target's stated credibility position, and how do they
      manage that tension?** Entenser has ruled out betting-affiliate revenue; the interesting
      question is which non-subscription revenue *doesn't* corrode a trust position.

### I. Operating cost

- [ ] Who runs this daily? Headcount, visible bylines, job postings, about page.
- [ ] What is automated versus hand-made?
- [ ] **The filter that matters:** could one person plus agents run this mechanism? Score every
      recommendation `solo-viable` / `needs help` / `impossible at current staffing`.

---

## The seven targets

Each entry says why it is on the list and the **one question it uniquely answers**. Run the full
common checklist on all seven; the notes below tell you where to spend the extra hours.

### 1. FanGraphs — `fangraphs.com`

**Why:** the closest business analog on the list. Public probabilistic projections, a season-long
odds page, an audited public record, and a membership that has funded the operation for nearly two
decades without paywalling the core numbers. This is approximately what Entenser is trying to be.

**Unique question:** *how do you sell a subscription on top of forecasts that stay free?*

Spend the extra time on:

- The **Membership pitch** itself. Read the copy word for word. It is simultaneously a patronage
  appeal, an ad-removal offer, and a tools upgrade. Which of the three leads? Quote it.
- **Tier structure** — the ad-free tier versus the higher tier, and precisely what separates them.
  Is the split "no ads" vs "more tools," and which one do they think sells?
- **Playoff-odds pages**: the change-since-yesterday columns, the season-long odds graph, mode
  toggles. Entenser's race pages and history charts are the same object. Diff them mercilessly —
  columns, defaults, what's linked, what's downloadable, what a returning user sees first.
- **The custom leaderboard / report builder** — selling *query power* rather than data access.
- **Daily editorial cadence** as the return-visit engine sitting on top of a reference product, and
  how many people it takes.
- Community: comment culture, and whether membership changes it.

### 2. FotMob — `fotmob.com` + iOS/Android listings

**Why:** the retention loop Club Watch is trying to build — follow a club, get told what happened,
come back — already exists here at mass-market scale and mobile-first quality.

**Unique question:** *what does a best-in-class follow-a-club notification system actually look
like, setting by setting?*

Spend the extra time on:

- **Onboarding**: how fast does it ask you to pick teams, and does it ask before or after any
  account step? Time it.
- **The full notification settings tree.** Every toggle, every granularity level, defaults on first
  install. This is directly transferable to Entenser's gated alerts, and Entenser has not yet
  shipped this surface — so borrowing a proven taxonomy is cheap and high value.
- **What a match-day sequence feels like** end to end: pre-match, kickoff, events, full time, and
  the morning after. Note what arrives when the user is *not* watching.
- **FotMob Plus**: exact price, what it gates (advanced stats, xG), and whether the gate lands
  before or after the habit is formed.
- **Widgets and Live Activities** — off-site surfaces that produce returns without a visit.
- **The offseason and the between-matches state** for a followed club. This is Entenser's hardest
  retention problem and FotMob has to solve it too.

### 3. Rotowire — `rotowire.com`

**Why:** explicitly requested for billing. A long-running multi-sport subscription business with
complex packaging, and a reputation worth understanding precisely rather than by rumour.

**Unique question:** *what does a mature, aggressive subscription billing system look like at every
step, and which of those steps would damage Entenser's trust position?*

This is the deepest **BILL** pass. Structure it against Entenser's own dress-rehearsal sequence in
`STATUS.md` blocker 6, step by step, so the comparison is directly usable:

| Entenser step | What to establish for Rotowire |
|---|---|
| Sign in | Account model, password vs link, whether sign-up gates the price |
| Start checkout | Screens to payment, what's disclosed, what's pre-selected |
| Pay | Tier/bundle structure, single-sport vs all-sport, monthly vs season pass vs annual |
| Durable entitlement | What access looks like, and whether it degrades in the offseason |
| Customer portal | Where subscription management lives and how findable it is |
| Cancel | Exact path, click count, retention interstitials, whether self-service exists |
| Refund | Written policy, window, pro-rata treatment, discretion language |

Then, and this is the point of including it:

- **Read 1–2 star app-store reviews and public complaint threads filtered for billing language.**
  Categorise the complaints: unexpected renewal, hard-to-find cancel, no refund, price change,
  bundle confusion. Count them. This is the `ANTI` list, evidenced.
- **Compare against Entenser's published guarantee.** Entenser has chosen no trial plus a 30-day
  first-period guarantee. Does Rotowire's structure suggest that choice is a competitive advantage
  worth *advertising*, or an unnecessary cost? Argue it from what you observed.
- Season-shaped pricing is genuinely interesting for a football product with an offseason — capture
  how in-season and out-of-season pricing differ, if they do.

### 4. American Soccer Analysis — `americansocceranalysis.com`

**Why:** same sport, overlapping audience, comparable team size. The realism check on every idea the
larger targets generate.

**Unique question:** *how does a tiny team sustain a paid layer without paywalling the analysis?*

Spend the extra time on:

- **g+ as a named, ownable metric**: how it is explained, where it is defined, and — most
  importantly — **how it travels** into other people's articles, broadcasts, and podcasts.
  Search for third-party citations and count them. Entenser has proprietary numbers and no
  ownable name for any of them; this is the cheapest credibility asset on the list.
- The **supporter/patron model**: price, tiers, what patrons actually get, and how it is pitched.
- The **interactive apps** — what is built, in what stack, and roughly what it would cost to
  maintain. These are the closest existing analogs to Entenser's interactive surfaces.
- **Podcast as the retention engine** for a team with no capacity for daily editorial. Cadence,
  format, and whether it drives the paid tier or just awareness.
- Where they publish besides their own site, and what that earns them.

### 5. Sports Reference — `fbref.com`, plus `baseball-reference.com` and `stathead.com`

**Why:** the reference layer as an unassailable moat, a paid tier that sells query power rather than
access, and — separately — the clearest proof on this list that a **daily game** can manufacture
repeat visits for a data site.

**Unique question:** *how do you monetise a free reference layer without damaging it, and what
converts a reference site into a daily habit?*

Spend the extra time on:

- **Stathead**: the paid product. Price, what it gates, and the crucial design decision — the data
  stays free, the *searching* is paid. Test the free query allowance and where the wall lands.
  This is the single most directly transferable pricing idea for Entenser, whose scenario tools and
  history are exactly this shape.
- **The daily-game object** (Immaculate Grid and its successors/imitators): what it is, where it
  lives, how it links back into entity pages, and what it did for traffic. Then ask the hard
  question — **what is the football-forecasting equivalent for Entenser, if any?** Be sceptical;
  a bad answer here is worse than none.
- **Page furniture on entity pages**: share/export links, embed affordances, glossary tooltips on
  every stat abbreviation, "on this page" navigation. Enumerate them exhaustively — this is a
  checklist Entenser's 1,446 club pages can be graded against directly.
- **Per-page sponsorship**, if still running — a monetization model that scales with page count
  rather than traffic, which suits a 1,543-URL site with no ad inventory.
- **The linking graph**: sample a player page and count internal links. Compare against a sampled
  Entenser club page and report both numbers.
- Cross-property consistency: one engine, many sports. Entenser runs one engine across 78 leagues —
  note where Sports Reference specialises per sport and where it refuses to.

### 6. Transfermarkt — `transfermarkt.com` / `.de` / `.co.uk`

**Why:** the largest football-data destination built on a number that is *argued about*. Enormous
entity-page depth, a community that generates the content, and localized domains.

**Unique question:** *how do you make a number into a conversation that people return for?*

Spend the extra time on:

- **The market-value mechanism**: who proposes values, how they are debated, who arbitrates, and how
  a change is surfaced and dated. This is a community-moderated data pipeline — describe it as a
  system. Entenser's numbers are model-generated and non-negotiable, so the transferable part is
  the *surfacing of change and the invitation to disagree*, not crowd-sourcing the number itself.
- **Club and player page anatomy**: section by section. Which sections are data, which are
  community, which are editorial, which are ads.
- **Forum and comment volume** — and what it does for the sitemap and search presence.
- **The rumour/transfer feed**: how unverified information is labelled and how reliability is
  signalled. Entenser has a hard claim-truth contract (`docs/paid-claim-matrix.md`); how a large
  site handles uncertain information at scale is directly relevant.
- **Localized domains**: what differs beyond language — content, ordering, ads, pricing.
  Note this against `G0.9`, which freezes localization. The finding is intelligence for later,
  not a proposal for now — say so explicitly.
- **Ad density** and what it costs the experience. Be blunt; Entenser has chosen a clean surface and
  needs to know what it is giving up and gaining.

### 7. PFF — `pff.com`

**Why:** a proprietary grade sold as the product, tiered by audience, with a free content layer
feeding a hard paywall.

**Unique question:** *how do you package one proprietary number into multiple priced products for
different audiences?*

Spend the extra time on:

- **The tier matrix**: every consumer tier, its price, its audience, and the exact feature deltas.
  Build the matrix as a table. This is the reference artifact for any future Entenser tiering
  conversation — and note that `G0.9` currently freezes a Creator tier, so this is preparation,
  not a proposal.
- **Annual-first pricing presentation** and how monthly is de-emphasised.
- **The free layer**: what articles and rankings are free, and how they are engineered to end at the
  paywall. Where does a free article stop?
- **The grade as a brand**: how a single proprietary number is explained, defended, and syndicated.
  Look for the methodology/explainer pages and how prominently they are linked.
- **What to reject:** PFF is betting-adjacent and Entenser is not. Sort every PFF finding into
  "packaging craft, portable" versus "depends on a betting or fantasy audience Entenser has
  explicitly deprioritised" (`G0.3` makes bettors secondary and non-public). Both lists are useful;
  conflating them is not.

---

## Cross-site synthesis — required

Individual teardowns are inputs. These tables are the deliverable. Build each one only from findings
you actually recorded, with the source site named in every cell.

1. **Pricing and packaging matrix** — every target × {tiers, monthly, annual, annual discount %,
   trial, what's gated, what stays free, ad-free included, price change history}.
2. **The free/paid boundary spectrum** — order all seven from "everything free, subscription is
   patronage" to "core product paywalled." Place Entenser on the same line and state whether its
   current boundary is coherent or is sitting in a dead zone between two working models.
3. **Repeat-visit mechanism inventory** — every distinct mechanism observed, which targets use it,
   the visit frequency it implies (daily / weekly / match-day / seasonal), and its daily operating
   cost. Rank by (frequency × cost⁻¹).
4. **Billing mechanics comparison** — the seven Entenser dress-rehearsal steps as rows, targets as
   columns. Mark every cell you could not verify as unknown rather than guessing.
5. **Credibility-display inventory** — how each target proves its numbers are worth trusting, and
   which techniques Entenser does not currently use.
6. **Named-metric audit** — which targets own a branded metric, how it is explained, how it travels.
   End with a direct recommendation: should Entenser name one of its numbers, which one, and what it
   would cost. Say "no" if the honest answer is no.

---

## Translating findings into Entenser work

This section is what separates a useful report from a list of screenshots. **Every idea gets routed.**

### Route each candidate through these gates, in order

1. **Does it breach the market-blind invariant?** Bookmaker odds as a model input → reject outright,
   no discussion.
2. **Does it breach the claim-truth contract?** Check `docs/paid-claim-matrix.md`. Anything implying
   profit, guaranteed edge, or accuracy Entenser cannot evidence → reject, and note the near-miss.
3. **Does it breach the `G0.9` scope freeze?** New leagues, extra paid modules, a Creator tier,
   localization, group pricing, betting-led acquisition → **do not propose it as work.** Record it
   in a separate "post-freeze candidates" list with the evidence, so it is ready when the gate opens.
   Do not smuggle frozen scope in as a "small improvement."
4. **Does it touch the money path before the first production transaction?** `STATUS.md` is explicit
   that no feature outranks completing one real transaction. Anything touching checkout, billing, or
   entitlement → propose as post-transaction, unless it is a defect.
5. **Does it survive the design contract?** Check `.interface-design/system.md`. A pattern that needs
   card-on-card, decorative shadows, or hero type inside a panel needs redesign before proposal.
6. **Is it solo-viable?** If it requires daily human editorial, say so and price it in days per week.

### Then rank what survives

Build one table, sorted by (impact ÷ effort):

| Idea | Source | Job | Impact | Effort | Gate status | Evidence |
|---|---|---|---|---|---|---|

Where **gate status** is one of: `ship-before-2026-08-17`, `after-first-transaction`,
`post-freeze — needs owner decision`, `rejected — <gate>`.

Impact must be argued against Entenser's actual funnel, using the definitions in
`docs/growth-measurement-contract.md` — activation, core value event, active paid, engaged paid.
"Would improve retention" is not an impact claim. "Would create a between-matches core value event
for followed clubs, which currently only fire on match days" is.

### The three questions the report must answer directly

Answer these in plain prose at the top of the report, before any table:

1. **Is Entenser's free/paid boundary the right one?** Compare against all seven and say so. The
   boundary is locked at `G0.5`, so a challenge here needs to be strong enough to be worth
   re-litigating — but if the evidence says the boundary is wrong, say it plainly. That is a finding,
   not insubordination.
2. **What is the single highest-value repeat-visit mechanism Entenser does not have?** One answer,
   defended, with a cost.
3. **What should Entenser stop planning to do**, based on watching someone else do it badly or
   expensively? At least one answer. A report with no subtractions has not been critical enough.

---

## Output format

Write to `docs/competitor-deep-dive-<YYYY-MM-DD>.md`. Report after **each target** — do not save it
all for the end.

### Per target

```
## <n>. <Target> — <primary URL>
Reviewed: <date> · Surfaces walked: <list> · Blocked by paywall: <yes/no>

Unique question answered: <one paragraph — the thing only this target could teach>

ACQ findings
- <mechanism> · observed at <URL> · <evidence label> · why it works · Entenser applicability

CONV findings
- <as above>

RET findings
- <as above>

BILL findings
- <as above>

ANTI — do not copy
- <mechanism> · why it would damage Entenser specifically

Pricing snapshot
| Tier | Monthly | Annual | Annual discount | Gates | Ads removed |

Operating cost read
- <headcount/automation evidence> → solo-viable | needs help | impossible

Screenshots
- <scratchpad filenames, with what each shows>

Unknowns
- <what you could not establish, and the escalation packet reference if any>
```

### Final rollup

- The three direct answers, in prose.
- The six synthesis tables.
- The ranked, gate-routed backlog.
- The post-freeze candidate list, held separately.
- All escalation packets, batched for one owner decision.
- **Coverage statement:** which targets × surfaces you actually exercised, what you could not reach,
  and what the report therefore cannot claim.

Every finding must be concrete and sourced. "Fangraphs has good retention" is not a finding.
"Fangraphs' playoff-odds page leads with a change-since-yesterday column, so the page has different
content on every visit without any editorial work; Entenser's race pages show current probability
only and would need `<x>` to match — observed 2026-08-0x at `<URL>`" is.

---

## Guardrails

- **No accounts, no payments, no submitted forms, no accepted terms.** Escalate instead.
- **Cite, don't recall.** Every price, tier, and feature claim carries a URL and a date.
- **Label every claim** Verified / Self-reported / Observed / Inference.
- **One target at a time**, full checklist, findings block written, before the next.
- **Do not restate `competitive-intelligence-2026-07-combined.md`.** If a finding is at positioning
  altitude, it is out of scope. Mechanics only.
- **Route every idea through the gates.** An unrouted idea list is a failed deliverable.
- **Frozen scope stays frozen.** Record post-freeze candidates separately; never propose them as
  current work.
- **Price every recommendation in operator days per week.** One person runs this.
- **Preserve the market-blind invariant** in every proposal.
- **Do not write code and do not change the product in this pass.** This is research. Implementation
  is a separate, owner-approved step.
- **Check for a concurrent session before committing:** `git log` plus running processes.
- **Update docs per `CLAUDE.md`** — append a verdict to the active plan file, and update
  `docs/STATUS.md` only if the research changed current product truth.

---

## Kick-off

The order is deliberate: establish the business model frame first, then the retention loop closest
to Club Watch, then the billing pass, then the realism check, then the reference and community
giants, then packaging.

1. **FanGraphs** — the closest business analog. Sets the frame for everything after it.
2. **FotMob** — the follow-a-club retention loop Club Watch is trying to build.
3. **Rotowire** — the full billing teardown against Entenser's seven dress-rehearsal steps.
4. **American Soccer Analysis** — same sport, same size; the cost-realism check on ideas 1–3.
5. **Sports Reference / FBref / Stathead** — the free-layer moat, paid query power, the daily game.
6. **Transfermarkt** — entity-page depth and community at scale.
7. **PFF** — tiering and the named proprietary metric.

Before target 1, complete the ground-truth pass: read the seven documents, walk `entenser.com` cold
on mobile and desktop, and open both the gated and paid Club Watch views on localhost. You cannot
evaluate a borrowed mechanism without knowing the thing it would be borrowed into.
