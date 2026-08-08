# API-Football as the data foundation — execution spec

**As of:** 2026-08-08 · **Owner:** Ryan · **Author:** Claude
**Status:** for execution in a fresh session. Stage 0 needs no approval and makes no requests.
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
| **Pinnacle closing 1X2 (value layer, paper ledger)** | football-data + intl (31) | **retained** unless `/odds` proves comparable |
| Goalkeeper z-score (3 cols, **MLS only**) | ASA | retained, and **extended to all leagues** if lineups support it |
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

| Capability | Used today | What it would unlock |
|---|---|---|
| Fixtures | ✅ (2 leagues) | the spine |
| **Statistics** | ❌ | xG for the **63 leagues that have none**, shots, possession |
| **Pre-match odds** | ❌ | market benchmark for the **39 leagues with no odds at all** |
| **Lineups** | ❌ | goalkeeper quality for **all** leagues, not just MLS; confirmed XI |
| **Injuries / players** | ❌ | availability — a feature family the model defines but only MLS can fill |
| **Events** | ❌ | goal times, cards, subs — match narrative for Club Watch |
| **Livescore** | ❌ | live match state without the ~50-minute ESPN fast-refresh loop |
| **Head-to-head** | ❌ | a modelling input the repo has never had |
| **Standings** | ❌ | independent cross-check against our computed tables |
| **Leagues / countries catalogue** | ❌ | expansion without bespoke research per league |
| Transfers | ❌ | squad churn beside Transfermarkt values |

**The largest single prize is xG coverage.** 18 of 31 model feature columns are xG rolling windows,
and only 7 of 70 leagues have a real xG source. The other 63 run the same model with its most
numerous feature family empty.

---

## 4. Request budget — the actual constraint

Pro is **7,500/day**. Two very different cost shapes sit underneath it.

### Per-league endpoints — negligible
`_fetch_league` already caches per `(league, season)` and refetches only the latest season, so a
league costs **1 request per refresh**. A cached 232-fixture season returned `paging {current: 1,
total: 1}` — unpaged at that size.

| Workload | Requests/day | % of cap |
|---|---|---|
| All 70 leagues, fixtures, daily | **70** | 0.9% |
| Standings for all 70, daily | 70 | 0.9% |
| One-time fixtures backfill, 70 × 9 seasons | 630 | 8.4% of one day |

### Per-fixture endpoints — this is what the budget is for
Statistics, lineups, events and (probably) odds are keyed per fixture. Measured: **17,851 fixtures
in one season** across built competitions.

| Workload | Requests | At 7,500/day |
|---|---|---|
| Statistics, one season, all competitions | 17,851 | **2.4 days** |
| Statistics, nine seasons (full training history) | 160,659 | **21 days** |
| Statistics + lineups + odds, one season | ~53,000 | ~7 days |
| **Steady state — only newly played matches** | **~50–150/day** | **~2%** |

**The shape of the answer:** ongoing operation never approaches the cap. Backfill does, and is a
metered background job measured in weeks, run once. That is affordable — it is 21 days of *idle
overnight capacity*, not 21 days of blocked work — but it must be a deliberate, resumable,
budget-governed job rather than something a refresh triggers.

Practical consequence: **backfill oldest-first and newest-first simultaneously.** Recent seasons
carry the most model weight (`XGB weight ½-life: 6 seasons`), so value arrives long before the job
finishes.

---

## 5. Migration tiers

**Tier A — move now, unconditional (30 leagues).** Currently ESPN. Measured: **0 of 30 carry xG, 0
carry odds.** They lose nothing and stand to gain xG, lineups and availability. This alone takes the
site's most fragile source out of the hot path.

**Tier B — move on evidence (31 leagues).** football-data + intl. They hold Pinnacle closing odds.
Move only if `/odds` is demonstrably the same measurement; otherwise take API-Football for
fixtures/statistics and **keep football-data for odds alone**. A league may legitimately have two
sources for two different columns — that is what the canonical frame is for.

**Tier C — hold (7 leagues).** understat + ASA. They hold the only real xG in the platform and, for
MLS, the only goalkeeper data. These move last, if ever, and only against a match-for-match
comparison over a full season.

**Tier D — new coverage.** The catalogue endpoint lists competitions we do not carry. Expansion
becomes a mapping row plus a build, at ~1 request/day each. Candidates worth evaluating: additional
CONMEBOL and Liga MX tiers, more of the Nordic and Central European pyramids, and women's
competitions beyond the five currently modelled. **Coverage growth is cheap; the limit is our
bridge evidence, not requests** — an unbridged league can publish a league page but cannot join
Global ELO.

---

## 6. Architecture

### 6.1 A source registry, not a source string
Today each league has `"source": "espn"` — one string, all-or-nothing. Replace with a per-capability
map, defaulting to the spine:

```
"epl": {"sources": {"fixtures":   ["api_football", "espn"],
                    "xg":         ["understat", "api_football"],
                    "odds":       ["football_data"],
                    "lineups":    ["api_football"]}}
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

### 6.5 Backfill is resumable and idempotent
A 21-day job cannot assume it runs to completion. Per-fixture results cached to disk keyed by
fixture id; restart re-reads rather than re-requests; progress and spend both queryable mid-flight.

---

## 7. Stages

| Stage | Requests | Gate | Output |
|---|---|---|---|
| **0 — Build blind** | **0** | none | registry, provenance, budget governor, pagination handling, all against fixtures |
| **1 — Map and probe** | ~10 | owner reviews mapping | committed league map; the five unknowns answered as measured facts |
| **2 — Validate on free key** | ~20 | none | one league builds end-to-end from the spine; payload compared column by column |
| **3 — Tier A migration** | ~30/day | paid plan | 30 leagues on the spine, ESPN as fallback |
| **4 — Capability backfill** | metered, weeks | stage-1 quality proof | xG/lineups for leagues that have none |
| **5 — Tier B/C review** | metered | measured comparison | odds and xG move only if proven equal or better |
| **6 — Tier D expansion** | ~1/day each | owner picks | new competitions |

### Stage 1 — the five questions everything else depends on
1. Are statistics/odds/lineups keyed **per fixture or per league+season**? Decides 2.4 days vs 21.
2. Does `/statistics` carry **real xG**, for which leagues, how far back?
3. Are `/odds` **Pinnacle closing**, or a different book or timing?
4. How far back does the paid plan serve — **does it reach 2017**?
5. Does a **552-fixture** season page? (232 did not.)

**Acceptance:** every answer written into this document as a measured fact with the probe that
produced it. Stages 4 and 5 are not scoped until they exist.

### Stage 2 — the comparison that defines success
Build one league end-to-end from the spine and diff it against the ESPN-built payload: same clubs,
same fixture count, same canonical columns, same standings. **Free-tier honesty: this validates the
mechanism, not current-season coverage**, since the free plan stops at 2024.

### Stage 3 — Tier A, in batches
Smallest and least-watched leagues first. Each batch runs a full week with `source_health` showing
the spine answering, spend published, and payloads byte-comparable apart from `generated`. Any league
whose data disagrees materially is rolled back to ESPN-first and recorded.

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

## 9. Open questions for the owner

1. **Overage terms** — the pricing page shows a flat $19 and a daily cap, which normally means
   requests are rejected rather than billed. Worth confirming before purchase; I could not verify it
   (their pricing page returns 403 to automated fetches).
2. **Backfill ambition** — full nine-season statistics history (~21 days of background capacity), or
   recent seasons only, which carry most of the model weight? Recommendation: **recent-first,
   open-ended**, so value arrives early and the job can stop whenever it stops paying.
3. **Expansion appetite** — new competitions are nearly free in requests but each one adds a surface
   to keep correct. How many, and chosen by what: audience, betting liquidity, or bridge evidence?
4. **Do we want live scores?** It is the one capability that changes the product's *character*
   rather than its accuracy, and it would retire the fast-refresh ESPN loop entirely.

---

## 10. Why this is worth doing beyond reliability

The reliability case is already made — three days of failed refreshes and 3–5 day stale payloads
during the week of a paid launch. But the stronger case is the one the band-aid framing misses:

**63 of 70 leagues run the champion model with its largest feature family empty.** Not because the
model cannot use xG there, but because no free source happened to publish it. That is the accretion
showing. A foundational source does not just make the site more reliable — it makes the *same model*
better on 90% of the competitions it serves, and it makes the next league an entry in a file.
