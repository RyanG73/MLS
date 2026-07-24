# Public Launch — Monday 2026-08-17

> **Verdict log (newest first)** — append a dated verdict here after each completed step.
>
> - 2026-07-19 (6): **Leagues tab (user-directed).** Masthead "Upcoming: N
>   fixtures projected · N leagues" ticker suppressed on `?league=leagues`
>   only; the small honest-coverage line ("N competitions tracked · N with
>   full live forecasts · …", launch plan B2) replaced by a serif brag
>   headline "56 competitions tracked" (`.lx-brag`, clamp 26px→44px) that
>   spans the full row (343/343px at 375px). Verified mobile: no ticker, no
>   overflow, no console errors.
> - 2026-07-19 (5): **Matches tab redesign (user-directed, continuing the
>   premium-site mobile sweep).** The PL-style `fxRow` axis rows (+ click-to-
>   expand scorelines and edge captions) are replaced by `mxCard` — the home
>   tab's stacked card with team names between crest and %/score, kickoff time
>   (or FT) above each match, and the draw on a slim footer. Day list now
>   groups by league (favorites first, then `_LEAGUE_POP`), chronological by
>   kickoff within a league; cards flow 2-up at 375px (flex-basis 148px),
>   single-column (full-width, max 520px) so full team names always read —
>   user follow-up replacing the first-pass 2-up flow. "Browse by day ·
>   built <timestamp>" header removed.
>   Verified 375px + desktop, upcoming and played days: zero console errors,
>   zero overflow.
> - 2026-07-19 (4): **Home polish round 3.** Crests up again (board 22px, table
>   20px, result/fixture rows 22px, movers 24px) with the crest img padding
>   dropped to 0 so logos fill the plate; result/fixture card rows switched
>   from space-between to left-packed (6px gap) so scores/percentages hug the
>   crest, cards narrowed 72→64px and 118→104px. Verified 375px: tables at
>   y=603 (above fold), no overflow, no console errors.
> - 2026-07-19 (3): **Home polish round 2 (user feedback with screenshots).**
>   Root-caused the "logos shifted top-left" bug: home CSS sized the `img`
>   inside `.crest` while the crest img is absolutely positioned `inset:0`, so
>   shrinking the img pinned it to the corner — selectors now size the `.crest`
>   box itself (`.hx-erow/.hx-tbl/.hx-scard/.mv-row`), and global crest img
>   padding went 2px→1px so logos fill their plate. Title Odds labels league →
>   country (from leagues.js registry; overrides mls→USA, ucl→UEFA CL; label
>   column 92→58px so full team names fit). Result cards 128→72px and fixture
>   cards 150→118px wide with tighter gaps (~12 results visible per strip
>   screen, was ~7). Upcoming Matches now filters to the board's top leagues
>   (epl/la-liga/serie-a/bundesliga/ligue-1/ucl/mls/liga-mx/brazil-serie-a,
>   full-slate fallback if none play) sorted date-then-prominence. Tagline is a
>   signature serif headline balanced across exactly two lines (canvas-measured
>   19.5px at 375px; `max-width:17.6em` + `text-wrap:balance` keeps the 2-line
>   break at any width). Verified 375px + desktop: 2-line tagline, League
>   Tables at y=575, zero console errors, zero overflow.
> - 2026-07-19 (2): **Home page overhaul (user-directed mobile review, first page
>   of the premium-site sweep).** Ticker → "Upcoming: N fixtures projected · N
>   leagues" (one line at 375px). Title Odds board: metric labels after the %
>   dropped, MLS above Liga MX, tighter rows, and a UCL row pinned under Ligue 1
>   (`build_home.py build_ucl_board()` → `ucl_board` payload key; between seasons
>   pct=null renders "New season odds coming soon"). League Tables: top-10 rows +
>   GD column (`build_tables` top_n 6→10, gd in rows). The promise block is gone —
>   h1 lives on as a slim muted tagline above Title Odds (`.hx-tag` grid area,
>   both breakpoints), pitch paragraph + "This week's recap →" CTA removed
>   (/weekly/ pages still exist, just unlinked from home). Results strip cards
>   rebuilt to the user's sketch: league-name header, then crest|score row per
>   team. Upcoming Matches: one-league-per-slide carousel replaced by the same
>   day→card strip, team rows show win% + fair odds with a slim draw footer
>   (missing crests now fall back to monograms via `crest()`, fixing the white-box
>   look). sw.js shell cache v12→v13. Verified in-browser at 375px and desktop:
>   League Tables header at y=625 (above the fold as requested), zero console
>   errors, zero horizontal overflow.
> - 2026-07-19: **E2/E3/E4 email capture BUILT (roadmap Phase-1 buildout).** `server/subscribe.py`
>   + `api/public/subscribe.py` expose `POST /public/subscribe`: KV-durable capture that mirrors to
>   Resend Contacts only when the key exists, so it deploys inert today and activates the moment E1
>   lands. All three webapp signup forms POST via `captureEmail()` with localStorage fallback. E4's
>   capture-only rule is enforced in code (never sends). E remains blocked on E1 (USER: Resend account)
>   only for *activation*, not build. See `docs/superpowers/plans/2026-07-19-roadmap-phase1-buildout.md`.
> - 2026-07-19: **Mobile nav active-tab glow + signed-out Intel Hub locked
>   preview (user-directed, from a phone screenshot).** Bottom tab bar: the
>   current tab now gets a soft green wash + icon drop-shadow glow
>   (`webapp/index.html` `.bnav a.active`) instead of the near-invisible
>   text-color swap. Intel Hub signed-out view (`webapp/intelligence.js`
>   `signInView`): auth block retitled "Sign in or create an account" (magic
>   link does both), and below it a new `lockedPreviewHTML()` — a greyed
>   (`opacity .42`, grayscale, bottom fade mask), `inert`/`aria-hidden`
>   sample mockup of the hub (tabs, trust tape, Season brief, movement tape,
>   Fixture leverage) with a sticky "🔒 Sign in to unlock" CTA that scrolls
>   to + focuses the email field, plus a full-opacity "Also inside" chip list
>   of the 10 remaining locked features. CSS in `webapp/intelligence.css`.
>   Verified in-browser (mobile 375px + desktop): DOM checks for inert/opacity/
>   chip placement, CTA focus lands on `#intel-email`, zero console errors.
>
> - 2026-07-18 (5): **Intel + Account shipped (user-directed): News → Intel tab
>   with a paywalled Personal Intelligence Hub mockup; Subscribe → full Account
>   hub; team pages gated behind Intel.** New routes `?league=intel` and
>   `?league=account` (old `?league=subscribe` links land on Account via alias +
>   `history.replaceState`; `?league=news` survives for old links and is linked
>   from Intel's free-headlines section). Intel page: gold-branded hero, founding-
>   member subscribe hook ($7.99/€7.99/£6.99 waitlist, own localStorage key
>   `entenser_intel_waitlist` + `waitlist_click{tier:'intel'}` event), six greyed-
>   out demo panels (deep dives, what-ifs, projection studio, team HQ — personalized
>   to the user's first pinned club — threshold alerts, CSV downloads) with crisp
>   gold 🔒 Intel chips over grayscaled bodies. Team profiles: header + favorite
>   star stay free; the full dashboard renders greyed under a gate card with a
>   fade-out mask, honoring `IntelStore` (`localStorage entenser.intel='unlocked'`
>   restores everything — hook for the future checkout). Account page (desktop
>   side-nav + scrollspy, mobile sticky pill rail): Profile (name/email →
>   `entenser.acct`, email mirrored to `entenser_email_interest`), Favorites
>   (picker moved from Subscribe), Subscriptions (Free vs Intel plan cards + hook +
>   weekly email), Notifications (5 toggles, 2 Intel-gated, alert threshold),
>   Preferences (odds format via `setOddsFmt`, tz note), Data & privacy (JSON
>   export, clear-all). Masthead gains 📡 Intel (PRO tag) + 👤 Account; bottom nav
>   is Home·Matches·Leagues·Intel·Account(pill). Verified in-browser desktop +
>   mobile: all routes, zero console errors, no horizontal overflow, gate
>   lock/unlock, waitlist + profile persistence, odds-pill ↔ masthead sync.
>
> - 2026-07-18 (4): **A1a shipped — GA4 analytics adapter in place.**
>   `webapp/index.html` now uses GA4/`gtag.js` as the launch analytics provider
>   behind the existing `track(event, props)` API, with all current revenue-relevant
>   events flowing to `gtag('event', ...)`. Analytics remains hard-disabled unless
>   the page is served from `https://entenser.com` and a valid `G-...` Measurement
>   ID is configured. Plausible remains a deferred provider option behind the same
>   adapter, without changing call sites. A1 still needs the user-created GA4 Web
>   stream ID before production e2e verification (A3/I2).
>
> - 2026-07-18 (3): **Measurement strategy shifted to Google-first for startup
>   capital discipline.** Plausible is no longer the launch-blocking analytics
>   account. Default stack is GA4 Standard ($0) + Google Search Console ($0), with
>   Plausible deferred until a simpler privacy-first dashboard is worth paying for.
>   Added A1a as the required codebase change: replace the current Plausible-only
>   loader with a provider adapter that supports GA4/gtag, keeps analytics disabled
>   on localhost/file previews, and routes the existing revenue-relevant events into
>   GA4. Primary metric remains weekly returning forecast users, now measured in GA4.
>
> - 2026-07-18 (2): **test_build_movers fixed — not date-rot** (test-only change,
>   production untouched). Root cause: the home-overhaul commit (3279e2a) changed
>   `compute_movers`' contract — return went `list` → `(list, span_days,
>   earliest_date)` and each (league, team)'s earliest snapshot is now dropped as
>   a sentinel bootstrap row — without updating the tests. compute_movers has no
>   `today()` dependence (window anchors to the data's max snapshot), so
>   hardcoded fixture dates never age out and stay hardcoded. Tests now unpack
>   the tuple and give each team a 100.0-valued bootstrap row, which doubles as
>   a regression check on the bootstrap-drop. 1024 passed / 15 skipped
>   (test_browser_smoke collection needs playwright, absent in this env).
>
> - 2026-07-18: **Home + Matches redesign shipped (desktop + mobile), News & Subscribe
>   routes added** — user-directed template iteration (5 wireframes) then full build.
>   Home: compact promise + Bundesliga-style results strip, rotating 8-league table
>   synced with a title-odds board, personalized RSS section (desktop; News tab on
>   mobile), one-league-at-a-time fixtures carousel, movers + news band kept; AI
>   headline ladder, "The Models" rail, and Europe map removed. Matches: day-strip
>   calendar with PL-style fixture rows (kickoff axis, team-colored bars, fair odds,
>   favorites-first sort), slim email + rotating mover ticker, ledger strip; hero/KPIs/
>   races/trust panels removed. Masthead: big-five stay in the bar, rest-of-Europe in a
>   3-column dropdown, "Odds Format" label, larger date. Bottom nav: Home·Matches·
>   Leagues·News·Subscribe (pill). Subscribe unifies weekly-email capture + favorites
>   picker (FavStore) + supporter waitlist. Data: home.js gains `tables` (8 featured
>   leagues) + per-league-capped fixtures (96) + 24 news; calendar.js gains ko/colors/
>   lam/mu. 1060 tests green (3 pre-existing date-rot failures in test_build_movers
>   flagged separately); sw.js→v10.
>
> - 2026-07-17 (5): **I1 — first pre-launch QA pass on production, no blocking
>   issues** (`docs/qa-pass-2026-07-17.md`). Swept every route type (home, league
>   SPA, command, power, results-only, team deep-link, support, all static pages)
>   desktop + mobile: zero console errors, zero 404s on real routes, no horizontal
>   overflow, static tables scroll in-container. Verified live: odds toggle
>   (switches + persists), canonical swap on SPA routes, OG/meta/title, PWA
>   (manifest valid, SW v9 active), robots + sitemap (61 URLs) + 404, valid JSON-LD
>   on all static pages (7–19 KB), 3 consecutive green refresh+deploy runs. Minor/
>   expected only: analytics no-op until Plausible exists (A1); results-only
>   leagues show an older "updated" date (honest but could reframe later); watch
>   the first CI weekly-recap run on 2026-07-18. More QA passes planned before
>   launch. **I2/I3/I4 remain** (analytics+email e2e once accounts exist; content
>   freeze Aug 14; user posts Aug 17).
>
> - 2026-07-17 (4): **H1–H4 shipped and browser-verified** (H5 is a USER task).
>   H1: `scripts/build_weekly_recap.py` → `webapp/data/weekly.js` + crawlable
>   `/weekly/` page (movers, closest races, model-vs-market when priced, and a
>   high-confidence hits/misses "receipt"); wired into refresh-daily.yml +
>   build_all.sh; home + footer links. H2: crawlable `/after-the-world-cup/`
>   on-ramp listing MLS/NWSL/Liga MX/Leagues Cup/USL/Canadian PL with live leaders
>   pulled from payloads; home kicker + footer link. H3: per-league CSV exports
>   (`/exports/<lid>.csv`, 51 table leagues) + `/open-data/` page with attribution
>   + DataCatalog JSON-LD (ClubElo backlink strategy); footer link. All three added
>   to the sitemap and generated at deploy time (gitignored). H4: announcement
>   drafts for Reddit (r/MLS, r/NWSL, r/soccer), Show HN, X/Bluesky + a
>   competitor-diff answer and sequencing plan in `docs/launch-announcements.md`
>   (USER posts them). sw.js → v9. 563 tests + 57/57 payloads green; every new
>   page verified live in-browser with zero console errors.
>
> - 2026-07-17 (3): **G1–G2 shipped and browser-verified.** New `?league=support`
>   info route with a "Support Entenser" card — locale-aware price (£4.99/€5.99/
>   $5.99, en-US→$5.99 verified), feature list (saved teams + alerts, forecast-
>   change history, weekly briefing, CSV downloads, ad-free), and a waitlist form
>   that stores to `entenser_supporter_waitlist` and fires `waitlist_click`
>   (`{tier:'supporter'}`; Plausible attributes country server-side). "The public
>   site never gets paywalled" stated explicitly to protect the trust position.
>   Added to the info-nav + a site-wide footer "Support" link. Invalid emails
>   rejected (no store, no event). Handler is E-ready: a one-line swap will POST to
>   the Resend proxy tagged supporter-waitlist. sw.js → v6. 560 tests + 57/57
>   payloads green, zero console errors. **Decision gate (Report 2): build the paid
>   tier only if ≥2% of returning users join.**
>
> - 2026-07-17 (2): **F1–F2 shipped and browser-verified.** F1: all 11
>   `toLocaleDateString('en-US')` sites now use the viewer's browser locale
>   (`undefined`); kickoff times already used `toLocaleTimeString([])`. F2:
>   `american()` replaced by a format-aware `oddsStr`/`oddsHTML` pair + a masthead
>   US/Dec/Frac toggle that re-renders every quoted price in place (no reload) and
>   fires `odds_format_change`; preference persisted in localStorage, default
>   American for `en-US` browsers and decimal otherwise (verified: en-US→american,
>   en-GB/de-DE/es-ES/en→decimal, stored preference wins). Odds math spot-checked
>   (p=0.706 → −240 / 1.42 / 5⁄12; p=0.085 → +1076 / 11.76 / 43⁄4). sw.js → v5.
>   **Also fixed a B1 latent bug found here:** the payload-side `data_status`
>   heuristic (`ts < year-1`) misfired on Liga MX (torneo-index season) →
>   `build_league_data.py` now reads `data_status` straight from
>   `fetch_league_teams.DATA_STATUS` so payload and registry can never disagree.
>   57/57 payloads valid, 562 tests pass, zero console errors.
>
> - 2026-07-17: **D1–D3 shipped and browser-verified** (ran early on user request).
>   D1: first-screen promise band on the Home landing ("Title, qualification and
>   relegation forecasts across world football" / "No bookmaker odds in the model
>   … every forecast graded in public"); head meta/OG/title rewritten to lead with
>   the fan outcome; Command Center eyebrow + subtitle gained the plain-English
>   "the model never sees betting odds" clause. D2: plain-English trust on-ramp
>   above the Command Center trust panel (translates Brier — "when we say 70% it
>   happens about 70% of the time — here's the receipt" — keeps raw family Brier
>   below; "we don't claim to beat the market, we show our work" preserved). The
>   per-league Model Health tab already had fan-friendly framing, left intact.
>   D3: About route now leads with "the only football model that grades itself in
>   public"; static-page `_METHOD_NOTE` was already consistent. sw.js → v4.
>   Verified: Home/command/about/trust render new copy, zero console errors, 10
>   static-page tests pass, 57/57 payloads valid, method note present on
>   /leagues/epl/.
>
> - 2026-07-16 (3): **C1–C9 shipped and live-verified** (d1c38c0). 56 standalone
>   `/leagues/<id>/` pages + hub + sitemap generated at deploy time by stdlib-only
>   `scripts/build_static_pages.py` (8–16 KB/page, unique titles, self-canonicals,
>   BreadcrumbList/SportsEvent/Dataset JSON-LD, data-status notes, method note,
>   sibling links, CTA into the SPA). `payload_utils.read_js_payload()` is the
>   payload-parse primitive; robots.txt + branded 404.html committed; SPA gained
>   canonical swap to the static pages + homepage WebSite/Organization JSON-LD +
>   crawl links; sw.js → v3. Live checks green: /leagues/epl/ 200 w/ correct
>   canonical, slash-less 301, sitemap (58 URLs) + robots 200, bogus league 404,
>   archive note on canadian-pl. 10 new contract tests pass (1018 total; 3
>   pre-existing test_build_movers failures are documented follow-up, chip filed).
>   **Remaining in C: C10 (GSC submission — blocked on user A2) and C11 (optional
>   per-league OG cards).**
>
> - 2026-07-16 (2): **B1–B3 implemented and browser-verified.** `data_status`
>   taxonomy (full_forecast / results_only / historical + format_approximate)
>   derived in `build_league_data.py`, stamped in `fetch_league_teams.DATA_STATUS`
>   + `webapp/leagues.js` + the 4 exception payloads (canadian-pl, k-league-1 →
>   historical; poland-ekstraklasa, finland-veikkausliiga → results_only);
>   registry/payload agreement check added to `validate_payloads.py` (57/57 pass);
>   UI badges in nav + Leagues hub, honest count line ("56 tracked · 52 with full
>   live forecasts"), per-league subtitle note + "updated <date>" stamp. UI edits
>   were committed inside a concurrent session's `fix(webapp)` commit; script/
>   registry changes staged, final commit pending resolution of that session's
>   autostash conflicts (73 UU generated files).
>
> - 2026-07-16: Plan created from the combined competitive-intelligence report
>   (`docs/competitive-intelligence-2026-07-combined.md`). Scope decisions by user:
>   full public launch · supporter-tier **waitlist** only (no checkout) · **locale
>   basics** only (Spanish pages deferred) · **Resend** email backend.

## Goal

Convert an invisible but differentiated product into a discoverable, honest, measurable
one, and announce it Monday 2026-08-17. The binding constraint is distribution, not
model quality. Success at launch+30d: league pages indexed in GSC, weekly returning
forecast users measurable in GA4, email list growing, waitlist conversion known.

**Primary early metric:** weekly returning forecast users on forecast routes (GA4).
**Secondary:** email signups, league-page search impressions, waitlist joins by country.

## Status at a glance (updated 2026-07-18)

**9 of 11 workstreams shipped and live on entenser.com.** The two that aren't done
are mostly blocked on ~15 minutes of user account setup; the GA4 adapter code is now
ready for the Measurement ID.

- ✅ **Done & live:** combined report · B (data honesty) · C1–C9 (crawlable SEO) ·
  D (messaging) · F (locale) · G (waitlist) · H1–H4 (distribution) · I1 (QA pass) ·
  A1a (GA4 adapter)
- ⛔ **Blocked on USER (accounts):** A1 GA4 · A2 GSC · C10 sitemap submission ·
  E1 Resend domain+key. **E2/E3 are now BUILT (2026-07-19), key-gated at runtime** —
  they deploy inert and light up the moment E1's key lands.
- 🗓 **Launch-week / USER:** H5 post announcements · I2 analytics+email e2e (needs
  accounts) · I3 content freeze Aug 14 · I4 user posts Aug 17.

| WS | What | Status |
|----|------|--------|
| — | Combined competitive-intel report | ✅ Done |
| A | Measurement (GA4 / GSC / events) | ⏳ A1a done; **A1/A2 blocked on USER** |
| B | Data-status honesty contract | ✅ Done & live |
| C | Crawlable pages + SEO | ✅ C1–C9 done & live · ⛔ C10 needs USER (GSC) · ⬜ C11 optional |
| D | Messaging + trust on-ramp | ✅ Done & live |
| E | Email capture (Resend) | ✅ E2/E3/E4 BUILT 2026-07-19 (key-gated, deploys inert) · ⛔ E1 needs USER |
| F | Locale basics | ✅ Done & live |
| G | Supporter-tier waitlist | ✅ Done & live |
| H | Distribution content | ✅ H1–H4 done & live · 🗓 H5 is USER (post) |
| I | QA + launch | ⏳ I1 done, no blockers found · I2 needs accounts · I3 Aug 14 · I4 USER Aug 17 |

**The single highest-leverage next action:** the ~15-min account setup (GA4, GSC,
Resend — runbook below). It unblocks A, C10, E, and the measurement half of I.

## Architecture decision (Workstream C, settled 2026-07-16)

Static standalone landing pages at `entenser.com/leagues/<id>/` (~15–25 KB each, NOT
copies of the SPA), generated **at deploy time** inside `deploy.yml` by a stdlib-only
Python script reading the same `webapp/data/*.js` payloads — no committed generated
HTML, nightly regeneration free via the existing `workflow_run` deploy chain. Static
pages are self-canonical; the SPA's `?league=` routes get a JS-swapped canonical
pointing at them. JSON-LD: BreadcrumbList + SportsEvent (next fixtures) + Dataset;
homepage WebSite + Organization; no FAQPage. `robots.txt` must NOT block `?league=`
(Google needs to render it to see the canonical). Team pages (~1,100) are explicitly
phase 2, after GSC proves league-page indexation.

## Workstreams and tasks

Owner is Claude unless marked **(USER)**. `[ ]` → `[x]` with a verdict-log entry.

### A — Measurement truth (Week 1: Jul 16–22) — P0

- [ ] **A1 (USER) — ⛔ BLOCKED** Create a free GA4 property + Web data stream for
      `entenser.com`; copy the Measurement ID (`G-...`) into the setup handoff.
- [x] **A1a** Modify the website analytics adapter in
      `webapp/index.html` to support Google Analytics 4 (`gtag.js`) as the launch
      provider, keep analytics disabled on localhost/file previews, and route the
      existing revenue-relevant events (`pageview_route`, `league_nav`, `tab_click`,
      `match_expand`, `team_open`, `favorite_toggle`, `email_signup`,
      `waitlist_click`, `article_click`, `home_table_jump`, `odds_format_change`)
      into GA4. Keep Plausible as an optional/deferred provider only if the adapter
      can do so without adding complexity.
- [ ] **A2 (USER) — ⛔ BLOCKED** Google Search Console: add property `entenser.com`,
      verify via DNS TXT record at the domain registrar. (Instructions in runbook.)
- [~] **A3 — PARTIAL** `waitlist_click` (G2) and `odds_format_change` (F2) events
      added and live. Remaining: verify GA4 events flow end-to-end — **needs A1**.
- [x] **A4** Metrics defined (see Goal). Done at plan creation.

### B — Data-status honesty contract (Week 1) — P0

- [x] **B1** `data_status` field on payloads + registry (`full_forecast` /
      `results_only` / `historical` + `format_approximate`); canadian-pl + k-league-1
      → historical, poland + finland → results_only. Reads from the registry so
      payload/registry can't disagree.
- [x] **B2** UI badges in nav + Leagues hub; per-league subtitle note + "updated
      <date>" stamp; honest count line ("56 tracked · 52 with full live forecasts").
- [x] **B3** `validate_payloads.py` fails on registry/payload `data_status` disagreement.

### C — Crawlable pages + SEO (Weeks 1–3: Jul 20–Aug 7) — P0, critical path

- [x] **C1** `payload_utils.read_js_payload()` added; `build_share_cards` refactored onto it.
- [x] **C2** `scripts/build_static_pages.py`: 56 per-league pages + `/leagues/` hub +
      `sitemap.xml` (+ later `/weekly/`, `/open-data/`, `/after-the-world-cup/`).
- [x] **C3** `webapp/robots.txt` committed (allow all + Sitemap; `?league=` not blocked).
- [x] **C4** `tests/test_static_pages.py` (12 tests: titles, JSON-LD, canonical, sitemap, escaping).
- [x] **C5** `index.html`: static canonical + JS canonical swap; league-overview link;
      `/leagues/` footer link; homepage WebSite/Organization JSON-LD.
- [x] **C6** `sw.js` cache bumped (now at v9); `/leagues/` deliberately never cached.
- [x] **C7** `deploy.yml` runs the generator (fails deploy on error); `.gitignore` +
      `build_all.sh` hookup.
- [x] **C8** `webapp/404.html` branded.
- [x] **C9** Deployed & live-verified: 200/301/404, sitemap (61 URLs) + robots, nightly lastmod.
- [ ] **C10 (USER assists) — ⛔ BLOCKED (needs A2/GSC)** submit sitemap; request indexing
      on `/leagues/` + flagship pages + the mis-indexed `?league=` URL.
- [ ] **C11 (optional) — ⬜ NOT DONE** per-league evergreen OG PNGs.

### D — Messaging + trust on-ramp (Week 2: Jul 23–29) — P0

- [x] **D1** First-screen promise band on Home + head meta/OG/title; plain-English
      "the model never sees betting odds" at first mention (Command Center too).
- [x] **D2** Plain-English trust on-ramp above the Command Center trust panel; raw
      Brier kept below; "we don't claim to beat the market" framing preserved.
- [x] **D3** About leads with "the only football model that grades itself in public";
      static-page method note consistent.

### E — Email capture via Resend (Weeks 2–3) — P1

- [ ] **E1 (USER) — ⛔ BLOCKED** Verify `entenser.com` in Resend; create API key;
      confirm proxy host (recommended: single Vercel serverless function).
- [x] **E2 — BUILT 2026-07-19, activates on E1** `POST /public/subscribe` (`server/subscribe.py`
      + `api/public/subscribe.py`): writes every subscriber to KV unconditionally and mirrors to the
      Resend audience **only when `RESEND_API_KEY`/`RESEND_AUDIENCE_ID` exist** — so it deploys now
      and lights up the moment E1 lands, with KV as the backfill source. Per-IP rate limiting; CORS
      via the central `ALLOWED_ORIGINS`; no key in the client.
- [x] **E3 — BUILT 2026-07-19** `bindCommandSignup()`, `bindWaitlist()`, and `bindIntelWaitlist()`
      now `captureEmail()`-POST to the endpoint (tags: `weekly-digest`+`lg-<id>` / `supporter-waitlist`
      +cadence+source / `intel-waitlist`); localStorage stays the primary UX record so a down/unbuilt
      API never breaks the form.
- [x] **E4** Standing rule honored: `server/subscribe.py` only writes contacts, never sends. **No email
      sends without explicit owner sign-off.**

### F — Locale basics (Week 3: Jul 30–Aug 5) — P1

- [x] **F1** All 11 `toLocaleDateString('en-US')` sites now use the browser locale;
      kickoff times already viewer-timezone via `toLocaleTimeString([])`.
- [x] **F2** `oddsStr`/`oddsHTML` (American/decimal/fractional) + masthead US/Dec/Frac
      toggle, re-renders in place, localStorage preference, `odds_format_change` event.

### G — Supporter-tier waitlist (Week 3) — P1

- [x] **G1** `?league=support` "Support Entenser" card: locale-aware price, feature
      list, waitlist form tagged `supporter-waitlist`; footer + info-nav links.
- [x] **G2** `waitlist_click` fires (GA4 will report geography once A1 is live).
      **Decision gate:** build the paid tier only if ≥2% of returning users join.

### H — Distribution + launch content (Weeks 3–4: Aug 3–14)

- [x] **H1** `build_weekly_recap.py` → `webapp/data/weekly.js` + crawlable `/weekly/`
      page (movers, closest races, model-vs-market, high-confidence hits/misses receipt);
      wired into refresh-daily.yml. (Share card deferred — reuses existing movers.png.)
- [x] **H2** Crawlable `/after-the-world-cup/` on-ramp with live US-league leaders;
      home kicker + footer link.
- [x] **H3** Per-league CSV exports (`/exports/<lid>.csv`, 51 leagues) + `/open-data/`
      page with attribution + DataCatalog JSON-LD.
- [x] **H4** Announcement drafts (Reddit r/MLS/r/NWSL/r/soccer, Show HN, X/Bluesky) +
      competitor-diff answer + sequencing in `docs/launch-announcements.md`.
- [ ] **H5 (USER) — 🗓 launch week** Post announcements; optional outreach to ASA /
      analytics newsletter writers offering the data feed.

### I — QA + launch (Week of Aug 10–17)

- [x] **I1** First production QA pass (2026-07-17, `docs/qa-pass-2026-07-17.md`): every
      route type desktop + mobile, PWA, canonical swap, robots/sitemap/404, static
      JSON-LD — **no blocking issues**. (More passes planned before launch.)
- [ ] **I2 — ⛔ needs accounts** Analytics + email capture verified end-to-end on production.
- [ ] **I3 — 🗓 Aug 14** Content freeze; nightly refresh + deploy chain green.
- [ ] **I4 (USER) — 🗓 Aug 17** Post announcements; monitor GA4/GSC.

## Timeline

**Actual progress vs plan:** engineering is ~3 weeks ahead — all of B, C, D, F, G,
H and the first QA pass landed in the Jul 16–17 window (originally scheduled through
mid-August). What's left is user account setup and launch-week execution.

| Week (original plan) | Focus | Actual |
|---|---|---|
| Jul 16–22 | report · A · B · C1–C4 | ✅ report, B, **all of C**, D, F, G, H, I1 done |
| Jul 23–29 | C5–C7 · D · E endpoint | ✅ done early · E blocked on E1 |
| Jul 30–Aug 5 | C9–C10 · F · G | ✅ done early · C10 blocked on GSC |
| Aug 6–12 | H1–H4 · QA starts | ✅ done early |
| Aug 13–17 | I freeze + final QA · **launch** | 🗓 remaining: I2–I4, more QA passes |

**Now user-blocking:** A1 (GA4 Measurement ID), A2 (GSC DNS), E1 (Resend + proxy
host) — runbook below. **Code-blocking:** none.

## Launch runbook — user setup instructions

1. **Google Analytics 4 (A1):** analytics.google.com → Admin → Create property →
   Web data stream → URL `https://entenser.com` → copy the Measurement ID (`G-...`).
   Keep enhanced measurement on. Then set `ANALYTICS.measurementId` in
   `webapp/index.html` and run A3 verification.
2. **Search Console (A2):** search.google.com/search-console → Add property →
   "Domain" type → `entenser.com` → copy the TXT record → add it at the DNS provider
   → Verify. Grant Claude the property URL for C10 submissions (screenshots suffice).
3. **Resend (E1):** resend.com dashboard → Domains → Add `entenser.com` → add the
   3 DNS records (SPF/DKIM) → verify. Create an API key (Full access, or
   Sending+Contacts). Create an Audience named "Entenser interest". Store the key as
   an environment secret on the chosen proxy host — never in the repo.

## Post-launch backlog (deferred by decision)

Plausible dashboard (deferred until traction justifies spend) · Team pages (~1,100;
after GSC proves league indexation) · Spanish landing pages (La Liga/Liga MX) ·
GBP/EUR pricing + real checkout (gated on G2) · weekly digest email sends (needs
owner sign-off) · dynamic OG cards · quarterly competitive monitor (Silver Bulletin
club-model watch; FotMob/Sofascore forecast features; Football Data Lab pricing) ·
contextual non-gambling sponsorship · ads (gated on RPM vs trust measurement).

## Verification (per workstream)

- **C:** `pytest tests/test_static_pages.py`; `python3 -m http.server -d webapp`
  spot-checks; view-source shows full content without JS; Rich Results Test on
  JSON-LD; post-deploy curl checks (200/301/404, lastmod advancing); GSC coverage
  weeks 1–4 (watch preseason pages for soft-404s).
- **SPA regression:** all route types after index.html edits; SW updates to v3,
  offline shell loads; `scripts/validate_payloads.py` green.
- **E:** production signup → contact appears in Resend audience; off-domain POST
  blocked by CORS.
- **F:** spoofed `en-GB`/`de-DE` locales show sensible dates/times/odds defaults;
  toggle persists across reloads.
- **Docs discipline (CLAUDE.md):** verdict appended here per completed step;
  `docs/PLAN.md` blockquote entry when something ships; `docs/PROJECT_HISTORY.md`
  summary + delete this file when the plan completes.
