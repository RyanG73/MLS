# UI Feedback Round 3 Implementation Plan

## Verdicts (newest first)

- **B1 ✅ B2 ✅ (2026-07-09):** `promoted` composite simulated server+client; sum(promoted) verified = slot count on all 7 second tiers (3.00 internal, 2.33 barrage); bracket JS↔Python parity ≤0.7pp on the live pmatrix. Pre-existing preseason σ-widening divergence in the client sim flagged as a spin-off task (task_8148b567). Rules lines shipped for every OUTLOOK league.
- **G1 ✅:** run-in difficulty panel (avg remaining-opponent ELO + next-3 chips) fills the desktop whitespace; hidden when no fixtures remain.
- **H1–H4 ✅:** input definitions inline+hover; live phase Brier (model/market/naive, client-side, all leagues) supersedes the MLS-only backtest slice; per-club Brier card on team profiles; decile card is paired predicted/observed bars with pp deltas. One TDZ crash found & fixed (FEATURE_DEFS had to precede the eager renderHealth call).
- **E1 ✅ E2 ✅:** scripts/build_news.py bakes 8 English-language feeds per league (anti-gossip filter, self-maintaining club-keyword routing, per-feed failures non-fatal, a file for every registry league so soon-leagues don't 404); client merges with live ESPN (now also gossip-filtered); club-news card on team pages. Verified: EPL news = 54 cards / 6 sources. GFFN needed a browser UA; GGFN dead → DW Sports.
- **F1 ✅ F2 ✅:** ko_utc/venue/venue_city as nullable extras on ESPN frames (canonical _COLS untouched); data_pipeline/weather.py (open-meteo, disk-cached geocode, all failures→None); MLS + European builders emit ko/venue/wx; expanded match rows show "⏱ Thu 7:30 PM · 📍 Stade Saputo · 🌡 20.6°C · 10% rain" (verified live).
- **I1 ✅:** UEFA Spots tab (UEFA leagues only) — coefficient explainer + country table generated from the sim's own OUTLOOK slot config; EPS stars on England/Italy explain 5-vs-4 UCL places.
- **W1 ✅ W2 ✅:** league-expansion report (football-data "new leagues" verified live: results+Pinnacle closings since 2012 for BRA/ARG/JPN/DEN/POL/SWE/NOR; ESPN probes for ksa.1/aus.1/eng.w.1; big-4 third tiers confirmed unavailable) and drift-tracking design; step 1a (archiver captures promoted/promo/conf/liguilla/playoffs) landed immediately.
- **R1 ◐ R2 ◐:** plumbing landed — `top15_value_eur` (quota 1/5/5/4, value-backfilled) in import_transfermarkt with unit tests; cross-tier ELO history stitch live (Hull City continuous 2014–2026 in the rebuilt epl.js, offsets composed along the England chain). REMAINING: R1 harness A/B vs total squad value and R2 unified two-tier ELO replay — run under docs/experiment-protocol.md as the next improvement campaign.
- **Suite:** 630 passed / 18 skipped; browser smoke 38/38 after the soon-league news-404 fix; validate_payloads 29/29.

- **A1 ✅ + A2 ✅ + C1 ✅ + C2 ✅ + D1 ✅ (2026-07-09):** Relabels shipped in registry + builders + built artifacts (sed'd in place; nightly build now emits the new names). Light-recolored lockup (`--recolor` added to matte_brand_logo.py) replaces the invisible navy moose in sidebar (176px, tagline removed) and header default. MLS table columns reordered Cup→Shield→PO→Top 4→Spoon; conference/outcome cards carry plain-language hints ("most points in conference"); squad-value positions show € amounts with % in parens. All verified via DOM probe in preview.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the 2026-07-09 user feedback round: correct promotion/playoff rules per league, MLS clarity fixes, branding fix, multi-source news, transfer-value money amounts, match metadata (time/venue/weather), a run-in visualization, model-health UX overhaul, a UEFA-coefficients explainer, two written reports (league expansion, projection-drift tracking), and two flagged model-research campaigns (top-15 constrained squad value, cross-tier ELO continuity).

**Architecture:** The webapp is a single static [webapp/index.html](webapp/index.html) (~2,180 lines, all CSS+JS inline) fed by per-league JS payloads built by [scripts/build_league_data.py](scripts/build_league_data.py) (Europe/Concacaf) and [scripts/build_dashboard_data.py](scripts/build_dashboard_data.py) (MLS). League registry lives in [scripts/fetch_league_teams.py](scripts/fetch_league_teams.py) → `webapp/leagues.js`. Anything simulated server-side in the season Monte-Carlo must be mirrored in the client's `runSimTable()`/`runSim()` (SIM PORTING CONTRACT, index.html ~line 872). Client-side computations (per-club Brier, phase Brier) are preferred where payloads already carry the raw data — no build change, works for all leagues.

**Tech stack:** Python 3 (pandas/numpy) pipeline, vanilla-JS static webapp, pytest (+ `tests/test_browser_smoke.py` Playwright smoke), Transfermarkt CSVs, ESPN public APIs, open-meteo (weather, no key), RSS via stdlib `xml.etree`.

**Execution notes:**
- Verdicts appended to this file per task (CLAUDE.md convention). Commit per task on `main`.
- Rebuilding a European league payload takes ~18 min — do NOT rebuild payloads to test UI changes; edit the built `webapp/data/*.js` in place where a payload field is needed for verification, and let the nightly build regenerate.
- Tasks W1–W2 (reports) and R1–R2 (model research) have no UI dependency and can run any time.

---

## Workstream A — Labels & branding

### Task A1: Relabel "English Premier League" → "Premier League", "Major League Soccer" → "MLS"

**Files:**
- Modify: `scripts/fetch_league_teams.py:36,47` (registry tuples)
- Modify: `scripts/build_league_data.py:323` (`OUTLOOK["epl"]["name"]`)
- Modify: `scripts/build_dashboard_data.py` (MLS league name string — grep `"Major League Soccer"`)
- Modify (in place, regenerated nightly): `webapp/leagues.js`, `webapp/data/epl.js`, `webapp/data/mls.js`

- [ ] **Step 1:** In `fetch_league_teams.py` change the two tuples: `("mls", "MLS", ...)` and `("epl", "Premier League", ...)`.
- [ ] **Step 2:** Change `OUTLOOK["epl"]["name"]` to `"Premier League"`; grep + change MLS name in `build_dashboard_data.py`.
- [ ] **Step 3:** Regenerate the registry: `python3 scripts/fetch_league_teams.py` writes `webapp/leagues.js` (verify names with grep). If the script requires network fetches, instead `sed -i '' 's/English Premier League/Premier League/; s/Major League Soccer/MLS/' webapp/leagues.js`.
- [ ] **Step 4:** Same sed for `webapp/data/epl.js` and `webapp/data/mls.js` (the `league.name` field) so the header updates before the next nightly build.
- [ ] **Step 5:** Verify in preview (sidebar + header title), commit.

### Task A2: Fix invisible moose; use full lockup in sidebar, bigger, no tagline

Both source logos (docs/logo1.PNG lockup, docs/logo2.PNG icon) are flat navy `rgb(7,30,46)` on near-white — invisible on the dark theme. [scripts/matte_brand_logo.py](scripts/matte_brand_logo.py) already reconstructs clean alpha; add a recolor step.

**Files:**
- Modify: `scripts/matte_brand_logo.py` (add `--recolor R,G,B`)
- Create: `webapp/assets/branding/entenser-lockup-light.png` (from docs/logo1.PNG), `webapp/assets/branding/entenser-icon-light.png` (from docs/logo2.PNG)
- Modify: `webapp/index.html:562` (sb-brand) and `:568` (header beacon)

- [ ] **Step 1:** In `matte()` after un-premultiply, if `recolor` is set, replace the RGB of every pixel with the recolor value, keep alpha:
```python
if recolor is not None:
    out_rgb[:] = np.array(recolor, dtype=np.float32)
```
plus `argparse` plumbing: `--recolor 227,233,228` (theme `--txt-1`).
- [ ] **Step 2:** Run:
```bash
python3 scripts/matte_brand_logo.py docs/logo1.PNG webapp/assets/branding/entenser-lockup-light.png --recolor 227,233,228
python3 scripts/matte_brand_logo.py docs/logo2.PNG webapp/assets/branding/entenser-icon-light.png --recolor 227,233,228
```
- [ ] **Step 3:** Replace the sidebar brand block with the lockup only, larger (`docs/logo1.PNG` is ~3:1 W:H):
```html
<div class="sb-brand"><img src="assets/branding/entenser-lockup-light.png" alt="Entenser" style="width:100%;max-width:170px;height:auto;object-fit:contain" /></div>
```
(drop the `<b>Entenser</b><span>Soccer Projections</span>` text entirely; adjust `.sb-brand` padding).
- [ ] **Step 4:** Header beacon img → `entenser-icon-light.png`.
- [ ] **Step 5:** Preview screenshot to confirm visibility on dark bg; commit.

---

## Workstream B — League rules correctness

### Task B1: Promotion-playoff simulation → honest "Promoted" probability

Second tiers already have `_PROMO(promo, band, rel)` buckets, but nothing simulates the playoff, so users see a "Playoff" (reach) probability, not "gets promoted". Add a simulated playoff-winner outcome, mirrored server + client.

**League rules to encode (verified 2025-26 formats):**
| League | Auto | Playoff (winner promoted) | Notes |
|---|---|---|---|
| Championship | 1–2 | 3–6, semis 3v6/4v5, final | internal |
| League One | 1–2 | 3–6 | internal; bottom 4 drop |
| League Two | 1–3 | 4–7 | internal; bottom 2 drop |
| Serie B | 1–2 | 3–8 (5v8, 6v7 prelim; 3,4 byes) | approximate as seeded KO with byes |
| LaLiga 2 | 1–2 | 3–6 | internal |
| Ligue 2 | 1–2 | 3–5 playoff → barrage vs Ligue 1 16th | cross-league barrage |
| 2. Bundesliga | 1–2 | 3rd → barrage vs Bundesliga 16th | cross-league barrage |

Cross-league barrages can't use the pmatrix (opponent not in league). Use the historical base rate: the tier-2 side wins ~33% of German/French barrages — encode as `barrage_win_rate: 0.33` in the bucket and document it in the hint.

**Files:**
- Modify: `scripts/build_league_data.py` — `_PROMO` gains a `promoted` composite bucket; sim loop simulates the bracket; new `playoff_format` block in payload `outlook`
- Modify: `webapp/index.html` — `runSimTable()` mirrors the bracket; tableLadder col renders `promoted`
- Test: `tests/test_second_tier_leagues.py` (extend), new `tests/test_promo_playoff_sim.py`

- [ ] **Step 1:** Write failing test `tests/test_promo_playoff_sim.py`: given a uniform pmatrix (all ties 33/33/33), a 24-team league with `_PROMO(2,[3,6],3)` sim must produce, for a team locked at rank 3–6, `promoted ≈ auto + 0.25 × P(in band)` within MC noise, and `sum(promoted over all teams) ≈ 3.0`.
- [ ] **Step 2:** Extend `_PROMO`:
```python
_PROMO = lambda promo, play, rel, barrage=None: [
    {"key": "promo", "label": "Auto Promo", "col": "Auto", "top": promo},
    {"key": "playoff", "label": "Promo Playoff", "col": "Playoff", "band": play, "card": False},
    {"key": "promoted", "label": "Promoted", "col": "Promoted",
     "promo_top": promo, "playoff_band": play,
     **({"barrage_win_rate": barrage} if barrage else {})},
    {"key": "releg", "label": "Relegation", "col": "Releg", "bottom": rel}]
```
Update OUTLOOK second tiers: `bundesliga-2` → `_PROMO(2, [3,3], 3, barrage=0.33)`, `ligue-2` → `_PROMO(2, [3,5], 4, barrage=0.33)`; others unchanged signature.
- [ ] **Step 3:** In the season-sim bucket tally (`_bucket_members` call site), handle the composite key: auto-promo teams count 1.0; for the band, run the bracket per iteration with `pwin(h,a) = (pm[h][a][0] + 0.5*pm[h][a][1])` seeding higher rank as host (semis high-v-low, then final; for Serie B's 6-team band: 5v8/6v7 prelims then 3v(6/7 winner), 4v(5/8 winner) semis, final). If `barrage_win_rate` set, multiply the bracket winner's tally by it (or, for bundesliga-2's [3,3] band, credit rank-3 directly × rate).
- [ ] **Step 4:** Mirror the same bracket in `runSimTable()` in index.html (the what-if resim). Acceptance per the SIM PORTING CONTRACT: JS@10k within ±1.5pp of server@20k on an unforced sim.
- [ ] **Step 5:** Run `pytest tests/test_promo_playoff_sim.py tests/test_second_tier_leagues.py -v` → PASS.
- [ ] **Step 6:** Rebuild ONE league to validate end-to-end (`python3 scripts/build_league_data.py --league championship` — ~18 min, run in background, capture log per memory rule), verify `promoted` column renders, commit.

### Task B2: Per-league rules line under the table

**Files:** `scripts/build_league_data.py` (OUTLOOK gains `rules` string per league; payload `outlook.rules`), `webapp/index.html` `renderTableOutlook()` laddernote.

- [ ] **Step 1:** Add `rules` strings, e.g. championship: `"Top 2 promoted automatically · 3–6 promotion playoff (winner promoted) · bottom 3 relegated"`; bundesliga-2: `"Top 2 promoted · 3rd plays a barrage vs the Bundesliga's 16th (modeled at 33%) · bottom 2 relegated, 16th plays the barrage"`; epl: `"Top 5 qualify for the Champions League (2025-26 coefficient allocation) · bottom 3 relegated"`; etc. for every OUTLOOK league.
- [ ] **Step 2:** `renderTableOutlook()`: prefer `ol.rules` over the generated `top N qualify · bottom M drop` note. Emit into payloads in place via sed only if needed for verification; otherwise wait for nightly build.
- [ ] **Step 3:** Commit.

---

## Workstream C — MLS clarity

### Task C1: MLS trophy column order Cup → Shield → Playoffs → Top 4 → Spoon

**Files:** `webapp/index.html:1020-1035` (`ladder()` col-head + row cells).

- [ ] **Step 1:** Reorder header spans to `Cup · Shield · PO · Top 4 · Spoon` and the `hcell` calls to `hcell(t.cup,'cup')+hcell(t.shield,'sh')+hcell(t.playoff,'po')+hcell(t.hfa,'hfa')+hcell(t.spoon,'sp')`.
- [ ] **Step 2:** Verify in preview (MLS view), check `tests/test_browser_smoke.py` still passes, commit.

### Task C2: Conference boxes say "best record", not playoff advancement

**Files:** `webapp/index.html:977-991` (`favCard`/`renderFavs`).

- [ ] **Step 1:** Extend `favCard(cls,lab,t,k,hint)` to render a hint under the label; call with `favCard('east','Eastern Conference',sByConf('East'),'conf_win','most points in conference')` and same for West. This is the regular-season #1 seed (the sim's `conf_win` = rank-1 by points key), NOT odds of winning the conference playoff bracket.
- [ ] **Step 2:** Verify + commit.

---

## Workstream D — Transfer value amounts

### Task D1: Show € amounts per position group, not just %

Payload already ships `squad_value_eur` + `att/mid/def/gk_value_pct` — the € split is derivable client-side (`total × pct`). No pipeline change (YAGNI).

**Files:** `webapp/index.html:1843` (`posRow` in `squadValuePanel`).

- [ ] **Step 1:**
```js
const posRow=(label,pct)=>{const eur=(pct!=null&&sv.squad_value_eur)?'€'+(sv.squad_value_eur*pct/1e6).toFixed(1)+'m':null;
  return `<div class="pstat"><span class="k">${label} value</span><span class="v">${pct==null?'—':`${eur} <span style="color:var(--txt-3);font-weight:400">(${(pct*100).toFixed(0)}%)</span>`}</span></div>`;};
```
- [ ] **Step 2:** Verify on a team with TM data + a league without (null state unchanged), commit.

---

## Workstream E — News

### Task E1: Multi-source news (The Athletic/NYT, Guardian, BBC, Sky + one English-language source per big country)

RSS is CORS-blocked client-side → bake at build time. Keep the live ESPN fetch and merge.

**Feed registry (all English-language, news/tactics/analytics — not gossip):**
- Global/England: NYT The Athletic football `https://www.nytimes.com/athletic/rss/football/`, Guardian `https://www.theguardian.com/football/rss`, BBC `https://feeds.bbci.co.uk/sport/football/rss.xml`, Sky Sports `https://www.skysports.com/rss/12040`
- Italy: Football Italia `https://football-italia.net/feed/`
- France: Get French Football News `https://www.getfootballnewsfrance.com/feed/`
- Germany: Get German Football News `https://www.getgermanfootballnews.com/feed/`
- Spain: Football España `https://www.football-espana.net/feed/`

**Files:**
- Create: `scripts/build_news.py`, Test: `tests/test_build_news.py`
- Create (output): `webapp/data/news/<league-id>.js` → `window.NEWS_DATA`
- Modify: `webapp/index.html` `renderNews()`; `scripts/daily_build.sh` (add step)

- [ ] **Step 1:** Failing test: feed-item→league routing. `route_item(title, desc)` returns league ids by keyword map (club names from `webapp/data/logos.js` keys + league aliases: "Premier League"→epl, "Serie A"→serie-a…), and `is_gossip(title)` blacklists `rumour|rumor|gossip|linked with|transfer news live|reportedly eyeing`.
- [ ] **Step 2:** Implement `scripts/build_news.py`: fetch each feed with `data_pipeline/http.py` helpers (timeout, UA), parse with `xml.etree.ElementTree` (`item` → title/link/pubDate/description/source), route to leagues, drop gossip, sort by date, cap 30/league, write `webapp/data/news/<lid>.js` with `window.NEWS_DATA = {...}` via `scripts/payload_utils.write_js_payload`. Failures per-feed are warnings, never fatal.
- [ ] **Step 3:** `renderNews()`: `document.write`-load `data/news/<LID>.js` alongside the league payload (cache-busted like the others); merge baked items with the live ESPN fetch, dedup by normalized title, tag each card with its source name; note becomes `"<league> · ESPN + curated feeds"`.
- [ ] **Step 4:** Add `python3 scripts/build_news.py` to `scripts/daily_build.sh`. Run it once for real; verify the News tab shows mixed sources. `pytest tests/test_build_news.py -v` PASS. Commit.

### Task E2: Team pages get a club-specific news list

**Files:** `webapp/index.html` (`renderProfile` — new async section), reuses E1's `NEWS_DATA` + live ESPN league fetch.

- [ ] **Step 1:** `clubNews(team)`: filter merged league articles where headline/description contains the club name (normalize: strip FC/AFC, accents). Render up to 6 `pmini`-style rows in a `pcard` "Club news"; if none match, show "No recent club-specific stories — see the News tab."
- [ ] **Step 2:** Wire into `renderProfile` grid (full-width card after squad value), verify for a busy club (e.g. Arsenal) + an empty case, commit.

---

## Workstream F — Match metadata (time, venue, weather)

### Task F1: Kickoff time + venue through the pipeline

**Files:**
- Modify: `data_pipeline/espn_fixtures.py:170-180` — keep `ko_utc` (full ISO timestamp) and `venue` (`competitions[0].venue.fullName` + `.address.city`) columns
- Modify: `scripts/build_league_data.py` upcoming-cards block (~line 1118) and `scripts/build_dashboard_data.py` equivalent — emit `"ko"` and `"venue"` on game cards
- Modify: `webapp/index.html` `renderGames()` — expanded row header shows `⏰ local kickoff · 📍 venue`
- Test: `tests/test_espn_fixtures.py` (extend with a fixture-JSON case asserting ko_utc/venue survive)

- [ ] **Step 1:** Failing test for the new columns. **Step 2:** Pipeline change. **Step 3:** Payload emission (guard: fields optional, old parquets lack them). **Step 4:** UI: in the `gr-why` block prepend `<div class="why-meta">${koLocal(g.ko)}${g.venue?' · '+g.venue:''}${wxStr(g)}</div>` where `koLocal` uses `toLocaleTimeString`. **Step 5:** pytest + preview verify, commit.

### Task F2: Weather at kickoff (open-meteo, no key)

**Files:**
- Create: `data_pipeline/weather.py` + `tests/test_weather.py`
- Modify: `scripts/build_league_data.py` / `build_dashboard_data.py` — attach `"wx": {"temp_c": …, "precip_pct": …}` for games <7 days out
- Modify: `webapp/index.html` — `wxStr(g)` renders `18°C · 40% rain`

- [ ] **Step 1:** `geocode(city)` → open-meteo geocoding API, cached in `data/venue_geo.json`. `forecast(lat, lon, iso_hour)` → `https://api.open-meteo.com/v1/forecast?latitude=…&longitude=…&hourly=temperature_2m,precipitation_probability` pick the kickoff hour. All failures → `None` (never break a build). Tests mock HTTP.
- [ ] **Step 2:** Wire into both builders behind `--no-weather` escape hatch; UI string; pytest; commit.

---

## Workstream G — Fill the desktop whitespace (table leagues)

### Task G1: "Run-in" schedule-difficulty panel under Projected Finish

**Files:** `webapp/index.html` — new `runInPanel()` appended in `renderTableOutlook()` after `finishPlotPanel()`.

- [ ] **Step 1:** Client-side, zero build changes: for each team, remaining fixtures = `UPCOMING` filtered by team; difficulty = mean opponent ELO (from `STAND`), home games discounted −40. Render all teams sorted hardest-first: name + a difficulty bar (scaled min→max) + next-3 opponent chips (`v`/`@` + monogram + date). Panel header "Run-in — remaining schedule difficulty · avg opponent ELO".
- [ ] **Step 2:** Empty state when `NF===0` (season done/preseason): hide panel. Verify desktop layout fills the right column (screenshot), mobile stacks cleanly. Commit.

---

## Workstream H — Model Health legibility

### Task H1: Input-completeness redesign + feature definitions on hover

**Files:** `webapp/index.html` `renderHealth()` feature block (~line 1442).

- [ ] **Step 1:** Add `FEATURE_DEFS` map (plain-English, one line per family): ELO→"Team strength rating updated after every match (K=25, home advantage 80)", xG→"Expected goals — shot-quality rolling averages over the last 3/5/10/15 matches", Form→"Points per game over recent matches", Schedule→"Rest days and fixture congestion", Availability→"Share of the squad healthy and available", GK→"Goalkeeper quality (save % above expected, z-scored)", is_playoff→"Playoff-match flag (0 all regular season — expected)", Market→"De-vigged betting-market probabilities where a line exists".
- [ ] **Step 2:** Restructure each row: family name + `ⓘ` with `title=` tooltip AND a visible one-line `hnote`-style description under the name; keep one "Complete" bar; demote "Active (≠0)" to small text (`92% active`) instead of a second bar. Replace the footnote with per-family notes only where the value is surprising.
- [ ] **Step 3:** Preview verify + commit.

### Task H2: Brier by season phase vs market and naive

Computed client-side from `D.games` (played rows carry `pH/pD/pA`, `result`, and `mkt_*` where a line exists) — works for every league, replaces the MLS-only `trust.by_season_phase` card.

- [ ] **Step 1:** `phaseBrier()`: split played games into thirds by date (Early/Mid/Late). Per slice compute mean 3-way Brier for (a) model, (b) market (matched subset only, de-vigged probs already in payload), (c) naive = this league's played-set base rates (constant vector). Render three grouped mini-bars per phase + n, colors: model green / market blue / naive gray; note "market on n matched games".
- [ ] **Step 2:** Replace the old phase card in `renderHealth()`; keep trust-based card only as fallback when `D.games` has <30 played. Verify on EPL (has market) + NWSL (no market → model vs naive only). Commit.

### Task H3: Per-club Brier on team pages (vs market + naive)

- [ ] **Step 1:** In `renderProfile`, from `gms.filter(g=>g.result)` compute club-scoped model/market/naive Brier (same math as H2, market = matched subset with its n). New pcard "Model accuracy — this club": three rows + a one-liner ("lower is better; naive = league base rates").
- [ ] **Step 2:** Verify a market league + a no-market league; commit.

### Task H4: Clean up "Brier by favorite-probability decile"

- [ ] **Step 1:** Replace text rows (`45%→48% n=…`) with paired horizontal bars per decile: predicted (outline) vs observed (filled), aligned to one 0–100% axis, delta labeled at the row end and colored by |gap| (<3pp green, <6pp amber, else red). Intro copy: "When the model says the favorite wins X%, how often does it actually? Bars should match."
- [ ] **Step 2:** Keep the reliability scatter unchanged; verify; commit.

---

## Workstream I — UEFA coefficients explainer

### Task I1: "UEFA Spots" tab for UEFA leagues

Champions-League place counts vary by season via association coefficients (EPL/Serie A had 5 in 2025-26). Data already lives in [data_pipeline/coefficients.py](data_pipeline/coefficients.py) (country coefficients, refreshed ~annually).

**Files:**
- Create: `scripts/build_coefficients_page.py` → `webapp/data/coefficients.js` (`window.COEFF_DATA`)
- Modify: `webapp/index.html` — seg gains a `UEFA Spots` tab (rendered only when `D.league.confederation==='UEFA'` or the payload group is a UEFA cup); new `renderCoeffs()`
- Test: `tests/test_coefficients.py` (extend: page builder emits every modeled UEFA league)

- [ ] **Step 1:** Builder exports, per association: coefficient value, rank, and 2025-26 UCL/UEL/UECL slot allocation (encode the allocation table: ranks 1–4 → 4 UCL, +2 European Performance Spots to the top-2 associations of the prior season, cup-winner paths noted as unmodelable), flagging which modeled league maps to which association.
- [ ] **Step 2:** `renderCoeffs()`: (a) explainer copy — how 5-year coefficients accrue (points per win/draw ÷ clubs entered, bonuses), how they set next season's slots, why the site's UCL columns are approximations; (b) association table (rank, coefficient, UCL/UEL/UECL spots) with the current league's row highlighted; (c) "performance spots" panel naming the current leaders. Hide tab for Concacaf leagues.
- [ ] **Step 3:** pytest + preview verify + commit.

---

## Workstream W — Written reports

### Task W1: League-expansion feasibility report

**Files:** Create `docs/league-expansion-report.md`.

- [ ] **Step 1:** Rank candidates on: (1) results/schedule source (football-data.co.uk "extra" CSVs cover Argentina, Brazil, Japan, Denmark, Poland, Sweden, Norway, Austria, Switzerland…; ESPN codes exist for Saudi `ksa.1`, A-League `aus.1`, WSL `eng.w.1`), (2) closing-odds availability (needed for the market Brier + edge product), (3) xG availability (Understat: none of these; ESPN/ASA: none → goals-only model family, the C1 path), (4) season-calendar shape (Apertura/Clausura & calendar-year already solved for Liga MX/MLS), (5) Transfermarkt coverage, (6) betting-market liquidity. Include the user's asks: Brazil, Argentina, Australia, Japan, Saudi Arabia, Denmark, Poland, Sweden, Norway, WSL. Also answer the lower-division question: 3. Liga / Ligue National / Serie C / Primera Federación — feasibility hinges on results+odds coverage (football-data has none of the 4; ESPN has partial fixtures; flag as verify-first, lowest tier).
- [ ] **Step 2:** Deliver tiered ranking (Ship next / Needs odds source / Research), one paragraph each, a summary table, and a recommended next-3. Send file to user. Commit.

### Task W2: Projection-catalog & model-drift tracking design report

**Files:** Create `docs/projection-drift-tracking.md`.

- [ ] **Step 1:** Audit what exists: `scripts/archive_odds_snapshot.py` (match-odds snapshots), `scripts/build_movers.py` (last-two-build season-odds deltas), `webapp/data/source_health.parquet`.
- [ ] **Step 2:** Design: (a) nightly append-only parquet `data/projection_log/{date}.parquet` — every team×outcome probability + every upcoming match×(pH,pD,pA) with build id, model config hash, league; (b) retention & size estimate; (c) drift metrics — trajectory plots per team-outcome, probability churn (mean |Δp| per build), calibration-over-time (rolling 90-day reliability), champion-config change markers; (d) alerting thresholds (churn spike without news = investigate); (e) UI hook (Model Health gains a "Projection stability" card); (f) implementation task list sized for a future round. Send file to user. Commit.

---

## Workstream R — Model research (run under docs/experiment-protocol.md; gate via promotion_gate.py)

### Task R1: Top-15 position-constrained squad value feature

Hypothesis: transfer value of a best-XI+bench proxy (top 1 GK + 5 DEF + 5 MID + 4 FWD by value) beats total squad value (dilution from unplayable depth).

**Files:** `scripts/import_transfermarkt.py` (`_aggregate_team` emits `top15_value_eur`), `scripts/eval_baseline.py` feature section, `docs/feature-hunt-log.md`.

- [ ] **Step 1:** In `_aggregate_team`, using `_pos_group` buckets, take top-by-value 1 GK / 5 DEF / 5 MID / 4 FWD (pad from the next-most-valuable players regardless of position when a bucket is short — positional flexibility caveat), sum → `top15_value_eur`; add column to mapped CSVs; unit test in `tests/test_transfermarkt_mapping.py` with a synthetic 20-player squad (assert a 16th striker's value is excluded but a short-DEF squad backfills).
- [ ] **Step 2:** A/B in the harness per verification protocol: baseline vs `+top15_value` (as ratio to league mean, same transform as the existing squad-value feature) — `--xgb-bag 5 --seed 42`, confirm at a second base seed; log to `docs/feature-hunt-log.md`; gate with `promotion_gate.py` before any champion change.

### Task R2: Cross-tier ELO continuity (the Hull City jump)

Team-page `elo_history` is built per-league-frame, so a relegated club's line freezes at relegation and jumps on return. Model-side promoted/relegated seeding exists (`_TIER2_FOR` bridging, build_league_data.py:167-290) — this task is (a) display continuity and (b) calibrating the bridge.

- [ ] **Step 1 (display):** In `build_league_data.py`, when building `elo_hist` for a top-flight league, stitch each team's tier-2 frames (England chain epl↔championship↔league-one↔league-two; ger/fra/ita/esp 1↔2) by concatenating that team's match-ELO series across frames with the fitted league offset applied (`experiments/league_offsets.json` via `coefficients.league_offset`), sorted by date. Hull City's line then declines through the Championship years instead of jumping. Extend `tests/test_build_league_data_tier2.py` with a two-frame stitch case.
- [ ] **Step 2 (calibration, research):** Evaluate whether continuous cross-tier ELO (one rating updated through both tiers) beats the current seed-on-promotion approach: replay England 2017–2025 with a unified two-tier ELO, compare promoted-team match Brier vs the current `promoted_team_brier` slice. Judge on the standard bagged config; results to `docs/feature-hunt-log.md`; only port if the gate passes.

---

## Docs closeout task

- [ ] Append blockquote entry to `docs/PLAN.md`; update `docs/CURRENT_STATE.md` if payload contract changed (new game-card fields ko/venue/wx, outlook.rules, promoted bucket); PROJECT_HISTORY entry + delete this plan when all tasks land.

## Self-review notes
- Spec coverage: 18 feedback items → A1 (two relabels), A2 (logo×2), B1/B2 (playoff rules), C1 (column order), C2 (conference boxes), D1 (money amounts), E1 (RSS sources), E2 (club feeds), F1/F2 (match info), G1 (whitespace viz), H1 (completeness+definitions), H2 (phase Brier vs market/naive), H3 (club Brier), H4 (decile cleanup), I1 (coefficient tab), W1 (expansion report + lower-divisions question), W2 (drift report), R1 (top-15 value), R2 (ELO calibration). ✔ all covered.
- Sim contract: B1 touches both engines — acceptance step included.
- No payload rebuild required to verify UI-only tasks (C, D, G, H) — they read existing fields.
