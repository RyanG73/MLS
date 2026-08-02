# League QA Audit — Reusable Prompt

> Hand this prompt to a fresh session (or run it yourself) to audit the ~78 leagues
> one at a time. It is self-contained: it names the exact files, fields, and units so
> the reviewer never has to reverse-engineer the data model. Work **one league per
> pass**, produce a findings block, then move to the next.

---

## Role & objective

You are auditing a market-blind football forecasting site (Entenser) league by league.
For each league you perform a **gut check**: does the forecast look right, is the page
formatted correctly, and does it respect that competition's real rules? You then either
**fix presentation/label/config errors at their source** or **flag odds that look wrong
as an upstream bug to diagnose** — you never hand-patch generated numbers.

Complete **one league fully** before starting the next. Do not batch-skim.

---

## The surfaces you inspect (per league)

Every league has an `id` (e.g. `mls`, `libertadores`, `argentina-primera`). For a given id:

| Surface | Path | What it is |
|---|---|---|
| Registry row | `webapp/leagues.js` (`window.LEAGUES`) | id, `name`, `confederation`, `group`, `tier`, `status`, `data_status`, `logo`, `espn_code`, `country` |
| Data payload | `webapp/data/<id>.js` (`window.LEAGUE_DATA`) | the numbers: `pmatrix`, `sim`, `perf_by_year`, `rules`, `format_label`, `phases`, `rounds`, `outlook`, etc. |
| SEO page | `webapp/leagues/<id>/index.html` | pre-rendered: `<title>`/meta description, canonical, JSON-LD (`Dataset` + `SportsEvent`), callouts, projected table, upcoming W/D/L, "updated" date, sibling links |
| Interactive view | `/?league=<id>` (renders from the data payload) | the live dashboard the user actually sees |
| CSV export | `webapp/exports/<id>.csv` | flat table: `rank, team, played, points, proj_points, playoff, shield, cup` (columns vary by league) |

**Units & encodings you must know:**
- `pmatrix` rows are `[home, draw, away]` **scaled to 1000** (integer per-mille). A valid row sums to ~1000.
- Percentages on the SEO page are clamped to `>99%` and `<1%` at the extremes — those strings are expected, not bugs.
- `data_status` governs what *should* render:
  - `full_forecast` — full projections + fixtures + sim.
  - `historical` — backtest/perf only, no live forecast; a live "projected table" here is a bug.
  - `results_only` — results ingested but no model output; forecast widgets should be absent/blank.

**Generated vs. authored — this determines how you fix things:**
- `webapp/data/*.js`, `webapp/leagues/*/index.html`, and `webapp/exports/*.csv` are **generated** by the build/refresh pipeline (`scripts/build_league_data.py`, GitHub Actions `refresh-leagues.yml`). **Do not hand-edit numbers in these files** — they are overwritten on the next refresh.
- Fix **labels, format descriptions, competition rules, and template/formatting bugs** in whatever config or generator produces them (trace with grep, below), then rebuild.
- If **the odds themselves look wrong**, that is an upstream data/config/model issue — **record it as a finding to diagnose**, do not paper over it in the output file.

---

## Per-league checklist

Run all three groups. Record every hit; if a group is clean, say so explicitly.

### 1. Odds gut check (are the numbers plausible?)
- [ ] **Row integrity:** spot-check several `pmatrix` rows — each sums to ~1000; no negatives, no `null` where a played-vs-upcoming match should have probs.
- [ ] **Home-advantage direction:** across upcoming fixtures, the home W% should on average exceed the mirror away W%. A league where home teams are systematically underdogs signals a swapped home/away join.
- [ ] **Favorites pass the smell test:** the clear title/relegation favorites match reality for this league and season. A mid-table side at `>99%` to win, or a known powerhouse near relegation, is a red flag.
- [ ] **Season sim internal consistency:** title/champion probabilities across all teams sum to ~100%; number of teams at `>99%` playoff ≤ the real number of playoff berths; relegation count matches the real number of relegation slots.
- [ ] **Draw share sanity:** draw column typically ~22–30%. A league showing ~5% or ~45% draws everywhere is a calibration/format bug.
- [ ] **Backtest sniff (`perf_by_year`):** `model` Brier should generally beat `naive`; a league where the model is consistently worse than base-rate is worth flagging.

### 2. Formatting / presentation
- [ ] **Team-name encoding:** accented/unicode names render correctly on the SEO page (e.g. `CF Montréal`, `Süper Lig`) — no mojibake, no raw `é`.
- [ ] **Stale "updated" date:** the footer/meta "Updated YYYY-MM-DD" is recent (matches the last refresh), not weeks stale.
- [ ] **Counts & copy match reality:** e.g. "All N leagues" link count, `pct_complete`, `played`/`upcoming` totals are internally consistent.
- [ ] **Callouts vs. table agree:** the header callouts (top playoff/title odds) match the top rows of the projected table.
- [ ] **JSON-LD sanity:** `SportsEvent` entries in the SEO page point to real upcoming fixtures with plausible venues and dates; `dateModified` matches the visible update date.
- [ ] **Logo present / correct:** `logo` is non-null where one should exist; a default-team-logo placeholder on a major league is worth noting.

### 3. Competition rules (does the page model the real competition?)
- [ ] **Table structure matches the competition:** single table vs. conferences (MLS = East/West; playoff odds must be per-conference, not from one merged table), group stage, or split-format (Scottish Prem, Belgian Pro League playoffs).
- [ ] **Season format:** Apertura/Clausura vs. single long season (Argentina, most of Liga MX, Central/South America) — check `format_label` / `format_approximate` / `season_label` describe the *actual* current format, and that `format_approximate:true` is set where the model only approximates it.
- [ ] **Qualification/relegation logic:** relegation by season table vs. multi-season average (Argentina *promedios*); continental qualification slots correct for the country.
- [ ] **Cup/knockout rules:** for `libertadores`, `sudamericana`, `ucl`, `europa`, `conference`, `leagues-cup`, `concacaf-champions` — check `format_label`, `rules`, `phases`, `rounds`, `advance`: two-legged ties where real, away-goals abolished (UEFA/CONMEBOL), correct group→knockout structure, correct number of qualifiers.
- [ ] **Column set fits the league:** the projected-table columns (`playoff`, `shield`, `cup`, etc.) are the ones that actually exist for this competition — no "MLS Cup" column on a European league, no "relegation" column on a league without relegation.

---

## Workflow for each league

1. **Read the registry row** in `webapp/leagues.js` — note `data_status`, `tier`, `confederation`. This sets expectations for what should render.
2. **Read `webapp/data/<id>.js`** — inspect `pmatrix`, `sim`, `perf_by_year`, and the rules/format fields.
3. **Read `webapp/leagues/<id>/index.html`** — check the rendered table, callouts, meta, dates, JSON-LD, encoding.
4. **Verify live if in doubt:** start the preview and open `/?league=<id>` and `/leagues/<id>/` to see what the user sees (use the browser preview tools; verify via DOM/read_page, not just a screenshot — deep-scroll screenshots can render blank).
5. **Trace any label/rules/format error to its source** before fixing:
   ```bash
   grep -rn "<the wrong string>" scripts/ config/ data_pipeline/ webapp/ --include=*.py --include=*.yaml --include=*.js
   ```
   Fix in the generator/config, not the generated artifact.
6. **Record findings** in the block below. Then move to the next league.

---

## Output format (one block per league)

```
### <id> — <League Name>  [data_status]
Verdict: CLEAN | ISSUES (n)

Odds gut check:      <pass, or specific flags with the numbers you saw>
Formatting:          <pass, or specific issues>
Competition rules:   <pass, or specific mismatches>

Actions taken:       <source-level fixes made, with file:line>
Flagged for upstream:<odds/data bugs to diagnose — NOT hand-patched>
```

Keep each finding concrete: name the team, the number, the file, and the line. "Odds
look off" is not a finding; "`argentina-primera` shows River Plate at 3% to win the
Apertura while sitting top of the table — favorite/table inversion, likely swapped
season split" is.

---

## Guardrails

- **Never hand-edit generated numbers** (`webapp/data/*.js`, `*.csv`, rendered tables). Diagnose and fix upstream, or flag.
- **One league at a time.** Finish the checklist and the findings block before the next id.
- **Preserve the "market-blind" invariant:** the model never ingests bookmaker odds. If you propose any fix, it must not introduce market odds as a model input. (Betting *edge* display that compares model vs. market is a separate, allowed feature — don't confuse the two.)
- **Update the docs** per `CLAUDE.md` conventions if a fix changes model config or metrics.
- **Commit source fixes with a clear message**; do not push unless asked. Rebuild the affected league(s) so the artifact reflects the source fix.
```
