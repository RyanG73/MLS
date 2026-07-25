# League QA Audit — Findings (pass of 2026-07-24)

Run against the prompt in `docs/league-qa-audit-prompt.md`, registry of 78 leagues.
Source fixes are committed; upstream/data issues are recorded, not papered over.

---

## Cross-cutting fixes (affect many leagues)

### F1. Winless clubs silently dropped from the table
`scripts/build_league_data.py:1601` built the team universe from `pts`, which only
gains a key once a club wins or draws. Any club that is still winless **and** has no
remaining fixture in the feed disappeared from the standings entirely. Invisible
while a fixture feed is healthy; catastrophic at a season boundary.
Observed: `liga-mx` shipped a **10-team** table (the 8 pointless clubs were gone),
`romania-liga1` a **9-team** table.
**Fixed** — key off `gp`, which is incremented for both sides of every played match.

### F2. Liga MX never had a forward fixture list
`data_pipeline/espn_soccer.py::_parse_events` skipped every event whose status was
not `completed`, so `liga_mx_frame` could not contain a scheduled match. With
`upcoming == 0`, `season_state` classified every torneo as CONCLUDED.
**The live site published "Liga MX 20 results · final · Champions: Cruz Azul" two
matchdays into Apertura 2026.** ESPN had all 153 Apertura fixtures (11 played, 142
scheduled) the whole time.
**Fixed** — scheduled rows are emitted (NaN goals, `is_result=False`), and a torneo
holding unplayed fixtures is always refetched rather than served from cache.
Rebuilt: 11 played + 142 upcoming, 18 teams, Liguilla odds summing to 800 (8 berths),
top club 88.4% instead of a wall of 100%.

### F3. Torneo index leaked into the page title
`liga-mx`'s `season` is a sequential torneo index, and `season_label` was only set in
pre-season, so pages read **"Liga MX 20"**. **Fixed** — decoded via `liga_mx_label`
→ `"Ap.2026"`.

### F4. Playoff matches counted toward league tables (10 leagues)
`data_pipeline/espn_fixtures.py` hard-coded `is_playoff = 0`, so the standings filter
that is meant to exclude knockout rounds was a no-op for every ESPN-sourced league.
Post-season results were being added to the "final table":

| league | GP spread before | after |
|---|---|---|
| honduras-liga | 40–52 | 40 |
| guatemala-liga | 46–56 | (rebuilt) |
| elsalvador-primera | 44–53 | (rebuilt) |
| liga-expansion-mx | 28–42 | (rebuilt) |
| australia-aleague | 26–30 | 26 |
| australia-aleague-women | 20–23 | 20 |
| usl-super-league | 28–30 | (rebuilt) |
| france-premiere-ligue | 22–24 | (rebuilt) |
| venezuela-primera | 13–20 | 13 |
| colombia-primera-a | mixed | 19 |

**Fixed** — `is_playoff_slug()` classifies ESPN's `event.season.slug`. The token list
was built from a live slug census of all 31 ESPN-sourced leagues, not guessed; it is
deliberately conservative (Ecuador's `final-stage`, a full second round robin, is *not*
treated as a playoff). Scheduled playoff fixtures are also dropped from the table sim.
**Caveat:** only the current-season parquet is refetched, so pre-2024 cached seasons
still carry `is_playoff = 0`. That affects `perf_by_year` sample composition, not any
displayed table.

### F5. Table leader captioned "Champions" where a playoff decides the title
`scripts/build_static_pages.py` fell back to the points leader and labelled it
`Champions:`. Cavalry FC led the 2024 CPL table; Forge won the final.
**Fixed** — caption keys on the payload's first probability column
(`premiers`/`liguilla`/`shield` → "Best regular-season record"/"Top of the table"),
plus a new `TITLE_BY_PLAYOFF` set for the eight South American aggregate-table leagues
whose `title` column ranks a table the championship is not drawn from.
Leagues whose table really does crown the champion (Poland, Thailand, Chile, Brazil,
K League's championship round, the European splits) keep "Champions".

### F6. A started season with no schedule was published as "final"
`season_state` only sees match counts, so *any* league whose new campaign has kicked
off before its fixture feed publishes gets `CONCLUDED` + a fabricated champion.
`romania-liga1` was live with **"Liga I (Romania) 2026 results · final · Champions:
CSU Craiova · 100% of the season played"** off **one matchday**.
**Fixed** — a season is held at in-progress when no club has completed even one full
round robin; `pct_complete` is blanked (the denominator is unknown), and a new
`no_fixture_feed` flag renders an explicit note that the probability columns restate
played matches rather than forecast anything. The guard is surgical: of the 27
currently-completed table leagues, only `romania-liga1` flips (india-isl sits exactly
on the boundary at 13/13 and correctly does not).

### F7. Invalid `<1%` markup on 42 pages
`pct()` returned a literal `<1%` interpolated straight into `<td>`. Browsers tolerate
it (`<` before a digit is text), but it is invalid markup and breaks strict parsers.
**Fixed** — `pctH()` escapes at the HTML sites; the attribute and `E()`-wrapped
callers keep the plain string so nothing double-escapes.

### F8. MLS rendered one merged table for two conferences
Playoff odds are computed per conference (East and West each sum to 900 = 9 berths),
but the static table merged both and sorted by projected points, so the playoff column
jumped around — Columbus Crew 53.8% sat below LA Galaxy 38.8%.
**Fixed** — the table splits per conference, and the CSV export gained a `conference`
column with within-conference ranking.

### F9a. Greek Super League rules text was stale
`rules` said "Top 6 enter the championship playoff round", but the post-split
pairing graph for both 2024-25 and 2025-26 resolves to pools of **1–4 / 5–8 / 9–14**
(8 clubs playing 6 post matches, 6 clubs playing 10) — which is exactly what
`FORMATS["greek-super"] = {"groups": [4, 4]}` already models. The model was right and
the prose was wrong. **Fixed.** Verified `scottish-prem` `[6]` and `belgian-pro`
`[6, 6]` against the same pairing-graph test; both correct.

### F9b. ESPN's placeholder crest stored as a league logo
Six leagues (`national-league`, `scottish-champ`, `romania-liga1`,
`norway-eliteserien`, `denmark-superliga`, `south-africa-psl`) carried ESPN's generic
grey-shirt `default-team-logo-500.png` as their league logo, which renders as a broken
placeholder next to the league name; the UI already renders nothing at all for the
eight leagues where ESPN returns null. Worse, `_stub_league_logo` reads the previous
build's own value back, so a placeholder stored once survived forever.
**Fixed** in both `fetch_league_teams._league_logo` and `_stub_league_logo`, and the
six registry rows normalised to null. ESPN genuinely has no logo for any of the 14 —
this is an upstream gap, the fix is just to stop dressing it up as an image.

### F9. Concacaf's two cups shipped null `rules`
`leagues-cup` and `concacaf-champions` were the only competitions with no rules text
while UCL/EL/UECL/Libertadores/Sudamericana all carry detailed descriptions.
**Fixed** — written from each competition's own fixture graph (CCC: 5 byes + 11
two-legged Round One ties, two-legged to the semis, one-off final, no away goals;
Leagues Cup: 36 clubs, two 18-club tables, 3 cross-league matches each, top 4 per
table to the quarter-finals).

---

## Flagged for upstream — not patched

### U1. `romania-liga1` / `liga-mx`-class fixture gaps produce degenerate odds
Where a season has started but no schedule exists, the sim has nothing to run and
every column collapses to 0/100 (CSU Craiova >99% champion off one 4–0 win; three
clubs at >99% relegation off one defeat). F6 labels this honestly but does not remove
it. The stronger fix — suppressing the probability columns entirely, or routing such
a league to `results_only` — is a product decision.
ESPN currently has **no** 2026-27 events for `rou.1`, `sui.1`, `eng.w.1`, `rsa.1`,
`tha.1`, `ind.1`; those leagues will hit this as their seasons start.

### U2. A league that reaches `status: completed` can never refresh itself
`.github/workflows/refresh-daily.yml` builds its matrix from payloads where
`status == "live"`, so the moment a league is classified `completed` the daily job
stops touching it. Only the weekly `refresh-leagues.yml` (which iterates `OUTLOOK`)
can ever flip it back. That is documented in the weekly workflow's own comment, but it
is what made liga-mx's false `completed` state sticky, and it left
`thai-league-1`, `eerste-divisie` and `k-league-1` generated `2026-07-14` while every
other league was `2026-07-23/24`.
**Resolved for now** — all three rebuilt (they also gained the `data_status` key,
which their old payloads predated). The structural coupling remains: a league wrongly
marked completed is invisible to the daily job that would otherwise correct it.

### U3. `canadian-pl` playoff contamination is not fixed
It is the only `api_football` league with a playoff, and `data_pipeline/api_football.py:167`
also hard-codes `is_playoff = 0`. The 2024 table still reads GP 28–31 (Forge's three
playoff matches counted). Low urgency — the league is `data_status: historical` — but
the same one-line class of fix applies if API-Football exposes a round/stage field.

### U4. `usl-league-one` model is worse than base rate in every year
`perf_by_year` shows the model losing to `naive` in **4/4** seasons (2023–2026), and
the payload's mean home-win probability is 0.370 against an observed home-win rate of
0.554 — the model is badly under-predicting home advantage in this league.
Other leagues with the model behind naive in half or more of their years:
`argentina-nacional` 7/10, `brazil-serie-b` 6/10, `bundesliga-2` 5/7,
`scottish-league-two` 5/7, `chile-primera` 5/10, `liga-expansion-mx` 5/9.

### U5. Cup competitions have no CSV export
`league_csv` is skipped when `outlook.columns` is empty, which is always true for
knockout mode — so all 7 cups are absent from `/open-data/` (71 of 78 exported).
`champion_odds` is a natural export shape for them.

### U6. Belgian Pro League: 18 clubs against a 16-club format model
`webapp/data/belgian-pro.js` carries 18 clubs and a 306-match double round robin for
2026-27, while `scripts/eval/season_format.py::FORMATS["belgian-pro"]` still encodes
the 16-club points-halving playoff model (`rr: 2, groups: [6, 6], carry: "half"`).
The group sizes are hard-coded and do not scale with the field. Worth confirming the
2026-27 format before the season starts.

### U6b. Relegation barrage modelled asymmetrically between tiers
`_TOP(ucl, rel)` makes `releg` a plain "bottom N" band, so for Germany, France, the
Netherlands, Portugal and Scotland the club in the relegation-**barrage** place is
counted as fully relegated (`releg` sums to 3.0 for the Bundesliga, whose own rules
text says "bottom 2 relegated, 16th plays a barrage"). The second-tier side of the
exact same barrage *is* modelled — `_PROMO(..., barrage=0.33)` gives 2. Bundesliga's
3rd a 33% shot, and its `promoted` column correctly sums to 2.33.
So one club is at 100% to go down and its opponent at 33% to come up, in the same tie.
The symmetric fix is a `barrage_lose_rate` on the `releg` bucket. Not applied here
because it changes published probabilities.

### U7. `conf` key collides across payload families
In MLS payloads `standings[].conf` is the conference name (`"East"`); in every
European payload it is the Conference League qualification percentage. Harmless today
because the two never share a code path, but it makes any generic standings consumer
type-unsafe (it already caused a `str < float` crash while adding F8).

---

## Per-league blocks

### mls — MLS  [full_forecast]
Verdict: ISSUES (2)

Odds gut check:      pass. 30 teams, playoff odds sum 900 per conference (9 berths
                     each), hfa 400 per conference (4 each), shield 100.0, cup 99.8,
                     conf_win 99.9 per conference. Mean pH 0.430 / pD 0.264 / pA 0.306
                     against observed 0.482 / 0.220 / 0.298. `perf_by_year` beats naive
                     in 3 of 5 years (2019 −1.32%, 2023 −0.09%).
Formatting:          `CF Montréal` renders correctly; updated date current; JSON-LD
                     SportsEvents point at real 2026-07-25 fixtures with venues.
                     Two bugs — F7 (`<1%`) and F8 (merged conference table).
Competition rules:   pass. Conferences, 9 playoff berths, Shield/MLS Cup columns all
                     correct for the competition.
Actions taken:       F7, F8 (`scripts/build_static_pages.py`).
Flagged for upstream: none.

### liga-mx — Liga MX  [full_forecast]
Verdict: ISSUES (4) — all fixed

Odds gut check:      was broken; every one of 8 qualifiers sat at 100% Liguilla after
                     one match and `proj_pts` equalled current points. After F1/F2:
                     Liguilla sum 800.1, Cruz Azul 88.4 / Toluca 85.5 / Pachuca 78.2.
Formatting:          title read "Liga MX 20" (F3); page badged "final" with a
                     fabricated champion (F2).
Competition rules:   top-8 Liguilla cut and "no relegation (suspended through 2026)"
                     are correct; `format_approximate` correctly false.
Actions taken:       F1, F2, F3. Rebuilt.
Flagged for upstream: none.

### canadian-pl — Canadian Premier League  [historical]
Verdict: ISSUES (3)

Odds gut check:      pass for what it is — a concluded 2024 archive, all columns
                     deterministic.
Formatting:          `historical` archive note renders correctly. Registry `logo` is
                     **null** for a tier-1 league.
Competition rules:   the payload's own rules say the championship is decided in the
                     playoffs, yet the page captioned Cavalry FC "Champions" (F5).
                     Table GP runs 28–31 because playoff matches are counted (U3).
Actions taken:       F5.
Flagged for upstream: U3 (api_football `is_playoff`), null logo.

### romania-liga1 — Liga I (Romania)  [full_forecast]
Verdict: ISSUES (4)

Odds gut check:      degenerate — one matchday played, no fixtures, so CSU Craiova
                     >99% champion and three clubs >99% relegated. See U1.
Formatting:          was "results · final · Champions: CSU Craiova · 100% of the
                     season played" off 8 matches; now live, no champion, no false
                     completion percentage, with an explicit no-forecast note.
                     Registry `logo` is the **default-team-logo placeholder**.
Competition rules:   `format_approximate` correctly true; rules honestly state the
                     championship play-off / play-out split is not modeled.
Actions taken:       F1 (9 → 16 teams), F6. Rebuilt.
Flagged for upstream: U1, placeholder logo.

### Concacaf cups — leagues-cup, concacaf-champions  [full_forecast]
Verdict: ISSUES (1) — fixed

Odds gut check:      pass. Both concluded; champion odds sum to 100 with the actual
                     winner at 100% (Seattle Sounders 2025, Toluca 2026). Leagues Cup
                     group tables are correctly split per league (18 + 18) with 3
                     cross-league matches each and exactly 8 clubs advancing.
Formatting:          pass.
Competition rules:   both shipped a null `rules` (F9).
Actions taken:       F9.
Flagged for upstream: U5 (no CSV export).

### ucl / europa / conference — UEFA  [full_forecast]
Verdict: CLEAN

Odds gut check:      pass. 2025-26 concluded, champion odds sum 100 with the winner at
                     100% (PSG / Aston Villa / Crystal Palace). 36-club league phase,
                     `playoff` column sums to 16 (the 9th–24th knockout play-off band).
Formatting:          pass.
Competition rules:   pass — `rules` describe both qualifying paths, the Swiss-model
                     league phase, the 8/16/12 split and the two-legged knockout, and
                     name what is not modeled.

### libertadores / sudamericana — CONMEBOL  [full_forecast]
Verdict: CLEAN

Odds gut check:      pass. `knockout_live`, champion odds sum 100, favourites are the
                     Brazilian sides (Palmeiras 19.8 / Cruzeiro 14.7 / Flamengo 14.1;
                     Botafogo 19.6 in the Sudamericana). `advance` sums to 16 — the
                     16 round-of-16 places.
Formatting:          pass.
Competition rules:   pass, and unusually careful — the Sudamericana rules explicitly
                     flag that runners-up are advanced directly because the
                     cross-competition inflow from the Libertadores cannot be
                     represented, and say their odds are correspondingly optimistic.

### venezuela-primera — Liga FUTVE  [results_only]
Verdict: ISSUES (2) — both fixed

Odds gut check:      the playoff-contamination fix (F4) **changed who tops the table**.
                     Before, Deportivo Táchira led on 20 GP against clubs on 13; with
                     the Apertura semi-finals and final removed, all 14 clubs sit on 13
                     and Deportivo La Guaira leads. The previous leader's advantage was
                     entirely post-season results.
Formatting:          page read "Champions: Deportivo Táchira"; now "Top of the table:
                     Deportivo La Guaira" (F5 + TITLE_BY_PLAYOFF).
Competition rules:   `format_approximate` correctly true; rules honestly say the real
                     berths come out of an Apertura/Clausura + final-series format.
Actions taken:       F4, F5. Rebuilt.

### greek-super — Greek Super League  [full_forecast]
Verdict: ISSUES (1) — fixed

Odds gut check:      pass. Pre-season 2026-27, 0 played / 182 fixtures, title 99.9
                     (AEK Athens 45.3 / Olympiacos 24.3 / PAOK 22.8), ucl 99.9 = 1 berth,
                     releg 200.0 = 2. Correctly badged "pre-season projection".
Formatting:          pass.
Competition rules:   rules text described a top-6 championship playoff the league has
                     not used since at least 2024-25 (F9a).
Actions taken:       F9a. Rebuilt.

### The 44 leagues not given an individual block
Every league was run through the mechanical checks (pmatrix row sums, per-match
`pH+pD+pA`, home-advantage direction, draw share, probability-column sums against the
real number of berths, per-team games played, SEO encoding/date/JSON-LD/canonical/CSV
parity) and through a favourites-and-rules review. Where a league is not written up
individually it means those checks came back clean and its `rules`, `format_label`,
`format_approximate`, column set and green/red lines matched the real competition.
Specifically verified clean and worth noting:

- **All 78** pass pmatrix and per-match probability integrity: every row sums to ~1000
  / ~1.0, no negatives, no upcoming fixture missing probabilities.
- **All 78** pass home-advantage direction (mean home win > mean away win) and draw
  share (all inside 0.19–0.34).
- **All 78** pass SEO checks: no mojibake, no stale "updated" date, canonical correct,
  JSON-LD parses, `dateModified` matches the visible date, every `SportsEvent` is a
  genuinely future fixture, and the "All 78 leagues" count matches the registry.
- **English tiers, big-5 and second tiers** have exactly correct promotion/playoff/
  relegation slot counts: Championship 2+4/3, League One 2+4/4, League Two 3+4/2,
  National League 1+6/4, Serie B's 6-team playoff, Segunda 2+4/4, Ligue 2 2+3/4 with
  the barrage at 33%, 2. Bundesliga 2+1/3 with its mirror barrage.
- **`epl` / `serie-a` at 5 UCL berths** is deliberate and documented in `rules`
  ("2025-26 coefficient allocation"), not a bug.
- **`argentina-primera` ships no relegation column at all** — correct, since Argentine
  relegation runs on multi-season *promedios* the sim does not model, and the rules
  text says so rather than inventing a column.
- **`bolivia-profesional`'s mean home win of 0.549** is the highest in the registry but
  matches an observed 0.500 home-win rate — altitude, not a swapped join.
- The **preseason squad-value tilt** (Ipswich projected above clubs with 100+ more ELO)
  is the documented, A/B-validated `_VALUE_BETA` correction for bottom-half clubs, not
  an ordering bug.

## 2026-07-25 — `romania-liga1` is live with zero upcoming fixtures (from the launch-readiness audit)

Surfaced by the new per-snapshot coverage manifest (`data/snapshot_coverage.json`, written by
`scripts/archive_odds_snapshot.py`) on its first real run.

- `webapp/data/romania-liga1.js`: `status: "live"`, `generated: 2026-07-25 12:02 UTC`, 8 games,
  **0 upcoming fixtures with dates**.
- Consequence: it contributes **zero rows** to `match_prob_history.parquet` while the site
  advertises it as a live competition. Under the paid tier this is a league a customer can see
  listed but which has no forecast history accruing at all.
- Not a launch blocker and not a crash — a silent coverage hole of exactly the class the manifest
  was added to make visible.
- **Hand-off:** belongs to `docs/league-qa-audit-prompt.md`. Likely either a fixture-source gap for
  the new Romanian season or a status flag that should not yet be `live`.
