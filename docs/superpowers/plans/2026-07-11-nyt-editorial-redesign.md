# NYT-Style Dark Editorial Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the Entenser webapp chrome and homepage as a dark-mode NYT-style front page: masthead + country/flag section bar site-wide, mobile bottom tab bar (Home · Matches · Leagues · Favorites), an editorial headline-driven homepage, a Leagues index page, and a Favorites page (leagues + teams).

**Architecture:** All frontend work happens inside the single-file SPA `webapp/index.html` (CSS in the `<style>` block, markup in `<body>`, JS in the trailing `<script>` blocks). One pipeline change adds a `fixtures` array to `scripts/build_home.py` → `webapp/data/home.js`. The left sidebar is deleted; new routes `?league=leagues` and `?league=favorites` follow the existing route-flag pattern (`_isHome`, `_isEdgeBoard`, `_infoPage`).

**Tech Stack:** Vanilla JS/CSS static site; Python 3 + pytest for the pipeline; browser preview for frontend verification.

**Spec:** `docs/superpowers/specs/2026-07-11-nyt-editorial-redesign-design.md`

**Key existing facts (verified 2026-07-11):**
- Route bootstrap: `webapp/index.html:768-806` (`_rawLeague`, `_isHome`, `_isEdgeBoard`, `_infoPage`, data-file `document.write`, `D` stub).
- Sidebar IIFE to delete: `webapp/index.html:812-862` (ends with `$('#sbToggle').onclick=...`). Sidebar markup: lines 668-672. Sidebar CSS: the `/* ── league sidebar ── */` block + `@media(max-width:900px)` sidebar rules + `body{...padding-left:var(--sbw)}` + `--sbw` token + `.brand{margin-left:54px}`.
- League fav pins already stored at localStorage key `pitchside.favLeagues` (a JSON array of league ids).
- Home render block: `webapp/index.html:2882-2940` (`if(_isHome && window.HOME_DATA){...}`).
- Helpers available at render time: `crest(name,logo)` (line ~877), `commandEsc(s)` (line ~2750), `$()`, `el()`, `FOOT_HTML` backfill IIFE (line ~3035).
- Per-league game shape: `{date:"2026-08-21", home, away, pH, pD, pA, result:null, ko, hlogo, alogo, ...}`; standings rows have `team, proj_rank, logo, color` + metric keys named by `outlook.cards[0].key`.
- `leagues.js` groups: Americas(5) · South America(2) · Asia(4) · England(5) · Spain(2) · Italy(2) · Germany(2) · France(2) · Other Europe(19) · Women(1) · Cups(5).
- Team profile header template: the `$('#teamProfile').innerHTML=` assignment at `webapp/index.html:2431` starting `<div class="prof-hd">`.

---

### Task 1: `build_home.py` — add upcoming-fixtures array

**Files:**
- Modify: `scripts/build_home.py`
- Test: `tests/test_build_home_fixtures.py` (new)

- [ ] **Step 1: Write the failing test**

Create `tests/test_build_home_fixtures.py`:

```python
"""build_fixtures: upcoming games only, horizon-capped, prominence-first, capped count."""
import importlib.util
from datetime import date, timedelta
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "build_home", Path(__file__).resolve().parents[1] / "scripts" / "build_home.py")
build_home = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(build_home)


def _mk(lid, games):
    return (lid, {"league": {"name": lid.upper()}, "games": games})


def _g(days_out, home="H", away="A", result=None):
    d = (date.today() + timedelta(days=days_out)).isoformat()
    return {"date": d, "home": home, "away": away, "result": result,
            "pH": 0.5, "pD": 0.3, "pA": 0.2, "ko": d + "T19:00Z",
            "hlogo": None, "alogo": None}


def test_filters_played_and_horizon():
    files = [_mk("epl", [_g(1), _g(2, result="H"), _g(30)])]
    fx = build_home.build_fixtures(files)
    assert len(fx) == 1
    assert fx[0]["league"] == "epl"
    assert set(fx[0]) >= {"league", "name", "date", "home", "away", "pH", "pD", "pA"}


def test_prominent_league_first_and_cap():
    files = [_mk("finland-veikkausliiga", [_g(1) for _ in range(10)]),
             _mk("epl", [_g(2) for _ in range(10)])]
    fx = build_home.build_fixtures(files, limit=12)
    assert len(fx) == 12
    assert fx[0]["league"] == "epl"          # prominence beats date
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/ryangerda/Development/MLS && python -m pytest tests/test_build_home_fixtures.py -v`
Expected: FAIL with `AttributeError: module 'build_home' has no attribute 'build_fixtures'`

- [ ] **Step 3: Implement `build_fixtures`**

In `scripts/build_home.py`, add after `build_movers()`:

```python
def build_fixtures(files: list[tuple[str, dict]], limit: int = 12,
                   days: int = 10) -> list[dict]:
    """Upcoming fixtures (next `days` days) across live leagues, biggest
    leagues first, for the homepage right-rail. Chronological within a league."""
    from datetime import date, timedelta
    today = date.today().isoformat()
    horizon = (date.today() + timedelta(days=days)).isoformat()
    fx = []
    for lid, d in files:
        name = (d.get("league") or {}).get("name", lid)
        for g in d.get("games", []):
            if g.get("result") is not None:
                continue
            gd = g.get("date") or ""
            if not (today <= gd <= horizon):
                continue
            fx.append({
                "league": lid, "name": name, "date": gd, "ko": g.get("ko"),
                "home": g.get("home"), "away": g.get("away"),
                "pH": g.get("pH"), "pD": g.get("pD"), "pA": g.get("pA"),
                "hlogo": g.get("hlogo"), "alogo": g.get("alogo"),
            })
    fx.sort(key=lambda f: (_prom_key(f["league"]), f["date"]))
    return fx[:limit]
```

In `main()`, add `"fixtures": build_fixtures(files),` after the `"movers"` line, and append fixture count to the print line.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_build_home_fixtures.py -v`
Expected: 2 passed

- [ ] **Step 5: Regenerate home.js and sanity-check**

Run: `cd /Users/ryangerda/Development/MLS && python scripts/build_home.py && python -c "import json;t=open('webapp/data/home.js').read();d=json.loads(t[t.index('{'):t.rindex('}')+1]);print(len(d['fixtures']),'fixtures');print(d['fixtures'][:2])"`
Expected: prints fixture count (0 is acceptable in mid-summer — the UI has an empty state) and well-formed rows.

- [ ] **Step 6: Commit**

```bash
git add scripts/build_home.py tests/test_build_home_fixtures.py webapp/data/home.js
git commit -m "feat(home): build_home.py emits upcoming-fixtures array for homepage rail"
```

---

### Task 2: Route bootstrap — new routes + shared FavStore

**Files:**
- Modify: `webapp/index.html:768-806` (bootstrap), `webapp/index.html:812+` (add FavStore before the sidebar IIFE)

- [ ] **Step 1: Add route flags and data loading**

In the bootstrap script (line ~772), after `const _isEdgeBoard=...`, add:

```js
const _isLeagues=_rawLeague==='leagues';   // full league index (replaces sidebar)
const _isFavs=_rawLeague==='favorites';    // pinned leagues + teams
```

Change the data-file `document.write` selector (line ~783) so the index and favorites routes also load the cross-league home payload:

```js
document.write('<scr'+'ipt src="data/'+((_isHome||_isLeagues||_isFavs)?'home':_isEdgeBoard?'edge-board':LID)+'.js?t='+Date.now()+'"></scr'+'ipt>');
```

Extend the two `if(!_isHome&&!_isEdgeBoard&&...)` guards for news/drift files with `&&!_isLeagues&&!_isFavs`.

Extend the `D` stub condition (line ~801) to `(_isPower || _isEdgeBoard || _isHome || _infoPage || _isLeagues || _isFavs)` and its name/mode ternaries with `_isLeagues?'Leagues':_isFavs?'Favorites':` branches (exact strings unimportant; the stub only prevents null derefs).

- [ ] **Step 2: Add FavStore (window-scoped, replaces sidebar-local fav helpers)**

Immediately before the sidebar IIFE (line ~812), add:

```js
// ── FavStore: league pins (existing key) + team pins (new), shared by masthead,
//    Leagues index, Favorites page, and team profiles ──
const FavStore=(()=>{ 
  const LKEY='pitchside.favLeagues', TKEY='pitchside.favTeams';
  const read=k=>{try{return JSON.parse(localStorage.getItem(k)||'[]');}catch(e){return[];}};
  const write=(k,v)=>localStorage.setItem(k,JSON.stringify(v));
  return {
    leagues:()=>new Set(read(LKEY)),
    toggleLeague:id=>{const s=new Set(read(LKEY));s.has(id)?s.delete(id):s.add(id);write(LKEY,[...s]);return s;},
    teams:()=>read(TKEY),                                   // [{league,team}]
    hasTeam:(lg,t)=>read(TKEY).some(x=>x.league===lg&&x.team===t),
    toggleTeam:(lg,t)=>{const a=read(TKEY);const i=a.findIndex(x=>x.league===lg&&x.team===t);
      const added=i<0; added?a.push({league:lg,team:t}):a.splice(i,1); write(TKEY,a); return added;},
  };
})();
```

- [ ] **Step 3: Verify no console errors on existing routes**

Load the preview (`?league=epl`, `?league=command`, no-param home) and check the console — no new errors. (Browser preview tooling; no test framework exists for the SPA.)

- [ ] **Step 4: Commit**

```bash
git add webapp/index.html
git commit -m "feat(chrome): leagues/favorites route flags + shared FavStore"
```

---

### Task 3: Masthead chrome — kill sidebar, add NYT header + bottom nav

**Files:**
- Modify: `webapp/index.html` — CSS `<style>` block, body markup (lines 668-681, 753), sidebar IIFE (812-862)

- [ ] **Step 1: CSS — remove sidebar tokens/rules, add serif token**

In `:root` (line 42): delete `--sbw:220px;` from the `--maxw` line and add `--serif:Georgia,'Times New Roman',serif;`.
In `body{...}` (line 56): delete `padding-left:var(--sbw)`.
Delete the whole `/* ── league sidebar ── */` CSS block (`.sidebar`, `.sb-brand`, `.sb-grp`, `.sb-lg`, `.sb-star`, `.sb-grp-toggle`, `.sb-chev`, `.sb-toggle` — lines ~70-88) and inside `@media(max-width:900px)` (line 89) delete the `:root{--sbw:0px}`, `.sidebar`, `.sidebar.open`, `.sb-toggle`, and `.brand{margin-left:54px}` rules (keep the media query if other rules land there in Step 2).

- [ ] **Step 2: CSS — masthead + country bar + bottom nav**

Add after the deleted sidebar block:

```css
/* ── NYT-style masthead (site-wide chrome) ── */
#mast{background:var(--ink-0);border-bottom:2px solid var(--line-3)}
.mast-top{display:grid;grid-template-columns:1fr auto 1fr;align-items:center;padding:12px var(--s4) 8px;gap:var(--s3)}
.mast-date{font-size:11px;color:var(--txt-2)}
.mast-date span{display:block;color:var(--txt-3)}
.mast-wordmark{font-family:var(--serif);font-weight:700;font-size:30px;letter-spacing:.01em;color:var(--txt-1);text-decoration:none;text-align:center}
.mast-stat{font-family:var(--mono);font-size:11px;color:var(--txt-3);text-align:right}
.mast-bar{display:flex;justify-content:center;gap:2px;border-top:1px solid var(--line-2);flex-wrap:nowrap;overflow-x:auto;scrollbar-width:none;-webkit-overflow-scrolling:touch;padding:0 var(--s4)}
.mast-bar::-webkit-scrollbar{display:none}
.mb-item{position:relative;flex:none}
.mb-item>a{display:flex;align-items:center;gap:5px;padding:9px 10px;font-size:12.5px;font-weight:600;color:var(--txt-2);text-decoration:none;border-bottom:2px solid transparent;white-space:nowrap}
.mb-item>a:hover{color:var(--txt-1)}
.mb-item>a.active{color:var(--txt-1);border-bottom-color:var(--txt-1)}
.mb-menu{display:none;position:absolute;left:0;top:100%;z-index:60;min-width:210px;background:var(--ink-1);border:1px solid var(--line-3);border-radius:0 0 var(--r-md) var(--r-md);box-shadow:0 12px 30px rgba(0,0,0,.5);padding:6px 0;max-height:60vh;overflow-y:auto}
.mb-item.open .mb-menu,.mb-item:hover .mb-menu{display:block}
.mb-menu a{display:flex;align-items:center;gap:8px;padding:7px 12px;font-size:12.5px;color:var(--txt-2);text-decoration:none}
.mb-menu a:hover{background:var(--ink-2);color:var(--txt-1)}
.mb-menu a img{width:16px;height:16px;object-fit:contain}
.mb-menu a .soon-tag{margin-left:auto;font-size:8px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;color:var(--txt-3);border:1px solid var(--line-2);border-radius:4px;padding:1px 4px}
.mast-live{display:flex;align-items:center;gap:8px;justify-content:center;padding:6px var(--s4);border-top:1px solid var(--line-2);font-size:11.5px;color:var(--txt-2)}
.mast-live .dot{width:7px;height:7px;border-radius:50%;background:var(--drop);animation:pulse 1.6s infinite}
@keyframes pulse{50%{opacity:.35}}
.mast-live a{color:var(--txt-1);text-decoration:none;font-weight:600}
/* ── mobile bottom tab bar ── */
.bnav{display:none}
@media(max-width:900px){
  body{padding-bottom:84px}
  .bnav{display:grid;grid-template-columns:repeat(4,1fr);position:fixed;left:0;right:0;bottom:0;z-index:70;
    background:rgba(10,13,11,.96);backdrop-filter:blur(12px);border-top:1px solid var(--line-3);padding:6px 0 calc(6px + env(safe-area-inset-bottom))}
  .bnav a{display:flex;flex-direction:column;align-items:center;gap:2px;font-size:10px;font-weight:600;color:var(--txt-3);text-decoration:none}
  .bnav a .ico{font-size:19px;line-height:1}
  .bnav a.active{color:var(--txt-1)}
  .mast-top{grid-template-columns:1fr;justify-items:center;padding:10px var(--s4) 6px}
  .mast-date,.mast-stat{display:none}
  .mast-wordmark{font-size:24px}
  .mast-bar{justify-content:flex-start}
}
```

- [ ] **Step 3: Markup — replace sidebar with mast + bnav**

Replace lines 668-672 (`<button class="sb-toggle"...>` through `</nav>`) with:

```html
<div id="mast"></div>
```

After `<footer class="wrap" id="foot"></footer>` (line 753) add:

```html
<nav class="bnav" id="bnav"></nav>
```

- [ ] **Step 4: JS — replace the sidebar IIFE with the masthead/bnav renderer**

Replace the whole sidebar IIFE (from `// ── Sidebar: leagues grouped by country/region` through `$('#sbToggle').onclick=...;` and its closing `})();`) with:

```js
// ── NYT-style masthead: date row + country bar with league dropdowns + LIVE strip ──
(()=>{ 
  const mast=$('#mast'); if(!mast) return;
  const MAST_GROUPS=[['England','🏴󠁧󠁢󠁥󠁮󠁧󠁿','England'],['Spain','🇪🇸','Spain'],['Italy','🇮🇹','Italy'],
    ['Germany','🇩🇪','Germany'],['France','🇫🇷','France'],['Americas','🌎','Americas'],
    ['South America','🇧🇷','S. America'],['Other Europe','🇪🇺','Europe'],['Asia','🌏','Asia'],
    ['Cups','🏆','Cups'],['Women','⚽','Women']];
  const groups={};
  (window.LEAGUES||[]).forEach(l=>{(groups[l.group||'Other Europe']=groups[l.group||'Other Europe']||[]).push(l);});
  const menuLink=l=>{const lg=l.logo?`<img src="${l.logo}" alt="" onerror="this.remove()">`:'';
    return `<a href="?league=${l.id}">${lg}<span>${l.name}</span>${l.status!=='live'?'<span class="soon-tag">soon</span>':''}</a>`;};
  const activeGroup=(!_isHome&&!_isEdgeBoard&&!_isLeagues&&!_isFavs&&!_infoPage&&LID!=='power')
    ? ((window.LEAGUES||[]).find(l=>l.id===LID)||{}).group : null;
  const H=window.HOME_DATA;
  const dstr=new Date().toLocaleDateString('en-US',{weekday:'long',month:'long',day:'numeric',year:'numeric'});
  let bar=`<div class="mb-item"><a href="${location.pathname}" class="${_isHome?'active':''}">🏠 Home</a></div>`
         +`<div class="mb-item"><a href="?league=command" class="${_isEdgeBoard?'active':''}">⚡ Matches</a></div>`;
  MAST_GROUPS.forEach(([g,flag,label])=>{ if(!groups[g]||!groups[g].length) return;
    bar+=`<div class="mb-item" data-group="${g}"><a href="?league=${groups[g][0].id}" class="${activeGroup===g?'active':''}">${flag} ${label}</a>
      <div class="mb-menu">${groups[g].map(menuLink).join('')}</div></div>`;});
  bar+=`<div class="mb-item"><a href="?league=power" class="${!_isEdgeBoard&&!_isHome&&!_isLeagues&&!_isFavs&&LID==='power'?'active':''}">🌍 Power</a></div>`;
  const live=(H&&H.fixtures&&H.fixtures.length)
    ?`<div class="mast-live"><span class="dot"></span><a href="?league=command">${H.fixtures.length} fixtures modeled in the next 10 days</a><span>· across ${H.stats.leagues} leagues</span></div>`:'';
  mast.innerHTML=`<div class="mast-top">
      <div class="mast-date">${dstr}${H?`<span>Updated ${H.generated}</span>`:''}</div>
      <a class="mast-wordmark" href="${location.pathname}">Entenser</a>
      <div class="mast-stat">${(window.LEAGUES||[]).filter(l=>l.status==='live').length} leagues live</div>
    </div><nav class="mast-bar">${bar}</nav>${live}`;
  // tap-to-toggle dropdowns (hover covers desktop; click covers touch)
  mast.querySelectorAll('.mb-item[data-group]>a').forEach(a=>a.addEventListener('click',e=>{
    if(matchMedia('(hover:hover)').matches) return;           // desktop: follow link
    const it=a.parentElement;
    if(!it.classList.contains('open')){e.preventDefault();
      mast.querySelectorAll('.mb-item.open').forEach(o=>o.classList.remove('open'));
      it.classList.add('open');}
  }));
  document.addEventListener('click',e=>{if(!mast.contains(e.target))mast.querySelectorAll('.mb-item.open').forEach(o=>o.classList.remove('open'));});
  // bottom tab bar
  const bn=$('#bnav'); if(bn) bn.innerHTML=
    `<a href="${location.pathname}" class="${_isHome?'active':''}"><span class="ico">🏠</span>Home</a>
     <a href="?league=command" class="${_isEdgeBoard?'active':''}"><span class="ico">⚡</span>Matches</a>
     <a href="?league=leagues" class="${_isLeagues?'active':''}"><span class="ico">🗂️</span>Leagues</a>
     <a href="?league=favorites" class="${_isFavs?'active':''}"><span class="ico">★</span>Favorites</a>`;
})();
```

- [ ] **Step 5: Verify in browser**

Preview desktop 1280px: masthead renders on `?league=epl`, home, `?league=command`; dropdowns open on hover; no sidebar remnants; no horizontal scroll. Mobile 375px: bottom nav shows with 4 tabs, country bar scrolls horizontally, no hamburger. Console clean on all three routes.

- [ ] **Step 6: Commit**

```bash
git add webapp/index.html
git commit -m "feat(chrome): NYT-style masthead + country bar + mobile bottom nav; sidebar removed"
```

---

### Task 4: Homepage editorial layout

**Files:**
- Modify: `webapp/index.html` — the `_isHome` block (was 2882-2940) and the `/* ── Home landing ── */` CSS section (~2666)

- [ ] **Step 1: CSS — editorial styles (append to the Home landing CSS section)**

```css
/* NYT editorial homepage (2026-07-11 redesign) */
.ed-wrap{padding-top:var(--s4)}
.ed-kicker{font-family:var(--mono);font-size:10px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:var(--txt-3);margin-bottom:6px}
.ed-lead h1{font-family:var(--serif);font-size:38px;line-height:1.12;font-weight:700;letter-spacing:0;margin:0 0 10px}
.ed-lead .deck{font-family:var(--serif);font-size:16px;line-height:1.45;color:var(--txt-2);max-width:640px;margin-bottom:8px}
.ed-lead a{color:inherit;text-decoration:none}
.ed-lead a:hover h1{text-decoration:underline;text-decoration-thickness:1px;text-underline-offset:3px}
.ed-cols{display:grid;grid-template-columns:1fr 1fr;gap:0 28px}
.ed-grid{display:grid;grid-template-columns:minmax(0,2fr) 1px minmax(0,1fr);gap:0 24px;margin-top:var(--s4)}
.ed-vrule{background:var(--line-2)}
.ed-story{display:block;padding:14px 0;border-top:1px solid var(--line-2);text-decoration:none;color:inherit}
.ed-story h3{font-family:var(--serif);font-size:19px;line-height:1.25;font-weight:700;letter-spacing:0;margin:0 0 5px}
.ed-story:hover h3{text-decoration:underline;text-decoration-thickness:1px;text-underline-offset:3px}
.ed-story .deck{font-size:13px;line-height:1.45;color:var(--txt-2)}
.ed-sec{font-family:var(--serif);font-size:15px;font-weight:700;border-bottom:1px solid var(--line-3);padding-bottom:6px;margin:var(--s4) 0 2px}
.ed-model{display:flex;align-items:center;gap:9px;padding:9px 0;border-top:1px solid var(--line-2);text-decoration:none;color:inherit;font-size:13px}
.ed-model:hover{background:var(--ink-1)}
.ed-model img{width:18px;height:18px;object-fit:contain}
.ed-model .lg{color:var(--txt-3);font-size:11px;width:92px;flex:none;text-transform:uppercase;letter-spacing:.03em}
.ed-model b{font-family:var(--mono);margin-left:auto;font-size:14px}
.ed-model .lab{color:var(--txt-3);font-size:10px}
.ed-fix{display:block;padding:9px 0;border-top:1px solid var(--line-2);text-decoration:none;color:inherit}
.ed-fix .t{display:flex;align-items:center;gap:6px;font-size:13px;font-weight:600}
.ed-fix .t img{width:15px;height:15px;object-fit:contain}
.ed-fix .t .vs{color:var(--txt-3);font-weight:400;font-size:11px}
.ed-fix .m{font-size:10.5px;color:var(--txt-3);margin-top:3px;font-family:var(--mono)}
.ed-probbar{display:flex;height:4px;border-radius:2px;overflow:hidden;margin-top:5px}
.ed-probbar i{display:block;height:100%}
.ed-news{display:block;padding:10px 0;border-top:1px solid var(--line-2);text-decoration:none;color:inherit}
.ed-news h4{font-family:var(--serif);font-size:14.5px;font-weight:700;line-height:1.3;margin:0 0 3px}
.ed-news:hover h4{text-decoration:underline;text-decoration-thickness:1px;text-underline-offset:3px}
.ed-news .m{font-size:10.5px;color:var(--txt-3)}
.ed-newsband{display:grid;grid-template-columns:repeat(3,1fr);gap:0 24px;margin-top:2px}
@media(max-width:900px){
  .ed-lead h1{font-size:28px}
  .ed-grid{grid-template-columns:1fr;gap:0}
  .ed-vrule{display:none}
  .ed-cols,.ed-newsband{grid-template-columns:1fr}
}
```

- [ ] **Step 2: Replace the `_isHome` render block**

Replace the entire `if(_isHome && window.HOME_DATA){...}` block with (keeps `nm`, `ago`; drops the hero/KPI/card-grid):

```js
if(_isHome && window.HOME_DATA){
  const H=window.HOME_DATA;
  const seg=$('#seg'); if(seg) seg.style.display='none';
  const hd=document.querySelector('header'); if(hd) hd.style.display='none';
  document.querySelectorAll('main.wrap > section').forEach(s=>{ if(s.id!=='view-outlook') s.classList.add('hidden'); });
  document.title="Entenser — Home";
  const nm=id=>{const l=(window.LEAGUES||[]).find(x=>x.id===id);return l?l.name:id;};
  const ago=iso=>{ if(!iso) return ''; const d=(Date.now()-new Date(iso))/36e5;
    return d<1?`${Math.max(1,Math.round(d*60))}m`:d<24?`${Math.round(d)}h`:`${Math.round(d/24)}d`; };

  // ── deterministic headline writer: movers → tight races → relegation ──
  const stories=[];
  (H.movers||[]).forEach(m=>{const up=m.delta>=0;stories.push({league:m.league,mag:Math.abs(m.delta),
    kicker:`${nm(m.league)} · ${m.metric_label}`,
    h:`${m.team}’s ${m.metric_label} Odds ${up?'Jump':'Fall'} ${Math.abs(m.delta).toFixed(1)} Points`,
    deck:`This week’s results moved the model to ${m.now}% — the ${up?'biggest riser':'sharpest drop'} tracked in ${nm(m.league)}.`});});
  (H.tight_races||[]).forEach(r=>{const [a,b]=r.teams;if(!a||!b)return;stories.push({league:r.league,mag:Math.max(0,20-r.gap),
    kicker:`${r.name} · ${r.metric_label} race`,
    h:`${a.team} Lead${a.team.endsWith('s')?'':'s'} ${r.name} Race by Just ${r.gap} Points`,
    deck:`${a.team} (${a.pct}%) hold${a.team.endsWith('s')?'':'s'} off ${b.team} (${b.pct}%)${r.teams[2]?` with ${r.teams[2].team} (${r.teams[2].pct}%) lurking`:''}.`});});
  (H.releg_battles||[]).forEach(b=>{stories.push({league:b.league,mag:b.n_contested,
    kicker:`${b.name} · relegation`,
    h:`${b.n_contested} Clubs Locked in the ${b.name} Relegation Scrap`,
    deck:`${b.teams.slice(0,3).map(t=>`${t.team} (${t.pct}%)`).join(', ')} are all live to go down.`});});
  stories.sort((x,y)=>y.mag-x.mag);
  const lead=stories.shift();
  const story=s=>`<a class="ed-story" href="?league=${s.league}"><div class="ed-kicker">${s.kicker}</div><h3>${s.h}</h3><div class="deck">${s.deck}</div></a>`;

  // ── right rail: the models (big-league leaders) + upcoming fixtures ──
  const BIG=['epl','la-liga','serie-a','bundesliga','ligue-1','mls'];
  const models=(H.leaders||[]).filter(l=>BIG.includes(l.league)).map(l=>
    `<a class="ed-model" href="?league=${l.league}"><span class="lg">${nm(l.league)}</span>${crest(l.team,l.logo)}<span>${l.team}</span><b>${l.pct}%</b><span class="lab">${l.metric_label}${l.preseason?' · pre':''}</span></a>`).join('');
  const fix=f=>{const pct=x=>Math.round((x||0)*100);
    return `<a class="ed-fix" href="?league=${f.league}"><div class="t">${crest(f.home,f.hlogo)}${f.home}<span class="vs">v</span>${crest(f.away,f.alogo)}${f.away}</div>
    <div class="ed-probbar"><i style="width:${pct(f.pH)}%;background:var(--qualify)"></i><i style="width:${pct(f.pD)}%;background:var(--draw)"></i><i style="width:${pct(f.pA)}%;background:var(--drop)"></i></div>
    <div class="m">${f.date} · ${f.name} · ${pct(f.pH)}/${pct(f.pD)}/${pct(f.pA)}</div></a>`;};
  const fixtures=(H.fixtures||[]).slice(0,8).map(fix).join('')||'<div class="news-empty">No fixtures modeled in the next 10 days.</div>';

  const news=(H.news||[]).slice(0,9).map(n=>`<a class="ed-news" href="${n.link}" target="_blank" rel="noopener noreferrer">
    <h4>${commandEsc(n.title||'')}</h4><div class="m">${nm(n.league)} · ${commandEsc(n.source||'')}${n.published?' · '+ago(n.published):''}</div></a>`).join('');

  const target=$('#view-outlook')||$('main.wrap');
  if(target){ target.classList.remove('hidden'); target.innerHTML=`<div class="ed-wrap">
    ${lead?`<div class="ed-lead"><a href="?league=${lead.league}"><div class="ed-kicker">${lead.kicker} · updated ${H.generated}</div><h1>${lead.h}</h1><div class="deck">${lead.deck}</div></a></div>`:''}
    <div class="ed-grid">
      <div><div class="ed-sec">More movement</div><div class="ed-cols">${stories.slice(0,6).map(story).join('')}</div></div>
      <div class="ed-vrule"></div>
      <div>
        <div class="ed-sec">The Models</div>${models}
        <div class="ed-sec">Upcoming Matches</div>${fixtures}
      </div>
    </div>
    <div class="ed-sec">Around the Leagues</div><div class="ed-newsband">${news||'<div class="news-empty">No headlines yet.</div>'}</div>
  </div>`; }
}
```

- [ ] **Step 3: Verify in browser**

Home route at 1280px: serif lead headline from the biggest mover, rules-not-cards, right rail with 6 model rows and fixtures (or empty state), news band 3-up. 375px: single column, lead 28px, bottom nav visible. Console clean. Old `.hm-*`/`.cc-hero` CSS becomes dead for the home route — leave the CSS (edge-board/`cc-*` classes are shared), but delete now-unused `.hm-lead*`/`.hm-race*`/`.hm-mover*` rules if nothing else references them (grep first).

- [ ] **Step 4: Commit**

```bash
git add webapp/index.html
git commit -m "feat(home): NYT-style editorial homepage — auto-written headlines, models rail, fixtures"
```

---

### Task 5: Leagues index route (`?league=leagues`)

**Files:**
- Modify: `webapp/index.html` — add a route block after the `_isHome` block; CSS appended to the masthead section

- [ ] **Step 1: CSS**

```css
/* ── Leagues index page (sidebar's successor) ── */
.lx-grp{font-family:var(--serif);font-size:17px;font-weight:700;border-bottom:1px solid var(--line-3);padding:var(--s4) 0 6px;margin-bottom:2px}
.lx-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:2px 20px}
.lx-lg{display:flex;align-items:center;gap:9px;padding:9px 4px;font-size:13.5px;color:var(--txt-2);text-decoration:none;border-bottom:1px solid var(--line)}
.lx-lg:hover{color:var(--txt-1);background:var(--ink-1)}
.lx-lg img{width:20px;height:20px;object-fit:contain;flex:none}
.lx-lg .soon-tag{font-size:8px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;color:var(--txt-3);border:1px solid var(--line-2);border-radius:4px;padding:1px 4px}
.lx-star{margin-left:auto;color:var(--txt-3);font-size:15px;cursor:pointer;padding:2px 4px}
.lx-star.on,.lx-star:hover{color:#e2b04f}
```

- [ ] **Step 2: Route block (insert right after the `_isHome` block)**

```js
// ── Leagues index (?league=leagues): the sidebar's successor, grouped by country ──
if(_isLeagues){
  const seg=$('#seg'); if(seg) seg.style.display='none';
  const hd=document.querySelector('header'); if(hd) hd.style.display='none';
  document.querySelectorAll('main.wrap > section').forEach(s=>{ if(s.id!=='view-outlook') s.classList.add('hidden'); });
  document.title="Leagues · Entenser";
  const GROUP_ORDER=[['England','🏴󠁧󠁢󠁥󠁮󠁧󠁿'],['Spain','🇪🇸'],['Italy','🇮🇹'],['Germany','🇩🇪'],['France','🇫🇷'],
    ['Americas','🌎'],['South America','🇧🇷'],['Other Europe','🇪🇺'],['Asia','🌏'],['Cups','🏆'],['Women','⚽']];
  const groups={};
  (window.LEAGUES||[]).forEach(l=>{(groups[l.group||'Other Europe']=groups[l.group||'Other Europe']||[]).push(l);});
  const render=()=>{
    const favs=FavStore.leagues();
    const link=l=>`<a class="lx-lg" href="?league=${l.id}">${l.logo?`<img src="${l.logo}" alt="" onerror="this.remove()">`:''}<span>${l.name}</span>${l.status!=='live'?'<span class="soon-tag">soon</span>':''}<span class="lx-star${favs.has(l.id)?' on':''}" data-lid="${l.id}">${favs.has(l.id)?'★':'☆'}</span></a>`;
    const favLg=(window.LEAGUES||[]).filter(l=>favs.has(l.id));
    let html='<div class="ed-wrap">';
    if(favLg.length) html+=`<div class="lx-grp">★ Favorites</div><div class="lx-grid">${favLg.map(link).join('')}</div>`;
    GROUP_ORDER.forEach(([g,flag])=>{ if(!groups[g]||!groups[g].length) return;
      html+=`<div class="lx-grp">${flag} ${g==='Other Europe'?'Europe':g}</div><div class="lx-grid">${groups[g].map(link).join('')}</div>`;});
    html+='</div>';
    const target=$('#view-outlook'); if(!target) return;
    target.classList.remove('hidden'); target.innerHTML=html;
    target.querySelectorAll('.lx-star').forEach(s=>s.onclick=e=>{e.preventDefault();e.stopPropagation();FavStore.toggleLeague(s.dataset.lid);render();});
  };
  render();
  const _fl=$('#foot'); if(_fl && !_fl.innerHTML.trim()) _fl.innerHTML=FOOT_HTML;
}
```

- [ ] **Step 3: Verify + commit**

Browser: `?league=leagues` shows all 11 groups with flags; star pin toggles persist across reload (localStorage `pitchside.favLeagues`); links navigate. Then:

```bash
git add webapp/index.html
git commit -m "feat(leagues): full-page league index with country groups and pin stars"
```

---

### Task 6: Favorites route (`?league=favorites`) + team-pin star

**Files:**
- Modify: `webapp/index.html` — route block after the Leagues block; team profile header (line ~2431); CSS

- [ ] **Step 1: CSS**

```css
/* ── Favorites page ── */
.fv-empty{padding:var(--s5) 0;color:var(--txt-2);font-size:14px}
.fv-empty a{color:var(--txt-1)}
.fv-card{display:flex;align-items:center;gap:10px;padding:11px 4px;border-bottom:1px solid var(--line);text-decoration:none;color:inherit;font-size:13.5px;flex-wrap:wrap}
.fv-card:hover{background:var(--ink-1)}
.fv-card img{width:19px;height:19px;object-fit:contain}
.fv-card .lg{color:var(--txt-3);font-size:11px;text-transform:uppercase;letter-spacing:.03em;width:150px;flex:none}
.fv-card b{font-family:var(--mono)}
.fv-card .sub{color:var(--txt-3);font-size:11.5px;width:100%;padding-left:160px}
.fv-unpin{margin-left:auto;color:#e2b04f;cursor:pointer;font-size:15px;padding:2px 6px}
.prof-hd .fav-team-star{margin-left:auto;font-size:22px;color:var(--txt-3);cursor:pointer;align-self:center}
.prof-hd .fav-team-star.on{color:#e2b04f}
@media(max-width:900px){.fv-card .sub{padding-left:0}}
```

- [ ] **Step 2: Favorites route block (insert after the Leagues block)**

```js
// ── Favorites (?league=favorites): pinned leagues (HOME_DATA snapshot) + pinned teams
//    (lazy per-league data loads; a failed load degrades to a "data unavailable" row) ──
if(_isFavs){
  const seg=$('#seg'); if(seg) seg.style.display='none';
  const hd=document.querySelector('header'); if(hd) hd.style.display='none';
  document.querySelectorAll('main.wrap > section').forEach(s=>{ if(s.id!=='view-outlook') s.classList.add('hidden'); });
  document.title="Favorites · Entenser";
  const H=window.HOME_DATA||{};
  const nm=id=>{const l=(window.LEAGUES||[]).find(x=>x.id===id);return l?l.name:id;};
  const target=$('#view-outlook');
  const favLg=[...FavStore.leagues()], favTm=FavStore.teams();
  const loadLeague=lid=>new Promise(res=>{const s=document.createElement('script');
    s.src=`data/${lid}.js?t=${Date.now()}`;s.async=false;
    s.onload=()=>res(window.LEAGUE_DATA);s.onerror=()=>res(null);document.head.appendChild(s);});
  const leagueRow=lid=>{const l=(H.leaders||[]).find(x=>x.league===lid);
    return `<a class="fv-card" href="?league=${lid}"><span class="lg">${nm(lid)}</span>${l?`${crest(l.team,l.logo)}<span>${l.team}</span><b>${l.pct}%</b><span style="color:var(--txt-3);font-size:11px">${l.metric_label}</span>`:'<span style="color:var(--txt-3)">open league page</span>'}</a>`;};
  const render=async()=>{
    if(!target) return;
    target.classList.remove('hidden');
    if(!favLg.length&&!favTm.length){
      target.innerHTML=`<div class="ed-wrap"><div class="ed-sec">★ Favorites</div>
        <div class="fv-empty">Nothing pinned yet. Star a league on the <a href="?league=leagues">Leagues page</a>, or star a club from its team profile, and it will live here.</div></div>`;
      return;
    }
    let html='<div class="ed-wrap">';
    if(favLg.length) html+=`<div class="ed-sec">★ Leagues</div>${favLg.map(leagueRow).join('')}`;
    html+=favTm.length?`<div class="ed-sec">★ Clubs</div><div id="fvTeams"><div class="fv-empty">Loading club data…</div></div>`:'';
    html+='</div>';
    target.innerHTML=html;
    if(!favTm.length) return;
    // group pinned teams by league; load each league file once, serially (each sets window.LEAGUE_DATA)
    const byLg={}; favTm.forEach(t=>{(byLg[t.league]=byLg[t.league]||[]).push(t.team);});
    let rows='';
    for(const lid of Object.keys(byLg)){
      const d=await loadLeague(lid);
      for(const team of byLg[lid]){
        const unpin=`<span class="fv-unpin" data-lg="${lid}" data-team="${commandEsc(team)}" title="Unpin">★</span>`;
        const st=d&&(d.standings||[]).find(s=>s.team===team);
        if(!st){rows+=`<div class="fv-card"><span class="lg">${nm(lid)}</span><span>${commandEsc(team)}</span><span style="color:var(--txt-3)">data unavailable</span>${unpin}</div>`;continue;}
        const metric=(((d.outlook||{}).cards||[])[0])||null;
        const next=(d.games||[]).filter(g=>g.result==null&&(g.home===team||g.away===team))
          .sort((a,b)=>(a.date<b.date?-1:1))[0];
        const nx=next?`next: ${next.home===team?'vs '+next.away:'@ '+next.home} ${next.date} · model ${Math.round((next.home===team?next.pH:next.pA)*100)}% win`:'no upcoming fixture';
        rows+=`<a class="fv-card" href="?league=${lid}">${crest(team,st.logo)}<span class="lg">${nm(lid)}</span><span>${team}</span>
          ${metric?`<b>${(+st[metric.key]||0).toFixed(1)}%</b><span style="color:var(--txt-3);font-size:11px">${metric.label}</span>`:''}${unpin}
          <span class="sub">proj. #${st.proj_rank} · ${nx}</span></a>`;
      }
    }
    const box=$('#fvTeams'); if(box) box.innerHTML=rows;
    target.querySelectorAll('.fv-unpin').forEach(u=>u.onclick=e=>{e.preventDefault();e.stopPropagation();
      FavStore.toggleTeam(u.dataset.lg,u.dataset.team);location.reload();});
  };
  render();
  const _ff=$('#foot'); if(_ff && !_ff.innerHTML.trim()) _ff.innerHTML=FOOT_HTML;
}
```

- [ ] **Step 3: Team-pin star on the profile header**

In the `$('#teamProfile').innerHTML=` assignment (line ~2431), change the `prof-hd` line to append a star before the closing `</div>`:

```js
`<div class="prof-hd">${crest(team,s.logo)}<div><h2>${team}</h2><div class="sub">${placeLabel} · ELO ${inp.elo??'—'} · ${troph.length} trophies</div></div><span class="fav-team-star${FavStore.hasTeam(LID,team)?' on':''}" id="favTeamStar" title="Pin to Favorites">${FavStore.hasTeam(LID,team)?'★':'☆'}</span></div>`
```

and immediately after the `fillClubNews(team);` call add:

```js
const _fts=$('#favTeamStar'); if(_fts) _fts.onclick=()=>{const on=FavStore.toggleTeam(LID,team);_fts.classList.toggle('on',on);_fts.textContent=on?'★':'☆';};
```

- [ ] **Step 4: Verify + commit**

Browser: pin a league on `?league=leagues`, pin a club from `?league=epl` → Teams → click a team → star; open `?league=favorites` → both appear, club row shows projection + next fixture; unpin star works; empty state renders after unpinning everything. Then:

```bash
git add webapp/index.html
git commit -m "feat(favorites): favorites page for pinned leagues + clubs, team-pin star on profiles"
```

---

### Task 7: Full verification + docs

- [ ] **Step 1: Cross-route regression sweep in the browser preview**

Desktop 1280px and mobile 375px, console clean and no horizontal scroll on each:
`/` (home), `?league=epl` (table league), `?league=mls` (conference league), `?league=command`, `?league=power`, `?league=leagues`, `?league=favorites`, `?league=about`.

- [ ] **Step 2: Run the Python test suite**

Run: `python -m pytest tests/ -x -q` — expected: all pass (only `build_home.py` changed on the Python side).

- [ ] **Step 3: Docs per CLAUDE.md convention**

- Append verdicts to this plan file per task.
- Add a blockquote entry to the top of `docs/PLAN.md` (feature add: NYT editorial redesign).
- On completion: 2-3 sentence dated entry in `docs/PROJECT_HISTORY.md`, then delete this plan file and the spec's job is done.

- [ ] **Step 4: Final commit**

```bash
git add docs/
git commit -m "docs: NYT editorial redesign — plan verdicts, PLAN.md changelog"
```
