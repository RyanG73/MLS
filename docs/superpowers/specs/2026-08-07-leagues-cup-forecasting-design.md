# Leagues Cup forecasting — design

**As of:** 2026-08-07 · **Owner:** Ryan · **Author:** Claude
**Status:** design, not approved, nothing implemented
**Canonical current state:** [`../../STATUS.md`](../../STATUS.md)

Owner request 2026-08-07: "do the same for the Leagues cup between MLS and Liga MX teams. note
that this is the fourth year of the competition and its rules have changed over time and need to be
accounted for in your modeling. In addition, factor in home field vs. neutral site games played at
true home or true neutral venues. the tournament just started for this year so we should have a
forecast for this tournament."

---

## Findings first — three defects, all currently shipping

A 2026 forecast **already exists and is live**: `webapp/data/leagues-cup.js`, 36 clubs, 54 league-
phase fixtures dated 2026-08-04 → 2026-08-14, champion odds led by Inter Miami 6.8%, Pumas UNAM
6.1%, América 4.8%. So the last sentence of the request is already satisfied. The three findings
below are why that forecast should not be trusted as it stands.

### 1. The 2026 tournament is running blind — no results are being ingested

Of 54 fixtures, **0 carry a result**, though the competition began 2026-08-04 and today is
2026-08-07. The cached match source `data/espn_continental/leagues-cup.parquet` holds **77 rows,
every one of them from 2024**. No 2023, no 2025, no 2026.

The payload's `status` field reads `knockout_live`, which for a tournament with zero recorded
results is an actively misleading label.

A full league rebuild was dispatched 2026-08-07 (run `31224260724`); it refreshes `leagues-cup`
for the previous and current year, so it may repair ingestion on its own. **Verify before building
anything else** — every other item here is downstream of having current results.

### 2. The simulator runs the old competition rules while the page prints the new ones

`scripts/eval/bracket_sim.py:322`:

```python
if hg > ag: pts[hi] += 3
elif ag > hg: pts[ai] += 3
else:                              # no draws -> PK decides, winner +3
    pts[hi if _pens(strengths[hi], strengths[ai], rng) == 0 else ai] += 3
```

The published `rules` string in `scripts/build_continental_data.py` says the opposite:

> "3 points for a win, 1 for a draw, no group-stage shootout"

The simulator awards 3 points to a shootout winner and 0 to the loser. The page tells a reader
draws are worth 1 point each. One of these is the 2026 competition and the other is 2023-24.

Two aggravating details:

- **`"no_draws": True` in `FORMATS` is never read.** The shootout branch is unconditional. The flag
  is decorative, so today the model has no way to express a competition that allows draws.
- The 2024 data confirms which rule was which: **24 of 77 matches finished level in regulation and
  all 24 recorded a winner**, including 15 of 15 in the group stage. Shootouts were real in 2024.

### 3. The "draw" is not a draw — fixtures are decided by alphabetical order

`bracket_sim.py:317`:

```python
a = A[k]; b = B[(k + gi) % len(B)]
```

Each club plays the club at a rotating index of the other league's list, and those lists arrive in
field order, which is alphabetical — the payload's Liga MX table begins América, Atlante, Atlas,
Atlético de San Luis. So a club's three opponents are a deterministic function of its name, the
same in every one of the N simulations.

This is the same class of defect as the UEFA league-phase draw (see the companion spec), but more
severe: UEFA at least permutes once with a seed. Here there is no randomisation at all, and no
schedule uncertainty reaches the published numbers.

---

## The venue question — measured, and the effect is large

`neutral` is `False` on **all 77 cached rows**, and `_sim_match(..., False, ...)` hardcodes the same
in the group phase. Every nominal home team therefore receives full home advantage.

That is wrong for this competition in a way the data shows plainly:

| Split (2024, n=77) | Rate |
|---|---|
| Home win, all matches | **44.2%** |
| Away win, all matches | 24.7% |
| Drawn in regulation | 31.2% |
| **Liga MX club as nominal home team** (n=25) | **28.0%** |

A nominal home side wins 44.2% of the time overall, but a Liga MX side listed as home wins 28.0% —
barely above the 24.7% that *away* teams manage. The reason is not subtle: in 2023–2024 every
Leagues Cup match was played in the United States or Canada, so a Liga MX club designated "home"
was playing at an MLS venue or a neutral American one. It received the home label without the home
advantage, and the model has been handing it the advantage anyway.

**Caveat, stated because n is small:** 25 matches is thin, and club strength is confounded with the
split — if the Liga MX clubs drawn as nominal hosts happened to be weaker, some of the gap is
theirs, not the venue's. The design below therefore proposes *fitting* the venue effect jointly
with strength rather than adopting 28% as a constant. The directional finding is solid; the
magnitude needs the fit.

---

## Design

### A. Per-edition format registry

Replace the single `FORMATS["leagues-cup"]` entry with a per-season mapping, so a simulation of any
edition runs that edition's rules. The registry must carry, per season: club count, phase shape,
matches per club, whether own-league matchups occur, the points rule (shootout vs draw), the
knockout ladder, and the venue policy.

What is **established from repo data**:

- **2024** — 47-ish club field; rounds present in the parquet are group-stage (45), round-of-32
  (16), round-of-16 (8), QF (4), SF (2), third place (1), final (1). Own-league matchups existed
  (29 MLS-v-MLS, 4 LigaMX-v-LigaMX). Shootouts on level regulation scores.
- **2026** — 18 MLS + 18 Liga MX, three cross-league matches each, two separate 18-club tables,
  never facing or ranked against own league, top 4 per table to the quarter-finals, 3 points for a
  win and 1 for a draw. (Source: the competition's own `rules` string, which describes 2026.)

**2023 resolved 2026-08-07** via API-Football (league id **772**; its free plan serves 2022–2024).
Both early editions are now established from data rather than memory:

| Season | Fixtures | Shape | Level matches |
|---|---|---|---|
| 2023 | 77 | 15 groups of 3 (45 matches) → R32 · R16 · QF · SF · 3rd · Final | **23 to penalties** |
| 2024 | 77 | identical | **24 to penalties** |

A 47-club field: 45 clubs in fifteen three-club groups playing two matches each, plus two seeded
byes straight into a 32-team knockout. Both decided level matches by shootout — the opposite of the
current edition's "1 for a draw". Both had own-league ties (Orlando City v Houston Dynamo in 2023's
group stage; 29 MLS-v-MLS in 2024), so the two-table shape is wrong for both.

**2025 remains unverified and is deliberately not described.** API-Football's free plan stops at
2024 and the repo holds no rows for it. It is the transition year between the two shapes, so it is
exactly the season a guess would most likely get wrong. It is recorded as unsupported and raises.

### B. Venue model

Add a venue class per fixture rather than a boolean:

| Class | Meaning | Lambda treatment |
|---|---|---|
| `true_home` | host is playing in its own stadium | full home advantage |
| `neutral` | neither side is at home | no home advantage |
| `road_home` | nominally home, but in the opponent's country or a third venue | no home advantage, or a fitted partial |

`match_lambdas(sh, sa, neutral, conf)` already accepts a neutral flag, so the change is to carry a
venue class on each scheduled fixture and resolve it there, plus extend the schedule tuples that
`_simulate_two_table` builds.

Then **fit the Leagues Cup home advantage on Leagues Cup matches** rather than inheriting the
Concacaf constant. There is direct precedent: `HOME_ADV` became per-competition on 2026-08-07
after a 19-league sweep showed a single flat value was optimal in zero of them, and
`scripts.eval.elo.home_adv_for` is already the single source every build path calls.

Whether 2026 uses Liga MX venues at all is a **data question**, not a modelling one — resolve it
from the fetched fixtures before choosing the 2026 venue policy.

### C. Draw randomisation

Replace the alphabetical rotation with a sampled cross-league pairing under the competition's real
seeding constraints, and follow the UEFA spec's approach: sample S schedules and run N/S
simulations against each, so the vectorised goal draw survives. Report a club's advance probability
with its spread across schedules.

### D. Forecast for the live 2026 edition

Once A–C are in and ingestion is confirmed, the existing pipeline produces the forecast — this
slice is mostly *correctness*, not new machinery. Two presentation fixes belong with it:

- `status` must distinguish "league phase in progress" from `knockout_live`.
- Results must appear as they land; a tournament three days old showing 0 of 54 results is the
  visible symptom of finding 1.

### E. Historical backtest

Same structure and the same hard constraint as the UEFA spec: **club strengths must be
reconstructed as of each edition's first fixture**, or the backtest scores a model that already
knew the answers. With per-edition formats in place (A), replaying 2023–2025 becomes possible;
without them it would replay every season under 2026's rules and report a number about nothing.

Sample size must be published beside any score. Three or four editions is very thin.

---

## Data-quality issue noticed in passing

The Liga MX table in the live payload includes **Atlante**, which is a Liga de Expansión club rather
than a Liga MX one. Either the ESPN roster is stale or club resolution has placed it wrongly. This
is the failure mode `scripts/eval/continental_resolve.py` was written to prevent, and its docstring
already warns that names alone are insufficient across these confederations. Worth confirming
against the refreshed roster before the field is trusted — a wrong club in the field is a wrong
forecast for every club in that table.

---

## Proposed sequence

1. **Verify ingestion** from the dispatched rebuild. Everything else depends on it, and it may
   already be fixed.
2. **Per-edition format registry (A)** — without it the model cannot be right about any season but
   the current one, and cannot be backtested at all.
3. **Venue model (B)** — the largest measured bias, and self-contained once A exists.
4. **Draw randomisation (C)** — shared approach with the UEFA spec; do them together if both are
   approved.
5. **Backtest (E)** — last, because it should measure the corrected model.

Items 2 and 3 change the live 2026 numbers. That is the point, but it should be a deliberate
decision rather than a side effect, and the change in champion odds should be reported before and
after.

## Open questions for the owner

1. **Does the live 2026 forecast stay up while this is fixed?** It is currently running on
   alphabetical fixtures, the wrong points rule, and an unearned home advantage for Liga MX clubs.
   Leaving it up is defensible — it is a projection, not a claim of accuracy — but it is the
   owner's call, and pulling it is also reasonable.
2. **2023 backfill.** Is one edition of extra history worth an explicit fetch, given the backtest
   sample is tiny either way?
3. **Third-place match.** Present in 2024 and named in the 2026 rules, but absent from the `ko`
   ladder in `FORMATS`. Should it be modelled, or explicitly declared out of scope like the
   unmodelled barrages elsewhere?
