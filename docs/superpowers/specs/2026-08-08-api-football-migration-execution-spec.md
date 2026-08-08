# API-Football migration — execution spec

**As of:** 2026-08-08 · **Owner:** Ryan · **Author:** Claude
**Status:** for execution. Stage 0 needs no approval and no requests. Stage 3 needs the paid plan.
**Supersedes the phase-3 section of** [`2026-08-08-match-data-source-resilience-design.md`](2026-08-08-match-data-source-resilience-design.md);
phases 1, 2 and 4 of that document stand.

Owner goal, 2026-08-08: *"move as many leagues to this api as possible without going over 7500
requests per day"*, built against the **free** key first, mapped end to end **before** any requests.

---

## The finding that shapes everything: the request cap is not the constraint

Measured from the adapter and the payloads, not estimated.

`api_football._fetch_league` already caches per `(league, season)` and re-fetches **only the latest
season** — every earlier season reads from disk. So a league in steady state costs **one request per
refresh**.

### Match data (`/fixtures`) — the cap never binds

| Workload | Requests/day | Share of Pro's 7,500 |
|---|---|---|
| All 30 ESPN leagues, daily | **30** | **0.4%** |
| Every one of the 70 leagues, daily | 70 | 0.9% |
| One-time backfill, 70 leagues × 9 seasons | 630 | 8.4% of a single day |

Pagination is a smaller worry than first thought: a cached response for a **232-fixture season came
back as `paging {current: 1, total: 1}`** — one page. Still unproven at 552 (the English tiers), so
the handler is built anyway and the assumption is checked in stage 1, not trusted.

### Statistics and odds — where the cap *does* bind

These are separate endpoints, and if they are keyed **per fixture** rather than per league the
arithmetic changes completely. Measured across the built competitions: **17,851 fixtures in a single
season.**

| Workload (per-fixture assumption) | Requests | At 7,500/day |
|---|---|---|
| One season of statistics, every competition | **17,851** | **2.4 days** |
| Nine seasons of history | 160,659 | **21 days** |
| Steady state — only newly played matches | **~50–150/day** | **~2%** |

**This is the real shape of the problem, and it vindicates the original framing.** Steady state is
trivial; the *backfill* is what the cap constrains. A full historical statistics pull is a
three-week background job, not something to run inside a refresh. Whether `/odds` batches by
`league+season` — in which case it is cheap — or is per-fixture like statistics is a **stage-1
question**, and it decides whether odds migration is a day or a month.

Consequence for sequencing: match data can migrate immediately; statistics and odds are a separate,
rate-limited backfill with its own budget, run once and then maintained incrementally.

---

## Which leagues move, and why

**Correction, 2026-08-08 (owner).** An earlier draft of this spec said "API-Football supplies no xG
and no market odds". That was wrong, and the error is worth keeping visible because it nearly halved
the plan's ambition. What is actually true, verified against cached responses:

- The **`/fixtures`** endpoint — the *only* one this adapter has ever called — returns exactly
  `fixture, league, teams, goals, score` per match. No odds, no statistics, no xG. So
  `_parse_fixtures` writing `home_xg: np.nan` is correct **for that endpoint**.
- The plan **also includes Pre-match Odds, In-play Odds and Statistics** as separate endpoints. We
  have never called them. "Our adapter does not fetch X" is not "the API does not have X", and the
  first draft treated them as the same sentence.

So the migration is potentially much larger than 30 leagues, and for the 30 ESPN ones it is an
**upgrade rather than a lateral move** — they carry no xG today and could gain it.

| Current source | Leagues | Today's unique value | Migrate? |
|---|---|---|---|
| **ESPN** | **30** | none — measured: **0 of 30 carry xG, 0 carry market odds** | ✅ **Yes, and may gain xG** |
| football-data | 17 | Pinnacle closing 1X2 | ⚠️ Only if `/odds` is demonstrably as good |
| football-data intl | 14 | Pinnacle closing 1X2 | ⚠️ Same |
| understat | 5 | xG — a champion model input | ⚠️ Only if `/statistics` carries real xG |
| ASA | 2 | MLS xG | ⚠️ Same |
| API-Football | 2 | already there | — |

**The 30 ESPN leagues move unconditionally** — nothing to lose, something to gain. Everything else
moves only on evidence, and the bar is high: Pinnacle closing odds and understat xG are load-bearing
for the value layer and the champion model respectively. "Available from the same vendor" is not
evidence they are equivalent.

For migrated leagues API-Football becomes **primary** and ESPN the fallback — the reverse of the
earlier failover design, and better: it puts the reliable source in the hot path instead of leaving
it a spare tyre nobody exercises.

---

## Unknowns to resolve in stage 1 — before any bulk requests

These are the reasons to map before spending, and each is a genuine risk to correctness rather than
to cost.

1. **Endpoint semantics for statistics and odds — the biggest unknown.** Are they keyed per fixture
   or per `league+season`? That single answer is the difference between a 2.4-day backfill and a
   21-day one, and between odds migration being cheap or being a month. Nothing else in this spec
   moves until it is settled. Answer it from the documentation and one probe fixture, not by
   launching a bulk job.
2. **Does `/statistics` actually carry expected goals**, for which leagues, and how far back? "The
   plan includes Statistics" does not mean every competition has xG in it. understat's xG is a
   champion model input; replacing it with a thinner series would quietly degrade the model. Compare
   on a league understat already covers, match by match, before trusting it anywhere.
3. **Are `/odds` comparable to Pinnacle closing?** The value layer is benchmarked against Pinnacle
   closing 1X2 specifically. A different book, or opening rather than closing prices, is a different
   measurement — and the paper ledger's history would no longer be comparable to its future.
4. **Pagination is not handled.** `_get` returns `payload["response"]` and nothing reads
   `paging.total`. A cached 232-fixture season came back as `paging {current: 1, total: 1}`, so the
   fixtures endpoint is unpaged at that size — **that proves nothing at 552**, which the English
   tiers run, and nothing at all about the statistics endpoint. Build the handler; verify rather
   than assume.
2. **Season depth.** Training is 2017+ and 2020-excluded (`CLAUDE.md`). The free plan serves
   2022–2024. Whether the paid plan reaches 2017 for these leagues decides whether migration is
   possible at all without losing training history.
3. **Coverage.** Does API-Football carry all 30? Second tiers and the smaller confederations are
   where a gap is most likely.
4. **Name and id mapping.** The single largest source of silent error. See below.

---

## The mapping is a committed artefact, not runtime matching

A `search=` call at build time is how "Liverpool" becomes the wrong Liverpool. The mapping must be a
file a human has read.

- **One request, not thirty.** `/leagues` with no search term returns the whole catalogue; cache it
  to disk, commit it, and match offline. Thirty `search=` calls would burn a third of a free day and
  produce a mapping nobody reviewed.
- **Output**: `config/api_football_leagues.json` — `{our_league_id: {af_id, af_name, af_country,
  matched_by, confidence}}`, sorted, with the ambiguous ones flagged.
- **Owner review before use.** I expect genuine ambiguity in second tiers, women's competitions, and
  anything called "Premier League". Those get flagged rather than guessed.
- **A test asserts every migrated league has an entry**, so a league cannot quietly fall back to
  fuzzy matching later.

---

## Budget guard — built in stage 0, enforcing from the first request

Not added afterwards. If it is not live before the first call, a loop costs a free day and we learn
about it from a 403.

- `_DAILY_BUDGET = 200` — about 6× the worst realistic need and 2.7% of the paid plan. Deliberately
  far below the provider's cap: the guard exists to catch *our* bugs, not to ration a scarce
  resource.
- Counter read from `data/source_health.parquet`, which already records every API-Football call
  (wired 2026-08-08). No new state file, and spend becomes a query rather than a guess.
- **Fail closed.** Over budget raises, records the refusal, and stops. Same posture as the
  payload-regression guard: a data path that silently keeps going is how you find out from an
  invoice.
- Applies to exploratory and backfill calls too, not just scheduled builds. A separate opt-in budget
  for backfills so a one-off cannot eat the operational allowance.

---

## Stages

| Stage | Requests | Gate |
|---|---|---|
| **0 — Build blind** | **0** | none — start immediately |
| **1 — Map and probe** | **~5** | owner reviews the mapping; endpoint semantics settled |
| **2 — Validate on free** | ~10 | none |
| **3 — Migrate match data** | ~30/day | paid plan |
| **4 — Statistics / odds backfill** | metered, weeks | only if stage 1 proves quality |

Stages 3 and 4 are deliberately separate. Match data is a same-day migration with a trivial request
cost; statistics and odds are a long metered backfill whose value depends entirely on the stage-1
quality answers. Coupling them would hold a cheap, certain win hostage to an expensive, uncertain
one.

### Stage 0 — build blind (no requests, no approval)
Source router, budget guard, provenance field, pagination handling, and the mapping file's schema
and loader — all against mocks and committed fixtures.

**Acceptance:** with the network patched out, a test proves the router picks API-Football first for a
migrated league, falls back to ESPN when it fails, records which source answered, and refuses past
budget. Pagination is exercised against a fixture with a multi-page `paging` object.

### Stage 1 — map and probe (~5 requests)
Fetch the catalogue once, cache and commit it, match offline, flag the ambiguous. Then spend a
handful of deliberate probes on the four unknowns above: one statistics call and one odds call on a
known fixture, and one fixtures call on a 552-match season.

**Acceptance:** `config/api_football_leagues.json` committed with every candidate either mapped or
explicitly marked unavailable. The probe results are written into this spec as measured facts —
endpoint keying, whether xG is present and for which leagues, which book the odds come from, and
whether 552 fixtures page. **Stage 4 is not scoped until those numbers exist.**

### Stage 2 — validate on the free key (~10 requests)
Blackhole ESPN; confirm failover fires, provenance records, budget enforces, payloads still build.

**Acceptance:** a league builds end to end from API-Football using 2024 data, and its payload is
structurally identical to the ESPN-built one — same clubs, same fixture count, same canonical
columns. **Free-tier honesty: this validates the mechanism, not current-season coverage**, because
the plan blocks 2025+. That remains the one thing only the paid plan can prove.

### Stage 3 — migrate (paid plan)
Flip the 30 in ordered batches, smallest and least-watched first. `source` becomes an ordered list;
ESPN stays as fallback so nothing is lost if a league turns out to be badly covered.

**Acceptance:** each batch runs a full week with `source_health` showing API-Football as the
answering source, actual daily spend published, and payload output byte-comparable to the ESPN build
apart from `generated`. Any league whose data disagrees materially is rolled back to ESPN-first and
recorded.

---

## What this must not break

- **The payload-regression guard stays authoritative.** It stopped 51 leagues silently rolling back
  a season on 2026-08-08. A new source is not a reason to bypass it — if API-Football yields an older
  season, the guard still refuses.
- **No league loses xG or odds.** That is the entire basis for migrating these 30 and not the other
  38. If a migration would drop either, it does not happen.
- **Provenance is published.** A payload built from a fallback says so, or a disagreement between two
  leagues becomes impossible to explain.
- **Training history is preserved.** If the paid plan cannot reach 2017 for a league, that league
  keeps ESPN as primary rather than losing model history.

---

## Open questions

1. **Overage terms.** The screenshot shows a flat $19 and a daily cap, which normally means requests
   are *rejected* rather than billed — but that should be confirmed in their terms before purchase.
   It is the one thing I could not verify (their pricing page returns 403 to automated fetches).
2. **Backfill scope.** Re-pulling 2017+ for 30 leagues is ~630 requests, comfortably one day. Worth
   doing for consistency, or leave existing ESPN-derived history in place and switch only
   going forward? Leaving it is cheaper and risks two sources' conventions meeting mid-history.
