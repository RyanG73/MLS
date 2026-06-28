# Webapp UI Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restyle the entire `webapp/index.html` dashboard onto a distinctive "quant-terminal" design system (mono numerics, flat panels, disciplined accents), add a race-strip header and projected-finish companion for single-table leagues, fix the trophy/conference bugs on the Teams tab, restyle all tournament tables, and add a global logo fallback — without touching any simulation/model logic.

**Architecture:** Presentation-only rewrite. Replace the `<style>` block with a new design system, then rewrite the HTML-template strings inside each render function. The Monte-Carlo engine (`runSim`, `runSimTable`, `confBracket`) and the JS↔Python porting contract are preserved; the only logic addition is capturing finishing-position percentiles inside the existing `runSimTable` loop. One new build script emits a logo lookup.

**Tech Stack:** Vanilla HTML/CSS/JS single file (`webapp/index.html`), per-league JSON-in-JS data files, Python 3 build scripts. No framework, no bundler, no JS test runner — **verification is done in the live browser preview** (launch config `webapp`, port 8090).

**Reference (exact styling source of truth):**
- Spec: `docs/superpowers/specs/2026-06-28-webapp-ui-redesign-design.md`
- Approved mockups: `docs/superpowers/specs/mockups/01-design-directions.html` (Direction B "Quant terminal" is chosen) and `docs/superpowers/specs/mockups/02-single-table-layout.html` (the full single-table page: race strip + dense table + projected-finish plot). **Match these for colors, fonts, spacing, and component structure.** Pixel values may be tuned against the real app during the verify loop.

**Standing verification protocol (every task that changes rendered output):**
1. `preview_start` (config `webapp`) if not running.
2. `preview_eval`: `window.location.href='http://localhost:8090/index.html?league=<id>'` for the relevant league, then reload.
3. `preview_console_logs` level `error` → expect none.
4. `preview_screenshot` → visually confirm against the mockup / description.
5. Where stated, `preview_eval` DOM assertions (computed widths, text content) to confirm structure.

**Standing commit rule:** commit after each task with a focused message. Branch first — do not commit redesign work directly without a feature branch.

---

## Task 0: Branch + design-reference sanity

**Files:** none (setup)

- [ ] **Step 1: Create a feature branch**

```bash
cd /Users/ryangerda/Development/MLS
git checkout -b feat/webapp-ui-redesign
```

- [ ] **Step 2: Confirm the preview server runs and the mockups render**

Start preview (config `webapp`). Open `http://localhost:8090/index.html?league=mls` and `?league=epl`; screenshot both to capture the **before** state for later comparison. Open `docs/superpowers/specs/mockups/02-single-table-layout.html` in the preview to re-confirm the target look.

Expected: MLS shows twin ladders; EPL shows the single table with the 770px-wide club column (the whitespace bug). No console errors.

- [ ] **Step 3: Commit the spec, mockups, and this plan**

```bash
git add docs/superpowers/specs/2026-06-28-webapp-ui-redesign-design.md \
        docs/superpowers/specs/mockups/ \
        docs/superpowers/plans/2026-06-28-webapp-ui-redesign.md
git commit -m "docs: webapp UI redesign spec, mockups, and plan"
```

---

## PHASE A — Design system + single-table page (sign-off gate)

Goal of this phase: get the new look approved on the real app for MLS + one single-table league before converting the rest.

### Task A1: Install the design-system foundations (tokens, fonts, primitives)

**Files:**
- Modify: `webapp/index.html` (the `<head>` font `<link>` ~line 9 and the `<style>` `:root` + base, ~lines 11–27)

- [ ] **Step 1: Add the mono font to the Google Fonts link**

In the `<link href="https://fonts.googleapis.com/css2?...">` add the `Spline Sans Mono` family:

```
family=Archivo:wght@600;700;800;900&family=Inter:wght@400;500;600;700&family=Spline+Sans+Mono:wght@500;600;700
```

- [ ] **Step 2: Replace the `:root` token block** with the new system (match mockup `02-single-table-layout.html`):

```css
:root{
  --ink-0:#070809; --ink-1:#0a0d0b; --ink-2:#0c100d; --ink-3:#121a14;
  --line:#131b14; --line-2:#18211a; --line-3:#243026;
  --txt-1:#e3e9e4; --txt-2:#9fb0a3; --txt-3:#54665b;
  --win:#f4b740; --qualify:#3ddc84; --europa:#4aa3ff; --drop:#ff5d5d; --draw:#5a6b7a;
  /* legacy aliases kept so untouched code keeps working until restyled */
  --floodlight:#3ddc84; --west:#f4b740; --hfa:#f4b740; --shield:#d7deea; --spoon:#bd7d4e;
  --mono:"Spline Sans Mono",ui-monospace,monospace;
  --r-sm:4px; --r-md:8px; --r-lg:10px;
  --s1:4px; --s2:8px; --s3:12px; --s4:16px; --s5:24px; --s6:36px;
  --maxw:1320px; --sbw:220px;
}
```

- [ ] **Step 3: Update `body` base** — remove the radial glow, set the new background and mono number defaults:

```css
body{font-family:"Inter",-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
  background:var(--ink-0); color:var(--txt-1);
  font-feature-settings:"tnum" 1; line-height:1.42;-webkit-font-smoothing:antialiased;
  padding-bottom:48px;padding-left:var(--sbw)}
```

- [ ] **Step 4: Add shared primitive classes** near the top of `<style>` (these are used by every later task — define once):

```css
.panel{border:1px solid var(--line-2);border-radius:var(--r-lg);background:var(--ink-1);overflow:hidden}
.panel-h{display:flex;align-items:center;gap:8px;padding:9px var(--s3);border-bottom:1px solid var(--line-2);background:var(--ink-2)}
.panel-h .dot{width:7px;height:7px;border-radius:50%;background:var(--qualify);box-shadow:0 0 8px var(--qualify);flex:none}
.panel-h h2{font-family:var(--mono);font-weight:700;font-size:11px;letter-spacing:.04em;color:var(--txt-1);text-transform:uppercase}
.panel-h .meta{margin-left:auto;font-family:var(--mono);font-size:10px;color:var(--txt-3)}
.num{font-family:var(--mono);font-variant-numeric:tabular-nums}
```

- [ ] **Step 5: Verify no breakage**

Run the standing verification protocol for `?league=mls`. The page will look half-migrated (that's expected) but must render without console errors and without layout collapse. Confirm numbers are unchanged (logic untouched).

- [ ] **Step 6: Commit**

```bash
git add webapp/index.html
git commit -m "feat(webapp): install quant-terminal design tokens + shared panel/mono primitives"
```

### Task A2: Race strip — replace the single-table favorite cards (#3)

**Files:**
- Modify: `webapp/index.html` — `.favs`/`.fav` CSS (~lines 107–123, 152–156) and `renderTableOutlook`/`tFavCard` (~lines 814–823, 895–898)

- [ ] **Step 1: Add `.races` / `.race` CSS** (copy from mockup `02-single-table-layout.html`, the `.races`, `.race`, `.cont` rules). Keep the accent-per-race rails (`.race.t/.u/.e/.r`). Use `repeat(auto-fit,minmax(220px,1fr))` so it wraps to ≤2 rows.

- [ ] **Step 2: Rewrite the table-league favorites as a race strip.** Replace `tFavCard` + the `$('#favs').innerHTML=...` line in `renderTableOutlook` with a race-card builder driven by `D.outlook.cards`. Each card: leader + top-2 contenders by that card's `key`:

```js
function raceCard(card){
  const ranked=[...D.standings.map(vals)].sort((a,b)=>(b[card.key]||0)-(a[card.key]||0));
  const lead=ranked[0], conts=ranked.slice(1,3);
  const max=Math.max(lead[card.key]||0,1);
  const accent={title:'t',ucl:'u',europa:'e',conf:'e',promo:'t',liguilla:'t',playoff:'u',releg:'r'}[card.key]||'u';
  const bar=t=>`<div class="cl"><span class="cn">${t.team}</span>
      <span class="cb"><i style="width:${((t[card.key]||0)/max*100).toFixed(0)}%"></i></span>
      <span class="cv num">${(t[card.key]||0).toFixed(0)}</span></div>`;
  return `<div class="race ${accent}">
    <div class="rk"><span>${card.label}</span><em>${card.hint||''}</em></div>
    <div class="lead">${crest(lead.team,lead.logo)}<span class="nm">${lead.team}</span><span class="pc num">${fmt(lead[card.key]||0)}</span></div>
    <div class="cont">${conts.map(bar).join('')}</div></div>`;
}
```

And in `renderTableOutlook`:

```js
$('#favs').className='races';
$('#favs').innerHTML=ol.cards.map(raceCard).join('');
```

> Note: `crest(...)` renders a 22px-ish crest; ensure the `.race .lead .crest` size is set in CSS (the mockup uses a bare `<img>`; here we reuse `crest()` so the fallback monogram still works — add `.race .lead .crest{width:22px;height:22px}`).

- [ ] **Step 3: Optional hint text.** `card.hint` may be absent in current payloads; the builder already guards with `||''`. Leave hints blank for now (a later, out-of-scope build change could add "top 5" etc.). Do **not** hardcode per-league hints.

- [ ] **Step 4: Verify** for `?league=epl` and `?league=serie-a`: race strip shows Title / Champions Lg / Relegation cards, each with a leader + 2 contender bars, on one row. Screenshot vs mockup. Confirm `document.querySelectorAll('#favs .race').length === D.outlook.cards.length` via `preview_eval`.

- [ ] **Step 5: Commit**

```bash
git add webapp/index.html
git commit -m "feat(webapp): race-strip header for single-table leagues (#3)"
```

### Task A3: Single-table layout — half-width dense table with labeled outcome columns (#2, #4 left half)

**Files:**
- Modify: `webapp/index.html` — `.tlad` CSS (~lines 157–173), `tableLadder` (~lines 861–894), `renderTableOutlook` grid (~line 904)

- [ ] **Step 1: Restyle the table grid + cells** to the dense mono panel from the mockup. Replace the `.tlad .thead/.trow` grid-template so the club column no longer eats all free space — give data columns fixed widths and constrain the club column. New grid (desktop), wrapped in a `.panel`:

```
grid-template-columns: 18px minmax(90px,1fr) 34px 34px /*per outcome col*/ ... ;
```

Concretely, build the grid string dynamically from the number of outcome columns so it stays tight regardless of league. In `tableLadder`, compute:

```js
const nOut=cols.length;
const grid=`18px minmax(90px,1fr) 36px 34px ${'34px '.repeat(nOut)}${hasUp?'80px':''}`;
```

and set it on the `.thead`/`.trow` via an inline style or a CSS custom property `--tgrid` on the `.tlad` container.

- [ ] **Step 2: Header row** — every outcome column gets its label (already from `cols.map(c=>c.label)`); add `Pts` and `Proj` (mono). This already exists; just confirm each `cols[]` entry (`title/ucl/europa/conf/releg`) renders a labeled `<span class="c">`. **Relegation now appears as a headed `Rel` column with a red heat cell — this is the #2 fix.**

- [ ] **Step 3: Heat cells** — keep `hc(v,key)` but map each `key` to its accent (`BRGB`): title/promo→win gold, ucl/playoff→qualify green, europa→blue, conf→blue, releg→drop red. Mono font on the number.

- [ ] **Step 4: Wrap the table in `.panel`** with a `.panel-h` ("League table" + meta `${ol.n_teams} teams · 10k sims`).

- [ ] **Step 5: Two-column body (table only for now).** In `renderTableOutlook`, set the ladders container to two equal columns and append the table into the left cell. The right cell stays empty until Task A4 adds the plot — so this task leaves the app working standalone:

```js
const l=$('#ladders'); l.innerHTML=''; l.style.gridTemplateColumns='minmax(0,1fr) minmax(0,1fr)';
l.append(tableLadder());   // Task A4 changes this line to: l.append(tableLadder(), finishPlotPanel());
```

Add a responsive rule: `@media(max-width:880px){#ladders{grid-template-columns:1fr!important}}`.

- [ ] **Step 6: Verify** `?league=epl`: table is now ~half width (left column) with labeled columns incl. `Rel`; club column no longer 770px; right half intentionally blank (plot lands in A4). Assert via `preview_eval` that the club column is now < 300px:

```js
getComputedStyle(document.querySelector('.tlad .trow')).gridTemplateColumns
```

Expected: second track now in the ~90–260px range, not ~770px.

- [ ] **Step 7: Commit**

```bash
git add webapp/index.html
git commit -m "feat(webapp): dense half-width single-table with labeled outcome columns (#2,#4)"
```

### Task A4: Projected-finish range plot companion (#4 right half)

**Files:**
- Modify: `webapp/index.html` — extend `runSimTable` (~lines 827–860); add `finishPlotPanel()` render fn; add plot CSS

- [ ] **Step 1: Capture finishing-position percentiles in `runSimTable`.** Inside the existing per-sim loop, after `order.sort(...)`, accumulate a position histogram. Add before the loop:

```js
const finishHist={}; SIM.teams.forEach(t=>finishHist[t]=new Float64Array(NT)); // [team][rank0..NT-1]
```

Inside the loop, after the `order` is sorted (already computed for column accounting):

```js
for(let r=0;r<NT;r++) finishHist[SIM.teams[order[r]]][r]++;
```

After the loop, compute P10/median/P90 (1-indexed positions) per team and attach to `out[t]`:

```js
function pctile(hist,N,q){let c=0,target=q*N;for(let r=0;r<hist.length;r++){c+=hist[r];if(c>=target)return r+1;}return hist.length;}
for(const t of SIM.teams){const h=finishHist[t];
  out[t].fin_p10=pctile(h,N,0.10); out[t].fin_med=pctile(h,N,0.50); out[t].fin_p90=pctile(h,N,0.90);}
```

(`out[t]` already exists in the function's return assembly — add these three fields there.)

- [ ] **Step 2: Run the table sim once at load** so non-what-if pages have finish data. The current code only runs the sim on what-if. Add, near the table render dispatch, a load-time populate that does NOT alter the server-provided odds — store finish percentiles separately:

```js
let finishVals=null;
function ensureFinish(){ if(!finishVals && SIM.teams.length) finishVals=runSimTable(10000); }
```

Call `ensureFinish()` inside `renderTableOutlook` before building the plot, and refresh `finishVals=simVals` semantics: when what-if is active, `simVals` already holds a fresh `runSimTable` result (which now includes `fin_*`), so prefer `simVals` when present, else `finishVals`.

- [ ] **Step 3: Add `finishPlotPanel()`** — returns a `.panel` element with one range row per team (match mockup `02-single-table-layout.html`'s `.plot`/`.frow`/`.rangebar`/`.median`):

```js
function finishZone(rank){ const ol=D.outlook;
  if(ol.green_line && rank<=1) return 'var(--win)';
  if(ol.green_line && rank<=ol.green_line) return 'var(--qualify)';
  if(ol.red_line && rank>ol.n_teams-ol.red_line) return 'var(--drop)';
  return 'var(--draw)'; }
function finishPlotPanel(){
  ensureFinish(); const src=simVals||finishVals||{};
  const N=D.outlook.n_teams;
  const teams=[...D.standings].map(s=>({...s,...(src[s.team]||{})}))
    .sort((a,b)=>(a.fin_med||99)-(b.fin_med||99));
  const pos=p=>((p-1)/(N-1)*100);
  const rows=teams.map(t=>{
    const a=t.fin_p10||1,m=t.fin_med||1,b=t.fin_p90||N, c=finishZone(Math.round(m));
    const L=pos(a),W=Math.max(2,pos(b)-pos(a));
    return `<div class="frow"><span class="fn">${crest(t.team,t.logo)}<b>${t.team}</b></span>
      <span class="track"><span class="rangebar" style="left:${L}%;width:${W}%;background:${c}"></span>
      <span class="median" style="left:calc(${pos(m)}% - 1px);background:${c}"></span></span></div>`;
  }).join('');
  const panel=el('div','panel');
  panel.innerHTML=`<div class="panel-h"><span class="dot" style="background:var(--europa);box-shadow:0 0 8px var(--europa)"></span>
      <h2>Projected finish</h2><span class="meta">10th–90th pct · ● median</span></div>
    <div class="plot"><div class="axis">${axisTicks(N)}</div>${rows}${finishLegend()}</div>`;
  return panel;
}
```

Add small helpers `axisTicks(N)` (ticks at 1, ~quartiles, N) and `finishLegend()` (zone color legend) — copy structure from the mockup.

- [ ] **Step 4: Append the plot into the right cell.** Change the `renderTableOutlook` append line introduced in Task A3 step 5 from `l.append(tableLadder());` to:

```js
l.append(tableLadder(), finishPlotPanel());
```

Then ensure the plot rebuilds on what-if: `renderTableOutlook` already re-runs on every what-if toggle (via `scheduleSim`), and it now re-appends `finishPlotPanel()`, which reads the freshest `simVals`/`finishVals` — confirm `simVals` carries the new `fin_*` fields after a toggle.

- [ ] **Step 5: Verify** `?league=epl`: right panel shows range bars with median dots; Arsenal/top teams cluster left (high finish), relegation teams right. Toggle a Next-5 what-if box and confirm the plot updates. Console clean. Screenshot vs mockup.

- [ ] **Step 6: Verify in-season + preseason** with `?league=liga-mx` (in-season) — plot reflects current standings; `?league=epl` (preseason) — plot spans full ranges from priors.

- [ ] **Step 7: Commit**

```bash
git add webapp/index.html
git commit -m "feat(webapp): projected-finish range plot companion + finish percentiles in runSimTable (#4)"
```

### Task A5: MLS twin-ladder restyle (keep layout, apply system)

**Files:**
- Modify: `webapp/index.html` — `.favs`/`.fav` MLS cards (~107–123), `.ladders`/`.ladder`/`.col-head`/`.row` (~125–151), `ladder()`/`renderFavs()` (~747–812)

- [ ] **Step 1: Restyle the MLS favorite cards** (Shield/East/West/Spoon) to the race-card aesthetic — but MLS keeps 4 single-team cards. Reuse `.race` styling: convert `favCard` markup to `.race`-style cards (leader crest + big mono %), accents: shield→neutral silver kept, east→qualify green, west→win gold, spoon→drop red (or keep `--spoon`). Keep it to one row of 4.

- [ ] **Step 2: Restyle `.col-head`/`.row`** to mono numerics, new heat colors (`RGB` map → accents), thin `--line` dividers, zone rails (`.row.hfa` green inset). Wrap each conference ladder in `.panel` + `.panel-h` ("Eastern Conference" + meta).

- [ ] **Step 3: Keep the twin-column `.ladders` grid** (`1fr 1fr`) — MLS already fills width; do NOT add the finish plot here.

- [ ] **Step 4: Verify** `?league=mls`: twin ladders, new look, what-if boxes still work (toggle one, confirm odds resimulate and rails update). Console clean. Screenshot.

- [ ] **Step 5: Commit**

```bash
git add webapp/index.html
git commit -m "feat(webapp): restyle MLS twin ladders + favorite cards onto new system"
```

### ⛳ PHASE A CHECKPOINT — get user sign-off

- [ ] Screenshot MLS, EPL, Liga MX (outlook tab) and present to the user. Confirm the look before proceeding to Phase B+. Address any aesthetic tweaks now (single place: tokens + primitives) before they propagate.

---

## PHASE B — Global logo fallback (#5)

### Task B1: Build the logo map

**Files:**
- Create: `scripts/build_logo_map.py`
- Create (generated): `webapp/data/logos.js`

- [ ] **Step 1: Write `scripts/build_logo_map.py`** — harvest `{team:logo}` from every `webapp/data/*.js` that has logos, add an alias map + manual supplement, emit `window.TEAM_LOGOS`:

```python
#!/usr/bin/env python3
"""Harvest a global {team_name: logo_url} map from per-league webapp data files.
Continental competitions (UCL, Leagues Cup, Concacaf) ship no logos; their teams
almost all appear in a domestic league file that does. Emits webapp/data/logos.js."""
import json, re, glob, os
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA=os.path.join(ROOT,'webapp','data')

def load(p):
    t=open(p).read(); t=re.sub(r'^[\s\S]*?=\s*','',t).rstrip().rstrip(';')
    return json.loads(t)

logos={}
for p in sorted(glob.glob(os.path.join(DATA,'*.js'))):
    if os.path.basename(p) in ('logos.js',): continue
    try: d=load(p)
    except Exception: continue
    rows=(d.get('standings') or [])+(d.get('field') or [])
    for s in rows:
        nm=s.get('team'); lg=s.get('logo')
        if nm and lg and nm not in logos: logos[nm]=lg

# Manual supplement for teams absent from every current file (promoted/relegated/new).
SUPPLEMENT={
  # name: ESPN team-logo URL (verify each id before adding)
  # "Coventry City":"https://a.espncdn.com/i/teamlogos/soccer/500/<id>.png",
}
for k,v in SUPPLEMENT.items(): logos.setdefault(k,v)

out=os.path.join(DATA,'logos.js')
with open(out,'w') as f:
    f.write('window.TEAM_LOGOS='+json.dumps(logos,ensure_ascii=False,separators=(',',':'))+';\n')
print(f'wrote {out}: {len(logos)} teams')
```

- [ ] **Step 2: Run it**

```bash
cd /Users/ryangerda/Development/MLS && python3 scripts/build_logo_map.py
```

Expected: `wrote .../logos.js: <N> teams` where N is ~150+.

- [ ] **Step 3: Verify coverage** for the previously-broken comps:

```bash
python3 - <<'PY'
import json,re,os
ROOT='/Users/ryangerda/Development/MLS/webapp/data'
def load(p):
    t=open(p).read();t=re.sub(r'^[\s\S]*?=\s*','',t).rstrip().rstrip(';');return json.loads(t)
logos=load(os.path.join(ROOT,'logos.js'))
for lg in ['ucl','leagues-cup','concacaf-champions']:
    d=load(os.path.join(ROOT,lg+'.js'))
    rows=(d.get('standings') or [])+(d.get('field') or [])
    miss=[s['team'] for s in rows if not s.get('logo') and s['team'] not in logos]
    print(lg,'still-missing:',len(miss),miss[:10])
PY
```

Expected: most teams now resolved; record any residual names — add them (with ESPN URLs) to `SUPPLEMENT` and re-run. Add a small `ALIAS` dict in the script for cross-payload name mismatches if any residuals are actually present under a different name (e.g. `Internazionale`↔`Inter Milan`).

- [ ] **Step 4: Commit**

```bash
git add scripts/build_logo_map.py webapp/data/logos.js
git commit -m "feat(webapp): global team logo map (build_logo_map.py -> logos.js) (#5)"
```

### Task B2: Wire the fallback into `crest()`

**Files:**
- Modify: `webapp/index.html` — add `<script src="data/logos.js">` after `leagues.js` (~line 507); update `crest()` (~line 560)

- [ ] **Step 1: Load the map.** After `<script src="leagues.js"></script>` add:

```html
<script src="data/logos.js"></script>
```

- [ ] **Step 2: Fallback in `crest()`**:

```js
const _logoMap=window.TEAM_LOGOS||{};
const _logoFor=(name,logo)=>logo||_logoMap[name]||_logoMap[(name||'').trim()]||'';
const crest=(name,logo)=>{const l=_logoFor(name,logo);
  return `<span class="crest"><span class="mono">${monogram(name)}</span>${l?`<img src="${l}" alt="" loading="lazy" onerror="this.remove()">`:''}</span>`;};
```

- [ ] **Step 3: Verify** `?league=ucl` and `?league=leagues-cup`: standings/bracket now show real crests instead of monograms. `preview_eval` count of `.crest:has(img)` should jump. Screenshot.

- [ ] **Step 4: Commit**

```bash
git add webapp/index.html
git commit -m "feat(webapp): crest() falls back to global logo map (#5)"
```

---

## PHASE C — Tournament / knockout views (#7)

### Task C1: League-phase + group tables as heat panels

**Files:**
- Modify: `webapp/index.html` — `renderKnockout` league-phase + group blocks (~1020–1048), associated `.tlad`/`.ko-*` CSS (~174–186)

- [ ] **Step 1: Replace the bare `<table>` league-phase block** with a `.panel` + `.thd`/`.trow` grid (same primitives as the single-table). Columns: `# · Team · Adv · Playoff · Out`, each a heat cell (Adv→qualify green, Playoff→win gold, Out→drop red), mono numerics, crest via `crest()`. Keep the top-8 / top-24 cut lines, restyled as `.ucl-line`-style dividers.

```js
// inside renderKnockout, phases.includes('league') branch — build with el()/grid, not <table>
```

- [ ] **Step 2: Replace the group-stage block** (Leagues Cup) with two side-by-side `.panel`s using the same grid (`# · Team · Adv` heat). Keep the advance line.

- [ ] **Step 3: Verify** `?league=ucl` (League Phase subtab) and `?league=leagues-cup` (group): styled panels with heat cells + crests, no bare tables, no right-half whitespace. Console clean. Screenshot.

- [ ] **Step 4: Commit**

```bash
git add webapp/index.html
git commit -m "feat(webapp): style knockout league-phase + group tables as heat panels (#7)"
```

### Task C2: Round-reach odds → heat matrix + bracket restyle

**Files:**
- Modify: `webapp/index.html` — `renderKnockout` champion-odds table (~1050–1056), `bracketTree` (~917–1000), `.br-*` CSS (~187–198)

- [ ] **Step 1: Replace the champion-odds `<table>`** with a heat matrix `.panel`: rows = teams sorted by `odds.win`; columns = `rounds` + `Win`; each cell a heat-mapped probability (alpha by value, qualify-green hue). Crest + team name in the first column. The `~` "estimated" marker becomes a small muted superscript.

```js
const fld=[...D.field].sort((a,b)=>b.odds.win-a.odds.win);
// header: '' , then rounds.map(label), then 'Win'
// row: crest+team, then rounds.map(r=>heatCell(odds[r])), then heatCell(odds.win) bold
```

Reuse a shared `koHeat(v)` returning `background:rgba(61,220,132,alpha)` with mono white-ish text.

- [ ] **Step 2: Restyle `bracketTree`** tie cards to the new system: `.br-tie` flat panel, winner in `--qualify`, scores mono, add `crest()` to team names (now that logos resolve via the map). Tighten `.br-col` widths. Keep the round-column horizontal-scroll layout.

- [ ] **Step 3: Verify** `?league=ucl` (Knockout subtab): heat-matrix round-odds + restyled bracket with crests. `?league=concacaf-champions` if it has a bracket. Console clean. Screenshot.

- [ ] **Step 4: Commit**

```bash
git add webapp/index.html
git commit -m "feat(webapp): round-reach heat matrix + bracket restyle (#7)"
```

---

## PHASE D — Teams tab: trophies + profile fix (#6)

### Task D1: Data-driven trophy registry + honest legend

**Files:**
- Modify: `webapp/index.html` — `TROPHY` map + `trophyGlyph` (~1221–1225), trophy legend HTML in `renderProfile` (~1314), trophy chips (~1292)

- [ ] **Step 1: Generalize the trophy registry.** Keep known glyphs, add a generic fallback:

```js
const TROPHY={
  'MLS Cup':{c:'#f4b740',g:'cup'},
  "Supporters' Shield":{c:'#cfd8e6',g:'shield'},
  'US Open Cup':{c:'#4aa3ff',g:'cup'},
  'League Title':{c:'#f4b740',g:'cup'}, 'Domestic Cup':{c:'#4aa3ff',g:'cup'}, 'Continental':{c:'#3ddc84',g:'cup'}
};
const trophyMeta=k=>TROPHY[k]||{c:'#9fb0a3',g:'cup'};  // unknown -> generic cup
```

Update `trophyGlyph` to use `trophyMeta(kind)` instead of bailing when `!TROPHY[kind]`.

- [ ] **Step 2: Build the legend from data, not hardcode.** Replace the hardcoded `<div class="troph-legend">...US Open Cup...</div>` with a legend generated from the distinct trophy `type`s present across `D.trophies` (excluding `Conference`):

```js
const _allTypes=[...new Set(Object.values(D.trophies||{}).flat()
                 .map(t=>t.type).filter(t=>t&&t!=='Conference'))];
const trophLegend=_allTypes.length
  ? `<div class="troph-legend">`+_allTypes.map(ty=>{const m=trophyMeta(ty);
      return `<span><svg width="13" height="13" viewBox="-4 -5 8 9"><path d="${m.g==='cup'?_CUP:_SHIELD}" fill="${m.c}"/></svg>${ty}</span>`;}).join('')+`</div>`
  : `<div class="troph-legend" style="color:var(--txt-3)">No trophy data for this league.</div>`;
```

Use `${trophLegend}` in the `renderProfile` template instead of the hardcoded markup.

- [ ] **Step 3: Verify** `?league=epl` Teams tab → click Arsenal: legend reads "No trophy data for this league." (NOT US Open Cup). `?league=mls` → Atlanta United: legend shows MLS Cup / Supporters' Shield / US Open Cup with markers on the ELO chart. Screenshot both.

- [ ] **Step 4: Commit**

```bash
git add webapp/index.html
git commit -m "fix(webapp): league-aware trophy legend + glyphs, no MLS leakage in Europe (#6)"
```

### Task D2: Fix the `0.4ern Conference` profile bug + ranking

**Files:**
- Modify: `webapp/index.html` — `renderProfile` (~1281–1316), specifically the `rank` computation (~1286) and the sub-header (~1313)

- [ ] **Step 1: Branch the profile header by league type.** Replace the sub-header build so table leagues never read `s.conf` as a conference name:

```js
const N=(D.outlook||{}).n_teams||D.standings.length;
const overallRank=[...D.standings].sort((a,b)=>(b.pts-a.pts)||(b.gd-a.gd)).findIndex(x=>x.team===team)+1;
const confRank=isTable?null
  :(D.standings.filter(x=>x.conf===s.conf).sort((a,b)=>(b.pts-a.pts)||(b.gd-a.gd)).findIndex(x=>x.team===team))+1;
const placeLabel=isTable ? `#${overallRank} of ${N}` : `${s.conf}ern Conference · #${confRank}`;
```

Use `${placeLabel}` in the `.prof-hd .sub` template instead of `${s.conf}ern Conference`. Also fix the `seasonCard` "`${s.conf} rank`" line: show `${isTable?'League':s.conf+' '} rank` → `#${isTable?overallRank:confRank}`.

- [ ] **Step 2: Verify** `?league=epl` Teams → Arsenal: sub reads "#1 of 20 · ELO …" (no "0.4ern"). `?league=mls` → still "Eastern Conference · #k". Screenshot.

- [ ] **Step 3: Commit**

```bash
git add webapp/index.html
git commit -m "fix(webapp): correct team-profile place label for single-table leagues (#6)"
```

---

## PHASE E — Remaining views onto the system (#8)

### Task E1: Header, sidebar, accuracy card, segmented tabs

**Files:**
- Modify: `webapp/index.html` — sidebar CSS (~30–52), header/`.acc` CSS (~54–85), `.seg` (~92–95)

- [ ] **Step 1: Restyle** sidebar (flat blocks, green active rail), header brand (flat beacon, no glow), the `#acc` accuracy card (mono numbers, drop rainbow → `--qualify`/`--drop` only), and the `.seg` tab bar (flat, mono-ish). Match the system tokens.
- [ ] **Step 2: Verify** across `?league=mls` and `?league=epl`: chrome consistent, no glow. Screenshot.
- [ ] **Step 3: Commit** `git commit -am "feat(webapp): restyle header/sidebar/accuracy/tabs onto new system"`

### Task E2: Matches view

**Files:** Modify `webapp/index.html` — `.grow`/`.cbar`/`.gr-*` CSS (~339–355), `renderGames` (~1190–1216)

- [ ] **Step 1: Restyle** the one-line match rows: mono odds/score, recolor the `cbar` win/draw/loss to `--qualify`/`--draw`/`--drop` (and team colors via `vis()` kept for the band), crest fallback already wired. Keep the result ✓/✗ badge.
- [ ] **Step 2: Verify** `?league=mls` Match Projections tab: rows styled, filters work (All/Upcoming/Played/Hit). Screenshot.
- [ ] **Step 3: Commit** `git commit -am "feat(webapp): restyle match-projection rows"`

### Task E3: Model Health + Power rankings + ELO grid

**Files:** Modify `webapp/index.html` — health CSS/`renderHealth` (~223–269, 1087–1144), power CSS/block (~1355–1398), elo-grid CSS (~301–320)

- [ ] **Step 1: Restyle** the Model Health cards/bars, the Power-rankings two panels (`.pr-*` → `.panel`, mono strength), and the Teams ELO mini-chart grid (mono ELO, new tier colors `--qualify`/`--drop`). Light touch — structure stays.
- [ ] **Step 2: Verify** `?league=epl` Model Health, `?league=power`, `?league=mls` Teams grid. Console clean. Screenshots.
- [ ] **Step 3: Commit** `git commit -am "feat(webapp): restyle health, power rankings, ELO grid onto new system"`

---

## PHASE F — Responsive + cleanup + docs

### Task F1: Responsive pass

**Files:** Modify `webapp/index.html` — media queries (~384–434) + any new grids

- [ ] **Step 1: Audit breakpoints.** `preview_resize` to 375px (mobile) and 768px (tablet) for `?league=mls`, `?league=epl`, `?league=ucl`. Confirm: race strip stacks; single-table body collapses to one column (table then plot); knockout panels stack; sidebar toggle works; no horizontal overflow.
- [ ] **Step 2: Fix** any overflow/collapse issues found (update the existing `@media` rules to the new grid template names).
- [ ] **Step 3: Verify** screenshots at 375px for the three leagues. Console clean.
- [ ] **Step 4: Commit** `git commit -am "fix(webapp): responsive pass for redesigned views"`

### Task F2: Remove dead CSS + final regression sweep

**Files:** Modify `webapp/index.html`

- [ ] **Step 1:** Grep the file for now-unused classes (old `.fav` variants, `.acc .bars`, `.heat` rainbow remnants) and remove genuinely dead rules. Be conservative — only remove classes with zero remaining references (`grep -o 'class="[^"]*"'` cross-check).
- [ ] **Step 2: Full regression sweep** — for each of `mls, epl, serie-a, liga-mx, ucl, europa, leagues-cup, concacaf-champions, power, championship`: load, switch through all tabs (Outlook/Matches/Teams/Health where present), `preview_console_logs` level error → none. Toggle a what-if box on mls + epl and confirm resim works and the finish plot updates.
- [ ] **Step 3: Commit** `git commit -am "chore(webapp): remove dead CSS after redesign"`

### Task F3: Docs per CLAUDE.md convention

**Files:** Modify `docs/PLAN.md`, `docs/CURRENT_STATE.md` (if relevant), delete the plan file

- [ ] **Step 1:** Add a blockquote entry to the top of `docs/PLAN.md` summarizing the UI redesign (date 2026-06-28, the 8 points addressed, new logo build step).
- [ ] **Step 2:** If `docs/CURRENT_STATE.md` documents run commands, add `python3 scripts/build_logo_map.py` to the build/run section.
- [ ] **Step 3:** Append a dated 2–3 sentence entry to `docs/PROJECT_HISTORY.md` and **delete** `docs/superpowers/plans/2026-06-28-webapp-ui-redesign.md` (completed plans are deleted, not archived).
- [ ] **Step 4: Commit** `git commit -am "docs: record webapp UI redesign; add logo-map build step"`

### Task F4: Finish the branch

- [ ] Use superpowers:finishing-a-development-branch to decide merge/PR. Present before/after screenshots (MLS, EPL, UCL, Teams tab) to the user.

---

## Self-review notes (coverage map)

- #1 generic look → A1 (tokens/primitives), E1–E3 (chrome/all views).
- #2 relegation column → A3 (labeled `Rel` outcome column).
- #3 top boxes → A2 (race strip, auto-fit ≤2 rows).
- #4 single-table whitespace → A3 (half-width table) + A4 (finish-plot companion).
- #5 logos → B1 (build map) + B2 (crest fallback).
- #6 trophies/conf bug → D1 (legend/registry) + D2 (place-label fix).
- #7 tournament tables → C1 (league/group heat panels) + C2 (round-reach matrix + bracket).
- #8 general → A5 (MLS), E1–E3, F1 (responsive).
- Preserve sim logic → only `runSimTable` gains accumulators (A4); no math changed.

No placeholders in load-bearing code (race card, table grid, finish plot, logo map, trophy legend, profile fix are all concrete). Derivative restyles (E1–E3) reference the shared primitives + mockup as the source of truth.
