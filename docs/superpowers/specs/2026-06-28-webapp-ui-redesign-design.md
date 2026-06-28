# Webapp UI Redesign — Design Spec

**Date:** 2026-06-28
**Scope:** `webapp/index.html` (single-file dashboard) + one supporting build artifact for logos.
**Status:** Approved direction (Bloomberg/"quant-terminal" base + editorial headers), pending spec review.

## 1. Goals

Significantly improve the dashboard UI. Eight issues from the user, mapped to sections below:

1. Generic "AI dashboard" aesthetic → distinctive design language (§3, §4).
2. Relegation odds buried under team name → its own labeled column (§6).
3. Top summary boxes don't scale to leagues with multiple European tiers / relegation spots; must stay crisp (1–2 rows) for all leagues (§5).
4. Single-table leagues waste the right half of the page (770px club column) → half-width table + companion visual (§7).
5. Missing logos (continental comps carry none; scattered domestic gaps) (§9).
6. Teams tab shows MLS-only trophies (US Open Cup) for European teams + "0.4ern Conference" bug (§8).
7. Tournament round-odds tables are bare, unstyled `<table>`s (§10).
8. General polish (§3, §11).

## 2. Constraints & non-goals

- **Preserve all simulation/data logic.** The what-if Monte-Carlo engine (`runSim`, `runSimTable`, `confBracket`) and its JS↔Python porting contract (per the comment block at `index.html` ~line 647) must not change behavior. This is a **presentation rewrite**: replace the `<style>` block and the HTML-template strings inside render functions; leave sim math, event wiring, and data plumbing intact.
- **No model / eval / pipeline changes.** The only new data artifact is a logo lookup (§9), generated webapp-side.
- **Stay single-file.** Keep `webapp/index.html` self-contained (plus `leagues.js`, per-league `data/*.js`, and the new `data/logos.js`). No build framework, no bundler.
- **Data-driven, not per-league hardcoding.** Every league-specific behavior derives from the payload (`outlook.cards`, `outlook.columns`, `trophies`, `standings` keys), never from `if (league === 'epl')`.

## 3. Visual design system (the new aesthetic)

A "quant-terminal" base (FiveThirtyEight / Bloomberg) with editorial-sports headers. Concretely, this means killing the three "AI smell" tells: uniform rounded gradient-glow cards, a rainbow of competing accent colors, and characterless even spacing.

**Color tokens** (replace current `:root`):
- Background: near-black greenish-ink `#070809` base, panels `#0a0d0b`, raised `#0c100d`.
- Hairlines: `#131b14` / `#18211a` (thin, low-contrast grid lines — no glows).
- Text: `#e3e9e4` / `#9fb0a3` / `#54665b` (primary/secondary/muted).
- **Disciplined accent system — one color per semantic role, reused everywhere:**
  - `--win/title` gold `#f4b740`
  - `--qualify/ucl` green `#3ddc84` (also the "live/model" signal dot)
  - `--europa` blue `#4aa3ff`
  - `--drop/loss` red `#ff5d5d`
  - `--draw/neutral` slate `#5a6b7a`
  - Team colors still used for the per-match probability band and crest accents only.
- Heat cells: a single hue per outcome at variable alpha (existing `heat()` approach kept, but mapped to the accent above for that column, not a rainbow).

**Typography:**
- Display/headers: `Archivo` 700–900 (kept).
- Body/labels: `Inter` (kept).
- **All numerics: `Spline Sans Mono`** (new) — tabular mono is the core of the "real model output" feel. Points, percentages, odds, ELO, ranks.

**Density & shape:**
- Radius drops to 3–10px (was up to 16px). Panels get a thin border + a header bar with a status dot + mono meta on the right.
- Remove the body radial-gradient glow and the beacon box-shadow glows; replace with flat, confident blocks.
- Establish a spacing scale and use it intentionally (denser rows, generous section gaps) rather than uniform padding everywhere.

**Core reusable components** (defined once, used across all views):
- `.panel` + `.panel-h` (dot + mono uppercase title + right-aligned mono meta).
- Table primitives: `.thd` / `.trow` grid rows, `.cell` heat cell, `.tm` team cell (crest + name), `.pts` mono number, zone rails (`inset 3px 0 0 <accent>`).
- `.race` card (§5).
- Heat-matrix cell (§10).

## 4. Header & chrome

- Sidebar, segmented tabs, and league header restyled to the new system (mono meta, flat blocks, single green status dot for "live").
- The model-vs-naive/market accuracy card (`#acc`) restyled as a compact mono stat block (keep the per-season tracks; drop glow/rainbow).
- Brand "Pitchside" retained; beacon becomes a flat mark, not a glowing orb.

## 5. Top boxes → "Race strip" (#3)

Replace the fixed 3-or-4 favorite cards with a **race strip**: one compact card per *race*, driven by `outlook.cards` (table leagues) or the MLS card set (Shield / East / West / Spoon).

Each `.race` card shows:
- Race label + qualifier hint (e.g., "Champions Lg · top 5").
- Leader: crest + name + mono % (colored by the race's accent).
- Two nearest contenders as `name · mini-bar · %` rows.
- A left rail in the race's accent color.

**Scaling rule:** cards are uniform-height and laid out in an auto-fit grid (`repeat(auto-fit, minmax(220px, 1fr))`), wrapping to a tidy second row. A league with Title + UCL + Europa + Conference + Relegation gets 5 cards on (at most) two rows; MLS gets 4. Never more than two rows at desktop width → "crisp for all leagues" holds by construction.

Contender data: top-2 (besides leader) by the race's metric, from `standings` sorted on that column. For "bottom" races (relegation, spoon) the metric is the drop/spoon probability.

## 6. League table — single-table leagues (#2, #4)

**Layout:** two-column `minmax(0,1fr) minmax(0,1fr)` body. Left = the table panel (now naturally half-width, ~580px — comparable to one MLS conference ladder). Right = the companion (§7). Collapses to one column under ~880px.

**Table columns** become explicit, labeled outcome columns derived from `outlook.columns`:
`# · Club · Pts · Proj · ELO · [one heat column per outcome: Win/UCL/EL/Conf/Rel] · [Next-5 what-if if fixtures exist]`.
- **Relegation is its own labeled `Rel` column** with a red heat cell — fixes #2. (It was never literally under the name in current code, but it was an unlabeled tiny heat cell; now every outcome column has a header and a consistent heat treatment.)
- Sub-line under the club name keeps `GP · GD · xGD` (the model inputs), not odds.
- Green/red qualification and relegation divider lines retained, restyled.

**MLS / two-conference leagues keep their twin-ladder layout** (they already fill the width). They get the same restyle (mono numerics, new heat, race strip) but NOT the half-width + companion treatment.

## 7. Companion panel — "Projected finish" range plot (#4)

For single-table leagues, the freed right half shows a **finishing-position range plot**:
- One row per team (ordered by current/projected position): crest + name, then a horizontal track over a 1→N position axis.
- A range bar from the team's **10th to 90th percentile** finishing position, with a **median dot**, colored by the team's current qualification zone.
- Axis ticks at 1 / 5 / 10 / 15 / 20 (scaled to league size); zone legend below.

**Data source:** extend `runSimTable` to also accumulate, per team, a finishing-position histogram (`counts[team][rank]`, an N×N int matrix — cheap). Derive P10 / median / P90 per team. Run the sim **once at page load** to populate the plot (the engine already runs 10k sims in tens of ms), and re-run on what-if toggles so the plot updates live with the table. No build/pipeline change required. (Optional future optimization: bake `finish_dist` into the build payload; not in scope now.)

Preseason leagues (0 played) simulate the full season from priors — exactly the preseason projection — so the plot is meaningful there too.

## 8. Teams tab — league-aware trophies + profile fix (#6)

**Root causes found:**
- `renderProfile` builds the sub-header as `${s.conf}ern Conference`. European table leagues reuse the `conf` standings key for the **Conference-League qualification %** (a number like `0.4`), producing "0.4ern Conference". The conference-rank filter (`x.conf === s.conf`) is likewise meaningless for table leagues.
- `TROPHY` map and the trophy legend are hardcoded to MLS Cup / Supporters' Shield / US Open Cup. European league files carry **no trophy data**, so the legend falsely advertises the US Open Cup for Premier League teams.

**Fixes (webapp-side):**
1. **Trophy registry, data-driven.** Build a registry mapping competition name → `{glyph, color}` (MLS Cup, Supporters' Shield, US Open Cup, plus generic fallbacks: "League Title", "Domestic Cup", "Continental"). The trophy **legend and ELO-chart markers render only the distinct `type`s actually present in `D.trophies` for the current league** (Conference excluded, as today). European leagues → no trophy data → legend hidden, profile shows "No trophy data for this league." Unknown trophy types fall back to a generic cup glyph instead of rendering nothing.
2. **Profile header & ranking generalized by league type.** For `isTable` leagues: show overall **league rank** (`#k of N`) and ELO/record — never "…ern Conference". For MLS: keep `${conf}ern Conference` and conference rank. Drive off the existing `isTable` flag.
3. ELO mini-chart grid (`renderTeams`) is already strong — light restyle only (mono ELO numbers, new tier colors).

## 9. Logos (#5)

**Problem:** continental competitions (UCL 72/72, Leagues Cup 72/72, Concacaf 27/27) carry **no** logos in `standings`/`field`; domestic leagues have a few gaps (Coventry, Ipswich, Hull, Venezia, Frosinone, Monza, Mazatlán — promoted/relegated/new clubs).

**Fix — global logo lookup, generated webapp-side:**
- New `scripts/build_logo_map.py`: harvests `{team_name: logo_url}` from every existing `webapp/data/*.js` that carries logos (covers nearly all continental teams, since they appear in their domestic files), plus a small **manual supplement** dict for known gaps mapped to ESPN team-logo URLs, plus an **alias map** for cross-payload name mismatches (e.g., `Internazionale`→`Inter Milan`, `Paris Saint-Germain`→`PSG` — only where the domestic name differs). Emits `webapp/data/logos.js` → `window.TEAM_LOGOS = {…}`.
- `index.html` loads `logos.js` (alongside `leagues.js`). The `crest(name, logo)` helper and the continental/power renderers fall back to `TEAM_LOGOS[name]` (normalized: trim, case-fold, alias) when the payload omits a logo.
- Result: continental brackets/tables and scattered domestic rows render real crests; monogram fallback remains for genuinely unknown clubs.

`build_logo_map.py` is re-runnable so the map stays current as league files rebuild.

## 10. Tournament / knockout views (#7)

Replace the bare `<table>`s in `renderKnockout` with the new panel + table system:
- **League-phase table** (UCL/Europa/Conference 36-team): a `.panel` with `Adv / Playoff / Out` as **heat columns** (green/amber/red at variable alpha), proper headers, mono numerics, and restyled cut lines (top-8 auto-advance, top-24 playoff).
- **Group tables** (Leagues Cup): two side-by-side `.panel`s with the same heat treatment.
- **Champion-odds "round reach" table** → a **heat matrix**: rows = teams (sorted by win odds), columns = rounds (R16 → … → Win), each cell a heat-mapped probability. This is the "odds of making each round" visual, now reading like the rest of the app instead of a raw spreadsheet. Fits in a `.panel`, no dead right-half.
- **Bracket** (`bracketTree`): restyle tie cards into the new system (mono scores, winner in accent, crest support via §9), tighten columns, keep the round-column layout.
- Concluded-edition banner restyled.

## 11. Matches view + Power rankings

- **Matches** (`renderGames`): keep the compact one-line-per-match rows; restyle to the system (mono odds/score, the probability `cbar` recolored to the disciplined accents, crest fallback via §9). The fair-odds American numbers stay but go mono.
- **Power rankings** (`renderPower`): restyle the two confederation panels to `.panel` + mono strength numbers + crest fallback. Light touch — structure is fine.

## 12. Responsive

- Race strip: `auto-fit` grid already reflows; verify ≤2 rows at desktop, stacks on mobile.
- Single-table body collapses to one column < 880px (table above, companion below).
- Existing mobile what-if sub-row behavior preserved.
- Verify the four breakpoints already in the file (1280/860/760/520/480) still hold with the new grids.

## 13. File touch list

- `webapp/index.html` — new `<style>` design system; rewritten template strings in `renderFavs`→race strip, `tableLadder`/`renderTableOutlook` (+ companion), `ladder`/`renderOutlook` (MLS restyle), `renderKnockout` (+ heat matrix), `bracketTree`, `renderGames`, `renderProfile`/`renderTeams` (trophy + conf fix), `renderHealth` (restyle), power-rankings block; extend `runSimTable` for finishing-position percentiles; `crest()` logo fallback; load `logos.js`.
- `scripts/build_logo_map.py` — **new**, emits `webapp/data/logos.js`.
- `webapp/data/logos.js` — **new** generated artifact.
- Docs per CLAUDE.md convention (PLAN blockquote, CURRENT_STATE if relevant, plan-file verdict).

## 14. Verification plan

Using the live preview (`webapp` launch config, port 8090), screenshot and sanity-check each archetype after implementation:
- **MLS** — twin ladders + race strip (4 cards), new aesthetic, no regressions in what-if.
- **EPL / Serie A** (single-table, preseason) — race strip, half-width table with labeled `Rel` column, projected-finish plot.
- **Liga MX** (single-table, in-season, sequential IDs) — confirm columns/labels and plot.
- **UCL** (knockout, concluded) — league-phase heat table, bracket, round-reach heat matrix; crests now present.
- **Leagues Cup** (group stage) — two heat panels; crests present.
- **Teams tab** for EPL — trophy legend hidden / honest; profile reads "#k of 20", not "0.4ern Conference".
- **Power rankings** — restyled, crests present.
- Mobile (375px) spot-check of MLS + EPL.
- Console clean (no errors) on each.

## 15. Open questions

None blocking. Default decisions taken: companion panel = projected-finish range plot (user approved); finishing-position percentiles computed client-side (no pipeline change); logo map harvested + supplemented webapp-side.
