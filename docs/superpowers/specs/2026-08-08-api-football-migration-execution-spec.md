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

| Workload | Requests/day | Share of Pro's 7,500 |
|---|---|---|
| All 30 ESPN leagues, daily | **30** | **0.4%** |
| Every one of the 70 leagues, daily | 70 | 0.9% |
| One-time backfill, 70 leagues × 9 seasons | 630 | 8.4% of a single day |
| Worst case with 4× pagination on every league | 280 | 3.7% |

**You could move every league on the platform and use under 1% of the plan.** So "as many as
possible without exceeding 7,500" has a disappointing answer: the ceiling never binds. The real
question is not how many we can *afford* to move, but which ones we *should* — and that is decided
by what each source uniquely provides.

---

## Which leagues move, and why

The deciding fact: **API-Football supplies no xG** — `_parse_fixtures` writes `home_xg: np.nan`
explicitly — **and no market odds**.

| Current source | Leagues | Uniquely provides | Migrate? |
|---|---|---|---|
| **ESPN** | **30** | nothing — measured: **0 of 30 carry xG, 0 carry market odds** | ✅ **Yes** |
| football-data | 17 | Pinnacle closing 1X2 odds — the betting benchmark | ❌ No |
| football-data intl | 14 | Pinnacle closing odds (PSCH/PSCD/PSCA) | ❌ No |
| understat | 5 | xG — a champion model input | ❌ No |
| ASA | 2 | MLS xG | ❌ No |
| API-Football | 2 | already there | — |

**Migration target: the 30 ESPN leagues, and only those.** They lose nothing, because they have
nothing to lose — ESPN gives them neither xG nor odds today. Every other league would trade a real
model input or the value layer for a more reliable transport, which is a bad trade.

That also means the migration is **not** a failover any more. For those 30, API-Football becomes the
**primary** and ESPN the fallback — the reverse of the earlier design, and better: it moves the
reliable source into the hot path instead of leaving it as a spare tyre nobody exercises.

---

## Unknowns to resolve in stage 1 — before any bulk requests

These are the reasons to map before spending, and each is a genuine risk to correctness rather than
to cost.

1. **Pagination is not handled.** `_get` returns `payload["response"]` and nothing in the adapter
   reads `paging.total` or `paging.current`. If API-Football pages a 380-fixture season, we would
   silently ingest only the first page and every downstream table would be wrong with no error. The
   2023 Leagues Cup pull returned all 77 fixtures in one response, so it is unpaged at that size —
   **that proves nothing about a 380-match season.** Resolve first; it also changes the request
   accounting.
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
| **1 — Map once** | **~1** | owner reviews the mapping file |
| **2 — Validate on free** | ~10 | none |
| **3 — Migrate** | ~30/day | paid plan |

### Stage 0 — build blind (no requests, no approval)
Source router, budget guard, provenance field, pagination handling, and the mapping file's schema
and loader — all against mocks and committed fixtures.

**Acceptance:** with the network patched out, a test proves the router picks API-Football first for a
migrated league, falls back to ESPN when it fails, records which source answered, and refuses past
budget. Pagination is exercised against a fixture with a multi-page `paging` object.

### Stage 1 — map once (~1 request)
Fetch the catalogue, cache and commit it, match the 30 offline, flag the ambiguous.

**Acceptance:** `config/api_football_leagues.json` committed with every one of the 30 either mapped
or explicitly marked unavailable, and the ambiguous ones flagged for review. Pagination and season
depth answered from the cached catalogue and one probe fixture.

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
