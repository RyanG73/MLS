# Public Launch — Monday 2026-08-17

> **Verdict log (newest first)** — append a dated verdict here after each completed step.
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
forecast users measurable in Plausible, email list growing, waitlist conversion known.

**Primary early metric:** weekly returning forecast users (Plausible).
**Secondary:** email signups, league-page search impressions, waitlist joins by country.

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

- [ ] **A1 (USER)** Create Plausible account for `entenser.com` (paid plausible.io or
      self-hosted). No code change needed — `webapp/index.html:25` is pre-configured.
- [ ] **A2 (USER)** Google Search Console: add property `entenser.com`, verify via DNS
      TXT record at the domain registrar. (Instructions in launch-runbook below.)
- [ ] **A3** After A1: verify events flow end-to-end (`pageview_route`, `league_nav`,
      `email_signup`, `edge_row_expand`); add `waitlist_click` and `odds_format_change`.
- [ ] **A4** Metrics defined (see Goal). Done at plan creation.

### B — Data-status honesty contract (Week 1) — P0

- [ ] **B1** Add `data_status` field to league payloads + registry:
      `full_forecast` / `preseason` / `results_only` / `historical`, plus a
      `format_approximate` boolean derived from `outlook.rules`. Reclassify:
      `canadian-pl` (2024 data), `k-league-1` (2022–24), `finland-veikkausliiga`,
      `poland-ekstraklasa` (results-only, no forward fixtures).
- [ ] **B2** Surface in UI: per-league badge + "last updated" in league header and the
      leagues hub; honest global copy ("56 competitions tracked · N with live
      forecasts") everywhere a count appears.
- [ ] **B3** `scripts/validate_payloads.py`: fail if registry and payload status disagree.

### C — Crawlable pages + SEO (Weeks 1–3: Jul 20–Aug 7) — P0, critical path

- [ ] **C1** `scripts/payload_utils.py`: add `read_js_payload()` (inverse of
      `write_js_payload`); refactor `build_share_cards._load_payload` onto it.
- [ ] **C2** `scripts/build_static_pages.py` (new, stdlib-only): per-league pages +
      `/leagues/` hub + `sitemap.xml`. Content: projected table w/ title/releg %,
      top-odds callouts, next ~8 fixtures with W/D/L probs, rules blurb, last-updated,
      method note (reuses D3 copy), CTA into `/?league=<id>`, sibling-league links.
      Status-variant copy for live/preseason/completed; skip placeholders; escape all
      payload strings.
- [ ] **C3** `webapp/robots.txt` (committed): allow all + `Sitemap:` line.
- [ ] **C4** `tests/test_static_pages.py`: unique titles, JSON-LD parses, canonical
      matches directory, well-formed sitemap, escaping of team names.
- [ ] **C5** `webapp/index.html`: static canonical + JS canonical swap in head router
      (~line 841); "league overview" link at league header (~line 1039); `/leagues/`
      link in `FOOT_LEGAL` (line 1126); homepage WebSite/Organization JSON-LD.
- [ ] **C6** `webapp/sw.js`: bump cache to `entenser-shell-v3`; document that
      `/leagues/` static pages are never cached.
- [ ] **C7** `.github/workflows/deploy.yml`: run generator between checkout and
      `upload-pages-artifact`, fail deploy on error. `.gitignore` `webapp/leagues/`
      + `webapp/sitemap.xml`. Non-fatal hookup in `scripts/build_all.sh`.
- [ ] **C8** `webapp/404.html` branded (optional).
- [ ] **C9** Deploy via `workflow_dispatch`; verify live: `/leagues/epl/` 200,
      slash-less 301, sitemap + robots 200, bogus league 404; after next nightly
      refresh confirm pages regenerated and sitemap `lastmod` advanced.
- [ ] **C10 (USER assists)** GSC: submit sitemap; request indexing on `/leagues/` +
      flagship pages (epl, mls, la-liga, liga-mx, nwsl) + the mis-indexed `?league=` URL.
- [ ] **C11 (optional)** `build_share_cards.py --league-cards`: evergreen per-league
      OG PNGs → `webapp/assets/og/leagues/`, generated locally once, committed.

### D — Messaging + trust on-ramp (Week 2: Jul 23–29) — P0

- [ ] **D1** First-screen promise: "Title, qualification and relegation forecasts
      across world football." / "No bookmaker odds in the model. Every forecast graded
      in public." One-clause market-blind explanation at every first mention.
- [ ] **D2** Plain-English trust layer: translate Brier ("when we say 70%, it happens
      about 70% of the time — here's the receipt"); keep expert metrics one click
      deeper; keep the "we do not claim to beat the market" framing intact.
- [ ] **D3** About/landing positioning: "the only football model that grades itself in
      public"; method-note copy shared with static pages (C2).

### E — Email capture via Resend (Weeks 2–3) — P1

- [ ] **E1 (USER)** Verify `entenser.com` in Resend; create API key; confirm proxy
      host (recommended: single Vercel serverless function; alternative: Cloudflare
      Worker).
- [ ] **E2** Build endpoint: POST `{email, tags}` → Resend Contacts audience; CORS
      locked to `https://entenser.com`; basic rate limiting; no key in client code.
- [ ] **E3** Rewire `bindCommandSignup()` (`webapp/index.html:3277`) to POST;
      localStorage kept as offline fallback; success/error states.
- [ ] **E4** Standing rule: capture only — **no email sends without explicit owner
      sign-off**.

### F — Locale basics (Week 3: Jul 30–Aug 5) — P1

- [ ] **F1** Replace hardcoded `'en-US'` locale at all 8 date call sites with browser
      default; kickoff times in the viewer's time zone (verify `ko` is ISO with TZ).
- [ ] **F2** Odds-format toggle: American / decimal / fractional; localStorage
      preference; single formatter replacing `american()` (`index.html:1112`);
      default American for `en-US` browsers, decimal otherwise; fire
      `odds_format_change`.

### G — Supporter-tier waitlist (Week 3) — P1

- [ ] **G1** "Support Entenser" card: £4.99/€5.99/$5.99 monthly framing; feature list
      (alerts, saved teams, forecast-change history, downloads, ad-free, weekly
      briefing); "join the waitlist" → email capture tagged `supporter-waitlist`.
- [ ] **G2** Track `waitlist_click`; segment by country in Plausible.
      **Decision gate:** build the paid tier only if ≥2% of returning users join.

### H — Distribution + launch content (Weeks 3–4: Aug 3–14)

- [ ] **H1** `scripts/build_weekly_recap.py`: weekly "biggest model-vs-market
      disagreements · race movement · model misses" from existing movers/drift/edge
      payloads → stable-URL page + share card. The Opta quotable-number playbook.
- [ ] **H2** "Just finished the World Cup?" on-ramp routing new US fans to
      MLS/NWSL/Liga MX race pages.
- [ ] **H3** Open-data page: per-league projection CSVs generated from payloads +
      attribution terms. (Check source data-licensing constraints first.)
- [ ] **H4** Announcement drafts: Reddit (r/MLS, r/soccer, r/NWSL — participate,
      don't spam), Show HN, X/Bluesky. Drafts only.
- [ ] **H5 (USER)** Post announcements; optional outreach to ASA / analytics
      newsletter writers offering the data feed.

### I — QA + launch (Week of Aug 10–17)

- [ ] **I1** Full production QA: mobile, PWA install/offline, dark mode, every route
      type; Lighthouse on static pages (target ~100).
- [ ] **I2** Analytics + email capture verified end-to-end on production.
- [ ] **I3** Content freeze Fri Aug 14; nightly refresh + deploy chain green.
- [ ] **I4 (USER)** Mon Aug 17: post announcements; monitor Plausible/GSC.

## Timeline

| Week | Focus |
|---|---|
| Jul 16–22 | Combined report ✅ · A (measurement) · B (status contract) · C1–C4 |
| Jul 23–29 | C5–C7 · D (messaging) · E (Resend endpoint) |
| Jul 30–Aug 5 | C9–C10 (deploy + GSC) · F (locale) · G (waitlist) |
| Aug 6–12 | H1–H4 (content + drafts) · QA starts |
| Aug 13–17 | I (freeze, final QA) · **Mon Aug 17 launch** |

**Critical path:** C. Start immediately after B so status labels render on the new pages.
**User-blocking this week:** A1 (Plausible), A2 (GSC DNS), E1 (Resend + proxy host).

## Launch runbook — user setup instructions

1. **Plausible (A1):** plausible.io → sign up → Add website → domain `entenser.com`,
   timezone America/New_York. Nothing to install — the site's script loads
   `plausible.io/js/script.tagged-events.js` already. Within minutes of the account
   existing, visits appear. Then tell Claude to run A3 verification.
2. **Search Console (A2):** search.google.com/search-console → Add property →
   "Domain" type → `entenser.com` → copy the TXT record → add it at the DNS provider
   → Verify. Grant Claude the property URL for C10 submissions (screenshots suffice).
3. **Resend (E1):** resend.com dashboard → Domains → Add `entenser.com` → add the
   3 DNS records (SPF/DKIM) → verify. Create an API key (Full access, or
   Sending+Contacts). Create an Audience named "Entenser interest". Store the key as
   an environment secret on the chosen proxy host — never in the repo.

## Post-launch backlog (deferred by decision)

Team pages (~1,100; after GSC proves league indexation) · Spanish landing pages
(La Liga/Liga MX) · GBP/EUR pricing + real checkout (gated on G2) · weekly digest
email sends (needs owner sign-off) · dynamic OG cards · quarterly competitive monitor
(Silver Bulletin club-model watch; FotMob/Sofascore forecast features; Football Data
Lab pricing) · contextual non-gambling sponsorship · ads (gated on RPM vs trust
measurement).

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
