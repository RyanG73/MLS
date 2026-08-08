# Match-data source resilience — scope

**As of:** 2026-08-08 · **Owner:** Ryan · **Author:** Claude
**Status:** scope for approval. Nothing implemented. One decision is the owner's and blocks phase 3.
**Canonical current state:** [`../../STATUS.md`](../../STATUS.md)

Owner, 2026-08-08: *"is ESPN always going to rate limit us? should we find another avenue to get
match information?"*

Short answer: **yes, it will keep happening.** It is not a bug to be fixed but a property of the
dependency. This scopes what to do about it.

---

## The problem, measured

ESPN's `site.api.espn.com` is an **undocumented, unofficial endpoint**. No contract, no published
limits, no support channel, no notice before it changes. It rate-limits by IP, answers with **403
rather than 429** — so it reads like an authorisation failure — and once tripped it refuses *every*
endpoint, not only the one that crossed the line.

Measured directly on 2026-08-07: `concacaf.leagues.cup/scoreboard` returned 200; within a minute
that same URL and `uefa.champions`, which had also just returned 200, were both 403.

What that cost in three days:

| Symptom | Evidence |
|---|---|
| Daily refresh failed outright | 2026-08-05, 08-06, 08-07 — the 08-07 failure was on `usa.1`, MLS itself |
| Fast refresh failed | **seven consecutive runs**, 16:03–21:56 UTC on 08-07 |
| Leagues Cup lost every season | run `31234585894`: 9 of 9 seasons 403'd, CI left with no cache |
| Championship still cannot rebuild | `eng.2` 403 while football-data's 2026-27 CSVs are not published |

### How much depends on it

| Source | Leagues | |
|---|---|---|
| **ESPN** | **30 of 70** | plus **every** continental competition, plus fixtures and rosters |
| football-data | 17 | European majors only; publishes late and not at all pre-season |
| football-data intl | 14 | |
| understat / ASA / API-Football | 9 | understat is xG-only; ASA is MLS-only |

Twelve modules import an ESPN adapter. A full rebuild issues roughly **560 ESPN requests** — that
burst is itself what trips the limit.

**This is not compatible with charging for the product.** `STATUS.md` already states the standard:
*"under a paid tier, stale data is a refund request."* A backbone that failed three consecutive
daily refreshes cannot underwrite an Aug 17 paid launch.

---

## What already exists — the work is smaller than it looks

Three pieces of the solution are already built, which is the main reason this is worth doing now.

1. **A canonical frame, and every adapter already speaks it.** `understat._COLS` defines
   `match_id, date, season, home_team, away_team, home_goals, away_goals, home_xg, away_xg,
   label_result, is_result, is_playoff`, and **all seven adapters** — ESPN soccer, ESPN fixtures,
   football-data, football-data intl, understat, ASA, API-Football — return it. Swapping one source
   for another is therefore a *routing* change, not a parsing change. This is the single fact that
   makes failover cheap.
2. **A health recorder, already live.** `data_pipeline/source_health.py` writes per-fetch accounting
   to `data/source_health.parquet` — **3,407 rows today**. It answers "when did this feed last
   succeed and how much did it return" without log archaeology.
3. **Retry and isolation, shipped 2026-08-07/08.** `espn_get` now backs off on 403/429/5xx with
   jitter and `Retry-After`; `fast_refresh` isolates per-league failures above a 50% threshold; a
   per-competition first-season floor stopped ~5 impossible requests per continental refresh.

**Do not mistake #3 for a solution.** Retry converts a *transient* limit into a success. It does
nothing when ESPN refuses for three hours, which is what actually happened.

### The gaps

- **`source_health` is only wired into 3 of 8 adapters** (ASA, ESPN soccer, understat). The feeds
  that failed hardest — `espn_continental`, `espn_fixtures`, football-data — record nothing.
- **Every existing fallback is to a stale cache, not to another provider.** `football_data` and
  `asa_cache` both fall back to their last good copy. Nothing has ever tried a second source.
- **No request budget.** Nothing limits or spreads the ~560-request burst.

---

## Options

### A. Reduce demand only — caching, budgets, conditional fetches
Cheapest, no new dependency, no cost. Fewer requests means the limit is tripped less often.
**Rejected as a complete answer:** it lowers probability, not consequence. When ESPN says no, there
is still no data, and a paid product needs an answer for that case.

### B. Add a paid second source with failover — **recommended**
API-Football is already integrated (`data_pipeline/api_football.py`), already has a key in `.env`,
already emits the canonical frame, and its league-id lookup already works — I resolved the Leagues
Cup to id **772** with it on 2026-08-08 and pulled the full 2023 and 2024 editions. A paid tier adds
current seasons (the free plan stops at 2024) and a real rate limit with an actual contract.

Cost is the owner's call and blocks phase 3 — see the open question.

### C. Self-hosted cache/proxy in front of ESPN
Would spread the burst and survive short outages. **Rejected for now:** it is new infrastructure to
run and monitor, and it still has exactly one upstream. Worth revisiting only if B is rejected.

**Recommendation: A then B.** A is worth doing regardless and needs no decision; B is the part that
makes the launch defensible.

---

## Phases

Each ships independently and is useful alone.

### Phase 1 — See it (no new dependency, no cost)
Wire `record_source_run` into the five adapters that lack it, and publish a small
source-health surface: per feed, last success, failure rate over 24h, rows returned. Alert when a
feed has failed N consecutive attempts.

*Why first:* right now a source failure is discovered by a human noticing a red workflow. Three days
passed before anyone did. **Acceptance:** a feed dark for two consecutive scheduled runs raises an
alert without anyone reading a log.

### Phase 2 — Ask for less (no new dependency, no cost)
A request budget and scheduling change: spread the ~560-request burst, skip seasons already complete
and cached, and make conditional fetches where the upstream supports them. Extend the first-season
floor idea to every comp.

**Acceptance:** a full rebuild issues measurably fewer ESPN requests — target ≤50% of today's 560 —
with byte-identical payload output. That last clause is the real test: fewer requests, same answers.

### Phase 3 — Fail over (needs the cost decision)
A source-router: each league declares an ordered list of sources rather than one `source` string.
The router tries them in order, records which answered via phase 1, and marks the payload with its
provenance. `build_league_data`'s existing `source` field becomes the head of that list, so nothing
changes for a league until a second source is added to it.

**Acceptance, and this is the one that matters:** with ESPN blackholed at the HTTP layer, a full
build still produces payloads for the leagues that have a second source, and `check_docs` plus the
payload-regression guard both pass. Verified by a fault-injection test, not by waiting for a real
outage.

### Phase 4 — Prove it stays fixed
A drill: block ESPN in CI on a schedule and assert the build degrades as designed. Without this,
phase 3 rots the first time an adapter changes.

---

## What this must not break

- **The payload-regression guard stays authoritative.** It is what stopped the Championship rolling
  back a season on 2026-08-08. A failover must never be a route around it — if the second source
  yields a worse season, the guard still refuses.
- **Provenance must be visible.** A payload built from a fallback source should say so. Silently
  swapping sources would make a disagreement between two leagues impossible to explain.
- **No source may be trusted more than it has earned.** Two sources disagreeing about a scoreline is
  a real possibility; the router picks by declared order, and the disagreement is recorded rather
  than averaged.

---

## Open question — the only one that blocks anything

**Is a paid API-Football tier approved, and at what monthly ceiling?** Phase 3 is designed around it
because the integration already exists, but the phase is source-agnostic: any second provider that
emits the canonical frame would do. Phases 1, 2 and 4 need no decision and no spend, and I would
start there regardless of the answer.

A secondary question, cheaper to answer later: whether the fallback should cover all 30 ESPN leagues
or only the subset the paid product actually promises. Covering fewer leagues costs less and is
easier to verify, and the promise is what has to hold.
