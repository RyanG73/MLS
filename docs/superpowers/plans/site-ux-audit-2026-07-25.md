# Full site UX review — mobile & desktop (`docs/site-ux-audit-prompt.md`)

Run 2026-07-25. Three lenses: production in the Chromium pane, production in the iOS Simulator
(iPhone 16 Pro Max, iOS 18.6), fixes on `http://localhost:8123`. Every surface treated as
unreviewed; all numbers measured, read twice, never taken from a screenshot.

## Verdicts

### 1. Home — `/` · ISSUES (2 bugs, 5 violations) — fixed

| metric | before (375) | after |
|---|---|---|
| AA contrast failures | 175 | **0** |
| elements < 11px | 117 | 66 (all badge glyphs, 0 content) |
| distinct font sizes | 20 | 16 |
| search input | 12px / 28px tall | 16px / 44px |
| iOS focus zoom | **zooms, never restores** | none |

- **BUG — iOS focus zoom made the Account tab unreachable.** `.mast-search input{font-size:12px}`
  → Mobile Safari zooms any field under 16px on focus and does not zoom back on blur. The page
  stayed scaled past the viewport and the 5th bottom-nav destination was pushed off-screen.
  Chromium cannot surface this class of bug at all — it reported zero overflow at all eight widths.
  Fixed to 16px + `min-height:44px`; verified in WebKit that focus no longer changes layout.
- **VIOLATION — semantic colour.** `moversRow()` coloured on `delta` sign alone, so
  "FC Botosani · Relegation ▲100.0" rendered in qualification green while the hero showed the same
  datum in amber. Now keyed on valence (relegation inverts); arrow still tracks raw direction, so
  colour never carries the meaning alone.
- **VIOLATION — `--txt-3` failed AA on three of four surfaces.** The 2026-07-23 pass set `#6b7d71`
  and recorded "4.58:1 — clears WCAG AA", but measured it against `--ink-0` only. The token is used
  207× and almost always sits on a panel: 4.46 / 4.38 / 4.05 on `--ink-1/2/3`. **172 of 175 Home
  failures were this one token.** Now `#738579`, solved against the lightest surface it lands on →
  4.85 / 4.72 / 4.64 / 4.53. This single change took 11 of 12 routes to zero contrast failures.
- **VIOLATION — heading outline.** Six visible section headings were `<div class="ed-sec">`, so the
  outline ran H1 → H4 with nothing between. All 12 converted to `<h2>`. Skip-link added.
- **VIOLATION — type floor.** 117 elements under 11px; ten rules raised.

### 2. Matches / edge board — `?league=command` · ISSUES (2 violations) — fixed
- **Type floor 248 → 16**, the worst surface measured, and it was the core product numbers: 87 odds
  prices at 8.5–9px, 29 kickoff times, 29 draw probabilities, 75 calendar labels. Nine rules raised;
  verified `.drw`/`.ko` (both `white-space:nowrap` in a 313px card) do not clip.
- Contrast 197 → 0 via the token.
- **Clean:** console silent; odds-format toggle converts every price in place
  (`+232 → 3.32 → 37/16`) and persists; no banned copy.

### 3. Leagues index — `?league=leagues` · ISSUES (1 bug, 2 violations) — fixed
- **BUG — 78 pin stars were dead controls for keyboard users.** `.lx-star` is a `<span>` nested
  inside the league `<a>`; it mutates `pitchside.favLeagues` on click but had no `tabindex`/`role`
  and was not in the tab order, so tabbing to a row and pressing Enter navigated instead of pinning.
  There was no way to pin a league without a mouse. Now `role=button` + `tabindex=0` + `aria-pressed`
  + per-league `aria-label` + Enter/Space handler + focus ring. Verified all four behaviours.
- 44×44 hit area achieved with `margin-block:-10px` so the 78-row list keeps its density
  (row 48 → 50px, not 63px).
- Type floor 92 → 5.

### 4. League detail — `?league=epl` · ISSUES (2 violations) — fixed
- **Type floor 319 → 24** (100 form-box labels at 8px, 96 heat cells at 10px, 60 chips at 8.5px).
- **Table a11y + ID leakage:** the season-outcome table exposed raw internal metric keys as column
  headers (`conf`, `europa`, `releg`, `ucl`) and had no `scope` on any `th` and no accessible name.
  Now human labels via `OSK_LABEL`, `scope="col"`/`scope="row"`, `aria-labelledby`.
- Fixed a **pre-existing** clip: "Europa" needed 36px in a fixed 34px column; reclaimed via
  `letter-spacing:0` rather than truncating a competition name or widening every column.
- **Reverted two of my own bumps** (`.tlad .thead`, `.acc-lbl`) after measuring that 11px clipped
  inside fixed-width grid columns. Documented as constrained exceptions rather than shipped broken.
- Canonical correctly swaps to `/leagues/epl/`.

### 7. Results-only — `?league=poland-ekstraklasa` · CLEAN
`data_status: results_only` renders a settled final table, not a live forecast: Pts == Proj
(60|60, 56|56), 34 GP, outcome columns show settled `100`/`·` rather than forward probabilities,
and an explicit note reads "results only — no fixture feed for this league, projections use played
matches". Reading the column *names* alone would have produced a false finding; the values are what
confirmed it.

## Site-wide sweep after fixes (12 routes, 375px)

Contrast **0 on 11 of 12** (support: 1). No horizontal overflow on any route. Non-badge text under
11px remaining: `/` 0, command 0, leagues 0, epl 20, mls 56, libertadores 17, poland 16,
**power 299**, account 8, support 0, intel 31, 404 0.

## Open — needs a decision, deliberately not shipped

1. **Desktop buries volatile content.** At 1280×800 (fold y=800) reference tables own the first
   screen at y=461 while Upcoming Matches sits at y=1266 and Biggest Movers at y=1514. Mobile was
   already fixed for exactly this; desktop kept the old order. Reordering `grid-template-areas` is
   one line but it changes information architecture → proposal, not a unilateral edit.
2. **Tablet dead zone.** The only breakpoint is `max-width:900px`; 768–900px gets the mobile stack
   stretched to a ~880px single column.
3. **Type scale is systemically sub-floor.** 105 of 401 `font-size` declarations remain under 11px
   (39 at 10px, 19 at 10.5, 15 at 9…). Raising all of them is a type-scale change across 17
   surfaces that trades against the contract's "dense" direction — one decision, not 105.
4. **Contract drift** (amend `system.md`, not the site): Georgia serif carries the wordmark and all
   8 editorial headings but is not in the contract; 5 drop shadows on overlays vs "no decorative
   shadows" — both are the shipped behaviour being better than the doc.

## Not reached
Static pages (14, 15), 404 treatment beyond route probe, PWA installed mode (17), Intel paid/gated
(10, 11) — Intel needs `./scripts/intel_preview.sh`. Landscape and iPad WebKit not exercised.
