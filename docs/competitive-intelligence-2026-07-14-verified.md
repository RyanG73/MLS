# Entenser competitive intelligence and market analysis

**Research date:** 14 July 2026  
**Scope:** Global consumer football forecasting, with emphasis on the United States, United Kingdom, and continental Europe  
**Product reviewed:** [Entenser](https://entenser.com/) and the repository in this workspace

## How to read this report

- **Verified** means observed on a cited public page or in the current repository on 14 July 2026.
- **Self-reported** means a company publishes the number about itself; it has not been independently audited here.
- **Observed** means a live-site or search-result test performed during this review.
- **Inference** means an analytical conclusion from the evidence. It is labeled and should not be treated as a fact.
- All market-size dollar figures below are scenario models, not published market estimates. The narrow category “consumer football projection products” is not separately measured by a credible public source.

## 1. Executive summary

### Bottom line

Entenser has a credible product wedge but not yet a distribution moat. Its strongest differentiator is not “more accurate picks.” It is the combination of broad league-race simulations, a model that deliberately excludes bookmaker odds, and unusually candid public grading against both naive and market benchmarks. The live site explicitly says it does not claim to beat the market; that honesty is strategically valuable because most free prediction sites are betting-led and opaque.

The immediate constraint is discoverability and international product fit. The codebase supports 56 entries marked “live,” but the public experience is one English-only, query-parameter single-page application with shared metadata, no sitemap, no canonical tags, no structured data, US date formatting, and American odds. Several leagues also have materially different data states: for example, the repository documents current results-only feeds for Finland and Poland, and 2024-only results for the Canadian Premier League and K League 1. Treating all 56 as equally “live” risks trust.

There is a real paying audience outside the United States, but it is a niche inside a vast fan market. The best early subscription is a low-priced supporter/utility tier—alerts, saved teams and races, forecast-change history, data downloads, ad-free viewing—not a hard paywall around raw probabilities. A £4.99/€5.99/$5.99 monthly test is consistent with the closest verified direct benchmark, Football Data Lab at £5.99/month. Ads can supplement subscriptions, but display ads alone are unlikely to support the product at early traffic levels, and betting-affiliate ads create regulatory and brand risk.

### The five most important strategic takeaways

1. **Own “independent forecasts that grade themselves.”** This is both differentiated and defensible. Do not position Entenser as a betting-edge service: its own historical EPL example trails the sharp market on aggregate and its displayed edge backtest is negative.
2. **Fix distribution before adding more leagues.** Crawlable league/team pages, unique metadata, a sitemap, clean URLs, and recurring editorial outputs should have higher priority than a 57th competition.
3. **Make “live” a data-quality contract.** Show current-season data, forward-fixture availability, last updated time, and projection status separately. Results-only or stale competitions should not receive the same label as fully simulated leagues.
4. **International revenue is plausible only after localization.** At minimum, the UK and Europe need local dates/time zones, decimal odds, GBP/EUR prices, and league-specific landing pages. Spanish should be the first non-English experiment because it can serve both Spain and a large US/Latin American audience.
5. **Sell utility and affiliation, not access to a number.** Free forecasts maximize sharing and search acquisition. Paid alerts, watchlists, change logs, scenarios, downloads, and an ad-free experience create repeat value competitors do not consistently offer.

## 2. Market landscape

### Category definition

Entenser sits at the intersection of four consumer categories:

1. probabilistic league and match forecasting;
2. football statistics and analytics media;
3. live-score/fan utility products; and
4. betting-adjacent prediction tools.

That matters because the direct forecast market is small and poorly measured, while the adjacent attention market is enormous. Users compare Entenser not only with model sites such as Opta Analyst and Forebet, but also with FotMob, Sofascore, newsletters, social accounts, and search results that answer “who will win the league?” without requiring another destination.

### Audience and demand signals

- **Global top of funnel — verified, medium confidence:** FIFA says there are **five billion football fans worldwide**. This is an older, extremely broad audience estimate, not an addressable subscriber count. [FIFA football landscape](https://publications.fifa.com/en/vision-report-2021/the-football-landscape/)
- **United States — verified, high confidence:** Nielsen reports a US soccer fanbase of **more than 62 million**, the fifth largest globally. It also reports that 56% of US soccer fans attribute rising interest to the 2026 World Cup, while 33% of the wider US population expected its soccer interest to grow. [Nielsen, June 2026](https://www.nielsen.com/insights/2026/world-cup-ad-spend/)
- **European engagement — verified, medium confidence:** UEFA reported 229 million aggregate attendances across European men’s and women’s domestic competitions in 2023/24. Attendance is not unique fans, but it demonstrates habitual demand across many leagues, not only the “big five.” [UEFA European Club Footballing Landscape](https://www.uefa.com/news-media/news/0291-1bd655648c06-6b05b0dbe265-1000--new-uefa-landscape-report-shows-popularity-of-european-foo/)
- **Digital consumption — verified, high confidence:** UEFA’s 2024/25 annual report says its club-competition sites and apps generated 357 million sessions, up 23% year over year. [UEFA annual report 2024/25](https://editorial.uefa.com/resources/02a1-1fcb1ef35df9-e69c325893be-1000/20260113_enclosure_03_annual_report_2024-25_en.pdf)
- **Current event tailwind — verified but event-driven:** FIFA reported 20 billion video views and 6.25 million cumulative attendance by the final eight of the 2026 World Cup. This is evidence of exceptional current interest, not a safe post-tournament run rate. [FIFA, 8 July 2026](https://inside.fifa.com/organisation/media-releases/packed-stadiums-record-digital-reach-world-cup-2026-numbers-unprecedented-scale)

### TAM, SAM, and SOM

No credible public source isolates consumer football-projection revenue. The following model is deliberately transparent and should be replaced with measured Entenser acquisition and conversion data.

| Layer | Scenario | Annual revenue implication | Confidence |
|---|---:|---:|---|
| Audience TAM | 5 billion global football fans | Not a revenue figure | Medium on FIFA's broad count; low as a product TAM |
| High-intent global niche | Assume 0.1%–0.3% of fans actively consume quantitative forecasts: 5m–15m people | If 1%–3% pay $40–$80/year: **$2m–$36m** subscription revenue | Very low; all conversion inputs are assumptions |
| Core SAM: US/UK/Europe | Assume 1m–5m reachable quantitative football fans, informed directionally by Opta Analyst's 1m+ monthly users and Forebet's self-reported 5m+ monthly visits | At 1%–3% paid and $50–$75 ARPPY: **$0.5m–$11.25m** | Low; audiences overlap and are not equivalent to buyers |
| Entenser three-year SOM | 25k–100k monthly active users | 1%–3% paid at ~$60/year: **$15k–$180k subscription ARR** | Low until traffic, retention, and willingness-to-pay tests exist |
| Entenser ad layer | Same 25k–100k MAU; assume 3–8 monetizable impressions per MAU/month and $3–$10 net RPM | **$2.7k–$96k/year** | Very low; page depth, geography, consent, fill, and ad format dominate |

The combined three-year scenario is roughly **$18,000–$276,000 in annual consumer revenue**, before taxes, payment fees, data costs, content costs, and labor. This is not a forecast. It shows why subscriptions plus selective sponsorship are more credible than an ad-only plan at modest scale.

**What would close the gap:** actual monthly users by country; search impressions and click-through rate; 30/90-day return rates; favorite-team/league cohorts; email conversion; a localized price-sensitivity survey; and a real or “coming soon” checkout test by currency. Without those, a tighter revenue forecast would be false precision.

### Growth trends and forces shaping the market

**Behavioral**

- Football consumption is mobile, continuous, and second-screen. FIFA's broad research found 83% of football fans used a smartphone while watching TV, and current incumbents train users to expect instant alerts and personalization. [FIFA football landscape](https://publications.fifa.com/en/vision-report-2021/the-football-landscape/)
- Interest is fragmented by league, language, nation, club, and tournament. Nielsen found Liga MX was the most-watched soccer league on US television in 2025, which makes Spanish-language and Mexican-football coverage an opportunity inside the United States as well as abroad. [Nielsen](https://www.nielsen.com/insights/2026/world-cup-ad-spend/)
- Free expectations are strong. Opta Analyst, Forebet, ClubElo, and score apps provide substantial utility at no charge. A paid product therefore needs recurrence, personalization, community, or exclusive interpretation—not simply a probability table.

**Technological**

- Commodity modeling and generative content lower the cost of launching a forecast site. The moat shifts toward data reliability, historical records, distribution, brand trust, and a distinctive model policy.
- Platforms are expanding. FIFA+ on DAZN says it will carry more than 8,500 live matches annually from about 100 national associations, illustrating how large aggregators can bundle content and fan utilities. [FIFA+ on DAZN](https://inside.fifa.com/organisation/media-releases/fifa-plus-dazn-global-home-of-football)
- Search engines can render JavaScript, but Google says app-shell pages must enter a rendering queue and recommends server-side or pre-rendering because it improves crawler/user performance and not all bots execute JavaScript. Unique titles, descriptions, canonical URLs, and crawlable links still matter. [Google JavaScript SEO guidance](https://developers.google.com/search/docs/crawling-indexing/javascript/javascript-seo-basics)

**Regulatory and commercial**

- A neutral forecast product is generally lower-risk than a sportsbook or tipster, but the position changes if Entenser encourages bets, carries affiliate links, or uses gambling creative. UK ASA guidance notes that Oddschecker content was treated as advertising when it encouraged users to bet, even though Oddschecker was not itself the gambling operator. UK rules also prohibit gambling advertising with strong appeal to under-18s. [UK ASA/CAP guidance, May 2026](https://www.asa.org.uk/advice-online/betting-and-gaming-appeal-to-children.html)
- European gambling-promotion rules vary by country. Italy has a broad online gambling-advertising prohibition, while Spain regulates commercial communications and affiliates. A single pan-European betting-affiliate program is therefore high-friction. [Italy AGCOM](https://www.agcom.it/competenze/piattaforme-online/divieto-di-pubblicita-sul-gioco-dazzardo-online-con-vincite-denaro), [Spain DGOJ](https://www.ordenacionjuego.es/en/node/2151)
- Behavioral advertising can introduce consent obligations. EU guidance says cookies requiring consent may not be set on first arrival and must wait for affirmative consent. Entenser's current cookie-less analytics posture is simpler; mainstream ad-tech could change it. [EU Your Europe cookie guidance](https://europa.eu/youreurope/business/dealing-with-customers/data-protection/online-privacy/index_en.htm)
- International subscriptions require local currency and tax operations. Stripe supports more than 135 currencies and notes that presentment in a customer's local currency can improve conversion, while cross-border digital services can trigger VAT/GST registration and collection obligations. [Stripe currencies](https://docs.stripe.com/currencies?locale=en-GB), [Stripe EU tax guidance](https://docs.stripe.com/tax/supported-countries/european-union)

This is commercial analysis, not legal or tax advice. Country-specific review is required before betting affiliates or paid digital services launch broadly.

## 3. Competitor deep-dive

### 3.1 Silver Bulletin / PELE

**Competitive type:** adjacent today; credible future direct competitor for club football.

**Positioning and segment — verified:** Nate Silver's personality-led subscription publication spans elections, media, sports, and poker. PELE is currently an international-team rating and forecasting system covering all 211 FIFA members, not a club-league product. Advanced sections and forecast content are paid. [PELE](https://www.natesilver.net/p/pele-international-football-rankings-soccer-ratings-projections)

**Pricing — last publicly verified, medium confidence:** Silver Bulletin announced $10/month or $95/year for new subscribers from June 2024. The current generic subscribe page did not expose a price to the audit crawler, so a later change cannot be ruled out. [Silver Bulletin pricing announcement](https://www.natesilver.net/p/comments-will-now-mostly-be-for-paying)

**Core features:** ratings, offense/defense and style components, historical data since 1872, pairwise team projections, future international-match projections, and a World Cup simulator.

**Traction/team/funding — mixed:** the subscribe page displayed **more than 316,000 subscribers** on the audit date; paid share is not disclosed. PELE identifies Nate Silver and Joseph George. Funding, full headcount, and soccer-specific traffic are not public. [Silver Bulletin subscribe page](https://www.natesilver.net/Subscribe)

**GTM:** author brand, newsletter distribution, social/media appearances, paywalled analysis, and event-timed model launches.

**Apparent strengths:** exceptional brand credibility, an existing large audience, editorial voice, and demonstrated ability to monetize models. **Apparent weaknesses/inference:** soccer is one subject within a broad newsletter; PELE is national-team-only; its $95 annual bundle is expensive for a fan who wants club forecasts alone. Silver wrote in April that club projections were “much further down the line,” though the July PELE page says expansion depends on interest. [April roadmap statement](https://www.natesilver.net/p/sbsq-31-trump-is-super-unpopular)

**Threat to Entenser:** medium today, high if Silver launches club projections. Entenser should not imitate Silver's personality model; it should accumulate club-level history and utility before Silver enters.

### 3.2 Opta Analyst / Stats Perform

**Competitive type:** direct for league-season forecasting; adjacent as a broader analytics publisher.

**Positioning and segment — verified:** free, polished, data-led sports editorial for mainstream fans; also a consumer showcase for Stats Perform's enterprise data and AI products.

**Pricing:** consumer content and supercomputer articles are free; no public consumer subscription was observed. The underlying B2B prices are not public and are not comparable to a consumer subscription.

**Core features:** league-season simulations, tournament forecasts, Power Rankings, advanced match and player analysis, interactive editorial, and broad historical data. Opta says its league forecasts combine betting-market odds with Opta Power Rankings and run thousands of simulations. [Opta Serie A methodology example](https://theanalyst.com/articles/serie-a-predictions-2025-26-opta-supercomputer)

**Traction/team/funding — self-reported:** Stats Perform says **more than one million monthly active users** visit Opta Analyst. It also reports 3,900 competitions and more than 500,000 matches covered annually across the parent business. Its careers page reports roughly 2,450 employees across 26 countries. Exact Opta Analyst headcount and traffic by football section are unavailable. Stats Perform is a private company; current funding details are not published on the reviewed pages. [Stats Perform company page](https://www.statsperform.com/about/), [careers](https://www.statsperform.com/careers/)

**GTM:** search-oriented editorial, press-ready “supercomputer” headlines, syndication, social graphics, and cross-promotion of the Opta brand.

**Apparent strengths:** data rights, brand authority, production quality, distribution, and the ability to publish immediately around news. **Apparent weaknesses/inference:** forecasts are episodic articles rather than a persistent fan workspace; inputs use market odds, creating a clean contrast with Entenser; public calibration and failure analysis are limited relative to Entenser's Trust view.

### 3.3 Forebet

**Competitive type:** direct for match probabilities; adjacent for season-race forecasting.

**Positioning and segment — verified:** “football is mathematics,” aimed mainly at high-frequency prediction and betting-intent users worldwide.

**Pricing:** free, ad-supported; no subscription is advertised. Its privacy policy names Google AdSense/AdMob and Criteo. [Forebet privacy policy](https://www.forebet.com/index.php/en/privacy-policy)

**Core features:** 1X2 probabilities, correct score, totals, both-teams-to-score, handicaps, live predictions, trends, livescores, injuries, favorites, team comparisons, and mobile apps. It offers many languages, time-zone selection, and decimal/fractional/American odds.

**Traction/team/funding — self-reported/verified platform signal:** Forebet says it covers 850+ football competitions and 2,400 sports leagues, producing analysis for 2,250+ games weekly. Its FAQ claims more than five million visits per month. Google Play shows 1m+ Android downloads. Exact headcount and funding are not disclosed; an official company profile describes a small team. [Forebet overview](https://www.forebet.com/index.php/en/what-is-forebet), [FAQ](https://www.forebet.com/en/faq), [Google Play](https://play.google.com/store/apps/details?hl=en&id=com.devclev.forebet)

**GTM:** massive programmatic SEO footprint, localization, free utility, apps, social channels, and advertising.

**Apparent strengths:** breadth, internationalization, search presence, habit-forming match volume, and mature ad monetization. **Apparent weaknesses/inference:** betting-heavy framing, proprietary/black-box modeling, little public calibration, and limited focus on full-season title/qualification/relegation races.

### 3.4 Football Data Lab

**Competitive type:** direct consumer probability and subscription competitor.

**Positioning and segment — observed:** a newer UK product for “serious football fans and punters,” emphasizing Dixon-Coles/xG methodology, public accuracy, EV tools, and 30 competitions.

**Pricing — observed 14 July 2026:** all competitions and today's fixtures are free; Pro is **£5.99/month or £57.50/year** with a seven-day trial. [Football Data Lab](https://www.footballdatalab.co.uk/)

**Core features:** match probabilities, future dates, expected value, odds and closing-line-value tracking, BTTS, radar and AI views, backtesting/bankroll tools, and player/scouting search. It markets a 60.4% “heavy-favourite” hit rate; that is not the same as full-probability calibration.

**Traction/team/funding:** no reliable public traffic, funding, customer count, or headcount was found. The product appears early-stage, but that is an inference from the public footprint rather than a verified founding date.

**GTM:** search pages, a generous free daily surface, a seven-day trial, and betting/analytics terminology.

**Apparent strengths:** the clearest direct price benchmark, modern UX, transparent methodological language, and concrete paid utilities. **Apparent weaknesses/inference:** only 30 competitions, match/betting orientation, English-only presentation observed, and no persistent title/qualification/relegation simulator comparable with Entenser.

### 3.5 ClubElo

**Competitive type:** adjacent ratings and historical-data competitor.

**Positioning and segment — verified:** a long-running European club-rating reference for quantitatively minded fans, journalists, and analysts.

**Pricing:** free; no consumer subscription or advertising proposition was found.

**Core features:** daily Elo club rankings, historical charts, country rankings, match probabilities derived from rating differences, and downloadable/reusable data with attribution. [ClubElo](https://clubelo.com/), [system description](https://clubelo.com/System), [data](https://clubelo.com/Data)

**Traction/team/funding:** exact traffic and funding are unavailable. The About page identifies Lars Schiefler as the creator and describes a Python-generated static site, supporting a one-person-project characterization. [ClubElo About](https://clubelo.com/About)

**GTM:** durable backlinks, data reuse, word of mouth, and historical authority rather than paid acquisition.

**Apparent strengths:** longevity, simple transparent mechanics, linkable historical records, and data portability. **Apparent weaknesses/inference:** dated interface, Europe-only scope, ratings rather than full season-race simulations, and limited personalization/editorial cadence.

### 3.6 American Soccer Analysis

**Competitive type:** adjacent US-soccer analytics and supporter-membership competitor.

**Positioning and segment — verified:** independent objective analysis of MLS and US soccer, with articles, podcasts, expected-goals data, tables, and visualizations. [American Soccer Analysis](https://www.americansocceranalysis.com/)

**Pricing:** Patreon membership starts at about $5/month; the site promotes $5/month access to data-visualization tools. [ASA Patreon](https://www.patreon.com/americansocceranalysis)

**Core features:** MLS/NWSL/US-focused analytics, xG and player/team data, interactive tools, written analysis, and podcasts. Forecasting is present but is not the single core product.

**Traction/team/funding — observed:** Patreon displayed roughly 246 members and approximately €376/month on the audit date; Patreon localizes currency and figures can move. Site traffic, formal headcount, and external funding are unavailable. [ASA Patreon](https://www.patreon.com/americansocceranalysis)

**GTM:** community credibility, contributor analysis, podcasting, Patreon, social media, and a specialized US-soccer audience.

**Apparent strengths:** domain authority in MLS/US soccer, proprietary analytical work, community trust, and a credible low-price supporter model. **Apparent weaknesses/inference:** limited geographic scope, forecasts are not the primary navigation object, and the experience is less suited to a casual global fan.

### 3.7 FotMob

**Competitive type:** adjacent fan-utility competitor with high feature-entry potential.

**Positioning and segment — verified:** a global, mobile-first score and football-following utility for mainstream fans.

**Pricing:** free with ads and in-app purchases; an exact internationally comparable subscription price was not available from the audited public pages. [FotMob Google Play](https://play.google.com/store/apps/details?hl=en-US&id=com.mobilefootie.wc2010)

**Core features:** live scores and alerts, personalized news, xG and shot maps, ratings, commentary, highlights, TV schedules, and coverage of more than 500 leagues. Its public “Predict” experience is a user guessing game rather than a published probabilistic model. [FotMob Google Play](https://play.google.com/store/apps/details?hl=en-US&id=com.mobilefootie.wc2010), [FotMob Predict](https://predict.fotmob.com/)

**Traction/team/funding — verified/self-reported:** Google Play shows **50m+ downloads**, 741k reviews, and a 4.9 rating; the listing says more than 20m fans use the product. LinkedIn lists 11–50 employees. Funding is not disclosed on the reviewed sources. [FotMob LinkedIn](https://www.linkedin.com/company/fotmob)

**GTM:** app-store distribution, alerts, personalization, editorial/news aggregation, partnerships, search, and a freemium ad model.

**Apparent strengths:** installed audience, habitual daily use, localization, speed, and polished mobile UX. **Apparent weaknesses relative to Entenser:** no public model-driven season probabilities were found in the reviewed feature set; detailed forecasting is not the core promise. **Threat:** high if it adds season forecasts because distribution is already solved.

### 3.8 Sofascore

**Competitive type:** adjacent fan-utility competitor with high feature-entry potential.

**Positioning and segment — verified:** a multi-sport score, statistics, and visualization platform for mainstream and advanced fans.

**Pricing:** free with ads and in-app purchases; an ad-free subscription exists, but a stable cross-country public price was not verified. [Sofascore Google Play](https://play.google.com/store/apps/details?hl=en-US&id=com.sofascore.results)

**Core features:** live scores, alerts, player ratings, heat maps, shot maps, community predictions, brackets, and coverage of thousands of leagues and tournaments across 25+ sports. [Sofascore Google Play](https://play.google.com/store/apps/details?hl=en-US&id=com.sofascore.results)

**Traction/team/funding — verified/self-reported:** Google Play shows **100m+ downloads**, 1.14m reviews, and a 4.5 rating. Sofascore says it reached 35m monthly active users in 2025 and had about 300 employees in 2024; LinkedIn displayed a larger current employee count during the audit, but LinkedIn counts are approximate. [Sofascore company history](https://www.sofascore.com/news/sofascore-turns-15-celebrating-15-years-of-the-platform-fans-love), [LinkedIn](https://www.linkedin.com/company/sofascore-ltd)

**GTM:** global apps, localization, search, product virality, push notifications, ad-supported free access, and sports partnerships.

**Apparent strengths:** enormous reach, visual polish, personalization, and deep match/player data. **Apparent weaknesses relative to Entenser:** community predictions are not an auditable probabilistic league model, and season-race simulation is not the primary value proposition. **Threat:** high distribution leverage if probabilistic forecasts become a feature.

## 4. Comparison matrix

Scores are directional analyst judgments based on publicly visible products: **1 = weak/absent; 3 = adequate; 5 = category-leading.** They are not performance measurements. “Season forecasts” emphasizes title/qualification/relegation probabilities; “transparent trust” emphasizes calibration, methodology, and visible failure modes.

| Product | Season forecasts | Match probabilities | Coverage breadth | Transparent trust | Casual-fan UX | Localization | Brand/distribution | Free value | Non-betting fit |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| **Entenser** | **5** | 4 | 4 | **5** | 3 | **1** | **1** | 5 | 4 |
| Silver Bulletin / PELE | 1 for clubs; 5 international | 4 international | 2 | 4 | 3 | 2 | 5 | 2 | 5 |
| Opta Analyst | 4 | 4 | 4 | 2 | 4 | 3 | 5 | 5 | 5 |
| Forebet | 1 | 5 | 5 | 2 | 3 | 5 | 4 | 5 | 1 |
| Football Data Lab | 1 | 4 | 3 | 4 | 4 | 1 | 1 | 4 | 1 |
| ClubElo | 1 | 3 | 2 | 4 | 2 | 2 | 2 | 5 | 5 |
| American Soccer Analysis | 2 | 2 | 1 | 4 | 3 | 1 | 2 | 4 | 5 |
| FotMob | 1 | 1 model / 3 user game | 5 | 1 | 5 | 5 | 5 | 5 | 5 |
| Sofascore | 1 | 1 model / 3 community | 5 | 2 | 5 | 5 | 5 | 5 | 5 |

Entenser leads on the intersection of season-race depth and model accountability. It is last or tied-last on the two dimensions that turn product quality into audience: localization and distribution.

## 5. Entenser assessment

### Positioning and differentiation

**Verified:** the live About page calls Entenser a “market-blind football prediction system,” states that it is never trained on betting odds, and explicitly says, “We do not claim to beat the market.” It presents Brier scores by model family and known weak spots. [Entenser About](https://entenser.com/?league=about)

**Assessment:** this is the right strategic substance but not yet the clearest consumer promise. “Football probabilities, explained and audited” is credible but abstract. A fan should understand within one line that the site answers three questions: Who wins the league? Who qualifies or goes down? How did those odds change?

The most ownable position is:

> **Independent football forecasts across dozens of competitions. No bookmaker odds in the model. Every forecast graded in public.**

That sentence combines scope, independence, and accountability. It avoids implying profitable betting advice.

### Product strengths

- **Verified:** title, qualification, relegation, match, team, what-if, power, trust, movement, result, news, and UEFA-place views are already represented in the live experience.
- **Verified:** the EPL forecast runs 10,000 season simulations and provides a persistent model-versus-market comparison. [Entenser Premier League](https://entenser.com/?league=epl)
- **Verified:** the current EPL trust payload reports model Brier 0.5887 versus market 0.5739, while the naive benchmark is materially worse. It also displays a negative historical flat-stake ROI for the highlighted high-edge backtest. That candor is a trust asset, not a defect, provided the site is sold as insight rather than betting profit.
- **Inference:** the broad league architecture, common data payloads, and automated build make it possible to create many highly specific pages and editorial outputs at low marginal production cost.

### Product and trust weaknesses

- **Verified:** all 56 registry entries are marked `status: "live"`, while repository documentation says the Canadian Premier League is results-only from 2024, K League 1 is limited to 2022–24 results, and Finland and Poland are results-only without forward fixtures. ([current-state notes](../docs/CURRENT_STATE.md))
- **Verified:** some split-round formats are approximate. This is disclosed in league rules, but the global “live” count does not communicate the distinction.
- **Assessment:** a compact status taxonomy is required: **Current forecast**, **Preseason forecast**, **Results only**, **Historical**, **Data delayed**, and **Format approximate**. Users will forgive limitations they can see; they will not forgive discovering stale data after trusting a “live” label.
- **Inference:** the number and density of expert metrics can overwhelm casual fans. Brier score should remain available, but the first layer should translate it: “better than a baseline; still behind the betting market.”

### SEO and discoverability posture

**Verified from the repository:** Entenser serves one large `index.html` and league views via query parameters such as `?league=epl`. The initial HTML has one title and description for every route. No canonical link, JSON-LD, `robots.txt`, or sitemap exists in `webapp/`. Internal league navigation also relies on query-parameter URLs. ([site shell](../webapp/index.html), [league registry](../webapp/leagues.js))

**Observed:** a live search test surfaced an Entenser Chinese Super League URL with a mismatched MLS-oriented title/snippet; a later `site:` query did not return stable results. Search results vary, so this is evidence of an indexing/metadata problem, not proof that the entire site is absent from Google. Search Console is needed to measure the actual indexed URL count and impressions.

**Assessment:** discoverability is weak. Google can render the application, but the crawl and rendering path is unnecessarily fragile, and the site does not provide distinct search documents for “Premier League title odds,” “MLS playoff probabilities,” club forecast histories, or weekly race changes. Google itself recommends unique titles/descriptions, canonical URLs, crawlable paths, and server-side or pre-rendered content for JavaScript applications. [Google JavaScript SEO](https://developers.google.com/search/docs/crawling-indexing/javascript/javascript-seo-basics), [canonical guidance](https://developers.google.com/search/docs/crawling-indexing/consolidate-duplicate-urls), [sitemap guidance](https://developers.google.com/search/docs/crawling-indexing/sitemaps/build-sitemap)

### International readiness

**Verified:** the document language is English; dates are explicitly formatted `en-US`; match probabilities are converted to “fair American odds”; and no locale/translation framework or decimal/fractional odds preference is present. The news implementation intentionally selects one English-language outlet per major European country.

**Assessment:** broad league coverage is not the same as a global product. UK users need decimal/fractional options, local dates and kickoffs, and GBP. Continental users need decimal odds, EUR, local time zones, and at least indexable local-language landing pages. Full application translation is not required for the first test; translated league/race summaries and localized metadata can establish demand.

### Messaging clarity

The current headline explains the method before the user benefit. The homepage should lead with live fan questions, then use “market-blind and publicly graded” as the reason to believe. “Market-blind” also needs a one-clause explanation every time it is introduced; many consumers will not know whether it means no betting data, no live data, or no market-value data.

### Analytics posture

The code includes privacy-preserving Plausible analytics, but a code comment warns that events will be dropped unless the domain is configured in the Plausible account. Whether production data is currently being collected could not be confirmed. Access to the Plausible account and Google Search Console is required before any confident funnel or SEO diagnosis.

## 6. Gaps and opportunities

### 1. Transparent, non-betting season forecasts

Forebet and Football Data Lab skew toward punters; Opta is market-informed and editorial; ClubElo is ratings-led; score apps emphasize live utility. No reviewed competitor combines Entenser's broad club-season simulations, bookmaker-independent input policy, and public trust ledger. This is the clearest position to own.

### 2. Forecast-change history

Fans care about movement after a match, injury, or run of form. Entenser already calculates movers and drift trajectories. Turning that into a team-specific timeline—“Arsenal title chance: 34% → 41% this month, with the three largest changes”—creates searchable content, shareable cards, and a paid alert feature from existing data.

### 3. Underserved leagues with honest data tiers

Women's leagues, second tiers, and leagues outside Western Europe's big five receive less high-quality season forecasting. Entenser can win these long-tail audiences, but only if it labels data quality and format approximations. Depth and reliability in 20–30 competitions is more valuable than nominal coverage in 56 indistinguishable statuses.

### 4. Local-language long-tail search

The product has data for Spain, Germany, France, Italy, Portugal, the Netherlands, Poland, Scandinavia, and more, but almost no native-language discovery surface. Programmatically generated, editor-reviewed pages such as “probabilidades de ganar LaLiga,” “Abstiegswahrscheinlichkeit Bundesliga,” and “probabilità scudetto Serie A” are a substantial whitespace opportunity. Forebet proves that localization matters, but its output is match/betting-led; Entenser can own season-race intent.

### 5. Publisher and creator distribution

Offer embeddable race tables, weekly charts, and a clearly attributed data feed for journalists, newsletters, supporter sites, and podcasts. Opta wins partly because its statistics travel. Entenser's forecast deltas and independent-market comparisons are inherently quotable.

### 6. A supporter tier between free sites and broad premium newsletters

The market has free/ad-supported products and Silver Bulletin at a last-verified $95/year. Football Data Lab provides a direct £5.99/month anchor; ASA demonstrates a $5 supporter audience. Entenser can test **£4.99 / €5.99 / $5.99 monthly** and approximately two months free annually, without paywalling the core public forecast.

Recommended paid value:

- favorite teams/leagues and email/push alerts;
- forecast-change history and custom thresholds;
- saved what-if scenarios;
- downloadable current and historical data;
- ad-free browsing;
- a weekly “model changed its mind” briefing;
- supporter recognition or member discussion, if community moderation is feasible.

### 7. Trust as content

Publish a recurring, plain-language scorecard: best calls, worst misses, calibration, and model-versus-market gap. Competitors publish predictions; few make the grading cycle a product. This can attract analytical fans without implying gambling profit.

## 7. Threats and risks

| Rank | Risk | Severity | Likelihood | Evidence / reason |
|---:|---|---|---|---|
| 1 | **No scalable discovery loop** | High | High | One query-parameter SPA, shared metadata, no sitemap/canonicals, and no established audience signal found. Good models do not self-distribute. |
| 2 | **Data freshness and “56 live” trust failure** | High | High | Repository documentation confirms results-only and stale-source exceptions while every registry entry is labeled live. |
| 3 | **Weak consumer willingness to pay** | High | High | Most alternatives are free; no Entenser traffic, retention, email, or checkout data was available. |
| 4 | **Incumbent feature expansion** | High | Medium-high | FotMob and Sofascore have tens of millions of users; Opta has data and editorial authority. A forecast module would be cheap for them to distribute. |
| 5 | **Execution sprawl across leagues** | High | High | Many data sources, formats, calendars, playoffs, and split rounds create ongoing operational burden. This is a codebase assessment; team capacity was not provided. |
| 6 | **Model positioned as betting edge** | High | Medium | “Fair odds,” value views, and market comparisons can pull messaging toward betting even though the public backtest is negative. That creates reputational and regulatory exposure. |
| 7 | **International commercial complexity** | Medium-high | High if monetized globally | Local currency, VAT/GST, consumer terms, privacy/consent, translations, support, and country-specific gambling-ad rules add friction. |
| 8 | **Silver Bulletin enters club football** | High | Low-medium in the near term | Silver has brand, audience, and model capability, but publicly described club forecasts as much further down the line in April 2026. |
| 9 | **Search/AI answer disintermediation** | Medium | High | Search engines and assistants can answer simple “who is favored?” questions. Entenser needs proprietary history, interactive scenarios, alerts, and attribution-worthy data. |
| 10 | **Monetization damages the product** | Medium | Medium | Dense display ads reduce trust and speed; betting affiliates conflict with the neutral position; a hard paywall reduces sharing and indexing. |

## 8. Prioritized recommendations

| Priority | Move | Impact | Effort | Rationale |
|---|---|---:|---:|---|
| P0 | **Establish measurement truth** | High | Low | Confirm Plausible production collection; connect Search Console; track league view, return visit, favorite intent, email signup, pricing click, country, and referrer. Define weekly returning forecast users as the primary early metric. |
| P0 | **Replace one “live” status with a public data-status contract** | High | Low-medium | Show season, last data timestamp, next-fixture availability, projection status, source class, and format caveats. Reclassify stale/results-only leagues. This protects the trust position immediately. |
| P0 | **Rewrite the first-screen promise** | High | Low | Lead with the fan outcome: “Title, qualification and relegation forecasts across world football.” Follow with “No bookmaker odds in the model. Every forecast graded in public.” Explain market-blind in plain language. Show “56 competitions tracked” separately from full-forecast status. |
| P0 | **Create crawlable league and team documents** | Very high | Medium | Use clean paths such as `/leagues/premier-league/forecast` and `/teams/arsenal/forecast`; pre-render meaningful HTML; set unique titles/descriptions/canonicals; add a sitemap and crawlable internal links. Keep the SPA for interaction. |
| P1 | **Turn forecast movement into a distribution product** | High | Medium | Generate weekly race recaps, biggest movers, model misses, and share cards with stable URLs. Add email signup at the point of interest: “Tell me when this changes by 5 points.” |
| P1 | **Localize the UK experience, then test Spanish** | High | Medium | Add browser/local preference for time zone and date; decimal/fractional/American odds; GBP/EUR/USD; UK English. Then ship Spanish league/race landing pages and metadata. Measure organic demand before translating every control. |
| P1 | **Run a supporter-tier demand test** | Medium-high | Low-medium | Test £4.99/€5.99/$5.99 per month and annual plans with alerts, saved teams, history, downloads, ad-free use, and weekly briefings. Use a waitlist or refundable preorder if the features are not ready. Segment results by country. |
| P1 | **Build an attribution-friendly embed/API layer** | High | Medium | Publish selected current snapshots as CSV/JSON and offer embeddable race tables. Require attribution and review data licensing/terms first. Backlinks and publisher use can become a moat. |
| P2 | **Use contextual sponsorship before behavioral or betting ads** | Medium | Medium | Target football media, apparel, ticketing, travel, streaming, games, and data/tech sponsors. Preserve fast pages and the independent brand. Obtain country-specific advice before any gambling affiliate program. |
| P2 | **Create a quarterly competitive and data-operations review** | Medium | Low | Monitor Silver club plans, Opta/score-app forecast features, competitor prices, index coverage, broken feeds, stale competitions, and user retention. Stop expanding coverage when freshness service levels are missed. |

### Recommended 90-day sequence

**Days 1–14:** verify analytics and Search Console; publish the data-status taxonomy; revise the homepage promise; instrument email and pricing intent.

**Days 15–45:** ship pre-rendered league pages for the top 10 demand markets, clean URLs, unique metadata/canonicals, sitemap, and weekly movers/misses pages. Start with Premier League, Champions League, MLS, Liga MX, La Liga, Bundesliga, Serie A, Ligue 1, NWSL, and the Championship.

**Days 46–75:** launch UK localization and decimal odds; add favorite-team/league email alerts; run the supporter-tier price test in USD, GBP, and EUR.

**Days 76–90:** publish Spanish landing pages for La Liga, Liga MX, Champions League, and major national-team/event content; begin publisher outreach with embeds and weekly data notes; decide whether to build the paid tier from measured conversion, not enthusiasm alone.

### Decision gates

- **Build paid membership** if at least 2% of returning users join a paid-intent list or at least 1% complete a real checkout at the proposed price.
- **Scale a locale** if localized pages produce material non-branded impressions and at least comparable email conversion to English pages after a full competition cycle.
- **Add another league** only if current full-forecast leagues meet freshness targets and the candidate has identifiable search/community demand.
- **Introduce ads** only after measuring revenue per thousand sessions against page-speed, return-rate, and trust effects.

## Unconfirmed facts and data needed

| Unknown | Why it matters | How to close it |
|---|---|---|
| Entenser traffic, geography, and retention | Determines realistic SOM, language order, and ad viability | Plausible production access and cohort export |
| Search index coverage and query demand | Determines the true SEO baseline | Google Search Console pages, queries, countries, and rich-result reports |
| Email list and repeat-usage behavior | Best early signal of subscription potential | Add/inspect signup events and 30/90-day cohorts |
| Willingness to pay by country | Public competitor prices are only anchors | Localized checkout/waitlist experiment and price-sensitivity survey |
| Entenser team capacity and operating cost | Determines feasible league count and roadmap | Team/headcount, weekly maintenance time, data/API spend, hosting, and support assumptions |
| Data licensing and redistribution rights | Governs ads, subscriptions, public downloads, and embeds | Source-by-source counsel/contract review |
| Competitor revenue and paid conversion | Mostly private | Paid intelligence services, company interviews, filings where available, or customer research |
| Football Data Lab traffic/team/funding | No reliable public data found | Direct outreach or paid traffic/company databases |
| Silver Bulletin's current checkout price and paid subscriber mix | Generic subscribe page hid price; soccer-specific conversion unknown | Manual logged-out checkout by locale and/or direct confirmation |

The most consequential missing evidence is first-party Entenser behavior. Until that is available, the strategic recommendations are robust, but the revenue range should remain a scenario rather than a forecast.
