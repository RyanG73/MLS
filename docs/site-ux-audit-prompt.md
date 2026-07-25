# Entenser Full Site UX Review — Mobile & Desktop

> A complete, from-scratch review of the Entenser interface across every surface, at every
> breakpoint, on both Chromium and real iOS WebKit. Treat every surface as **unreviewed**. Prior
> review notes elsewhere in `docs/` are out of scope — do not read them for verdicts, do not
> inherit their conclusions, do not skip a surface because something claims it was done. Find it
> yourself, measure it yourself.
>
> This prompt covers **the interface**. `docs/league-qa-audit-prompt.md` covers **data
> correctness** league by league. If a probability looks wrong, note it and hand it there.

---

## Role & objective

You are reviewing the interface of Entenser, a market-blind football forecasting site, on mobile
and desktop. For every surface you answer three questions in this order, and you handle each
answer differently:

| Class | Question | What you do |
|---|---|---|
| **Bug** | Is it broken? | **Fix it.** Console errors, silent render aborts, overflow, dead controls, wrong state, iOS-only breakage. |
| **Violation** | Does it obey the design contract? | **Fix it and cite the clause** from `.interface-design/system.md`. |
| **Suggestion** | Could it be better than the contract requires? | **Write it down. Do not ship it.** |

That split is the discipline of this review. A pass that quietly redesigns the header while
"fixing bugs" has failed, no matter how good the header looks. Structural change — new routes,
moved navigation, changed information architecture, altered product promise — is **always a
proposal**, never a unilateral edit.

Work **one surface at a time**, completely, across all viewports, before moving on. Do not
batch-skim the site and then write everything up at the end; findings decay and you will conflate
surfaces.

---

## The three lenses

### Lens 1 — production in the browser pane (where numbers come from)

Chromium with full DOM access. Every numeric claim in your report originates here.

```
preview_start  {url: "https://entenser.com"}
```

No dev server, no build. Then `read_page`, `javascript_tool`, `read_console_messages`,
`read_network_requests`, `resize_window`.

### Lens 2 — production in the iOS Simulator (where truth comes from)

Real WebKit on a real iOS shell. Xcode is installed and a simulator is normally already booted
(verified 2026-07-24: iOS 18.6, iPhone 16 Pro Max booted).

```bash
xcrun simctl list devices available
```

Drive it with `mcp__Claude_Code_iOS_Simulator__control`:

1. **`attach` first**, before anything else — opens the live panel so the user can watch.
2. **`open_url` `https://entenser.com`** — Mobile Safari in the simulator has ordinary internet
   access, so you browse the live site directly. Nothing local required.
3. `screenshot`, `tap`, `swipe`, `touch_path`, `text` to observe and interact.

Cover at minimum:

| Device | Why |
|---|---|
| **iPhone 16 Pro Max** | large phone, Dynamic Island, home indicator |
| **iPhone 16e** | small phone, tightest real viewport |
| **iPad Pro 11-inch** | the site has no tablet breakpoint — confirm what that actually looks like |

Also test **landscape** on at least one phone, and the **PWA installed** mode (Add to Home
Screen → launch standalone).

### Lens 3 — localhost (where fixes happen)

```
preview_start  {name: "webapp"}      →  http://localhost:8123
```

From `.claude/launch.json`. Never start a dev server with Bash. The simulator shares the host
network, so `http://localhost:8123` is reachable from Mobile Safari there too.

Signed-in **Intel** requires this lens: `./scripts/intel_preview.sh` restarts the API and prints
a **one-time** magic link (1-hour session; tokens are single-use, so a lost session needs a fresh
run — revisiting an old URL can never work). `./scripts/intel_preview.sh free` seeds a free
account so you can review the **gated** view. Review both paid and gated states.

### How the lenses relate

- **Discover on production** (lenses 1 and 2). It costs nothing to load and guarantees every
  finding is real rather than a local artifact.
- **Fix on localhost** (lens 3), then re-verify in both the pane and the simulator.
- **If a finding appears on production but not localhost**, local work already fixed it — check
  `git log` and `git status` before "fixing" it again.
- **If it appears on localhost but not production**, you probably just introduced it.
- **When Chromium and WebKit disagree, WebKit wins.** That is what iPhone users get.
- **Production is read-only.** Browse freely; never submit forms, never start a Stripe checkout,
  never create an account, never hit admin endpoints against the live site. Those flows get
  exercised on localhost with a seeded account.

---

## Methodology — measure, do not eyeball

**Screenshots of this app lie.** League tables and data payloads render asynchronously, so a
capture taken at paint time can place a section hundreds of pixels from where it settles. Never
derive a number from a picture.

**Take every measurement twice, ~2 seconds apart, and only trust stable values.** If two reads
disagree, the page is still rendering — wait and read again.

The simulator gives you pixels and taps, no DOM. So numbers come from the pane; the simulator
tells you whether it *renders*, *scrolls*, and *responds* correctly. If you need a WebKit-only
number (safe-area inset size, `vh` vs `dvh` resolution), reproduce the surface on localhost and
temporarily render the measurement into visible page text — a throwaway `?debug=metrics` block —
then screenshot that. Remove the scaffold before committing.

### Measurement snippets

Paste into `javascript_tool`. All six were run against production on 2026-07-24 and return clean
output — if one throws, the page changed, so fix the snippet rather than working around it.

**Horizontal overflow + offenders.** Elements inside a horizontally scrolling container are
*allowed* to exceed the viewport, so they are excluded — without that filter this returns dozens
of false positives from the fixture strip.

```js
(() => {
  const inScroller = e => { let n = e.parentElement;
    while (n && n !== document.body) { const ox = getComputedStyle(n).overflowX;
      if (ox === 'auto' || ox === 'scroll') return true; n = n.parentElement; } return false; };
  const off = [...document.querySelectorAll('*')]
    .filter(e => e.getBoundingClientRect().right > innerWidth + 1 && !inScroller(e))
    .map(e => (e.tagName + '.' + e.className).slice(0, 60));
  return { docW: document.documentElement.scrollWidth, winW: innerWidth,
           overflow: document.documentElement.scrollWidth > innerWidth,
           pageOffenders: off.slice(0, 12), total: off.length };
})()
```

**Type floor (elements under 11px)**

```js
(() => { const m = {};
  document.querySelectorAll('*').forEach(e => {
    if (!e.offsetParent) return;
    if (![...e.childNodes].some(n => n.nodeType === 3 && n.textContent.trim())) return;
    const fs = parseFloat(getComputedStyle(e).fontSize);
    if (fs < 11) { const k = (e.className || e.tagName) + ' @' + fs.toFixed(1) + 'px';
                   m[k] = (m[k] || 0) + 1; } });
  return { total: Object.values(m).reduce((a, b) => a + b, 0),
           byClass: Object.entries(m).sort((a, b) => b[1] - a[1]).slice(0, 20) }; })()
```

**Tap targets under 44px**

```js
(() => { const sel = 'a,button,input,select,textarea,[role=button],[onclick],[tabindex]';
  const bad = [...document.querySelectorAll(sel)].filter(e => { const r = e.getBoundingClientRect();
    return r.width && r.height && (r.width < 44 || r.height < 44); })
    .map(e => { const r = e.getBoundingClientRect();
      return { el: (e.tagName + '.' + e.className).slice(0, 50), w: Math.round(r.width),
               h: Math.round(r.height), txt: (e.textContent || '').trim().slice(0, 24) }; });
  return { count: bad.length, sample: bad.slice(0, 20) }; })()
```

**AA contrast failures, grouped by colour pair**

```js
(() => {
  const lum = c => { const [r,g,b] = c.match(/[\d.]+/g).map(Number).map(v => { v /= 255;
    return v <= .03928 ? v / 12.92 : ((v + .055) / 1.055) ** 2.4; });
    return .2126*r + .7152*g + .0722*b; };
  const bgOf = e => { let n = e; while (n) { const c = getComputedStyle(n).backgroundColor;
    if (c && !/rgba\(0, 0, 0, 0\)|transparent/.test(c)) return c; n = n.parentElement; }
    return 'rgb(0, 0, 0)'; };
  const out = [];
  document.querySelectorAll('*').forEach(e => {
    if (!e.offsetParent) return;
    if (![...e.childNodes].some(n => n.nodeType === 3 && n.textContent.trim())) return;
    const s = getComputedStyle(e), bg = bgOf(e);
    const L1 = lum(s.color), L2 = lum(bg);
    const ratio = (Math.max(L1,L2) + .05) / (Math.min(L1,L2) + .05);
    const fs = parseFloat(s.fontSize), bold = parseInt(s.fontWeight) >= 700;
    const need = (fs >= 24 || (fs >= 18.66 && bold)) ? 3 : 4.5;
    if (ratio < need) out.push({ el: (e.tagName + '.' + e.className).slice(0, 50),
      ratio: +ratio.toFixed(2), need, fs, pair: s.color + ' on ' + bg }); });
  const byPair = {}; out.forEach(o => byPair[o.pair] = (byPair[o.pair] || 0) + 1);
  return { failures: out.length,
           byPair: Object.entries(byPair).sort((a,b) => b[1]-a[1]).slice(0, 15),
           sample: out.slice(0, 10) }; })()
```

Group failures **by colour pair**, not by element. A single token change can lift hundreds of
elements at once; 200 individual overrides is the wrong fix for the same problem. When this ran on
production Home at 375px it returned **175 failures across just 5 pairs, 172 of them one token** —
that ratio is the norm here, so always fix at the pair level and re-run.

*Known limitation:* `bgOf` returns the first non-transparent background it finds and does not
composite alpha. A semi-transparent background (`rgba(61, 220, 132, 0.1)`) is measured as if
opaque, so those rows are approximate — verify any alpha-background failure by hand before
"fixing" it.

**Section offsets (layout order).** The `height > 20` filter is required: unrendered and
zero-height nodes all report `y: 0` and otherwise crowd the real sections out of the list.

```js
[...document.querySelectorAll('[class*=hx-], section, .card, h1, h2')]
  .filter(e => e.offsetParent && e.getBoundingClientRect().height > 20)
  .map(e => ({ el: (e.className || e.tagName).slice(0, 40),
               y: Math.round(e.getBoundingClientRect().top + scrollY),
               h: Math.round(e.getBoundingClientRect().height) }))
  .sort((a, b) => a.y - b.y).slice(0, 30)
```

**Numeric text not in the mono face**

```js
(() => { const bad = [];
  document.querySelectorAll('*').forEach(e => {
    if (!e.offsetParent) return;
    const t = [...e.childNodes].filter(n => n.nodeType === 3).map(n => n.textContent).join('').trim();
    if (!t || !/^[\d\s.,%+\-–:/]+$/.test(t) || t.length < 2) return;
    const ff = getComputedStyle(e).fontFamily;
    if (!/mono/i.test(ff)) bad.push({ el: (e.className || e.tagName).slice(0, 40),
                                      txt: t.slice(0, 16), font: ff.split(',')[0] }); });
  return { count: bad.length, sample: bad.slice(0, 20) }; })()
```

---

## Surfaces to review

The SPA is one authored file, `webapp/index.html` (~352 KB), routed by `?league=`. Every path
below resolves against either origin — prepend `https://entenser.com` or `http://localhost:8123`.

| # | Surface | Path | Notes |
|---|---|---|---|
| 1 | Home | `/` | the front page; editorial hierarchy |
| 2 | Matches / edge board | `?league=command` | `_isEdgeBoard`; no-line and neutral states live here |
| 3 | Leagues index | `?league=leagues` | grouped by country, flags, pin stars |
| 4 | League detail — major | `?league=epl` | densest surface: table + fixtures + sim + news |
| 5 | League detail — MLS | `?league=mls` | conference split; different table shape |
| 6 | League detail — cup | `?league=libertadores` | two-legged ties, group→knockout phases |
| 7 | League detail — results-only | `?league=poland-ekstraklasa` | must show the data-status note, not a forecast |
| 8 | Team view | `?league=epl&team=Arsenal` | deep-link target |
| 9 | Rankings | `?league=power` | `_isPower` |
| 10 | Intel — paid | `?league=intel` | needs `intel_preview.sh` (creator plan) |
| 11 | Intel — gated | `?league=intel` | needs `intel_preview.sh free` |
| 12 | Account | `?league=account` | |
| 13 | Support / waitlist | `?league=support` | `bindWaitlist()`; form — localhost only |
| 14 | Static league page | `/leagues/epl/` | **generated** SEO page |
| 15 | Static content | `/weekly/`, `/open-data/`, `/after-the-world-cup/` | **generated** |
| 16 | 404 | any unknown league | |
| 17 | PWA installed | Add to Home Screen → launch | simulator only |

### Breakpoint ladder

Run every surface at these widths in the pane. Mobile and desktop are both in full scope; the
in-between widths are where undiscovered breakage usually lives, because the site was built
mobile-first and desktop-first with little attention to the middle.

| Width × height | Represents | Priority |
|---|---|---|
| 320 × 568 | smallest phone still in use | check overflow only |
| **375 × 812** | **primary mobile target** | full checklist |
| 414 × 896 | large phone | full checklist |
| 768 × 1024 | tablet portrait — **no breakpoint exists here** | full checklist |
| 1024 × 768 | tablet landscape / small laptop | full checklist |
| **1280 × 800** | **primary desktop target** | full checklist |
| 1440 × 900 | common laptop | layout only |
| 1920 × 1080 | large monitor — check for max-width and line-length blowout | layout only |

Desktop is **not** "mobile with more room." The grid is defined separately, so a mobile fix
implies nothing about desktop and vice versa. Verify both.

---

## The design contract

`.interface-design/system.md` is the contract. **Read it in full before your first finding.** The
clauses you will be checking against:

- **Direction:** dense, auditable, fast, calm — a football probability command center. Lead with
  probability movement, model trust, race fragility, market-line status. Not generic dashboard
  decoration.
- **Palette:** dark quant-terminal. Canvas near-black; low-contrast chalk-line borders; floodlit
  pitch green for *validated signal or qualification only*; bookmaker-slip amber for priced edge
  or caution; restrained red for relegation/danger/errors; muted gray-blue for draw/no-line/
  neutral. Green must **not** broadly mean "profitable."
- **Depth:** borders-only plus subtle surface shifts. **No decorative shadows, no gradient orbs,
  no card-on-card.** Surfaces `--ink-0` (canvas) → `--ink-1` (panels) → `--ink-2` (panel headers,
  nested rows) → `--ink-3` (active/hover). Borders quiet: `--line`, `--line-2`, `--line-3`.
- **Typography:** `Archivo` for compact headings and high-emphasis numbers; `Inter` for body and
  interface text; `Spline Sans Mono` for probabilities, Brier values, odds, dates, aligned
  numeric metrics. **No hero-scale type inside cards or operational panels.**
- **Spacing:** 4px grid — `--s1` 4, `--s2` 8, `--s3` 12, `--s4` 16, `--s5` 24, `--s6` 36. Repeated
  card gaps 10–16px. Compact rows 7–10px vertical padding.
- **Mobile:** cards stack full-width; tables may scroll horizontally but **cards and headers must
  not clip**; header model status collapses to compact trust language; fixed-format rows and KPI
  cards use stable dimensions so content does not resize the layout.
- **Component patterns:** the landing page shows value even when odds are missing; "no line yet"
  reads neutral, not alarming; race cards sort by uncertainty or movement, not league hierarchy;
  match rows keep compact probability bars and suppress draw-side betting recommendations;
  expected scorelines and raw inputs live behind expansion; weak spots use human club names, not
  internal IDs; missing diagnostics are explicit chips, never hidden.
- **Copy:** lead with "Market-blind football probabilities, explained and audited." Never
  "guaranteed edge," never "picks" as the main promise, no profit claims without paper-ledger and
  CLV evidence. Prefer "model-market disagreement," "no line yet," "thin sample," "known weak
  spot," "diagnostics pending."

**The site is intentionally dark-only** — fixed palette, no `prefers-color-scheme`. Light mode is
not a gap; do not report it or build it.

Where the live site and the contract disagree, the contract is the reference **and** a candidate
for amendment: if the shipped behaviour is clearly better, say so and propose the doc change
rather than silently reverting the interface to the doc.

---

## Review checklist

Run every group on every surface. If a group is clean, **say so explicitly** — a silent group
reads as unchecked.

### A. Bugs

- [ ] **Console clean** on load, on route change, on interaction.
- [ ] **Silent render aborts.** A throw inside a render function can abort an entire page with
      *nothing* in the console. If a section is missing, suspect this before anything else. Check
      helper scope: functions that look global here may be module/IIFE-scoped.
- [ ] **HTML validity is load-bearing.** Layout is driven by `grid-area` classes on siblings, so
      one mismatched or unclosed tag collapses the grid and swallows following sections into one
      node. Validate the markup of any surface whose layout looks structurally wrong.
- [ ] **No horizontal page overflow** at any width: `documentElement.scrollWidth === innerWidth`.
      Tables may scroll inside their own container; the page body may not.
- [ ] **Network all 200:** lazy per-league payloads (news, drift-trajectory, momentum), logos and
      crests, CSV exports, fonts, icons. No 404 crests, no failed fetches, no mixed content.
- [ ] **Every control works:** buttons, toggles, pin stars, tabs, dropdowns, links. Specifically
      the odds-format toggle (US / Decimal / Fractional) must switch every price in place and
      persist across navigation.
- [ ] **Routing:** deep links load directly, back/forward behave, canonical swaps correctly on
      SPA routes (`?league=mls` → `/leagues/mls/`), unknown league → 404.
- [ ] **State correctness:** loading, empty, error, and gated states each render the right thing;
      `data_status` variants behave (`full_forecast` full output, `historical` backtest only,
      `results_only` no forecast widgets — a live projected table there is a bug).

### B. Layout & responsive

- [ ] **Information order:** volatile content first, reference second, ambient last. Measure real
      offsets; anything important below the fold on mobile is a finding.
- [ ] **Breakpoint ladder** clean at all eight widths — no orphaned columns, no 1-column desktop
      grid, no stretched-to-1920px line lengths, no tablet dead zone.
- [ ] **Cards and headers never clip** on mobile; tables scroll in-container with a visible
      affordance.
- [ ] **Stable dimensions:** fixed-format rows and KPI cards don't resize as data lands. Watch for
      layout shift between your two measurement reads.
- [ ] **Desktop-specific:** max content width sensible, right rail proportion holds, sticky
      elements don't overlap, no vast empty gutters, hover states exist and are discoverable.

### C. Typography

- [ ] **Type floor:** nothing under 11px. Report the count and the offending selectors.
- [ ] **Fonts by role:** numbers in `Spline Sans Mono`, headings in `Archivo`, body in `Inter`.
      Run the numeric-font snippet.
- [ ] **Numeric alignment:** columns of probabilities actually align; tabular figures where
      numbers stack.
- [ ] **No hero-scale type inside cards or operational panels.**
- [ ] **Scale coherence:** count the distinct font sizes on the surface. A surface using eleven
      sizes has no scale.
- [ ] **Line length and leading:** 45–90 characters at desktop; leading comfortable at both ends
      of the ladder.
- [ ] **Any font not named in the contract** is drift — report it with where it's used.

### D. Colour & contrast

- [ ] **AA everywhere:** ≥ 4.5:1 body, ≥ 3:1 large text. Run the contrast snippet and group by
      pair. Prefer one token fix over many local overrides.
- [ ] **Non-text contrast:** borders, focus rings, chart strokes, probability bars, icons ≥ 3:1
      against their background where they carry meaning.
- [ ] **Semantic colour:** green only for validated signal or qualification; amber for edge or
      caution; red restrained; neutral for draw and no-line.
- [ ] **Never colour alone** to convey meaning — pair with text, shape, or position.
- [ ] **Surface ladder used correctly** (`--ink-0` → `--ink-3`), no ad-hoc hex outside the tokens.

### E. Spacing & density

- [ ] **4px grid** respected; report off-grid values with selectors.
- [ ] **Card gaps 10–16px**; compact rows 7–10px vertical padding.
- [ ] **Consistent rhythm:** same component type has the same internal spacing everywhere.
- [ ] **Alignment:** shared left edges, no 1–3px misalignments between stacked sections.
- [ ] **Density appropriate to the surface:** dense is the goal, cramped is not.

### F. Interaction & states

- [ ] **All five states** for every interactive element: default, hover, focus, active, disabled.
- [ ] **Loading:** skeletons or explicit pending copy, never a bare flash of empty layout.
- [ ] **Empty:** says what's missing and why (a real contract clause — "no line yet" is neutral).
- [ ] **Error:** actionable, not a raw stack or a silent blank.
- [ ] **Tap/click targets ≥ 44px**; adequate spacing between adjacent targets.
- [ ] **Forms** (waitlist, any input): labels, validation, error placement, keyboard type,
      autocomplete, submit feedback. **Exercise on localhost only.**
- [ ] **Motion restrained** and `prefers-reduced-motion` respected.

### G. Accessibility

- [ ] **One `h1`**, valid heading outline, no level skips.
- [ ] **Landmarks:** `header`, `nav`, `main`, `footer` present and correct.
- [ ] **Keyboard:** every control reachable and operable, logical tab order, **visible focus
      ring**, no traps, skip-link to main.
- [ ] **Names:** `alt` on meaningful images and empty `alt` on decorative ones; accessible names
      on icon-only buttons; labels tied to inputs.
- [ ] **Custom controls** carry correct `role` / `aria-*` / state.
- [ ] **Tables:** `th` with `scope`, caption or accessible name.
- [ ] **Live regions** for content that updates without navigation.
- [ ] **Language** set on `html`; zoom to 200% without loss of content or function.

### H. Copy

- [ ] **Contract phrasing:** run the banned and preferred lists over every visible string.
- [ ] **Consistent terminology** for the same concept across surfaces — one name per thing.
- [ ] **Numbers labelled with units** and their meaning (per-mille vs percent, which season).
- [ ] **Dates and staleness honest:** "updated" reflects reality; stale reads as stale, not fresh.
- [ ] **Microcopy** carries the "explained and audited" posture rather than hype.
- [ ] **Typos, mojibake, unescaped entities** — accented club names must render correctly.

### I. Performance & delivery

- [ ] **Weight and requests** per surface; anything pathological for a static site.
- [ ] **Render-blocking resources**, font loading strategy, layout shift on load.
- [ ] **Service worker** (`entenser-shell-v*`) serves offline **without presenting stale data as
      fresh**.
- [ ] **Images:** dimensions set, no oversized crests, no layout shift as logos land.
- [ ] **Meta and social:** `<title>`, description, canonical, OG/Twitter tags per surface;
      JSON-LD valid where present.

### J. iOS / WebKit (Lens 2 — the reason the simulator is in scope)

- [ ] **Safe-area insets:** the fixed bottom tab bar clears the home indicator
      (`env(safe-area-inset-bottom)`); the masthead clears the Dynamic Island; landscape notch
      handled.
- [ ] **Viewport units:** Mobile Safari's `100vh` includes chrome that later retracts — anything
      full-height should use `dvh`/`svh`. Look for content jumping as the URL bar hides.
- [ ] **Input focus zoom:** any `input`/`select` with `font-size < 16px` makes iOS zoom the page
      on focus. Check every form field.
- [ ] **Scroll physics:** momentum and rubber-band on horizontally scrolling tables and strips;
      no scroll trapping; no nested-scroll fighting.
- [ ] **Sticky and fixed** survive rubber-band overscroll and an open keyboard.
- [ ] **Tap feedback:** no lingering `-webkit-tap-highlight-color` flash, no 300ms delay, no
      accidental double-tap zoom on controls, no text selection where a tap was intended.
- [ ] **`backdrop-filter`, blur, and blend modes** render as intended — WebKit differs from
      Chromium here.
- [ ] **PWA installed mode:** Add to Home Screen, launch standalone, verify manifest name and
      icons, status bar not overlapping content, navigation usable without browser chrome,
      offline behaviour honest.
- [ ] **Orientation:** landscape phone, and iPad where no tablet breakpoint exists.
- [ ] **Dynamic Type / larger accessibility text** doesn't destroy the layout.
- [ ] **Any Chromium/WebKit divergence** recorded explicitly — this is the highest-value output of
      the whole review.

### K. Cosmetic suggestions (document only — never ship in this pass)

Craft observations beyond the contract: visual rhythm, alignment refinement, density tuning,
iconography, empty-state personality, microcopy warmth, hierarchy of numeric display, chart
styling, restraint of animation, polish of the data-dense tables.

Write each as **observation → proposed change → why it's better → cost/risk**, and stop there.
The user decides.

---

## Workflow per surface

1. **Read the relevant contract clauses** in `.interface-design/system.md`.
2. **Lens 2, iPhone:** `attach`, `open_url` `https://entenser.com`, navigate to the surface as a
   user would. Screenshot. Work checklist **J** by actually tapping, scrolling, rotating.
3. **Lens 1, mobile 375×812 on production:** measure. Run all six snippets. Twice, 2s apart.
4. **Lens 1, the rest of the ladder:** 320, 414, 768, 1024, **1280**, 1440, 1920. Full checklist
   at the priority widths, layout/overflow at the others.
5. **Work checklists A–I** against what you measured, at both primary targets.
6. **Classify every finding** as bug / violation / suggestion.
7. **Lens 3:** start localhost, confirm each bug and violation reproduces there — if it does not,
   local work already fixed it, so check `git log`/`git status` before touching anything.
8. **Fix.** Bugs and clear violations only. Prefer token-level fixes: one variable that lifts
   every page beats forty local overrides. Trace anything in a generated file to its generator.
9. **Re-measure** in the pane *and* in the simulator. Record before/after. A fix with no measured
   delta is not a verified fix; a mobile fix is not verified until WebKit has seen it.
10. **Write the findings block.** Then next surface.

---

## Generated vs. authored — this decides how you fix

| Path | Status | How to fix |
|---|---|---|
| `webapp/index.html` | **authored** | edit directly — this is the SPA |
| `webapp/intelligence.css`, `intelligence.js`, `leagues.js`, `sim-engine.js` | **authored** | edit directly |
| `webapp/data/*.js` | generated | never hand-edit; fix the generator in `scripts/` |
| `webapp/leagues/*/index.html` | generated | fix `scripts/build_league_data.py` / `build_static_pages.py`, rebuild |
| `webapp/exports/*.csv` | generated | fix the generator |
| `webapp/weekly/*`, `open-data/`, `after-the-world-cup/` | generated | fix `scripts/build_*.py` |

Trace before fixing:

```bash
grep -rn "<the wrong string>" scripts/ config/ data_pipeline/ webapp/ --include=*.py --include=*.yaml --include=*.js
```

---

## Output format

### Per surface

```
### <n>. <Surface> — <path>
Verdict: CLEAN | ISSUES (n bugs, n violations, n suggestions)

Measured:
| metric | 375 | 768 | 1280 | 1920 | iOS |
|---|---|---|---|---|---|
| horizontal overflow      |  |  |  |  |  |
| console errors           |  |  |  |  |  |
| AA contrast failures     |  |  |  |  | n/a |
| elements < 11px          |  |  |  |  | n/a |
| tap targets < 44px       |  |  |  |  | n/a |
| distinct font sizes      |  |  |  |  | n/a |
| key section offsets      |  |  |  |  | n/a |

BUGS (fixed)
- <what broke> · root cause <file:line> · fix <what changed> · before → after <measurement>

VIOLATIONS (fixed)
- <clause quoted from system.md> · offender <selector, file:line> · fix · before → after

iOS/WebKit divergence
- <what WebKit does that Chromium did not show>

SUGGESTIONS (not shipped)
- observation → proposal → why better → cost

FLAGGED ELSEWHERE
- <data/odds issues → league-qa-audit-prompt.md; user decisions; contract amendments proposed>
```

### Final rollup, after every surface

- **Site-wide patterns** — one root cause showing up on many surfaces is the highest-value
  finding in the review. Lead with these.
- **Token-level opportunities** — single-variable changes with site-wide reach.
- **Contract drift table** — where the site and `system.md` disagree, and which one you think
  should change.
- **Prioritised suggestion list** — cosmetic proposals ranked by impact ÷ cost, for the user to
  approve or decline.
- **Coverage statement** — which surfaces × widths × devices you actually exercised, and anything
  you could not reach and why.

Every finding must be concrete. "Spacing feels off" is not a finding. "`.hx-scard` uses an 18px
gap — off the 4px grid and outside the 10–16px card-gap rule (`index.html:2841`); tightened to
12px, card height 214px → 198px, three more cards above the fold at 375px" is.

---

## Guardrails

- **Bugs: fix. Violations: fix and cite. Taste: propose.** Never silently reshape the product
  while reviewing it.
- **Ask before anything structural** — new routes, moved navigation, changed information
  architecture, removed features, altered product copy.
- **Never hand-edit generated files.** Fix the generator, rebuild.
- **Measure, never eyeball.** Read twice, trust stable values. WebKit wins ties.
- **Production is read-only.** No form submissions, no Stripe checkout, no account creation, no
  admin endpoints against the live site. Never try to edit production; fixes ship through the
  normal refresh/deploy pipeline.
- **One surface at a time**, all viewports, findings block complete, before the next.
- **`webapp/index.html` is one 352 KB file.** Surgical targeted edits only — never rewrite it
  wholesale, never reformat regions you aren't fixing.
- **Remove debug scaffolding** (`?debug=metrics`, temporary overlays) before committing.
- **Preserve the market-blind invariant:** no fix may introduce bookmaker odds as a model input.
  Displaying model-vs-market *edge* is a separate, allowed feature — don't conflate them.
- **Check for a concurrent session before committing:** `git log` plus running processes. Another
  session may be live in this repo and mid-edit on the same file.
- **Update docs** per `CLAUDE.md`: a plan file under `docs/superpowers/plans/` carrying the
  per-surface verdicts, and a blockquote entry at the top of `docs/PLAN.md` if behaviour changed.
- **Commit with clear messages; do not push unless asked.**

---

## Kick-off

Start with **Home (`/`)**, and start on the phone:

1. `attach` the iOS Simulator, `open_url` **`https://entenser.com`**, screenshot, and work
   checklist J with your thumbs.
2. `preview_start {url: "https://entenser.com"}` in the pane at 375×812, run all six measurement
   snippets twice, and record the baseline.
3. Walk the breakpoint ladder to 1280 and 1920.
4. Classify, then move to localhost to fix.

Then surfaces 2 through 17 in order. Report after each one; do not save it all for the end.
