# API-Football as the data foundation — execution spec

**As of:** 2026-08-08 · **Owner:** Ryan · **Author:** Claude
**Status:** for execution in a fresh session. All owner decisions are recorded (§9); nothing below
blocks on an owner answer. Stages 0–2 run on zero requests and the free key; **the paid plan is not
yet purchased** — it is bought at the §7 checkpoint, after the infrastructure is proven.
**Supersedes the phase-3 section of** [`2026-08-08-match-data-source-resilience-design.md`](2026-08-08-match-data-source-resilience-design.md);
phases 1, 2 and 4 of that document are shipped or still stand.

Owner brief, 2026-08-08: *"consider how we would do this if we were building the site from scratch.
I don't want to use this api as just a band aid… we should be using it as foundational information
that consistently supports our website… It is critical that the site doesn't lose anything we
already have, but we should look at ways we can grow the site."*

---

## 1. The design if we were starting today

Entenser's data layer grew by accretion: a league was added, whichever free source happened to carry
it became that league's source, and its capabilities became that league's ceiling. The result is not
a design. It is six adapters, **five different capability profiles**, and a model whose feature set
silently varies by which website had a CSV.

Built from scratch with this API available, the shape is different:

> **One spine, several specialists.** API-Football supplies the universal layer for every
> competition — fixtures, results, squads, lineups, events, standings, and the catalogue that lets
> new leagues be added without new code. Specialist sources stay *only* where they are demonstrably
> better than the spine at something the product depends on.

Two properties follow, and both are things the current design cannot offer:

- **Uniform capability.** Every league gets the same feature families, so the model stops varying by
  accident of sourcing. Today MLS runs 34 features and all 69 others run 31 — a difference nobody
  chose.
- **Expansion is configuration.** Adding a competition becomes a row in a mapping file, not a new
  adapter, a new parser, and a new set of quirks.

This spec is therefore not "swap a source". It is **make one source foundational, keep the
specialists that earn their place, and use the headroom to grow.**

---

## 2. What the site has today — the "lose nothing" baseline

This is the contract. Anything below that regresses is a failed migration, regardless of what
is gained.

| Surface | Today's source | After |
|---|---|---|
| Results + fixtures, 70 leagues / 78 competitions | ESPN 30, football-data 17, intl 14, understat 5, ASA 2, API-F 2 | **API-Football spine**, specialists retained where required |
| **xG (model input: 18 of 31 feature columns)** | understat (5), ASA (2) | **understat/ASA retained** unless `/statistics` xG matches them match-for-match |
| **Pinnacle closing 1X2 (value layer, paper ledger)** | football-data + intl (31) | **retained** — the `/odds` comparison is deferred (§3.1) |
| Goalkeeper z-score (3 cols, **MLS only**) | ASA | retained; all-league extension via lineups is **deferred** (§3.1) |
| Squad values | Transfermarkt | unchanged |
| ELO, projections, bridges, Global ELO | derived in-repo | unchanged |
| Continental competitions (8) | ESPN | API-Football spine |
| Trophies, trust, model card, provenance | derived in-repo | unchanged |

**Three hard non-negotiables**, each already load-bearing:

1. **xG windows (3/5/10/15) are champion features.** `CLAUDE.md` fixes them; `health.features` shows
   18 of 31 columns are xG rolling. A thinner xG series is a model regression, not a data swap.
2. **Pinnacle closing is the benchmark the paper ledger is scored against.** Switching book or
   switching closing→opening makes historical edge figures incomparable with future ones.
3. **Training history is 2017+, 2020 excluded.** A source that cannot reach 2017 for a league cannot
   be that league's primary without discarding model history.

---

## 3. What the spine offers that we have never used

From the plan's own feature list. We call exactly one of these.

| Capability | Used today | Status | What it would unlock |
|---|---|---|---|
| Fixtures | ✅ (2 leagues) | **the spine** | — |
| **Statistics** | ❌ | **this migration** | xG for the **63 leagues that have none**, shots, possession |
| **Pre-match odds** | ❌ | deferred (§3.1) | market benchmark for the **39 leagues with no odds at all** |
| **Lineups** | ❌ | deferred (§3.1) | goalkeeper quality for **all** leagues, not just MLS; confirmed XI |
| **Injuries / players** | ❌ | deferred (§3.1) | availability — a feature family the model defines but only MLS can fill |
| **Events** | ❌ | deferred (§3.1) | goal times, cards, subs — match narrative for Club Watch |
| **Livescore** | ❌ | roadmap (§3.1) | live match state |
| **Head-to-head** | ❌ | free with fixtures | a modelling input the repo has never had |
| **Standings** | ❌ | cheap, optional | independent cross-check against our computed tables |
| **Leagues / countries catalogue** | ❌ | **Tier D** | expansion without bespoke research per league |
| Transfers | ❌ | not planned | squad churn beside Transfermarkt values |

**The largest single prize is xG coverage.** 18 of 31 model feature columns are xG rolling windows,
and only 7 of 70 leagues have a real xG source. The other 63 run the same model with its most
numerous feature family empty. That prize — statistics — is the one per-fixture capability this
migration takes. The rest are deliberately parked:

### 3.1 Deferred — future modeling and product options (owner decision, 2026-08-08)

Not rejected; parked, each with the condition that would revive it:

- **Live scores** — the owner's call: they change the product's *character*, not its accuracy.
  Roadmap idea for later: watching live match state move season-long odds in the table.
- **Lineups** — would extend the MLS-only goalkeeper z-score to every league and open the
  availability feature family. Revive as a gated model experiment with a Brier comparison, never as
  a plumbing side effect (invariant 4).
- **Odds (`/odds`)** — unusable until proven to be the same measurement as Pinnacle closing; that
  comparison is itself the deferred work. Until then, football-data keeps the odds column
  everywhere it holds it today.
- **Events** — goal times, cards, subs. Club Watch narrative, not model input.

One nuance the live-scores decision exposes: **declining live scores does not mean keeping the ESPN
fast-refresh loop.** Same-day result updates come from the ordinary `/fixtures` endpoint at ~1
request per league per poll (~70 per cycle), so the spine still replaces fast-refresh's ESPN
dependency as part of Tier A. Only true in-match live state is deferred.

---

## 4. Request budget and plan economics

### 4.1 Plans and terms — verified 2026-08-08

Source: owner screenshot of the 1-month pricing page plus the pasted "How it works" terms — the
measured facts the earlier draft could not confirm (the pricing page 403s automated fetches).

| Plan | $/month | Requests/day | Rate limit | Seats |
|---|---|---|---|---|
| Free | 0 | 100 | 10 r/m | — |
| Pro | 19 | 7,500 | 300 r/m | 1 |
| Ultra | 29 | 75,000 | 450 r/m | 2 |
| **Mega** | **39** | **150,000** | **900 r/m** | 3 |

All paid plans include all competitions and all endpoints. There is **no overage billing** — the
daily cap is hard. The quota resets at 00:00 UTC and unused requests are lost, so a backfill
scheduler should straddle the reset to use whole days. 3/6/12-month terms exist (presumably
discounted; unverified).

**Purchase strategy (owner decision, 2026-08-08): Mega for month 1, then Pro month-to-month.** The
backfill runs inside the Mega month; steady state (~50–150/day) never approaches even Pro's cap.
Month-to-month holds until site traffic justifies a longer term. **There is no automatic renewal**,
which makes plan-hopping legitimate by design — and creates the lapse risk below. Nothing is
purchased yet: the buy happens at the §7 checkpoint.

**Lapse risk.** An expired subscription silently reverts to Free — 100 requests/day and, decisively,
**seasons capped at 2024**: every league's current season would quietly stop updating. Two guards:
the budget governor asserts the active plan from the rate-limit response headers on every call and
**fails loud** the moment they show Free-tier quotas (§6.4), and a renewal reminder lands before
each expiry.

**Firewall clause → throttle policy.** The terms reserve the right to block accounts, temporarily or
permanently and without notice, for "significantly exceeding rate limits or abnormal traffic
spikes". All bulk jobs therefore run at **≤~50% of the plan's per-minute limit, smoothed, never
bursting**. On Mega that is ~450 r/m — the full 150k/day is spendable in ~5.5 hours — so pacing the
backfill across the day costs nothing and never looks like a spike.

### 4.2 The two cost shapes

Two very different cost shapes sit underneath the daily cap.

#### Per-league endpoints — negligible
`_fetch_league` already caches per `(league, season)` and refetches only the latest season, so a
league costs **1 request per refresh**. A cached 232-fixture season returned `paging {current: 1,
total: 1}` — unpaged at that size.

| Workload | Requests/day | % of cap |
|---|---|---|
| All 70 leagues, fixtures, daily | **70** | 0.9% |
| Standings for all 70, daily | 70 | 0.9% |
| One-time fixtures backfill, 70 × 9 seasons | 630 | 8.4% of one day |

#### Per-fixture endpoints — this is what the budget is for
Statistics — `/fixtures/statistics`, **one request per played match**, returning that match's stat
sheet (xG, shots, shots on target, possession, cards) — are keyed per fixture, as are lineups,
events and (probably) odds. Measured: **17,851 fixtures in one season** across built competitions.

**The backfill this spec commits to is statistics only** (owner decision, §9). Its scope, precisely:

- **Current 78 competitions only.** Expansion leagues (Tier D) are opted into separately and carry
  their own costs.
- **Not scores or fixtures** — those are already held; re-pulling nine seasons of fixtures for every
  league is only ~630 requests.
- **The 7 leagues with real xG (understat 5, ASA 2) are excluded.** Tier C keeps them as the xG
  source. They get only a **~400-request validation sample** (one league-season, compared
  match-for-match) — not a nine-season backfill. That removes ~2,400 fixtures/season.
- **The target is the 63 xG-less leagues** — where 18 of 31 model feature columns sit empty today —
  at ~15,400 fixtures/season.

| Workload | Requests | Pro (7.5k/day) | **Mega (150k/day)** |
|---|---|---|---|
| Statistics, one season, 63 target leagues | ~15,400 | 2.1 days | ~2.5 h of quota |
| Statistics, nine-season **ceiling** | ~139,000 | ~19 days | **inside 1 day's quota** |
| **Steady state — only newly played matches** | **~50–150/day** | ~2% | <0.1% |

The nine-season figure is a **ceiling, not a commitment**. Stage 1 measures which leagues and
seasons actually carry real xG; the job spends a request only where the stat sheet exists and feeds
a model feature, and stops at whatever depth the data runs out. *(Measured 2026-08-08: xG appears
from the 2023 season, so the realistic ceiling is ~46k — see Stage 1's answers in §7.)* The deferred families (lineups,
odds, events — §3.1) would add roughly another 300k *if* ever revived; they are no part of this
budget.

**The shape of the answer changed with the plan decision:** on Mega the entire ceiling fits inside
one to two days' quota, and the pace-setter is not the daily cap but the firewall-safe throttle
(§4.1). The job still runs **recent-first per league** (`XGB weight ½-life: 6 seasons` — value
arrives immediately), extending backward, and stays resumable (§6.5): a job that can finish in a day
must still survive being interrupted in the middle of it.

---

## 5. Migration tiers

**Tier A — move now, unconditional (30 leagues).** Currently ESPN. Measured: **0 of 30 carry xG, 0
carry odds.** They lose nothing and stand to gain xG now — plus lineups and availability if those
deferred families are ever revived (§3.1). This alone takes the site's most fragile source out of
the hot path.

**Tier B — fixtures/statistics from the spine; odds stay where they are (31 leagues).**
football-data + intl hold Pinnacle closing odds — the paper ledger's benchmark. Decision: take
API-Football for fixtures and statistics, and **football-data keeps the odds column, full stop**.
The `/odds`-vs-Pinnacle comparison is deferred (§3.1); until it is done and passes, no odds column
moves. A league may legitimately have two sources for two different columns — that is what the
canonical frame is for.

**Tier C — hold (7 leagues).** understat + ASA. They hold the only real xG in the platform and, for
MLS, the only goalkeeper data. These move last, if ever, and only against a match-for-match
comparison over a full season.

**Tier D — new coverage (owner: yes, from a menu).** The catalogue endpoint lists competitions we
do not carry. Expansion becomes a mapping row plus a build, at ~1 request/day each. **Coverage
growth is cheap; the limit is our bridge evidence, not requests** — an unbridged league can publish
a league page but cannot join Global ELO.

*Admission criteria* (owner decision, 2026-08-08 — every candidate must clear all of these):

1. **API-Football carries fixtures + results with enough history to seed a model** — ELO/DC needs
   several seasons; the projections-only precedent (Poland, Finland `results_only`) is the floor.
2. **An active, continuous schedule.** No long-dormant, ad-hoc, or sporadically contested
   competitions — the predictions layout has to have something to predict, year over year.
3. **A format the existing machinery can model** — the plain-table + honest `rules` caveat
   approximation (Denmark/Poland/Argentina precedent), not bespoke split-round modelling.
4. **Bridge evidence is optional but scoping:** without it a league publishes a page but stays out
   of Global ELO.

*Candidate menu* — grounded in `docs/league-expansion-report.md`, whose round-6 finding was that
**ESPN's catalog is exhausted**; the spine reopens that frontier. To be validated against the
`/leagues` catalogue in Stage 1 — this list is candidates, not measurements:

| Family | Candidates | Why now |
|---|---|---|
| Previously rejected on sourcing | 3. Liga (GER), Serie C (ITA), Championnat National (FRA), Primera Federación (ESP) | rejected as "not feasible with the current source stack" — exactly what the spine changes |
| European pyramids not carried | Czech First League, Croatia HNL, Serbia SuperLiga, Hungary NB I, Ukraine Premier | top flights with continuous schedules |
| Second tiers under carried leagues | Portugal Liga 2, Turkey 1. Lig, Belgium Challenger Pro, Norwegian/Swedish/Danish second divisions | tier-bridge ELO seeding from the parent league (Scottish precedent) |
| AFC | J2 League, K League 2, Qatar Stars League, UAE Pro League | active calendars; J2/K2 bridge to carried top flights |
| CAF | Egypt Premier League, Morocco Botola | South Africa PSL is CAF's only current entry |
| CONMEBOL / Concacaf tiers | CONMEBOL and Liga MX second tiers | as previously scoped |
| Women's | Frauen-Bundesliga, Serie A Femminile, Damallsvenskan, Liga MX Femenil | five women's competitions carried today |
| Continental cups | AFC Champions League, CAF Champions League | slugs already exist in `espn_continental.py`; blocker is confederation offset calibration, **not plumbing** — the spine does not change that |

The owner picks per the Stage-6 gate; the menu is the options, not the order.

---

## 6. Architecture

### 6.1 A source registry, not a source string
Today each league has `"source": "espn"` — one string, all-or-nothing. Replace with a per-capability
map, defaulting to the spine:

```
"epl": {"sources": {"fixtures":    ["api_football", "espn"],
                    "xg":          ["understat", "api_football"],
                    "odds":        ["football_data"],
                    "statistics":  ["api_football"]}}
```

This is the change that makes the API foundational rather than a band-aid: a league draws each
*column family* from whichever source is best for it, with an ordered fallback, instead of
inheriting one provider's whole capability profile.

### 6.2 Provenance is published per column family
A payload records which source answered for each family. Without it, two leagues disagreeing becomes
unexplainable, and a silent fallback becomes indistinguishable from a healthy build.

### 6.3 The canonical frame stays the contract
`understat._COLS` already is the interface and **all seven adapters already emit it** — which is why
this is a routing change rather than a rewrite. New families (lineups, availability) extend the
frame additively; nothing that exists changes shape.

### 6.4 Budget governor
- `_DAILY_BUDGET` for operations, **separate** from a backfill allowance, so a one-off can never eat
  the daily refresh's capacity.
- Counted from `data/source_health.parquet`, which already records every API-Football call — spend
  is a query, not a guess.
- **Fails closed**, like the payload-regression guard. A data path that silently keeps spending is
  how you find out from an invoice.
- Applies to exploratory and development calls too. Not exempting myself: I spent 4 requests on
  2026-08-08 looking up the Leagues Cup, and that should have been counted.
- **Asserts the plan from response headers.** Every API response carries the rate-limit headers; the
  governor checks them against the expected plan and **fails loud** when they show Free-tier quotas
  — the silent-lapse guard from §4.1. A lapse must look like an outage, never like a quiet
  regression to 2024 data.
- **Enforces the throttle**: bulk jobs at ≤~50% of the plan's per-minute limit, smoothed (§4.1's
  firewall clause).
- **Schedules around the 00:00 UTC reset** — quota is use-it-or-lose-it, so multi-day jobs straddle
  the reset to spend whole days.

### 6.5 Backfill is resumable and idempotent
No backfill assumes it runs to completion — even one that fits inside a Mega day (interruption,
throttling, a firewall block mid-flight). Per-fixture results cached to disk keyed by
fixture id; restart re-reads rather than re-requests; progress and spend both queryable mid-flight.

---

## 7. Stages

**Progress — Stage 0 complete, 2026-08-08, zero requests spent.** Shipped: budget governor
(`data_pipeline/api_budget.py` — separate fail-closed ops/backfill allowances, plan assertion from
response headers, ≤50% r/m throttle, spend counted from `source_health.parquet` since 00:00 UTC),
pagination (`_get_paged` follows `paging{current,total}`), source registry + router
(`data_pipeline/source_registry.py`, empty by default — no league's sourcing changed), and payload
`provenance` per column family via `build_league_data._routed_frame`. 34 tests; full suite 1975
passed / 0 failed.

**Stage 1 complete, 2026-08-08, 13 free-key requests.** The five questions are answered as
measured facts below; the league map is drafted 78/78 (`config/api_football_league_map.json`).
Headline: xG starts with the **2023 season**, so the statistics backfill ceiling drops from ~139k
to **~46k requests**; historical closing odds **do not exist** on this API.

**Map approved by owner; Stage 2 passed, 2026-08-08 (~6 requests, 19 total today).** Brasileirão
2022–2024 from the spine vs football-data: 1,140/1,140 scorelines agree, standings identical,
champion feature builder accepts the frame unmodified. Ten club-name pairs measured (the Stage-3
name-map seed); API-Football spellings drift across seasons (K-League problem, now confirmed
systemic). Next: build the resumable backfill job (§6.5, blind — the checkpoint requires it),
then declare **"infrastructure complete, ready to buy."**

| Stage | Requests | Gate | Output |
|---|---|---|---|
| **0 — Build blind** | **0** | none | registry, provenance, budget governor, pagination handling, all against fixtures |
| **1 — Map and probe** | ~10 | owner reviews mapping | committed league map; the five unknowns answered as measured facts |
| **2 — Validate on free key** | ~20 | none | one league builds end-to-end from the spine; payload compared column by column |
| **☑ Purchase checkpoint** | 0 | **owner buys Mega** | "infrastructure complete, ready to buy" — nothing beyond the free tier before this |
| **3 — Tier A migration** | ~30/day | Mega active | 30 leagues on the spine, ESPN as fallback |
| **4 — Statistics backfill** | metered, ~1–2 days on Mega | stage-1 quality proof | xG for the 63 leagues that have none — **statistics only** |
| **5 — Tier C validation sample** | ~400 | measured comparison | API-Football xG vs understat, match-for-match, one league-season |
| **6 — Tier D expansion** | ~1/day each | owner picks from the §5 menu | new competitions |

### Stage 1 — the five questions, ANSWERED 2026-08-08 (13 free-key requests)

Probes: `scripts/api_football_probe.py` (+ two season-bracketing follow-ups); raw responses cached
in `data/api_football/probe/` (gitignored, regenerable — the probe never re-spends on a cached
answer). All 13 requests governor-checked, throttled at 12 s, recorded in `source_health`, and the
plan assertion held on every response.

1. **Per fixture — measured.** `/fixtures/statistics?fixture=<id>` answers (2 rows, one per team);
   `?league=40&season=2024` is rejected: *"The Fixture field is required. The League field do not
   exist."* Lineups likewise answer per fixture. The per-fixture cost shape in §4.2 is real.
2. **Yes, real xG — from the 2023 season.** `expected_goals` present in Championship 2024 and 2023
   statistics, **absent in 2022**; Brasileirão 2024 has it too (plus `goals_prevented`, a
   goalkeeper metric relevant to the deferred lineups work). Sampled one finished fixture per
   season. **Consequence: the xG-era backfill is ~3 seasons (2023+), not nine** — the ~139k
   ceiling drops to **~46k requests**, a fraction of one Mega day. Statistics *without* xG (shots,
   possession, cards) run much deeper — catalogue `statistics` coverage median start 2016 — a
   future-features option, not champion-feature material. Catalogue flags say 60 of our 78
   competitions carry fixture statistics at all; 18 never do (incl. argentina-nacional, a-league,
   ecuador-ligapro, liga-expansion-mx, the lower Scottish tiers) — those stay xG-less on any source.
3. **Pinnacle exists; closing history does not.** Pinnacle is one of 33 bookmakers in
   `/odds/bookmakers`, but `/odds?fixture=<finished 2024>` returns **0 rows** — odds for completed
   fixtures are purged. There is no historical closing-odds backfill on this API, full stop.
   Tier B's "football-data keeps the odds column" is now measured, not cautious; any future
   `/odds`-vs-Pinnacle comparison must be a *live capture at close*, not a backfill.
4. **64 of 78 reach 2017** by catalogue season metadata (fixtures/results). The 14 that do not are
   young leagues (Northern Super League 2025, USL Super League 2024) or API depth limits (Poland,
   Chile, India 2018; NWSL, Ireland, USL League One, Libertadores/Sudamericana 2019; Canadian PL
   2020; Conference 2021). Invariant 3 holds regardless: those leagues keep their current sources
   for history — the spine takes current seasons, the registry's ordered lists handle the split.
   Caveat: these are the provider's own coverage flags; the free key cannot fetch pre-2022 to
   verify, so paid-tier spot-checks are part of Stage 3 batch validation.
5. **No paging even at 557.** Championship 2024 returned 557 fixtures in one response,
   `paging {current: 1, total: 1}` (2022 and 2023 likewise). `_get_paged` stands ready anyway.

**League map: drafted and 78/78 mapped** — `config/api_football_league_map.json`, generated
offline from the single cached catalogue request (1,239 leagues) by
`scripts/api_football_map_draft.py`. 77 of 78 at high/anchor confidence; the one review flag is
real: **API-Football splits Paraguay into two ids (Apertura 250 / Clausura 252)**, which the
Stage-3 wiring must merge. Gate: owner reviews the map before Stage 3 uses it.

### Stage 2 — the comparison that defines success — PASSED 2026-08-08 (~6 requests)

League: **brazil-serie-a** (id 71), chosen over an ESPN league deliberately — its football-data
source carries real scorelines (a stronger diff than goals-only), sits fully inside the free key's
2022–2024 window, and loads its comparison frame from cached CSVs, so validation never depended on
ESPN's rate limiter. Runner: `scripts/api_football_stage2_validate.py`; report cached at
`data/api_football/probe/stage2_report.json`.

Measured, three full seasons (2022, 2023, 2024):

- **1,140 of 1,140 fixtures matched** on (season, home, away) — 380 per season, both sides.
- **Scorelines: 1,140/1,140 agree. Zero disagreements.**
- **Standings: identical** — 20 teams per season, computed points tables match exactly.
- **The champion feature builder accepts the spine frame unmodified** (1,140 rows → 67 feature
  columns), so downstream is equivalence-by-construction: the canonical frame is the whole
  interface (§6.3).

Two migration facts the diff surfaced, both now measured rather than anticipated:

1. **Ten club-name pairs differ between API-Football and football-data** (Flamengo↔Flamengo RJ,
   Fortaleza EC↔Fortaleza, Vasco DA Gama↔Vasco, …) — encoded in the validator's `SPINE_RENAME`.
   This is the seed of the per-league name map Stage 3 needs, in the `FD_ESPN` tradition.
2. **API-Football's own spellings drift across seasons** ("Atletico Paranaense" in 2022,
   "Athletico Paranaense" later; "RB Bragantino"→"Bragantino") — the K-League `TEAM_RENAME`
   problem confirmed as systemic, so Stage 3's per-league validation must always diff a full
   season set, not a sample.

One local deviation from this stage's original wording: no local payload rebuild was run — local
rebuilds regress payloads (recorded failure mode; CI owns payload writes). Frame-level equivalence
plus the feature-build acceptance is the mechanism proof; the first CI-built payload from the spine
arrives with Stage 3's first batch.

**Free-tier honesty stands: this validates the mechanism, not current-season coverage**, since the
free plan stops at 2024.

### The purchase checkpoint — between Stages 2 and 3
**Nothing is purchased yet.** Stages 0–2 run entirely on zero requests and the free key (~30
requests total). When they pass — registry, provenance, budget governor and the backfill job all
built and validated end-to-end on a free-tier league — the executing session **stops and tells the
owner explicitly: "infrastructure complete, ready to buy."** The owner then buys Mega, and only
after the purchase is confirmed does any paid-tier request happen.

This sequencing also settles how the Stage-1 unknowns interact with the spend: all five are answered
on the free key *before* money moves, so the owner buys against measured facts, not estimates.

### Stage 3 — Tier A, in batches
Smallest and least-watched leagues first. Each batch runs a full week with `source_health` showing
the spine answering, spend published, and payloads byte-comparable apart from `generated`. Any league
whose data disagrees materially is rolled back to ESPN-first and recorded.

### Stage 4 — statistics, and only statistics
One request per played match against `/fixtures/statistics`, for the 63 xG-less leagues,
recent-first per league and extending backward until the API's depth, the data's real xG coverage,
or 2017 — whichever comes first (§4.2). Lineups, odds and events are deferred families (§3.1) and no
part of this stage. Resumable and idempotent per §6.5: a job that can finish inside a Mega day must
still survive being interrupted in the middle of one.

---

## 8. Invariants — a migration that breaks one of these has failed

1. **No league loses xG or odds.** The basis for the whole tiering.
2. **The payload-regression guard stays authoritative.** It stopped 51 leagues silently rolling back
   a season on 2026-08-08. A new source is not a route around it.
3. **Training history is preserved.** No league moves to a primary that cannot reach 2017.
4. **The champion config does not change as a side effect.** New features are a gated experiment
   with a Brier comparison, never a consequence of a plumbing change.
5. **Provenance is published**, per column family.
6. **Every published figure keeps one source.** `docs/figures.json` and `check_docs` still hold.
7. **The free/paid boundary is untouched.** Better data does not move anything behind the paywall —
   `CLAUDE.md`'s continuity rule stands.

---

## 9. Owner decisions — 2026-08-08

The four questions this section used to hold are answered. They are recorded here so no future
session re-litigates them; the five Stage-1 questions remain open, but they are *measured-fact*
gates, not owner calls.

1. **Terms verified; plan chosen: Mega ($39) for month 1, then Pro ($19) month-to-month.** Pricing
   and terms are in §4.1 — no overage billing, no automatic renewal, hard daily cap, quota reset at
   00:00 UTC. Month-to-month holds until site traffic justifies a longer term (revisit the 3/6/12-
   month discounts then). The lapse-to-Free risk is guarded by the governor's header assertion plus
   a renewal reminder.
2. **Backfill: as deep as the data goes, statistics only.** Every season the paid API serves down to
   the 2017 training floor — but only the stat families the models use or could plausibly use, which
   today means `/fixtures/statistics` for the 63 xG-less leagues (~139k-request ceiling, §4.2).
   Lineups, odds and events are explicitly **deferred, not rejected** (§3.1).
3. **Expansion: yes, from a menu.** Admission requires an active, continuous schedule and enough
   history for at least a basic model behind the predictions layout. The criteria and candidate menu
   are in Tier D (§5); the owner picks per the Stage-6 gate.
4. **Live scores: no — roadmap.** They change the product's character, not its accuracy; someday it
   may be worth watching live state move season-long odds in the table. Note §3.1's nuance:
   declining live scores does *not* keep the ESPN fast-refresh loop alive — `/fixtures` polling
   replaces it without the livescore endpoint.
5. **Purchase timing: nothing is bought yet.** The buy happens at the §7 checkpoint, after Stages
   0–2 prove the infrastructure on the free key and the executing session explicitly reports
   "infrastructure complete, ready to buy."

---

## 10. Why this is worth doing beyond reliability

The reliability case is already made — three days of failed refreshes and 3–5 day stale payloads
during the week of a paid launch. But the stronger case is the one the band-aid framing misses:

**63 of 70 leagues run the champion model with its largest feature family empty.** Not because the
model cannot use xG there, but because no free source happened to publish it. That is the accretion
showing. A foundational source does not just make the site more reliable — it makes the *same model*
better on 90% of the competitions it serves, and it makes the next league an entry in a file.
