# Platform reliability, model improvement, and API opportunity — execution spec

**As of:** 2026-08-09 · **Owner:** Ryan · **Author:** Claude
**Status:** for execution in a fresh session. Self-contained: assumes no memory of the
2026-08-08 session that produced it.
**Canonical current state:** [`../../STATUS.md`](../../STATUS.md) — this document never overrides it.
**Predecessor:** [`2026-08-08-api-football-migration-execution-spec.md`](2026-08-08-api-football-migration-execution-spec.md)
(Stages 0–4 complete; Stages 3-batch-2, 5 and 6 remain and are folded into this roadmap).

Owner brief: *"get us back to a point where we can update the site multiple times per day, look
for ways to improve the model through data available in the api, and launch features for the site
based on new opportunities available via the api."*

---

## 0. Why this document exists

On 2026-08-08 the platform migrated its match-data backbone to API-Football (Mega plan), backfilled
46,205 match statistics sheets, and shipped a source router with per-family provenance. That work
is done and is not re-litigated here.

What the day also produced was **eight defects, five of them introduced by the migration itself**,
every one invisible to a green test suite. That is the real subject of this spec. The site cannot
update several times a day on a foundation where a source can serve the wrong country's league with
a 200, a validator can assert arithmetic no surface uses, and a helper import can silently kill the
refresh path. **Reliability first, then model, then features** — in that order, because the latter
two are worthless on a stale site.

### The eight defects, and the single pattern underneath

| # | Defect | Consequence | Caught by |
|---|---|---|---|
| 1 | `provenance` key assigned twice in one dict literal | Routing provenance silently discarded; invariant claimed shipped was false for a day | Reading the file |
| 2 | Fast refresh never consulted the source registry | Migrated leagues still died behind ESPN's circuit breaker | Reading CI logs |
| 3 | Backfill spend counted against the ops allowance | 46k-request job locked the daily refresh out for a UTC day | Running it live |
| 4 | `segunda` mapped to af_id 140 (**La Liga**, not Segunda) | 1,140 sheets of the wrong division, reported as 100% coverage | The xG join surfacing Real Madrid in a 2nd-tier frame |
| 5 | football-data 301-redirects unpublished ES files onto Scottish ones | Wrong division cached under the right filename, 200 OK | A club-set sanity check |
| 6 | `football_data_intl` never read the `League` column | 920 Argentine cup matches inside the league frame | A handoff investigation |
| 7 | `attach_market` merged on a non-unique key | ~15,500 duplicate rows across 9 leagues; matches got **other fixtures' closing odds** | Found incidentally while fixing #6 |
| 8 | `source_registry` imported pandas at module scope | Fast refresh `--select` runs on bare Python → `ModuleNotFoundError` every 15 min | Reading CI logs |

**The pattern: a source states its own identity and the consuming code never asks.** `Div`,
`League`, `Country`, an API league id, a payload's own `elo_scale` — five of the eight are that
exact shape. None produced an error; every one produced *confident, healthy-looking wrong data*.
A sixth (#7) is the sibling failure: joining on a key never verified to be unique.

Two more were measurement errors of my own that reached the owner as fact: xG coverage reported at
92.1% (counting a field's *presence*, not its *value*; true figure 43.9%) and mid-run progress
sampled by recency (structurally biased toward whichever league was in flight).

**Design consequence for everything below: validation must assert identity and uniqueness, and a
coverage claim must be a full pass over the artifact asserting the condition the consumer needs.**

---

## 1. Where the platform actually stands (verified 2026-08-09)

### Sources
| Source | Leagues | Notes |
|---|---|---|
| ESPN | 30 | Still the largest group; rate-limits by IP, answers 403 not 429, refuses *every* endpoint once tripped |
| football-data | 17 | Now `Div`-validated (defect #5 fixed) |
| football-data intl | 14 | Now `League`-validated; `attach_market` de-duplicated (#6, #7 fixed) |
| understat | 5 | Real xG, Tier C — hold |
| ASA | 2 (+MLS) | Real xG + the only GK data, Tier C — hold |
| API-Football | 2 routed + 3 mapped | `northern-super-league`, `usl-super-league` spine-first; CPL/K-League/Costa Rica mapped |

**Only 2 of 78 competitions are registry-routed.** The migration proved the mechanism and stopped.

### Known-broken, known-risky
- **`build (mls)` has failed since ~2026-08-06** on ESPN 403 for `usa.1/scoreboard`. The flagship
  league is not rebuilding. **Unresolved.**
- **ESPN availability is bimodal** — dark for hours on 08-07 and 08-08, answering 200 at 01:20 on
  08-09. Any plan that depends on ESPN answering *at a particular moment* will fail intermittently.
- **Mega expires 2026-09-08.** On downgrade, `API_FOOTBALL_PLAN` must change in **both**
  `refresh-daily.yml` and `refresh-leagues.yml`, or the lapse guard fails builds loudly.
- **`source_health.parquet` is gitignored, read by no workflow, and discarded every CI run.** The
  new division-mismatch guard and every router fallback log there — i.e. into nothing.
- **The club ELO chart contradicts the league table** on 75 clubs, up to ±86.3 (Liverpool: 1706 in
  the EPL table, 1643 on its own chart). Needs a product decision, not a code fix.
- **Argentina's 2026 table is structurally wrong**: 30 clubs, pairs meeting 3×, because Apertura +
  Clausura + interzonal sum into one table under a single label. Needs a stage/round source.

### Budget reality (the constraint is not what the spec originally assumed)
Mega is 150,000/day at 900 r/m. Measured throughput is **~126 requests/minute** — network
round-trip bound, not quota bound, at the firewall-safe 50% throttle. A full statistics backfill
(46,485 requests) took ~4.5 hours and 31% of one day's quota. **Steady state is ~50–150/day.**
Quota is effectively free; wall-clock time and the firewall clause are the real limits.

---

## 2. Requirements — the standing rules everything below must satisfy

These are not aspirations. Each exists because its absence produced a defect above.

### R1 — Identity validation at every source boundary
Any fetch that can return a *different thing than requested* must validate the response against
what it declares. Implemented for `football_data` (`Div`) and `football_data_intl` (`League`).
**Still required for:** API-Football responses (assert `league.id` and `season` in `/fixtures`
payloads match the request), ESPN (assert the returned competition slug), and any future adapter.
A cache hit must be validated on read, not just on write — the poisoned `SP2` file was already on
disk.

### R2 — Join keys must be proven unique before use
Defect #7 shipped because `(season, home, away)` *looks* unique and is not. Any merge must either
assert uniqueness on both sides or carry a key that is unique by construction (a fixture id, a
date). Add the assertion to the merge, not to a comment.

### R3 — Coverage claims are full passes, asserting the consumer's condition
Never sample. Never count a field's presence when the consumer needs its value. State the
condition being asserted alongside the number ("both teams non-null" ≠ "field present").

### R4 — API budget: separate allowances, per-kind accounting, fail closed
`ops` and `backfill` draw from separate allowances counted separately from `source_health`
(defect #3). Bulk jobs throttle at ≤50% of the plan's r/m. Every response's rate-limit headers are
asserted against the expected plan so a silent lapse to Free is an outage, not a quiet regression
to 2024-capped data.

### R5 — League rebuilds are serialized
Two concurrent `refresh-leagues` runs race on the shared `power.js`, `team-catalog.js` and
`news/*.js` artifacts; the second fails its rebase. **Enforce this in the workflow** (a concurrency
group) rather than relying on discipline — see §3.3.

### R6 — The refresh path's `--select` step runs on bare Python
Before `pip install`. Anything it imports, transitively, must import without pandas/requests
(defect #8). A test enforces this for `source_registry`; **extend it to `fast_refresh`'s whole
import closure.**

### R7 — Local league rebuilds are untrusted; CI owns payload writes
A local `build_league_data` rebuilds the *previous* season and exits 0. Source-side fixes land on
the next CI rebuild. Never rebuild locally to "verify" a data fix.

### R8 — Every published figure has one source, measured not typed
Existing CLAUDE.md rule, restated because the ELO chart violation (§1) is live. When correcting a
figure, `rg` for it across `docs/`, `CLAUDE.md`, `README.md`, `.claude/` before committing.

---

## 3. Phase 1 — Restore multi-daily updates (do this first)

**Goal: the site updates several times a day, unattended, and a failure is visible within one
cycle.** Nothing in Phases 2–3 matters until this holds.

### 3.1 Fix the MLS build (blocking, flagship league)
`build (mls)` has failed since ~08-06 on ESPN 403 for `usa.1/scoreboard`.

**Note the structural difference before starting:** MLS is **not** in `build_league_data.OUTLOOK`.
It is built by `scripts/build_dashboard_data.py` off the ASA adapter, so the Stage-0 source router
(`_routed_frame`, which only covers `OUTLOOK` leagues) **does not cover MLS at all**. Results come
from ASA; the ESPN dependency is for fixtures/rosters/scoreboard.

**Action:** enumerate every ESPN call in the MLS path; route what API-Football can serve
(MLS is `af_id` **253**, confirmed in the approved map) through a router the dashboard builder can
use — either by extending `_routed_frame`'s reach or by giving `build_dashboard_data` the same
ordered-source treatment. Keep ESPN as ordered fallback, and keep ASA primary for results (Tier C:
it is the only source of the goalkeeper z-score).
**Acceptance:** `build (mls)` succeeds with ESPN blackholed at the HTTP layer, and MLS's payload is
byte-comparable apart from `generated`.

### 3.2 Migrate Tier A in batches — the real fix for ESPN fragility
30 leagues remain ESPN-primary; each migration removes one from the circuit-breaker blast radius.
**Batch-1 pattern, proven, repeat it:**
1. Fetch the spine frame for the league's full history.
2. Diff against the ESPN frame on `(season, home, away)` — **must reach 100% scoreline agreement**
   and identical standings before anything moves.
3. The diff *generates* the name map (never fuzzy-match it — fuzzy proposed
   `Bristol City → Stoke City`, which would have attributed one club's xG to another and looked
   entirely plausible).
4. Add the registry entry spine-first with ESPN fallback; run an observation week.
**Order:** smallest/least-watched first. **Hold and record** any league that cannot reach 100%
(`costa-rica-primera` currently holds on 4 unadjudicated scoreline disagreements — adjudicate it
first, since ESPN is answering again and that window is not guaranteed).
**Acceptance per batch:** `source_health` shows the spine answering; payloads byte-comparable apart
from `generated`.

### 3.3 Enforce rebuild serialization in CI (R5)
Add a `concurrency:` group to `refresh-leagues.yml` so a second dispatch queues instead of racing.
Today the protection is that the workflow *refuses to force a data commit* — correct, but it means
a rebuild is silently lost rather than queued.

### 3.4 Make failure visible (R4/the `source_health` gap)
`source_health.parquet` is written and discarded every CI run. Options, in preference order:
1. **Publish a small health surface** — commit a compact JSON summary (per feed: last success,
   24h failure rate, rows returned) as a build artifact, and fail the workflow when a feed is dark
   for N consecutive scheduled runs.
2. Emit `::warning::`/`::error::` annotations from the guards so they surface in the run UI.
**A division mismatch, a router fallback, and a plan-lapse assertion must never be as quiet as a
routine pre-season 404.**

### 3.5 Extend the bare-Python import test (R6)
Defect #8 was one import away from the refresh path. Test `fast_refresh`'s entire import closure
under blocked pandas/requests, not just `source_registry`.

### 3.6 Fault-injection drill
Block ESPN at the HTTP layer in CI on a schedule and assert the build degrades as designed:
migrated leagues still produce payloads, unmigrated ones fail visibly, `check_docs` and the
payload-regression guard both pass. **Without this, the router rots the first time an adapter
changes.**

---

## 4. Phase 2 — Model improvement from API data

### 4.1 Port the xG KEEPs (decision pending, evidence complete)
The 2026-08-08 campaign (`scripts/xg_feature_campaign.py`, two seeds, n_bags=5, 4 folds) judged
per-league A/B where the only variable is whether xG carries values:

| League | mean Δ Brier | Verdict |
|---|---|---|
| `primeira` | −0.0055 | **KEEP** |
| `belgian-pro` | −0.0020 | **KEEP** |
| `championship` | −0.0012 | **KEEP** |
| `eredivisie` | −0.0011 | **KEEP** |
| `super-lig` | −0.0009 | marginal |
| `brazil-serie-a` | **+0.0026** | **REJECT — regresses on both seeds** |

**Action:** wire `xg_store.attach_xg` into the frame load for the four KEEPs only. **Brasileirão
must be explicitly excluded with its regression recorded in code**, or the reason will be lost and
someone will "fix" the inconsistency later. Its 100% coverage and its Stage-2 diff matching
football-data 1,140/1,140 rule out a data explanation — real xG simply makes that model worse.

### 4.2 Re-measure on the undiluted window
Every delta above is diluted ~25%: xG begins in the 2023 season while the folds run 2022–2025, so
the first fold is identical in both arms. **Re-run 2023–2025 only** to size the effects honestly —
this decides `super-lig`, and may promote `championship`/`eredivisie` from "modest" to "clear".

### 4.3 Un-mined API capabilities, ranked by expected value
All are per-fixture (~1 request per match) except where noted. None are wired.

| Capability | Model hypothesis | Cost | Risk |
|---|---|---|---|
| **Lineups** | Extends the MLS-only GK z-score to every league; confirmed-XI strength; a rest/rotation proxy | ~1/fixture; ~46k for the xG era | Publication timing — lineups land ~1h pre-kickoff, so a *forecast* feature must use them only when present |
| **Injuries / availability** | The model defines an availability family only MLS can fill | Per league-season | Historical injury data is thin; may only support forward features, which cannot be backtested |
| **Events (goal times, cards, subs)** | Time-weighted form; red-card-adjusted results; late-goal variance | ~1/fixture | Mostly narrative; weak prior for 1X2 |
| **Head-to-head** | A feature family the repo has never had | Cheap, derivable from existing fixtures | Likely subsumed by ELO; test before building |
| **Standings** | Independent cross-check of our computed tables | ~1/league/day | Not a model input — a **data-integrity** win (see §5.1) |
| **Statistics beyond xG** | Shots, shots-on-target, possession, corners, cards for **all 52 backfilled competitions** — already on disk | **Zero — already fetched** | The obvious next campaign |

**Highest-value next experiment: §4.3's last row.** 46,205 sheets are already stored and only the
xG field has been used. Shots and shot-quality features are the standard xG-adjacent signal and
cost nothing to test. Run the same two-seed A/B harness.

**`goals_prevented`** also appears in the stat sheets — a goalkeeper metric, and the only path to
extending GK features beyond MLS without lineups.

### 4.4 Campaign discipline (do not skip)
- Two seeds minimum. On 08-08, seed 42 alone read `super-lig` KEEP and `championship` noise; seed 7
  swapped them exactly. **A single seed produces a confidently wrong shortlist.**
- Per-league gating on *realised* coverage, never on "the backfill ran". Only 6 of 52 competitions
  clear a 90% usable-xG bar.
- Invariant: new features enter through a gated Brier comparison, never as a plumbing consequence.

---

## 5. Phase 3 — Data integrity as a product feature

### 5.1 Standings cross-check (cheap, high trust value)
Fetch API-Football `/standings` per league per day (~70 requests) and diff against our computed
table. A disagreement means one of: a missing fixture, a wrong scoreline, a competition-mixing bug
(#6), or a points-deduction we don't model. **Every one of those is a defect we currently discover
by accident.** This is the single highest-leverage integrity check available and costs 0.05% of
daily quota.

### 5.2 Roster/club-set validation
Defects #4 and #5 were both caught by asking *"do these clubs belong in this league?"* — a question
no automated check asks. Assert each built league's club set against the spine's roster for that
season; flag any club appearing in one and not the other.

### 5.3 Fixture-count sanity
A double round-robin of N clubs has a known fixture count. Assert it per league-season; a mismatch
catches truncation, contamination and pagination loss in one check.

---

## 6. Phase 4 — Feature and product opportunities

Ideas, not commitments. Each notes what it needs and what could go wrong.

### 6.1 Near-term, low-risk
- **Live match state** (owner deferred it, correctly, as changing the product's character). The
  roadmap idea worth revisiting: *watching live scores move season-long odds in the table*. Note
  the nuance already established — declining live scores does **not** require keeping the ESPN
  fast-refresh loop; ordinary `/fixtures` polling (~70 requests/cycle) replaces it.
- **Confirmed-XI previews** — lineups land ~1h before kickoff; "who's actually playing" is a
  high-engagement pre-match surface, and it feeds §4.3's lineup features.
- **Match narrative** from events — goal times, cards, subs for Club Watch recaps.
- **Head-to-head panels** — cheap, familiar, and derivable from data already held.

### 6.2 Expansion (the Tier D menu, owner-approved in principle)
Admission criteria, already agreed: API-Football carries fixtures + results with enough history to
seed a model; the league maintains an active continuous schedule; the format is modelable with the
existing plain-table machinery; bridge evidence optional (an unbridged league publishes a page but
stays out of Global ELO).
**Candidates:** the big-4 third tiers previously rejected for sourcing (3. Liga, Serie C,
Championnat National, Primera Federación); Czech/Croatia/Serbia/Hungary/Ukraine top flights;
second tiers under carried leagues; J2/K2/Qatar/UAE; Egypt/Morocco; women's competitions beyond the
five carried; AFC and CAF Champions Leagues (blocked on confederation offset calibration, **not**
plumbing).
**Cost:** ~1 request/day each. **The limit is surfaces to keep correct, not requests.**

### 6.3 Speculative, needs evidence first
- **Transfers** (squad churn beside Transfermarkt values) — plausible signal at season boundaries,
  where the model is weakest.
- **Referee data** — a probe already exists (`scripts/probe_referee_calibration.py`); revisit with
  the richer stat sheets.
- **Odds** — historical closing odds **do not exist** on API-Football (measured: Pinnacle is a
  listed bookmaker but `/odds` for a finished fixture returns 0 rows). Any use must be a **live
  capture at close**, not a backfill. football-data keeps the odds column meanwhile.

---

## 7. Roadmap

| Order | Work | Gate to proceed | Est. |
|---|---|---|---|
| **1** | §3.1 MLS build fix | `build (mls)` green with ESPN blocked | S |
| **2** | §3.3 rebuild serialization + §3.5 import-closure test | CI enforces both | S |
| **3** | §3.4 health surface + alerting | A dark feed alerts within one cycle | M |
| **4** | §3.2 Tier A batch 2 (Costa Rica adjudication first — ESPN is answering *now*) | 100% diff per league | M, repeating |
| **5** | §5.1 standings cross-check | Disagreements surface as warnings | S |
| **6** | §4.2 undiluted xG re-run → §4.1 port the KEEPs | Owner approves the port | S |
| **7** | §4.3 shots/possession campaign (data already on disk) | Two-seed A/B | M |
| **8** | §3.6 fault-injection drill | Scheduled, passing | M |
| **9** | §5.2/§5.3 roster + fixture-count validation | Green across 78 competitions | M |
| **10** | §6 features / §6.2 expansion | Owner picks | — |

**Sequencing logic:** 1–3 make the site trustworthy; 4–5 make it durable; 6–7 make it better;
8–9 keep it that way; 10 grows it. Do not reorder 10 above 3.

---

## 8. Edge cases to design for explicitly

Each has already bitten or is one step from biting.

1. **A source returns 200 with the wrong thing.** The redirect case (#5). Assume it recurs; it is
   *seasonal* — it appears whenever a division's season starts later than a same-numbered sibling's
   and will return around August 2027.
2. **A cache hit is poisoned.** Validate on read, not only on write.
3. **A league renames itself upstream.** `'Liga Profesional '` vs `'Liga Profesional'` — a trailing
   space, 2,114 rows, and an exact-match filter would have silently deleted a third of a league.
   Normalize, and make an undeclared value log loudly.
4. **A club renames or relocates across seasons.** Sangju → Gimcheon split one franchise into two
   ELO identities. Unify forward to the current name.
5. **Cross-tier fixtures inside a league feed.** K League's promotion playoff is round
   `"Relegation Round"` in some seasons and `"Final"` in others — the exclusion set must be
   verified per season, not assumed stable.
6. **Split seasons summed into one table.** Argentina 2026: Apertura + Clausura + interzonal,
   30 clubs, pairs meeting 3×. Needs a stage source; a competition filter cannot reach it.
7. **The subscription lapses.** Reverting to Free caps seasons at 2024 — current data would
   quietly stop updating. Header assertion makes it loud; **the plan value must be updated in both
   workflows when the plan changes.**
8. **A provider bug mid-bulk-job.** A `5xEr` "bug on our side" killed a 46k-request run at 676.
   Transient errors skip and retry; N consecutive aborts as systemic.
9. **Network timeouts in a long job.** 16 isolated read timeouts were skipped and recovered by a
   16-request rerun. Resumability is the design, not retry.
10. **Two sessions in one repo.** HEAD moves under you; a file you read may be another session's
    uncommitted work. Stage explicit paths, and **read a file before staging it if the editor
    warned it changed** — on 08-08 that warning was ignored and another session's STATUS.md work
    was committed under an unrelated message.
11. **A test clobbers real data.** Mocking `requests.get` is not filesystem isolation — a fetcher
    that persists as a side effect will overwrite the real cache with fixtures. Audit the other
    adapters' test modules for this shape.
12. **In-progress seasons look like coverage gaps.** 2026 xG is thinnest because sheets publish
    after matches. Do not read that as a source defect.
13. **A payload's own metadata drifts from its producer.** The Global ELO validator asserted
    `elo + offset` after the producer moved to `pivot + dispersion×(elo−pivot) + offset + adj`.
    Derive checks the way a *client* does, never by calling the producer (that passes
    tautologically).
14. **Off-season/dormant leagues.** ~40% of the catalogue is between seasons at any moment; a
    "no fixtures" response is normal, not a failure.

---

## 9. Open decisions for the owner

1. **Port the four xG KEEP leagues?** Evidence is complete; this is a production change.
2. **The club ELO chart vs league table contradiction** (75 clubs, ±86.3). Should a club's shrunk
   continental adjustment apply retroactively across its whole ELO history? A one-figure-two-answers
   violation is live on a public surface until this is answered.
3. **Expansion appetite, concretely** — how many Tier D competitions, and which families first?
4. **Plan after 2026-09-08** — Pro month-to-month as decided, or longer term if traffic justifies?
5. **Live scores** — still deferred, or does the season make it worth scheduling?

---

## 10. What must not regress

1. **The payload-regression guard stays authoritative.** It stopped 51 leagues silently rolling
   back a season.
2. **Training history is preserved** — 2017+ floor; no league moves to a primary that cannot reach
   it (or keeps its old source for history via the registry's ordered lists).
3. **The champion config does not change as a side effect.** Gated experiment with a Brier
   comparison, always.
4. **Provenance is published per column family** — and *verified in a built payload*, not assumed
   from code (defect #1 was exactly this assumption).
5. **No league loses xG or odds.**
6. **The free/paid boundary is untouched.** Better data does not move anything behind the paywall.
7. **Every published figure keeps one source**; `check_docs` still holds.
