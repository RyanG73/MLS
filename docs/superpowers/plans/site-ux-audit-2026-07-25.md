# Full site UX review — mobile & desktop (`docs/site-ux-audit-prompt.md`)

Run 2026-07-25. Three lenses: production in the Chromium pane, production in the iOS Simulator
(iPhone 16 Pro Max, iOS 18.6), fixes on `http://localhost:8123`. Every surface treated as
unreviewed; all numbers measured, read twice, never taken from a screenshot.

## Verdicts

### 1. Home — `/` · ISSUES (2 bugs, 5 violations) — fixed

| metric | before (375) | after |
|---|---|---|
| AA contrast failures | 175 | **0** |
| elements < 11px | 117 | 66 (all badge glyphs, 0 content) |
| distinct font sizes | 20 | 16 |
| search input | 12px / 28px tall | 16px / 44px |
| iOS focus zoom | **zooms, never restores** | none |

- **BUG — iOS focus zoom made the Account tab unreachable.** `.mast-search input{font-size:12px}`
  → Mobile Safari zooms any field under 16px on focus and does not zoom back on blur. The page
  stayed scaled past the viewport and the 5th bottom-nav destination was pushed off-screen.
  Chromium cannot surface this class of bug at all — it reported zero overflow at all eight widths.
  Fixed to 16px + `min-height:44px`; verified in WebKit that focus no longer changes layout.
- **VIOLATION — semantic colour.** `moversRow()` coloured on `delta` sign alone, so
  "FC Botosani · Relegation ▲100.0" rendered in qualification green while the hero showed the same
  datum in amber. Now keyed on valence (relegation inverts); arrow still tracks raw direction, so
  colour never carries the meaning alone.
- **VIOLATION — `--txt-3` failed AA on three of four surfaces.** The 2026-07-23 pass set `#6b7d71`
  and recorded "4.58:1 — clears WCAG AA", but measured it against `--ink-0` only. The token is used
  207× and almost always sits on a panel: 4.46 / 4.38 / 4.05 on `--ink-1/2/3`. **172 of 175 Home
  failures were this one token.** Now `#738579`, solved against the lightest surface it lands on →
  4.85 / 4.72 / 4.64 / 4.53. This single change took 11 of 12 routes to zero contrast failures.
- **VIOLATION — heading outline.** Six visible section headings were `<div class="ed-sec">`, so the
  outline ran H1 → H4 with nothing between. All 12 converted to `<h2>`. Skip-link added.
- **VIOLATION — type floor.** 117 elements under 11px; ten rules raised.

### 2. Matches / edge board — `?league=command` · ISSUES (2 violations) — fixed
- **Type floor 248 → 16**, the worst surface measured, and it was the core product numbers: 87 odds
  prices at 8.5–9px, 29 kickoff times, 29 draw probabilities, 75 calendar labels. Nine rules raised;
  verified `.drw`/`.ko` (both `white-space:nowrap` in a 313px card) do not clip.
- Contrast 197 → 0 via the token.
- **Clean:** console silent; odds-format toggle converts every price in place
  (`+232 → 3.32 → 37/16`) and persists; no banned copy.

### 3. Leagues index — `?league=leagues` · ISSUES (1 bug, 2 violations) — fixed
- **BUG — 78 pin stars were dead controls for keyboard users.** `.lx-star` is a `<span>` nested
  inside the league `<a>`; it mutates `pitchside.favLeagues` on click but had no `tabindex`/`role`
  and was not in the tab order, so tabbing to a row and pressing Enter navigated instead of pinning.
  There was no way to pin a league without a mouse. Now `role=button` + `tabindex=0` + `aria-pressed`
  + per-league `aria-label` + Enter/Space handler + focus ring. Verified all four behaviours.
- 44×44 hit area achieved with `margin-block:-10px` so the 78-row list keeps its density
  (row 48 → 50px, not 63px).
- Type floor 92 → 5.

### 4. League detail — `?league=epl` · ISSUES (2 violations) — fixed
- **Type floor 319 → 24** (100 form-box labels at 8px, 96 heat cells at 10px, 60 chips at 8.5px).
- **Table a11y + ID leakage:** the season-outcome table exposed raw internal metric keys as column
  headers (`conf`, `europa`, `releg`, `ucl`) and had no `scope` on any `th` and no accessible name.
  Now human labels via `OSK_LABEL`, `scope="col"`/`scope="row"`, `aria-labelledby`.
- Fixed a **pre-existing** clip: "Europa" needed 36px in a fixed 34px column; reclaimed via
  `letter-spacing:0` rather than truncating a competition name or widening every column.
- **Reverted two of my own bumps** (`.tlad .thead`, `.acc-lbl`) after measuring that 11px clipped
  inside fixed-width grid columns. Documented as constrained exceptions rather than shipped broken.
- Canonical correctly swaps to `/leagues/epl/`.

### 7. Results-only — `?league=poland-ekstraklasa` · CLEAN
`data_status: results_only` renders a settled final table, not a live forecast: Pts == Proj
(60|60, 56|56), 34 GP, outcome columns show settled `100`/`·` rather than forward probabilities,
and an explicit note reads "results only — no fixture feed for this league, projections use played
matches". Reading the column *names* alone would have produced a false finding; the values are what
confirmed it.

## Site-wide sweep after fixes (12 routes, 375px)

Contrast **0 on 11 of 12** (support: 1). No horizontal overflow on any route. Non-badge text under
11px remaining: `/` 0, command 0, leagues 0, epl 20, mls 56, libertadores 17, poland 16,
**power 299**, account 8, support 0, intel 31, 404 0.

## Open — needs a decision, deliberately not shipped

1. **Desktop buries volatile content.** At 1280×800 (fold y=800) reference tables own the first
   screen at y=461 while Upcoming Matches sits at y=1266 and Biggest Movers at y=1514. Mobile was
   already fixed for exactly this; desktop kept the old order. Reordering `grid-template-areas` is
   one line but it changes information architecture → proposal, not a unilateral edit.
2. **Tablet dead zone.** The only breakpoint is `max-width:900px`; 768–900px gets the mobile stack
   stretched to a ~880px single column.
3. **Type scale is systemically sub-floor.** 105 of 401 `font-size` declarations remain under 11px
   (39 at 10px, 19 at 10.5, 15 at 9…). Raising all of them is a type-scale change across 17
   surfaces that trades against the contract's "dense" direction — one decision, not 105.
4. **Contract drift** (amend `system.md`, not the site): Georgia serif carries the wordmark and all
   8 editorial headings but is not in the contract; 5 drop shadows on overlays vs "no decorative
   shadows" — both are the shipped behaviour being better than the doc.

## Not reached
Static pages (14, 15), 404 treatment beyond route probe, PWA installed mode (17), Intel paid/gated
(10, 11) — Intel needs `./scripts/intel_preview.sh`. Landscape and iPad WebKit not exercised.

---

# Feedback batch 2026-07-25 (masthead, RSS, crests, season state)

Second pass the same day, from a 14-item user list. Four items shipped and verified, two
investigations closed with findings, eight remain open (tracked at the bottom).

## 5. Masthead — SHIPPED
- Continent icons removed. The `REGION_MARK` boxes ("NA"/"EU"/"AS") read as a different visual
  language than the country flags beside them. Country flags kept — they are flags, not badges.
- **Rankings tab removed entirely.** Note: `?league=power` had no other entry point anywhere in
  the app, so the cross-league Power Rankings view is now unreachable from the UI. The route still
  resolves for anyone holding the URL. Flagged, not decided.
- **MLS promoted to the top bar**, directly after England. It stays inside the Americas menu too,
  so both routes reach it; the Americas item no longer highlights when MLS is the active league.
- Verified in the pane: bar reads Home · Matches · England · MLS · Spain · Italy · Germany ·
  France · Americas · Europe · Asia · Africa · Intel · Account, `region-mark` count 0.

## 6. Masthead dropdowns — SHIPPED
- Rows now group under a country heading, countries A–Z, continental cups collected into one
  trailing "Continental" section. Within a country, leagues sort by tier.
- Per-row country flag and the "Spain · tier 1" subtitle were redundant under a country heading;
  subtitle is now the tier alone and the flag moved to the heading.
- Column layout switched from CSS grid to CSS **multi-column**. Grid would put one country per
  cell and leave ragged gaps; `columns` + `break-inside:avoid` keeps a country intact and flows
  naturally. Column thresholds now count country sections, not league rows.
- Verified: Europe menu renders 17 sections Austria→Turkey + Continental, 3 columns.

## 7. Women's leagues — SHIPPED
- `women: true` added to the registry, sourced from a new `WOMENS` set in `fetch_league_teams.py`
  (8 leagues). Deriving it from `espn_code` would have been wrong — NWSL is `usa.nwsl`, no `.w.`.
- Rendered as a **"W" badge**, not a "(W)" name suffix: several women's sides share a club name
  with the men's outright (Barcelona in Liga F, Arsenal in the WSL, Tenerife in Liga F vs Segunda),
  so the marker has to survive truncation and stay scannable. Applied in the masthead and the
  Leagues hub.
- `webapp/leagues.js` patched in place rather than regenerated — `fetch_league_teams.main()` hits
  the network and clobbers built payloads for any league still marked "soon".

## 8. RSS never refreshed — ROOT-CAUSED AND FIXED
`scripts/build_news.py` ran **only** in the local `scripts/daily_build.sh` (launchd), never in
either GitHub Actions workflow. Since the live site moved to CI refresh+deploy, payloads rebuilt
nightly while the news rail did not. Evidence: `webapp/data/news/*.js` last written **2026-07-13**,
payloads generated 2026-07-25 — 12 days stale.
Added to `refresh-daily.yml` and `refresh-leagues.yml`, non-fatal (`|| echo`) so a dead outlet
cannot cost the run its payload commit — the bug #2 lesson. Verified: all 9 feeds live, 78 league
files rewritten.

## 9. Crests matched to the wrong club — ROOT-CAUSED AND FIXED
Far worse than reported. `build_logo_map.py` kept ONE flat `{normalised_name: url}` index and
matched into it by substring guarded only by `len >= 4` **characters**. `norm()` strips club
tokens (SC/CD/FC/Club), and the pool holds single-word short-name aliases, so:

| crest | was worn by |
|---|---|
| Carlisle United | Bangkok, Buriram, Muangthong, Chiangrai, BG Pathum, Ayutthaya, Chippa, Sekhukhune, Canberra, JEF, NorthEast, Fort Lauderdale, HERA — **13 clubs** |
| Atlético Madrid | Junior, Goianiense, Bucaramanga, Grau, Mictlán, Rafaela, Nacional, Morelia, La Paz, Alianza — **10 clubs** |
| Sporting CP | Sporting Cristal, Defensor Sporting, Sporting Delhi, Sporting San Miguelito |
| FC Barcelona | **Barcelona SC (Ecuador)** — the reported case |
| Everton FC | Everton CD (Chile) |
| Orlando City | Orlando Pirates (South Africa) |
| Philadelphia Union | Union Omaha, Unión La Calera |
| Independiente (ARG) | Medellín, Santa Fe, del Valle, Petrolero |

**71 clubs wore another club's crest.** Fixed by resolving narrowest-scope-first — country →
confederation → global — and refusing the global step for keys claimed by more than one country.
Continental payloads already tag each club with its domestic league (Libertadores rows carry
`league: "ecuador-ligapro"`); the builder was discarding it. Substring matching additionally
requires a **whole-token prefix** against a **multi-token key**, which is what kills
`united`→everything, `albion`→West Brom, `adt`→Darmstadt, `port`→Portland Timbers.

Down to **10 collisions, all structural**: `window.TEAM_LOGOS` is keyed by NAME, so Liverpool
(Uruguay) and Liverpool (England) — also Santos, Platense, Alianza FC, Athletic, Aurora, Nacional,
Atlanta, San Antonio, Toronto — cannot both be right in a name-keyed map. Real fix is keying by
`(league_id, name)` or the `team_id` payloads already carry, plus every webapp consumer. Not
bolted on here. `tests/test_logo_map.py` (21 tests) locks the win and lists the 10 as a
known-limitation set that fails if it grows *or* silently shrinks.

## 10. Season-state tracker — SHIPPED (private)
`scripts/season_state_report.py` → `output/season-state.md` (gitignored, never reaches webapp).
Status is a *fixture-feed* decision, not a calendar one: a league parks on `completed` from its
last match until its source publishes the next schedule, and nothing watched that gap.

Current state: **29 leagues showing a dead final table ≥45 days**, worst offenders Canadian
Premier League (**623 days**, 2024 table), K League 1 (**608 days**, 2024), Leagues Cup (**327
days**). Also surfaced a second and nastier failure mode the request did not mention — leagues
still *labelled* live while months idle: Vrouwen Eredivisie (64d, still on 2025), Libertadores
(57d), J1 League (49d). A stale "completed" is honest; a stale "live" actively claims a current
projection.

## 11. Liga MX playoffs — INVESTIGATED, premise partly incorrect
- `season: 20` is **not** a bug. Liga MX uses sequential torneo ids (Clausura 2017 = 1 … Apertura
  2026 = 20) with the label in `outlook.season_label` ("Ap.2026").
- The Liguilla **qualification** column exists and is correct: `outlook.columns` carries
  `{key: liguilla, top: 8}`, every club has a probability, and they sum to 799.9 ≈ 8 × 100%.
- What is genuinely missing is the **bracket**: no champion probability, `title_by_playoff: null`.
  And this is systemic, not Liga MX–specific — **no domestic championship playoff is simulated
  anywhere except MLS.** Affects liga-mx, liga-expansion-mx, nwsl, usl-championship,
  usl-league-one, usl-super-league, northern-super-league, canadian-pl, india-isl,
  costa-rica-primera, elsalvador-primera, guatemala-liga, honduras-liga, australia-aleague(-women).
  `_promo_playoff_winner` already simulates *promotion* playoffs, so the machinery exists.
- Separately, `format_approximate` is applied inconsistently: belgian-pro, greek-super and
  eredivisie all describe an unmodelled split/playoff in `rules` while reporting
  `format_approximate: False`.

## Still open from this batch
Matches-to-watch feature draft · cross-league ELO for continental competitions · retention
features · European market analysis · sub-daily refresh cadence · post-season ELO recalibration by
club tier · playoff-bracket simulation (the item 11 finding) · Leagues Cup 2026 projections.

---

## 12. Leagues Cup 2026 — SHIPPED · and the root cause was bigger than the symptom

The page showed the 2025 champion because **continental competitions were never rebuilt in CI**.
`build_continental_data.py` ran only in the local `scripts/build_all.sh` — the identical omission as
`build_news.py` (item 8). All seven comps (UCL, Europa, Conference, Concacaf Champions, Leagues Cup,
Libertadores, Sudamericana) were frozen at whatever the last local run produced.

Two code defects on top of the missing CI step, both of which would have re-broken it next season:

1. `latest_season()` reads **results**, and an edition that has not kicked off has none — so the
   builder was structurally pinned to the last COMPLETED season for ever. Added `_roll_forward()`,
   which probes for published fixtures and only ever moves forward.
2. `_resolve_field()` returned `[]` when a season had no results, so even at the right season there
   was no field to simulate. It now falls back to the fixture list.

ESPN had the full 2026 field the whole time: 54 matches, 36 clubs, Aug 4–14. Now building —
advance probabilities sum to exactly 4.000 per table (top 4 of each), champion odds to 99.9,
Inter Miami favourite at 6.0%. The group/knockout layout the request asked for already existed and
renders correctly once real data reaches it: two 18-club tables with ADV, a Knockout tab with
round-by-round QF/SF/Final/Win odds, and the format explainer.

Continental rebuilds + `build_logo_map.py` + `build_news.py` added to both workflows, each non-fatal.

## 13. Championship playoff brackets — SHIPPED
The item-11 finding, fixed. `_championship_winner()` simulates the post-season for leagues whose
title is decided in a bracket rather than by the table, and a `Champion` column now sits beside the
qualification column.

Implemented as **one general re-seeded ladder**, not a table of hand-written shapes: each round the
survivors re-sort by original seed, the top seeds take byes until the field is a power of two, and
best-remaining plays worst-remaining with the better seed hosting. That is literally how the
Liguilla works (Liga MX re-seeds every round), and it handles any field size — the first draft was
a shape table and a new test immediately crashed it on a 5-seed field.

Enabled where the real format is a standard seeded ladder: **liga-mx, liga-expansion-mx, nwsl,
usl-league-one, usl-super-league, northern-super-league, india-isl**. Deliberately NOT enabled for
costa-rica-primera, honduras-liga, guatemala-liga, elsalvador-primera (Apertura/Clausura grand
finals), australia-aleague(-women) (double-chance finals series) or usl-championship
(per-conference bracket) — those keep honest qualification-only odds rather than a confidently
wrong champion number.

Liga MX now reads: title sums to 100.0, Liguilla to 800.1, no club's title exceeds its
qualification odds, and conditional win rates run 20.4% for the top seed down to ~6% for marginal
qualifiers against a 12.5% coin-flip baseline — the right shape for a seeded 8-team bracket.

**SIM PORTING CONTRACT honoured.** `champWinner` in index.html mirrors the Python. The first
version shipped silently broken: `champ_playoff` was not in the whitelist that forwards bucket
fields into `outlook.columns`, so the client had nothing to branch on and the what-if reported 0%
for every club while the server showed real numbers. Now verified in the browser — client and
server agree to within 0.6pp across the top 8 at 20k sims, inside Monte-Carlo noise. The whitelist
carries a comment about exactly this failure mode.

`tests/test_championship_playoff.py` (18 tests): bracket returns a real seed for every field size
1–8, oversized fields truncate rather than crash, better seeds win more, and every shipped payload
stays coherent (title ≈ 100, title never exceeds qualification).

Suite: **1453 passed, 7 skipped**.

---

## 14. Post-season ELO recalibration by club tier (the AC Milan case) — INVESTIGATED, NOT SHIPPED

The observation is correct and reproducible. Serie A preseason 2026:

| club | ELO | proj pts | title% |
|---|---:|---:|---:|
| Inter | 1785 | 80.5 | 48.9 |
| **Como** | 1658 | 73.6 | **19.2** |
| Roma | 1681 | 72.0 | 15.2 |
| **AC Milan** | 1635 | 58.0 | **1.0** |

Como — promoted from Serie B in 2024 — projects second and nineteen times likelier to win the
league than Milan.

**The mechanism the request asks for already exists, and is deliberately restricted.** There is a
preseason value-informed ELO correction (`build_league_data.py`, M2/A10(a), 2026-07-07): fit
`log(squad value) → ELO`, then tilt fixture log-odds by `β·(value_elo − elo)` with β=0.5. It is
gated to clubs **at or below the league median ELO**. The comment records why: an untargeted tilt
was A/B tested and rejected — relegation Brier improved −0.0055, but title Brier degraded +0.005
because the tilt drags title odds toward the richest club.

Milan sits at 1635 against a 1542 median, so it receives **exactly zero** correction — while having
the **largest positive value-vs-ELO gap in the league** (+50: value implies 1685, ELO says 1635).
The gate is inverted with respect to precisely the case that motivated the request.

### The blocker: the squad-value data is corrupt

Before extending the tilt upward, the input has to be trusted, and it cannot be.

- Inter's 2026 squad value reads **€28.37m**, against €680.1m in 2025.
- **13.5% of big-5 rows (132 of 976) are under €60m**, which is implausible for a top flight.
- The affected clubs are the *largest* ones: Bayern Munich (€20.46m, 2019), Real Madrid (€21.28m,
  2020), Barcelona (€20.41m, 2022), PSG (€21.35m, 2021), Chelsea (€20.59m, 2024), Liverpool
  (€20.82m, 2022). Every season 2017–2026 is affected; 2026 is the worst at 23 rows.
- The values cluster around €20–30m for clubs worth €700m–1bn, which is about the size of an
  **average per-player value**. Working hypothesis: the scraper intermittently reads Transfermarkt's
  "ø value" (per-player average) column instead of total market value. Serie A 2026 also has 21 rows
  for a 20-team league, so there is a duplicate/mapping fault too.

Consequences, in priority order:

1. **This is already user-visible.** `squad_value` is rendered on team pages
   (`index.html:3277`, `€{...}m`) and drives the `value_rank_gap` diagnostic — so the site is
   currently telling readers Inter's squad is worth €28m.
2. **The bottom-half gate is accidentally load-bearing.** It shields the model from the corruption,
   because the mis-parsed clubs are almost all top-half. Extending the tilt to top-half clubs — the
   obvious fix for Milan — would hand Inter a −600 gap × β 0.5 = **−300 ELO tilt** and wreck Serie A.
3. Only after the data is fixed does the modelling question become answerable.

### Recommended order
1. Fix the Transfermarkt parse (chase the ø-value hypothesis), backfill 2017–2026, add a validator
   that fails when a big-5 squad reads under, say, €60m or drops >60% year over year.
2. Re-fit `log(value) → ELO` on clean data and re-measure the rejected untargeted tilt — the +0.005
   title regression was measured on corrupt inputs and may not survive.
3. Only then test the tier-aware variant the request describes. The specific hypothesis worth
   testing is an **asymmetric, divergence-gated** tilt — correct only where value and ELO diverge
   beyond a threshold, and consider correcting upward only — rather than the symmetric untargeted
   version that was already rejected. Uniform 40% season regression treats a fallen giant and a
   genuine mid-table club identically, which is the structural reason Milan stays pinned.

Gate every step on the 4-fold challenger report per `CLAUDE.md`; the champion is avg 0.6330.

---

## 15. Transfermarkt squad-value parse — FIXED (2026-07-26)

**Correction to the item-14 note above:** the corruption was NOT user-visible. Team pages read
`build_squad_value_league()`, which sources the *worldfootballR* R bridge
(`data/transfermarkt_squad_values_<CODE>_<season>_mapped.csv`) and is healthy — Serie A 2026 shows
Inter €680.8m, Milan €533.0m. The corrupt file is `data/transfermarkt_backfill/values.csv`, a
separate regex scrape whose only consumer is the preseason ELO value tilt. Model-internal, not
customer-facing.

### Cause
`scripts/eval/tm_value_backfill.py` parsed with one regex over raw HTML,
`title="([^"]+)".*?€([\d.]+)(bn|m)`, plus a `v > 20` floor "to skip player-value cells". The real
row is:

```
<td class="zentriert no-border-rechts"><a title="Bayern Munich" ...crest
<td class="hauptlink no-border-links"><a title="Bayern Munich" ...name
<td class="zentriert"><a title="Bayern Munich" ...>38</a>      squad size
<td class="zentriert">24.2</td>  <td class="zentriert">21</td> ø age, foreigners
<td class="rechts">€20.46m</td>                     <-- ø MARKET VALUE
<td class="rechts"><a ...>€777.33m</a></td>         <-- TOTAL market value
```

`title="Bayern Munich"` appears three times per row, so the non-greedy `.*?` resolved to the ø
(per-player average) cell — and an elite squad's per-player average clears a €20m floor, so the
guard passed it. The floor was not just useless, it was the thing that let the error through.

### Fix
Structural parse: locate the value column by HEADER TEXT ("Total market value"), read cells
positionally, fall back to the last money cell in the row (never the first — that is always the ø).
Row matching is scoped to the first `<table class="items">` so other page tables stop leaking in —
Bundesliga 2019 was yielding 23 "clubs" for an 18-team league.

### Result
Full re-scrape, 2017–2026 × big-5. 976 → 972 rows; **85 repaired**; every league-season now has
exactly 18 or 20 clubs, zero duplicates.

| club | before | after |
|---|---:|---:|
| Manchester City 2026 | €44.79m | **€1,500m** |
| Real Madrid 2026 | €44.74m | **€1,430m** |
| PSG 2025 | €37.29m | **€1,370m** |
| Bayern Munich 2019 | €20.46m | **€777.33m** |
| Inter 2026 | €28.37m | **€688.80m** |

The 52 rows still under €60m are all genuine — every one ranks 15th–20th in its own league-season
(Paderborn, Greuther Fürth, Le Mans, Monza, Leganés).

### It moved the model more than expected
The tilt only touches bottom-half clubs, and the repaired rows are nearly all top-half — but the
corrupt values were in the `log(value) → ELO` **fit**, so a €44m Manchester City was flattening the
slope and inflating every modest club's value-implied ELO. Rebuilt big-5:

- **La Liga**: Elche −6.1 proj pts (relegation 2.8% → 9.1%), Alavés −5.8 (4.0% → 12.0%), Osasuna −5.6
- **Serie A**: Frosinone +4.6 pts, relegation **35.1% → 21.6%**
- **EPL**: max 1.1 pts — barely moved

### Guardrails
`validate()` checks each league-season's SHAPE, not individual numbers, because a plausible value in
the wrong column is the failure mode that hid for years. The decisive assertion: a big-5 season whose
*richest* club is under €200m is the ø column, not the total. Called from `run_backfill` (loud, but
still writes — a partial scrape is easier to inspect than to reproduce).
`tests/test_tm_value_backfill.py` — 18 tests, including an offline HTML fixture that pins Bayern to
€777.33m rather than €20.46m, bn→m scaling, and a check that the committed table passes `validate()`.

Suite: **1471 passed, 7 skipped**.

### Still open (unchanged from item 14's recommended order)
Step 2 — re-measure the value tilt on clean data. Its original validation (relegation Brier −0.0055,
title +0.005 → untargeted variant rejected) was measured on the corrupt fit, so the rejection may not
survive. Only then is the tier-aware AC Milan variant answerable. Note this path lives in
`build_league_data.py`, not `eval_baseline.py`, so the 4-fold champion gate does not directly cover
it — `scripts/eval_season_outcomes.py` is the closer validator.

---

## 16. Dixon-Coles predict path — 40% off every build (2026-07-26)

Profiling for the refresh-cadence question found the cost of a build is not the simulation at all:
20,000 sims and 2,000 sims both took 67s, because **84% of the time is retraining the model**
(`walk_forward_predictions`), and over half of that was one function.

`_dc_predict` ran an 81-cell Python loop making two `scipy.stats.poisson.pmf` **scalar** calls per
cell — 162 per match, ~1.9M per league build, 52s. The same file's `_dc_nll` had already been
vectorised for exactly this reason, carrying a comment that reads "~500× faster per call"; the
predict path was simply missed. Rewrote it as a closed-form Poisson outer product
(`exp(k·ln(m) − m − lgamma(k+1))`) with the Dixon-Coles τ patched into the low-score 2×2 block
instead of branched on per cell. Also removed three redundant identical `dc_predict_batch(cal, …)`
calls feeding two calibrations of the same fold.

**67.2s → 40.4s, output bit-identical**: max absolute difference 2.2e-16 across 2,280 predictions
spanning three ρ and two HFA values, and every `perf_by_year` Brier unchanged. 1,471 tests pass.

## 17. Product & strategy pack — `docs/product-strategy-2026-07-26.md`

Covers the four remaining requests. Headlines:

- **Matches to Watch** — working prototype at `scripts/match_leverage.py`, conditional-simulation
  leverage (pin each fixture to H/D/A, measure expected L1 movement in table odds). Whole world,
  121 fixtures, **8 seconds**, no refit and no network. It works: the top Brazilian fixture is
  Mirassol v Remo (relegation ±15.6pp), not the marquee Internacional v Flamengo. It also exposed a
  ranking flaw worth knowing before building — raw leverage over-rewards small volatile leagues, so
  the global board fills with Bolivian relegation six-pointers. Fix is three rails (yours /
  league-normalised / around-the-world), not a different metric.
- **Retention** — the diagnosis is right: a probability is a purchase trigger, not a habit trigger.
  Ranked list; the load-bearing four are Matches to Watch, a pre-match "what's at stake" card, a
  personalised accountability page, and a season-long prediction game (the only mechanic that
  creates a *decaying personal stake*).
- **Europe** — the binding constraint is regulatory, not competitive. Italy's Decreto Dignità bans
  gambling advertising and affiliate marketing outright; Spain restricts affiliates and PPC exactly
  as it does operators; seven regulators have formed a joint enforcement coalition explicitly
  targeting affiliate networks. **The betting-edge framing is close to unmarketable in the biggest
  markets.** Recommendation: lead with forecasting, sequence UK → Netherlands/Nordics → Germany →
  Italy/Spain (analytics-only), and compete on *breadth* (78 competitions incl. tiers 3–5 and
  women's) where Opta and Understat go deep on the big five and free.
- **Refresh cadence** — yes, 15–30 min is reachable, but by splitting refit (daily) from reproject
  (fast path), not by making the build faster. The real blocker is the **deploy**, not the compute:
  every refresh redeploys the whole site and bumps the service-worker cache. Recommendation is a
  data-only publish path so the shell deploy stays daily. The Odds API free tier (500/mo) is the one
  hard cost ceiling; decouple odds from model refresh.

## Still open from the original 14-item list
**Cross-league ELO for continental competitions** — bundled into the ELO option but not started.
`experiments/league_offsets.json` currently anchors MLS, Brazil, EPL, Japan, Saudi, China, India,
Thailand, K-League and Australia at exactly 0.0, i.e. uncalibrated, so those confederations are not
mutually comparable. The request's own suggestion is the right method: fit offsets from actual
cross-confederation results (Club World Cup, Concacaf Champions Cup, AFC/CAF competitions,
intercontinental friendlies) and fall back to historical odds where matches are too sparse.
`scripts/eval/continental_calibrate.py` already does this within CONMEBOL and is the place to extend.

---

## 18. Cross-league ELO across confederations — SHIPPED (2026-07-26)

The last open item from the original 14.

### The problem
`league_bridge.fit_offsets` fits league offsets INSIDE a confederation, each group
anchored at its own reference pinned to 0.0 (UEFA→epl, CONMEBOL→brazil-serie-a,
Concacaf→mls, AFC→japan-j1). So MLS and EPL both read 0.0 — which never meant they were
equal, it meant **nothing at all**, because no match in the fitting data connected them.
`coefficients.league_offset` said so in its own docstring; the power-rankings page told
readers the scales "don't connect across"; and CONMEBOL, AFC and CAF were simply left off
that page because their numbers would have been uninterpretable next to a European one.

### The evidence
The **FIFA Club World Cup** is the only competition in the dataset where confederations
actually meet. Added as `club-world-cup` (ESPN `fifa.cwc`, calendar-year): 133 completed
matches 2015-2025, 64 from the expanded 32-club 2025 edition. Resolving both clubs to a
modeled domestic league by ESPN team id leaves **60 inter-confederation matches**.

Records in that data, which is what the fit is reading:

| confederation | W-D-L | points per game |
|---|---|---:|
| CONMEBOL | 10-7-14 | 1.19 |
| AFC | 8-3-13 | 1.13 |
| Concacaf | 3-5-15 | **0.61** |

### The method
One free parameter per confederation — a whole-scale shift — with UEFA pinned at 0:

    strength = domestic_elo + league_offset(league) + C[confederation]

Within-confederation offsets are **untouched**; this never re-litigates validated work.
Ridge-regularised toward an explicit prior rather than left to overfit, because 60
matches for four parameters is thin and CAF has three. The prior encodes conventional
wisdom (CONMEBOL −80, Concacaf/AFC −210, CAF −250) so that where the data cannot speak
the published number is a considered default rather than noise.

| confederation | prior | fitted | moved | matches |
|---|---:|---:|---:|---:|
| UEFA | 0 | 0 | — | 39 |
| CONMEBOL | −80 | **−110** | −30 | 31 |
| AFC | −210 | **−228** | −18 | 24 |
| CAF | −250 | **−268** | −18 | 3 |
| Concacaf | −210 | **−275** | −65 | 23 |

### Validation
Mean held-out Brier over **200 random 25% splits** (a single split is worthless here —
the first run of this script printed "ADOPT" off a 15-match split on which the fit was
actually *worse* than the prior alone, which is why the verdict logic now requires
beating the prior too, by more than its own standard error):

| model | Brier |
|---|---|
| **fitted shifts** | **0.5411 ± 0.0033** |
| prior only | 0.5453 ± 0.0031 |
| all-zero (previous behaviour) | 0.6056 ± 0.0022 |
| naive base rates | 0.5961 ± 0.0034 |

**−0.065 Brier against what the code did before.**

### The safety property
A constant added to every league in a confederation **cannot** change a within-
confederation projection, because `match_lambdas` consumes the strength DIFFERENCE and
the constant cancels. Asserted directly in `tests/test_interconf_calibrate.py` and
`test_league_bridge.py`. Every continental competition we build is single-confederation
(UCL/Europa/Conference all UEFA, Leagues Cup and Concacaf Champions all Concacaf,
Libertadores/Sudamericana all CONMEBOL), so **no existing projection moves.** Only
cross-confederation comparisons — previously unfounded — change.

### Fixed on the way
`continental_resolve.team_name_index` looked leagues up in `build_league_data.OUTLOOK`
and defaulted `source` to `"espn"`. MLS is not in OUTLOOK (it is built by
`build_dashboard_data.py` off the ASA parity frame), so every lookup raised "Unknown
league 'mls'" and **every MLS club silently failed to resolve in every cross-league fit
touching Concacaf** — 12 Concacaf-UEFA meetings were being seen as 7. Now routed the same
way `league_bridge._build_elo_history` already did; the two must agree or a club resolves
in one and not the other.

### Result
Power rankings now carry all six panels on one ladder, and the page copy no longer tells
readers the scales don't connect. Best club per confederation, global rank in brackets:

    Bayern Munich 1770 (1) · Palmeiras 1610 (24) · Al Hilal 1563 (44)
    Mamelodi Sundowns 1494 (80) · Cruz Azul 1397 (186)

Al Hilal at 44 and Palmeiras at 24 are consistent with the 2025 tournament (Al Hilal beat
Manchester City; Palmeiras reached the quarter-finals). **Cruz Azul at 186 is the number
to be sceptical of** — it follows from Liga MX going W2 D4 L11, and it is a strong claim
resting on 23 matches. Revisit after the next edition.

### Caveats worth keeping
- One shift per confederation means a strong Liga MX side and a weak MLS side move
  together; the within-Concacaf gap is still just the +30 Liga MX edge fitted elsewhere.
- CWC participants are champions, not representative clubs. Each club's own domestic ELO
  absorbs most of that, but any difference in ELO *spread* between leagues lands in the
  shift.
- CAF rests on three matches and is prior-dominated by design — a test asserts it has not
  wandered more than 100 points from the prior.

Suite: **1487 passed, 7 skipped**.

---

## 19. Season rollover — SHIPPED (2026-07-26)

24 leagues were showing a dead final table 45+ days old; nine had next-season fixtures already
public. Two source paths never consulted the feed for a NEW season:

- **`source == "espn"` had no pre-season flip at all** — 30 of 78 leagues, the largest source
  group. `ts` derives from max_played_season, so they waited for ESPN to report RESULTS rather
  than a schedule. `espn_results_frame` already returns played AND scheduled rows, so the
  fixtures were in `frame` the whole time; the season selector never advanced to them.
- **`footballdata_intl` only ever asked ESPN for the CURRENT season.** Its comment argued a
  flip-ahead check "would fire mid-season and wrongly treat an in-progress season as done" —
  true unguarded, since some leagues publish fixtures months ahead.

Both now roll forward **guarded on the current season having nothing left to play**, which
removes exactly that hazard. Controls verify it: chile-primera and brazil-serie-b (espn,
mid-season) and japan-j1 (FDI, 200 played + 200 upcoming) all stay put.

Rolled: eerste-divisie (380 fixtures), saudi-pro (306), liga-f (240), australia-aleague (156),
austria-bundesliga (132), france-premiere-ligue (132), usl-super-league (56), honduras-liga (30).
**24 → 16 idle.** The rest are genuine source gaps — eight feeds with nothing published, the
UEFA cups (2026-27 draw is late August; `_roll_forward` takes them automatically), and three on
SOURCE_BLOCKED where API-Football's free plan caps out.

`tests/test_season_rollover.py` — no league two seasons stale, "preseason" payloads have
fixtures, "completed" ones do not, and the blocked list stays honest (that last test immediately
rejected finland-veikkausliiga, which tracks fine via FIXTURE_OVERRIDE).

## 20. AC Milan / value tilt — the gate was wrong, and the corrupt data is why

The original request: recalibrate post-season ELO so underperforming rich clubs aren't pinned to
bad form. The mechanism already existed and was **gated to below-median-ELO clubs**, so AC Milan
— above the median, and holding the largest positive value-vs-ELO gap in Serie A — received
exactly zero correction.

That gate came from a 2026-07-07 A/B measuring +0.005 title Brier for the untargeted variant.
**That A/B ran on the corrupt value table** fixed in item 15: Manchester City read €44m, Real
Madrid €45m, which flattened the log(value)→ELO slope and made an untargeted tilt push nonsense
at the top of the table. Re-run on clean data (big-5, 2018–2025, 800 team-seasons, preseason):

| arm | title | ucl | releg | sum |
|---|---:|---:|---:|---:|
| no tilt | 0.03162 | 0.09436 | 0.11426 | 0.24024 |
| bottom-half (old production) | 0.03166 | 0.09459 | 0.10305 | 0.22930 |
| **untargeted — promoted** | 0.03224 | **0.08728** | **0.10198** | **0.22150** |
| up (never demote) | 0.03153 | 0.08950 | 0.10720 | 0.22823 |
| gap ≥ 40 | 0.03258 | 0.08848 | 0.10292 | 0.22398 |

The title penalty is **+0.0006** — an eighth of the corrupt-data figure — and buys −0.0073 on
UCL qualification. Confirmed at seed 7 (0.22980 → 0.22178, same margin). Broad-based: Bundesliga
−0.0148, Serie A −0.0132, Ligue 1 −0.0112, EPL −0.0072 on UCL; La Liga +0.0090 the exception.

Gate removed. **AC Milan preseason 2026: UCL 26.6% → 37.8%, title 1.0% → 3.0%, proj 58.0 → 60.8.**
Como stays high (22.7% title) — that is *supported* by the value data, not a model error: Como's
€437.9m squad is 5th in Serie A after heavy spending.

The tilt gate is now a knob (`--value-gate bottom|all|up|gap`) so this is re-testable rather than
re-argued, and `tests/test_value_tilt.py` fails loudly if the median gate returns without a fresh
A/B. Tracked baseline `experiments/season-outcomes-baseline.report.json` regenerated.

**The general lesson worth keeping:** a modelling decision is only as good as the data it was
measured on. This gate looked like a considered trade-off for nineteen days and was actually an
artefact of a regex reading the wrong HTML column.

---

## 21. Matches to Watch — SHIPPED (2026-07-26)

The §1 prototype promoted to a built payload + rendered feature.

**Metric change from the draft: leverage now sums over EVERY club, not just the two
playing.** That is the literal request — "the biggest swing in **table odds**" is a property
of the table, not of the two teams — and it changes the ranking materially. Brazil, same
week: pair-scope leads with Mirassol v Remo (13.2), all-scope with Internacional v Flamengo
(36.3) and promotes Vitória v Palmeiras to 3rd because a title race moves everyone.
`--scope pair` keeps the old behaviour.

**Static payload, not an Intel-hub API feature.** The hub is auth-gated and team-scoped, but
leverage is a property of the FIXTURE. `scripts/build_match_leverage.py` →
`webapp/data/match-leverage.js` (122 KB, 321 fixtures, 29 leagues, 7-day horizon), and the
client intersects it with FavStore for the personal rail — personalisation with no auth
round-trip, and the hub can consume the same file when it wants to.

**Three rails**, mounted on the Matches page:

| rail | ranking | why |
|---|---|---|
| Your matches | pinned leagues/teams by leverage | never empty, never irrelevant |
| Biggest swing in each league | one fixture per league, tier-ordered | lets a big-five game compete |
| Around the world | raw global leverage | the exotic rail, labelled as such |

Rail 2 needed two fixes the draft did not anticipate. Sorting by percentile alone reproduced
the world rail exactly — every league's top fixture ties at pct 1.0, so the sort fell through
to raw leverage. It now dedupes to one fixture per league and orders by league TIER.

Cost: the whole board is 8 seconds at 2,000 sims and needs no model refit and no network — it
reads the per-fixture probabilities the payloads already publish. Wired into both refresh
workflows, non-fatal, after the league builds.

`tests/test_match_leverage.py` (8) pins the properties rather than the values: non-negative and
bounded, percentile monotone in leverage within a league and reaching 1.0, ranks dense and
ordered, a dead rubber scores ~0, and a title-deciding fixture scores 5× a dead one.

Also caught: `match-leverage.js` carries `status: "live"`, which would have spawned a bogus
`build (match-leverage)` matrix job in refresh-daily. Added to that filter and to
`validate_payloads._NON_PAYLOAD` — one change fixing both the payload-contract and
registry-drift tests.

**Known limitation, deliberately shipped:** rail 2 is South-America-heavy right now because the
European leagues are in preseason with nothing played, so their fixtures carry little leverage.
That is correct behaviour in late July and rebalances once seasons start — worth re-checking in
September rather than tuning against a preseason snapshot.
