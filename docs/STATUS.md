# Entenser — Consolidated Status

**Last updated:** 2026-07-19 · **Owner:** Ryan · **Launch target:** Monday **2026-08-17**

This is the single hub that reconciles the four planning docs so you don't have to. It
answers: *where are we, what do I act on, what's broken, what's left to build.* Each row
points back to the canonical doc — this page is a dashboard, not a replacement.

**Source docs:** [product-roadmap-2026-07.md](product-roadmap-2026-07.md) (feature roadmap) ·
[superpowers/plans/2026-08-17-public-launch.md](superpowers/plans/2026-08-17-public-launch.md) (launch plan) ·
[social-media-strategy-2026-08-launch.md](social-media-strategy-2026-08-launch.md) (social) ·
[remaining-external-dependencies-2026-07-11.md](remaining-external-dependencies-2026-07-11.md) (spend/decision ledger) ·
[CURRENT_STATE.md](CURRENT_STATE.md) (model config) · [PROJECT_HISTORY.md](PROJECT_HISTORY.md) (narrative history).

---

## 1. Where we are — one paragraph

The **free static product is live and shipping** on entenser.com: 56 leagues, full
forecasts/tables/trust pages, plus the six roadmap Phase‑1 features that shipped today
(sparklines, race‑history chart, My matchday, shareable scenarios, waitlist upsells +
annual toggle, dated weekly pages). The **email‑capture and paid‑tier code is built but
inert** — it can't activate until you create three external accounts. **Nothing is
monetized, nothing sends email, and no analytics are recording yet** — all three are
gated on ~15 minutes of your account setup, which is the single highest‑leverage thing
you can do. Launch is **~4 weeks out** (Aug 17); the code is essentially ready, the
blockers are accounts, content posting, and a few decisions/spends only you can make.

---

## 2. 🔴 What YOU need to act on

### 2a. Account setup — ~15 min total, unblocks almost everything

Do these three first. Runbook detail in the [launch plan §"Launch runbook"](superpowers/plans/2026-08-17-public-launch.md).

| # | Action | Time | Unblocks | How |
|---|---|---|---|---|
| ~~**A1**~~ | ~~**Google Analytics 4**~~ — ✅ **done 2026‑07‑23.** ID `G-GVSLY1KBHQ` is wired into the SPA *and* the static SEO pages. Google's "install a tag" step needed nothing — the code was already there (A1a). **Remaining: deploy, then confirm GA4 Realtime shows a session** (that's I2). | — | *All* measurement. Gates the Oct 31 paid‑tier decision. | Done in code; verify at analytics.google.com → Reports → Realtime |
| ~~**A2**~~ | ~~**Google Search Console**~~ — ✅ **done 2026‑07‑23** (domain property verified). **Remaining: submit the sitemap** (C10) at `https://entenser.com/sitemap.xml`, then wait ~1–2 weeks for indexing before judging the 1.7 OG‑cards gate. | — | Sitemap submission (C10) + the 1.7 OG‑cards gate (needs proof leagues are indexing) | search.google.com/search-console → Sitemaps → enter `sitemap.xml` |
| **E1** | **Resend** — add `entenser.com` domain (SPF/DKIM DNS records), create an API key + an Audience "Entenser interest", store the key as a **secret on the host, never in the repo** | ~5–10 min | Email capture starts mirroring to Resend (it's already recording to KV; see bug #1 caveat). **No emails send** regardless until you sign off. | resend.com → Domains / API Keys / Audiences |

### 2b. Infrastructure — the API isn't deployed

| Action | Why | Notes |
|---|---|---|
| **Create/link the Vercel project + set its secrets** (`VERCEL_TOKEN`, `VERCEL_ORG_ID`, `VERCEL_PROJECT_ID`) | The Intelligence API (email endpoint, magic‑link auth, Stripe webhook) **fails to deploy on every push** — see bug #1. All that server code exists and is tested but has nowhere to run. | This is the same "no Vercel account exists yet" gap the S5 history entry flagged. Until it's linked, the webapp works but nothing server‑side does. |

### 2c. Launch execution (Aug 14–17) — yours to run

- **Aug 14:** content freeze (I3).
- **Aug 17 (Mon):** post the launch announcements (H5 — drafts ready in [launch-announcements.md](launch-announcements.md)), go live (I4). **Block two reply windows** that day (social plan §6).
- **Social warm‑up starts now:** claim handles, comment in r/MLS & r/NWSL without linking for 1–2 weeks first (social plan §6 timeline).

### 2d. Decisions & spends (no deadline, but they gate later work)

| Decision | When it matters | Est. cost |
|---|---|---|
| Buy an **Odds API tier** (leagues + frequency) | Unblocks real model‑vs‑market depth, CLV, edge history | $50–300+/mo |
| **Legal/compliance review** before *any* monetization | Required before affiliate links / paid tier / betting‑adjacent copy | $500–2,500 one‑time |
| **Paid social** test | Only *after* GA4 live + 2 organic hooks proven | $500–1,000 test |
| **Weekly digest email sends** sign‑off | Capture is built; sends need your explicit go‑ahead | Time |

---

## 3. 🐛 Outstanding bugs & things needing attention

| # | Issue | Severity | Status / cause | Action |
|---|---|---|---|---|
| 1 | **Intelligence API deploy fails on every push** | Medium (blocks all server features) | Not a code bug — the "Deploy Intelligence API" workflow dies at the Vercel credential step (`--token` missing) because the Vercel project/secrets don't exist. Failed identically on the last 3 pushes. | Fixed by **2b** (link Vercel). Until then, email capture, auth, and Stripe can't run in prod. |
| 2 | **Nightly data refresh failed 2026‑07‑19** | Medium (if it recurs) | Was green Jul 16/17/18, failed today with exit code 2 and `"failures": {}` (no per‑league failure logged) — looks transient/partial. A *persistent* failure would freeze the data payloads **and** the F‑3 weekly archive. | Watch tomorrow's run. If it fails again, dig into the `finalize` step. |
| 3 | **Dated `/weekly/<date>/` pages return 404** | Low (transient, self‑resolving) | The pages build correctly but from committed `data/weekly-archive/*.json`, and none are committed yet (feature is 1 day old; today's nightly — bug #2 — didn't commit one). Wiring is correct end‑to‑end. | Resolves automatically on the **first successful nightly refresh** (which commits an archive file and triggers a rebuild). No code change needed. |
| 4 | **1 test fails: `test_intelligence_state_replay`** | Low (pre‑existing, non‑blocking) | Monte‑Carlo replay tolerance breach (spoon odds 3.4pp vs a 3.0pp tolerance). **Proven to fail identically before any recent work** — it's data‑drift/flakiness, not a regression. Rest of suite: 1179 passed. | Decide later: widen tolerance or re‑baseline the snapshot. Not launch‑blocking. |
| 5 | Vercel CLI is a few versions behind (local tooling) | Trivial | Session‑start notice only. | `npm i -g vercel@latest` whenever convenient. |

---

## 4. 🔨 Remaining builds (I can do these — mostly gated, not blocked)

| Build | Gated on | Notes |
|---|---|---|
| **1.7 — per‑league OG cards + ~1,100 team pages** | A2/GSC proving league pages actually index | The one Phase‑1 item not yet built. Don't spend the render effort until indexation is confirmed. |
| **Phase 2 (M1–M7) — paid supporter tier** | **Oct 31 gate:** waitlist joins ≥ **2% of returning users AND ≥ 150 absolute** | Much of M1 (checkout/entitlement/auth plumbing) already exists from Intelligence Hub S5. If the gate passes, time‑to‑paid is mostly Stripe config, not new engineering. Kill criterion: gate fails → build none of it, fall back to a donation link. |
| **Weekly digest email *sends*** | Your explicit sign‑off (§2d) | Capture + templates exist; the send loop does not. Standing rule: no sends without sign‑off. |
| **Phase 3 — annual report card, women's runway (NWSL/WSL → WWC 2027), saved scenarios, Spanish pages, embeds/API** | Later gates (see roadmap §7) | Post‑launch; each has its own evidence gate. |

**Deliberately *not* building** (deferred by decision): Plausible dashboard, dynamic OG cards at scale, ads (gated on RPM‑vs‑trust), contextual sponsorship, quarterly competitor monitor. See [launch plan "Post‑launch backlog"](superpowers/plans/2026-08-17-public-launch.md).

---

## 5. ✅ Done & live — you can stop tracking these

- **Free static product:** 56 leagues, forecasts, tables, projected points, what‑if sim, trust/model‑health/calibration pages, mobile layout, locale + odds‑format toggle. Live.
- **Launch workstreams:** B (data‑honesty labels), C1–C9 (crawlable SEO pages + sitemap + robots), D (messaging/trust on‑ramp), F (locale), G (supporter waitlist), H1–H4 (distribution content incl. after‑the‑World‑Cup page, open‑data CSVs, announcement drafts), I1 (QA pass), A1a (GA4 adapter code — waiting only on the ID from A1).
- **Intelligence Hub S0–S6:** history flywheel + guards, stable IDs, shared sim engine, reproducible‑state archiving, canonical intelligence events, secure‑delivery code (magic‑link auth, KV entitlements, Stripe webhook, rate limiting), and the first live‑data Intel panel. (Code done; activation waits on Vercel + accounts.)
- **Roadmap Phase 1 (shipped 2026‑07‑19, live):** 1.1 sparklines + race‑history chart · 1.2 My matchday · 1.3 shareable what‑if URLs · 1.4/E2/E3/E4 email capture (inert, key‑gated) · 1.5 dated weekly pages · 1.6 waitlist annual toggle + source‑tagged upsells · §6 ad‑free copy.

---

## 6. 📅 Key dates & gates

| Date | Milestone |
|---|---|
| **Now → Jul 26** | Social warm‑up: claim handles, participate in communities without linking |
| **Jul 27 → Aug 9** | Social "soft proof": a few no‑hype example posts; private feedback from 5–10 people |
| **Aug 10 → 16** | Freeze & queue: launch copy freeze Aug 14, refresh links with UTMs |
| **Aug 17 (Mon)** | **LAUNCH** — announcements, go‑live, two reply windows |
| **Aug 17 → 23** | Launch week: Reddit → Show HN → analytics communities, in that order |
| **Oct 31** | **Phase‑1 → Phase‑2 gate:** read waitlist conversion; decide whether to build the paid tier |

---

## 7. The single most important thing

**Do the account setup that's left (E1 Resend — A1 GA4 and A2 GSC are done) and link the Vercel
project.** That one afternoon unblocks measurement, email capture, the API, and the
launch's measurement half — and it's the difference between launching blind and
launching instrumented. Everything else is either already done, gated on a future date,
or a decision that can wait.
