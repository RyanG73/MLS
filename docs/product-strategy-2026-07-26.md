# Product & strategy pack — 2026-07-26

> **Dated evidence, as of 2026-07-26.** Superseded by `docs/STATUS.md` for anything it also covers.
> Figures inside are as-of and may be stale — re-measure before quoting, and never publish a
> number from here without checking `docs/figures.json`.
Four questions from the 2026-07-25 feedback round: a daily match-recommendation feature, retention
for Intel subscribers, European market entry, and how often the site can update. Written after the
same session shipped the masthead, RSS, crest, Leagues Cup, playoff-bracket and Transfermarkt fixes;
numbers here are measured against this repo, not estimated.

> **Implementation status — shipped 2026-07-26.** The four immediate recommendations are now
> implemented in order: (1) "since your last visit" consumes a durable, league-qualified user
> cursor; (2) followed clubs receive a win/draw/loss stakes card in the hub and a timezone-aware
> match-morning briefing; (3) a cached-probability fast path publishes result-driven projections
> from a one-snapshot `live-data` branch every 15 minutes in match windows and hourly otherwise,
> without refitting or refreshing prices; and (4) public acquisition pages, RSS and share cards
> are forecast-first, with local league aliases and a European coverage landing page. The
> authenticated comparison layer remains available only after an explicit `?market=1` request.

---

## 1. "Matches to Watch" — shipped feature

**Status: built by `scripts/build_match_leverage.py`, wired into both refresh paths, and rendered
as three rails on the Matches page.**

### The metric

Leverage is *the expected movement in table odds attributable to one match*. Not a heuristic —
a conditional simulation:

1. Simulate the remaining season N times from the payload's own per-fixture pH/pD/pA → baseline
   `P(bucket)` for every club.
2. Re-simulate three times per candidate fixture, pinning it to home / draw / away →
   `P(bucket | outcome)`.
3. `leverage = Σ_outcome P(outcome) × Σ_{club∈match, bucket} w_bucket × |P(bucket|outcome) − P(bucket)|`

It needs no model refit and no network: the built payloads already carry every fixture's
probabilities, which is the same input the client what-if sim uses. **The whole cross-league board
computes in 8 seconds for 121 fixtures across 78 leagues** (2,000 sims/fixture), so this is cheap
enough to run on every build.

### It works, and the output is the point

Brazilian Série A, next 10 days:

| fixture | leverage | what turns on it |
|---|---:|---|
| Mirassol v Remo | 12.85 | Mirassol relegation ±15.6pp |
| Internacional v Flamengo | 11.08 | Internacional relegation ±14.2pp |
| Vitória v Palmeiras | 7.76 | Palmeiras title ±8.5pp |

The top fixture is two clubs nobody outside Brazil follows. The marquee name-brand fixture
(Internacional v Flamengo) ranks second — and for a *relegation* reason, not a title one. That is
the feature working: **leverage is not prestige**, and a reader would never have found Mirassol v
Remo on their own. That is the thing worth selling.

### The problem the prototype exposed

Run it globally and the board is dominated by leagues nobody asked about:

| fixture | leverage |
|---|---:|
| GV San José v Universitario de Vinto (Bolivia) | 35.31 |
| Cerro v Racing Montevideo (Uruguay) | 32.29 |
| Utah Royals v Washington Spirit (NWSL) | 18.85 |

Raw leverage systematically over-rewards **small, volatile, few-games-remaining leagues**. A
16-team Bolivian table with 30 games left genuinely does swing 33pp on one result; a 20-team
Premier League in August does not. Left as-is, a Premier League subscriber opens the hub and sees a
Bolivian relegation six-pointer.

This is a ranking problem, not a metric problem — the metric is correct, it is just answering
"where is the table most volatile" rather than "what should *I* watch."

### Proposed shape

Three rails rather than one list. Each answers a different question and only the third uses raw
leverage:

1. **Your matches** — favourite teams and leagues, ordered by leverage *within* that set. This is
   the retention rail (see §2); it is personal, so it is never empty and never irrelevant.
2. **Biggest swing in your leagues** — leverage normalised *within league* (percentile, not raw),
   so a big-five fixture can compete with a volatile small league.
3. **Around the world** — raw global leverage, explicitly framed as the exotic rail. Cap it at 3–5
   and label it. Someone opening this rail *wants* the Bolivian relegation fight.

Copy should always state the consequence, never the score: "Mirassol's survival odds move 16 points
on this result" beats "high-leverage fixture."

### Open questions before building

- **Bucket weights** (`BUCKET_WEIGHT` in the prototype) are opening priors. Title and relegation at
  1.0, continental places lower. These should be set from engagement data, not taste.
- **Two-club scope.** Leverage currently sums over the two clubs playing. A title six-pointer also
  moves *third parties* — arguably the most interesting case ("this match decides someone else's
  season"). Extending the sum to all clubs is a one-line change and probably a better metric; it
  needs a look at whether it makes the board harder to explain.
- **Kickoff-time awareness.** "Today" is timezone-dependent; the payload carries dates, not times.
- The `champ_playoff` bucket is approximated in the prototype (top seed only). Fine for ranking,
  wrong for display — reuse `_championship_winner` if the number is ever shown.

---

## 2. Retention for Intel subscribers

The stated problem is right: **odds do not move much week to week, so a product whose only artifact
is a probability has nothing to say on most days.** Simulation is a *purchase* trigger, not a habit
trigger. Everything below converts a static number into a recurring event.

Ordered by (my estimate of) habit value against build cost.

### Tier 1 — daily reasons to open

1. **Matches to Watch** (§1). The canonical daily artifact. Different every day *by construction*,
   because the fixture list changes even when the model does not.
2. **"What changed while you were away."** Not a number, a *diff*: which of your clubs' outcome
   probabilities moved most since your last visit, and the match that caused it. The data already
   exists — `data/race_deltas_history.parquet` and `build_race_deltas.py` compute per-race deltas,
   and `movers.js` ships a movers strip. It is not personalised and not framed as a since-you-left
   digest. That reframing is most of the feature.
3. **Pre-match "what's at stake" card** for followed clubs, posted the morning of a match: the three
   conditional tables (win/draw/loss) side by side. This is the single highest-value use of the
   conditional sim — it turns "we have a model" into "here is what tonight means."

### Tier 2 — weekly rhythm

4. **Result post-mortem.** After a club plays: predicted vs actual, and what it cost or bought in
   the table. Closes the loop the pre-match card opens. `postgame_win_expectancy.py` already exists.
5. **Model accountability page, personalised.** "Your clubs: we were right about X, wrong about Y."
   Trust is the product's differentiator against tipsters; showing misses builds more of it than
   showing hits. `perf_by_year` and `in_season_brier` are already in every payload.
6. **Streaks and milestones** — "Palmeiras' title odds have risen 9 straight builds." Trend beats
   level for engagement, and trend is derivable from history already stored.

### Tier 3 — identity and habit-forming

7. **Season-long prediction game.** Let users lock a preseason table, score it against the model and
   against other users with Brier. This is the strongest retention mechanic available: it creates a
   *personal stake that decays if ignored*, which is precisely what a probability lacks.
8. **Club-page notifications** on threshold crossings ("first time above 50% for the title"), not on
   a schedule. Event-driven beats cadence-driven — it is never noise.
9. **Rivalry / mini-league tables** among friends, seeded from favourites.

### What I would not build

- More leagues. Coverage is already 78 and it is not the retention constraint.
- Daily model retraining to manufacture movement. It would be dishonest volatility, and it directly
  contradicts the calibration work the project has done.

### The honest framing

A forecast product's retention comes from **narrative, accountability, and stake** — not from the
forecast. Items 1, 3, 5 and 7 are the ones that create a reason to return on a Tuesday in February.

---

## 3. Marketing in Europe — deep dive

### Verdict up front

**Do not lead with the betting-edge positioning in Europe.** The core product hook — edge %, Kelly
staking, a paper bet ledger — is the single hardest thing to market in exactly the largest markets,
and in Italy it is close to unmarketable. Lead with *forecasting and analysis*; keep the betting
layer as a logged-in feature for users who sought it out.

### Why: the regulatory picture is the binding constraint

| market | position | what it means for us |
|---|---|---|
| **Italy** | Decreto Dignità: near-total ban on gambling advertising and sponsorship. Affiliate marketing prohibited; influencer/celebrity promotion treated as promotional communication. | A betting-framed product effectively cannot be marketed. Analytics framing only. |
| **Spain** | Broadcast ads confined to 01:00–05:00; sports sponsorship banned; restrictions apply to affiliates and PPC alike, not just operators. Tighter youth-targeting controls arriving 2026. | Paid acquisition on a betting frame is impractical. |
| **Germany** | GlüStV 2021; 21:00–06:00 window for slot/poker advertising, strict content rules. | Workable but constrained; analytics framing far safer. |
| **UK / Netherlands / Malta** | Regulated; affiliates held to the same advertising standards as operators — responsible-gambling messaging, accurate terms, licensed branding. | Viable *if* we accept operator-grade compliance obligations. |
| **cross-border** | Austria, France, Germany, GB, Italy, Portugal and Spain have formed a joint enforcement coalition explicitly targeting social, video and **affiliate networks**. | Enforcement risk is rising, not falling. Do not build the plan on affiliate arbitrage. |

The through-line: European regulators are converging on treating anyone who promotes betting as if
they were an operator. A small subscription product cannot carry operator-grade compliance in seven
jurisdictions.

### The competitive picture makes the same argument

The free tier in Europe is genuinely strong and entrenched:

- **FBref** — free, no registration, StatsBomb-powered, 40+ leagues, 194k+ players.
- **Understat** — free, the reference for xG and shot quality across the top five leagues.
- **Opta Analyst (Stats Perform)** — free, editorial plus "Opta Supercomputer" forecasts, **1M+
  monthly visitors**, with dedicated hubs for all big-five leagues.

Reporting on premium stats sites is blunt: they are worth the cost mainly to high-volume bettors
(£5,000+ monthly turnover) or syndicates. That is a narrow, hard-to-reach, compliance-heavy segment
— and it is the segment the current positioning targets.

### Where the actual opening is: breadth

Opta and Understat go **deep on the big five**. This product goes **wide**: 78 competitions
including English tiers 3–5, Scottish tiers 1–4, eight women's leagues, all of Central and South
America, and continental cups — each with a calibrated forecast, a published Brier score, and an
honest `rules` string describing what is and is not modelled.

Nobody serious is serving a Scottish League Two or Eerste Divisie or Liga F follower with a
calibrated table forecast. That is a real differentiator and it is *legal to advertise everywhere*.

### Recommended sequencing

1. **UK first.** Shared language, the deepest lower-league culture in the world (EFL, National
   League), and our tier 2–5 coverage is a genuine gap in the market. Regulated and navigable if we
   keep the public framing analytical.
2. **Netherlands / Nordics second.** High English proficiency (localisation is a *marketing* cost,
   not a product one, at first), strong analytics culture, Eredivisie + Eerste Divisie + Allsvenskan
   + Eliteserien + Superliga already covered.
3. **Germany third.** Large market, 2.Bundesliga covered, workable rules under an analytics frame.
4. **Italy and Spain last, and analytics-only.** Serie A/B and La Liga/Segunda are covered and the
   audience is large, but nothing in the funnel may reference betting.

### What has to change before any of it

- **A betting-free public surface.** Landing pages, share cards, RSS and the OG images must be
  presentable with zero edge/odds/staking language. Today the front door leads with market-facing
  framing.
- **Pricing.** $5.99/$7.99 is a US anchor. Test EUR/GBP pricing at local psychological points, and
  expect a lower willingness to pay where a strong free tier exists.
- **Language.** Start English-only, but the *league names* should localise before the UI does — a
  Spanish user searching "Segunda División" should land on the right page. Cheap, high SEO leverage.
- **VAT / consumer law.** EU digital-services VAT (MOSS/OSS) and a 14-day statutory withdrawal
  right apply to consumer subscriptions. Worth confirming with the existing Stripe setup before
  taking EU money at volume.

### What I could not determine

Traffic, conversion and willingness-to-pay figures for the closest comparables are not public. The
sequencing above rests on regulatory and competitive structure, which is well documented, not on
market-size estimates, which I could not source. Treat market sizing as an open question.

---

## 4. Updating the site more often

**Verdict: yes — 15–30 minutes is achievable, and the blocker is not what it looks like.**

### What actually costs the time (profiled 2026-07-26)

A single league build was 67s. Almost none of it was the thing that "updating" implies:

| stage | share |
|---|---|
| `walk_forward_predictions` — **retraining the model** | 84% (83s of 98s under profiler) |
| — Dixon-Coles predict | ~54s |
| — XGBoost refit (7 fits × 5-seed bag) | ~31s |
| Monte-Carlo season simulation | negligible |

The tell: **20,000 sims and 2,000 sims both took 67s.** The projection is nearly free. The build
re-fits the entire model from scratch every single time, which is only necessary when new *results*
arrive.

### Already fixed this session

`_dc_predict` ran an 81-cell Python loop making two `scipy.stats.poisson.pmf` **scalar** calls per
cell — 162 per match, ~1.9M per league build. The same file's `_dc_nll` had already been vectorised
for exactly this reason, with a comment noting "~500× faster"; the predict path was missed.
Rewrote it as a closed-form outer product with the Dixon-Coles τ patched into the low-score 2×2
block, plus removed three redundant identical `dc_predict_batch(cal, …)` calls.

**67.2s → 40.4s (−40%), output bit-identical** (max abs difference 2.2e-16, and every `perf_by_year`
Brier unchanged). 1,471 tests pass.

### The architecture for frequent updates

Split the build in two. This is the real unlock:

- **Slow path (daily, unchanged).** Refit DC + XGB, recalibrate, recompute ELO. Persist the fitted
  artifacts *and the fixture probability matrix* alongside the payload.
- **Fast path (every 15–30 min).** Load the cached probability matrix, refresh results and kickoff
  times from the fixture feed, update `base_pts`/`base_gd`, re-run the Monte Carlo, rewrite the
  payload. No refit, no model load. Based on the profile this is **seconds per league**, and the
  leverage prototype in §1 — which is exactly this shape of computation — does all 78 leagues in 8s.

A fast path is also *more correct* than a frequent full rebuild would be: refitting the model every
20 minutes would inject fit noise into published probabilities and undo the calibration work.

### What genuinely constrains cadence

1. **Upstream feeds.** ESPN scoreboard data is the real clock. Polling every 15 minutes is fine
   during match windows and pointless at 04:00. Schedule against the fixture calendar —
   `build_calendar.py` already knows when matches are.
2. **The Odds API.** Free tier is 500 requests/month; `config/settings.yaml` records that MLS
   openers + closers alone are ~60/month and enabling all filed leagues at *daily* cadence is ~390.
   **Sub-daily odds refresh requires a paid key** — this is the one hard cost. Model probabilities
   have no such limit; decouple the two so the fast path never touches odds.
3. **Deploy, not compute.** Every refresh triggers `deploy.yml` → rebuild static pages → upload the
   whole `webapp/` artifact → GitHub Pages. At 15-minute cadence that is ~96 deploys/day of a
   largely unchanged site, plus a service-worker cache-version bump each time, which forces every
   returning visitor to re-download the shell. **This is the binding constraint, not the model.**
4. **Git history.** A commit per refresh at 15-minute cadence is ~35k commits/year of binary
   payloads.

### Recommendation

- **Tonight:** keep the daily full rebuild. It is now 40% cheaper.
- **Next:** build the fast path, and have it write payloads **without** triggering a full site
  deploy — serve the data files from a small object store or a data-only branch the page fetches at
  runtime, so the shell deploy stays daily and the numbers go live in minutes. This sidesteps
  constraints 3 and 4 entirely.
- **Cadence:** 15 minutes during a league's match window, hourly otherwise, driven by
  `build_calendar.py`. Do not poll uniformly.
- **Odds:** leave daily until a paid key is justified by paying users, and make the UI honest about
  the two clocks — "model updated 12 minutes ago · market prices 6 hours ago."

---

## Sources (§3)

- [World Cup 2026 pushes European gambling ad rules — European Gaming](https://europeangaming.eu/portal/latest-news/2026/05/25/205188/world-cup-2026-pushes-european-gambling-ad-rules-belgium-netherlands-and-france-warn-operators/)
- [iGaming Regulations Across the EU — complete 2026 guide](https://irev.com/blog/igaming-regulations-across-the-eu-a-complete-guide-in-2025/)
- [iGaming regulation in the EU — Voluum](https://voluum.com/blog/igaming-eu-regulations/)
- [European regulators join forces to combat illegal online gambling — DLA Piper](https://www.dlapiper.com/en/insights/blogs/mse-today/2026/european-regulators-join-forces-to-combat-illegal-online-gambling)
- [Affiliate marketing trends: where is iGaming promotion legal in Europe — SOFTSWISS](https://www.softswiss.com/news/affiliate-marketing-trends-igaming-promotion-europe/)
- [Major European markets tighten iGaming laws — EU Reporter](https://www.eureporter.co/general/2026/04/29/major-european-markets-tighten-igaming-laws-what-to-expect-in-2026/)
- [Opta Analyst — Stats Perform](https://www.statsperform.com/about/opta-analyst/)
- [Opta Analyst](https://theanalyst.com/)
- [Best xG websites 2026 compared](https://statpair.com/blog/best-xg-websites-2026-comparison)
- [Best football statistics websites for betting 2026](https://www.mrsupertips.com/guides/best-football-statistics-websites)
