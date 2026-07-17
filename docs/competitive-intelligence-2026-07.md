# Entenser — Competitive Intelligence & Market Analysis

**Date:** 2026-07-14 · **Scope:** Neutral projections positioning, growth & positioning strategy, assumed pre-traction · **Analyst note:** Facts verified by web search are cited; inferences and unverifiable claims are flagged as such. Competitive data has a short shelf life — re-check quarterly.

---

## 1. Executive summary

Entenser (entenser.com) enters a market with a genuine structural vacancy: since ABC shut down FiveThirtyEight in 2023, no product has claimed the role of the free, transparent, always-on, multi-league club soccer projections destination. The closest heir, Nate Silver's Silver Bulletin, has explicitly left its club soccer model dormant ("possibly more work than we could do," Aug 2024) while running only an international model (PELE) for the 2026 World Cup. Entenser's actual product — 56 leagues, market-blind probabilities, public calibration audits, model-vs-market views — is arguably the most complete answer to that vacancy that currently exists.

The problem is that nobody can find it. The site is a single-URL, client-rendered PWA with no sitemap, no robots.txt, no per-league pages, and zero search-index presence even for its own brand name. Its differentiation ("market-blind," "audited") is expressed in quant jargon a casual fan won't parse. Pre-traction, the binding constraint is distribution, not model quality.

**Top strategic takeaways:**

1. **The FiveThirtyEight-shaped hole is real, verified, and still open** — but it is a window, not a permanent condition. Silver Bulletin has the brand, audience (315k+ subscribers), and demonstrated capability (PELE) to close it whenever soccer rises up Nate Silver's priority list.
2. **Discoverability is the #1 gap.** Entenser's architecture makes 56 leagues of daily-refreshed projections invisible to search engines and AI answer engines. Fixing this (per-league static pages, sitemap) is low-effort, high-impact, and should precede any monetization work.
3. **Timing is extraordinary and expiring.** The 2026 World Cup final is in five days in the US; Nielsen counts 136M North American soccer fans (+10.9% in five years) and 40% of US adults planned to watch the tournament. The post-World Cup cohort of new US fans looking for "what do I follow now?" content (MLS, NWSL, Liga MX) maps directly onto leagues Entenser covers and incumbents don't.
4. **Differentiate on trust, not predictions.** "Football predictions" as a search category is owned by betting-affiliate content farms; Opta's model literally ingests betting odds. A market-blind, publicly audited model is the one position no competitor can credibly copy — but it must be translated from quant-speak into fan language.
5. **Defer subscriptions.** Willingness to pay exists in adjacent proof points ($5/mo American Soccer Analysis Patreon, $10/mo Silver Bulletin, ~$8/mo The Athletic), but every successful analog built distribution first. Ads/affiliate monetization carries gambling brand-safety risk that would undercut the "market-blind" trust position.

---

## 2. Market landscape

### Sizing (TAM → SAM → SOM)

| Layer | Estimate | Basis | Confidence |
|---|---|---|---|
| TAM — soccer fans in core geographies | 136M North America alone; UK/EU adds hundreds of millions | Nielsen via [TV Tech](https://www.tvtechnology.com/insights/analysis/nielsen-north-american-soccer-fans-jump-to-more-than-136-million) / [Media Play News](https://www.mediaplaynews.com/nielsen-136-million-u-s-soccer-fans-ready-for-fifa-world-cup-launching-june-11/) | High for NA figure; EU figure not independently sized here |
| TAM — paying intent for sports content (US) | 100M US sports-journalism readers; ~24M willing to pay | NYT internal research reported by [A Media Operator](https://www.amediaoperator.com/newsletter/nyt-rationale-for-the-athletic-comes-into-focus/) | Moderate (single source, internal research, all sports not just soccer) |
| SAM — stats-inclined soccer fans who seek out probabilities | Order of single-digit millions of monthly actives globally | Proxy: Forebet claims 5M+ visits/mo (self-reported/third-party blog — **unverified**); FiveThirtyEight SPI's mainstream cultural footprint pre-2023; Silver Bulletin's 315k+ (all-topic) subscriber base | Low — no authoritative sizing exists for "model-consuming fans"; closing this gap needs paid traffic-intelligence data (Similarweb/Sensor Tower) |
| SOM — realistic 12–24 month target for a pre-traction indie site | ~10k–100k monthly visits | Inference from the observed scale of comparable independents (ClubElo, American Soccer Analysis) | Low (inference only) |

### Forces shaping the space

- **Behavioral — the World Cup effect (now).** 40% of US adults planned to watch the 2026 tournament vs ~30% in prior cycles ([Men's Journal/Gallup](https://www.mensjournal.com/news/world-cup-us-viewership-2026)); 55% of Americans 18–34 planned to watch ([YouGov](https://yougov.com/en-us/articles/54777-soccer-is-gaining-ground-in-the-us-ahead-of-the-fifa-world-cup)); the share of Americans actively following soccer rose from 8% to 12% since mid-2022 (YouGov). Young-skewing growth is exactly the demographic that consumes probabilistic/analytics content. The 2027 Women's World Cup (Brazil) and the ongoing MLS/NWSL growth cycle extend the runway.
- **Regulatory/commercial — betting gravity.** Legal US sports betting keeps pulling "predictions" search intent and ad inventory toward gambling. The top of every prediction-related SERP is betting-affiliate content (Dimers, SportyTrader, OddsLot — observed directly in searches for this report). This is simultaneously a monetization temptation and a brand-safety trap for a "market-blind" product.
- **Technological — discovery is being re-intermediated.** AI answer engines and Google AI Overviews increasingly answer "who will win the league?" directly, compressing clicks. Sites win by being the *cited source* (structured data, crawlable per-entity pages, quotable numbers) — the "Opta supercomputer" gets syndicated by mainstream outlets (e.g., GiveMeSport) precisely because it emits quotable, attributable numbers.
- **Supply side — the transparency vacuum.** FiveThirtyEight was shut down by ABC in 2023 and SPI went dark with it ([From the Byline](https://fromthebyline.substack.com/p/fivethirtyeight-is-dead-long-live), [Transfer Science](https://www.transferscience.com/p/how-good-really-was-fivethirtyeights)). Remaining public models are either opaque (Opta), B2B (Twenty First Group), partial (ClubElo — ratings, not projections), or low-credibility (tipster sites). Multiple sites still fraudulently claim to republish "live" SPI numbers — evidence of unmet demand for the real thing.

---

## 3. Competitor deep-dive

**Traction caveat:** traffic, funding, and headcount for most players below are private and not reliably findable from public sources; where a number is self-reported or third-party-estimated I say so. Closing this gap properly requires Similarweb/Sensor Tower data (a Similarweb connector is available but unauthenticated in this session).

### 3.1 Silver Bulletin (Nate Silver) — direct, dormant in-category

- **Positioning:** "Essays and analysis about elections, media, sports, poker" — a personality-led Substack where models are subscriber perks, not the product.
- **Target segment:** data-literate general audience; US-centric.
- **Pricing:** $10/mo or $95/yr as of June 1, 2026 (grandfathered $8/$80 for earlier subscribers) — verified via search of [natesilver.net](https://www.natesilver.net/p/soft-launch-of-paid-subscriptions) coverage. 315,000+ total (free+paid) subscribers per its Substack page; paid count undisclosed.
- **Soccer status:** club soccer model **not running**; in Aug 2024 Silver called it "complicated on the backend" and floated selling it ([SBSQ #11b](https://www.natesilver.net/p/sbsq-11b-on-the-future-of-the-newsletter)). For the 2026 World Cup he launched **PELE**, an international-teams model with a live 100,000-simulation forecast page, advanced sections paywalled ([PELE launch](https://www.natesilver.net/p/pele-international-football-rankings-soccer-ratings-projections)). **Unconfirmed:** whether a club-model relaunch is planned post-World Cup — monitor.
- **Strengths:** unmatched brand in "trustworthy probabilistic forecasting"; huge owned audience; proven subscription engine.
- **Weaknesses:** soccer is peripheral; one-man editorial bottleneck; club coverage absent; interactive product surface is thin (Substack-native).
- **GTM:** newsletter + X virality + press citation.

### 3.2 Opta Analyst / theanalyst.com (Stats Perform) — direct, free incumbent

- **Positioning:** consumer showcase for Opta's B2B data business; "Opta supercomputer" league and match predictions.
- **Pricing:** free (brand marketing for Stats Perform's enterprise data products).
- **Core features:** season simulations (10,000 runs) for major leagues, match predictions, power rankings, stats content ([Opta Analyst](https://theanalyst.com/articles/opta-football-predictions)).
- **Method note (verified):** the model uses **betting market odds** plus Opta Power Rankings as inputs — i.e., it is market-*informed*, the direct opposite of Entenser's market-blind stance.
- **Strengths:** gold-standard data; enormous press syndication ("supercomputer predicts…" headlines are a distribution machine); credibility.
- **Weaknesses:** methodology opaque; no persistent interactive interface or per-team probability explorer (a gap already called out publicly in [From the Byline](https://fromthebyline.substack.com/p/fivethirtyeight-is-dead-long-live)); no calibration accountability; editorial article format rather than a living dashboard.
- **GTM:** SEO + press syndication + social clips.

### 3.3 Forebet — direct on SEO intent, different league (credibility)

- **Positioning:** "Mathematical football predictions" across 850+ leagues since 2009; free, ad-supported.
- **Features:** 1X2 probabilities, over/under, correct score, live in-play tips ([forebet.com](https://www.forebet.com/)).
- **Traction:** third-party blogs claim 5M+ visits/month — **self-reported/unverified**; directionally, it dominates "football predictions" SEO.
- **Strengths:** massive league coverage, entrenched SEO moat, simple habit-forming utility.
- **Weaknesses:** no transparency or public track-record auditing; cluttered ad-heavy UX; tipster/gambling framing limits mainstream trust; no season-race narratives.
- **GTM:** pure programmatic SEO (a page for every match, every day — the exact playbook Entenser's architecture currently forecloses).

### 3.4 ClubElo — direct-adjacent, hobbyist reference

- **Positioning:** long-running free Elo ratings for European clubs with history charts and an API ([clubelo.com](http://clubelo.com/) — still active as of 2026).
- **Strengths:** respected by the analytics community; open data/API generates backlinks and durable relevance.
- **Weaknesses:** ratings ≠ projections (no season simulations, no title/relegation odds); dated UX; Europe-only; no calibration reporting. From the Byline: it "does not fulfill a true projection use case."
- **Lesson rather than threat:** its API is why it survives — data access creates ecosystem lock-in for tiny teams.

### 3.5 American Soccer Analysis — direct in Entenser's home niche (MLS/NWSL)

- **Positioning:** community-run US soccer analytics (xG tables, game projections, podcasts) for MLS/NWSL/USL ([americansocceranalysis.com](https://www.americansocceranalysis.com/)).
- **Pricing:** free site + $5/mo Patreon for data-viz tool access; active 2026 season coverage confirmed.
- **Strengths:** deep credibility in US soccer analytics circles; community and podcast distribution; the reference for MLS xG.
- **Weaknesses:** US-only; volunteer cadence; projections are secondary to writing/tables; no global league product.
- **GTM:** community, podcast, X, word of mouth.

### 3.6 FotMob / Sofascore — adjacent mass-market apps (the platform threat)

- **Positioning:** live-score utilities with tens of millions of users (app-store scale; exact MAU not publicly verified).
- **Prediction status (verified):** FotMob offers a user *prediction game* (FotMob Predict), not a model; Sofascore displays third-party market odds rather than original probabilities ([comparison coverage](https://insideformation.com/blog/best-livescore-apps-2026-comparison)).
- **Threat shape:** if either ships a native win-probability model, they instantly own the casual end of the category via installed base. Their incentive, though, is engagement + betting-affiliate revenue, not transparency — leaving the trust position open.

### 3.7 Twenty First Group — adjacent B2B

- Sports-intelligence consultancy whose projections occasionally surface via analysts on social media; primarily B2B, "lacks the public value of an always-accessible interface" (From the Byline). Not a consumer threat; a reminder that serious modeling talent exists one strategic pivot away from consumer.

### 3.8 Dimers / betting-prediction sites (BetQL et al.) — adjacent, US-focused

- Free "win probability" content funded by sportsbook affiliate deals; polished but structurally biased toward driving bets. They will dominate any gambling-intent keyword Entenser might chase, and their existence is the strongest argument for Entenser *not* competing on betting framing while pre-traction.

---

## 4. Comparison matrix

Dimensions chosen for what a stats-curious soccer fan actually evaluates. Scale: **Strong / Adequate / Weak / Absent**. Entenser scores reflect the shipped product, not roadmap.

| Dimension (why it matters) | **Entenser** | Silver Bulletin | Opta Analyst | Forebet | ClubElo | Am. Soccer Analysis | FotMob/Sofascore |
|---|---|---|---|---|---|---|---|
| League coverage breadth | **Strong** (56 leagues, 6 confederations) | Weak (international only, club dormant) | Adequate (majors) | Strong (850+ claimed) | Weak (Europe) | Weak (US only) | Strong (scores, not projections) |
| Season race projections (title/relegation/playoff odds) | **Strong** | Absent (club) | Adequate (article-based) | Weak | Absent | Adequate (MLS) | Absent |
| Match win/draw/loss probabilities | **Strong** | Absent (club) | Adequate | Strong (volume) | Absent | Adequate | Absent/market odds |
| Methodology transparency | **Strong** (explained, market-blind) | Strong (published methods) | Weak (opaque) | Weak | Adequate | Strong | Absent |
| Public track record / calibration audit | **Strong — unique** (Trust pages, hit/miss filters) | Adequate (retrospectives) | Absent | Absent | Absent | Adequate | Absent |
| Model-vs-market disagreement view | **Strong — unique** | Absent | Absent (odds are an input) | Absent | Absent | Absent | Absent |
| US-fan coverage (MLS/NWSL/USL/Liga MX/CPL) | **Strong — near-unique combo** | Absent | Weak | Adequate (thin) | Absent | Strong (MLS/NWSL) | Adequate (scores) |
| UX / persistent interactive dashboard | Adequate (solid PWA; unproven with casual users) | Weak (newsletter) | Weak (articles) | Weak (cluttered) | Weak (dated) | Adequate | Strong |
| Brand trust & authority | **Absent** (unknown) | Strong | Strong | Adequate (in tipster niche) | Adequate (niche) | Adequate (niche) | Strong |
| Discoverability (SEO/social/press) | **Absent** (not indexed) | Strong | Strong | Strong | Adequate | Adequate | Strong |
| Price | Free | $10/mo for extras | Free | Free | Free | Free/$5 Patreon | Free(mium) |

**Reading:** Entenser wins or co-wins on six product rows — and scores Absent on the two rows that determine whether anyone ever experiences the product. That asymmetry is the entire strategic story.

---

## 5. Entenser site assessment (outside-in)

**What's verifiably visible:** title/meta "Entenser — Football probabilities, explained and audited"; sections for League Projections, Match Projections, Teams, Trust, News, UEFA Spots; match filters including "Model hits/misses," "High-confidence misses," "Biggest edges"; Elo history charts; installable PWA; privacy-preserving Plausible analytics.

**Positioning & differentiation.** The trust/audit apparatus (public calibration, hit/miss self-reporting, model-vs-market status) is genuinely differentiated — no competitor in the set does public self-auditing. "Market-blind" is a defensible, ownable claim precisely because Opta's model ingests odds and tipster sites are odds-adjacent. But the differentiation is currently expressed for quants: "market-blind," "audited," "high leverage," "calibration" are insider terms. A new fan landing here won't know why any of it matters. The brand name "Entenser" carries no semantic hook and is unsearchable-by-guess (inference, but reinforced by the zero brand-search footprint).

**SEO/discoverability posture — the critical weakness (verified from the codebase and live fetch):**

- Client-rendered single-page app: a crawler sees the shell and placeholders, not data ([index.html](webapp/index.html), confirmed by live fetch).
- **One URL for the entire product.** 56 leagues, thousands of matches — zero of them addressable pages. No `robots.txt`, no `sitemap.xml` in [webapp/](webapp/).
- Not indexed: a web search for "entenser" returns nothing related to the site.
- Meta/OG tags on the shell are actually good (proper og:image, description) — but they apply to one page.
- The analytics bootstrap comment in index.html notes Plausible events only record "once entenser.com exists in a Plausible account" — worth verifying the account is live, or the site is flying blind on the traffic it does get.

**Messaging clarity:** the header promise ("explained and audited") is the right idea; the execution needs a plain-English on-ramp ("We predict every league. We ignore betting odds. We show you every time we were wrong.") — that's the same claim in fan language.

`★ Insight ─────────────────────────────────────`
- A static-JSON PWA is a great *architecture* for a daily-refresh data product (cheap, fast, CI-deployable) but a poor *distribution surface* — search engines index URLs, not JS state. The fix isn't abandoning the SPA; it's emitting pre-rendered per-league HTML alongside it from the same CI pipeline that already writes `webapp/data/*.js`.
- Entenser's "Trust" pages invert the usual industry pattern: competitors hide misses to protect credibility, which caps their credibility. Publishing misses is a costly signal — the classic economics of trust — and it's the one feature an odds-fed or affiliate-funded competitor can't imitate without self-harm.
`─────────────────────────────────────────────────`

---

## 6. Gaps and opportunities

1. **The vacant "SPI heir" position (verified gap).** The demand signal is unusually concrete: fake "538 predictions" sites still farm the dead brand's search traffic, and the analytics community has publicly catalogued the lack of a replacement. Entenser's product is already the closest fit; it needs URLs, name recognition, and a track record page to claim it.
2. **Underserved-league SEO whitespace.** "NWSL playoff odds," "USL Championship projections," "Canadian Premier League predictions," "Liga MX probabilities in English," Scandinavian leagues — Entenser already models all of these; incumbents either don't cover them (Silver Bulletin, ClubElo) or cover them thinly (Opta, Forebet). Low-competition keywords, high fit with the post-World Cup US fan cohort.
3. **Trust as the product.** No competitor offers public calibration auditing. "The only football model that grades itself in public" is a headline no one else can run.
4. **Model-vs-market as content.** "Where our model disagrees with the market this weekend" is inherently shareable weekly editorial that requires zero new modeling — and it serves neutral fans and value-curious readers without becoming a tipster product.
5. **Quotable-number syndication.** Opta manufactures headlines by giving journalists a number and a name ("supercomputer says 28.5%"). Entenser can run the identical playbook per league at near-zero marginal cost once per-league pages exist to link back to.
6. **Open data/API.** FiveThirtyEight's published SPI CSVs created a generation of loyal tinkerers; ClubElo survives on its API. Publishing projection CSVs would buy backlinks, citations, and community goodwill cheaply.
7. **Women's soccer runway.** WSL + NWSL coverage now, compounding toward the 2027 Women's World Cup, where the competitive field is even emptier.

---

## 7. Threats and risks (ranked by severity × likelihood)

| # | Risk | Severity | Likelihood | Notes |
|---|---|---|---|---|
| 1 | **Invisibility persists** — product excellence never meets an audience; motivation/investment decays | High | High (it's the status quo) | Entirely self-inflicted and fixable; every month of delay burns the World Cup attention dividend |
| 2 | **Silver Bulletin relaunches club soccer** | High | Medium | Capability proven (PELE), audience in place, and Silver has said the model exists but is shelved; also floated *selling* it — a buyer could be worse (a sportsbook or major media outlet). **Monitor natesilver.net announcements.** |
| 3 | **SEO channel is structurally hostile** — betting affiliates own generic "predictions" terms; AI Overviews absorb simple queries | Medium-High | High | Mitigate by targeting long-tail league/team terms and by being the citable source, not the SERP winner |
| 4 | **Platform apps add native probabilities** (FotMob/Sofascore) | High | Low-Medium | Would own the casual segment overnight; trust/transparency niche would survive but shrink |
| 5 | **Data-source fragility** — reliance on third-party feeds (ESPN endpoints visible in league config; API-Football per project docs) | Medium-High | Medium | ToS/endpoint changes could break 56-league coverage; diversification and caching discipline are the hedges |
| 6 | **Solo-operator execution risk** — one person, 56 leagues, daily refresh, CI, modeling, and now marketing | Medium | Medium | Recent commit history shows refresh-pipeline firefighting; automation debt compounds with league count |
| 7 | **Gambling-adjacency brand risk** — ad networks and affiliate money pull toward betting framing that contradicts "market-blind" trust positioning; UK/EU gambling-ad rules add compliance surface | Medium | Medium (only if ads monetization proceeds carelessly) | Choose ad partners deliberately; keep the paper-ledger/edge work internal until positioning is established |
| 8 | **Opta productizes a persistent consumer dashboard** | Medium | Low | Their incentive is B2B; the consumer site is marketing. But if it happens, they win on brand instantly |

---

## 8. Prioritized recommendations (impact vs effort)

1. **Ship crawlable per-league pages + sitemap + robots.txt.** *(High impact / Low-medium effort — do first.)* The CI pipeline already generates per-league data files nightly; emit a pre-rendered HTML page per league (current table, title/relegation odds, next matches with probabilities, canonical link into the SPA) at `entenser.com/<league>/`. Add `sitemap.xml`, `robots.txt`, and JSON-LD (SportsEvent/Dataset). This single change converts 56 leagues of invisible daily output into 56 indexable, linkable, citable surfaces.
2. **Add a plain-English trust on-ramp.** *(High impact / Low effort.)* One landing section: what market-blind means, why publishing misses matters, and a headline track-record stat ("Brier 0.633 across 4 seasons" means nothing to fans — translate: "when we say 70%, it happens ~70% of the time — here's the receipt"). This is the conversion layer for the differentiation that already exists.
3. **Ride the World Cup → domestic-league handoff (next 60 days).** *(High impact / Medium effort, time-boxed.)* New US fans exiting the tournament are the cheapest audience Entenser will ever have. Publish "just finished the World Cup? Here's your MLS/NWSL/Liga MX race, live-projected" content; NWSL/USL/CPL projections are near-uncontested.
4. **Start a weekly syndication artifact.** *(High impact / Medium effort.)* One newsletter/thread per week: "biggest model-vs-market disagreements," "title race movement," one shareable auto-generated graphic per league. This is the Opta supercomputer distribution playbook run by one person with CI. Distribution channels: X/Bluesky, r/MLS, r/soccer, r/footballstrategy (mind self-promotion norms — participate, don't spam).
5. **Verify analytics are actually recording.** *(Low effort, do this week.)* The index.html comment implies the Plausible account may never have been created. Growth strategy without measurement is guesswork.
6. **Publish projection CSVs / a simple API.** *(Medium impact / Low effort.)* Fill the SPI data hole; earn backlinks and the tinkerer community's loyalty (ClubElo's survival strategy).
7. **Defer subscriptions ~12 months; sequence monetization as support-tier → premium.** *(Prevents unforced errors.)* Pre-traction paywalls kill compounding. When traction arrives, the evidence supports a $5/mo ASA-style supporter tier before a $8–10/mo premium tier (The Athletic and Silver Bulletin anchor the ceiling). If running ads meanwhile, exclude gambling ad categories to protect the market-blind position.
8. **Stand up a lightweight competitive monitor.** *(Low effort.)* Quarterly checks: Silver Bulletin model announcements (natesilver.net archive), Opta Analyst product surface changes, FotMob/Sofascore feature releases. Risk #2 and #4 are the ones that arrive suddenly.

---

## Appendix: verification status of key claims

| Claim | Status |
|---|---|
| FiveThirtyEight shut down 2023; SPI dark | Verified ([From the Byline](https://fromthebyline.substack.com/p/fivethirtyeight-is-dead-long-live)) |
| Silver Bulletin club model dormant; PELE live for WC2026; $10/mo/$95/yr; 315k+ subs | Verified ([SBSQ #11b](https://www.natesilver.net/p/sbsq-11b-on-the-future-of-the-newsletter), [PELE](https://www.natesilver.net/p/pele-international-football-rankings-soccer-ratings-projections), natesilver.net) — *paid* sub count undisclosed; club-model relaunch plans unknown |
| Opta model uses betting odds + power rankings; free | Verified ([Opta Analyst](https://theanalyst.com/articles/opta-football-predictions)) |
| Forebet 5M+ visits/mo | **Unverified** (third-party blog; needs Similarweb) |
| 136M NA soccer fans; 40% US adults watching WC2026; 8%→12% active followers | Verified ([TV Tech/Nielsen](https://www.tvtechnology.com/insights/analysis/nielsen-north-american-soccer-fans-jump-to-more-than-136-million), [Gallup via Men's Journal](https://www.mensjournal.com/news/world-cup-us-viewership-2026), [YouGov](https://yougov.com/en-us/articles/54777-soccer-is-gaining-ground-in-the-us-ahead-of-the-fifa-world-cup)) |
| NYT: 24M Americans willing to pay for sports journalism; Athletic $7.99/mo | Moderate confidence ([A Media Operator](https://www.amediaoperator.com/newsletter/nyt-rationale-for-the-athletic-comes-into-focus/), [Subger](https://subger.com/en/service/the-athletic)) |
| FotMob has no native prediction model; Sofascore shows market odds | Verified as of mid-2026 ([predict.fotmob.com](https://predict.fotmob.com/), [comparison](https://insideformation.com/blog/best-livescore-apps-2026-comparison)) — feature sets change fast |
| entenser.com not indexed; SPA/single-URL; no sitemap/robots | Verified (codebase inspection + live fetch + brand search) |
| Competitor funding/headcount (Forebet, FotMob, Sofascore, ASA) | **Not findable from public sources in this pass** — needs Crunchbase/PitchBook or Similarweb access |
