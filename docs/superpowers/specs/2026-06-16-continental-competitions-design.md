# Continental Competitions — Cross-League Knockout Modeling (Design)

*Date: 2026-06-16. Status: approved design, pre-implementation.*

## Goal

Add predictive modeling for the 6 scaffolded continental competitions — UEFA
Champions League, Europa League, Conference League (UEFA) and Concacaf Champions
Cup, Concacaf League, Leagues Cup (Concacaf) — to the multi-league platform.
"Predictive" means cross-league strength estimates → group/league-phase standings
odds + knockout-bracket advance odds + win-the-cup odds per team, on the same
prediction/edge mission as the rest of the platform.

These are **cross-league knockout** tournaments: a single tie can pit an EPL team
against a La Liga team, whose domestic ELOs are each anchored to 1500 independently
and are therefore **not comparable**. Solving that comparability is the core of this
work. The project docs have repeatedly flagged this as "a separate effort"; this is
that effort.

## Decisions (locked with the user, 2026-06-16)

1. **Ambition: full predictive model** (not display-only). Cross-league strength +
   bracket Monte-Carlo + advance/champion odds.
2. **Unmodeled entrants: external strength-prior fallback.** Teams from leagues we
   don't model (Portuguese/Dutch/Belgian in UCL; Central-American/Caribbean in
   Concacaf) get a strength estimate from an external anchor placed on the common
   scale. **v1 anchor = UEFA club coefficient** for Europe and the Concacaf club
   index for Concacaf (both free, official, no scraping); squad market value is a
   documented future alternative, not built in v1. **No new per-league data builds**
   — scope stays bounded.
3. **Cross-league strength method: Approach A (external-coefficient anchor),
   structured so Approach C (bridge-regression refinement) is a drop-in upgrade.**
4. **Build order: UCL vertical slice first**, validate end-to-end, then generalize
   to the other 5 (each becomes a config + coefficient table).
5. **Webapp: two sub-tabs** under League Projections — a League-Phase table and a
   Knockout bracket — driven by the comp's format spec.

## Non-goals (YAGNI)

- No changes to `models/research_model.py`, the MLS champion, the promotion gate,
  or any existing league build. New files only, plus one webapp mode branch and the
  registry status flips.
- No what-if force-results simulator for the **knockout** bracket in v1 (the
  league-phase table inherits the existing table what-if for free; the bracket is
  inert). A force-a-tie-winner resimulate is a later enhancement.
- No bridge-regression (Approach C) in v1 — the seam is designed in, the
  implementation is deferred.

## Architecture

The model is reused, not modified. Everything below the cross-league strength layer
(ELO, Poisson→1X2) is existing pure-function machinery. New components compose it.

| File | Purpose | Depends on |
|------|---------|-----------|
| `data_pipeline/coefficients.py` | League + club strength anchors (UEFA league coefficients, Concacaf index, club coefficients) → ELO points. Static, periodically-refreshed dicts with dated source comments (like `trophies.py`). No scraping in the build path. | — |
| `scripts/eval/cross_league.py` | Core. `team_strength(team, league)` = within-league ELO + `Δ_league` (modeled) **or** coefficient-derived (fallback). Match model: strength_diff → 1X2 probs and → Poisson λ/μ scorelines. | `scripts/eval/elo.py`, `coefficients.py` |
| `scripts/eval/bracket_sim.py` | Generic group/knockout Monte-Carlo engine driven by a per-comp **format spec**. Produces league-phase standings AND bracket advance odds. | `cross_league.py` |
| `data_pipeline/espn_continental.py` | Fetch continental results + fixtures by ESPN slug + format (generalizes `espn_soccer.py`). Parquet-cached, timeout+verify+cache-fallback discipline. | — |
| `scripts/build_continental_data.py` | Build: resolve field → strengths → bracket MC → `webapp/data/<comp>.js`. Mirrors `build_league_data.py`. `--comp ucl`. | all above |
| `scripts/validate_continental.py` | Walk-forward backtest on historical continental results; calibrates + validates the 3 constants. Mirrors `validate_league.py`. | `cross_league.py`, `espn_continental.py` |
| `webapp/index.html` | New `outlook.mode === 'knockout'` branch + `renderKnockout()` two-sub-tab container. | — |

**Data flow:** ESPN field/fixtures + coefficient tables → `cross_league.team_strength`
per entrant → `bracket_sim` Monte-Carlo → standings + advance/champion odds payload →
webapp knockout view.

## Cross-league strength + match model

**Strength scale** — every team is a single number on a common ELO-point scale:

```
strength(team) = within_league_ELO(team) + Δ_league       # modeled teams
strength(team) = anchor_to_elo(club_coefficient)           # unmodeled fallback
```

- `within_league_ELO` from the existing `compute_elo` snapshot of the team's domestic
  league (already cached by the league builds — no re-fetch).
- `Δ_league = k · (league_coefficient − ref_league_coefficient)`. `ref_league` = the
  strongest modeled league (EPL), anchored at Δ=0; other leagues shift down by their
  coefficient gap. `k` = one fitted slope constant.
- `anchor_to_elo` maps an unmodeled club's coefficient onto the same scale via the
  same `k`, so e.g. Porto and Arsenal become comparable.

**A-baseline, C-ready:** `Δ_league` and `anchor_to_elo` are isolated behind functions
in `cross_league.py`. Approach C (bridge regression) replaces **only** how `Δ_league`
is computed — fitting offsets from historical continental results instead of
coefficients — with zero change to the simulator or webapp. That function boundary is
the seam.

**Match model** — scorelines are needed (two-leg aggregate, away goals, ET, pens), so
each match is independent Poisson:

```
λ_home = base_goals · exp( β·(strength_home − strength_away) + home_adv )
λ_away = base_goals · exp( β·(strength_away − strength_home) )
```

Neutral-site finals drop `home_adv`. Poisson → 1X2 / scoreline reuses the existing DC
engine's score-matrix machinery, fed by cross-league strength instead of within-league
attack/defense.

**Three calibrated constants:** `k` (coefficient→ELO slope), `β` (strength→goals
sensitivity), `base_goals` (≈1.35). Fit once on historical continental results
(Brier-minimizing), validated on held-out later seasons, then frozen in
`cross_league.py` as documented constants — same discipline as the ELO grid search.

## Bracket simulator

A declarative **format spec** per comp drives one engine:

```python
"ucl": {
  "phase": {"type": "league", "teams": 36, "matches_each": 8,
            "auto_advance": 8, "playoff": (9, 24)},   # new UCL format (2024-25+)
  "ko": [{"round": "R16", "legs": 2}, {"round": "QF", "legs": 2},
         {"round": "SF", "legs": 2}, {"round": "Final", "legs": 1, "neutral": True}],
  "away_goals": False, "extra_time": True, "pens": True,
}
```

`bracket_sim.simulate(field, fmt, N)` runs N Monte-Carlo tournaments:
- **League/group phase:** simulate each scheduled match (Poisson scores) → standings →
  resolve auto-advance / playoff / eliminated per spec.
- **Two-leg KO:** simulate both legs (home/away swap), aggregate; away-goals if the
  comp uses it, else ET (home_adv-neutral mini-Poisson) then penalties (slight favorite
  via a logistic on strength_diff, near-50/50).
- **Single-leg neutral final:** one match, no home_adv, ET+pens.
- Accumulate → per-team **advance% at each round + win-the-cup%**, and league-phase
  **standings** with bucket probabilities.

**Season timing:** in-season with a drawn bracket → simulate the real bracket (live
odds). Out of season (the field isn't drawn yet) → show the **completed** bracket with
resolved results — the same "finished" treatment the European leagues use now. Live
odds activate at the next draw.

## Payload schema

Extends the existing payload; `outlook.mode = "knockout"`. Carries BOTH structures
because the simulator produces both:

```js
outlook: { mode:"knockout", confederation, format_label,
           phases:["league","knockout"],   // or ["knockout"] for pure-bracket comps
           rounds:[...] }
standings: [ {team, league, pts, auto_advance, playoff, eliminated,
              reach_R16, reach_QF, reach_SF, reach_Final, win, logo, color} , ... ]
field: [ {team, league, strength, modeled:true|false, logo, color,
          odds:{R16, QF, SF, Final, win}} , ... ]
games: [ {round, leg, home, away, pH,pD,pA, lam,mu, hg,ag,result, mkt_*, edge_*} ]
champion_odds: [ {team, win_pct} , ... ]   // sorted leaderboard
```

`standings` matches the shape `renderTableOutlook` already consumes. `games` keeps the
existing match-card shape, so Match Projections + `edgePick()`/`mkt_*` edge fields work
unchanged.

## Webapp

One new mode branch, mirroring the existing `isTable` split:

```js
const mode = (D.outlook||{}).mode;          // 'table' | 'knockout' | undefined(MLS)
const isKnockout = mode === 'knockout';
```

`renderKnockout()` is a **two-sub-tab container** in League Projections:
- **"League Phase" sub-tab → table.** Reuses the `renderTableOutlook` ladder: a single
  table with bucket cut-lines relabeled **top-8 auto-advance (green) / 9–24 playoff
  (amber) / 25–36 eliminated (red)**, columns for P(auto-advance), P(playoff),
  P(eliminated), and carry-through P(reach each KO round) + P(win). Inherits the
  existing what-if force-results simulator for free (it's a table).
- **"Knockout" sub-tab → bracket strip.** R16→QF→SF→Final left-to-right, each tie's
  teams + model win-prob; champion-odds leaderboard alongside. A badge marks
  `modeled:false` (coefficient-only) teams so coarser estimates are visible. Inert in
  v1 (no force-resim).

**Format spec decides which sub-tabs appear** via `outlook.phases`: league+knockout
comps (UCL, Europa, Conference, Leagues Cup) show both; pure-bracket comps (Concacaf
Champions Cup) show only Knockout.

**Reuse, not new infrastructure:** Match Projections, Teams, Model Health tabs are
already league-agnostic and unchanged. Colors via existing `BRGB` (add `advance`/`win`
keys).

## Data adapter notes

- `espn_continental.py`: `continental_results(comp_id)` (completed matches, round/stage
  from ESPN `season.slug` / `competitions[].notes`) and `continental_fixtures(comp_id)`
  (upcoming; undrawn ties absent until the draw). ESPN's competitor objects carry a
  league hint used to tag each entrant's domestic league for the strength lookup; an
  `ESPN→modeled-league key` name-map (like `FD_ESPN`/`espn_name`) handles name
  mismatches.
- **Leagues Cup data gap:** the registry has `slug=None`. It is MLS vs Liga MX (both
  modeled — the cleanest data of any comp). Resolve its real ESPN slug during
  implementation (likely `usa.leagues_cup` / a Concacaf slug); if none exists it is the
  one comp that may need an alternate source. Not a UCL blocker — flagged for the
  Concacaf generalization phase.

## Validation & testing

The MLS promotion gate does **not** apply (it guards the MLS champion on the parity
frame; this is a separate model surface).

- `scripts/validate_continental.py`: walk-forward by season on historical continental
  results — model Brier vs naive vs market (football-data.co.uk odds where they cover
  continental matches, via the existing de-vig path). Also where `k`/`β`/`base_goals`
  are fit (earliest seasons) and validated (held-out later seasons). Success: model
  beats naive and isn't embarrassed by the market (the goals-only-league bar).
- **Behavior-preservation guardrails:** `make parity-check` PASS |Δ|=0.0000 (MLS
  champion untouched) after the webapp edit; `make test` (109) green; MLS + all 12
  existing leagues render unchanged.
- **New unit tests:** `tests/test_cross_league.py` (strength composition, Poisson match
  model, monotonicity, unmodeled fallback), `tests/test_bracket_sim.py` (format-spec
  resolution, two-leg/away-goals/ET/pens, advance% sums per round, league-phase
  buckets), `tests/test_coefficients.py` (coefficient→ELO mapping, missing-team
  fallback).
- **In-browser close-out:** build UCL, confirm both sub-tabs render (league table with
  cut-lines; bracket with champion odds), match cards + edges work, MLS/existing
  leagues regression-clean — then flip UCL `soon→live`.

## Implementation order (vertical slice → generalize)

1. `coefficients.py` (UEFA league + club tables) + `tests/test_coefficients.py`.
2. `cross_league.py` (strength + match model) + `tests/test_cross_league.py`.
3. `bracket_sim.py` (format spec + engine) + `tests/test_bracket_sim.py`.
4. `espn_continental.py` (UCL results + fixtures).
5. `validate_continental.py` — calibrate `k`/`β`/`base_goals` on UCL history, confirm
   beats naive.
6. `build_continental_data.py` (`--comp ucl`) → `webapp/data/ucl.js`.
7. Webapp `renderKnockout()` + two sub-tabs; in-browser verify; parity-check; tests.
8. Flip UCL `soon→live`.
9. Generalize: Europa, Conference (same UEFA format + coefficients), then the Concacaf
   comps (Concacaf index, format variants; resolve Leagues Cup slug).
