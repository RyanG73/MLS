# NYT-Style Dark Editorial Redesign — Design Spec

**Date:** 2026-07-11
**Status:** Approved by user (site-wide chrome · editorial serif · Favorites = leagues + teams)
**Reference:** Two user-supplied screenshots of The New York Times (desktop homepage + mobile app), both dark mode.

## Goal

Rework the Entenser webapp's navigation chrome and homepage to read like a dark-mode
newspaper front page: headline-driven hierarchy, a country/flag section bar along the top,
and a mobile bottom tab bar (Home · Matches · Leagues · Favorites). The left sidebar is
removed everywhere.

## Scope

All changes live in `webapp/index.html` (single-file SPA) plus one pipeline change in
`scripts/build_home.py`. League-page *content* is unchanged — only the chrome around it.

## 1. Site-wide chrome

**Desktop masthead (every route):**
- Row 1: today's date + "updated Xh ago" (left) · centered serif **Entenser** wordmark ·
  "44 leagues live" stat (right).
- Row 2 — country bar sourced from the `group` field in `webapp/leagues.js`:
  `🏠 Home · 🏴󠁧󠁢󠁥󠁮󠁧󠁿 England · 🇪🇸 Spain · 🇮🇹 Italy · 🇩🇪 Germany · 🇫🇷 France · 🌎 Americas ·
  🇧🇷 South America · 🇪🇺 Europe · 🌏 Asia · 🏆 Cups · ⚽ Women`.
  Hover (desktop) / tap (mobile) opens a dropdown listing that group's leagues with logos
  and live/soon status. Active group is underlined NYT-style. Double 1px rule below the bar.
- Row 3: slim "LIVE"-style strip — today's fixture count linking to `?league=command`.

**Mobile:**
- Country bar becomes a horizontally scrollable strip (NYT app pattern).
- Fixed bottom tab bar: **Home** (`?` none) · **Matches** (`?league=command`) ·
  **Leagues** (new `?league=leagues` index page) · **Favorites** (new `?league=favorites`).
- The `.sidebar` element, `#sbToggle` hamburger, and their CSS/JS are deleted.
  The Leagues index page (grouped by country, flags, pin stars) replaces the sidebar's
  full-list role on both desktop and mobile.

## 2. Homepage — editorial hierarchy

Replace the current hero + uniform card grid with:

- **Lead story:** auto-written headline from the largest projection swing (`H.movers`) or
  tightest race (`H.tight_races`) — e.g. "Southampton's Promotion Odds Jump 12 Points" —
  serif ~38px, one-sentence deck, kicker `LEAGUE · UPDATED 2H`, links to the league.
- **Main well (left ⅔):** 4–6 secondary auto-headlines from movers / tight races /
  relegation battles, separated by 1px rules, no card boxes. Headline templates are
  deterministic client-side functions of HOME_DATA (no LLM, no pipeline change).
- **Right rail (⅓):** "The Models" module — leader snapshots for EPL, La Liga, Serie A,
  Bundesliga, Ligue 1, MLS (title/playoff %); below it "Upcoming Matches" with model
  H/D/A probabilities.
- **Bottom band:** existing real news headlines (`H.news`) in NYT small-story style.

**Pipeline change:** `scripts/build_home.py` additionally emits
`fixtures: [{league, date, home, away, pH, pD, pA, logo_h, logo_a}]` — next ~48h across
the biggest live leagues (cap ~12), reading the same per-league JSON it already ingests.

## 3. Typography & tokens

- Serif stack `Georgia, 'Times New Roman', serif` for headlines, section titles, masthead.
- Existing dark `--ink`/`--line` palette retained; mono retained strictly for numbers.
- Cards give way to 1px hairline rules and whitespace in the new homepage sections.

## 4. Favorites (`?league=favorites`)

- League pins: existing localStorage star system carries over (stars move to the Leagues
  index page). Shows each pinned league's leader/race snapshot from HOME_DATA.
- Team pins: new star affordance on the team profile header (standings rows keep their
  fixed dense grid; profiles are one click away via the existing team links), stored as
  `entenser-fav-teams` = `[{league, team}]`. The Favorites page dynamically injects
  `data/<league>.js` scripts for pinned teams' leagues, then shows each team's next
  fixture (model probabilities) + a one-line season projection.
- Empty state: prompt to pin leagues/teams with a link to the Leagues index.

## Error handling

- Missing/stale HOME_DATA fields → sections render their existing empty-state notes.
- A pinned team whose league file fails to load → row shows the pin with a "data
  unavailable" note, never blocks other favorites.
- Flag emoji are plain text — no image dependencies.

## Testing

Browser preview verification at desktop (1280px) and mobile (375px): country-bar
dropdowns, bottom-nav routing, lead-story generation against current `home.js`, favorites
pin/unpin round-trip through localStorage, and no regression on a league page
(`?league=epl`) and the edge board (`?league=command`).

## Build order

1. `build_home.py`: fixtures array (+ regenerate `webapp/data/home.js`).
2. Chrome: masthead, country bar + dropdowns, LIVE strip, mobile bottom nav, sidebar removal.
3. Homepage editorial layout + headline generator.
4. Leagues index page + Favorites route + team pins.
5. Verify in browser both widths; update docs per CLAUDE.md convention.
