# UI Feedback Batch Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the 2026-07-08 UI feedback batch (design: `docs/superpowers/specs/2026-07-08-ui-feedback-batch-design.md`) — bug fixes, a squad-value 4-way breakdown rollout, the Entenser rebrand, MLS top-box completion, mobile layout fixes, and navigation changes.

**Architecture:** All frontend work is in one file, `webapp/index.html` (a single-page static dashboard, no build step, no JS framework, no bundler). Data-pipeline work touches `scripts/import_transfermarkt.py` (position-group aggregation), `scripts/build_dashboard_data.py` / `scripts/build_league_data.py` (squad-value passthrough), and a small standalone patch script that regenerates only the `squad_value` key of already-built `webapp/data/*.js` payloads — deliberately avoiding the full multi-hour model rebuild (ELO/DC/XGB/20k sims) since squad value is independent of the prediction model.

**Tech Stack:** Python 3 (pandas, pytest) for the data pipeline; vanilla JS/CSS/HTML for the frontend; Playwright (`tests/test_browser_smoke.py`) for browser-level regression tests.

---

## Important grounding notes (read before starting)

- **MLS top boxes are already 4 cards** (Shield / East / West / Spoon), not 3. The `outlook.cards` array `mls.js` carries (`playoff`/`shield`/`cup`) is **dead data** — `renderFavs()` in `index.html` (~line 928) hardcodes the 4-card layout and never reads `outlook.cards` for MLS. Only a 5th "MLS Cup" card needs to be added.
- **The EPL "Tottenham 12th vs 17th" bug is a real, reproduced discrepancy** between two independent simulation engines: the Python build bakes `proj_pts`/`proj_rank` into `D.standings` (Tottenham: 47.9 pts, rank 12), while the client's own `runSimTable()` (used only by the "Projected Finish" plot) independently re-simulates from `SIM.pmatrix` and gets a materially different mean (~41 pts, rank ~16-17) for the same team. Verified via a faithful Python port of the client's Monte Carlo loop against `webapp/data/epl.js`'s actual `sim.pmatrix`/`games`. This is NOT a data-join bug — full reconciliation of the two engines is out of scope for this batch. The scoped fix: anchor the "Projected Finish" plot's row order and median marker to the already-baked, already-correct `proj_rank`/`proj_pts` (consistent with the main standings table), while keeping the client sim's percentile spread for context.
- **Squad-value ATT/DEF split is already live** for EPL, Championship, League One, League Two, Bundesliga, 2. Bundesliga, La Liga, Segunda, Serie A, Serie B, Ligue 1, Ligue 2, Liga MX, Eredivisie, Primeira, Süper Lig, Scottish Premiership, Belgian Pro, Greek Super League, and MLS — all 19 leagues in `TM_LEAGUE_CODES` plus MLS already have cached raw per-player CSVs (`data/transfermarkt_squad_values_<CODE>_2026.csv`). Adding Midfield + GK percentages is one function change (`_aggregate_team()`) plus an **offline** `--skip-fetch` re-run — no new scraping.
- **Do not run the full model-rebuild scripts** (`scripts/build_league_data.py`, `scripts/build_dashboard_data.py`) just to refresh squad value — each takes ~18 minutes of CPU-bound work per league (per project memory), and squad value doesn't depend on the prediction model at all. Task 9 below writes a small standalone patch script instead.
- 8 team-logo gaps have **no ESPN-hosted crest at all** (verified live against ESPN's API): Energie Cottbus, RC Celta Fortuna, Académico de Viseu, Lommel SK, Defense Force FC, Forge FC, Mount Pleasant FA, Universidad O&M. These keep the existing graceful monogram-initial fallback (`.crest .mono`) — do not fabricate a logo URL for them.

---

## Workstream 1 — Bug fixes & formatting

### Task 1: Odds decimal formatting — show one decimal for values strictly between 0 and 1

**Files:**
- Modify: `webapp/index.html:945` (`hcell`, MLS conference ladder heat cells)
- Modify: `webapp/index.html:1057` (`hc`, single-table `tableLadder` heat cells)
- Modify: `webapp/index.html:1236-1237` (`koCell`, knockout heat cells)
- Test: `tests/test_browser_smoke.py` (new test class)

- [ ] **Step 1: Add a shared decimal-aware formatter and use it in all three heat-cell functions**

Current (`index.html:945`):
```js
function hcell(v,key){return v<0.05?`<span class="heat z">·</span>`:`<span class="heat" style="${heat(v,RGB[key],MAX[key])}">${v.toFixed(0)}</span>`;}
```
Replace with (add the shared helper right above `hcell`, since `hc` and `koCell` are defined later in the same script and can reuse it):
```js
const oddsFmt=v=>(v>0&&v<1)?v.toFixed(1):v.toFixed(0);   // sub-1% odds keep one decimal so they don't read as "0"
function hcell(v,key){return v<0.05?`<span class="heat z">·</span>`:`<span class="heat" style="${heat(v,RGB[key],MAX[key])}">${oddsFmt(v)}</span>`;}
```

Current (`index.html:1057`):
```js
const hc=(v,k,t)=>v<0.05?`<span class="heat z"${finTip(t)}>·</span>`:`<span class="heat" style="${heat(v,brgb(k),mx[k])}"${finTip(t)}>${v.toFixed(0)}</span>`;
```
Replace with:
```js
const hc=(v,k,t)=>v<0.05?`<span class="heat z"${finTip(t)}>·</span>`:`<span class="heat" style="${heat(v,brgb(k),mx[k])}"${finTip(t)}>${oddsFmt(v)}</span>`;
```

Current (`index.html:1236-1237`):
```js
const koCell=(p,rgb)=> p==null||p<0.005?`<span class="heat z">·</span>`
    :`<span class="heat" style="${heat(p*100,rgb,100)}">${(p*100).toFixed(0)}</span>`;
```
Replace with:
```js
const koCell=(p,rgb)=> p==null||p<0.005?`<span class="heat z">·</span>`
    :`<span class="heat" style="${heat(p*100,rgb,100)}">${oddsFmt(p*100)}</span>`;
```

- [ ] **Step 2: Add a Playwright regression test**

Append to `tests/test_browser_smoke.py` (new class, after `TestRouteStateCorrectness`):
```python
class TestOddsDecimalFormatting:
    """Sub-1% odds in the league table must show one decimal, not round to '0'."""

    def test_epl_table_has_sub_one_percent_with_decimal(self, page: Page, webapp_url: str):
        _load_route(page, webapp_url, "epl")
        text = _visible_body_text(page)
        # EPL preseason title odds include several teams under 1% (e.g. relegation
        # candidates' title odds) — at least one heat cell must render "0.X", not a bare "0".
        import re as _re
        assert _re.search(r"\b0\.\d\b", text), (
            "Expected at least one sub-1% odds cell formatted as '0.X' on the EPL table"
        )
```

- [ ] **Step 3: Run the test to verify it fails, then passes**

Run: `venv/bin/python -m pytest tests/test_browser_smoke.py::TestOddsDecimalFormatting -v --browser chromium`
Expected before Step 1: FAIL (no `0.X` pattern found — everything rounds to whole numbers).
Apply Step 1, re-run: PASS.

- [ ] **Step 4: Commit**

```bash
git add webapp/index.html tests/test_browser_smoke.py
git commit -m "fix(ui): show one decimal for sub-1% odds in league tables"
```

---

### Task 2: Fill resolvable missing team logos

**Files:**
- Modify: `webapp/data/logos.js`

- [ ] **Step 1: Add the 23 resolved entries**

`webapp/data/logos.js` is a single-line `window.TEAM_LOGOS = {...};` file. Add these 23 keys (exact team-name strings as used in `webapp/data/*.js`, verified against ESPN's live team API 2026-07-08) to the object. Do not remove or reformat existing entries — insert alongside them:

```json
"Bolton": "https://a.espncdn.com/i/teamlogos/soccer/500/358.png",
"Burnley": "https://a.espncdn.com/i/teamlogos/soccer/500/379.png",
"Cardiff": "https://a.espncdn.com/i/teamlogos/soccer/500/347.png",
"Lincoln": "https://a.espncdn.com/i/teamlogos/soccer/500/314.png",
"West Ham United": "https://a.espncdn.com/i/teamlogos/soccer/500/371.png",
"Wolverhampton Wanderers": "https://a.espncdn.com/i/teamlogos/soccer/500/380.png",
"Cambridge": "https://a.espncdn.com/i/teamlogos/soccer/500/351.png",
"Leicester": "https://a.espncdn.com/i/teamlogos/soccer/500/375.png",
"Oxford": "https://a.espncdn.com/i/teamlogos/soccer/500/311.png",
"Sheffield Weds": "https://a.espncdn.com/i/teamlogos/soccer/500/399.png",
"Exeter": "https://a.espncdn.com/i/teamlogos/soccer/500/324.png",
"Northampton": "https://a.espncdn.com/i/teamlogos/soccer/500/353.png",
"Rochdale": "https://a.espncdn.com/i/teamlogos/soccer/500/303.png",
"Rotherham": "https://a.espncdn.com/i/teamlogos/soccer/500/402.png",
"York City": "https://a.espncdn.com/i/teamlogos/soccer/500/315.png",
"1. FC Heidenheim 1846": "https://a.espncdn.com/i/teamlogos/soccer/500/6418.png",
"VfL Osnabruck": "https://a.espncdn.com/i/teamlogos/soccer/500/7013.png",
"VfL Wolfsburg": "https://a.espncdn.com/i/teamlogos/soccer/500/138.png",
"SV Elversberg": "https://a.espncdn.com/i/teamlogos/soccer/500/10388.png",
"CD Sabadell": "https://a.espncdn.com/i/teamlogos/soccer/500/11487.png",
"Eldense": "https://a.espncdn.com/i/teamlogos/soccer/500/7320.png",
"Tenerife": "https://a.espncdn.com/i/teamlogos/soccer/500/245.png",
"Maritimo": "https://a.espncdn.com/i/teamlogos/soccer/500/552.png"
```

Concretely: open the file, find the closing `};` at the end of the single-line object, and insert `,"Bolton":"https://a.espncdn.com/i/teamlogos/soccer/500/358.png",...` (all 23, comma-separated, no trailing comma before the closing brace) just before it.

- [ ] **Step 2: Verify no JSON syntax break and no dupe keys**

Run:
```bash
python3 -c "
import json
txt = open('webapp/data/logos.js').read().split('=',1)[1].rstrip(';\n')
d = json.loads(txt)
for k in ['Bolton','Burnley','Cardiff','Lincoln','West Ham United','Wolverhampton Wanderers','Cambridge','Leicester','Oxford','Sheffield Weds','Exeter','Northampton','Rochdale','Rotherham','York City','1. FC Heidenheim 1846','VfL Osnabruck','VfL Wolfsburg','SV Elversberg','CD Sabadell','Eldense','Tenerife','Maritimo']:
    assert k in d, f'missing {k}'
print('OK,', len(d), 'total entries')
"
```
Expected: `OK, 799 total entries` (776 original + 23 new).

- [ ] **Step 3: Commit**

```bash
git add webapp/data/logos.js
git commit -m "fix(ui): add 23 resolved team logos (promoted/relegated clubs + lower-tier gaps)"
```

---

### Task 3: Anchor "Projected Finish" plot to the baked proj_rank instead of the client's independent re-simulation

**Files:**
- Modify: `webapp/index.html:1102-1120` (`finishPlotPanel`)

- [ ] **Step 1: Sort and anchor the median by the server-baked `proj_pts`/`pts`, not the client's `fin_med`**

Current (`index.html:1102-1120`):
```js
function finishPlotPanel(){
  ensureFinish();
  const src=simVals||finishVals||{}, N=D.outlook.n_teams||D.standings.length;
  const teams=D.standings.map(s=>Object.assign({},s,src[s.team]||{}))
    .sort((a,b)=>(a.fin_med||99)-(b.fin_med||99));
  const pos=p=>((p-1)/(Math.max(1,N-1))*100);
  const rows=teams.map(t=>{
    const a=t.fin_p10||1,m=t.fin_med||1,b=t.fin_p90||N, c=finishZone(Math.round(m));
    const L=pos(a),W=Math.max(2,pos(b)-pos(a));
    return `<div class="frow"><span class="fn">${crest(t.team,t.logo)}<b>${t.team}</b></span>`+
      `<span class="ftrack"><span class="rangebar" style="left:${L.toFixed(1)}%;width:${W.toFixed(1)}%;background:${c}"></span>`+
      `<span class="fmed" style="left:calc(${pos(m).toFixed(1)}% - 1px);background:${c}"></span></span></div>`;
  }).join('');
  const panel=el('div','panel plotpanel');
  panel.innerHTML=`<div class="panel-h"><span class="dot" style="background:var(--europa);box-shadow:0 0 8px var(--europa)"></span>`+
    `<h2>Projected finish</h2><span class="meta">10th–90th pct · ● median</span></div>`+
    `<div class="plot"><div class="faxis">${axisTicks(N)}</div>${rows}${finishLegend()}</div>`;
  return panel;
}
```

Replace with (row order and the median tick now come from the same `(pts, gd, proj_pts)` ordering the standings table already uses; the client re-simulation still supplies the 10th–90th spread, since that's the only place a percentile band exists — but it draws around the trusted rank now, not its own independently-computed one):
```js
function finishPlotPanel(){
  ensureFinish();
  const src=simVals||finishVals||{}, N=D.outlook.n_teams||D.standings.length;
  // Row order matches the main standings table (pts → gd → proj_pts) so a team can
  // never show one rank in the League Table and a materially different rank here —
  // the client's own runSimTable() re-simulation (fin_med) is a DIFFERENT, independently
  // -noisy engine from the server-baked proj_pts and is not reliable as a sort key on its
  // own (verified: EPL/Tottenham preseason diverges by ~5 ranks between the two engines).
  const ranked=[...D.standings].sort((a,b)=>(b.pts-a.pts)||(b.gd-a.gd)||(b.proj_pts-a.proj_pts));
  const rankOf=new Map(ranked.map((s,i)=>[s.team,i+1]));
  const teams=ranked.map(s=>Object.assign({},s,src[s.team]||{},{fin_med:rankOf.get(s.team)}));
  const pos=p=>((p-1)/(Math.max(1,N-1))*100);
  const rows=teams.map(t=>{
    const m=t.fin_med, a=Math.min(t.fin_p10||m,m),b=Math.max(t.fin_p90||m,m), c=finishZone(Math.round(m));
    const L=pos(a),W=Math.max(2,pos(b)-pos(a));
    return `<div class="frow"><span class="fn">${crest(t.team,t.logo)}<b>${t.team}</b></span>`+
      `<span class="ftrack"><span class="rangebar" style="left:${L.toFixed(1)}%;width:${W.toFixed(1)}%;background:${c}"></span>`+
      `<span class="fmed" style="left:calc(${pos(m).toFixed(1)}% - 1px);background:${c}"></span></span></div>`;
  }).join('');
  const panel=el('div','panel plotpanel');
  panel.innerHTML=`<div class="panel-h"><span class="dot" style="background:var(--europa);box-shadow:0 0 8px var(--europa)"></span>`+
    `<h2>Projected finish</h2><span class="meta">10th–90th pct (model spread) · ● projected rank</span></div>`+
    `<div class="plot"><div class="faxis">${axisTicks(N)}</div>${rows}${finishLegend()}</div>`;
  return panel;
}
```

Note: `Math.min(t.fin_p10||m,m)` / `Math.max(t.fin_p90||m,m)` guards against the spread (still computed by the independent client re-simulation) landing on the wrong side of the now-authoritative median — clamps the bar to always contain its own median tick.

- [ ] **Step 2: Manual verification (no existing automated test covers this plot; add a smoke assertion)**

Append to `tests/test_browser_smoke.py`:
```python
class TestProjectedFinishConsistency:
    """The Projected Finish plot's team order must match the League Table's order —
    same team must not appear at a materially different rank in the two views."""

    def test_epl_finish_plot_matches_standings_order(self, page: Page, webapp_url: str):
        _load_route(page, webapp_url, "epl")
        standings_order = page.locator(".tlad .trow .tname").all_inner_texts()
        finish_order = page.locator(".plotpanel .frow b").all_inner_texts()
        assert standings_order == finish_order, (
            f"Standings order {standings_order} != Projected Finish order {finish_order}"
        )
```

- [ ] **Step 3: Run and confirm**

Run: `venv/bin/python -m pytest tests/test_browser_smoke.py::TestProjectedFinishConsistency -v --browser chromium`
Expected before Step 1: FAIL (orders differ). After: PASS.

- [ ] **Step 4: Commit**

```bash
git add webapp/index.html tests/test_browser_smoke.py
git commit -m "fix(ui): anchor Projected Finish plot to the server-baked rank, not the client's independent re-simulation"
```

---

## Workstream 2 — Rebrand: Entenser

### Task 4: Process the logo assets to transparent PNGs

**Files:**
- Create: `webapp/assets/branding/entenser-wordmark.png`
- Create: `webapp/assets/branding/entenser-icon.png`
- Create: `webapp/assets/branding/favicon.png`

- [ ] **Step 1: Matte the white background to transparency**

`docs/logo1.PNG` (wordmark) and `docs/logo2.PNG` (icon) are flat RGB, opaque near-white background, no alpha. Run:

```bash
python3 -c "
from PIL import Image
import numpy as np

def mattea(src, dst, resize=None):
    im = Image.open(src).convert('RGBA')
    arr = np.array(im)
    # near-white (>=245 on all channels) -> transparent; flat navy/white art, no gradients,
    # so a hard threshold is safe (verified: both source images are pure navy-on-white).
    white_mask = (arr[:,:,0]>=245)&(arr[:,:,1]>=245)&(arr[:,:,2]>=245)
    arr[white_mask,3]=0
    out = Image.fromarray(arr)
    if resize: out = out.resize(resize, Image.LANCZOS)
    out.save(dst)

mattea('docs/logo1.PNG','webapp/assets/branding/entenser-wordmark.png')
mattea('docs/logo2.PNG','webapp/assets/branding/entenser-icon.png')
mattea('docs/logo2.PNG','webapp/assets/branding/favicon.png', resize=(64,64))
"
```

- [ ] **Step 2: Verify transparency and dimensions**

```bash
python3 -c "
from PIL import Image
for f in ['webapp/assets/branding/entenser-wordmark.png','webapp/assets/branding/entenser-icon.png','webapp/assets/branding/favicon.png']:
    im = Image.open(f)
    alpha = im.split()[-1]
    print(f, im.size, im.mode, 'alpha min/max:', alpha.getextrema())
"
```
Expected: `mode RGBA` for all three, alpha extrema `(0, 255)` (both fully-transparent and fully-opaque pixels present — confirms the matte worked, not a no-op).

- [ ] **Step 3: Commit**

```bash
git add webapp/assets/branding/
git commit -m "feat(brand): add transparency-matted Entenser wordmark/icon/favicon assets"
```

---

### Task 5: Wire up the Entenser brand across title, header, sidebar, and favicon

**Files:**
- Modify: `webapp/index.html:6` (`<title>`)
- Modify: `webapp/index.html:527` (sidebar brand)
- Modify: `webapp/index.html:685-686` (per-league header title/JS)
- Modify: `webapp/index.html:2026` (edge-board page title)

- [ ] **Step 1: Add a favicon link and set the static title**

Current (`index.html:5-6`):
```html
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover" />
<title>MLS Projections</title>
```
Replace with:
```html
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover" />
<link rel="icon" type="image/png" href="assets/branding/favicon.png" />
<title>Entenser</title>
```

- [ ] **Step 2: Replace the sidebar brand block with the wordmark**

Current (`index.html:527`):
```html
  <div class="sb-brand"><div class="beacon"></div><div><b>Pitchside</b><span>Soccer Projections</span></div></div>
```
Replace with:
```html
  <div class="sb-brand"><img src="assets/branding/entenser-icon.png" alt="" style="width:24px;height:24px;object-fit:contain" /><div><b>Entenser</b><span>Soccer Projections</span></div></div>
```

- [ ] **Step 3: Keep the per-league dynamic title (league name) but stop it from ever showing "MLS Projections" as a static fallback**

Current (`index.html:685-686`, inside the league-header IIFE):
```js
  document.title=lg.name;
  $('#leagueTitle').textContent=lg.name;
```
No change needed here — `document.title` is already set to the league's own name at runtime (e.g. "Major League Soccer"), so the static `<title>Entenser</title>` from Step 1 is only what a user sees for the instant before this JS runs, or on routes that never reach this branch (`renderSoonView`, edge board). That's already correct. Leave as-is.

- [ ] **Step 4: Update the edge-board ("Matches") page title fallback** — done together with Task 15 (Workstream 7), since it touches the same line.

- [ ] **Step 5: Manual verification**

Start the preview server, load `/index.html?league=mls`, and confirm:
- Browser tab title reads the league name (unaffected)
- Sidebar shows the Entenser moose icon + "Entenser" wordmark text, readable against the dark sidebar background
- Favicon loads (check Network tab for `favicon.png` 200, not 404)

- [ ] **Step 6: Commit**

```bash
git add webapp/index.html
git commit -m "feat(brand): wire up Entenser wordmark, icon, and favicon"
```

---

## Workstream 3 — MLS top boxes: add the missing MLS Cup card

### Task 6: Add a 5th "MLS Cup" favorite card

**Files:**
- Modify: `webapp/index.html:130` (`.favs` grid CSS)
- Modify: `webapp/index.html:475` (860px breakpoint)
- Modify: `webapp/index.html:925-937` (`favCard`/`renderFavs`)
- Test: `tests/test_browser_smoke.py` (new test)

- [ ] **Step 1: Update the CSS grid to 5 columns**

Current (`index.html:130`):
```css
.favs{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:var(--s5)}
```
Replace with:
```css
.favs{display:grid;grid-template-columns:repeat(5,1fr);gap:10px;margin-bottom:var(--s5)}
```

Current (`index.html:475`, inside `@media(max-width:860px)`):
```css
  .favs{grid-template-columns:1fr 1fr}
```
Leave unchanged — 5 cards in a 2-column grid wraps to 3 rows (2+2+1), which is the existing wrap behavior for any non-multiple-of-2 card count and needs no special-casing.

- [ ] **Step 2: Add the `.fav.cup` accent (reuse the existing europa/blue token — same hue already used for cup's heat-cell color at `RGB.cup=[74,163,255]`)**

Current (`index.html:143-146`):
```css
.fav.shield::before{background:var(--shield)} .fav.shield .pct{color:var(--shield)} .fav.shield .sq{background:var(--shield)}
.fav.east::before{background:var(--qualify)} .fav.east .pct{color:var(--qualify)} .fav.east .sq{background:var(--qualify)}
.fav.west::before{background:var(--win)} .fav.west .pct{color:var(--win)} .fav.west .sq{background:var(--win)}
.fav.spoon::before{background:var(--spoon)} .fav.spoon .pct{color:var(--spoon)} .fav.spoon .sq{background:var(--spoon)}
```
Add a new line immediately after:
```css
.fav.cup::before{background:var(--europa)} .fav.cup .pct{color:var(--europa)} .fav.cup .sq{background:var(--europa)}
```

- [ ] **Step 3: Add the Cup card to `renderFavs()` and drop the now-redundant inline "cup" sub-stat**

Current (`index.html:924-937`):
```js
/* favorites — four title races: Shield · Eastern Conf · Western Conf · Spoon */
const favCard=(cls,lab,t,k)=>`<div class="fav ${cls}"><div class="lab"><span class="sq"></span>${lab}</div>
  <div class="teamrow">${crest(t.team,t.logo)}<div class="ftxt"><div class="team">${t.team}</div></div></div>
  <div class="favstats"><span class="pct">${fmt(t[k])}</span><span class="pp">proj <b>${t.proj_pts}</b> pts · cup <b>${t.cup}%</b></span></div></div>`;
function renderFavs(){
  const all=D.standings.map(vals);
  const sBy=k=>[...all].sort((a,b)=>b[k]-a[k])[0];
  const sByConf=c=>all.filter(s=>s.conf===c).sort((a,b)=>b.conf_win-a.conf_win)[0];
  $('#favs').innerHTML=
    favCard('shield',"Supporters' Shield",sBy('shield'),'shield')+
    favCard('east','Eastern Conference',sByConf('East'),'conf_win')+
    favCard('west','Western Conference',sByConf('West'),'conf_win')+
    favCard('spoon','Wooden Spoon',sBy('spoon'),'spoon');
}
```
Replace with (drop the `· cup X%` sub-stat since Cup is now its own card — keeps the footer stat line meaningful rather than duplicating what's now shown as a full card):
```js
/* favorites — five title races: MLS Cup · Shield · Eastern Conf · Western Conf · Spoon */
const favCard=(cls,lab,t,k)=>`<div class="fav ${cls}"><div class="lab"><span class="sq"></span>${lab}</div>
  <div class="teamrow">${crest(t.team,t.logo)}<div class="ftxt"><div class="team">${t.team}</div></div></div>
  <div class="favstats"><span class="pct">${fmt(t[k])}</span><span class="pp">proj <b>${t.proj_pts}</b> pts</span></div></div>`;
function renderFavs(){
  const all=D.standings.map(vals);
  const sBy=k=>[...all].sort((a,b)=>b[k]-a[k])[0];
  const sByConf=c=>all.filter(s=>s.conf===c).sort((a,b)=>b.conf_win-a.conf_win)[0];
  $('#favs').innerHTML=
    favCard('cup','MLS Cup',sBy('cup'),'cup')+
    favCard('shield',"Supporters' Shield",sBy('shield'),'shield')+
    favCard('east','Eastern Conference',sByConf('East'),'conf_win')+
    favCard('west','Western Conference',sByConf('West'),'conf_win')+
    favCard('spoon','Wooden Spoon',sBy('spoon'),'spoon');
}
```

- [ ] **Step 4: Add a Playwright regression test**

Append to `tests/test_browser_smoke.py`:
```python
class TestMlsTopBoxes:
    """MLS must show all 5 title-race boxes: Cup, Shield, East, West, Spoon."""

    def test_mls_shows_five_fav_cards(self, page: Page, webapp_url: str):
        _load_route(page, webapp_url, "mls")
        cards = page.locator(".fav")
        assert cards.count() == 5, f"Expected 5 .fav cards, got {cards.count()}"
        labels = page.locator(".fav .lab").all_inner_texts()
        assert any("MLS Cup" in l for l in labels), f"No MLS Cup card in {labels}"
```

- [ ] **Step 5: Run to verify fail then pass**

Run: `venv/bin/python -m pytest tests/test_browser_smoke.py::TestMlsTopBoxes -v --browser chromium`
Expected before Steps 1-3: FAIL (`cards.count() == 4`). After: PASS.

- [ ] **Step 6: Commit**

```bash
git add webapp/index.html tests/test_browser_smoke.py
git commit -m "feat(ui): add MLS Cup as its own top-box card (5th race, alongside Shield/East/West/Spoon)"
```

---

## Workstream 4 — Squad value: prominence + 4-way (Attack/Mid/Defense/GK) breakdown

### Task 7: Extend `_aggregate_team()` to emit Midfield + GK percentages

**Files:**
- Modify: `scripts/import_transfermarkt.py:401-474`
- Test: `tests/test_transfermarkt_mapping.py` (new tests)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_transfermarkt_mapping.py`:
```python
import pandas as pd
from scripts.import_transfermarkt import _aggregate_team


def _players(rows):
    """rows: list of (name, position, value_eur, age)."""
    return pd.DataFrame(rows, columns=["player_name", "position", "market_value_eur", "age"])


def test_aggregate_team_emits_four_way_split():
    players = _players([
        ("GK1", "Goalkeeper", 10_000_000, 25),
        ("DEF1", "Centre-Back", 20_000_000, 24),
        ("MID1", "Central Midfield", 30_000_000, 26),
        ("ATT1", "Striker", 40_000_000, 22),
    ])
    feats = _aggregate_team(players)
    assert feats["att_value_pct"] == pytest.approx(0.4)
    assert feats["def_value_pct"] == pytest.approx(0.2)
    assert feats["mid_value_pct"] == pytest.approx(0.3)
    assert feats["gk_value_pct"] == pytest.approx(0.1)
    assert feats["n_mid"] == 1
    # the four percentages must sum to 1.0 (no player's value silently dropped)
    total_pct = feats["att_value_pct"] + feats["def_value_pct"] + feats["mid_value_pct"] + feats["gk_value_pct"]
    assert total_pct == pytest.approx(1.0)


def test_aggregate_team_zero_value_branch_still_has_four_way_keys():
    players = _players([("P1", "Central Midfield", 0, 24)])
    feats = _aggregate_team(players, keep_if_zero_value=True)
    assert feats["n_mid"] == 1
    import math
    assert math.isnan(feats["mid_value_pct"])
    assert math.isnan(feats["gk_value_pct"])
```

Add `import pytest` near the top of `tests/test_transfermarkt_mapping.py` if not already imported (it is — confirmed at line 12 of the existing file).

- [ ] **Step 2: Run to verify it fails**

Run: `venv/bin/python -m pytest tests/test_transfermarkt_mapping.py::test_aggregate_team_emits_four_way_split -v`
Expected: FAIL with `KeyError: 'mid_value_pct'`.

- [ ] **Step 3: Implement — add MID/GK percentages to both branches of `_aggregate_team()`**

Current (`scripts/import_transfermarkt.py:422-436`, the zero-value branch):
```python
    if total_val <= 0:
        avg_age = float(np.nanmean(ages)) if np.isfinite(ages).any() else np.nan
        return {
            "squad_value_eur":  0.0,
            "att_value_pct":    np.nan,
            "def_value_pct":    np.nan,
            "tilt":             np.nan,
            "value_wtd_age":    np.nan,
            "avg_age":          avg_age,
            "dp_value_share":   np.nan,
            "n_players":        len(players),
            "n_att":            int((pos_groups == "ATT").sum()),
            "n_def":            int((pos_groups == "DEF").sum()),
            "n_gk":             int((pos_groups == "GK").sum()),
        }
```
Replace with:
```python
    if total_val <= 0:
        avg_age = float(np.nanmean(ages)) if np.isfinite(ages).any() else np.nan
        return {
            "squad_value_eur":  0.0,
            "att_value_pct":    np.nan,
            "mid_value_pct":    np.nan,
            "def_value_pct":    np.nan,
            "gk_value_pct":     np.nan,
            "tilt":             np.nan,
            "value_wtd_age":    np.nan,
            "avg_age":          avg_age,
            "dp_value_share":   np.nan,
            "n_players":        len(players),
            "n_att":            int((pos_groups == "ATT").sum()),
            "n_mid":            int((pos_groups == "MID").sum()),
            "n_def":            int((pos_groups == "DEF").sum()),
            "n_gk":             int((pos_groups == "GK").sum()),
        }
```

Current (`scripts/import_transfermarkt.py:438-474`, the normal branch):
```python
    # Position-group value sums
    att_val = float(vals[pos_groups == "ATT"].sum())
    def_val = float(vals[pos_groups == "DEF"].sum())
    gk_val  = float(vals[pos_groups == "GK"].sum())

    att_pct = att_val / total_val
    def_pct = def_val / total_val
    tilt    = att_pct - def_pct  # positive = more value in attack
```
Replace with:
```python
    # Position-group value sums
    att_val = float(vals[pos_groups == "ATT"].sum())
    mid_val = float(vals[pos_groups == "MID"].sum())
    def_val = float(vals[pos_groups == "DEF"].sum())
    gk_val  = float(vals[pos_groups == "GK"].sum())

    att_pct = att_val / total_val
    mid_pct = mid_val / total_val
    def_pct = def_val / total_val
    gk_pct  = gk_val / total_val
    tilt    = att_pct - def_pct  # positive = more value in attack (unchanged definition)
```

And immediately below, current return block:
```python
    return {
        "squad_value_eur":  total_val,
        "att_value_pct":    att_pct,
        "def_value_pct":    def_pct,
        "tilt":             tilt,
        "value_wtd_age":    val_wtd_age,
        "avg_age":          avg_age,
        "dp_value_share":   dp_value_share,
        "n_players":        len(players),
        "n_att":            int((pos_groups == "ATT").sum()),
        "n_def":            int((pos_groups == "DEF").sum()),
        "n_gk":             int((pos_groups == "GK").sum()),
    }
```
Replace with:
```python
    return {
        "squad_value_eur":  total_val,
        "att_value_pct":    att_pct,
        "mid_value_pct":    mid_pct,
        "def_value_pct":    def_pct,
        "gk_value_pct":     gk_pct,
        "tilt":             tilt,
        "value_wtd_age":    val_wtd_age,
        "avg_age":          avg_age,
        "dp_value_share":   dp_value_share,
        "n_players":        len(players),
        "n_att":            int((pos_groups == "ATT").sum()),
        "n_mid":            int((pos_groups == "MID").sum()),
        "n_def":            int((pos_groups == "DEF").sum()),
        "n_gk":             int((pos_groups == "GK").sum()),
    }
```

- [ ] **Step 4: Run to verify it passes**

Run: `venv/bin/python -m pytest tests/test_transfermarkt_mapping.py -v`
Expected: all PASS, including the two new tests.

- [ ] **Step 5: Commit**

```bash
git add scripts/import_transfermarkt.py tests/test_transfermarkt_mapping.py
git commit -m "feat(data): emit midfield + GK value percentages from squad-value aggregation"
```

---

### Task 8: Regenerate mapped CSVs for every cached league (offline, no scraping)

**Files:** none modified — this step only regenerates `data/transfermarkt_squad_values_*_mapped.csv` files (already gitignored/data files, not source).

- [ ] **Step 1: Re-run MLS (no `--league` flag = MLS)**

Run: `venv/bin/python scripts/import_transfermarkt.py --season 2026 --skip-fetch`
Expected: `data/transfermarkt_squad_values_2026_mapped.csv` rewritten; console prints a validation report ending in "PASS" (matches the existing `run_one_league` behavior — `--skip-fetch` only skips the `Rscript` network fetch, reusing the already-cached raw CSV).

- [ ] **Step 2: Re-run every other league in one pass**

Run: `venv/bin/python scripts/import_transfermarkt.py --all-leagues --season 2026 --skip-fetch`
Expected: console prints one `PASS`/`FAIL` line per of the 19 `TM_LEAGUE_CODES` (GB1, GB2, GB3, GB4, ES1, ES2, IT1, IT2, L1, L2, FR1, FR2, MEX1, NL1, PO1, TR1, SC1, BE1, GR1), ending with `N/19 leagues passed validation.` Most should PASS (CDN1/Canadian PL is excluded — not in scope). Investigate and report any unexpected FAIL before continuing (a FAIL here means that league's mapped CSV did not regenerate — Task 9 must skip that league to avoid stale data).

- [ ] **Step 3: Spot-check the new columns landed**

Run:
```bash
python3 -c "
import pandas as pd
for f in ['data/transfermarkt_squad_values_2026_mapped.csv','data/transfermarkt_squad_values_GB1_2026_mapped.csv','data/transfermarkt_squad_values_NL1_2026_mapped.csv']:
    df = pd.read_csv(f)
    assert 'mid_value_pct' in df.columns and 'gk_value_pct' in df.columns, f'{f} missing new columns'
    row = df.iloc[0]
    s = row['att_value_pct']+row['mid_value_pct']+row['def_value_pct']+row['gk_value_pct']
    print(f, 'first row 4-way sum:', round(s,3))
"
```
Expected: `mid_value_pct`/`gk_value_pct` present in all three files, sums close to 1.0 (allowing for float rounding).

*(No commit — these are local data artifacts, not committed to git; verify `git status` shows no changes from this task before moving on.)*

---

### Task 9: Pass the two new fields through the league-data builders

**Files:**
- Modify: `scripts/build_dashboard_data.py:131-132`
- Modify: `scripts/build_league_data.py:151-152`

- [ ] **Step 1: MLS builder — add the passthrough**

Current (`scripts/build_dashboard_data.py:131-132`, inside `build_squad_value_mls`'s `out[name] = {...}` dict):
```python
                "att_value_pct": _clean(row.get("att_value_pct")),
                "def_value_pct": _clean(row.get("def_value_pct")),
```
Replace with:
```python
                "att_value_pct": _clean(row.get("att_value_pct")),
                "mid_value_pct": _clean(row.get("mid_value_pct")),
                "def_value_pct": _clean(row.get("def_value_pct")),
                "gk_value_pct":  _clean(row.get("gk_value_pct")),
```

- [ ] **Step 2: Non-MLS builder — add the same passthrough**

Current (`scripts/build_league_data.py:151-152`, inside `build_squad_value_league`'s `out[name] = {...}` dict):
```python
                "att_value_pct": _clean(row.get("att_value_pct")),
                "def_value_pct": _clean(row.get("def_value_pct")),
```
Replace with:
```python
                "att_value_pct": _clean(row.get("att_value_pct")),
                "mid_value_pct": _clean(row.get("mid_value_pct")),
                "def_value_pct": _clean(row.get("def_value_pct")),
                "gk_value_pct":  _clean(row.get("gk_value_pct")),
```

- [ ] **Step 3: Commit**

```bash
git add scripts/build_dashboard_data.py scripts/build_league_data.py
git commit -m "feat(data): pass midfield + GK squad-value percentages through to league payloads"
```

---

### Task 10: Patch `squad_value` into the already-built webapp data files (no full model rebuild)

**Files:**
- Create: `scripts/patch_squad_value.py` (small, standalone, run-once utility — not part of the regular build pipeline)

- [ ] **Step 1: Write the patch script**

```python
#!/usr/bin/env python3
"""One-off: refresh only the `squad_value` key of already-built webapp/data/*.js
payloads from freshly-regenerated transfermarkt CSVs (Task 7-8), without re-running
the full model pipeline (ELO/DC/XGB/sims — ~18 min per league per project memory).

Usage: venv/bin/python scripts/patch_squad_value.py
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.build_league_data import build_squad_value_league
from scripts.build_dashboard_data import build_squad_value_mls
from scripts.payload_utils import write_js_payload
from scripts.import_transfermarkt import TM_CODE_TO_LEAGUE_ID

WEBAPP_DATA = Path(__file__).parent.parent / "webapp" / "data"


def _load(lid: str) -> dict:
    path = WEBAPP_DATA / f"{lid}.js"
    text = re.sub(r"^[\s\S]*?=\s*", "", path.read_text(encoding="utf-8")).rstrip().rstrip(";")
    return json.loads(text)


def patch_non_mls(lid: str) -> bool:
    data = _load(lid)
    team_names = {s["team"] for s in data.get("standings", [])}
    if not team_names:
        print(f"[{lid}] no standings/team names found, skipping")
        return False
    sv = build_squad_value_league(lid, team_names)
    if sv is None:
        print(f"[{lid}] no squad-value data available, leaving unchanged")
        return False
    data["squad_value"] = sv
    write_js_payload(WEBAPP_DATA / f"{lid}.js", "LEAGUE_DATA", data)
    print(f"[{lid}] patched squad_value for {len(sv)} teams")
    return True


def patch_mls() -> bool:
    from data_pipeline.asa_cache import get_teams
    data = _load("mls")
    team_names = {s["team"] for s in data.get("standings", [])}
    teams = get_teams("mls")
    id2name = {r.team_id: r.team_name for r in teams.itertuples()}
    abbr2id = {r.team_abbreviation: r.team_id for r in teams.itertuples()}
    tids = [tid for tid, name in id2name.items() if name in team_names]
    sv = build_squad_value_mls(tids, id2name, abbr2id, 2026)
    if sv is None:
        print("[mls] no squad-value data available, leaving unchanged")
        return False
    data["squad_value"] = sv
    write_js_payload(WEBAPP_DATA / "mls.js", "LEAGUE_DATA", data)
    print(f"[mls] patched squad_value for {len(sv)} teams")
    return True


def main():
    patch_mls()
    for lid in sorted(set(TM_CODE_TO_LEAGUE_ID.values()) - {"canadian-pl"}):
        if (WEBAPP_DATA / f"{lid}.js").exists():
            patch_non_mls(lid)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run it**

Run: `venv/bin/python scripts/patch_squad_value.py`
Expected: one `[<lid>] patched squad_value for N teams` line per league (14 non-MLS leagues + MLS — `canadian-pl` has no live `webapp/data/canadian-pl.js` outlook to patch and is excluded). Leagues with no `webapp/data/<lid>.js` file yet (shouldn't happen for any live league) print "no squad-value data available" and are skipped harmlessly.

- [ ] **Step 3: Verify one file's payload actually changed and 4-way percentages sum to ~1**

Run:
```bash
python3 -c "
import json
txt = open('webapp/data/epl.js').read().split('=',1)[1].rstrip(';\n')
d = json.loads(txt)
team, sv = next(iter(d['squad_value'].items()))
print(team, sv['att_value_pct'], sv['mid_value_pct'], sv['def_value_pct'], sv['gk_value_pct'])
s = sv['att_value_pct']+sv['mid_value_pct']+sv['def_value_pct']+sv['gk_value_pct']
print('sum:', round(s,3))
"
```
Expected: all four keys present with non-null floats, sum ≈ 1.0.

- [ ] **Step 4: Commit**

```bash
git add scripts/patch_squad_value.py webapp/data/*.js
git commit -m "feat(data): roll out 4-way squad-value breakdown to all 15 leagues with cached transfermarkt data"
```

---

### Task 11: Un-collapse the squad-value panel and render the 4-way breakdown

**Files:**
- Modify: `webapp/index.html:1740-1747` (`squadValuePanel`)
- Test: `tests/test_browser_smoke.py` (new test)

- [ ] **Step 1: Default the panel open and show 4 position groups**

Current (`index.html:1740-1747`):
```js
  return `<div class="pcard sv-panel" style="grid-column:1/-1">
    <h3 onclick="this.closest('.sv-panel').classList.toggle('open')">Squad value (Transfermarkt)${lowConf} <span class="fi-chev">▾</span></h3>
    <div class="sv-body">
    <div class="pstat"><span class="k">Total squad value</span><span class="v">€${(sv.squad_value_eur/1e6).toFixed(1)}m${asOf}</span></div>
    <div class="pstat"><span class="k">League rank</span><span class="v">#${sv.league_rank} of ${sv.n_teams} · ${sv.percentile.toFixed(0)}th percentile</span></div>
    <div class="pc-track" style="margin:6px 0 10px"><span style="width:${sv.percentile}%"></span></div>
    <div class="pstat"><span class="k">Value-wtd age</span><span class="v">${sv.value_wtd_age??'—'}<span style="color:var(--txt-3);font-weight:400"> (league avg ${sv.league_avg_value_wtd_age??'—'})</span></span></div>
    <div class="pstat"><span class="k">ATT / DEF value split</span><span class="v">${sv.att_value_pct==null?'—':(sv.att_value_pct*100).toFixed(1)+'%'} / ${sv.def_value_pct==null?'—':(sv.def_value_pct*100).toFixed(1)+'%'}</span></div>
    <div class="pstat"><span class="k">Squad size</span><span class="v">${sv.n_players??'—'}</span></div>
    ${playersHtml}
    <div style="margin-top:8px;font-size:10px;color:var(--txt-3)">Values: <a href="https://www.transfermarkt.com" target="_blank" rel="noopener" style="color:var(--txt-3)">Transfermarkt.com</a></div>
    </div></div>`;
```
Replace with (panel starts `open`; the header is still clickable to collapse it for anyone who wants to; ATT/DEF single line becomes 4 separate stat rows, each falling back to "—" independently since `gk_value_pct` may be null for older cached CSVs that haven't been through Task 8-10 yet):
```js
  const posRow=(label,pct)=>`<div class="pstat"><span class="k">${label} value</span><span class="v">${pct==null?'—':(pct*100).toFixed(1)+'%'}</span></div>`;
  return `<div class="pcard sv-panel open" style="grid-column:1/-1">
    <h3 onclick="this.closest('.sv-panel').classList.toggle('open')">Squad value (Transfermarkt)${lowConf} <span class="fi-chev">▾</span></h3>
    <div class="sv-body">
    <div class="pstat"><span class="k">Total squad value</span><span class="v">€${(sv.squad_value_eur/1e6).toFixed(1)}m${asOf}</span></div>
    <div class="pstat"><span class="k">League rank</span><span class="v">#${sv.league_rank} of ${sv.n_teams} · ${sv.percentile.toFixed(0)}th percentile</span></div>
    <div class="pc-track" style="margin:6px 0 10px"><span style="width:${sv.percentile}%"></span></div>
    <div class="pstat"><span class="k">Value-wtd age</span><span class="v">${sv.value_wtd_age??'—'}<span style="color:var(--txt-3);font-weight:400"> (league avg ${sv.league_avg_value_wtd_age??'—'})</span></span></div>
    ${posRow('Attack',sv.att_value_pct)}
    ${posRow('Midfield',sv.mid_value_pct)}
    ${posRow('Defense',sv.def_value_pct)}
    ${posRow('Goalkeeper',sv.gk_value_pct)}
    <div class="pstat"><span class="k">Squad size</span><span class="v">${sv.n_players??'—'}</span></div>
    ${playersHtml}
    <div style="margin-top:8px;font-size:10px;color:var(--txt-3)">Values: <a href="https://www.transfermarkt.com" target="_blank" rel="noopener" style="color:var(--txt-3)">Transfermarkt.com</a></div>
    </div></div>`;
```

- [ ] **Step 2: Add a Playwright regression test**

Append to `tests/test_browser_smoke.py`:
```python
class TestSquadValuePanel:
    """Squad value must render expanded by default with a 4-way position breakdown."""

    def test_squad_value_panel_is_open_and_shows_four_positions(self, page: Page, webapp_url: str):
        _load_route(page, webapp_url, "epl")
        page.locator('[data-view="teams"]').click()
        page.wait_for_timeout(300)
        panel = page.locator(".sv-panel").first
        assert "open" in (panel.get_attribute("class") or ""), "Squad value panel is not open by default"
        text = panel.inner_text()
        for label in ["Attack value", "Midfield value", "Defense value", "Goalkeeper value"]:
            assert label in text, f"Missing '{label}' row in squad value panel"
```

- [ ] **Step 3: Run to verify fail then pass**

Run: `venv/bin/python -m pytest tests/test_browser_smoke.py::TestSquadValuePanel -v --browser chromium`
Expected before Step 1: FAIL (panel lacks `open` class, only "ATT / DEF value split" text exists). After Step 1 + Task 10's data patch: PASS.

- [ ] **Step 4: Commit**

```bash
git add webapp/index.html tests/test_browser_smoke.py
git commit -m "feat(ui): squad value panel opens by default, shows 4-way Attack/Mid/Defense/GK breakdown"
```

---

## Workstream 5 — Logo contrast fix

### Task 12: Add a light backing plate behind crest logos

**Files:**
- Modify: `webapp/index.html:123-127` (`.crest` CSS)

- [ ] **Step 1: Give the crest a light backing so dark-heavy logos (e.g. Tottenham navy) stay visible against the dark theme**

Current (`index.html:123-127`):
```css
.crest{width:26px;height:26px;border-radius:6px;flex:none;display:grid;place-items:center;position:relative;
  font-family:"Archivo";font-weight:700;font-size:9.5px;color:var(--txt-2);background:var(--ink-3);
  border:1px solid var(--line-2);overflow:hidden}
.crest img{position:absolute;inset:0;width:100%;height:100%;object-fit:contain;padding:2px;background:transparent}
.crest:has(img) .mono{display:none}   /* logo present → hide fallback initials */
```
Replace with (the `.crest` container already has a background — `var(--ink-3)`, a dark near-black tone — which is exactly why a navy-on-transparent crest disappears into it; swap to a fixed light backing plate specifically for the image layer, independent of the monogram-fallback background):
```css
.crest{width:26px;height:26px;border-radius:6px;flex:none;display:grid;place-items:center;position:relative;
  font-family:"Archivo";font-weight:700;font-size:9.5px;color:var(--txt-2);background:var(--ink-3);
  border:1px solid var(--line-2);overflow:hidden}
.crest img{position:absolute;inset:0;width:100%;height:100%;object-fit:contain;padding:2px;
  background:#eef1f4;border-radius:5px}   /* light plate so dark-heavy crests (navy, black) stay visible on the dark theme */
.crest:has(img) .mono{display:none}   /* logo present → hide fallback initials */
```

- [ ] **Step 2: Manual verification**

Start the preview server, load `/index.html?league=championship` (has Tottenham... actually Tottenham is EPL; use `/index.html?league=epl`), open the Teams tab, and use `preview_inspect` on a `.crest img` element to confirm `background-color` renders as `rgb(238, 241, 244)` and the crest is visually distinguishable from the dark page background. Take a screenshot for visual confirmation.

- [ ] **Step 3: Commit**

```bash
git add webapp/index.html
git commit -m "fix(ui): add light backing plate behind team crests for dark-on-dark logo visibility"
```

---

## Workstream 6 — Mobile layout

### Task 13: Bring back team names next to crests in league tables on mobile

**Files:**
- Modify: `webapp/index.html:188`

- [ ] **Step 1: Remove the name-hiding rule, keep the crest slightly larger for legibility**

Current (`index.html:187-188`):
```css
/* narrow screens: drop the team name/sub, show crest only */
@media(max-width:620px){.ladder .tcol{display:none} .ladder .tcell{justify-content:center}}
```
Replace with:
```css
/* narrow screens: keep the team name (crest-only was too hard to scan) — just
   tighten the subtitle line so the row still fits without truncating names. */
@media(max-width:620px){.ladder .tsub{display:none}}
```

(Dropping `.tsub` — the "GP · GD · xGD" subtitle — instead of the team name itself keeps the row height reasonable on narrow screens while addressing the actual complaint: names were unreadable at crest-only size. The crest itself is unchanged.)

- [ ] **Step 2: Manual verification**

Use `preview_resize` to set the mobile preset (375×812), load `/index.html?league=mls`, and use `preview_snapshot` to confirm team names are visible in the league table rows (not just crests).

- [ ] **Step 3: Commit**

```bash
git add webapp/index.html
git commit -m "fix(ui): show team names (not just crests) in mobile league tables"
```

---

### Task 14: Move "Next 5" beside the team row instead of stacking below on mobile

> **VERDICT (2026-07-09):** Shipped for the MLS conference ladder (`ladder()`/`.col-head,.row`) — team names legible again after a caught-and-fixed regression (commits `51a0679`, `237c21c`; a first attempt collapsed `.tname` to 9px/0 characters at 375px by not accounting for the crest+gap overhead in the Club column's `minmax()` floor, caught by spec review before merge).
>
> **Scope gap found, not fixed here:** this only covers the MLS-style renderer. The single-table (European) renderer, `tableLadder()` — used by ~19 of this dashboard's ~27 leagues with standings (EPL, Bundesliga, La Liga, Serie A, Ligue 1, Championship, League One/Two, 2. Bundesliga, Segunda, Serie B, Ligue 2, Liga MX, Eredivisie, Primeira, Süper Lig, Scottish Prem, Belgian Pro, Greek Super, NWSL, USL Championship) — has Next-5 completely clipped and unreachable on mobile (`--tgrid` is computed once in JS and isn't width-aware; `.ladder{overflow:hidden}` has no scroll fallback). This is a different code path (JS column-width generation, not a media-query tweak) and was correctly left out of this CSS-only task's scope. Flagged as a follow-up task chip during implementation — recorded here too so this batch doesn't read as "mobile Next-5: done" when it's done for one league out of ~20.

**Files:**
- Modify: `webapp/index.html:503-521` (mobile what-if CSS block)

- [ ] **Step 1: Replace the full-width stacked layout with an inline, horizontally-scrollable strip**

Current (`index.html:503-521`):
```css
/* Mobile what-if mode: the desktop Next-5 column is too narrow to tap, so on
   mobile the .wgroup reflows to a full-width sub-row under each team with large
   touch targets + opponent labels. Reuses the same forced/scheduleSim logic and
   #ladders click delegation — presentation only. */
@media(max-width:760px){
  .row .wgroup,.tlad-w .trow .wgroup{
    grid-column:1/-1;display:flex;flex-wrap:wrap;justify-content:flex-start;
    gap:6px;margin-top:7px;padding-top:7px;border-top:1px dashed var(--line-3)}
  .row .wgroup::before,.tlad-w .trow .wgroup::before{
    content:"Next 5 — tap to force W / D / L";flex-basis:100%;
    font-size:9px;text-transform:uppercase;letter-spacing:.04em;
    color:var(--txt-3);margin-bottom:1px}
  .row .wbox,.tlad-w .trow .wbox{
    width:auto;min-width:0;height:36px;flex:1 1 0;max-width:84px;
    display:flex;align-items:center;justify-content:center;border-radius:7px}
  .wb-l{display:flex;flex-direction:column;align-items:center;line-height:1.1;
    font-size:10.5px;font-weight:700;color:var(--txt-2);pointer-events:none}
  .wbox.w .wb-l,.wbox.d .wb-l,.wbox.l .wb-l{color:#06121d}
}
```
Replace with (Next 5 stays in its own grid column, same as desktop — no `grid-column:1/-1` takeover — but becomes a horizontally-scrollable strip with larger touch targets, since mobile screens are too narrow to fit 5×36px boxes inline without scrolling):
```css
/* Mobile what-if mode: keep Next-5 in its own column (matching desktop), but
   make the boxes bigger touch targets and let the strip scroll horizontally
   instead of taking over the full row width. */
@media(max-width:760px){
  .row .wgroup,.tlad-w .trow .wgroup{
    overflow-x:auto;flex-wrap:nowrap;gap:5px;-webkit-overflow-scrolling:touch;scrollbar-width:none;
    max-width:100%}
  .row .wgroup::-webkit-scrollbar,.tlad-w .trow .wgroup::-webkit-scrollbar{display:none}
  .row .wbox,.tlad-w .trow .wbox{
    width:28px;min-width:28px;height:28px;flex:none;
    display:flex;align-items:center;justify-content:center;border-radius:7px}
  .wb-l{display:flex;flex-direction:column;align-items:center;line-height:1.1;
    font-size:8px;font-weight:700;color:var(--txt-2);pointer-events:none}
  .wbox.w .wb-l,.wbox.d .wb-l,.wbox.l .wb-l{color:#06121d}
}
```

Note: this removes the `col-head .c-w5` / `row .eloc` hiding rule's interaction with `.wgroup` full-width takeover — verify the 760px column-count rule at `index.html:481-484` (`.col-head,.row{grid-template-columns:...}`, which already excludes ELO and Next-5 from the mobile column set) still applies cleanly; if Next-5 is being dropped from the grid entirely at 760px (check `.col-head .c-w5,.row .eloc{display:none}` at line 482), this task's CSS is dead until that exclusion is also revisited — confirm during manual verification (Step 2) whether Next-5 is visible at all at this breakpoint before assuming the fix is complete.

- [ ] **Step 2: Manual verification**

Use `preview_resize` (mobile preset), load `/index.html?league=mls`, and use `preview_snapshot` / `preview_screenshot` to confirm: (a) Next-5 boxes appear beside the team row, not stacked below with a dashed separator; (b) if Step 1's note above surfaces a conflict with the existing `display:none` column exclusion at line 482, resolve it by removing `.col-head .c-w5,.row .eloc{display:none}`'s effect on `.c-w5`/`.wgroup` specifically (keep ELO hidden, stop hiding Next-5) before re-verifying.

- [ ] **Step 3: Commit**

```bash
git add webapp/index.html
git commit -m "fix(ui): keep Next-5 beside the team row on mobile (scrollable) instead of stacking below"
```

---

## Workstream 7 — Navigation

### Task 15: Rename "Today's Edge" to "Matches"

**Files:**
- Modify: `webapp/index.html:622` (D stub name)
- Modify: `webapp/index.html:654` (sidebar link)
- Modify: `webapp/index.html:2026` (page title)

- [ ] **Step 1: Update all three user-facing label strings**

Current (`index.html:622`):
```js
     ? {league:{name:_isEdgeBoard?"Today's Edge":'Cross-League Power Rankings'},
```
Replace with:
```js
     ? {league:{name:_isEdgeBoard?"Matches":'Cross-League Power Rankings'},
```

Current (`index.html:654`):
```js
  html+=`<a class="sb-lg sb-power${_isEdgeBoard?' active':''}" href="${location.pathname}"><span class="lgc">⚡</span><span>Today's Edge</span></a>`;
```
Replace with:
```js
  html+=`<a class="sb-lg sb-power${_isEdgeBoard?' active':''}" href="${location.pathname}"><span class="lgc">⚡</span><span>Matches</span></a>`;
```

Current (`index.html:2026`):
```js
  const ttl=$('#leagueTitle'); if(ttl) ttl.textContent="Today's Edge";
```
Replace with:
```js
  const ttl=$('#leagueTitle'); if(ttl) ttl.textContent="Matches";
```

Internal identifiers (`_isEdgeBoard`, `EDGE_BOARD_DATA`, `data/edge-board.js`, `.eb-*` CSS classes, `ebRow()`) are left unchanged — only user-visible text changes, per the design doc's scope (avoid an unnecessary wide rename that doesn't touch anything the user sees).

- [ ] **Step 2: Commit**

```bash
git add webapp/index.html
git commit -m "feat(ui): rename 'Today's Edge' to 'Matches'"
```

---

### Task 16: Group the Matches view by date, then league

**Files:**
- Modify: `webapp/index.html:2029-2039` (edge-board body construction)
- Test: `tests/test_browser_smoke.py` (new test)

- [ ] **Step 1: Restructure the body from edge-tier grouping to date → league grouping**

Current (`index.html:2028-2039`):
```js
  const priced=EB.priced||[], noLine=EB.no_line||[], nextKo=EB.next_kickoffs||[];
  let body;
  if(!priced.length && !noLine.length){
    body=`<div class="eb-empty">No qualifying edges today.<br>${nextKo.length
      ? 'Next kickoffs: '+nextKo.map(k=>`${k.league_name}: ${k.home} v ${k.away} (${k.date})`).join(' · ')
      : 'No upcoming matches in the next '+(EB.window_days*24)+'h across live leagues.'}</div>`;
  } else {
    const withEdge=priced.filter(r=>r.bet), noEdge=priced.filter(r=>!r.bet);
    body=(withEdge.length?`<div class="eb-panel"><div class="eb-h">≥${EB.edge_threshold_pct}% edge — quarter-Kelly sizing</div>${withEdge.map(ebRow).join('')}</div>`:'')
       +(noEdge.length?`<div class="eb-panel"><div class="eb-h">Priced, below threshold</div>${noEdge.map(ebRow).join('')}</div>`:'')
       +(noLine.length?`<div class="eb-panel"><div class="eb-h">No line yet</div>${noLine.map(ebRow).join('')}</div>`:'');
  }
```
Replace with (every match — priced or not — carries `.date` and `.league_name`; group by date first, preserving the existing chronological order already present in `EB.priced`/`EB.no_line`, then by league within each date; the ≥threshold edge badge still renders per-row via the existing `ebRow()`, it's just no longer the top-level grouping):
```js
  const allMatches=[...(EB.priced||[]), ...(EB.no_line||[])], nextKo=EB.next_kickoffs||[];
  let body;
  if(!allMatches.length){
    body=`<div class="eb-empty">No qualifying edges today.<br>${nextKo.length
      ? 'Next kickoffs: '+nextKo.map(k=>`${k.league_name}: ${k.home} v ${k.away} (${k.date})`).join(' · ')
      : 'No upcoming matches in the next '+(EB.window_days*24)+'h across live leagues.'}</div>`;
  } else {
    // Group by date (already chronological), then by league within each date.
    const byDate={};
    allMatches.forEach(r=>{(byDate[r.date]=byDate[r.date]||[]).push(r);});
    const fmtDay=d=>new Date(d+'T12:00').toLocaleDateString('en-US',{weekday:'long',month:'short',day:'numeric'});
    body=Object.keys(byDate).sort().map(date=>{
      const byLeague={};
      byDate[date].forEach(r=>{(byLeague[r.league_name]=byLeague[r.league_name]||[]).push(r);});
      const leaguePanels=Object.keys(byLeague).sort().map(lg=>
        `<div class="eb-panel"><div class="eb-h">${lg}</div>${byLeague[lg].map(ebRow).join('')}</div>`
      ).join('');
      return `<div class="daygrp"><div class="dayhead">${fmtDay(date)}</div>${leaguePanels}</div>`;
    }).join('');
  }
```

- [ ] **Step 2: Add a Playwright regression test**

Append to `tests/test_browser_smoke.py`:
```python
class TestMatchesGroupedByDateAndLeague:
    """The Matches (formerly Today's Edge) view groups fixtures by date, then league."""

    def test_matches_view_has_day_groups(self, page: Page, webapp_url: str):
        page.goto(f"{webapp_url}/index.html", wait_until="networkidle")
        page.wait_for_timeout(400)
        title = page.locator("#leagueTitle").inner_text()
        assert title == "Matches", f"Expected page title 'Matches', got {title!r}"
        # daygrp is only rendered when there are upcoming matches — skip gracefully
        # in a quiet data window rather than asserting on scraped external state.
        if page.locator(".eb-empty").count() > 0:
            pytest.skip("no upcoming matches in the current data window")
        assert page.locator(".daygrp").count() > 0, "Expected at least one .daygrp day-group"
```

- [ ] **Step 3: Run to verify pass**

Run: `venv/bin/python -m pytest tests/test_browser_smoke.py::TestMatchesGroupedByDateAndLeague -v --browser chromium`
Expected: PASS (or skip, if the current data window genuinely has no upcoming matches — check `webapp/data/edge-board.js` manually in that case to confirm the skip is legitimate, not masking a bug).

- [ ] **Step 4: Commit**

```bash
git add webapp/index.html tests/test_browser_smoke.py
git commit -m "feat(ui): group Matches view by date then league instead of by edge tier"
```

---

### Task 17: Add a "News" tab stub

**Files:**
- Modify: `webapp/index.html:541-546` (tab bar)
- Modify: `webapp/index.html:557-567` area (add a new `<section>`)
- Modify: `webapp/index.html:1914-1919` (`$('#seg').onclick` view-switch list)

- [ ] **Step 1: Add the tab button**

Current (`index.html:541-546`):
```html
  <div class="seg" role="tablist" id="seg">
    <button role="tab" aria-selected="true" data-view="outlook">League Projections</button>
    <button role="tab" aria-selected="false" data-view="matches">Match Projections</button>
    <button role="tab" aria-selected="false" data-view="teams">Teams</button>
    <button role="tab" aria-selected="false" data-view="health">Model Health</button>
  </div>
```
Replace with:
```html
  <div class="seg" role="tablist" id="seg">
    <button role="tab" aria-selected="true" data-view="outlook">League Projections</button>
    <button role="tab" aria-selected="false" data-view="matches">Match Projections</button>
    <button role="tab" aria-selected="false" data-view="teams">Teams</button>
    <button role="tab" aria-selected="false" data-view="health">Model Health</button>
    <button role="tab" aria-selected="false" data-view="news">News</button>
  </div>
```

- [ ] **Step 2: Add the (empty-state) section**

Current (`index.html:564-568`, right after the `view-health` section, before `view-matches`):
```html
  <section id="view-health" class="hidden">
    <div class="sec-h"><h2>Model &amp; data health</h2><span class="note">How the model is built, how well it predicts, and how complete its inputs are</span></div>
    <div id="healthBody"></div>
  </section>
```
Add a new section immediately after it (before `<section id="view-matches"...>`):
```html
  <section id="view-news" class="hidden">
    <div class="sec-h"><h2>News</h2><span class="note">Coming soon</span></div>
    <div style="color:var(--txt-3);padding:32px;text-align:center">News coverage for this league is coming soon.</div>
  </section>
```

- [ ] **Step 3: Add `news` to the view-switch list**

Current (`index.html:1914-1919`):
```js
$('#seg').onclick=e=>{const b=e.target.closest('button');if(!b)return;[...e.currentTarget.children].forEach(c=>c.setAttribute('aria-selected',c===b?'true':'false'));
  const v=b.dataset.view;
  ['outlook','matches','teams','health'].forEach(x=>$('#view-'+x).classList.toggle('hidden',v!==x));
  if(v==='matches'&&!$('#gameList').children.length){renderMarketPanel();renderGames();}
  if(v==='teams'&&!$('#eloGrid').children.length)renderTeams();
  if(v==='health'&&!$('#healthBody').children.length)renderHealth();};
```
Replace with:
```js
$('#seg').onclick=e=>{const b=e.target.closest('button');if(!b)return;[...e.currentTarget.children].forEach(c=>c.setAttribute('aria-selected',c===b?'true':'false'));
  const v=b.dataset.view;
  ['outlook','matches','teams','health','news'].forEach(x=>$('#view-'+x).classList.toggle('hidden',v!==x));
  if(v==='matches'&&!$('#gameList').children.length){renderMarketPanel();renderGames();}
  if(v==='teams'&&!$('#eloGrid').children.length)renderTeams();
  if(v==='health'&&!$('#healthBody').children.length)renderHealth();};
```

- [ ] **Step 4: Manual verification**

Load `/index.html?league=mls`, click the "News" tab, confirm it shows the "coming soon" placeholder and no console errors (check `preview_console_logs`).

- [ ] **Step 5: Commit**

```bash
git add webapp/index.html
git commit -m "feat(ui): add News tab placeholder"
```

---

### Task 18: Date the Model/Market/Naive comparison to the last model run

**Files:**
- Modify: `webapp/index.html:809-815` (`#acc` innerHTML)

- [ ] **Step 1: Add a "built" date line reusing the existing `D.generated` field**

Current (`index.html:809-815`):
```js
  $('#acc').innerHTML=
    `<div class="acc-nums">
       <div class="acc-row"><span class="t">Model</span><span class="v">${b3(m)}</span></div>
       <div class="acc-row"><span class="t">Market</span><span class="v">${b3(mk)}</span></div>
       <div class="acc-row"><span class="t">Naive</span><span class="v muted">${b3(n)}</span></div>
     </div>
     <div class="acc-tracks">${row('vs naive',naiveMap)}${row('vs market',mktMap)}</div>`;
```
Replace with (`D.generated` is already populated for every league — confirmed used identically in the Health tab's freshness strip at `index.html:1397`):
```js
  $('#acc').innerHTML=
    `<div class="acc-nums">
       <div class="acc-row"><span class="t">Model</span><span class="v">${b3(m)}</span></div>
       <div class="acc-row"><span class="t">Market</span><span class="v">${b3(mk)}</span></div>
       <div class="acc-row"><span class="t">Naive</span><span class="v muted">${b3(n)}</span></div>
       ${D.generated?`<div class="acc-row"><span class="t" style="width:auto">as of ${D.generated}</span></div>`:''}
     </div>
     <div class="acc-tracks">${row('vs naive',naiveMap)}${row('vs market',mktMap)}</div>`;
```

- [ ] **Step 2: Manual verification**

Load `/index.html?league=mls`, use `preview_snapshot` to confirm an "as of <date>" line appears near the Model/Market/Naive numbers in the header.

- [ ] **Step 3: Commit**

```bash
git add webapp/index.html
git commit -m "feat(ui): show last-model-run date next to the naive/market comparison"
```

---

## Final verification (run once, after all 18 tasks)

- [ ] Run the full Python test suite: `venv/bin/python -m pytest tests/ -v --browser chromium 2>&1 | tail -60` — expect no new failures beyond the two pre-existing, intentionally-unfixed mobile-overflow pins documented in `test_browser_smoke.py`'s `TestNoHorizontalOverflow` docstring.
- [ ] Start the preview server (`preview_start`), load `?league=mls`, `?league=epl`, `?league=eredivisie`, and the no-param Matches landing route; screenshot each.
- [ ] Resize to mobile (375×812) and screenshot the MLS league table + a team profile page.
- [ ] Confirm `git status` shows only the files this plan touched, no stray changes.
