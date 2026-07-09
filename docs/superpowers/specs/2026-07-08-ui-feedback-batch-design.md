# UI Feedback Batch — Design

Source: user QA pass on the live dashboard (desktop + mobile), 2026-07-08. Seven independent
workstreams; sequencing below is the intended execution order.

## 1. Bug fixes & data correctness
- **Odds decimal formatting**: in the league table's Title/UCL/Europa/Conf/Releg columns, any
  value `>0 and <1` renders with one decimal (`.toFixed(1)`) instead of rounding down to `0`.
- **EPL projected-finish bug** (Tottenham 12th in standings, 17th in projected finish): root cause
  not yet confirmed. Leading theory is a name-based join mismatch between `D.standings` and the
  simulation output (`runSimTable()`). Diagnose and fix during implementation.
- **Missing logos**: full audit — cross-reference every team name across all 35
  `webapp/data/*.js` files against `webapp/data/logos.js`, fill every gap. West Ham confirmed
  missing; audit will surface the rest (Lincoln City is present in the mapping, contrary to the
  original report — the underlying issue may be a broken/stale URL rather than a missing key).

## 2. Rebrand — "Entenser"
- Assets: `docs/logo1.PNG` (horizontal wordmark: moose head + "Entenser" text) and
  `docs/logo2.PNG` (standalone moose-head icon). Both are flat RGB, opaque near-white background,
  no alpha channel.
- Matte the white background to transparency via threshold-based alpha extraction (flat
  navy/white art, no gradients — safe to chroma-key). Save processed copies to
  `webapp/assets/branding/`.
- Touch points: `<title>` (currently "MLS Projections"), sidebar brand text (currently
  "Pitchside"), page header, and a new favicon generated from the icon (none exists today).

## 3. MLS top boxes — 5-card layout
Every team record in `webapp/data/mls.js` already carries independent per-team percentages:
`shield`, `conf_win`, `cup`, `spoon`, plus a `conf` field (`"East"`/`"West"`). No new modeling or
data computation — extend `outlook.cards` from 3 entries to 5:
1. **MLS Cup** (existing) — highest `cup` league-wide
2. **Supporters Shield** (existing) — highest `shield` league-wide (best overall record,
   independent of conference — stays a standalone percentage even when the Shield leader is also
   a conference leader)
3. **Eastern Conference Winner** (new) — highest `conf_win` among `conf=="East"`
4. **Western Conference Winner** (new) — highest `conf_win` among `conf=="West"`
5. **Wooden Spoon** (new) — highest `spoon` league-wide (worst team)

## 4. Squad value panel
- Un-collapse the panel on the team page — value shows immediately, no click required.
- Add a position-group breakdown row: Attack / Midfield / Defense / GK, as % of squad value.
- `scripts/import_transfermarkt.py` already buckets players into ATT/MID/DEF/GK internally
  (`_pos_group`) but `_aggregate_team()` only emits ATT/DEF/GK — midfield value isn't reported as
  its own column today. Extend `_aggregate_team()` to emit `mid_value_pct` / `n_mid`, then
  regenerate the Eredivisie (NL1) pilot CSV (`data/transfermarkt_squad_values_NL1_2026_mapped.csv`).
- MLS already ships full player-level rows — compute its 4-way breakdown client-side from existing
  data, no pipeline change needed.
- Scope for this pass: MLS + Eredivisie only. Every other league keeps the existing
  squad-value-total treatment with no breakdown row, until a follow-up project extends the
  transfermarkt import league-by-league (see Deferred, below).

## 5. Logo contrast fix
Same transparency-matting technique as the rebrand assets, applied to the general "dark crest on
dark background" problem (e.g. Tottenham). Wrap crest `<img>` in a small light rounded plate
(subtle off-white circle/chip behind the logo) via the existing `.crest` component — a CSS/markup
change, not per-team special-casing.

## 6. Mobile
- Revert the 620px rule that hides team names in league tables (`.ladder .tcol{display:none}`) —
  bring the name back alongside a larger crest.
- Move "Next 5" beside the team row (matching desktop grid) instead of the current
  wrap-below-with-dashed-border behavior at the 760px breakpoint; use horizontal scroll if it
  overflows.

## 7. Navigation
- Rename the "Today's Edge" sidebar entry (`_isEdgeBoard` route, currently loads
  `data/edge-board.js`) and its page title to "Matches". Restructure its rendering to group
  upcoming fixtures by date, then by league, instead of the current edge-sorted list.
- Add a "News" tab as an empty stub, wired into the existing tab bar alongside Projections /
  Matches / Teams / Health.
- Add a "model last run: {date}" label near the Model/Market/Naive comparison header, sourced from
  the `generated` timestamp already present in each league payload.

## Explicitly out of scope for this pass
- **Canadian Premier League**: confirmed no working ESPN data feed exists (`espn_code: null`;
  `can.1` returns 404/400/500 across teams/scoreboard/standings endpoints). Leave the "soon"
  placeholder exactly as-is. No code change.
- **Comprehensive trophy history for all 28 leagues/teams**: today only MLS has full trophy data.
  Building this out for every league is a data-sourcing project (which competitions, how far back,
  what source) — deferred to a dedicated follow-up plan, not folded into this batch.
- **Squad-value breakdown for leagues beyond MLS/Eredivisie**: requires running the transfermarkt
  import per league — same follow-up deferral as trophies.

Both deferred items are captured for a future planning pass so the scoping conversation already
had (2026-07-08) isn't lost.
