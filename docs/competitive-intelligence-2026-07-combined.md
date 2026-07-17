# Entenser — Competitive Intelligence & Market Analysis (Combined)

**Date:** 2026-07-16 · **Sources:** two independent reports commissioned 2026-07-14, merged 2026-07-16; claims re-verified against the repository during merge. · **Scope:** global consumer football forecasting (emphasis US/UK/Europe), positioning, growth, and monetization strategy; assumed pre-traction.

**How to read this report.** *Verified* = observed on a cited public page or in this repository. *Self-reported* = published by the company about itself, not independently audited. *Observed* = a live-site or search test performed during the reviews. *Inference* = analytical conclusion, labeled. All market-size dollar figures are scenario models — no credible public source measures "consumer football projection products" as a category. Competitive data has a short shelf life; re-check quarterly.

**Action:** the recommendations in §8 are superseded by the execution plan at `docs/superpowers/plans/2026-08-17-public-launch.md` (public launch target: Mon 2026-08-17). This document is the strategic evidence base.

---

## 1. Executive summary

Entenser (entenser.com) enters a market with a genuine structural vacancy: since ABC shut down FiveThirtyEight in 2023, no product has claimed the role of the free, transparent, always-on, multi-league club soccer projections destination. The closest heir, Nate Silver's Silver Bulletin, has left its club model dormant while running only an international model (PELE) for the 2026 World Cup. Entenser's shipped product — 56 leagues, market-blind probabilities, public calibration audits, model-vs-market views — is arguably the most complete answer to that vacancy that currently exists.

The problem is that nobody can find it, and parts of what they'd find overstate themselves. The site is a single-URL, client-rendered PWA with no sitemap, no robots.txt, no per-league pages, shared metadata on every route, and essentially zero search-index presence. Its differentiation ("market-blind," "audited") is expressed in quant jargon a casual fan won't parse. All 56 registry entries are labeled "live" while several are results-only or running on stale seasons. The product is English-only with US date formatting and American odds. Pre-traction, the binding constraint is distribution, not model quality.

Entenser has a credible product wedge but no distribution moat. Its strongest differentiator is not "more accurate picks" — its own EPL trust payload shows the model trailing the sharp market (model Brier 0.5887 vs market 0.5739) and a negative flat-stake ROI on the highlighted high-edge backtest. The differentiator is the combination of broad league-race simulation, a model that deliberately excludes bookmaker odds, and unusually candid public grading against both naive and market benchmarks. "We do not claim to beat the market" is on the live About page; that honesty is strategically valuable because most free prediction sites are betting-led and opaque.

### The five strategic takeaways (both reports independently converged on all five)

1. **Own "independent forecasts that grade themselves."** The FiveThirtyEight-shaped hole is real, verified, and still open — but it is a window, not a permanent condition. Trust/public-audit is the one position no odds-fed or affiliate-funded competitor can copy without self-harm. Do not position as a betting-edge service.
2. **Fix distribution before adding more leagues.** Crawlable per-league pages, unique metadata, sitemap, clean URLs, and recurring editorial outputs outrank a 57th competition. Discoverability is the #1 gap and it is self-inflicted and fixable.
3. **Make "live" a data-quality contract.** Results-only and stale competitions (Canadian PL on 2024 data, K League 1 on 2022–24, Finland and Poland without forward fixtures) must not share a label with fully simulated leagues. Users forgive visible limitations; they do not forgive discovering stale data behind a "live" badge.
4. **Timing is extraordinary and expiring.** The 2026 World Cup produced record US engagement; the post-tournament cohort of new US fans looking for "what do I follow now?" (MLS, NWSL, Liga MX) maps directly onto leagues Entenser covers and incumbents don't. International revenue, however, is plausible only after localization basics.
5. **Sell utility and affiliation, not access to a number — and not yet.** Free forecasts maximize sharing and search acquisition. Every successful analog built distribution first. When monetization comes, it is a low-priced supporter/utility tier (alerts, watchlists, change history, downloads, ad-free — anchors: Football Data Lab £5.99/mo, ASA $5/mo Patreon, Silver Bulletin $10/mo ceiling), not a paywall around probabilities. Betting-affiliate ads are a regulatory and brand trap that would undercut the market-blind position.

---

## 2. Market landscape

### Category definition

Entenser sits at the intersection of four consumer categories: probabilistic league/match forecasting; football statistics and analytics media; live-score/fan utility products; and betting-adjacent prediction tools. The direct forecast market is small and poorly measured; the adjacent attention market is enormous. Users compare Entenser not only with model sites (Opta Analyst, Forebet) but with FotMob, Sofascore, newsletters, social accounts, and search results that answer "who will win the league?" without requiring another destination.

### Audience and demand signals

- **Global top of funnel — verified, medium confidence:** FIFA counts **five billion football fans worldwide** — a broad audience estimate, not an addressable count. [FIFA football landscape](https://publications.fifa.com/en/vision-report-2021/the-football-landscape/)
- **North America — verified:** Nielsen counts **136M North American soccer fans** (+10.9% in five years) ([TV Tech](https://www.tvtechnology.com/insights/analysis/nielsen-north-american-soccer-fans-jump-to-more-than-136-million), [Media Play News](https://www.mediaplaynews.com/nielsen-136-million-u-s-soccer-fans-ready-for-fifa-world-cup-launching-june-11/)); Nielsen separately reports a **US fanbase of 62M+**, fifth largest globally, with 56% of US soccer fans attributing rising interest to the 2026 World Cup ([Nielsen, June 2026](https://www.nielsen.com/insights/2026/world-cup-ad-spend/)).
- **US growth — verified:** 40% of US adults planned to watch WC2026 vs ~30% in prior cycles ([Gallup via Men's Journal](https://www.mensjournal.com/news/world-cup-us-viewership-2026)); 55% of Americans 18–34 planned to watch; the share of Americans actively following soccer rose 8% → 12% since mid-2022 ([YouGov](https://yougov.com/en-us/articles/54777-soccer-is-gaining-ground-in-the-us-ahead-of-the-fifa-world-cup)). Nielsen found Liga MX was the most-watched soccer league on US television in 2025 — a Spanish-language/Mexican-football opportunity inside the US.
- **European engagement — verified, medium confidence:** UEFA reported 229M aggregate attendances across European domestic competitions in 2023/24, and 357M sessions on its club-competition sites/apps in 2024/25 (+23% YoY). ([UEFA landscape report](https://www.uefa.com/news-media/news/0291-1bd655648c06-6b05b0dbe265-1000--new-uefa-landscape-report-shows-popularity-of-european-foo/), [UEFA annual report 2024/25](https://editorial.uefa.com/resources/02a1-1fcb1ef35df9-e69c325893be-1000/20260113_enclosure_03_annual_report_2024-25_en.pdf))
- **Event tailwind — verified but event-driven:** FIFA reported 20B video views and 6.25M cumulative attendance by the final eight of WC2026 ([FIFA, 8 July 2026](https://inside.fifa.com/organisation/media-releases/packed-stadiums-record-digital-reach-world-cup-2026-numbers-unprecedented-scale)). Evidence of exceptional current interest, not a post-tournament run rate. The 2027 Women's World Cup (Brazil) and the MLS/NWSL growth cycle extend the runway.
- **Paying intent — moderate confidence:** NYT internal research reported ~100M US sports-journalism readers, ~24M willing to pay ([A Media Operator](https://www.amediaoperator.com/newsletter/nyt-rationale-for-the-athletic-comes-into-focus/)); The Athletic ~$8/mo anchors the content ceiling.

### TAM / SAM / SOM (scenario model, not a forecast)

| Layer | Estimate / scenario | Revenue implication | Confidence |
|---|---|---|---|
| Audience TAM | 5B global fans; 136M NA; 62M+ US | Not a revenue figure | Medium (broad counts) |
| High-intent global niche | 0.1%–0.3% of fans actively consume quantitative forecasts: **5M–15M people** | If 1%–3% pay $40–$80/yr: $2M–$36M category subscription revenue | Very low; conversion inputs assumed |
| Core SAM (US/UK/EU) | **1M–5M reachable quantitative fans** — directional anchors: Opta Analyst 1M+ MAU (self-reported), Forebet 5M+ visits/mo (self-reported, unverified) | 1%–3% paid at $50–$75 ARPPY: $0.5M–$11.25M | Low; audiences overlap, ≠ buyers |
| Entenser 3-yr SOM | **25k–100k MAU** (observed scale of comparable independents: ClubElo, ASA) | 1%–3% paid at ~$60/yr: **$15k–$180k ARR**; ad layer $2.7k–$96k/yr | Low until traffic/retention/WTP data exist |

Combined 3-year scenario: roughly **$18k–$276k annual consumer revenue** before costs. This is why subscriptions-plus-selective-sponsorship beats an ad-only plan at modest scale. **Closing the gap requires first-party data:** actual users by country, search impressions/CTR, 30/90-day return rates, email conversion, localized price tests — currently unmeasurable because analytics may not be recording (§5).

### Forces shaping the space

- **Behavioral — mobile, continuous, second-screen.** 83% of fans used a smartphone while watching TV (FIFA); incumbents train users to expect instant alerts and personalization. Free expectations are strong — a paid product needs recurrence, personalization, or exclusive interpretation, not a probability table.
- **Regulatory/commercial — betting gravity.** Legal US sports betting pulls "predictions" search intent and ad inventory toward gambling; the top of every prediction SERP is betting-affiliate content (observed: Dimers, SportyTrader, OddsLot). UK ASA treated Oddschecker content as gambling advertising when it encouraged bets; Italy broadly prohibits online gambling advertising; Spain regulates affiliates ([UK ASA/CAP](https://www.asa.org.uk/advice-online/betting-and-gaming-appeal-to-children.html), [Italy AGCOM](https://www.agcom.it/competenze/piattaforme-online/divieto-di-pubblicita-sul-gioco-dazzardo-online-con-vincite-denaro), [Spain DGOJ](https://www.ordenacionjuego.es/en/node/2151)). A pan-European betting-affiliate program is high-friction; it is simultaneously a monetization temptation and a brand-safety trap for a "market-blind" product. EU consent rules add friction to behavioral ad-tech; Entenser's cookie-less Plausible posture is simpler. International subscriptions add currency/VAT/GST surface ([Stripe currencies](https://docs.stripe.com/currencies?locale=en-GB), [Stripe EU tax](https://docs.stripe.com/tax/supported-countries/european-union)). *(Commercial analysis, not legal advice.)*
- **Technological — discovery is being re-intermediated.** AI answer engines and Google AI Overviews absorb "who will win the league?" clicks. Sites win by being the *cited source* (structured data, crawlable per-entity pages, quotable numbers) — Opta's "supercomputer" gets syndicated precisely because it emits quotable, attributable numbers. Google recommends server-side or pre-rendering for app-shell pages; unique titles, canonicals, and crawlable links still matter ([Google JavaScript SEO](https://developers.google.com/search/docs/crawling-indexing/javascript/javascript-seo-basics)). Commodity modeling and generative content also lower the cost of launching a forecast site — the moat shifts to data reliability, historical record, distribution, and a distinctive model policy.
- **Supply side — the transparency vacuum.** FiveThirtyEight shut down in 2023 and SPI went dark ([From the Byline](https://fromthebyline.substack.com/p/fivethirtyeight-is-dead-long-live), [Transfer Science](https://www.transferscience.com/p/how-good-really-was-fivethirtyeights)). Remaining public models are opaque (Opta), B2B (Twenty First Group), partial (ClubElo — ratings, not projections), or low-credibility (tipster sites). Multiple sites still fraudulently claim to republish "live" SPI numbers — concrete evidence of unmet demand for the real thing.

---

## 3. Competitor deep-dive

**Traction caveat:** traffic, funding, and headcount for most players are private; self-reported and third-party figures are labeled. Closing this properly needs Similarweb/Sensor Tower or direct outreach.

### 3.1 Silver Bulletin / PELE (Nate Silver) — adjacent today; the credible future direct competitor

- **Positioning:** personality-led Substack (elections, media, sports, poker); models are subscriber perks, not the product. PELE is an international-teams system covering all 211 FIFA members with a live 100,000-simulation WC2026 forecast; advanced sections paywalled ([PELE launch](https://www.natesilver.net/p/pele-international-football-rankings-soccer-ratings-projections)).
- **Club soccer status — verified:** club model **not running**. Aug 2024: "complicated on the backend," floated selling it ([SBSQ #11b](https://www.natesilver.net/p/sbsq-11b-on-the-future-of-the-newsletter)). April 2026: club projections "much further down the line" ([SBSQ #31](https://www.natesilver.net/p/sbsq-31-trump-is-super-unpopular)); the July PELE page says expansion depends on interest. **Monitor.**
- **Pricing/traction:** $10/mo or $95/yr since mid-2024 (grandfathered $8/$80); subscribe page showed **316,000+ total subscribers** on audit date; paid share undisclosed. Current checkout price not re-verifiable by crawler — could have changed.
- **Strengths:** unmatched brand in trustworthy probabilistic forecasting; huge owned audience; proven subscription engine. **Weaknesses:** soccer peripheral; one-man editorial bottleneck; club coverage absent; thin Substack-native product surface; $95/yr bundle is expensive for a club-forecast-only fan.
- **Threat:** medium today, high if club projections launch — or if the shelved model is *sold* to a worse owner (a sportsbook or major outlet). Entenser should accumulate club-level history and utility before Silver enters, not imitate the personality model.

### 3.2 Opta Analyst / theanalyst.com (Stats Perform) — direct, free incumbent

- **Positioning:** free, polished consumer showcase for Opta's B2B data business; "Opta supercomputer" league/match predictions.
- **Method — verified:** league forecasts combine **betting-market odds** with Opta Power Rankings across thousands of simulations ([methodology example](https://theanalyst.com/articles/serie-a-predictions-2025-26-opta-supercomputer)) — market-*informed*, the direct opposite of Entenser's stance.
- **Traction — self-reported:** 1M+ MAU on Opta Analyst; parent covers 3,900 competitions, ~2,450 employees ([Stats Perform](https://www.statsperform.com/about/)).
- **Strengths:** gold-standard data, enormous press syndication ("supercomputer predicts…" is a distribution machine), brand authority, production quality. **Weaknesses:** methodology opaque; episodic articles rather than a persistent interactive dashboard (gap publicly noted by [From the Byline](https://fromthebyline.substack.com/p/fivethirtyeight-is-dead-long-live)); no calibration accountability.
- **GTM:** SEO editorial + press syndication + social clips — the "quotable number" playbook Entenser can run per league at near-zero marginal cost once per-league pages exist.

### 3.3 Forebet — direct on SEO intent, different league (credibility)

- **Positioning:** "football is mathematics" — 1X2/correct-score/totals/BTTS/live predictions across 850+ competitions since 2009; free, ad-supported (AdSense/AdMob, Criteo per its privacy policy); many languages, time-zone selection, decimal/fractional/American odds.
- **Traction — self-reported:** 5M+ visits/mo (FAQ; unverified); 2,250+ games analyzed weekly; 1M+ Android downloads (verified platform signal); small team.
- **Strengths:** massive coverage, entrenched programmatic-SEO moat (a page for every match, every day — the playbook Entenser's architecture currently forecloses), internationalization, habit-forming utility, mature ad monetization. **Weaknesses:** no transparency or public calibration; cluttered ad-heavy UX; tipster/gambling framing caps mainstream trust; little season-race focus.

### 3.4 Football Data Lab — direct consumer probability + subscription competitor (the price anchor)

- **Positioning — observed:** newer UK product for "serious football fans and punters"; Dixon-Coles/xG methodology, public accuracy claims, EV tools, 30 competitions.
- **Pricing — observed 2026-07-14:** free daily surface; Pro **£5.99/mo or £57.50/yr**, 7-day trial ([footballdatalab.co.uk](https://www.footballdatalab.co.uk/)). The clearest direct price benchmark for a supporter/utility tier.
- **Features:** match probabilities, EV, odds/closing-line-value tracking, backtesting/bankroll tools, player search. Markets a 60.4% "heavy-favourite" hit rate — not full-probability calibration.
- **Strengths:** modern UX, transparent methodological language, concrete paid utilities. **Weaknesses:** 30 competitions, match/betting orientation, English-only, no persistent season-race simulator comparable to Entenser. Traffic/funding/team: not findable.

### 3.5 ClubElo — adjacent hobbyist reference (the survival lesson)

- Long-running free European club Elo ratings with history charts and downloadable data/API; one-person Python-generated static site (Lars Schiefler) ([clubelo.com](http://clubelo.com/), [About](https://clubelo.com/About)).
- **Strengths:** longevity, community respect, durable backlinks from data reuse. **Weaknesses:** ratings ≠ projections (no season sims, no title/relegation odds); dated UX; Europe-only; no calibration reporting. From the Byline: "does not fulfill a true projection use case."
- **Lesson rather than threat:** its open data/API is why it survives — data access creates ecosystem lock-in for tiny teams.

### 3.6 American Soccer Analysis — direct in Entenser's home niche (MLS/NWSL)

- Community-run US soccer analytics (xG tables, projections, podcasts) for MLS/NWSL/USL; free site + ~$5/mo Patreon for data-viz tools ([americansocceranalysis.com](https://www.americansocceranalysis.com/), [Patreon](https://www.patreon.com/americansocceranalysis)).
- **Traction — observed:** Patreon showed ~246 members / ~€376/mo on audit date — a real but small supporter-model proof point.
- **Strengths:** deep credibility in US soccer analytics, community/podcast distribution, the reference for MLS xG. **Weaknesses:** US-only, volunteer cadence, projections secondary to writing.

### 3.7 FotMob / Sofascore — adjacent mass-market apps (the platform threat)

- **FotMob — verified:** 50M+ Google Play downloads, 4.9★, "20M+ fans"; 11–50 employees (LinkedIn). "FotMob Predict" is a user guessing game, **not a model** ([predict.fotmob.com](https://predict.fotmob.com/)).
- **Sofascore — verified/self-reported:** 100M+ downloads, 35M MAU claimed (2025), ~300 employees (2024). Community predictions and third-party market odds, not an auditable probabilistic model.
- **Threat shape:** if either ships a native win-probability model it instantly owns the casual end via installed base — high leverage, but their incentive is engagement + betting-affiliate revenue, not transparency, leaving the trust position open. Feature sets change fast; monitor quarterly.

### 3.8 Twenty First Group — adjacent B2B

Sports-intelligence consultancy whose projections surface occasionally via analysts on social; "lacks the public value of an always-accessible interface" (From the Byline). Not a consumer threat; a reminder that serious modeling talent sits one strategic pivot from consumer.

### 3.9 Dimers / BetQL and betting-prediction sites — adjacent, US-focused

Free "win probability" content funded by sportsbook affiliates; polished but structurally biased toward driving bets. They will dominate any gambling-intent keyword Entenser might chase — the strongest argument for not competing on betting framing while pre-traction.

---

## 4. Comparison matrix

Directional analyst judgments of publicly visible products: **1 = weak/absent, 3 = adequate, 5 = category-leading.** Entenser scores reflect the shipped product, not roadmap. "Transparent trust" = calibration, methodology, visible failure modes.

| Product | Season forecasts | Match probabilities | Coverage breadth | Transparent trust | Model-vs-market view | US-fan coverage (MLS/NWSL/USL/Liga MX/CPL) | Casual-fan UX | Localization | Brand/distribution | Free value | Non-betting fit |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| **Entenser** | **5** | 4 | 4 | **5** | **5 (unique)** | **5 (near-unique combo)** | 3 | **1** | **1** | 5 | 4 |
| Silver Bulletin / PELE | 1 club · 5 intl | 4 intl | 2 | 4 | 1 | 1 | 3 | 2 | 5 | 2 | 5 |
| Opta Analyst | 4 | 4 | 4 | 2 | 1 (odds are an input) | 2 | 4 | 3 | 5 | 5 | 5 |
| Forebet | 1 | 5 | 5 | 2 | 1 | 3 | 3 | 5 | 4 | 5 | 1 |
| Football Data Lab | 1 | 4 | 3 | 4 | 3 | 1 | 4 | 1 | 1 | 4 | 1 |
| ClubElo | 1 | 3 | 2 | 4 | 1 | 1 | 2 | 2 | 2 | 5 | 5 |
| American Soccer Analysis | 2 | 2 | 1 | 4 | 1 | 4 | 3 | 1 | 2 | 4 | 5 |
| FotMob | 1 | 1 model / 3 game | 5 | 1 | 1 | 3 | 5 | 5 | 5 | 5 | 5 |
| Sofascore | 1 | 1 model / 3 community | 5 | 2 | 1 | 3 | 5 | 5 | 5 | 5 | 5 |

**Reading:** Entenser wins or co-wins the product rows — season-race depth, model accountability, the model-vs-market view no one else has, and the US-fan league combination — and is last on the two rows that determine whether anyone ever experiences the product: localization and brand/distribution. That asymmetry is the entire strategic story.

---

## 5. Entenser site assessment (outside-in, re-verified against the repo 2026-07-16)

**Positioning & differentiation.** The live About page calls Entenser a "market-blind football prediction system," never trained on betting odds, and says plainly "We do not claim to beat the market," with Brier scores by model family and known weak spots. The trust apparatus (public calibration, hit/miss filters, model-vs-market status) is genuinely unique in the competitive set — publishing misses is a costly signal competitors funded by odds or affiliates cannot imitate. But the differentiation is expressed for quants: "market-blind," "audited," "calibration" are insider terms; the headline explains the method before the user benefit. The most ownable consumer promise: **"Independent football forecasts across dozens of competitions. No bookmaker odds in the model. Every forecast graded in public."** The brand name "Entenser" has no semantic hook (inference, reinforced by zero brand-search footprint).

**SEO/discoverability — the critical weakness (verified in code):**
- Single hand-written 3,812-line client-rendered SPA (`webapp/index.html`); routing is `?league=<id>` query params. One URL for the entire product: 56 leagues, thousands of matches, zero addressable pages.
- No `robots.txt`, no `sitemap.xml`, no canonical tags, no JSON-LD anywhere. OG/description meta are static homepage values on every route; only `document.title` updates per view.
- Observed: brand search returns nothing related; one indexed Chinese-Super-League URL carried mismatched MLS-oriented metadata. Search Console is needed to measure actual coverage.
- The shell's meta/OG tags are good — for exactly one page.

**Data-status honesty (verified):** all 56 entries in `webapp/leagues.js` carry `status:"live"`, while repo docs confirm Canadian PL is results-only on 2024 data, K League 1 on 2022–24, and Finland/Poland are results-only without forward fixtures; several split-round formats are approximations (disclosed in `outlook.rules` but not in the global count). Treating all 56 as equally live risks the trust position that is the product's core asset.

**International readiness (verified):** English-only; dates hardcoded `en-US` (8 call sites); probabilities shown as "fair American odds" only; no i18n scaffolding. Broad league coverage ≠ a global product.

**Analytics (verified):** Plausible is wired for `entenser.com` with 8 custom events, but the code's own comment says events only record "once entenser.com exists in a Plausible account" — the account has likely never been created. The site is flying blind on whatever traffic it gets.

**Email capture (verified):** the "weekly model movement" signup form saves to localStorage and goes nowhere — no backend, no digest generator.

**Infrastructure (verified, favorable):** GitHub Pages, nightly data refresh via GitHub Actions chained into deploys; PWA with service worker; share-card generator (Playwright) already produces OG images; payload contract validated in CI. The architecture is cheap, fast, and CI-deployable — a great data-product architecture and a poor distribution surface, and the fix (emitting pre-rendered per-league HTML from the same pipeline that writes `webapp/data/*.js`) does not require abandoning it.

---

## 6. Gaps and opportunities

1. **The vacant "SPI heir" position (verified gap).** Fake "538 predictions" sites still farm the dead brand's traffic; the analytics community has publicly catalogued the lack of a replacement. Entenser is the closest fit; it needs URLs, name recognition, and a track-record page to claim it.
2. **Transparent, non-betting season forecasts.** No reviewed competitor combines broad club-season simulations, bookmaker-independent inputs, and a public trust ledger. The clearest position to own; "the only football model that grades itself in public" is a headline no one else can run.
3. **Underserved-league SEO whitespace — with honest data tiers.** "NWSL playoff odds," "USL Championship projections," "Canadian Premier League predictions," "Liga MX probabilities in English," Scandinavian leagues: Entenser models all of these; incumbents don't or barely do. Low-competition keywords, high fit with the post-World Cup US cohort. Condition: label data quality — depth in 20–30 competitions beats nominal coverage of 56 indistinguishable statuses.
4. **Forecast movement as content.** Movers and drift trajectories already exist as data. "Arsenal title chance 34% → 41% this month" timelines create searchable pages, shareable cards, and a future paid-alert feature from existing computation. "Where our model disagrees with the market this weekend" is inherently shareable weekly editorial requiring zero new modeling.
5. **Quotable-number syndication.** Opta manufactures headlines by giving journalists a number and a name. Entenser can run the identical playbook per league at near-zero marginal cost once per-league pages exist to link back to.
6. **Open data / embeds.** FiveThirtyEight's SPI CSVs created a generation of loyal tinkerers; ClubElo survives on its API. Projection CSVs and embeddable race tables buy backlinks, citations, and publisher distribution cheaply. (Review data-licensing terms per source first.)
7. **Local-language long-tail search (post-launch).** "Probabilidades de ganar LaLiga," "Abstiegswahrscheinlichkeit Bundesliga," "probabilità scudetto Serie A" — programmatic, editor-reviewed landing pages are substantial whitespace. Spanish first (Spain + US/LatAm). Forebet proves localization works; its output is betting-led, leaving season-race intent open.
8. **A supporter tier between free sites and $95/yr newsletters.** Test £4.99/€5.99/$5.99 monthly (~2 months free annually) for utility — alerts, watchlists, change history, downloads, ad-free, weekly briefing — without paywalling public forecasts.
9. **Women's soccer runway.** WSL + NWSL coverage now, compounding toward the 2027 Women's World Cup, where the field is even emptier.

---

## 7. Threats and risks (merged, ranked severity × likelihood)

| # | Risk | Severity | Likelihood | Notes |
|---|---|---|---|---|
| 1 | **Invisibility persists** — no scalable discovery loop; product excellence never meets an audience; motivation/investment decays | High | High (status quo) | Entirely self-inflicted and fixable; every month burns the World Cup dividend |
| 2 | **"56 live" data-freshness trust failure** | High | High | Repo docs confirm results-only/stale exceptions behind a uniform live label; contradicts the core trust positioning |
| 3 | **Weak willingness to pay** | High | High | Most alternatives free; zero first-party traffic/retention/checkout data exists |
| 4 | **Execution sprawl (solo operator)** | High | High | 56 leagues, many sources/formats/calendars, daily refresh, CI, modeling, now marketing; recent commit history shows refresh firefighting; automation debt compounds with league count |
| 5 | **SEO channel structurally hostile** | Medium-High | High | Betting affiliates own generic "predictions" terms; AI Overviews absorb simple queries. Mitigate: long-tail league/team terms; be the citable source, not the SERP winner |
| 6 | **Incumbent feature expansion (FotMob/Sofascore native probabilities; Opta persistent dashboard)** | High | Low-Medium | Would own the casual segment overnight via installed base; trust/transparency niche survives but shrinks |
| 7 | **Silver Bulletin enters club soccer (or sells the model)** | High | Low-Medium near term | Capability proven (PELE), audience in place; Apr 2026: "much further down the line." Monitor natesilver.net |
| 8 | **Model positioned as betting edge** | High | Medium | "Fair odds"/edge views pull messaging toward betting although the public backtest is negative — reputational + regulatory exposure. Keep the paper-ledger/edge work internal-facing |
| 9 | **Data-source fragility** | Medium-High | Medium | ESPN endpoints, football-data.co.uk, API-Football free tier: ToS/endpoint changes could break coverage; diversification + caching discipline are the hedges |
| 10 | **International commercial complexity** | Medium-High | High if monetized globally | Currency, VAT/GST, consent, translations, country gambling-ad rules |
| 11 | **Search/AI disintermediation** | Medium | High | Counter: proprietary history, interactive scenarios, alerts, attribution-worthy data |
| 12 | **Monetization damages the product** | Medium | Medium | Dense ads reduce trust/speed; affiliates conflict with neutrality; hard paywall kills sharing and indexing |

---

## 8. Strategic recommendations (superseded by the execution plan)

Both reports' prioritized recommendations were merged into the launch execution plan at `docs/superpowers/plans/2026-08-17-public-launch.md` (workstreams A–I: measurement truth; data-status contract; crawlable pages/SEO; messaging/trust on-ramp; Resend email capture; locale basics; supporter-tier waitlist; distribution content; QA/launch). Consensus priority order preserved there: **measurement + honesty + crawlability first; distribution second; monetization tests third; ads/localization expansion later.** Decision gates adopted from Report 2:

- **Build the paid tier** only if ≥2% of returning users join the waitlist (or ≥1% complete a real checkout at the proposed price).
- **Scale a locale** only if localized pages produce material non-branded impressions and comparable email conversion after a full competition cycle.
- **Add another league** only if current full-forecast leagues meet freshness targets and the candidate has identifiable demand.
- **Introduce ads** only after measuring revenue per thousand sessions against page-speed, return-rate, and trust effects — and exclude gambling categories.

---

## Appendix A: verification status of key claims

| Claim | Status |
|---|---|
| FiveThirtyEight shut down 2023; SPI dark | Verified ([From the Byline](https://fromthebyline.substack.com/p/fivethirtyeight-is-dead-long-live)) |
| Silver Bulletin club model dormant; PELE live; $10/mo/$95/yr; 316k+ subs; club "much further down the line" (Apr 2026) | Verified (natesilver.net; current checkout price not re-verifiable) |
| Opta model uses betting odds + Power Rankings; free; 1M+ MAU | Verified method ([Opta](https://theanalyst.com/articles/serie-a-predictions-2025-26-opta-supercomputer)); MAU self-reported |
| Forebet 5M+ visits/mo | Self-reported/unverified; 1M+ Android downloads verified |
| Football Data Lab Pro £5.99/mo | Observed 2026-07-14 |
| FotMob 50M+ downloads, no native model; Sofascore 100M+ downloads, market odds/community predictions | Verified as of mid-2026 — feature sets change fast |
| 136M NA fans; 62M+ US fanbase; 40% US adults watching WC2026; 8%→12% followers | Verified (Nielsen, Gallup, YouGov — cited in §2) |
| ASA Patreon ~246 members / ~€376/mo | Observed 2026-07-14 |
| entenser.com: SPA/single-URL, no sitemap/robots/canonical/JSON-LD; Plausible account unconfirmed; email capture no-op; all 56 leagues labeled live incl. 4 results-only; en-US dates; American odds only | Verified (codebase + live fetch, re-confirmed 2026-07-16) |
| Entenser EPL: model Brier 0.5887 vs market 0.5739; negative high-edge flat-stake ROI backtest | Verified (live trust payload, 2026-07-14) |
| Competitor funding/headcount (Forebet, FotMob, Sofascore, ASA, Football Data Lab) | Not findable publicly — needs paid data or outreach |

## Appendix B: unknowns and how to close them

| Unknown | Why it matters | How to close |
|---|---|---|
| Entenser traffic, geography, retention | Realistic SOM, language order, ad viability | Plausible account (launch plan A1) + cohort export |
| Search index coverage and query demand | True SEO baseline | Google Search Console (launch plan A2) |
| Email list growth and repeat usage | Best early subscription signal | Resend capture (launch plan E) + 30/90-day cohorts |
| Willingness to pay by country | Prices are only anchors | Supporter-tier waitlist test (launch plan G), segmented by country |
| Data licensing / redistribution rights | Governs downloads, embeds, ads | Source-by-source review before open-data expansion |
| Silver Bulletin club plans; FotMob/Sofascore forecast features; competitor prices | The threats that arrive suddenly | Quarterly competitive monitor (post-launch backlog) |
| Competitor revenue/paid conversion; Football Data Lab traffic/team | Category benchmarks | Paid intelligence services or direct outreach |
