# Entenser Competitor Deep Dive — Product, Subscription Traction, Repeat Visits

**Executed:** 2026-08-01 · **Prompt:** `docs/prompts/competitor-deep-dive.md` ·
**Scope:** FanGraphs, FotMob, Rotowire, American Soccer Analysis, Sports Reference/FBref/Stathead,
Transfermarkt, PFF

**Evidence labels:** *Verified* = observed on a cited public URL on the stated date ·
*Self-reported* = company's own claim, unaudited · *Observed* = result of a test run during this
review · *Inference* = analytical conclusion, labeled as such.

**Constraints honored:** no accounts created, no payment details entered, no subscription purchased,
no forms submitted, no terms accepted. Checkout flows walked only to the point where payment details
would be entered.

## Corrections to this report

**Correction 1 (2026-08-01, after review).** The first draft stated that Entenser's static club pages
carry no track/sign-in/price CTA and that the funnel event `track_club` was "unreachable from the
entire acquisition layer." **That was wrong.** It came from a detection regex testing for the literal
phrase "track this club"; the shipped copy is `Track Arsenal with Club Watch →`. Re-verified directly
on production: `#clubWatchCTA` exists, links to
`/?league=intel&intelLeague=epl&team=…&track=1`, and carries a `gtag('event','track_club')` hook.
The generator is `scripts/build_static_pages.py:943–959`, committed in `1d954fa`.

What survives the correction: club pages are **266 words vs FBref's 5,583**, the CTA sits **below**
all the data where FotMob's Follow sits above it, and the **78 league pages carry no Club Watch path
at all** and never mention the product. Affected sections have been amended in place.

**Correction 2.** The annual-discount reading in §1 (FanGraphs) was revised after §5 (Stathead)
showed the category runs two conventions, not one. Entenser's 17% is not an outlier.

---

# The three answers

## 1. Is Entenser's free/paid boundary the right one?

**Yes — and more confidently than expected.** `G0.5` puts the current answer, one-match scenarios and
league race history on the free side, and continuity, explanation, stakes and multi-club on the paid
side. That is a **metered** boundary rather than a binary one: the same objects exist on both sides,
in limited and unlimited form. Two independent targets have converged on exactly that shape from
opposite directions — Stathead keeps all the data free and charges for the ability to *query* it, and
PFF gives "limited access" to the same grades and tools it sells "unlimited" access to. Neither is a
philosophical cousin of the other, which makes the agreement worth something.

There is one real challenge, from Transfermarkt. The single most engaging free surface on the biggest
football data site in the world is *the argument about what changed and why* — which is close to the
job Club Watch sells. The lesson is not that the boundary is wrong; Transfermarkt's "why" is crowd
opinion monetised by heavy advertising, and Entenser's is a model-supported causal account monetised
by subscription. The lesson is a **requirement**: the free tier has to carry enough "what changed" to
start the conversation, because conversation is how a site with no ad budget and no newsroom gets
found. The design does carry it — public race history, public movers, one complete free sample.

**But it is not carrying it today.** The live movers strip is publishing six impossible ±100.0
moves, and the news rail is filing darts and cricket under football league labels. Both fixes exist
in the working tree and are undeployed. So the honest verdict is: *the boundary is sound; its free
side is currently under-delivering for deployment reasons, not design reasons.*

## 2. What is the single highest-value repeat-visit mechanism Entenser does not have?

**A "changes since <date>" display mode**, of the kind FanGraphs ships on its playoff odds page.
Selecting it rewrites the URL to `?mode=changes&date=…&dateDelta=…` and re-renders the same columns
as a diff against a baseline date the reader chooses, defaulting to seven days back.

It wins on every axis that matters here. It costs almost nothing to run, because it is a display mode
over data that already exists rather than a digest someone has to generate. It is **not
personalised**, so it needs no account, works logged out, and is shareable and indexable — three
things a "since your last visit" digest can never be. It has something to say on any day where any
window contains movement, including preseason, which is the state 78 leagues spend a large part of
the year in and which currently leaves Entenser's pages completely static. And Entenser's own product
strategy already identified the underlying idea as a top-three retention play while assuming a more
expensive personalised form.

Most importantly, **the hard prerequisite already shipped**. A diff view needs a dated archive of
probability snapshots with trustworthy provenance; that landed on 2026-07-31 — 5,725 reconstructed
team-points merged with exact archives, reconstructed and archived segments visibly distinguished.
The expensive part is done and is currently being used for one chart.

*Runner-up, with a higher ceiling and a longer build:* a daily cross-league "which club is stronger?"
duel over the 892-club shared ELO scale. Immaculate Grid is proof that one engineer can build a daily
game that lifts a data site's traffic 20–30%.

## 3. What should Entenser stop planning to do?

**Stop planning a second paid tier — permanently, not until the freeze lifts.** `G0.9` currently
defers a Creator tier. The evidence says retire it. PFF, the market leader in selling a proprietary
sports grade, **folded PFF Edge and PFF Elite into a single PFF+ plan**. Rotowire sells one
subscription across all sports. FanGraphs lists five SKUs at two prices, which is one product wearing
five labels. Three of the four paid targets converge on one consumer tier, and one of them got there
by dismantling the alternative. Treat `G0.9` as a finding, not a holding pattern.

**And stop treating price as the lever.** Entenser sits in a defensible band — 3.75× FotMob, 0.75×
FanGraphs and Stathead, with its standard annual exactly matching PFF's sale annual. The pricing
questions this review surfaced (deeper annual discount, multi-year prepay, seasonal SKUs) are real
but second-order, and all of them are `G0.6`-locked anyway.

The first-order problem is the **acquisition layer's thinness and its uneven door into the product.**
Club pages do carry `Track {team} with Club Watch →` with a working `track_club` hook — that part is
built and live (Correction 1). But those pages are **266 words against a competitor's 5,583**, the
CTA sits below all the data rather than above it, and the **78 league pages — the higher-traffic
surface for "Premier League predictions" — carry no Club Watch path and never name the product.**
Thickening those pages and evening out the door costs template work, not pricing work. No pricing
change would matter until that is done.

---

## Entenser baseline — measured 2026-08-01

Recorded first so every competitor finding has something to compare against. All *Observed* on
production.

| Surface | Measurement |
|---|---|
| Home hero | "Know what every match means for your club's season." CTAs: *Track my club* / *Explore free forecasts* |
| Free boundary copy | "Current forecasts across 70+ competitions remain free." |
| Static league page (`/leagues/epl/`) | 53 links, 41 of them club pages, 1 JSON-LD block, self-canonical |
| Static club page (`/leagues/epl/clubs/arsenal/`) | **266 words**, 26 links, 17 sibling-club links |
| **Club-page Club Watch CTA** | ✅ **Live.** `Track Arsenal with Club Watch →` (`#clubWatchCTA`) → `/?league=intel&intelLeague=epl&team=…&track=1`, with a `gtag('event','track_club')` hook |
| **League-page Club Watch CTA** | ❌ **None.** 455 words; only "Open the interactive Premier League dashboard →"; the phrase "Club Watch" does not appear |
| Club page content | Current probabilities, expected finish, global ELO, upcoming match W/D/L |
| EPL state on review date | `PRE-SEASON` — 0 pts, 0 matches, priors only, first fixture 2026-08-21 |

**Two live trust defects observed on the home page**, both already fixed in the working tree but
sitting in `STATUS.md` as 🟡 Built, not deployed:

1. **Biggest Movers shows ▲100.0 / ▼100.0 saturation artifacts** — SJK, Sligo Rovers, FCSB, Jaro,
   CSU Craiova, FC Arges all at exactly ±100.0. `build_movers.py` withholds these in the working
   tree ("46 suppressed, 0 of the 0↔100 artifacts remain") but the fix is undeployed.
2. **"Your Stories" news routing is publishing non-football under football labels** — darts
   (Price/Littler) tagged `EFL League One`, cricket (SunRisers/Ravindra) tagged `Premier League`,
   rugby league tagged `Ligue 1`. Word-boundary routing and non-football rejection exist in the
   working tree; also undeployed.

*Inference:* these two matter more than any finding in this report. Every competitor below spends
real effort on credibility display (§G findings throughout), and Entenser's entire strategic
position is "the model that grades itself in public." A home page showing darts under a football
league label and six impossible ±100pp moves undercuts that position on first visit. **Deploying
the existing fixes outranks adopting anything new in this document.**

---

## 1. FanGraphs — `fangraphs.com`

**Reviewed:** 2026-08-01 · **Surfaces walked:** home, blogs index, membership product page, playoff
odds (Default + Changes modes), playoff odds graphs · **Blocked by paywall:** no (all observations
made logged out)

**Unique question answered.** FanGraphs proves you can sell a subscription on top of forecasts that
stay free, by making the subscription a *patronage* purchase wrapped around a bundle of small
conveniences — none of which is individually worth $80, and none of which gates the core numbers.
The playoff-odds page also turns out to hold the single most transferable mechanism in this entire
review: a **Changes display mode** that converts a static probability table into a diff against a
user-chosen baseline date, at zero editorial cost.

### CONV findings

- **The pitch is patronage-first, not feature-first** *(Verified, 2026-08-01,
  [membership page](https://plus.fangraphs.com/product/fangraphs-membership/))*. Headline: "By
  becoming a FanGraphs Member, you're supporting our mission to provide quality baseball analysis by
  helping fund thousands of articles per year, as well as our growing collection of tools and
  stats." The feature list appears *below* the mission statement. The interstitial modal
  (screenshot below) carries no feature list and no price at all — only "All the great work that
  you've come to rely on is made possible by Member support."
  **Entenser applicability:** high. A solo operator's most honest and most defensible pitch is
  patronage, and Entenser currently has no patronage framing anywhere — Club Watch is sold purely on
  utility. Worth testing as secondary copy beneath the utility pitch, *not* replacing it.

- **The conversion moment is feature-triggered, not page-load-triggered** *(Observed, 2026-08-01)*.
  The membership modal did not fire on landing. It fired when I switched the playoff-odds page into
  **Changes** mode — i.e. at the moment of consuming an advanced view. **Entenser applicability:**
  this independently validates the outcome-triggered conversion moments Entenser already shipped
  (`STATUS.md`: "Approved outcome conversion… route into club-specific Club Watch continuation copy
  without paywalling the value just consumed"). No change needed; it confirms the existing design is
  the industry-correct one.

- **Tier structure is a decoy — there is effectively one price** *(Verified, 2026-08-01)*. The
  product page lists five SKUs: Monthly $15, Yearly $80, Ad Free Monthly $15, Ad Free Yearly $80,
  Ad Free 3-Year $200. The "Ad Free" and plain variants are the *same price*. The only real ladder
  is interval: month / year / 3-year.
  **Entenser applicability:** the **3-year prepay at $200** (vs $240 at the annual rate, ~17% off)
  is the interesting object — it removes two renewal decisions and converts a retention problem into
  a cash-up-front problem. `G0.6` locks monthly and annual only; a multi-year SKU is a post-freeze
  candidate, not current work.

- **The annual discount is enormous: $15/mo vs $80/yr = 56% off** *(Verified)*. Entenser's
  $5.99/mo vs $59.99/yr is **17% off** — roughly "two months free," the conventional SaaS ratio.
  *Inference:* FanGraphs is pricing monthly as a deliberate penalty to push everyone to annual, which
  for a seasonal sport is a churn defence — an annual subscriber cannot cancel in the offseason.
  Football has the same seasonality problem, arguably worse across 78 leagues with staggered
  calendars.

  **Corrected after target 5:** on first pass this looked like evidence that Entenser's 17% was an
  outlier. It is not. Sports Reference/Stathead prices annual at exactly "two months free" — the same
  17% Entenser chose — so the category runs **two conventions**, not one. See the synthesis table;
  the real question is which convention fits a seasonal product, not whether 17% is wrong.

- **Price increases are announced publicly, in advance, with reminder posts** *(Verified via
  [FanGraphs blog](https://blogs.fangraphs.com/a-note-on-membership-pricing/) and
  [reminder post](https://blogs.fangraphs.com/instagraphs/last-day-before-membership-price-increase/))*.
  Price history: **2017 $50/yr** (Ad Free introduced) → **June 2021 $60/yr** (base yearly $20→$25) →
  **August 2025 $80/yr**. Four-year holds between increases, each pre-announced as an article.
  **Entenser applicability:** directly relevant. Entenser has *already decided* on a launch price
  ($5.99/$59.99) below a standard price ($7.99/$79.99) with four immutable Stripe Prices. FanGraphs
  shows the mature version of that move: hold for years, then raise loudly and honestly, treating the
  increase as a trust event rather than something to hide. Worth writing into the launch plan now, so
  the launch-vs-standard transition has a published playbook rather than an awkward silence.

### RET findings

- **★ The `Changes` display mode — the single most transferable mechanism in this review**
  *(Verified/Observed, 2026-08-01)*. The playoff odds page has three Display Options: **Default,
  Changes, Distribution**. Selecting *Changes* rewrites the URL to:

  ```
  /standings/playoff-odds/fg/div?mode=changes&date=2026-08-01&dateDelta=2026-07-25
  ```

  and the page renders "the playoff odds diff" — the same columns, expressed as movement between two
  dates. **`Change Since` is a user-driven date picker**, defaulting to 7 days back, with forward and
  backward calendar navigation.

  Why this matters for Entenser specifically: `docs/product-strategy-2026-07-26.md` §2 Tier 1 item 2
  already identifies "what changed while you were away" as a top-three retention idea, and notes the
  data exists (`race_deltas_history.parquet`, `build_race_deltas.py`). FanGraphs' version is
  **cheaper than the version Entenser is planning**, because it is not personalized and not a digest
  — it is a display mode on a page that already exists, with a URL that is shareable, linkable, and
  indexable. It also solves the offseason/quiet-period problem: a diff view has something to say
  whenever *any* window contains movement, and the user chooses the window.

  The prerequisite is a dated archive of probability snapshots per league — **which Entenser shipped
  on 2026-07-31** (point-in-time season history, 5,725 reconstructed team-points plus archived
  forecasts, reconstructed/archived provenance preserved). The hard part is already done.
  **Applicability: highest in this report.** Cost estimate: low — a mode toggle over an existing
  payload, no new pipeline. Solo-viable.

- **Selectable projection models, including a "Coin Flip" naive baseline** *(Verified)*. Projection
  Mode offers: FanGraphs, FG WAR, ATC, THE BAT X, OOPSY, Season to Date, **Coin Flip**. A reader can
  switch the entire table to a naive baseline and see what the model is actually adding.
  **Entenser applicability:** this is Entenser's public-calibration story rendered as an interactive
  control instead of a static audit page. Entenser already computes Brier against naive and market
  baselines; exposing "show me the coin-flip table" on a race page would make the market-blind,
  graded-in-public position *legible to a non-quant on the page where it matters*, rather than
  requiring a trip to an About page written in insider vocabulary (a weakness §5 of the July
  intelligence report already flagged). Cost: low-medium. Note the claim-truth constraint — the
  comparison must be presented as calibration evidence, never as an edge claim.

- **Point-in-time snapshot selection is a first-class control** *(Verified)*. "Quick Dates" offers
  preseason snapshots back to 2016, plus an arbitrary date calendar.
  **Entenser applicability:** validates the history work shipped 2026-07-31 and suggests surfacing it
  as a *control on the race page* rather than a separate History view.

- **Editorial cadence ≈ 10 articles in 7 days across ~8 named bylines** *(Verified,
  [blogs index](https://blogs.fangraphs.com/), 2026-08-01)*: Ben Lindbergh, Dan Szymborski, Ryan
  Blake, Eric Longenhagen, Davy Andrews, Brendan Gawlowski, Michael Baumann. Plus podcasts and
  prospect chats. **Entenser applicability: none directly — this is the boundary of the analogy.**
  FanGraphs' daily-return engine is a newsroom. Entenser has one person. Every FanGraphs retention
  mechanism that depends on human writing is out of reach; the two that don't (Changes mode, model
  toggles) are exactly the two ranked highest above. *Score: `impossible at current staffing` for the
  editorial engine; `solo-viable` for the tooling.*

- **Playoff Odds Graphs** — season-long probability trajectory lines, selectable by league, division,
  team, metric (Make Playoffs / Win Division / Clinch WC / Win WS) and projection mode; **free**
  *(Verified)*. This is a near-exact analog of Entenser's race history chart, with two deltas worth
  copying: metric switching within one chart, and multi-team overlay on one axis.

### ACQ findings

- **Free/paid boundary is unusually generous:** playoff odds, odds graphs, leaderboards, and the
  article stream are all free logged-out. What membership buys is *unlimited* articles, ad-free,
  **one-click data exports**, mailbag access, historical/platoon projections, dashboard
  customization, dark/classic modes, and homepage photo removal *(Verified)*.
  *Inference:* the gate is placed on **convenience, personalization, and comfort** — not on data.
  Note that three of the nine listed benefits (dark mode, classic mode, photo removal) are pure
  display preferences that cost almost nothing to build and nothing to run.
  **Entenser applicability:** Entenser's `G0.5` boundary is philosophically identical (public current
  answer free; continuity, explanation and monitoring paid), which is reassuring. But Entenser's paid
  side is *all* high-cost machinery. FanGraphs suggests padding a paid tier with cheap comfort
  features materially increases perceived value per dollar. Candidates that don't breach the claim
  matrix: saved views, custom club ordering, export convenience, density preferences. Cost: low.
  **Caution:** `docs/paid-claim-matrix.md` explicitly lists "ad-free" and "blanket CSV promise" in the
  *remove or replace* column for Pricing/Support — Entenser has no ads to remove, and CSV is
  contractually free. So copy the *pattern* (cheap comfort in the bundle), not the specific items.

### BILL findings

- Membership SKUs are explicitly labeled "(Auto Renewing)" in the product name itself *(Verified)* —
  auto-renewal disclosed in the SKU title, before checkout, rather than in fine print.
  **Entenser applicability:** free, honest, and directly compatible with the approved legal copy work
  in blocker 5. Adopt the labeling convention.
- Checkout not walked further; no account exists and none was created.

### ANTI — do not copy

- **Five SKUs where two would do.** "Monthly / Yearly / Ad Free Monthly / Ad Free Yearly / Ad Free
  3-Year" at two distinct prices is a legacy artifact that requires a reader to work out that the
  first two and next two are the same money. Entenser's four immutable Prices already risk this;
  keep the *customer-visible* choice to exactly two (monthly, annual).
- **The interstitial modal covering the feature the user just requested.** It fired over the Changes
  table before I could read it. Entenser's approved pattern — continuation copy *after* the value is
  consumed, without paywalling it — is better, and the claim matrix forbids "gating the scenario just
  used." Do not regress toward the modal.

### Pricing snapshot

| Tier | Monthly | Annual | 3-Year | Discount vs monthly | Gates |
|---|---|---|---|---|---|
| Membership | $15 | $80 | — | 56% | unlimited articles, exports, mailbag, projections, customization |
| Ad Free Membership | $15 | $80 | $200 | 56% (annual), ~17% (3yr vs annual) | as above + ad removal |

Price history *(Verified via company blog posts)*: 2017 $50/yr → Jun 2021 $60/yr → Aug 2025 $80/yr.

### Operating cost read

~8+ named writers, podcasts, prospect coverage, RosterResource. **Editorial engine: impossible at
current staffing. Tooling mechanisms (Changes mode, model toggles, odds graphs): solo-viable.**

### Screenshots

- Membership interstitial over the Changes view — yellow modal, "Support FanGraphs / Become a
  Member", green "Sign Me Up", no price shown, `Already a Member: Log In` beneath. Captured in
  session 2026-08-01. Also visible: Projection Mode row (FanGraphs / FG WAR / ATC / THE BAT X /
  OOPSY / Season to Date / Coin Flip) and the `Change Since  7/25/2026 → 8/1/2026` date pair.

### Unknowns

- Member-only surfaces (mailbag, Walk-Off, historical/platoon projections, one-click exports) were
  not observed — no account was created. Escalation packet EP-1 below.
- Whether the Changes mode is itself member-gated after the modal, or merely modal-interrupted, is
  unresolved: the table rendered behind the modal, suggesting free. *Low confidence.*

---

## 2. FotMob — `fotmob.com` + iOS listing

**Reviewed:** 2026-08-01 · **Surfaces walked:** web team page (Arsenal), news hub, US App Store
listing · **Blocked by paywall:** partially — the in-app notification settings tree requires the
installed app (EP-2)

**Unique question answered.** FotMob is the price and expectation anchor Entenser's buyers already
live inside, and it demonstrates that the follow-a-club retention loop is won on the **club page
itself changing daily**, not on the notification alone. Its club page has something new every day
with zero human writing — which is precisely the problem Entenser has not solved.

### CONV findings — the pricing reality check

- **FotMob's full IAP ladder** *(Verified, [US App Store listing](https://apps.apple.com/us/app/fotmob-soccer-live-scores/id488575683), 2026-08-01)*:

  | SKU | Price |
  |---|---|
  | Standard Monthly | **$1.99** |
  | Standard Annual | **$15.99** |
  | 3 months membership | $4.99 |
  | FotMob Gold Member | $2.99 |
  | Family Monthly | $2.99 |
  | Family Annual | **$29.99** |
  | Remove ads / Remove all ads | $2.99 |

  App rating **4.9 across ~169,000 ratings**; 400+ competitions covered.

- **★ The uncomfortable number: Entenser's $59.99/yr is 3.75× FotMob's $15.99/yr.** *(Inference from
  two Verified prices.)* A committed supporter evaluating Entenser has very likely already paid, or
  declined to pay, $15.99 for an app that covers their club with live scores, xG, shot maps,
  highlights, and alerts across 400+ competitions. This does not make Entenser's price wrong —
  Club Watch sells a different job (`G0.4`: "tell me what changed, why, and what the next match can
  change") and `G0.6` is locked — but it does mean **the price needs an explicit answer to "why is
  this four times FotMob?"** in the pricing copy, and that answer must be about the job, not the
  data. Right now no Entenser surface addresses it, because no Entenser surface names a competitor.
  *Recommended: not a price change — a positioning sentence.* Ship-before-launch, low cost.

- **Ad removal is unbundled and cheap ($2.99), separate from the subscription** *(Verified)*.
  *Inference:* FotMob discovered a segment that will pay to remove annoyance but not for features,
  and sells to it separately. **Entenser applicability: none — Entenser has no ads**, and the claim
  matrix explicitly bans "ad-free" as a paid claim. Recorded for completeness.

- **Family Annual at $29.99 is only 1.9× the individual annual** *(Verified)*. A household expansion
  SKU at a shallow multiple. **Entenser applicability:** `G0.9` freezes group pricing; post-freeze
  candidate. Worth noting that Club Watch's up-to-ten-clubs allowance already contains most of the
  value a family plan would deliver, so the two may be substitutes rather than additions.

- **A 3-month SKU ($4.99)** exists alongside monthly and annual *(Verified)*. *Inference:* a
  season-shaped or tournament-shaped commitment — buy it for the run-in, or for a World Cup. For a
  product covering 78 leagues with staggered calendars and long offseasons, a term shorter than a
  year and longer than a month is a genuinely interesting third option. Post-freeze candidate
  (`G0.6` locks two intervals).

### RET findings — the machinery Club Watch is trying to build

- **★ The club page changes every day without a writer** *(Verified,
  [Arsenal team page](https://www.fotmob.com/teams/9825/overview/arsenal), 2026-08-01)*. Section
  order, top to bottom: tabs (Overview / Table / Fixtures / Squad / Player stats / Team stats /
  Transfers / History) → prominent **Follow** button → **Next Match** → **"Daily Summary" — three
  news items in a generated AI summary** → team form (last five, with crests and scores) → key stats
  incl. per-manager win% and points-per-game → last starting XI with player ratings → full league
  table → stadium info. **Nothing is gated or marked Plus.**

  The comparison is stark. Entenser's Arsenal page is **266 words, static, with no follow control and
  nothing that differs tomorrow.** FotMob's has a next match, a form strip, an auto-generated daily
  summary, and player ratings — at least three elements that change without anyone writing anything.
  **This is the concrete shape of Entenser's repeat-visit gap**, and it sits on the exact surface
  Entenser has 1,446 of.

- **★ It answers the offseason question, which Entenser currently fails** *(Observed, 2026-08-01)*.
  On review date the Premier League has not started. Entenser's EPL page reads `PRE-SEASON`, 0 pts,
  0 matches, priors only — honest, and *completely static* until 2026-08-21. FotMob's Arsenal page
  on the same day shows a preseason friendly as the next match, transfer-rumour content in the daily
  summary, and manager commentary. **The answer to "what does a club page do when nothing is being
  played" is: fixtures that aren't league fixtures, plus transfers, plus generated summary.** Entenser
  models none of these and need not — but it does need *something* in that slot, and the review's
  strongest candidate is the FanGraphs Changes mode (§1), which has something to say in a preseason
  window precisely because priors move as squads change.

- **Follow is on the club page, above the data, with no account required to press it**
  *(Verified)*.

  **Corrected 2026-08-01 (see Correction 1).** An earlier draft of this report claimed Entenser's
  club pages had no follow control. That was a false negative from a bad regex. **Entenser's 1,446
  club pages do carry `Track {team} with Club Watch →` with a `track_club` analytics hook, live in
  production.** The real gaps against FotMob are narrower and two: the CTA sits **at the bottom**,
  after all the data, where FotMob's Follow sits **above** it; and the **78 league pages carry no
  Club Watch path at all** and never mention the product.

- **Notification taxonomy** *(medium confidence — secondary sources: App Store description plus
  third-party guides; the settings tree itself needs the installed app, EP-2)*: per-team and
  per-league follows, with alerts for **goals, red cards, kickoff, half-time, full-time, lineups**,
  plus custom notification sounds. **Entenser applicability:** when the alerts gate opens (two shadow
  matchweeks, quiet cycle, ≥50 reviewed, owner approval per the claim matrix), this taxonomy is a
  proven default. Entenser's equivalents are not match events but *probability events* — threshold
  crossings, material change, next-match stakes — which `product-strategy` §2 item 8 already
  identifies. Adopt the *granularity model* (per-club, per-event-type, individually toggleable),
  not the event list.
- **Home-screen widgets** and a personalized "For you" news feed with a newsletter subscribe
  *(Verified)*. Off-site return surfaces. Entenser has a PWA and an RSS feed but no widget story.

### ACQ findings

- Team pages are fully public, deep, and interlinked across eight tabs — no registration wall
  anywhere in the browsing path *(Verified)*. Same philosophy as Entenser's static layer, executed
  with roughly 10× the on-page content.

### ANTI — do not copy

- **"FotMob Predict" is a user guessing game, not a model** *(prior intelligence, §3.7)*. It
  manufactures engagement without any forecasting claim. Entenser could build the same thing
  (`product-strategy` §2 item 7 proposes a season-long prediction game) — but note the difference:
  FotMob can run a guessing game because it makes no accuracy claims. Entenser scoring users
  *against its own model with Brier* is a much stronger and much riskier object, because it invites
  direct public comparison. Attractive, but not before the model's public grading is clean.
- **Ad density in the free tier** is what funds the $1.99 price point. Entenser has chosen a clean
  surface; the trade is that it cannot reach FotMob's price and must justify a higher one.

### Pricing snapshot

| Tier | Monthly | 3-month | Annual | Family annual | Discount vs monthly |
|---|---|---|---|---|---|
| FotMob Standard | $1.99 | $4.99 | $15.99 | $29.99 | 33% |

### Operating cost read

11–50 employees (LinkedIn, prior intelligence). The daily-summary generation and form/next-match
strips are **solo-viable** — they are template slots over data Entenser already holds. The editorial
news feed and video highlights are not.

### Unknowns

- Full notification settings tree not observed (EP-2). Taxonomy above is medium confidence.
- Whether "FotMob Gold Member" ($2.99) is a distinct tier or a legacy SKU is unresolved.

---

## 3. Rotowire — `rotowire.com`

**Reviewed:** 2026-08-01 · **Surfaces walked:** home, `/subscribe/`, terms and conditions,
US App Store listing (Fantasy Football app) · **Blocked by paywall:** yes — **web pricing is behind
account creation** (EP-3). App Store IAP disclosure and the published terms substituted.

**Unique question answered.** Rotowire shows what a mature subscription business does at each of the
seven steps of Entenser's own dress rehearsal — and its most instructive move is a refund mechanic
that quietly claws back the annual discount, which Entenser has not yet decided about and will have
to.

### The seven-step comparison against Entenser's dress rehearsal (`STATUS.md` blocker 6)

| Entenser step | Rotowire, as established | Evidence |
|---|---|---|
| **Sign in** | Account required. `/subscribe/` renders **"Create RotoWire Account"** — **the price is not visible before account creation on the web** | *Observed 2026-08-01* |
| **Start checkout** | Web flow not walked (account wall). In-app: standard Apple IAP sheet | *Observed / Verified* |
| **Pay** | Web: "as low as **$8.91/month billed annually** or **$17.99/month billed monthly**". Entry pricing quoted elsewhere at $6.99/mo. iOS IAPs: **$14.99 / $59.99 / $83.90**. One subscription spans all sports | *Verified, [App Store](https://apps.apple.com/us/app/rotowire-fantasy-football/id6740585331)* |
| **Durable entitlement** | Not observed — no account created | — |
| **Customer portal** | Self-service: "going to your RotoWire Account page and following the relevant instructions" | *Verified, [terms](https://www.rotowire.com/termsandconditions.php)* |
| **Cancel** | Self-service **or** email. Access continues "through the end of your relevant Subscription Period" | *Verified, terms* |
| **Refund** | **60-day window, email-only, pro rata** — see below | *Verified, terms* |

### BILL findings

- **★ The refund is pro-rated at the *monthly* rate, not the rate paid** *(Verified, terms,
  2026-08-01)*. Quoted: refunds are "calculated on a pro rata basis **using the relevant monthly
  subscription rate**, for the time period from the date you purchased the relevant subscription to
  the date you contact our Customer Service."

  *Inference — and this is the mechanic worth understanding:* an annual subscriber who cancels at
  month two is charged the **monthly** price for those two months, not two-twelfths of the annual
  price. At the quoted rates that is $17.99 × 2 = $35.98 consumed against an ~$83.90 payment. **The
  annual discount is conditional on completing the year, and is clawed back on early exit.**

  **Entenser applicability — a decision that must be made before launch.** `G0.7` approves a
  "30-day first-billing-period guarantee" but the repository documents do not state whether an annual
  refund inside that window is *full* or *pro-rated*, or at which rate. Rotowire shows there is a
  real choice here with real revenue consequences. *Recommendation: for a launch built on a trust
  position, take the simple and more generous option — full refund inside 30 days, stated plainly —
  and treat the foregone revenue as marketing spend.* But make it an explicit, documented decision
  rather than something Stripe's default settles by accident. **Ship-before-launch; it belongs in
  the blocker-5 legal copy.**

- **Auto-renewal wording is plain and up-front in the app** *(Verified)*: "Payment will be charged to
  iTunes Account at confirmation of purchase and auto-renews at the same price unless disabled in
  iTunes Account Settings at least 24 hours before the end of the current period." Note **"at the
  same price"** — an explicit promise not to raise the renewal price silently.
  **Entenser applicability:** adopt the "auto-renews at the same price" phrasing. It costs nothing,
  it is true of Stripe's default behaviour with immutable Prices, and it pre-empts the single most
  common subscription complaint. Feed into blocker 5.

- **Terms are clear that access survives cancellation to period end** *(Verified)* — which matches
  Entenser's already-implemented rule ("Scheduled cancellation remains active until
  `current_period_end`", `growth-measurement-contract.md`). Confirms Entenser's implementation is
  the industry norm.

- **Outside the 60-day window, "any subscription fee will be non-refundable"** except where law
  requires *(Verified)*.

- **Annual discount is ~50%** ($8.91 vs $17.99 monthly) *(Verified)* — the second data point, after
  FanGraphs' 56%, showing that **a deep annual discount is the category norm and Entenser's 17% is
  the outlier.** See the synthesis for the combined picture.

### ANTI — do not copy

- **★ Price behind an account wall.** `/subscribe/` asks you to create an account before showing what
  anything costs *(Observed 2026-08-01)*. This is precisely what
  `docs/paid-claim-matrix.md` already forbids for Entenser — "See price at checkout" sits in the
  *remove or replace* column, and the approved truth requires the "Stripe-resolved monthly/annual
  amount, renewal, cancellation, 30-day guarantee, coverage limits, and free boundary visible
  **before checkout**." **Entenser's existing rule is correct and is a genuine competitive
  differentiator. Keep it, and consider saying so.**

- **Email-only refunds.** Requiring a support email to obtain a refund adds friction at exactly the
  moment a customer is already unhappy, and it converts a self-service event into a support ticket
  the operator must handle. Entenser is a one-person operation; every refund that requires a human
  is a real cost. *Recommendation: make the guarantee self-service where Stripe allows it, or at
  minimum publish a single-click support path with a stated response time.*

- **Price fragmentation across surfaces.** $6.99, $8.91, $17.99, $14.99, $59.99, $83.90 appear across
  the web and app surfaces with no single legible ladder *(Verified across sources)*. A customer
  cannot tell what the product costs. Entenser's four immutable Stripe Prices resolving to exactly
  two customer-visible options (monthly, annual) is materially better; the discipline is worth
  protecting as SKUs multiply.

### CONV findings

- **One subscription spans all sports** *(Verified)* — no per-sport upsell. *Inference:* simplifies
  the decision and maximises perceived value, at the cost of not extracting more from a
  single-sport superfan. **Entenser applicability:** direct analogue is per-league or per-club
  pricing. Club Watch already chose the Rotowire shape — one plan, up to ten clubs — which this
  supports as the right call. No change.

### Operating cost read

Large editorial and product operation (multi-sport newsroom, apps per sport). Not a staffing model
Entenser can imitate; included here purely for billing mechanics, which is what it was chosen for.

### Pricing snapshot

| Surface | Monthly | Annual (as monthly) | Observed IAP SKUs | Annual discount |
|---|---|---|---|---|
| Web / app (football) | $17.99 | $8.91 | $14.99 · $59.99 · $83.90 | ~50% |
| Entry offer quoted elsewhere | $6.99 | — | — | — |

App rating **4.8 across 51 ratings** (Fantasy Football app) *(Verified)*.

### Unknowns

- **EP-3:** the web checkout flow, the in-account cancellation screen, and any retention interstitial
  on cancel are all behind account creation and were not observed. The terms describe cancellation as
  self-service but the *number of steps and any save-offer* are unverified. Store review text was
  not available at useful volume for this app (51 ratings total), so the planned complaint-taxonomy
  count could not be produced. **This is the weakest evidence in the report; treat the Rotowire
  cancellation-friction picture as documented-policy-only, not as observed behaviour.**

---

## 4. American Soccer Analysis — `americansocceranalysis.com`

**Reviewed:** 2026-08-01 · **Surfaces walked:** home, explainers index, Patreon landing, g+ citation
trail · **Blocked by paywall:** no

**Unique question answered.** ASA is the cost-realism check, and it delivers two things at once: a
sobering revenue ceiling for the patronage model in this exact sport, and the clearest proof in the
review that **a named metric, not a paywall, is what buys a small operation distribution.**

### CONV findings — the reality anchor

- **★ ASA's Patreon shows 255 members and $372/month** *(Verified,
  [Patreon](https://www.patreon.com/americansocceranalysis), 2026-08-01; single visible tier at
  **$5/month**, "Unlock exclusive posts")*. The July 2026 intelligence report recorded ~246 members
  / ~€376/mo, so this is essentially flat.

  *Inference, and it needs stating plainly:* **$372/month ≈ $4,500/year is what the most credible
  independent US soccer analytics brand — decade-old, podcast, league-cited metric — earns from
  direct patronage.** Entenser's `G0.1` objective is 7,000 active paid at $59.99, i.e. roughly
  **$420,000/year, about 94× ASA's patronage revenue.**

  This does not invalidate the objective. The two models are different: ASA sells *patronage on top of
  a free site with no product gate*, Entenser sells *a product with a defined job and boundary*. The
  point is narrower and important: **the patronage framing that works so well as FanGraphs' copy
  (§1) is not, on this evidence, a revenue engine at Entenser's scale in this sport.** Use patronage
  language to soften the utility pitch; do not build the business on it. The `G0.4` job-to-be-done
  framing remains the right primary sell.

- Single tier, $5/month *(Verified)*. Below Entenser's $5.99. *Inference:* the $5–6 band is where this
  audience's patronage instinct sits; Entenser's monthly price is at the top of it, and its annual
  is well above.

### ACQ / G findings — the named metric

- **★ g+ travels further than the site does** *(Verified via citation trail, 2026-08-01)*. "Goals
  added (g+)" appears on:
  - **the league's own site** — [MLSSoccer.com, "Introducing 'goals added'"](https://www.mlssoccer.com/news/introducing-goals-added-new-soccer-analytics-metric-values-every-touch-ball)
  - **a club's own site** — [Minnesota United, "Beyond the Box: Goals Added (And Subtracted)"](https://www.mnufc.com/news/beyond-the-box-goals-added-and-subtracted)
  - **a foreign-league fan analytics blog** — [Fear The Wall (Borussia Dortmund)](https://www.fearthewall.com/2020/10/23/21526850/westfalenstats-is-goals-added-the-future-of-football-analytics)
  - **academic work** — a Carnegie Mellon SURE showcase poster
  - independent Substack analysis

  A $372/month operation has its metric explained on the official channels of the league it covers.
  **That is the highest-leverage distribution asset in this entire review, and it cost a name and an
  explainer page.**

- **The mechanism is a canonical explainer URL per metric** *(Verified)*. ASA runs a free
  **Explainers** section with one page each for xG, xP, **g+**, g−, and net g+ — including a
  dedicated ["What are Goals Added (g+)?"](https://www.americansocceranalysis.com/what-are-goals-added)
  page. Anyone citing the metric has one obvious thing to link to.

  **Entenser applicability: high, and this is a real gap.** Entenser has proprietary quantities —
  the market-blind probability itself, the shared `global_elo` cross-league strength scale, the race
  "swing score", the movement/mover magnitude — and **not one of them has an ownable name or a
  canonical explainer page.** The About page explains method in insider vocabulary ("market-blind",
  "calibration", "Brier"), which the July intelligence report already flagged as a positioning
  weakness. Naming one number and giving it a permanent, linkable, plainly-written page is cheap,
  solo-viable, breaches no gate, and is the prerequisite for the "quotable-number syndication"
  opportunity that report identified as §6.5.

  *Recommendation:* name **the cross-league strength scale** (`global_elo`), not the probability. It
  is the most distinctive thing Entenser computes — 892 clubs across 50 leagues on one comparable
  scale is genuinely unusual — it is the number most likely to start arguments (and therefore to
  travel), and naming it makes no accuracy claim, so it clears the claim matrix cleanly. **Effort:
  one page plus a naming decision. Gate: none.**

### RET findings

- **Podcast as the return engine for a team with no daily-editorial capacity** *(Verified — Apple
  Podcasts and Spotify)*. The cadence obligation is weekly and conversational rather than daily and
  written. **Entenser applicability:** possible but it is a *person* commitment, not a code
  commitment; score `needs help`. Not recommended before launch.
- **Free interactive apps on subdomains** — Interactive Tables (`app.americansocceranalysis.com`)
  and **Viz Hub** (`viz.americansocceranalysis.com`) *(Verified, both appear free)*. Same
  architecture posture as Entenser: heavy interactive tools kept free, monetization elsewhere.
  Validates `G0.5`.

### ANTI — do not copy

- **Patreon as the billing rail.** It caps you at a patronage relationship, takes a cut, keeps the
  customer relationship off your own system, and — on this evidence — plateaus around $400/month.
  Entenser's Stripe + durable entitlement + own account system is the right architecture and is
  already built.

### Operating cost read

Volunteer/community cadence, podcast, free tools. **Solo-viable overall** — this is the one target
in the review whose whole operating model is within reach. Which is exactly why its revenue number
matters.

### Unknowns

- Patreon tier detail beyond the single visible $5 tier was not enumerated; the landing page shows
  member count and income but not the paid/free split.

---

## 5. Sports Reference — `fbref.com`, `sports-reference.com`, `stathead.com`

**Reviewed:** 2026-08-01 · **Surfaces walked:** FBref Arsenal squad page (measured in-browser),
Stathead pricing, Sports Reference blog, Immaculate Grid coverage · **Blocked by paywall:** no.
*Note: WebFetch is 403-blocked across these domains; observations were made in a real browser
session. No bot-detection was bypassed — the interstitial resolved on its own.*

**Unique question answered.** Sports Reference answers both halves of the monetisation problem at
once: the free reference layer stays completely free and becomes unassailably deep, while the paid
tier sells **the ability to search it** rather than access to it. Separately, it holds the review's
strongest and most surprising repeat-visit proof — one that a solo operator actually built.

### The entity-page measurement — the comparison that should sting

*Observed 2026-08-01, both pages measured with the same DOM script.*

| Metric | Entenser `/leagues/epl/clubs/arsenal/` | FBref `/squads/…/Arsenal-Stats` | Ratio |
|---|---|---|---|
| Word count | **266** | **5,583** | 21× |
| Total links | **26** | **1,238** | 48× |
| Internal links | 26 | **1,123** | 43× |
| Data tables | 1 | 8 | 8× |
| Glossary-annotated headers (`th[aria-label]`) | 0 | **298** | — |
| Follow / account CTA | **present, at page bottom** (corrected) | n/a (no accounts on free layer) | — |

*Inference:* Entenser has 1,446 club pages that are each roughly one-twentieth of a competitor's
entity page. The pages exist and are self-canonical with JSON-LD — the hard structural work is done —
but they are thin, and thinness is why they will lose long-tail search to FBref, Transfermarkt, and
FotMob on every club name. **The cheapest fix is not more pages; it is more on each page**, and
Entenser already computes far more than it renders there (match-by-match history, movement, race
context, ELO trajectory, head-to-head).

### RET findings

- **★ Immaculate Grid: a daily game, built by one person, that lifted the parent site 20–30%**
  *(Verified via [Sports Reference acquisition post](https://www.sports-reference.com/blog/2023/07/sports-reference-acquires-immaculate-grid/)
  and [Front Office Sports](https://frontofficesports.com/new-owner-of-immaculate-grid-baseball-game-eyes-football-other-sports/))*.
  Built by Brian Minter, a software engineer in Atlanta, in his free time; launched April 4; **over
  100,000 daily plays by mid-June**; ~**200,000 users most weekdays**; acquired by Sports Reference
  in July 2023, which reported **20–30% more traffic on Baseball Reference** after the game caught
  on. It later became a TV show.

  This is the review's single strongest repeat-visit data point, and unlike FanGraphs' newsroom it is
  **demonstrably solo-viable — one engineer, spare time.**

  **The honest question my own prompt demanded: what is the football-forecasting equivalent?**
  Immaculate Grid works because baseball offers a huge, familiar player×team trivia substrate.
  Entenser's substrate is probabilities, which is *not* trivia. So a direct port fails. Two candidates
  actually fit:

  1. **★ A daily cross-league "which club is stronger?" duel.** Two clubs from different leagues,
     pick one, the answer is the shared `global_elo`. Entenser holds 892 clubs across 50 leagues on a
     single comparable scale — an unusually large and genuinely arguable substrate. It is an
     argument-starter (the Transfermarkt lesson, §6), it teaches the exact number the named-metric
     recommendation says to brand (§4), it generates endlessly without editorial work, **and it works
     in the offseason**, which nothing else in this report does. *Recommended candidate.*
  2. **A daily calibration guess.** User guesses a club's title/relegation probability, model reveals,
     user is scored with Brier over time. On-brand — it makes calibration *felt* rather than
     explained — but it invites direct public comparison with the model's own record and so should
     not launch before the grading surface is clean. *Hold.*

  Both are `post-freeze` in the strict sense that neither is required for the first transaction, but
  neither breaches `G0.9` (they are not new leagues, modules, tiers, localization, group pricing, or
  betting-led acquisition). *Recommendation: build candidate 1 after the transaction milestone, not
  before.*

### CONV findings

- **★ Stathead sells query power, not data** *(Verified, 2026-08-01)*:

  | Plan | Monthly | Annual | Note |
  |---|---|---|---|
  | Single sport | **$8** | **$80** | annual = "two months free" |
  | All sports | **$16** | **$160** | exactly 2× single |

  Plus **one month free trial**, **student 50% off**, **military 25% off**, cancel anytime. The data
  on FBref/Baseball-Reference stays entirely free; what you buy is the ability to *query* it.

  **Entenser applicability: this is the most directly transferable pricing architecture in the
  review.** Entenser's paid tier is already boundary-compatible — the public current answer is free,
  and continuity/explanation/monitoring is paid. Stathead suggests a further, cleanly claim-safe
  addition: **saved and multi-match scenarios are query power.** `docs/paid-claim-matrix.md` already
  anticipates exactly this — "One current one-match scenario is free; saved or multi-match paths may
  be paid." Stathead is the proof that this boundary sells, and that it does not damage the free
  layer's reach.

- **The subscription also removes ads across the free sites** — "Become a Stathead & surf this site
  ad-free" *(Verified, observed on the FBref page)*. One purchase, two benefits, spanning properties.
  **Entenser applicability: none** (no ads; claim matrix bans the ad-free claim). Recorded as the
  cross-property bundling pattern only.

- **Annual = "two months free" (17%)** *(Verified)*. **This is the same ratio Entenser chose**, and
  it corrects the target-1 reading. Two conventions exist in the category: deep discount (FanGraphs
  56%, Rotowire ~50%) and two-months-free (Stathead 17%, Entenser 17%). See synthesis.

- **A free trial exists here** (one month), where Entenser has deliberately chosen **no trial** plus
  a 30-day guarantee (`G0.7`) *(Verified)*. *Inference:* these are near-equivalent economically; the
  guarantee is better for a trust position because it requires the customer to have actually valued
  the thing before money is at stake, and it produces a cleaner activation signal. No change
  recommended; the decision holds up against the comparison.

### ACQ / G findings

- **298 glossary-annotated table headers on a single page** *(Observed)* — every stat abbreviation
  carries an inline definition. **Entenser applicability: high and cheap.** Entenser's surfaces are
  dense with insider quantities (Brier, ELO, xGD, swing score, `PROJ`) and the July intelligence
  report specifically flagged that its differentiation "is expressed for quants." Inline definitions
  on hover/tap for every abbreviation is a small, contract-compatible change that directly attacks
  that weakness. *Ship-before-launch candidate; low cost.*
- **Cross-entity navigation from a club page** includes men's, **women's (Arsenal WFC)** and **U21**
  sides, plus per-competition splits, wages, and player career details *(Observed)*. The entity graph
  is the product.

### ANTI — do not copy

- **Ad density on the free layer** is what the Stathead ad-free upsell exists to relieve. Entenser's
  clean surface is a deliberate and better choice for a trust product; the cost is that it forgoes
  both the ad revenue and the ad-removal upsell, which is precisely why the paid tier must sell a
  real job.

### Operating cost read

The reference pipeline is a large engineering operation. But the two mechanisms recommended above —
**a daily duel game** and **inline glossary definitions** — are `solo-viable`, and Immaculate Grid is
direct evidence that the game category specifically is within one person's reach.

### Unknowns

- The Stathead free-search allowance for logged-out users was not established (FAQ URL 404s; no
  account created). The *shape* of the boundary is confirmed by the pricing page and blog; the exact
  free quota is not.
- Per-page sponsorship: no sponsorship text was detected on the FBref page sampled. Whether it
  persists on Baseball Reference was not checked.

---

## 6. Transfermarkt — `transfermarkt.com` / `.us` / `.co.in`

**Reviewed:** 2026-08-01 · **Surfaces walked:** community structure page, market-value explainer,
academic literature on the valuation process · **Blocked:** yes — `transfermarkt.com` refused both
the browser pane (300s timeout) and WebFetch; regional domains (`.us`, `.co.in`) served. **The club
page itself was not measured**, so the three-way entity-page comparison is incomplete (EP-4).

**Unique question answered.** Transfermarkt turns a number into a permanent argument, and the
argument — not the number — is the product. It also runs the most sophisticated unpaid-labour ladder
in football data. And it raises the sharpest strategic challenge in this review to Entenser's paid
boundary.

### RET findings — the argument as the retention engine

- **★ The market value is explicitly not an algorithm** *(Verified,
  [Transfermarkt's own explainer](https://www.transfermarkt.co.in/transfermarkt-market-value-explained-how-is-it-determined-/view/news/385100))*.
  Quoted: "Transfermarkt does not use an algorithm but instead relies on the wisdom of the
  community." Values are debated in a **market value analysis forum** in each regional area;
  well-argued posts are "collected and evaluated"; **volunteer moderators curate a consensus that is
  explicitly not an arithmetic mean**. Factors include age, performance, contract length, league
  level, prestige, marketing value, number and reputation of interested clubs, and injury
  susceptibility. Values change **roughly twice per season**, plus intermediary updates.

  *Inference:* the slowness is a feature. A number that moves twice a season, after public argument,
  with a named human arbiter, generates far more return visits per change than a number that updates
  silently every night. Entenser's probabilities refresh every 15 minutes in match windows — vastly
  more current, and vastly less discussed.

- **★ The role ladder converts readers into unpaid staff** *(Verified,
  [community page](https://www.transfermarkt.us/intern/community))*: **User → Expert** (grades player
  performances, evaluates transfer rumours) **→ Data Scout** (maintains database accuracy for an
  assigned league) **→ Moderator** (enforces rules) **→ Superadmin** (actual employees). Over 500
  forums across many languages. There is even a "Friends" forum gated by a **€10 charity admission
  fee** — a paid tier that is explicitly *not* about product access.

  **Entenser applicability — real but narrow.** Entenser must never crowdsource its probabilities;
  that would destroy the market-blind, model-generated integrity that is its entire position. But
  the *Data Scout* rung is directly relevant: Entenser's biggest recurring operational cost is data
  quality across 78 leagues with heterogeneous sources, calendars and formats (risk #4 in the July
  threat table: "execution sprawl — solo operator"). A structured way for a supporter of an
  under-covered club to **report a fixture error, a wrong crest, a missing playoff format** is
  cheap, uses the enthusiasm that already exists, and touches nothing about the model.
  *Post-transaction candidate; low cost; solo-viable if it is a form plus a queue, not a forum.*

- **Localized domains** serve different regional communities and forums *(Verified — `.us`,
  `.co.in`, `.co.uk`, `.de` all resolve with distinct content)*. **`G0.9` freezes localization.**
  Recorded as post-freeze intelligence only, per the routing rules; explicitly **not** proposed.

### The strategic challenge to Entenser's boundary

**★ Transfermarkt gives away, as its primary engagement engine, the thing Club Watch sells.**

Club Watch's job (`G0.4`) is: *"Tell me what changed, why, and what the next match can change."*
Transfermarkt's most-discussed free surface is precisely *what changed and why* — with the "why"
supplied by the community rather than the operator. Academic work exists specifically on
[the debates behind the valuations](https://www.tandfonline.com/doi/full/10.1080/23750472.2025.2557905)
and on
[fans as co-creators of market values](https://www.tandfonline.com/doi/full/10.1080/16138171.2026.2694209),
which is a strong signal of how much engagement that discussion generates.

*This is not an argument that `G0.5` is wrong.* Two things distinguish Entenser's case, and both are
real: Transfermarkt's "why" is opinion, whereas Entenser's is a supported causal account derived from
its own model; and Transfermarkt monetises the resulting attention through heavy advertising, a route
Entenser has deliberately closed. But the comparison does establish a requirement:

> **The free tier must contain enough "what changed" to start the argument, or there is no argument
> to monetise.** A boundary that puts *all* change explanation behind the paywall risks a product
> nobody discusses — and discussion is how a site with no ad budget and no newsroom gets found.

The current boundary appears to satisfy this — public league race history, public movers, and one
complete free sample are all change-shaped — **but the live movers strip is currently broken**
(±100.0 artifacts, see baseline), which means the free change surface is, today, actively
counter-productive. *Another reason the undeployed fixes outrank everything else in this document.*

### ACQ findings

- Entity-page depth and the forum archive together produce enormous indexable surface area. Not
  measured here (EP-4); the FBref measurement in §5 is the usable proxy for what "deep entity page"
  means numerically.

### ANTI — do not copy

- **Ad density.** Widely regarded as heavy; it is what funds a free site of this scale. Entenser's
  clean surface is the deliberate opposite and should stay that way.
- **Crowdsourced numbers.** Structurally incompatible with the market-blind invariant and with
  `docs/paid-claim-matrix.md`. The mechanism to borrow is the *role ladder for data quality*, never
  the *valuation method*.
- **Unverified rumour content as a traffic engine.** Transfermarkt's rumour feed drives volume;
  Entenser's claim matrix requires every published claim to be supportable. Do not chase this.

### Operating cost read

Hundreds of forums, volunteer scouts and moderators, plus employed superadmins and an editorial team.
**Impossible at current staffing** as a whole. The single extractable rung — a structured data-error
report queue — is `solo-viable`.

### Unknowns (EP-4)

- **The club page itself was never loaded**, so word count, link count, section order, and ad density
  are unmeasured for the review's most link-dense competitor. The three-way entity comparison in the
  synthesis therefore runs Entenser vs FBref only.
- Forum volume, active member counts, and moderator headcount are not published.

---

## 7. PFF — `pff.com`

**Reviewed:** 2026-08-01 · **Surfaces walked:** subscribe page, membership landing page, support
FAQ, offers page · **Blocked by paywall:** no (pricing and boundary are fully public)

**Unique question answered.** PFF was on this list to show how one proprietary number gets packaged
into multiple priced products for different audiences. **It answers the opposite of what was
expected: PFF abolished its tiers.** Former PFF Edge and PFF Elite have been folded into a single
PFF+ subscription. That is the most decision-relevant finding of this target.

### CONV findings

- **★ Tier consolidation, not tier proliferation** *(Verified,
  [PFF support FAQ](https://profootballfocussupport.zendesk.com/hc/en-us/articles/360023223833-What-types-of-subscriptions-does-PFF-offer))*.
  Quoted: PFF+ "gives you access to all the articles, data, and tools on our website for both the NFL
  and College. Former subscription types from bygone years (like PFF Edge, PFF Elite) have all been
  folded into PFF+."

  **This is the strongest evidence in the review for `G0.9`'s freeze on a Creator tier.** The market
  leader in selling a proprietary sports grade tried multi-tier packaging and retreated to one plan.
  So did Rotowire (one subscription, all sports) and FanGraphs (five SKUs, two prices, one real
  product). **Three of the four paid targets converge on a single consumer tier.** The scope freeze
  is not merely prudent scope control — it matches what the category learned. *Recommend recording
  this in the decision record as supporting evidence for `G0.9`, so the Creator tier is not revived
  on instinct later.*

- **Pricing and the sale mechanic** *(Verified, [subscribe page](https://www.pff.com/subscribe), 2026-08-01)*:

  | | List | On sale |
  |---|---|---|
  | Monthly | **$24.99** | **$9.99** |
  | Annual | **$119.99** ($10.00/mo equivalent) | **$79.99** (33% off) |

  Live banner: **"EARLY BIRD SALE — SAVE 33% THROUGH AUG 17."** Annual is presented second and framed
  as the promotional option; list annual is ~60% off list monthly. **ID.me verification gives 50% off
  to military, first responders and students.**

  Two notes for Entenser. First, **$79.99/yr is exactly Entenser's approved *standard* annual price**
  — a useful anchor showing that number is not unreasonable for a serious analytics product, even
  though it is 5× FotMob. Second, **the dated pre-season sale is structurally identical to what
  Entenser has already approved** — a launch price ($5.99/$59.99) below a standard price
  ($7.99/$79.99) — but PFF frames it as an *expiring offer with a deadline* while Entenser currently
  frames it as nothing at all. **Adding an explicit, honest "launch pricing through <date>" frame
  costs nothing, breaches no gate, requires no new Stripe object (the four Prices already exist), and
  gives the controlled beta a reason to convert now rather than later.** *Ship-before-launch; needs
  only a copy decision and a date from `G0.2`.*

- **The wall is metered, not hard** *(Verified, [membership LP](https://www.pff.com/lp/membership))*.
  Free tier gets *"limited access"* to the Mock Draft Simulator, player grades, premium stats, and
  in-season fantasy tools, plus all free editorial. Paid gets *"unlimited"* versions of the same
  objects. **The gate is quantity, not existence.**
  **Entenser applicability:** this is Stathead's model again from a different direction, and it maps
  cleanly onto the claim matrix's approved boundary — "One current one-match scenario is free; saved
  or multi-match paths may be paid." Entenser's boundary is already a metered boundary. **Two of
  seven targets independently validate it. No change recommended.**

### G findings — the named metric, again

- **The grade's explanation is free and plainly written** *(Verified)*: "A PFF+ Grade represents a
  player's performance — on a single play, in a whole game, or over an entire season in a single
  number," measuring "how well a player performed their role on each play, independent of the
  outcome." Available without a subscription.

  **★ This is now a three-way convergence.** ASA publishes a free canonical explainer for g+; PFF
  publishes a free plain-language definition of the PFF Grade; Sports Reference annotates 298 table
  headers inline on a single page. **Every target that owns a proprietary quantity gives its
  explanation away for free and puts it somewhere permanent and linkable. Entenser explains its
  quantities in insider vocabulary on an About page and has named none of them.** See the
  named-metric recommendation in the synthesis — this is the most repeated pattern in the review.

### ANTI — do not copy

- **★ "Unlock your edge. Get PFF+ today."** *(Verified — the headline pitch, repeated on the
  subscribe page.)* Edge framing plus "up-to-date betting models and picks" as a headline benefit.
  **This is precisely and explicitly what `docs/paid-claim-matrix.md` forbids** — "Do not use
  betting-pick, profit, staking, or affiliate positioning" — and what the July intelligence report
  ranked as threat #8. PFF can run it because it sells to a betting and fantasy audience; Entenser
  has made bettors secondary and non-public (`G0.3`) and its own published backtest shows negative
  flat-stake ROI on the highlighted high-edge sample. **Sort the entire PFF packaging playbook into
  "craft, portable" (metering, tier consolidation, dated sale, student/military discounts) and
  "audience-dependent, reject" (edge framing, picks, betting models). Do not let the first category
  smuggle in the second.**
- **A 60% list-price gap between monthly and annual** paired with a near-permanent sale means the
  list price is largely fictional. That is a trust cost Entenser cannot afford.

### RET findings

- Free editorial across NFL, NCAA, fantasy and betting feeds the metered wall *(Verified)*. Newsroom
  model; **impossible at current staffing**.

### Pricing snapshot

| Tier | Monthly (list) | Annual (list) | Monthly (sale) | Annual (sale) | Discounts |
|---|---|---|---|---|---|
| **PFF+** (only consumer tier) | $24.99 | $119.99 | $9.99 | $79.99 | 50% military / first responder / student via ID.me |

### Operating cost read

Large grading operation plus newsroom. **Impossible at current staffing.** The portable items are
pricing-and-packaging craft, which cost nothing to adopt.

### Unknowns

- Whether the "Early Bird Sale" is genuinely time-boxed or effectively permanent was not established
  across archives (Wayback unavailable to WebFetch this session). *The near-permanent-sale reading is
  labeled Inference.*

---

# Cross-site synthesis

## Table 1 — Pricing and packaging matrix

All *Verified* on 2026-08-01 unless noted.

| Target | Consumer tiers | Monthly | Annual | Annual discount | Trial | Other SKUs | Discounts |
|---|---|---|---|---|---|---|---|
| **FanGraphs** | 1 real (5 SKUs) | $15 | $80 | **56%** | none seen | $200 / 3 years | — |
| **FotMob** | 1 | $1.99 | **$15.99** | 33% | none seen | 3-month $4.99; Family $2.99/mo, $29.99/yr; ad removal $2.99 | — |
| **Rotowire** | 1 (all sports) | $17.99 | ~$8.91/mo equiv. | **~50%** | not established | IAPs $14.99 / $59.99 / $83.90 | — |
| **ASA** | 1 (Patreon) | $5 | — | — | — | — | — |
| **Stathead** | 2 (1 sport / all) | $8 / $16 | **$80 / $160** | **17%** ("2 months free") | **1 month** | — | student 50%, military 25% |
| **Transfermarkt** | none (ad-funded) | — | — | — | — | €10 charity forum | — |
| **PFF** | **1** (consolidated) | $24.99 list / $9.99 sale | $119.99 list / **$79.99 sale** | **60%** list | none seen | — | 50% military / first responder / student |
| **→ Entenser (planned)** | **1** | **$5.99** launch / $7.99 std | **$59.99** launch / $79.99 std | **17%** | **none** (30-day guarantee) | — | none |

**Readings.**
- **Entenser's price sits in a defensible band**, not an aberrant one: 3.75× FotMob, 0.75× FanGraphs
  and Stathead, and its *standard* annual ($79.99) is exactly PFF's sale annual.
- **The annual discount splits into two conventions**: deep (FanGraphs 56%, PFF 60%, Rotowire ~50%)
  and two-months-free (Stathead 17%, Entenser 17%). Entenser is not an outlier — it has picked the
  conservative convention. The open question is whether a *seasonal* product should use the deep
  convention as churn defence, since an annual subscriber cannot cancel during a five-week offseason.
  `G0.6`-locked; post-freeze.
- **Three of four paid targets run exactly one consumer tier**, and PFF got there by *abolishing* two.

## Table 2 — Free/paid boundary spectrum

Ordered from most generous free tier to most gated.

| | Target | Boundary |
|---|---|---|
| 1 | **Transfermarkt** | Everything free; ad-funded; no consumer subscription at all |
| 2 | **FBref / Sports Reference** | All data free forever; pay only to *query* it (Stathead) and to remove ads |
| 3 | **FanGraphs** | Forecasts, odds pages, graphs and articles free; pay for convenience, exports, comfort, patronage |
| 4 | **ASA** | Everything free; pay for exclusive posts / patronage |
| 5 | **→ Entenser** | **Current answer + one-match scenario + league history free; one club + one complete sample on registration; continuity, explanation, stakes, multi-club paid** |
| 6 | **FotMob** | Nearly all data free; pay to remove ads and unlock some advanced stats |
| 7 | **PFF** | Metered — "limited" vs "unlimited" access to the same objects |
| 8 | **Rotowire** | Freemium, but **price itself is behind account creation** |

*Verdict:* Entenser sits in the middle of a spectrum whose two ends both work, and its specific shape
— **metered rather than binary** — is independently validated by the two nearest analogues on either
side (Stathead sells query power; PFF sells unlimited versions of free-limited objects). **This is not
a dead zone. The boundary is sound.**

## Table 3 — Repeat-visit mechanism inventory

Ranked by (visit frequency ÷ operating cost). "Has it?" = Entenser today.

| Mechanism | Used by | Frequency implied | Daily cost | Has it? |
|---|---|---|---|---|
| **Diff / "changes since date" view on an existing page** | FanGraphs | any visit | ~zero | **No** ★ |
| **Auto-generated daily summary on entity pages** | FotMob | daily | ~zero | No (news routing broken) |
| **Next-match + form strip on entity page** | FotMob | match-cycle | ~zero | Partial (no form strip) |
| **Naive-baseline / model-switch toggle** | FanGraphs | occasional, high trust value | ~zero | No |
| **Daily game** | Sports Reference (Immaculate Grid) | **daily** | low once built | No ★ |
| **Named metric that travels off-site** | ASA, PFF | indirect, compounding | one-time | **No** ★ |
| **Follow → event notifications** | FotMob | match-cycle | low (once gated work clears) | Built, not offered |
| **Season-long probability trajectory chart** | FanGraphs | weekly | ~zero | **Yes** (shipped 2026-07-31) |
| **Point-in-time snapshot picker** | FanGraphs | occasional | ~zero | Partial (History view) |
| **Community debate on a changing number** | Transfermarkt | daily | high (moderation) | No — and correctly so |
| **Daily editorial** | FanGraphs, PFF, Rotowire | daily | very high | No — out of reach |
| **Podcast** | ASA | weekly | medium (person cost) | No |

## Table 4 — Billing mechanics comparison

| Step | FanGraphs | FotMob | Rotowire | Stathead | PFF | **Entenser (planned)** |
|---|---|---|---|---|---|---|
| Price visible logged out | ✅ | ✅ (store) | ❌ **account wall** | ✅ | ✅ | ✅ **required by claim matrix** |
| Auto-renew disclosed pre-purchase | ✅ in SKU name | ✅ store terms | ✅ | unknown | unknown | ✅ planned |
| "Renews at the same price" promise | unknown | ✅ | ✅ | unknown | unknown | ⚠️ **adopt this** |
| Self-service cancel | unknown | store-managed | ✅ + email | ✅ "cancel anytime" | unknown | ✅ Stripe portal |
| Access to period end | unknown | store default | ✅ | unknown | unknown | ✅ implemented |
| Refund window | unknown | store policy | **60 days** | unknown | unknown | **30 days** (first period) |
| Refund basis | unknown | store policy | **pro rata at monthly rate** | unknown | unknown | ⚠️ **undecided** |
| Refund self-service | unknown | store | ❌ email only | unknown | unknown | ⚠️ **undecided** |
| Trial | none seen | none seen | not established | **1 month** | none seen | **none, by decision** |

Cells marked "unknown" require an account and were not observed — see escalation packets.

## Table 5 — Credibility-display inventory

| Technique | Who does it | Entenser today |
|---|---|---|
| Free plain-language explainer for the proprietary metric | ASA (g+), PFF (Grade) | ❌ insider vocabulary on About |
| Inline glossary on every abbreviation | Sports Reference (298 on one page) | ❌ |
| Naive baseline selectable in-product ("Coin Flip") | FanGraphs | ❌ (Brier vs baselines exists, but off-page) |
| Public accuracy record | FanGraphs, Entenser | ✅ **Entenser leads here** |
| Publishing misses as well as hits | Entenser | ✅ **unique in the set** |
| Methodology page | all | ✅ |
| Dated point-in-time archive with provenance labels | FanGraphs (quick dates) | ✅ **shipped 2026-07-31, with reconstructed/archived provenance — better than any target reviewed** |
| Transparent, pre-announced price changes | FanGraphs | ❌ not yet a practice |

*Entenser's credibility apparatus is genuinely the strongest in this set on the two hardest
dimensions (publishing misses, provenance-labelled history) and the weakest on the two cheapest
(naming the number, explaining it in plain language).*

## Table 6 — Named-metric audit

| Target | Named metric | Free explainer? | Travels off-site? |
|---|---|---|---|
| ASA | **g+ / goals added** | ✅ canonical page | ✅ MLSSoccer.com, Minnesota United, foreign fan blogs, academia |
| PFF | **PFF Grade** | ✅ free FAQ definition | ✅ broadcast and media standard |
| Transfermarkt | **Market Value** | ✅ explainer article | ✅ universally cited in transfer coverage |
| FanGraphs | WAR / playoff odds | ✅ glossary | ✅ |
| Sports Reference | — (reference, not metric) | ✅ 298 inline definitions | ✅ |
| FotMob | — (licenses xG) | partial | ❌ |
| **Entenser** | **none** | ❌ | ❌ |

**Recommendation: name the cross-league strength scale (`global_elo`).** It is the most distinctive
thing Entenser computes (892 clubs across 50 leagues on one comparable scale), it is inherently
arguable and therefore travels, it is the substrate for the recommended daily game, and **naming it
makes no accuracy claim**, so it clears `docs/paid-claim-matrix.md` cleanly. Pair it with one
canonical, plainly-written explainer URL. *Effort: a naming decision plus one page.*

---

# Ranked, gate-routed backlog

Every item routed through: market-blind invariant → claim-truth → `G0.9` scope freeze → money-path
priority → design contract → solo-viability.

## Ship before 2026-08-17

| # | Idea | Source | Job | Impact | Effort | Evidence |
|---|---|---|---|---|---|---|
| 1 | **Deploy the undeployed movers + news-routing fixes** | *(not competitive — observed in baseline)* | Trust | **Critical.** The free "what changed" surface is the one Transfermarkt shows must work, and it is currently publishing ±100pp artifacts and darts under football labels | Deploy only — code exists | Observed on production 2026-08-01 |
| 2 | **Add a Club Watch path to the 78 league pages, and raise the club-page CTA above the data** | FotMob | ACQ→CONV | **Corrected scope.** Club pages already carry `Track {team} with Club Watch →` with a `track_club` hook, live. League pages carry none and never name the product — and they are the higher-traffic SEO surface ("Premier League predictions"). Club-page CTA also sits below all data, where FotMob's Follow sits above it | Low — template slot | Entenser measured vs FotMob team page |
| 3 | **Decide and publish the annual refund basis** (full vs pro-rata, and at which rate) | Rotowire | BILL | Prevents a launch-day ambiguity on the money path; feeds blocker 5 legal copy | Decision + copy | Rotowire terms, Verified |
| 4 | **Adopt "auto-renews at the same price" wording** | Rotowire, FotMob | BILL | Pre-empts the most common subscription complaint; already true of immutable Stripe Prices | Copy only | Verified |
| 5 | **Frame launch pricing as an explicit dated offer** | PFF | CONV | Gives the controlled beta a reason to convert now; the four Prices already exist | Copy + a date from `G0.2` | PFF "Early Bird Sale", Verified |
| 6 | **One positioning sentence answering "why 4× FotMob?"** | FotMob | CONV | Buyers have already priced the category at $15.99/yr; nothing on the site addresses the gap | Copy only | Two Verified prices |

## After the first production transaction

| # | Idea | Source | Job | Impact | Effort |
|---|---|---|---|---|---|
| 7 | **★ "Changes since <date>" display mode on race and club pages** | FanGraphs | RET | **Highest retention value in the report.** Turns every existing page into a diff with a user-chosen baseline; URL-addressable and shareable; works in preseason. The archive prerequisite shipped 2026-07-31 | Low–medium |
| 8 | **Name `global_elo` and publish one canonical explainer page** | ASA, PFF, Transfermarkt (3-way convergence) | ACQ | The only distribution asset in this review that a $372/month operation was able to build | Low |
| 9 | **Thicken club pages** — match history, movement, race context, ELO trajectory, H2H | Sports Reference | ACQ | 266 words vs 5,583 measured; the data is already computed and simply not rendered there | Medium |
| 10 | **Daily-changing element on club pages** — next match, form strip, since-last-update movement | FotMob | RET | Gives 1,446 pages a reason to be revisited without editorial work | Low–medium |
| 11 | **Naive-baseline toggle ("what a coin flip says")** on race pages | FanGraphs | Trust | Makes the market-blind, graded-in-public position legible on the page where it matters, not in About-page jargon | Low–medium |
| 12 | **Inline glossary definitions on every abbreviation** | Sports Reference | Trust | Attacks the "expressed for quants" weakness directly | Low |
| 13 | **Structured data-error report queue** (form + queue, not a forum) | Transfermarkt (Data Scout rung) | Ops | Converts supporter enthusiasm into data QA across 78 leagues — the top operational risk | Low |
| 14 | **Daily cross-league "which club is stronger?" duel** | Sports Reference (Immaculate Grid) | RET | The only proven *daily* mechanism in the review, and demonstrably solo-buildable. Works in the offseason. Depends on #8 | Medium |

## Post-freeze candidates — `G0.9`, owner decision required. Not proposed as work.

Recorded with evidence so they are ready when the gate opens, per the routing rules.

- **Multi-year prepay SKU** — FanGraphs $200/3yr. Removes two renewal decisions.
- **3-month / seasonal SKU** — FotMob $4.99, Rotowire season shapes. Fits a sport with an offseason.
- **Family or group pricing** — FotMob Family Annual $29.99 (1.9× individual). *Note: Club Watch's
  ten-club allowance may already be a substitute rather than a complement.*
- **Deeper annual discount as seasonal churn defence** — FanGraphs 56%, PFF 60%, Rotowire ~50%.
- **Student / military discounts** — Stathead (50%/25%), PFF (50% via ID.me).
- **Localization** — Transfermarkt regional domains. Frozen; recorded only.
- **Creator tier** — **recommend permanent abandonment, not deferral.** PFF folded Edge and Elite
  into one plan; Rotowire runs one; FanGraphs runs one real product. Three of four converge.

## Rejected at a gate

| Idea | Source | Gate |
|---|---|---|
| "Unlock your edge" / picks / betting models | PFF | **Claim matrix** — betting-pick and profit positioning banned; `G0.3` |
| Ad-free as a paid benefit | FanGraphs, Stathead, FotMob | **Claim matrix** — listed in *remove or replace*; no ads exist |
| Crowdsourced or community-set numbers | Transfermarkt | **Market-blind invariant** + claim matrix |
| Unverified rumour feed as traffic engine | Transfermarkt | **Claim matrix** — every claim must be supportable |
| Price behind an account wall | Rotowire | **Claim matrix** — price must be visible before checkout |
| Patreon as billing rail | ASA | Architecture already better; caps at ~$400/mo on this evidence |
| Daily editorial cadence | FanGraphs, PFF, Rotowire | **Solo-viability** — impossible at current staffing |
| Season-long user-vs-model prediction game | FotMob Predict / `product-strategy` §2.7 | **Hold** — scoring users against the model invites public comparison the grading surface is not ready for. Revisit after #1 and #11 |

---

# Escalation packets — batched for one owner decision

| ID | Target | Behind the wall | Cheapest unlock | If unlocked, capture |
|---|---|---|---|---|
| **EP-1** | FanGraphs | Member surfaces: one-click exports, mailbag, Walk-Off, historical/platoon projections; whether Changes mode is member-gated | $15 one month | Whether the diff view is free or paid; export UX; the member-only retention emails |
| **EP-2** | FotMob | Full notification settings tree and first-run onboarding defaults | Free app install (no account needed) — **but installing is an owner action, not mine** | Every toggle, every granularity level, defaults on install; the match-day notification sequence end to end |
| **EP-3** | Rotowire | Web checkout screens, in-account cancel flow, any save-offer interstitial | $17.99 one month | Click count from logged-in home to cancel; retention offers presented; refund request UX |
| **EP-4** | Transfermarkt | Club page itself (site refused both fetch paths) | none needed — retry from a normal browser session | Word/link count for the three-way entity comparison; section order; ad density |

**Recommendation:** EP-2 is free and the highest value — it is the notification taxonomy Entenser
will need when the alerts gate opens. EP-4 costs nothing but a retry. EP-1 and EP-3 are ~$33 combined
and are the only way to close the billing-mechanics table; worth it only if Entenser wants observed
rather than documented cancellation behaviour before writing its own.

---

# Coverage statement

**Exercised:** FanGraphs (home, blogs, membership product page, playoff odds Default *and* Changes
modes driven in-browser, odds graphs, price-history via company blog posts); FotMob (web team page,
news hub, full US App Store IAP listing); Rotowire (home, `/subscribe/`, full terms and conditions,
App Store IAP listing and auto-renew language); ASA (home, explainers, Patreon landing with live
member/income figures, g+ citation trail); Sports Reference (FBref club page **measured in-browser**
with the same script used on Entenser, Stathead pricing, Immaculate Grid acquisition record);
Transfermarkt (community structure, market-value explainer, academic literature); PFF (subscribe
page, membership LP, support FAQ).

**Not reached, and what the report therefore cannot claim:**
- **No account was created anywhere**, so every member-only surface is unobserved. All "unknown"
  cells in Table 4 are genuinely unknown, not inferred.
- **The Transfermarkt club page never loaded** (EP-4). The entity-depth comparison is
  Entenser-vs-FBref only; Transfermarkt's link density is asserted nowhere in this report.
- **Rotowire's cancellation friction is documented-policy-only.** Its terms describe self-service
  cancellation; the actual step count and any save-offer are unverified, and the app has only 51
  ratings, so the planned complaint-taxonomy count could not be produced. **The common assumption
  that Rotowire is hostile to cancel is neither confirmed nor refuted here** — its published 60-day
  pro-rata refund is more generous than expected.
- **Wayback was unavailable to WebFetch this session**, so price-history is complete only for
  FanGraphs (recovered from its own announcement posts) and absent for the rest.
- **FotMob's notification tree is medium-confidence secondary sourcing** (EP-2), not observed.

---

# Recommendations and executable prompts

Each prompt below is self-contained: hand it to a fresh session without this report. They are ordered
so that earlier ones unblock later ones. Every prompt states its gate status; none of them breach
`G0.9`, the market-blind invariant, or `docs/paid-claim-matrix.md`.

## First: what is already right — protect these

A competitor review that only lists gaps invites damage. These are decisions the evidence
**validates**, and no prompt below may weaken them:

| Doing right | Evidence |
|---|---|
| **Metered free/paid boundary** (`G0.5`) | Independently converged on by Stathead and PFF from opposite directions |
| **Price visible before checkout** | Claim matrix requires it; Rotowire violates it and is worse for it |
| **One consumer tier** | PFF folded Edge + Elite into one; Rotowire one; FanGraphs one product / five labels |
| **No trial + 30-day guarantee** (`G0.7`) | Cleaner activation signal than Stathead's free month; customer must have valued it before money moves |
| **Publishing misses alongside hits** | Unique in the seven-target set. Do not soften this to look better |
| **Provenance-labelled point-in-time history** | Better than any target reviewed, FanGraphs included |
| **Market-blind invariant; no betting framing** | The one position no odds-fed competitor can copy. PFF's "Unlock your edge" is what not to become |
| **Stripe + own durable entitlement** | ASA's Patreon rail plateaus at ~$372/mo and hides the customer |
| **Club-page `track_club` CTA + GA4 hook** | Already built and live — see Correction 1 |
| **Clean, ad-free surface** | The cost is real (no ad revenue, no ad-removal upsell) but it is what makes the trust claim legible |

## Risk register — ranked by what could actually go wrong before 2026-08-17

| # | Risk | Severity | Evidence |
|---|---|---|---|
| **R1** | **Release logjam.** 194 uncommitted files spanning four unrelated workstreams (movers suppression, UEFA coefficient refit, Club Watch teaser rewrite, home/ladder/palette presentation), plus ~170 regenerated data payloads — 14 days before code freeze. There is no way to ship the movers fix without shipping a model refit | **High** | `git status`; `STATUS.md` 🟡 rows |
| **R2** | **Live trust defects on the claim-bearing surface.** ±100.0 movers and darts/cricket under football labels, on the home page, while the whole strategy rests on public credibility | **High** | Observed 2026-08-01 |
| **R3** | **Beta opens into the offseason.** 2026-08-17 is four days before the first EPL fixture (2026-08-21). The highest-search-volume leagues will show preseason priors — 0 pts, 0 matches, nothing moving — for the beta's first days | **Medium-High** | Observed: EPL page reads `PRE-SEASON` |
| **R4** | **Money-path ambiguity.** The annual refund basis (full vs pro-rata, at which rate) is undecided and unwritten | **Medium-High** | `G0.7` vs Rotowire's clawback mechanic |
| **R5** | **Measurement access unconfirmed.** GA4 tag `G-GVSLY1KBHQ` is live and firing, but owner access and exports are still an open owner action — so improvements may be unmeasurable | **Medium** | Observed tag live; `STATUS.md` owner action 6 |
| **R6** | **Thin acquisition pages.** 266 words vs 5,583; league pages never name the paid product | **Medium** | Measured 2026-08-01 |

---

## P1 — Untangle and ship the pending release *(gate: ship before 2026-08-17; blocks P2–P8)*

> **Prompt.**
> The Entenser working tree has ~194 uncommitted files spanning four unrelated workstreams, and
> production is missing several completed fixes. Code freeze is 2026-08-15. Your job is to get the
> repository into a state where each workstream can be shipped or held **independently**, then ship
> the trust fixes first.
>
> Do not write new features. This is release hygiene.
>
> 1. Run `git status` and classify every changed path into exactly one workstream. The four known
>    ones are: (a) movers saturation suppression — `scripts/build_movers.py`,
>    `tests/test_build_movers.py`; (b) UEFA coefficient refit — `data_pipeline/coefficients.py`,
>    `scripts/eval/league_bridge.py`, `experiments/league_offsets.json`,
>    `tests/test_uefa_prior_floor.py`; (c) Club Watch teaser rewrite — `webapp/intelligence.js`,
>    `tests/test_club_watch_lock.py`; (d) home/ladder/palette presentation — `scripts/build_home.py`,
>    `webapp/index.html`, `webapp/intelligence.css`, `tests/test_build_home_fixtures.py`. Report
>    anything that does not fit, and do not guess.
> 2. Treat `webapp/data/*.js` and `data/*.parquet` as **regenerable build output**, not source.
>    Confirm this by regenerating and diffing rather than by assumption. If any payload cannot be
>    reproduced from committed source, that is a finding — stop and report it.
> 3. Commit each workstream as its own commit, smallest-risk first, with the full test suite green
>    between commits. Expected baseline is 1,729 tests passing with 14 intentional skips; if the
>    count differs, reconcile before continuing.
> 4. Ship workstream (a) **first and alone**, then verify on production that Biggest Movers no longer
>    renders any ±100.0 entry.
> 5. **Do not ship the UEFA refit (b) in the same deployment as anything else.** It changes published
>    club rankings; it needs its own deploy and its own verification.
>
> **Acceptance:** four independent commits; suite green at each; production movers strip free of
> saturation artifacts; `docs/STATUS.md` production table updated to match what is actually live.
> **Guardrails:** never hand-edit generated payloads — fix the generator and rebuild. Do not push
> without asking. Another session may be active in this repo: check `git log` and running processes
> before committing.

## P2 — Close the news mis-routing defect *(gate: ship before 2026-08-17)*

> **Prompt.**
> `https://entenser.com` is publishing non-football stories under football league labels on the home
> page: darts ("Price to Littler…") tagged `EFL League One`, cricket ("SunRisers edge Brave…") tagged
> `Premier League`, and rugby league tagged `Ligue 1`. Observed 2026-08-01.
>
> The routing code in `scripts/build_news.py` already contains both a `NON_FOOTBALL_SIGNAL` /
> `FOOTBALL_SIGNAL` rejection and Unicode word-boundary matching (`route_item()`, ~line 153), and
> that file is committed at HEAD. So **first establish which of these is true** before changing
> anything:
>
> - the deployed news payloads simply predate the fix, and a rebuild clears it; or
> - the fix has a real gap — most likely `_league_keywords()` admitting a club name that also occurs
>   in other sports, since it accepts any club name ≥5 characters or containing a space.
>
> Reproduce by running the router over the exact offending headlines and printing which keyword
> matched which league. Report the matched keyword before proposing a fix.
>
> If it is a gap, fix it at the routing layer — do not add a per-headline blocklist. Add a regression
> test using these three real headlines. If it is staleness, rebuild, redeploy, and confirm.
>
> **Acceptance:** the three headlines route to no league; a regression test covers them; production
> home page shows no non-football item under a football label.
> **Guardrail:** the fix must not suppress legitimate football stories — verify the routed item count
> per league before and after and report both.

## P3 — Confirm the funnel is actually measurable *(gate: ship before 2026-08-17)*

> **Prompt.**
> Entenser's GA4 tag `G-GVSLY1KBHQ` is live on production and `gtag` is defined (verified
> 2026-08-01), and club pages fire `gtag('event','track_club', …)` from `#clubWatchCTA`. But
> `docs/STATUS.md` still lists GA4/GSC production inputs as missing, and
> `docs/growth-measurement-contract.md` requires every scorecard row to be marked `known`,
> `estimated`, or `missing`.
>
> Establish, with evidence, whether the canonical funnel is observable end to end:
> `club_page_view → track_club → registration_start → registration_complete → sample_update_view →
> upgrade_view → checkout_start → purchase`.
>
> For each event: confirm it is emitted by real code (cite file and line), and confirm it arrives in
> GA4. Where you cannot confirm arrival without owner console access, say so and produce the exact
> list of checks the owner must run — do not infer arrival from the presence of the call.
>
> **Acceptance:** a table of the eight funnel events × {emitted: yes/no + citation, arriving:
> confirmed/unconfirmed}, plus a short owner checklist for anything needing console access.
> **Guardrail:** do not add new analytics events in this task, and do not send test events to the
> production property.

## P4 — Even out the door into Club Watch *(gate: ship before 2026-08-17)*

> **Prompt.**
> Entenser's 1,446 generated club pages carry a working Club Watch CTA
> (`scripts/build_static_pages.py:943–959` — `Track {team} with Club Watch →`, `#clubWatchCTA`, with
> a `track_club` gtag hook). The 78 generated **league** pages carry none: verified on
> `https://entenser.com/leagues/epl/`, the only call to action is "Open the interactive Premier
> League dashboard →" and the phrase "Club Watch" does not appear at all. League pages are the
> higher-volume search surface ("premier league predictions").
>
> Two changes in `scripts/build_static_pages.py`:
>
> 1. In `league_page()` (~line 520), add a Club Watch path consistent with the club-page treatment.
>    Because a league page has no single club, the honest CTA is club **selection**, not club
>    tracking — e.g. a short row of the league's top-movement or top-of-table clubs each linking to
>    that club's existing `?league=intel&intelLeague=…&team=…&track=1` intent. Reuse
>    `_club_href()` / the existing `watch_query` construction rather than inventing a second URL
>    shape. Emit the same `track_club` gtag hook the club page uses.
> 2. In `club_page()` (~line 943), the CTA currently sits after every table and the methodology note.
>    Move or duplicate it so a Club Watch path is reachable **above the fold** without scrolling past
>    the full projection table, matching how FotMob places Follow above the data.
>
> Copy must obey `docs/paid-claim-matrix.md`: current forecasts stay free, no alerts/email promise,
> no "full team pages are paid", no profit or edge language.
>
> **Acceptance:** all 78 league pages contain a Club Watch path; club-page CTA renders above the
> table; the site rebuilds cleanly; sitemap and page counts unchanged (78 league, 1,446 club); no new
> console errors; verify at 375px and 1280px.
> **Guardrails:** never hand-edit generated HTML — change the generator and rebuild. Do not alter the
> free/paid boundary; this task adds a *path*, not a gate.

## P5 — Ship the "changes since" diff view *(gate: after the first production transaction)*

> **Prompt.**
> Build a diff mode for Entenser's race and club forecast surfaces, modelled on FanGraphs' playoff
> odds page, which renders `?mode=changes&date=<today>&dateDelta=<baseline>` and shows the same
> columns as movement between two dates, with a user-chosen baseline defaulting to seven days back.
>
> Entenser already holds the prerequisite: dated probability snapshots per league, shipped
> 2026-07-31 — `data/race_deltas_history.parquet`, `data/reconstructed_trajectory_history.parquet`,
> `scripts/build_race_deltas.py`, and the archived forecast history behind the current History view.
>
> **The trap you must handle, and the reason this task is not trivial.** That history merges two
> kinds of point: *reconstructed* replays (a model re-run over past data) and *exact archived*
> forecasts (what was actually published). `docs/paid-claim-matrix.md` forbids "calling a
> reconstruction an originally published forecast." A diff whose baseline lands on a reconstructed
> point, or which spans the reconstruction/archive boundary, is **not** a record of what the forecast
> did — it is partly an artifact of re-running the model. Therefore:
>
> - Every diff must carry the provenance of **both** endpoints, using the existing dashed/solid
>   convention already shipped on the history chart.
> - A diff spanning the boundary must say so in words, not only in styling.
> - Prefer archive-to-archive baselines when one is available at or near the requested date; if only
>   a reconstructed point exists, label the result explicitly as a model replay comparison.
>
> Scope: URL-addressable (so it is shareable and indexable), works logged out, no personalization.
> This is deliberately **not** the personalized "since your last visit" digest in
> `docs/product-strategy-2026-07-26.md` §2 — that remains a separate, later, paid-side feature.
> Nothing here may move a currently-free number behind the paywall.
>
> **Acceptance:** a mode toggle on race pages; a URL that reproduces a given diff exactly; correct
> provenance labelling on mixed-provenance diffs, with tests for the boundary case; sensible empty
> state when a league has no movement in the window (common in preseason — an empty diff must read as
> "nothing moved", never as an error or as zeros); verified at 375px and 1280px.
> **Guardrails:** obey `.interface-design/system.md` — no new fonts, no decorative shadows, semantic
> colour only. Do not manufacture movement; if the model did not move, say so.

## P6 — Name the cross-league strength scale *(gate: after the first production transaction)*

> **Prompt.**
> Three of the seven competitors reviewed own a named metric with a free canonical explainer page —
> ASA's g+, PFF's Grade, Transfermarkt's Market Value — and each travels off-site into other
> people's writing. ASA's g+ reaches MLSSoccer.com and Minnesota United's own site on roughly
> $372/month of revenue. **Entenser names none of its quantities**, and its About page explains
> method in insider vocabulary ("market-blind", "calibration", "Brier").
>
> Give Entenser's shared cross-league ELO (`global_elo` — 892 clubs across 50 leagues on one
> comparable scale) a public name and one canonical, permanently-linkable explainer page written for
> a supporter, not a quant.
>
> The page must: define the number in one sentence a non-technical reader understands; say what it
> is **not** (not a power ranking of form, not a betting rating, not derived from bookmaker odds —
> the market-blind invariant is the interesting part and should be stated plainly); show two or three
> concrete cross-league comparisons that make the scale legible; state its known limits, including
> inter-confederation uncertainty, which `STATUS.md` already flags as pending more Club World Cup
> evidence; and link to the public grading record.
>
> Propose three candidate names with reasoning and let the owner choose — **do not pick one
> unilaterally.** Constraints on the name: it must make no accuracy or profit claim (so it clears
> `docs/paid-claim-matrix.md`), must not imply betting utility, and must be pronounceable and
> searchable in English.
>
> **Acceptance:** one new free page at a stable URL, linked from the club page, the rankings page, and
> anywhere `global_elo` is displayed; in the sitemap; JSON-LD where the other static pages carry it;
> owner has chosen the name from your shortlist.
> **Guardrail:** naming is a claim surface. Nothing on the page may assert accuracy the grading record
> does not already support.

## P7 — Money-path copy pack *(gate: ship before 2026-08-17; feeds launch blocker 5)*

> **Prompt.**
> Resolve four commercial-copy decisions for Entenser's Club Watch launch. Three are copy; one is a
> real policy decision that must be made explicitly rather than inherited from a Stripe default.
>
> 1. **The annual refund basis — decide and document.** `G0.7` approves a 30-day first-billing-period
>    guarantee, but nothing states whether an annual refund inside that window is *full* or
>    *pro-rated*, and at which rate. Rotowire's published terms pro-rate at the **monthly** rate,
>    which claws the annual discount back on early exit. Present both options with their revenue and
>    trust consequences, **recommend the simpler and more generous one** (full refund inside 30 days)
>    for a launch built on a trust position, and get an owner decision. Then write it into the refund
>    policy and the pre-checkout summary.
> 2. **Adopt "auto-renews at the same price"** wording, which is true of immutable Stripe Prices and
>    pre-empts the most common subscription complaint. Label auto-renewal in the plan name itself, as
>    FanGraphs does.
> 3. **Frame launch pricing as an explicit dated offer.** The four immutable Prices already encode
>    launch ($5.99/$59.99) below standard ($7.99/$79.99); today nothing tells a customer the launch
>    price expires. This needs the `G0.2` date from the owner. If no date exists, say so and stop —
>    **do not invent one**, and do not imply scarcity that is not real.
> 4. **Answer "why is this more than the football app I already pay for?"** FotMob is $15.99/year;
>    Entenser's annual is $59.99. Write one honest sentence for the pricing surface grounded in the
>    `G0.4` job — continuous monitoring and explanation of a club's season — not in data volume,
>    where Entenser does not win.
>
> **Acceptance:** an owner decision recorded for (1); copy drafted for all four and placed adjacent to
> checkout as the claim matrix requires; every claim traceable to `docs/paid-claim-matrix.md`.
> **Guardrails:** no profit, edge, staking or affiliate language. No alerts or email promise —
> delivery is still shadow-only. Price must remain visible before checkout.

## P8 — Trust legibility on the page where it matters *(gate: after the first production transaction)*

> **Prompt.**
> Entenser's credibility apparatus is the strongest in its competitive set on the hard dimensions
> (it publishes misses; it labels reconstructed vs archived history) and the weakest on the cheap
> ones. Two additions, both drawn from competitors:
>
> 1. **A naive-baseline toggle.** FanGraphs' playoff odds page lets a reader switch the projection
>    model, including a literal **"Coin Flip"** baseline, so they can see what the model adds.
>    Entenser already computes Brier against naive and market baselines but only exposes it on an
>    About page in quant vocabulary. Add an on-page control to a race page that re-renders against a
>    naive baseline. Present it strictly as calibration evidence — **never as an edge claim** — and
>    keep the market-blind invariant intact: showing a market comparison is a separate, existing,
>    opt-in feature and must not be merged into this control.
> 2. **Inline glossary definitions.** FBref annotates 298 table headers on a single club page so
>    every abbreviation carries its definition. Entenser's surfaces are dense with `PROJ`, `GD`,
>    `xGD`, ELO, Brier, swing score. Add accessible inline definitions (title/`aria-label` plus a
>    visible affordance, keyboard-reachable, working on touch) across the static and interactive
>    table headers.
>
> **Acceptance:** the toggle works on at least one race page and is honest in its framing; every
> abbreviation on the static league and club templates carries a definition; keyboard and screen
> reader reachable; verified at 375px and 1280px with no console errors.
> **Guardrails:** obey `.interface-design/system.md`. Do not introduce hero type or new fonts. Do not
> let the baseline toggle imply profitability.

## P9 — The daily habit object *(gate: after the first production transaction; depends on P6)*

> **Prompt.**
> Immaculate Grid was built by one engineer in his spare time, reached 100,000+ daily plays within
> ten weeks, was acquired by Sports Reference in 2023, and lifted Baseball Reference traffic by
> 20–30%. It is the only proven *daily* repeat-visit mechanism in Entenser's competitive set, and the
> only one demonstrably within one person's build capacity.
>
> Build the football-forecasting equivalent: **a daily cross-league duel.** Two clubs from different
> competitions; the reader picks which is stronger; the answer is Entenser's shared cross-league
> strength scale (892 clubs across 50 leagues). One puzzle per day, same for everyone, shareable
> result, no account required to play.
>
> Why this shape and not a trivia grid: Entenser's substrate is probabilities, not player history, so
> a Grid clone has nothing to draw on. A duel uses the most distinctive thing Entenser computes,
> teaches the scale named in P6, generates endlessly without editorial work, is inherently arguable
> (which is what makes such objects travel), and **has content during the offseason** — the state
> most of 78 leagues are in for much of the year, and currently a dead zone for the whole site.
>
> Requirements: deterministic daily selection from a seed so everyone gets the same pairing and it is
> reproducible; difficulty balance so pairings are not trivially obvious; a share format that does
> not spoil the answer; a link from the result into the two clubs' forecast pages; and honest framing
> — this is one model's strength estimate, not a fact, and the result should say so.
>
> **Acceptance:** a stable URL; a new puzzle daily without manual intervention; works logged out and
> on mobile; the result links into club pages; no claim that the scale is authoritative.
> **Guardrails:** must not become a betting or prediction-accuracy game — no scoring users against
> model probabilities in this task (that is a separate, riskier idea deliberately held). No new
> external data dependency. Obey the design contract.

## P3 result — funnel measurability audit *(executed 2026-08-01)*

**Verdict: instrumentation is complete and firing. The open item is owner reporting access, not
code. No analytics work is needed.**

| Funnel event | Emitted | Citation |
|---|---|---|
| `club_page_view` | ✅ static **and** SPA | `build_static_pages.py:863`; `index.html:3888` |
| `track_club` | ✅ static **and** SPA | `build_static_pages.py:957`; `intelligence.js:1648` |
| `registration_start` | ✅ | `intelligence.js:1686` |
| `registration_complete` | ✅ | `intelligence.js:1587` |
| `sample_update_view` | ✅ | `intelligence.js:581` |
| `upgrade_view` | ✅ | `intelligence.js:585` |
| `checkout_start` | ✅ | `intelligence.js:1780` |
| `purchase` | ✅ | `intelligence.js:1626` |

**Live confirmation (Observed, production, 2026-08-01).** Loading
`/leagues/epl/clubs/arsenal/` logged out pushes `club_page_view` to `dataLayer` with the full
dimension set the growth contract specifies:

```
club_id: "v1:1c90591709108353", club_name: "Arsenal", competition_id: "epl",
competition_name: "Premier League", country: "England",
data_state: "pre-season", surface: "club_page"
```

GA4 `G-GVSLY1KBHQ` is loaded and `gtag` is a function. Static pages deliberately load their own
gtag (`build_static_pages.py:90–101`) because "organic search lands here first" — so the 1,446-page
acquisition layer is instrumented independently of the SPA. This corrects an assumption worth
naming: the acquisition surface is *not* a measurement blind spot.

**Owner checklist — the part that cannot be done from the repository:**

1. Confirm ownership/admin of GA4 property `G-GVSLY1KBHQ` and grant reporting access.
2. Confirm the eight events above appear in GA4 **Realtime**, then in **Events** after ~24h.
3. Mark `purchase` as a conversion; confirm currency/value arrive on it.
4. Verify Search Console is linked and the 1,543-URL sitemap is submitted.
5. Confirm internal traffic (Ryan's own devices, CI) is filtered, or `STATUS.md` reconciliation
   rule 1 will never balance against Stripe.

Until steps 1–2 are done, every scorecard row stays **`missing`** under
`docs/growth-measurement-contract.md` — not zero.

## P7 result — money-path copy pack *(drafted 2026-08-01; two owner decisions open)*

### Decision 1 — the annual refund basis **(owner)**

`G0.7` approves a 30-day first-billing-period guarantee. Nothing states what an *annual* refund
inside that window returns. Stripe will not decide this for you; whatever you do the first time
becomes the policy.

| Option | Annual buyer cancels day 20 | Revenue effect | Trust effect |
|---|---|---|---|
| **A — Full refund (recommended)** | Gets $59.99 back | Loses up to $59.99 per refunder | Simplest sentence on the page: "30 days, full refund, no questions." Nothing to dispute |
| B — Pro-rata at the annual rate | Gets ~$56.70 back | Keeps ~$3.29 | Reads fair, but needs a formula on the page |
| C — Pro-rata at the monthly rate (Rotowire's) | Gets ~$44.00 back | Keeps ~$16 | Claws back the annual discount. Defensible, but the buyer discovers it at the worst moment |

**Recommendation: A.** At Entenser's price a full refund is worth ~$60; the sentence it buys is worth
more than that on a launch whose entire positioning is trust. C is what a company optimising a mature
funnel does, and Entenser is not that yet.

### Decision 2 — the launch-price end date **(owner, `G0.2`)**

The four immutable Stripe Prices already encode launch ($5.99/$59.99) below standard
($7.99/$79.99). Nothing currently tells a customer the launch price ends. PFF runs the same structure
as a dated "EARLY BIRD SALE — SAVE 33% THROUGH AUG 17".

**This needs a real date. Per the prompt's own guardrail I have not invented one, and the copy below
leaves it as `<DATE>`.** If you would rather not commit to a date, the honest alternative is to drop
the framing entirely rather than imply a deadline that does not exist.

### Draft copy — ready once the two decisions land

> **Club Watch** · $5.99/month or $59.99/year
> *Launch pricing through `<DATE>`. After that, Club Watch is $7.99/month or $79.99/year. Your price
> never changes while your subscription stays active — it auto-renews at the same price you signed
> up at.*
>
> **Cancel any time** from your billing portal; access runs to the end of the period you paid for.
> **30-day guarantee:** if Club Watch isn't for you, tell us within 30 days of your first payment and
> we'll refund it in full.
>
> **What stays free, always:** current forecasts for all 78 competitions, every league table and race
> page, one-match what-ifs, and the full public record of how the model has scored.

**Plan names carry the renewal term** (FanGraphs' convention): "Club Watch — Monthly (auto-renewing)"
and "Club Watch — Annual (auto-renewing)".

### The "why more than the football app I already pay for?" sentence

FotMob is $15.99/year. Entenser's annual is $59.99 — 3.75×. One honest sentence, grounded in the
`G0.4` job rather than in data volume, where Entenser does not win:

> Your scores app tells you what happened. Club Watch tells you what it changed — which of your
> club's season outcomes moved, why, and what the next match can still swing.

*All copy above is traceable to `docs/paid-claim-matrix.md`: free boundary named, no alerts or email
promise, no profit/edge/picks language, price visible before checkout.*

## P6 result — name shortlist *(owner decision required; not chosen)*

The number: the shared cross-league ELO (`global_elo`), 892 clubs across 50 leagues on one comparable
scale. Constraints applied — makes no accuracy or profit claim, implies no betting utility,
pronounceable and searchable in English.

| Candidate | Reasoning | Risk |
|---|---|---|
| **Club Level** | Plainest possible English; "Arsenal are at club level 1756" needs no explanation; searchable as a phrase | Generic; weak trademark distinctiveness |
| **World Rating** | Says exactly what it is — one rating across every league; travels well in headlines ("Entenser World Rating") | "World" may over-claim coverage at 50 of ~200 leagues |
| **Crossbar** | Football-native, memorable, ownable, no existing metric uses it; "Arsenal's Crossbar is 1756" | Cute; less self-describing, needs the explainer to do more work |

**Not recommended:** anything containing *Power*, *Index*, *Edge*, *Score*, or *Strength Rating* —
the first three are crowded or betting-adjacent, and the claim matrix bans edge positioning.

Ryan chooses; the explainer page in P6 is written against whichever name is picked.

## Sequencing

```
P1 (release hygiene) ──┬── P2 (news defect)
                       ├── P3 (measurement) ──┐
                       └── P4 (league CTA) ───┴── [first production transaction]
                                                        │
                       P7 (money-path copy) ─────────────┤
                                                        │
                                          ┌─────────────┴──────────────┐
                                          P5 (diff view)   P6 (name the scale)
                                          P8 (trust legibility)        │
                                                                  P9 (daily duel)
```

**P1 through P4 and P7 are the pre-launch set.** They are small, they are mostly release and copy
work rather than feature work, and none of them touches the model. P5, P6, P8 and P9 are the growth
set and should wait until one real transaction has completed, per the rule in `STATUS.md` that no
feature outranks that milestone.
