# Entenser — Subscription Feature Roadmap (Aug 2026 → Jul 2027)

**Date:** 2026-07-17 · **Purpose:** the 12-month feature roadmap for converting free
users into paying supporters. Picks up where `docs/superpowers/plans/2026-08-17-public-launch.md`
ends. Evidence base: `docs/competitive-intelligence-2026-07-combined.md` (cited as
"CI report") plus a full inventory of the shipped webapp.

**Owner decisions recorded 2026-07-17 (do not re-litigate without being asked):**
1. **Edge tools = "quiet middle."** Model-vs-market/ledger/CLV features may ship inside
   the paid tier behind login, but are never marketed, never on SEO pages, never in
   announcements. Public positioning stays utility + trust (CI report risk #8).
2. **Backend = minimal serverless, cost-gated.** Stripe Checkout + a few Vercel
   functions + Resend + a free-tier KV store. No database server. Decisions that add
   fixed monthly cost get a cost line in this doc first.
3. **Historical data accumulation is a first-class goal.** Forecast history compounds
   daily and cannot be backfilled; features can be copied, a multi-year graded track
   record cannot. Anything that loses private archive rows, or accidentally exposes
   private archive rows through static public payloads, is a P0 bug.
4. **Free-floor ratchet (2026-07-17).** The free tier only ever grows — no shipped
   free feature is ever moved behind the paywall. Paid features are *born* paid. The
   permanent boundary: **current season free, the vault is paid** — everything in the
   public static payloads (current-season forecasts, tables, trajectories) is free
   forever; paid = the private multi-season archive, match-level probability history,
   alerts, personalization, downloads-at-depth. Temporary access to paid features
   happens only through a clearly-labeled free trial, never through free features that
   later shrink.

---

## 1. Willingness-to-pay thesis

Nobody pays for access to a probability — free alternatives are everywhere and the CI
report's own scenario model caps 3-yr revenue at $15k–$180k ARR. People pay for:

| WTP driver | What it means here |
|---|---|
| **Recurrence** | The product tells *them* when something changed (alerts, briefings) instead of requiring a visit |
| **Personalization** | *Their* teams, *their* leagues, *their* thresholds — powered by `FavStore` |
| **Interpretation** | Not "34%," but "34% → 41% this month, here's why" — powered by `drift-traj` |
| **Affiliation** | Supporting the only model that grades itself in public; identity, not access |
| **Utility** | Downloads, history, saved scenarios — tools, not numbers |

**Pricing:** $5.99 / £4.99 / €5.99 monthly (already live on the `/support` waitlist
card). **Annual = 10× monthly — "2 months free":** $59.99 / £49.99 / €59.99.
**Free trial: 14 days, card-required, full paid access** (Stripe `trial_period_days`,
no custom infra) — two briefings and two matchweeks per trial, because the paid loop
is weekly; a 7-day trial can contain a single matchday and no visible forecast
movement. Anchors: Football Data Lab £5.99/mo · £57.50/yr with a 7-day trial, ASA $5,
Silver Bulletin $10 ceiling.

**The contract already made:** the live support page promises five features — saved
teams + alerts · forecast-change history · weekly briefing · CSV downloads · ad-free.
The data for the first four is **already computed nightly** (`drift-traj/`,
`movers.js`/`race-deltas.js`, `weekly.js`, `exports/*.csv`, `FavStore`). The gap is
delivery infrastructure, not modeling. "Ad-free" is a null promise until ads exist —
see §6.

**The standing rule (CI report):** the public site never gets paywalled. Paid =
convenience, depth, and history on top of free forecasts.

### The line: free vs supporter

Governed by the free-floor ratchet (owner decision #4): the Free column can only grow,
and nothing ever migrates right-to-left… or left-to-right. The 14-day card-required
trial grants full temporary access to the Supporter column.

| Area | Free, forever | Supporter — $5.99/mo · $59.99/yr (born paid) |
|---|---|---|
| **Forecasts & tables** | Everything: league tables, title/playoff/relegation/promotion odds, projected points, sim what-ifs — never paywalled | — |
| **Match projections** | W/D/L probabilities, projected goals, fair odds in all three formats, momentum charts, filters | — |
| **Forecast history** | Current-season trajectories from public static payloads (sparklines, race-history charts — Phase 1.1) | **The vault:** private multi-season trajectory archive + match-level probability history (M4) |
| **Personalization** | Local pins/favorites, "My matchday" panel (Phase 1.2) | **Threshold email alerts** on your teams (M2); **personalized weekly briefing** (M3) |
| **Email** | Weekly-digest subscriber collection (Phase 1.4); sends require explicit owner sign-off | Personalized briefing + alerts (above) |
| **Data downloads** | Current-table CSVs on `/open-data/` (distribution asset — stays free) | Full-history exports: trajectories, match-probability history, bulk archives (M5) |
| **What-if scenarios** | In-browser 10k-run simulator + shareable scenario URLs (Phase 1.3) | Saved scenario library, cross-device (Phase 3) |
| **Edge / market (quiet middle)** | What's shipped today stays free per the ratchet: edge-board list, paper-ledger strip, value-summary card, model-vs-market panel | **Edge room depth** (login-only, unmarketed): full ledger + CLV archive, historical edge-performance explorer, edge alerts (M6) |
| **Trust & transparency** | All of it — trust tab, model health, weekly receipts, calibration. Paywalling trust would defeat its purpose | Supporter-depth annual Model Report Card (Phase 3) |
| **Affiliation** | — | Supporter badge, credits page, founding-supporter flag, "ad-free always" pledge (M7) |

---

## 2. The historical-data flywheel (starts immediately, costs nothing)

The moat in 2028 is the history recorded in 2026. Current state of history assets:

| Asset | Contents | Durable? |
|---|---|---|
| `webapp/data/drift-traj/<lid>.js` | **Public current-season** per-team trajectories (elo, proj_pts, title/playoff/releg/… odds) | ✅ season-bounded 2026-07-18 (F-2) — filtered to each league's current `season` before truncating |
| `data/odds_history.parquet` | Market odds snapshots; already accrues multi-season history indefinitely | ✅ committed nightly — doubles as the private multi-season trajectory archive, so no separate `trajectory_history.parquet` was built (F-2 found it would have duplicated these rows) |
| `data/match_prob_history.parquet` | **Private** per-match model probability snapshots | ✅ fixed 2026-07-18 (F-1) — allowlisted past `.gitignore` and staged in both refresh workflows; locally-accrued rows seeded |
| `webapp/data/weekly.js` | Weekly recap (movers, receipts, hits/misses) | ✅ archived 2026-07-18 (F-3) — dated copy written to `data/weekly-archive/<date>.json` on every run |
| `webapp/data/race-deltas.js` / `movers.js` | Day-over-day deltas with cause attribution | ✅ race-deltas archived 2026-07-18 (F-4) to `data/race_deltas_history.parquet`; `movers.js` unchanged (not in S0 scope) |

**Flywheel actions (Phase 0) — all done 2026-07-18, see `docs/PROJECT_HISTORY.md` "Intelligence Hub S0":**
- ~~**F-1 (P0, one line):** add `data/match_prob_history.parquet` to every CI commit
  step that runs `archive_odds_snapshot.py` (`refresh-daily.yml` and
  `refresh-leagues.yml`); seed with the local file if it has accumulated rows.
  *(Chip filed 2026-07-17.)*~~ **Done.**
- ~~**F-2 (P0 before first season rollover):** split public vs private trajectory
  history. Keep `webapp/data/drift-traj/<lid>.js` current-season-only and archive the
  full multi-season series privately in `data/trajectory_history.parquet` for M4/M5.~~
  **Done, with a scope adjustment:** `data/odds_history.parquet` already accrues every
  snapshot indefinitely and is already committed, so it already **is** the private
  multi-season archive — a second file would only have duplicated those rows. Fixed
  the actual gap instead: `webapp/data/drift-traj/<lid>.js` now filters to each
  league's current `season` (captured on every archived row) before truncating to
  180 points, so a rollover can no longer leak prior-season rows into the public payload.
- ~~**F-3:** archive each weekly recap to a dated file (`data/weekly-archive/2026-08-17.json`
  or dated static pages `/weekly/2026-08-17/` — the latter is also SEO surface area).~~
  **Done** — `data/weekly-archive/<date>.json`, written alongside `webapp/data/weekly.js`
  on every run.
- ~~**F-4:** append daily race-deltas to a compact parquet before overwrite.~~ **Done** —
  `data/race_deltas_history.parquet`, deduped on league+metric+to_date.
- ~~**F-5:** add CI guard tests: private history files must be strictly growing during
  the season, and public trajectory files must not contain rows outside the active
  season (catches both silent loss and accidental vault leakage).~~ **Done** —
  `scripts/validate_history_growth.py` runs as the last step of both refresh workflows,
  before the commit step, and fails the build on either violation.

---

## 3. Phase 0 — Pre-launch hardening (now → Aug 17)

Owned by the launch plan; listed here only for continuity.

- **USER:** Plausible + GSC + Resend account setup (~15 min) — gates all measurement.
- E2–E4 email capture build the moment the Resend key exists.
- Flywheel actions F-1…F-5 above.
- I2–I4 QA/freeze/launch per the launch plan.

**Exit criterion:** launch happens with measurement live, so Phase 1's gate can be read honestly.

---

## 4. Phase 1 — Free habit loops + paid-value teasers (Aug 17 → Oct 31)

Goal: maximize **weekly returning forecast users** and email list, and make the
waitlist gate meaningful by showing users *previews* of what paid buys. Everything
here is static-site/product work except the already-planned Resend capture endpoint;
zero new fixed cost.

> **Buildout status (2026-07-19):** 1.1–1.6 and the §6 copy tweak are **built and committed**
> (see `docs/PROJECT_HISTORY.md` and the retired plan referenced below). They deploy with the
> next push. **1.4's capture endpoint is live but key-gated** — it records subscribers to KV now
> and mirrors to Resend only once E1's key exists; **no sends** happen regardless (E4 rule). **1.7
> is not done** — it stays gated on A2/GSC proving league indexation before spending on ~1,100 OG
> cards. Everything here was built by an agent with no account access; the remaining Phase-0 USER
> tasks (A1 GA4, A2 GSC, E1 Resend) are the actual launch blocker, not feature work.

| # | Feature | WTP driver teased | Existing asset | Effort | Status |
|---|---|---|---|---|---|
| 1.1 | **Trajectory sparklines** on team profiles + a "race history" chart per league — **current season, free forever** (this data is public in the static payloads; the ratchet forbids gating it later). Paid (Phase 2 M4) is the private *vault*: multi-season archive + match-level history, never shipped free | Interpretation / history | `drift-traj` after F-2 season bounding | M | ✅ 2026-07-19 |
| 1.2 | **"My matchday" panel** on Home: this weekend's matches for pinned teams, ranked by leverage | Personalization / recurrence | `FavStore` + `leverageScore` (both shipped) | S | ✅ 2026-07-19 |
| 1.3 | **Shareable what-if scenarios** — encode pinned hypothetical results in the URL | Utility + viral distribution | in-browser 10k-run `runSim` (shipped) | S | ✅ 2026-07-19 (keyed on stable `fixture_id`) |
| 1.4 | **Weekly digest subscriber collection** (league-level interest, not personalized): POST to Resend Contacts once capture infra is live; **no sends in Phase 1** without explicit owner sign-off | Recurrence; measures the retention channel every analog built first | `build_weekly_recap.py` preview + Resend capture | S | ✅ 2026-07-19 capture built (key-gated; no sends) |
| 1.5 | **Dated weekly recap pages** `/weekly/<date>/` (from F-3) | History + SEO | recap builder | S | ✅ 2026-07-19 |
| 1.6 | **Waitlist upsell placements** beside each free feature ("the full multi-season vault is a supporter feature") with distinct `waitlist_click` source tags, plus a **monthly vs annual preference toggle** on the waitlist form (measures annual appetite before any billing exists) | — (measures WTP per feature + billing-cadence mix) | waitlist form (shipped) | S | ✅ 2026-07-19 (`upsell_click` + `src-*`/`cadence-*` tags) |
| 1.7 | Dynamic per-league OG cards (launch-plan C11) + team pages (~1,100, after GSC proves league indexation) | — (distribution) | `build_share_cards.py`, `build_static_pages.py` | M | ⬜ gated on A2/GSC |

Deliberately **not** in Phase 1: any auth, payments, per-user server state, or
scheduled email sends. Phase 1 collects subscribers and waitlist intent only.

**Gate reading (Oct 31):** build the paid tier only if waitlist joins ≥ **2% of
returning users AND ≥150 absolute** (the absolute floor keeps a tiny denominator from
green-lighting a tier with single-digit buyers). Read per-source tags from 1.6 to
learn *which* promised feature pulls hardest — that feature ships first in Phase 2.

---

## 5. Phase 2 — Paid supporter tier MVP (gate-dependent; Nov 2026 → Feb 2027)

### Infrastructure (startup fixed cost < $40/mo; scale ceiling ~$60/mo; each line has a free on-ramp)

| Component | Choice | Cost |
|---|---|---|
| Payments | Stripe Checkout + Customer Portal (no auth to build for billing) | $0 fixed; 2.9% + 30¢/txn |
| Functions | Vercel serverless (same host as the planned Resend proxy) | Free tier → $20/mo Pro if needed |
| Entitlements | Upstash Redis (email → plan, alert prefs) | Free tier → ~$10/mo |
| Email | Resend | Free 3k/mo → $20/mo |
| Auth | **Magic-link via Resend** → signed token in localStorage. No passwords, no sessions DB. Billing managed entirely in Stripe's portal | $0 |
| Analytics | Plausible (already planned) | ~$9/mo |

Site stays static; paid features fetch entitlement-gated data from functions, or
arrive by email. This honors the cost-gate decision: ~$10/mo at the start if the
free tiers hold, with an explicit ~$60/mo ceiling before another cost review.

### Build order (each module independently shippable; ordered by default, reordered by 1.6 signal)

- **M1 — Checkout + entitlement + supporter badge.** Stripe Checkout with monthly
  **and annual** prices and the **14-day card-required trial** (`trial_period_days=14`);
  Stripe webhook → KV; magic-link unlock in-app; supporter badge in masthead. Trial
  UX rules: labeled "free trial" everywhere; configure Stripe Billing customer emails
  and hosted cancellation portal before launch; verify the trial-ending reminder in
  test mode for card-required trials ≥ 7 days; cancel = one click in the Stripe portal.
  *Everything else depends on this.*
- **M2 — Threshold alerts.** Nightly job (rides the existing refresh chain — no new
  daily process) diffs `drift`/`race-deltas` against per-user thresholds → Resend.
  Conservative defaults (playoff/title/releg odds crossing 25/50/75%, clinch/elimination)
  to prevent alert fatigue.
- **M3 — Personalized weekly briefing.** `build_weekly_recap.py` output filtered to the
  user's pinned teams/leagues; "what the model changed its mind about, for you."
- **M4 — Forecast time machine (the vault).** Private multi-season trajectory archive
  (`trajectory_history`) + private match-level probability history
  (`match_prob_history`), served entitlement-gated from functions — data that was
  never public, so nothing is taken away. The free current-season view (1.1) is the
  permanent front door; the vault gets more valuable every single day.
- **M5 — Supporter downloads.** Full-history CSVs (trajectories, per-match probability
  history). **Basic current-table CSVs stay free** — `/open-data/` is a distribution
  asset (ClubElo lesson), not a paywall casualty. Data-licensing review per source
  before expanding scope (CI report App. B).
- **M6 — Quiet-middle edge room.** Ratchet-compliant scoping: the edge surfaces
  already public (edge-board list, ledger strip, value-summary card, model-vs-market
  panel) **stay free**. The paid room is depth that never shipped: full ledger + CLV
  archive, historical edge-performance explorer by bucket/league/season, and edge
  alerts. Login-only; excluded from marketing, SEO, share cards, and announcements;
  responsible-gambling copy at the door; honest negative-ROI backtest shown (it's a
  trust feature as much as a tool). Outright-market recommendations respect the
  ≥25%-season-progress skill gate (CURRENT_STATE standing rule).
- **M7 — Affiliation.** Supporters' credits page, early-access changelog, founding-
  supporter flag for year-one joiners.

**Kill criterion:** gate fails → do **not** build M1–M7. Fallback: GitHub Sponsors /
Ko-fi donation link (zero infra), keep compounding Phase 1 loops and history, re-read
the gate after the 2027 Women's World Cup traffic wave.

---

## 6. The "ad-free" promise

No ads exist and none are planned (CI report gates ads on RPM-vs-trust measurement).
Do not ship ads in order to sell their absence. **Action:** reword the support card's
"ad-free" bullet to "ad-free, always — supporters keep it that way," converting a null
feature into an affiliation pitch. One-line copy change, Phase 1. **✅ Done 2026-07-19.**

---

## 7. Phase 3 — Retention + expansion (Mar → Jul 2027)

| Item | Rationale / gate |
|---|---|
| **Annual Model Report Card** (season-end, per league): full-season graded receipts, free + shareable; supporter version with per-team depth | The trust position, weaponized as a content moment; uses accumulated history |
| **Women's soccer runway** — NWSL/WSL depth now, evaluate a women's international model before WWC 2027 (Brazil) | Emptiest competitive field (CI report §6.9); timing asset |
| **Saved scenarios** — persist supporters' what-if simulations (KV) | Upgrade of 1.3 once auth exists |
| **Spanish landing pages** (La Liga/Liga MX) | Gate: localized pages must earn material non-branded impressions + comparable email conversion over a full cycle (CI report) |
| **Embeds / API exploration** — embeddable race tables; possible $15/mo data tier | Gate: licensing review first; only with evidence from M5 download usage |
| **Quarterly competitive monitor** | Silver Bulletin club model, FotMob/Sofascore native probabilities, Football Data Lab pricing (CI report App. B) |
| **Churn instrumentation** | Stripe cohort retention + Plausible return cohorts; paid North star shifts from MRR to 90-day retention |

---

## 8. Metrics and review cadence

- **North star (free):** weekly returning forecast users (Plausible) — unchanged from launch plan.
- **Phase 1 adds:** email list growth, waitlist % of returning users **by feature-source tag**.
- **Phase 2 adds:** trial starts, **trial → paid conversion rate** (the primary paid
  metric; healthy card-required benchmarks run ~40–60%), annual vs monthly mix,
  supporter MRR, alert open/click rates.
- **Phase 3 adds:** 90-day supporter retention, download/API usage.
- **Cadence:** monthly roadmap review against gates; quarterly competitive re-check.
  Every phase boundary is a gate, not a date — dates here are defaults, evidence moves them.

## 9. Risks specific to this roadmap

| Risk | Mitigation |
|---|---|
| Solo-operator sprawl (CI report risk #4) | Every Phase 2 module rides the existing nightly chain; nothing adds a recurring manual task; modules shippable independently |
| Edge room erodes trust position | Quiet-middle rules in §5-M6 are standing policy; review annually |
| History leak repeats silently | F-5 CI guard tests for private growth and public current-season bounds |
| Alert fatigue → churn | Conservative default thresholds; per-user frequency cap |
| Paid tier built on a failed gate out of enthusiasm | Kill criterion in §5 is explicit; donations fallback preserves affiliation revenue |
| Accidentally gating something that was free (trust damage from "taking away") | Free-floor ratchet (owner decision #4) is standing policy; the free/paid line is structural — static payloads = free, function-served vault = paid — so a paywall can't silently creep into shipped free surface |
| Trial abuse (serial trialing) | Card-required trial makes it self-limiting; not worth further engineering at this scale |
