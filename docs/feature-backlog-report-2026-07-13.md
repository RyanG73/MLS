# Feature backlog report — 2026-07-13

Recommendations for the open-question items from the 2026-07-13 feedback round.
The build-now items from that same round (masthead reorder, South America icon,
qualify-line labels, power-rankings fix, contact page, home page Recent Results +
Movers board, Matches-tab day calendar) shipped directly — see commit history and
`docs/PLAN.md`. This doc covers only the items that need a decision before work
starts.

---

## 1. RSS-in tactical-breakdown articles ("intelligent analysis")

**Current state:** `scripts/build_news.py` already does exactly this pattern —
8 curated RSS feeds (The Athletic, Guardian, BBC, Sky, Football Italia, GFFN, DW,
Football España) fetched server-side at build time (RSS is CORS-blocked in-browser,
so client-side fetching isn't an option), keyword-routed to the league they
mention, with a gossip-keyword filter (`GOSSIP` regex) that already drops
transfer-rumour churn.

**Recommendation:** Extend the existing pipeline rather than build a new one —
add tactical-analysis-leaning feeds (Statsbomb's blog, Tifo Football's written
pieces if they publish RSS, spielverlagerung.com, Analytics FC) to the `FEEDS`
list, and add a second filter mirroring `GOSSIP` but inverted — an
`ANALYSIS_SIGNAL` regex (`tactical|shape|press|build-up|xG breakdown|analysis`)
that can tag/boost these items so they can be surfaced in their own "Tactical
Reads" rail distinct from general news. Effort: small (~1-2 hours), same script.

## 2. RSS for podcasts / YouTube channels

**Current state:** No podcast/video ingestion exists today.

**Recommendation:** Feasible with the same architecture. Nearly every major
football podcast (The Athletic Football Podcast, Football Weekly, Tifo) publishes
a standard podcast RSS feed with episode title/description/link/pubDate — this
is a straight extension of `build_news.py`'s existing XML-RSS parser, just a
different `FEEDS` list and a `type: "podcast"` tag so the client can render a
distinct "Listen" rail with episode art if the feed carries `<itunes:image>`.
YouTube channels also expose an RSS feed at
`https://www.youtube.com/feeds/videos.xml?channel_id=<id>` (no API key needed),
same parser, same pattern. Effort: small-medium — mostly picking a curated
channel/podcast list, which is an editorial decision more than an engineering one.

## 3. RSS for social media

**Current state:** None.

**Recommendation:** This is the one with real friction. Twitter/X killed free
RSS access years ago — there's no legitimate no-cost feed anymore, only paid
API tiers or third-party scraping proxies (fragile, ToS-risk). Bluesky and
Mastodon both expose real RSS/AT-Proto feeds for public accounts at no cost, so
if the goal is "surface what named accounts are saying," that's buildable today
for those platforms only. **Recommendation: skip X/Twitter, ship Bluesky/Mastodon
RSS using the same `build_news.py` pattern if there are analysts worth
following on those platforms; otherwise deprioritize this one** — the
value is lower than #1/#2 and the X gap makes it a partial feature either way.

## 4. Ad space

**Recommendation:** Reserve, don't build yet. The layout already uses CSS Grid
areas (`.ed-wrap`, `grid-template-areas`) that make inserting an ad slot later
low-risk — e.g. a `.ga-ad` area between `stories` and `movers` on the home page,
or a right-rail unit under `.ga-models`. Concretely: pick placements now (home
mid-feed, league-page sidebar, between Matches-tab panels), but don't wire an ad
network until there's traffic worth monetizing — most networks (AdSense, Ezoic)
have minimum-traffic gates anyway. The betting-adjacent content also needs care:
`docs/PLAN.md`'s responsible-gambling stance (no sportsbook affiliate links,
Privacy page explicitly says "There are no sportsbook affiliate links on this
site") should stay true even with generic display ads — don't let an ad network
backfill sportsbook creative without a policy decision first.

## 5. Subscription model

**Recommendation:** This is a product/business decision more than an engineering
one, but the technical path: this is a static site with no backend and no user
accounts today (`Privacy` page: "does not require an account"). A subscription
needs three new pieces regardless of provider — (a) auth/accounts, (b) payment
processing, (c) a gate that gives paying users something free users don't get.
Cheapest real path: **Stripe Checkout + Stripe Customer Portal** (hosted, no
PCI burden) paired with a lightweight auth layer (Clerk or Supabase Auth both
have generous free tiers) — this still means standing up *some* backend
(even just Vercel/Cloudflare serverless functions) since a pure static site
can't verify a paid session. Before building anything: decide what's actually
gated — more likely candidates given what exists are the paper-ledger/edge-board
depth, the calibration/model-health detail, or an ad-free tier, not the core
projections (those are the product's credibility engine and gating them would
undercut the "transparent, market-blind" positioning).

## 6. Mobile app packaging

**Current state:** The mobile web experience is already close to app-shell —
there's a bottom tab bar (Home/Matches/Leagues/Favorites, visible in the mobile
screenshot), favorites persist in localStorage, and the layout is
already responsive-first.

**Recommendation:** Don't build a native app yet — wrap it as a **PWA**
(Progressive Web App) first, which gets ~80% of "feels like an app" for a few
hours of work: a `manifest.json` (name, icons, theme color, `display:
"standalone"`), a minimal service worker for offline-shell caching, and an
"Add to Home Screen" prompt. That alone gives a home-screen icon, no browser
chrome, and app-switcher presence on both iOS and Android — no App Store
review, no Apple Developer fee, no React Native rewrite. Only reach for a real
native/React Native wrapper (or Capacitor, which wraps the *existing* web app
in a native shell with minimal rewrite) if push notifications or App Store
discoverability specifically become a goal — PWAs can't do push on iOS Safari
as of this writing.

## 7. Other leagues addable as projection-only

**Current state:** Live leagues use two result-history adapters —
`data_pipeline/football_data.py` (per-season-file format, England's tiers) and
`data_pipeline/football_data_intl.py` (one-CSV-per-country format, used for the
2026-07-10 expansion: Brazil, Japan, Sweden, Norway, Denmark, Poland,
Argentina). ESPN supplies every upcoming schedule. Both adapters are
results-only.

**Recommendation:** Check `football-data.co.uk`'s and `football-data_intl`'s
country coverage list for leagues not yet onboarded — from the existing
adapter's supported set, likely near-term candidates are additional South
American top flights (Chile, Colombia, Uruguay, Peru — Primera División each),
more Asian leagues (K League 1 South Korea, Thai League), and a few more
second-tier European leagues (2. Bundesliga is already in, so France's Ligue 2
tier peers like Eredivisie's Eerste Divisie). Each addition is mechanically the
same as the 2026-07-10 expansion (`docs/league-expansion-report.md` is the
template) — the binary constraint each time is "does ESPN have a confirmed
schedule slug for it" (`NO_ESPN_SCHEDULE` in `football_data_intl.py` already
flags Poland as results-only for exactly this reason). Recommend running the
same feasibility check script used for round 4 against a candidate list before
committing to specific leagues.

## 8. Better way to show Brier scores

**Current state:** The About page already states the honest framing in prose
("We do not claim to beat the market... typically trails by a couple of percent
on aggregate Brier") but it's buried in a callout box after a metrics table of
raw numbers (0.593, 0.615, 0.625...) that mean nothing to a non-technical
reader on first glance.

**Recommendation:** Lead with a relative, not absolute, framing — a simple
horizontal scale showing **Random guess → This model → Sharp market**, with the
model's position plotted between the two anchors (it's genuinely most of the
way from random to market, which is the actual selling point) rather than a
bare decimal table. Concretely: keep the raw Brier numbers (transparency
matters, don't hide them) but demote them to a hover/expand detail, and
promote a single sentence + visual like *"On a scale from random guessing to
the closing market line, this model captures about 82% of the gap"* — computed
as `(naive_brier - model_brier) / (naive_brier - market_brier)` per family,
which is exactly the kind of number this codebase already computes
(`improvement_pct` exists; a symmetric `market_capture_pct` is the same math
with the market as the second anchor). This is a good `data:data-visualization`
or `dataviz` skill task when it's greenlit — it's explicitly a "how do I show
this data honestly and legibly" problem.

## 9. Momentum-chart integration ([JakeBonnici22/match-momentum](https://github.com/JakeBonnici22/match-momentum))

**What it actually needs:** I checked the repo. It's a standalone Python script
(NumPy/Matplotlib/SciPy) that takes **event-level match data** — shots, chances,
goals with timestamps — and computes momentum via exponential decay (≈3-minute
half-life) per event, then Gaussian-smooths the two teams' curves into the
familiar broadcast-style "who's on top" chart. The author's own note: swap in a
real event feed and "the pipeline works unchanged."

**The gap:** this codebase does not currently have event-level shot data
anywhere. `data_pipeline/understat.py` pulls Understat's **season-aggregate**
per-match goals+xG only (confirmed by reading the module — no minute/shot
fields extracted), not the shot-by-shot data Understat's own match pages
actually carry. American Soccer Analysis's MLS/NWSL/USL feed is match-level
too.

**Recommendation:** This is buildable but is a two-part project, not a
port: (1) a new ingestion module pulling Understat's per-match shot data
(minute, xG, player, situation) for the Big-5 leagues only — Understat doesn't
cover MLS/NWSL/lower leagues, so this would ship for a subset of leagues, not
site-wide; (2) port the exponential-decay+Gaussian-smoothing math to either a
build-time SVG/PNG generator (simplest, matches the original script's design)
or a small client-side JS function if you want it interactive. Scope this as
its own plan once there's appetite — it's a genuinely nice "game story" feature
for completed Big-5 matches, but it's new-data-source work, not a weekend
UI add.

## 10. Postgame win-expectancy model (Bill Connelly style)

**What this means concretely:** given the actual in-game process stats (shots,
xG, box scores), compute what a team's win probability *should have been* based
on the balance of play — so a 1-0 win on one shot reads as "10% postgame WE,
got lucky" rather than the boxscore's flat binary result. Connelly's college
football version blends expected points added per play into a
possession-by-possession win-probability model.

**Recommendation:** This is real modeling work, not a display tweak, and per
`CLAUDE.md` model changes go through `scripts/eval_baseline.py` and get
A/B-validated before touching production — don't hand-wave a number onto the
results feed. A reasonable first-pass approach: a **postgame logistic
regression** (or simple hand-tuned formula, given a smaller dataset than
Connelly's) on shot- and xG-differential-weighted features (total xG for/against,
shot quality, not just shot count) fit against actual match outcomes, output as
a single 0-100% number per completed match, framed clearly as *"how deserved
was this result"* rather than a prediction (the match already happened). This
needs the same event/shot-level data gap noted in #9 to do well — box-score xG
alone (which the pipeline has today) gets you partway (an xG-differential-based
postgame WE is legitimate and buildable now), but a true shot-quality-weighted
version wants the same Understat shot-level ingestion. Recommend scoping this
as a `model-architect` agent task once prioritized, likely starting from the
xG-only version as an MVP.

## 11 & 12. Transfer-value modeling (contract + age adjusted) and transfer-window spend/earnings

**Current state:** Transfermarkt squad values are already ingested as
**team-level aggregates** (per the Data & Attribution page: "shown only as
team-level aggregates with attribution; individual player valuations stay
local-only") — meaning player-level contract length, age curves, and individual
valuations exist locally but aren't currently modeled as a feature, and
transfer-window spend/earnings isn't tracked at all today.

**Recommendation, #11 (contract+age adjusted value):** Legitimate idea —
Transfermarkt's own valuation already implicitly factors contract length and
age into their number, so "remodel value from scratch" is really "extract
Transfermarkt's contract-remaining and age fields (both are on their player
pages) and use them as *separate* features alongside raw value," rather than
building a whole new valuation model — that's both less work and more
defensible than re-deriving a market value estimate independently. Frame it as
two new features (`contract_years_remaining`, `age`) that interact with
existing squad-value features, not a new "value model."

**Recommendation, #12 (transfer spend/earnings):** Needs a new data pull —
Transfermarkt does publish transfer history per club (in/out, fees) but it's
not currently scraped here. This is a clean, scoped feature-engineering
candidate: net transfer spend over the last 1-2 windows as a team-strength
signal, tested the same way every other feature candidate in this repo is
(`docs/feature-hunt-log.md` is the existing rejection/acceptance log — this
should go through that process, not ship straight to production). Both #11 and
#12 belong with the `feature-engineer` agent against `scripts/eval_baseline.py`
per this repo's existing experiment protocol — they're promising but unproven,
exactly what that harness exists to test before either gets near the champion
model.

## 13. Comprehensive UEFA phase coverage (draws, pots, qualifying, league phase, knockout)

**Current state:** `scripts/build_continental_data.py` models the knockout
bracket (`_isKnockout`, `renderKnockout()`, seeds through to a champion) and the
36-team league phase table (`renderKnockout` at line ~1745 handles the
"Auto-advance line (top 8)" / "Knockout-playoff line (top 24)" dividers already
seen in this session's standings-label fix). Qualifying rounds and the actual
draw/pot mechanics are not modeled — the competition is picked up already
in-progress.

**Recommendation:** This is the largest single item in the whole list — UEFA's
real format has real structure to reproduce: 4 qualifying paths (Champions Path
vs League Path, itself branching by coefficient), pot allocation for the league
phase draw (4 pots of 9, Swiss-style pairing constraints — no two teams from
the same country, exactly 2 opponents per pot), then the 36-team league table,
then a knockout-phase play-off round (17-24 vs 9-16) before the round of 16.
Suggest scoping this as its own plan with three separable phases rather than
one big build: **(a)** qualifying-round tracking (lowest effort, mostly a data
question — does a results source cover them), **(b)** a draw/pot simulator for
before the league-phase fixtures are known (highest complexity — real
constraint-satisfaction, not just a random draw), **(c)** the
qualification-scenario detail already partially built for the league phase
(extend the existing bracket simulator's per-team "path to X" framing back to
mid-league-phase uncertainty). (b) is the one worth scrutinizing hardest before
committing — it's a genuinely hard combinatorial problem for a website feature,
and the value (a nice "watch the pots" moment once a year) is narrower than
(a)/(c)'s year-round payoff.
