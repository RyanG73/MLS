# UEFA competition forecasting — design

**As of:** 2026-08-07 · **Owner:** Ryan · **Author:** Claude
**Status:** design, not approved, nothing implemented
**Canonical current state:** [`../../STATUS.md`](../../STATUS.md)

Owner request 2026-08-07: "a full historical forecast, cross league elo impact, and upcoming
season forecast for the uefa champions league, conference league, and europa league. include
qualifying rounds, randomness related to the unknown results of the league phase draw as well as
knockouts all the way to the final." All four slices below were selected by the owner.

---

## What already exists

This is not a greenfield build. Roughly 60% of the request already ships.

| Piece | State | Where |
|---|---|---|
| UCL / Europa / Conference sims | ✅ built and live | `scripts/eval/bracket_sim.py` `FORMATS` |
| 36-team league phase, 8 matches each (6 for Conference) | ✅ | `FORMATS[*].phase` |
| Top 8 auto-advance, 9–24 play-off, two-legged R16→SF, neutral final | ✅ | `FORMATS[*].ko` |
| Champion odds, per-club advance odds, published payloads | ✅ | `webapp/data/{ucl,europa,conference}.js` |
| Cross-league strength scale | ✅ calibrated | `scripts/eval/cross_league.py` |
| Field resolution when a season has no results yet | ✅ | `build_continental_data._resolve_field` |

The cross-league layer the request asks for is **already the most recently calibrated part of the
system**: `_CONF_CONST["UEFA"]` was fitted on 2026-08-06 against 743 cross-league continental
matches, replacing hand-typed priors that predicted 39.5% home wins against an actual 50.3%.
Continental results also already feed back into club strength through
`coefficients.club_continental_offset()`. **Slice-level work on "cross-league ELO impact" is
therefore not proposed here** — it exists, it is fitted, and re-opening it needs a measured reason.

The 2025-26 editions are concluded in the payloads: PSG (UCL), Aston Villa (Europa).

---

## Slice 1 — League-phase draw randomness and pot seeding

**This is a live defect, not a missing feature. It should ship first and separately.**

`make_league_schedule(field, matches_each, seed)` builds **one** schedule and
`simulate()` reuses it across all N simulations:

```python
schedule = make_league_schedule(field, fmt["phase"]["matches_each"], seed)
_, _, order_arr = _sim_league_vectorized(schedule, strengths, N, rng, conf=conf)
```

Two consequences:

1. **Every published league-phase probability is conditional on a single arbitrary fixture list.**
   A club's "top 8" number reflects the specific eight opponents that one draw handed it. The
   quoted uncertainty is goal-level noise only; draw-level uncertainty is absent.
2. **Pot seeding is not implemented at all.** `make_league_schedule` places clubs on a randomised
   circle and pairs neighbours. The competition's own `rules` string on the page advertises
   "4 pots of 9" — so the site currently describes a draw structure its model does not run.

### Real rule to implement

36 clubs in 4 pots of 9 by coefficient. Each club plays 8 matches — two against each pot, one home
and one away. No club faces another from its own association, and at most two from any single
association. Conference plays 6 matches on the same pot logic.

### Approach

Sample **S distinct schedules** and run N/S simulations against each, rather than resampling per
simulation. The reason is mechanical: `_sim_league_vectorized` precomputes a lambda per scheduled
match **once**, outside the N loop, and then draws all goals as one `(N, n_matches)` Poisson block.
Per-simulation redrawing destroys that vectorisation and makes the run ~N times more expensive.
S≈200 batches of N/S captures draw variance at ~S/N of the cost.

The pot-constrained draw is a constraint-satisfaction problem that can dead-end. Use the standard
approach: attempt a randomised assignment, and on failure retry with a fresh seed rather than
back-tracking; log the retry rate so a structurally impossible constraint set is visible instead of
silently looping.

### Acceptance

- A club's advance probability is reported with its spread **across** schedules, not only within one.
- Association constraints hold in 100% of sampled draws (assert in test, not by inspection).
- If the measured spread turns out to be negligible, **say so in the payload and the docs** — that
  is a real finding and it retires the concern honestly. Do not ship a more expensive model that
  buys nothing and claim it as an improvement.

### Risk

Low and contained. One function, one file, no data dependency, no new source.

---

## Slice 2 — Upcoming-season (2026-27) forecast

`_resolve_field` already falls back to published fixtures when a season has no results:

> `[%s] %d season has no results yet — resolving the field from %d published fixtures`

So **once the draw happens, an upcoming-season forecast largely works today.** The hard case is the
window the request actually asks about: *before* the draw, when ESPN has no fixtures and the
entrant list does not exist.

### Approach

Build a **probabilistic field**. The site already forecasts, for every modelled domestic league,
each club's probability of finishing in a Champions League / Europa / Conference position — those
are the `ucl`, `europa` and `conf` buckets in `build_league_data._TOP`. So:

1. Sample an entrant list by drawing domestic finishing positions from the existing season sims.
2. Map positions to competition slots per association.
3. Run the competition sim on that field.
4. Repeat, and aggregate over both the field uncertainty and the match uncertainty.

This is the honest structure: a pre-draw forecast *should* be wider than a post-draw one, and this
makes the extra width come from the right place.

### Known unmodellable inputs — state them, do not fake them

- **Domestic cup winners** take a Europa/Conference slot in most associations. The site does not
  model domestic cups. Precedent exists for exactly this admission in `_TOP`'s comment
  ("domestic-cup-winner spots are unmodelable and omitted, so these are approximate").
- **Association coefficient slots** shift year to year (England and Italy had 5 UCL places for
  2025-26). These must be read from a dated table, not hardcoded.
- **Unmodelled leagues.** Entrants from associations the site does not model have no domestic
  forecast to sample from and need a coefficient-based prior.

### Acceptance

- A pre-draw forecast is visibly wider than the same competition's post-draw forecast.
- Every slot whose occupant is guessed rather than modelled is counted and published.

### Risk

Medium. The sim is reused unchanged; the work is field construction and slot bookkeeping.

---

## Slice 3 — Qualifying rounds

Currently excluded by explicit design, and documented as such in both the code and each
competition's public `rules` string.

### Why this is the largest slice

It is not one competition's problem. UEFA qualifying is a **cascade across all three**: the
Champions Path and League Path run separate ties; UCL losers drop into the Europa League; Europa
losers drop into the Conference League. Modelling it for one competition in isolation would produce
a field that contradicts the other two. `bracket_sim` today has no representation for a club
entering from another competition's failure — the same limitation already documented for the
Sudamericana R16 inflow.

### Approach

A joint pre-tournament stage that runs before all three competition sims:

1. Seed the qualifying bracket from association coefficients and domestic finishing positions.
2. Play the qualifying rounds (two-legged, existing `sim_two_leg`).
3. Route losers to the next competition down, per the real path rules.
4. Hand each competition its resulting 36-club field.

This makes slices 2 and 3 naturally one pipeline: qualifying *is* how the upcoming-season field is
determined for the clubs that do not enter directly.

### Prerequisite to verify before committing to this slice

Whether the ESPN feed carries qualifying-round fixtures and results under the existing comp slugs
(`uefa.champions`, `uefa.europa`, `uefa.europa.conf`) or under separate qualifying slugs. **If the
data is not available, this slice cannot be validated and should not ship** — an unvalidatable
qualifying model is worse than the current honest exclusion.

### Risk

High. New data dependency, cross-competition coupling, and the largest surface for a confidently
wrong number.

---

## Slice 4 — Historical backtest

`value_layer.backtest` is `null` in all three payloads. Nothing exists.

### The one constraint that decides whether this is worth anything

**Ratings must be reconstructed as of the start of each replayed season.** Today's `global_elo`
already encodes those seasons' results — scoring a 2023-24 forecast with 2026 ratings would report
an accuracy the model never had. This is leakage, it flatters the result, and it is the single
easiest way to make this slice actively misleading.

`compute_elo` is already a walk-forward routine, so as-of ratings are obtainable; the work is
plumbing a date cutoff through field construction and strength lookup, and asserting it.

### Approach

1. For each past edition, rebuild the field from that season's actual entrants.
2. Recompute club strengths using only matches before that season's first fixture.
3. Run the competition sim.
4. Score against actual outcomes: Brier on advance-to-each-round and on champion, plus a
   calibration curve.

### Acceptance

- A leakage test that fails if any rating used post-dates the replayed season's first fixture.
- Published per-edition, alongside the existing calibration reporting rather than as a new surface.
- Sample size stated next to every score. Four editions of a 36-club competition is a small sample
  and the report must not imply otherwise.

### Risk

Medium. The danger is a plausible, leaky number rather than a broken build.

---

## Proposed sequence

1. **Slice 1** — fixes a live defect, contained, no data dependency.
2. **Slice 4** — so later slices are measured against a scored baseline. Depends on 1, because a
   backtest should measure the model that ships.
3. **Slice 2** — reuses the sim; the work is field construction.
4. **Slice 3** — largest, gated on the data check above, and subsumes part of slice 2.

Each slice gets its own implementation plan and ships independently. Slice 1 should not wait for
agreement on slice 3.

## Open questions for the owner

1. **Publication surface.** Do the upcoming-season and backtest numbers belong on the existing
   competition pages, or is a pre-draw forecast a different enough object to deserve its own?
2. **Paywall.** `CLAUDE.md` locks the continuity layer and never a published figure. A pre-draw
   forecast is a *new* figure, so it is not covered by that promise either way — it is a free
   choice, and it is the owner's.
3. **Slice 3 gate.** If ESPN does not carry qualifying data, is a lower-fidelity qualifying model
   worth having, or is the current explicit exclusion preferable?
