# League Expansion Feasibility Report

*2026-07-09 · prepared for UI feedback round 3 ("write a report of all leagues around the world we should consider expanding to — rank by feasibility")*

> **2026-07-24 update — Round 6: ESPN's catalog is now exhausted. +20 leagues, registry 56 → 76.**
> User decision: "add them all to whatever extent possible… projections only is ok."
>
> **Method change from earlier rounds — candidates were enumerated, not guessed.** Previous rounds
> probed plausible slugs one at a time (round 5 burned four guesses proving K League 1 has none).
> This round pulled ESPN's own league index —
> `sports.core.api.espn.com/v2/sports/soccer/leagues?limit=1000`, **220 entries** — and diffed it
> against the 50 slugs already wired across `espn_fixtures.SLUGS` and `espn_continental.SLUGS`.
> That is the definitive frontier: anything absent from those 220 is not on ESPN at any slug.
>
> **Shipped (20).** CONMEBOL: `brazil-serie-b` (bra.2), `argentina-nacional` (arg.2),
> `ecuador-ligapro` (ecu.1), `paraguay-primera` (par.1), `bolivia-profesional` (bol.1),
> `venezuela-primera` (ven.1). Concacaf: `liga-expansion-mx` (mex.2), `usl-league-one` (usa.usl.l1),
> `costa-rica-primera` (crc.1), `honduras-liga` (hon.1), `guatemala-liga` (gua.1),
> `elsalvador-primera` (slv.1). CAF: `south-africa-psl` (rsa.1). AFC: `india-isl` (ind.1).
> Women's: `liga-f` (esp.w.1), `france-premiere-ligue` (fra.w.1), `vrouwen-eredivisie` (ned.w.1),
> `australia-aleague-women` (aus.w.1), `northern-super-league` (can.w.nsl), `usl-super-league`
> (usa.w.usl.1). All `source="espn"` goals-only → projections-only, no odds, no edge product.
>
> **Season shape, again the trap.** Round-5 Gotcha #1 applied at scale: every candidate was
> classified from a **monthly event histogram over 2025**, not a first/last-date span. Eight are
> genuinely calendar-year; twelve are Aug–May straddles with an off-season gap the span check would
> have missed. Central America's gap is only ONE month (June) because Apertura starts late July and
> Clausura ends May — a naive span check calls those calendar-year and slices both tournaments in half.
>
> **Gotcha — `_PROMO(promo, play, rel)` cannot express direct promotion.** It always emits a
> `{"band": play}` playoff bucket, and `_bucket_idx` would read `band: None` for a league that
> promotes straight off the table. Brazil Série B (top 4 up, bottom 4 down, 38-round double
> round-robin, no post-season) needed the new `_PROMO_DIRECT`. Kept as a separate helper rather than
> making `play` optional so the promotion-playoff sim (`_promo_playoff_winner`) stays unreachable for
> these leagues. A second new helper, `_PLAYOFFS`, covers the far more common round-6 shape where the
> table only decides playoff berths and the championship bracket is not simulated.
>
> **Deliberately NOT shipped — the 4 continental cups.** `conmebol.libertadores`,
> `conmebol.sudamericana`, `afc.champions` and `caf.champions` all resolve live with real fixtures,
> and `build_continental_data.py` already handles bracket formats. The blocker is strength
> calibration, not plumbing: `coefficients.py` carries `_LEAGUE_COEFF` (UEFA) and
> `_CONCACAF_OFFSET` (Concacaf) only, and `cross_league._CONF_CONST` has goal-rate/home-advantage
> constants only for those same two confederations. `team_strength` returns offset `0.0` for any
> other league, so a Libertadores tie would baseline a Bolivian club level with a Brazilian one and
> emit confident, wrong probabilities. Prerequisites: a calibrated CONMEBOL/AFC/CAF league-offset
> scale, per-confederation `_CONF_CONST` entries, `_ESPN_ROUND` labels for CONMEBOL group stages,
> and name resolution across ~12 domestic frames (cheap — both sides are ESPN displayNames, so an
> exact-string join against the domestic ELO caches should resolve most clubs automatically, the way
> the Concacaf branch of `_resolve_one` already does).
>
> **Weakest-modeled league of the round, shipped with the caveat visible rather than silently:**
> `argentina-nacional`. The real Primera Nacional splits 36 clubs into two zones of 18 that play
> almost exclusively within their own zone; a combined table ranks teams on non-comparable
> schedules. Its `rules` string opens with a plain-language WARNING, rendered on the page. Match
> probabilities come from the pairing matrix and are unaffected; only the standings column is soft.
> Its in-season Brier (0.6442) is worse than the naive baseline (0.6376) — the honest tell.
>
> **Not on ESPN at all** (checked against all 220 slugs, so these need a paid API-Football plan, not
> more guessing): Poland, Finland, South Korea and Canada's CPL — confirming why the four existing
> partial leagues cannot be upgraded — plus Czechia, Croatia, Serbia, Ukraine, Israel, Hungary,
> Bulgaria, Slovakia, Slovenia, Iceland, Cyprus, Egypt, Morocco, UAE, Qatar, Indonesia, Vietnam,
> Malaysia and Japan's J2.
>
> **Two pre-existing bugs found and fixed in passing.** (1) `refresh-leagues.yml`'s hardcoded league
> list had drifted to 21 of 70 leagues. Because it is the *only* job that flips an off-season league
> from `status="completed"` back to `live` (`refresh-daily.yml` builds only leagues already live),
> nothing added since round 3 — `saudi-pro`, `australia-aleague`, `wsl`, all of round 5 — could ever
> have come back from its off-season. Now derived from `OUTLOOK`. (2) `build_all.sh` was missing all
> seven round-5 leagues. Also dropped a `"Women"` entry from `tests/test_fetch_league_teams.py`'s
> `_VALID_GROUPS` that `GROUP_ORDER` never rendered — the test would have passed a league into a
> group the UI drops.
>
> **State on ship:** 9 leagues live with active forecasts, 10 `status="completed"` between seasons
> (identical to where `saudi-pro`/`australia-aleague`/`wsl` sit today; they flip on the weekly job
> once ESPN publishes 2026-27 fixtures), 1 (`venezuela-primera`) tagged `results_only` — mid-season
> with no published forward fixtures. 77/77 payloads valid, 1396 passed / 15 skipped, 76 static
> pages + sitemap regenerated, all 76 leagues verified rendering in-browser across 11 groups.

> **2026-07-14 update — Round 5: South America + more Asia + Eerste Divisie, all 7 candidates shipped.**
> User decision: Chile/Colombia/Uruguay/Peru Primera División (CONMEBOL top flights), K League 1
> (South Korea), Thai League 1, and Eerste Divisie (Netherlands tier 2). Follow-up: "complete item 7"
> — a prior attempt died mid-run to an account spend-limit error after confirming K League 1 has no
> ESPN slug; that finding is reused below, everything else is a fresh pass. **All 7 fully shipped** —
> none needed a `"soon"` placeholder.
>
> **Source-verification order used (per league):**
> 1. ESPN teams endpoint (`site.api.espn.com/apis/site/v2/sports/soccer/<slug>/teams`), live-probed,
>    not guessed.
> 2. If no ESPN slug: API-Football free tier (100 req/day shared quota, seasons 2022-2024 only) for
>    a results-only build, the `canadian-pl` precedent.
> 3. If neither: `"soon"` placeholder with a `reason` string. Not needed this round.
>
> football-data.co.uk was ruled out for all 7 before dispatch (checked live 2026-07-14: its country
> list has no South American entry besides Argentina/Brazil, no Asian entry besides Japan/China, and
> no Eerste Divisie — only Eredivisie tier 1).
>
> **ESPN slugs verified live (teams endpoint, non-zero team count):**
>
> | League | Slug | Teams | Season shape |
> |---|---|---|---|
> | Chile Primera División (Liga de Primera) | `chi.1` | 16 | Calendar-year |
> | Colombia Primera A (Categoría Primera A) | `col.1` | 20 | Calendar-year |
> | Uruguay Primera División | `uru.1` | 16 | Calendar-year |
> | Peru Liga 1 | `per.1` | 18 | Calendar-year |
> | Thai League 1 | `tha.1` | 16 | Aug–May straddle |
> | Eerste Divisie (Netherlands tier 2) | `ned.2` | 20 | Aug–May straddle |
> | K League 1 (South Korea) | — none found — | — | — |
>
> **Gotcha #1 — a date-span check alone misclassifies season shape.** Naively fetching
> `dates=20250101-20251231` and checking whether events span the full year is NOT enough to call a
> league calendar-year: Thai League 1's window for that query spans January through December too,
> but has a hard gap May–July (its season actually runs Aug–May, straddling two calendar years — the
> Jan–Apr and Aug–Dec events belong to *different* seasons). Same check applied to Eerste Divisie
> shows the same Jun–Jul gap. Confirmed via a monthly event-count breakdown, not just first/last
> event date. The 4 South American leagues have no such gap (continuous Feb/Jan–Dec, format churn
> from Apertura/Clausura splits notwithstanding) and are genuinely calendar-year.
>
> **Gotcha #2 — K League 1 has no ESPN slug, confirmed against 4 guesses.** `kor.1`, `kor.k1`,
> `k.league.1`, `kor.ext` all return 0 teams live (reused finding + 3 more guesses this round).
> Not on football-data.co.uk either (Korea absent from its country list). Shipped **results-only**
> via `data_pipeline/api_football.py` (league id `292`, confirmed via `find_league_id`), free-plan
> seasons 2022-2024 — same treatment as `canadian-pl`. Two data-quality issues found in K League 1's
> raw fixture feed and fixed generically in `api_football.py`:
> - **Cross-tier playoff contamination.** Every season carries a fixture under the bare round label
>   `"Relegation Round"` (no dash-number — distinct from the real `"Relegation Round - N"` bottom-6
>   split games) that pits K League 1's relegation-round loser against a K League 2 side. Left in,
>   this shows up as a 13th team in standings for a handful of matches. Fixed with a new
>   `ROUND_EXCLUDE: dict[int, set[str]]` (keyed by API-Football league id) applied in
>   `_parse_fixtures`/`_fetch_league`.
> - **Inconsistent team naming within one season.** In the 2022 season, the military-rotation club
>   (which relocates cities every few years) is named `"Sangju Sangmu FC"` in every `"Regular
>   Season"` fixture but `"Gimcheon Sangmu FC"` (its 2023+ name, post-relocation) in that same
>   season's `"Relegation Round - N"` fixtures — an API-side retroactive-renaming artifact, not a
>   real mid-season rename. Fixed with a new `TEAM_RENAME: dict[tuple[int, int], dict[str, str]]`
>   (keyed by `(af_id, season)`), applied at parse time. Verified after both fixes: all 3 free
>   seasons (2022-2024) show exactly 12 real K League 1 teams in `"Regular Season"` rounds.
>
> **Gotcha #3 — a real, unrelated bug found and fixed in the shared build path.**
> `build_league_data.py` was calling `liga_mx_label()` — which decodes a *sequential Apertura/
> Clausura torneo index* (liga-mx's own season numbering, e.g. `19 → "Cl.2026"`) — for `perf_by_year`
> and edge-backtest labels on **every** `source="espn"` league, gated on `cfg["source"] == "espn"`
> instead of `lid == "liga-mx"`. Harmless for liga-mx (whose `season` really is a torneo index), but
> for every other espn-source league `season` is a real calendar year — feeding e.g. `2026` through
> `season_label()` computes a bogus multi-thousand year (`idx = 2025`, `year = base + 2025 // 2`),
> producing nonsense labels like `"Ap.3028"`. This has been shipping since round 4: Saudi Pro League
> and A-League Men and WSL's `perf_by_year` arrays have carried these bogus labels since 2026-07-11.
> Fixed by gating both call sites on `lid == "liga-mx"`; Saudi/A-League/WSL rebuilt alongside the 7
> new leagues to pick up the fix (labels now read e.g. `"2024"`, `"2025"`).
>
> **Continental qualification / relegation counts** (the numbers that matter for each league's
> `rules` string and bucket `top`/`bottom` cutoffs) were verified via live web search per country
> (not assumed from stale general knowledge), since several of these federations changed their
> allocation rules for the current CONMEBOL/AFC cycle. Where the real format is a split
> Apertura/Clausura(+playoff) season with multi-year rolling-average relegation tables (Chile,
> Colombia, Uruguay, Peru — same shape as Argentina's round-1 caveat), the shipped model uses a
> single combined-season table with the real qualification/relegation **counts**, and the `rules`
> string says plainly that the split-format/rolling-average mechanics aren't modeled. Peru's format
> maps unusually cleanly onto a plain table (its own "cumulative table" IS the official continental/
> relegation basis, contiguous top 4 → Libertadores, next 4 → Sudamericana, bottom 2 relegated) — no
> gap-cutline caveat needed there. Chile has a real discontinuity (Copa Chile winner takes a
> Libertadores berth that would otherwise be 3rd's; Sudamericana is 4th-7th, skipping 3rd) that a
> simple top-N cut line can't represent — caveated explicitly rather than silently overstated.
>
> Eerste Divisie ships on `source="espn"` (not the `footballdata` second-tier family, since it has
> no football-data coverage) with **custom buckets** instead of the `_PROMO()` helper — there is no
> reliably modelable automatic relegation (licensing-based, rare) to put in a trailing `"releg"`
> bucket, so the bucket list stops after `promo`/`playoff`/`promoted`, matching the no-relegation
> precedent already used by `australia-aleague`/`liga-mx`/`nwsl`/`usl-championship`. Live-verified
> 2025-26 format (search, not memory): champion + runner-up promote automatically (a change from the
> historically-remembered "only the champion" rule); 3rd-8th enter a promotion playoff whose winner
> then faces the Eredivisie's 16th-placed side for the final spot — that cross-league leg isn't
> modeled (no fabricated `barrage_win_rate`; the playoff-band winner is shown directly as promoted,
> which is the sim's default behavior when `barrage_win_rate` is omitted).
>
> **Two more pre-existing, unrelated bugs found while validating this round's payloads** (both
> flagged as separate follow-up tasks, not fixed here — out of scope for a league-expansion pass):
> `scripts/build_logo_map.py` crashes (`AttributeError: 'list' object has no attribute 'get'`) on
> `webapp/data/search-index.js`, which is a top-level JSON list; the script has its own stale
> exclusion list instead of importing the canonical `_NON_PAYLOAD` set from `validate_payloads.py`.
> `tests/test_build_movers.py` has 3 failures because `compute_movers()` now returns a 3-tuple
> `(movers, actual_span_days, earliest_used_date)` but the tests still unpack it as a plain list.
> One drive-by fix WAS made here (directly blocking this round's own validation): `calendar.js`
> (added in `3279e2a`, the commit immediately prior to this round) was missing from the canonical
> `_NON_PAYLOAD` set in `validate_payloads.py`, failing both payload-contract validation and
> `tests/test_fetch_league_teams.py`'s REGISTRY-vs-disk test — added to the set.
>
> **Registration:** `scripts/fetch_league_teams.py` REGISTRY + `LEAGUE_INFO` (all `status: "live"`
> from the start — no interim `"soon"` stub needed since every source was already confirmed working
> before registration); `scripts/build_league_data.py` OUTLOOK entries; `data_pipeline/
> espn_fixtures.py` SLUGS + `CALENDAR_YEAR_LEAGUES`; `data_pipeline/api_football.py` LEAGUE entry.
> `webapp/leagues.js` now 56 leagues (0 `"soon"` stubs). All 7 new payloads + the 3 rebuilt
> pre-existing ones pass `scripts/validate_payloads.py` (57/57 after the `calendar.js` fix) and the
> full test suite (1006 passed / 15 skipped / 3 pre-existing unrelated failures flagged above).

> **2026-07-10 update — all 7 Tier-1 leagues + the England National League item now LIVE**,
> built and shipped in this report's ranked order (Brazil → Japan → Sweden → Norway → Denmark
> → Poland → Argentina), England National League last, per an explicit user decision. Two
> corrections to this report surfaced during the build:
> - **Poland's ESPN gap is real, not a maybe.** Every plausible ESPN slug was tried live
>   (`pol.1`, `pl.1`, `pol.e`, `pol.ekstraklasa`, …) — none resolve. Poland ships **results-only**
>   (no in-season projection, no upcoming-fixture schedule) until an alternative fixture source
>   is found. This was a gap in the original write-up below, which only checked football-data's
>   odds coverage for Poland, not ESPN's schedule coverage.
> - **football-data.co.uk's per-country refresh cadence is uneven**, not uniformly "live" as
>   implied below. Brazil's file tracked the current season in real time; Japan's file lagged a
>   full season boundary (last row was the *prior* season's finale). The build now backfills
>   already-played ESPN matches onto the frame whenever this happens — see
>   `docs/PLAN.md`'s 2026-07-10 entry and `scripts/build_league_data.py` for the fix. Any future
>   Tier-1-style addition should verify this per country before assuming the CSV is current.
>
> Implementation detail: Brazil/Japan/Sweden/Norway/Denmark/Argentina use a new adapter,
> `data_pipeline/football_data_intl.py` (the "new leagues" single-file format is NOT the same
> schema as the existing per-season `football_data.py` adapter). England National League reused
> the existing adapter directly (same old-format scheme England 1-4 already use).

> **2026-07-11 update — Round 4: +12 leagues live, Finland + Canadian PL gated on an API key.**
> Spec/plan: `docs/superpowers/{specs,plans}/2026-07-11-league-expansion-round4-*`.
> - **Tier 1 shipped:** Scottish Championship/League One/League Two (mmz4281 `SC1/SC2/SC3`,
>   chained to scottish-prem for tier-bridge seeding) + Austria/Switzerland/Romania/Ireland
>   (footballdata_intl new-leagues CSVs).
> - **Corrections to this report:** Switzerland's football-data code is **`SWZ`, not `SUI`**
>   (the "key verified finding" above was wrong — `/new/SUI.csv` 404s, `/new/SWZ.csv` is the
>   Swiss Super League back to 2012/13). Finland has **no ESPN slug** (`fin.1` returns 0 teams),
>   so it is NOT a clean add — it needs a secondary fixture source.
> - **Secondary schedule source decision:** TheSportsDB's free tier hard-caps `eventsseason` at
>   5 rows (useless for history); **API-Football (api-sports.io), free tier 100 req/day** was
>   chosen. New `data_pipeline/api_football.py`, env `API_FOOTBALL_KEY`. Only Finland (fixtures)
>   and Canadian PL (everything — not on football-data OR ESPN) depend on it.
> - **Projection-only tier shipped** (no betting-edge product): China + Russia kept on
>   footballdata_intl (odds backbone retained for a future edge layer) rendered projection-only;
>   Saudi Pro League / A-League Men / WSL on a new slug-generic `espn_results_frame`.
> - **Workflow gotcha found:** `fetch_league_teams.py` rewrites every still-`"soon"` league to a
>   stub, so a freshly-built league must be flipped to `"live"` in REGISTRY before any later
>   fetch or its data is clobbered. Correct order documented in `docs/CURRENT_STATE.md`.

## How feasibility was scored

Every candidate was checked against the five things a league needs to go live on this platform, in order of how hard they are to substitute:

1. **Results + schedule source** — free, stable, already integrated or near-integrated.
2. **Closing odds** — required for the market-Brier benchmark and the betting-edge product (the site's actual goal). Pinnacle closings are the gold standard.
3. **xG** — nice, not required. The C1 goals-only model family (Eredivisie, Primeira, Süper Lig…) is the proven fallback.
4. **Season shape** — calendar-year and split/playoff formats are already solved (MLS, Liga MX, Scotland split, Belgian halving, promotion playoffs).
5. **Transfermarkt + crest coverage** — for squad-value features and UI polish.

**Key verified finding (2026-07-09):** football-data.co.uk's "new leagues" endpoint (`/new/<CCC>.csv`) carries **results AND Pinnacle closing odds (PSCH/PSCD/PSCA) back to 2012** for Argentina, Brazil, Japan, Denmark, Poland, Sweden, Norway (also Austria, Switzerland, Finland, Ireland, Romania, Russia, China, Mexico, USA). ESPN carries teams/fixtures/crests for all of them (`bra.1` 20 teams, `jpn.1` 20, `swe.1` 16, `nor.1` 16, `den.1` 12, `arg.1` 30 — probed live). One new adapter path (different URL scheme + column map than the current `mmz4281` files) unlocks the entire tier.

## Tier 1 — Ship next: free results + free Pinnacle closings, ~14 years of history

| # | League | Odds | Season shape | Notes |
|---|--------|------|--------------|-------|
| 1 | **Brazil Série A** | ✅ PSC | calendar year (solved) | Biggest market of the set, 20 teams, deep TM coverage, liquid betting market. Best product fit. |
| 2 | **Japan J1** | ✅ PSC | calendar year | Clean 20-team round-robin, stable format, good market liquidity. |
| 3 | **Sweden Allsvenskan** | ✅ PSC | calendar year | 16 teams + relegation playoff (already-modeled pattern). |
| 4 | **Norway Eliteserien** | ✅ PSC | calendar year | 16 teams, same shape as Sweden. |
| 5 | **Denmark Superliga** | ✅ PSC | Aug–May + **championship/relegation split** | Split round is more format work — the Scotland/Greece `FORMATS` machinery covers it. |
| 6 | **Poland Ekstraklasa** | ✅ PSC | Aug–May, plain table | Simplest European add of the set. |
| 7 | **Argentina Primera** | ✅ PSC | calendar year, **30 teams, format churn** | Data is fine; the league itself reshuffles format frequently (zones, name changes — visible even in the CSV: "Liga Profesional"). Highest modeling-maintenance cost in Tier 1. |

**Shared one-time cost:** a `football-data "new leagues"` adapter (single CSV per country, all seasons, `Date/Time/Home/Away/HG/AG/Res + PSC*` columns), then per-league: name mapping, `OUTLOOK` entry, walk-forward eval folds, promotion gate. Estimate: adapter ~1 day, then roughly a league per day following the C1 playbook.

## Tier 2 — Fixtures free, odds need the deferred Odds API spend

| League | Results source | The gap |
|--------|----------------|---------|
| **Saudi Pro League** (`ksa.1`, 18 teams) | ESPN | Not on football-data. Odds exist at books via The Odds API (paid — currently deferred). Growing market, high squad-value variance (good for the value features). |
| **Australia A-League** (`aus.1`, 12 teams) | ESPN | Same gap. Finals-series playoff = MLS-style bracket (solved pattern). Calendar-friendly timezone diversification for daily content. |
| **WSL — England women** (`eng.w.1`, 12 teams) | ESPN | No football-data, no ASA xG (NWSL's xG source doesn't cover WSL), thin odds markets. Ship as **projections-only** (no edge product) if the goal is coverage; model family = goals-only ESPN, the NWSL precedent gets us most of the way. |

These can go live as *projections-only* leagues immediately (the "soon" → C1 path), with the betting layer activating if/when the Odds API budget is approved.

## Tier 3 — The lower-divisions question (Germany, France, Italy, Spain)

Direct answer: **the big-4 third tiers are not feasible with the current source stack.**

- Probed live: ESPN has **no team data** for `ger.3`, `fra.3`, `esp.3`, and `ita.3` returns an empty list. football-data has no third-division files for any of the four.
- 3. Liga has a free community source (OpenLigaDB) but **no free odds**, and Serie C / Championnat National / Primera Federación have neither results nor odds in any integrated source.

**What IS feasible in the lower-division direction** (football-data main files, with odds):

- **England National League (tier 5)** — file `EC`, completing the English pyramid 1→5. The tier-2 ELO-seeding chain (`_TIER2_FOR`) extends naturally.
- **Scottish Championship / League One / League Two** — files `SC1/SC2/SC3`. Small squads, quirky markets, but free and odds-backed.

## Recommendation

1. **Build the "new leagues" adapter and ship Brazil + Japan first** — biggest markets, calendar-year seasons the pipeline already handles, full odds history for honest backtests.
2. **Follow with the Nordics (Sweden, Norway, Denmark) + Poland** as a batch — same adapter, same eval protocol, minimal incremental cost.
3. **Hold Argentina** until after the batch (format churn needs a season-state audit), and **hold Saudi/A-League/WSL** behind either the Odds API decision or an explicit projections-only product call.
4. **England National League** is the one genuinely feasible "more lower divisions" add today; treat the big-4 third tiers as closed until a new data source appears.
