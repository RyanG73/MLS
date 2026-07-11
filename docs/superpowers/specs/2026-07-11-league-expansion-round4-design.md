# League Expansion Round 4 — Design Spec

*2026-07-11 · approved architecture from the brainstorming session. Extends `docs/league-expansion-report.md` (2026-07-09) and the 2026-07-10 wave.*

## Goal

Add 14 leagues to the dashboard, in three dependency-ordered phases. Twelve reuse
adapters that already exist; only one new adapter (API-Football) is written.

## Scope

**Phase 1 — Tier 1 (no API key needed):**
1. Scottish Championship (`SC1` / ESPN `sco.2`) — `footballdata`
2. Scottish League One (`SC2` / ESPN `sco.3`) — `footballdata`
3. Scottish League Two (`SC3` / ESPN `sco.4`) — `footballdata`
4. Austria Bundesliga (`AUT` / ESPN `aut.1`) — `footballdata_intl`
5. Switzerland Super League (`SUI` / ESPN `sui.1`) — `footballdata_intl`
6. Romania Liga I (`ROU` / ESPN `rou.1`) — `footballdata_intl`
7. Ireland Premier Division (`IRL` / ESPN `irl.1`) — `footballdata_intl`

**Phase 2 — Projection-only (no API key needed):**
8. China Super League (`CHN` / ESPN `chn.1`) — `footballdata_intl`, odds backbone
   stays wired but not rendered (projection-only presentation)
9. Russia Premier League (`RUS` / ESPN `rus.1`) — `footballdata_intl`, same as China
10. Saudi Pro League (ESPN `ksa.1`) — `espn` goals-only (no football-data odds)
11. Australia A-League (ESPN `aus.1`) — `espn` goals-only
12. WSL, England women (ESPN `eng.w.1`) — `espn` goals-only

**Phase 3 — API-Football adapter (needs `API_FOOTBALL_KEY`):**
13. Finland Veikkausliiga (`FIN`) — `footballdata_intl` for results+odds; **upcoming
    fixtures patched from API-Football** because ESPN `fin.1` is empty. Full-featured.
14. Canadian Premier League — new `source: "api_football"`, projection-only,
    replaces the current `status: soon` placeholder. Full history + fixtures from
    API-Football. Concacaf.

## Non-goals

- **No betting-edge product for projection-only leagues.** China/Russia keep the
  football-data odds *columns* (backbone for a future edge layer, a config flip),
  but no edge board / market-Brier surface ships for any Phase 2 league.
- **No split-round format modeling.** Romania, Austria, Finland (championship/
  relegation splits), Scottish lower-tier playoffs, and A-League finals series are
  modeled as **plain-table approximations with an honest `rules` caveat**, following
  the shipped Denmark/Poland/Argentina precedent. Scottish tiers use the `_PROMO`
  helper where it is a clean fit.
- **No new model architecture or hyperparameters.** New leagues reuse the goals-only
  C1 model family (footballdata / footballdata_intl) or the ESPN goals-only family
  (liga-mx / NWSL / USL).

## Architecture

`OUTLOOK` in `scripts/build_league_data.py` is a data-driven registry: a league is
mostly a config row (`name`, `source`, `n`, `confederation`, `buckets`, `green_line`,
`red_line`, `eval_seasons`, `rules`) plus an ESPN name-map. The sim / model / render
code is source-agnostic and routes on `source`. So the only real *code* is the new
adapter; everything else is configuration and per-league caveats.

### Source routing per phase
- `footballdata` → `data_pipeline/football_data.py` (mmz4281, add `SC1/SC2/SC3` to `DIV`).
- `footballdata_intl` → `data_pipeline/football_data_intl.py` (new-leagues CSV, add
  `AUT/SUI/ROU/IRL/CHN/RUS/FIN` to `COUNTRY`).
- `espn` → existing goals-only path (liga-mx precedent) for KSA/AUS/WSL.
- `api_football` → **new** `data_pipeline/api_football.py`, keyed on env
  `API_FOOTBALL_KEY`, mirroring `football_data_intl.py`'s shape (played-results frame
  + upcoming-fixtures frame). Used by CPL (everything) and Finland (fixtures override).

### API-Football adapter (`data_pipeline/api_football.py`)
- Reads `API_FOOTBALL_KEY` from env; if absent, raises a clear "provision the key"
  error and the dependent leagues degrade to results-only / stay placeholder.
- `results_frame(league_id, seasons)` → same columns the model expects (Date, Home,
  Away, HG, AG, Res). `upcoming_fixtures(league_id)` → scheduled rows (is_result=False).
- Respects the 100 req/day free-tier ceiling: cache responses to disk (mirror
  `football_data_intl` caching), one fetch per league per build.
- Config: map our slug → API-Football league id (CPL, Finland) + season list.

### Finland fixtures override hook
`footballdata_intl` supplies Finland's results+odds; a small hook in the build lets a
league declare `fixtures_source: "api_football"` so upcoming rows come from
API-Football while historical/odds rows come from football-data. This generalizes the
Poland "results-only" gap fix.

## Per-league config (shapes finalized during implementation against current formats)

| League | conf | n | outlook shape (approx) | relegation |
|---|---|---|---|---|
| Scottish Championship | UEFA | 10 | champ promoted + playoff | yes + playoff |
| Scottish League One | UEFA | 10 | champ promoted + playoff | yes + playoff |
| Scottish League Two | UEFA | 10 | champ promoted + playoff | pyramid playoff |
| Austria Bundesliga | UEFA | 12 | champ→UCL, top→Europe | bottom + playoff |
| Switzerland Super League | UEFA | 12 | champ→UCL, top→Europe | bottom + playoff |
| Romania Liga I | UEFA | 16 | champ→UCL, top→Europe | bottom |
| Ireland Premier Division | UEFA | 10 | champ→UCL | bottom + playoff |
| China Super League | AFC | 16 | champ→AFC CL | bottom |
| Russia Premier League | UEFA | 16 | champ (UEFA berths suspended — caveat) | bottom + playoff |
| Saudi Pro League | AFC | 18 | champ→AFC CL | bottom |
| Australia A-League | AFC | 12 | top-6 finals series | none (closed league) |
| WSL (women) | UEFA | 12 | champ→Women's CL | bottom |
| Finland Veikkausliiga | UEFA | 12 | champ→UCL | bottom + playoff |
| Canadian Premier League | Concacaf | 8–9 | top-N playoffs → final | none |

Scottish tiers additionally get a `tier2_offsets`/tier-bridge chain to `scottish-prem`
(the SC0↔SC1↔SC2↔SC3 pyramid), matching the England 1→5 chain.

## Evaluation & gate

- **Full-featured leagues** (Phase 1 + Finland) get walk-forward eval folds consistent
  with the 2026-07-10 wave; changes to shared code paths must not regress the pinned
  baselines (`docs/experiment-protocol.md`).
- **Projection-only leagues** (China, Russia, Saudi, A-League, WSL, CPL) get advisory
  eval only, like NWSL/USL (`eval_seasons=None`, derived dynamically). No gate.

## Verification (per league)

Build the league `.js`, load `webapp/` in the preview browser, confirm the league
renders — table, outlook buckets, drift trajectory — with real crests and no console
errors. Share a screenshot / DOM check as proof, per league.

## Dependencies & sequencing

1. **Phase 1 and Phase 2 need no key** → build and verify immediately (12 of 14).
2. **Phase 3 is gated on the user provisioning `API_FOOTBALL_KEY`** (free api-sports.io
   account; 100 req/day is ample). The adapter is written and unit-checked against a
   fixture, but Finland-fixtures and CPL cannot be end-to-end verified until the key is
   set. Finland ships results-only (Poland-class) in the interim; CPL stays a placeholder.

## Risks / open items

- **football-data.co.uk per-country refresh cadence is uneven** (the Japan-lag lesson).
  Each new `footballdata_intl` country's CSV currency is verified during build; the
  ESPN backfill path already handles a lagging CSV.
- **ESPN slug fixtures vs. teams**: teams resolved for all Phase 1/2 leagues, but the
  scoreboard (fixtures) endpoint is re-checked per league at build time; any that lack
  scoreboard coverage degrade to results-only with a caveat (Poland precedent).
- **Russia**: structurally UEFA but its European berths are currently suspended — the
  `rules` string carries this caveat; berth buckets shown as domestic-only where apt.
- **API-Football free-tier ceiling**: disk caching + one-fetch-per-league keeps daily
  builds well under 100 req/day even as the league count grows.
