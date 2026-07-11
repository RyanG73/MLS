# League Expansion Feasibility Report

*2026-07-09 · prepared for UI feedback round 3 ("write a report of all leagues around the world we should consider expanding to — rank by feasibility")*

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
