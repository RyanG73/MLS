# Entenser — Consolidated Status

**Last updated:** 2026-07-24 · **Owner:** Ryan · **Launch target:** Monday **2026-08-17**

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
annual toggle, dated weekly pages). The **Intelligence API is deployed and live**
(2026‑07‑24, `https://mls-five.vercel.app/v1/public/config` → 200 — custom domain
`api.entenser.com` still needs DNS attached). **Email capture is now fully live**: GA4,
GSC, and Resend are all set up and wired end‑to‑end — a real `/public/subscribe` call
against production returned `"resend": true`, confirming the contact actually landed in
the Resend Audience. **Nothing is monetized and no *broadcast* emails send** (that still
needs your explicit sign‑off, §2d) but capture itself is live. Launch is **~4 weeks
out** (Aug 17); the code is essentially ready, the remaining blockers are the custom
domain, content posting, and a few decisions/spends only you can make.

---

## 2. 🔴 What YOU need to act on

### 2a. Account setup — ~15 min total, unblocks almost everything

Do these three first. Runbook detail in the [launch plan §"Launch runbook"](superpowers/plans/2026-08-17-public-launch.md).

| # | Action | Time | Unblocks | How |
|---|---|---|---|---|
| ~~**A1**~~ | ~~**Google Analytics 4**~~ — ✅ **done 2026‑07‑23.** ID `G-GVSLY1KBHQ` is wired into the SPA *and* the static SEO pages. Google's "install a tag" step needed nothing — the code was already there (A1a). **Remaining: deploy, then confirm GA4 Realtime shows a session** (that's I2). | — | *All* measurement. Gates the Oct 31 paid‑tier decision. | Done in code; verify at analytics.google.com → Reports → Realtime |
| ~~**A2**~~ | ~~**Google Search Console**~~ — ✅ **done 2026‑07‑23** (domain property verified). **Remaining: submit the sitemap** (C10) at `https://entenser.com/sitemap.xml`, then wait ~1–2 weeks for indexing before judging the 1.7 OG‑cards gate. | — | Sitemap submission (C10) + the 1.7 OG‑cards gate (needs proof leagues are indexing) | search.google.com/search-console → Sitemaps → enter `sitemap.xml` |
| ~~**E1**~~ | ~~**Resend**~~ — ✅ **fully done and verified live 2026‑07‑24.** Domain/DNS, API key, and Audience all set up; `RESEND_API_KEY`/`RESEND_AUDIENCE_ID`/`RESEND_FROM_EMAIL` are stored as Vercel production env vars. A live `POST /v1/public/subscribe` test (using Resend's `delivered@resend.dev` test address, nothing real emailed) returned `{"ok":true,"resend":true}` — the contact landed in the Resend Audience. `RESEND_WEBHOOK_SECRET` still unset (optional, only needed once a Resend webhook exists). | — | Email capture now mirrors to Resend on every signup. **Broadcast/digest sends still need your explicit sign‑off** (§2d) — capture ≠ sending. | Nothing left to do here. |

### 2b. Infrastructure — ✅ Vercel linked, API deployed and verified (2026‑07‑24)

| Action | Why | Notes |
|---|---|---|
| ~~Create/link the Vercel project + set its secrets~~ | ✅ Done. `VERCEL_TOKEN`/`VERCEL_ORG_ID`/`VERCEL_PROJECT_ID` are set as GitHub secrets on `intelligence-api-production`; project `ryang73/mls` is linked and deploys cleanly — see bug #1. | Remaining infra work: attach the `api.entenser.com` custom domain (Vercel dashboard → Domains). Resend env vars are done (E1 above). |

### 2c. Launch execution (Aug 14–17) — yours to run

- **Aug 14:** content freeze (I3).
- **Aug 17 (Mon):** post the launch announcements (H5 — drafts ready in [launch-announcements.md](launch-announcements.md)), go live (I4). **Block two reply windows** that day (social plan §6).
- **Social warm‑up starts now:** claim handles, comment in r/MLS & r/NWSL without linking for 1–2 weeks first (social plan §6 timeline).

#### Open-access promo switch — run a "everything free" push

Drops the paid-plan requirement on every Intel endpoint for a fixed window, without touching anyone's real plan. Needs `ADMIN_TOKEN` set in the Vercel project (shared secret; the endpoint **fails closed** if it's unset, so nothing is exposed before you set it).

**Open it** — `days` defaults to 7, max 90:

```bash
curl -X POST https://api.entenser.com/v1/admin/open-access \
  -H "X-Admin-Token: $ADMIN_TOKEN" -H 'Content-Type: application/json' \
  -d '{"days":7,"note":"launch week"}'
```

**Check what's running** (also public at `/v1/public/config`, which is what the site reads to drop its lock chrome):

```bash
curl https://api.entenser.com/v1/admin/open-access -H "X-Admin-Token: $ADMIN_TOKEN"
```

**Close it early:**

```bash
curl -X DELETE https://api.entenser.com/v1/admin/open-access -H "X-Admin-Token: $ADMIN_TOKEN"
```

What it does and does not do:

- **Auto-closes at the expiry** even if you forget — the window is enforced on every read, not just by a TTL. A promo cannot be left open by accident; that's the failure mode that costs money.
- **Never waives the login.** Open access means "no payment", not "no account" — Intel state is per-user (workspaces, journal, saved teams), so a free magic-link signup is still the front door. Requests with no token, or a forged one, stay 401.
- **Does not resurrect a `canceled` account.** Cancellation is a deliberate state, not a missing entitlement.
- Swap the host for `http://127.0.0.1:8787` to exercise it locally against `scripts/dev_intelligence_server.py`.

Built + tested 2026‑07‑23: `server/open_access.py`, `api/admin/open_access.py`, `api/pub/config.py`, bypass wired at the single chokepoint `bearer_user()` in `server/api_support.py`. 16 tests in `tests/test_open_access.py`. Verified end‑to‑end on genuinely gated endpoints (`/intel/journal`, `/intel/workspaces`): 401 → 200 → 401 across close/open/close. **Live now that the API is deployed (§2b)** — confirmed via `GET /v1/public/config` returning 200.

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
| 1 | ~~**Intelligence API deploy fails on every push**~~ — ✅ **fixed 2026‑07‑24**, `https://mls-five.vercel.app/v1/public/config` returns 200 (custom domain not attached yet — see §7) | ~~Medium~~ | Was five stacked issues, not one: (a) Vercel project/secrets never existed — fixed by linking the project and setting `VERCEL_TOKEN`/`VERCEL_ORG_ID`/`VERCEL_PROJECT_ID` as GitHub secrets on `intelligence-api-production`; (b) Vercel's Python build now needs `uv` on the CI runner, added to `deploy-api.yml`; (c) `pyproject.toml` had zero declared dependencies and Vercel's `uv` builder reads it *instead of* `requirements-api.txt` when both exist, so numpy/requests/Pillow silently never installed; (d) that revealed a `.python-version` mismatch (3.13 vs the runtime's actual 3.12, a numpy binary-incompatibility); (e) with those fixed, `api/public/*` was still missing from every deploy — confirmed via a local `vercel build` that every other `api/` subpackage appeared in the function's file map except `api/public`, i.e. Vercel silently drops any directory literally named `public`. Renamed to `api/pub` (route strings like `/public/config` are untouched, they're string literals in `api/index.py`, not tied to the package name). | Done. Custom domain `api.entenser.com` still isn't in DNS yet (`NXDOMAIN`) — the live URL today is the Vercel-assigned `mls-five.vercel.app`; attaching the domain is a separate follow-up. |
| 2 | ~~**Nightly data refresh failing**~~ — ✅ **fixed 2026‑07‑23** | ~~Medium~~ | **Not transient — it failed 5 nights running (Jul 19–23), and the earlier "looks transient/partial" reading was wrong.** The build itself succeeded every night (47 leagues, 836 teams, `"failures": {}`, validation ok); the run died on the *last* command of the `finalize` step, `publish_intelligence_artifacts.py`, which exits 2 when Upstash is unprovisioned. Because "Commit and push if changed" runs after it with no `if: always()`, five nights of good data were built and discarded — the last CI data commit was `a594590` (Jul 18); everything since was hand‑committed locally, which is why the site looked current and this stayed invisible. The weekly `refresh-leagues.yml` had the identical bug (last green Jul 6). | Fixed by passing the flag the script already supported: `--allow-missing-config` in both workflows. **Drop the flag once the `UPSTASH_*` secrets exist (§2b)** so a real publish failure is loud again. |
| 3 | ~~**Dated `/weekly/<date>/` pages return 404**~~ — ✅ **resolved, verified live 2026‑07‑23** (`/weekly/2026-07-21|22|23/` all return HTTP 200) | Low | The pages build from committed `data/weekly-archive/*.json`. The old note said this "resolves automatically on the first successful nightly refresh" — that was never going to happen, because bug #2 meant no nightly refresh *could* succeed. Archives through `2026-07-23.json` are now committed (via local runs), and CI can commit again as of the bug #2 fix. | Should already be resolved on the live site. Verify a dated URL after the next nightly run. |
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

**Attach the `api.entenser.com` custom domain to the Vercel project.** Everything else in
account setup is done: A1 GA4, A2 GSC, and E1 Resend (domain/DNS, API key, Audience, and the
Vercel env vars) are all live — a real subscribe call against production confirmed a contact
landed in Resend. The Intelligence API itself is deployed and working as of 2026‑07‑24 (bug #1's
five stacked build issues are all fixed), but today it only answers on the Vercel‑assigned
`mls-five.vercel.app`; `api.entenser.com` still returns `NXDOMAIN`. Attaching the domain (Vercel
dashboard → Domains) is what makes the API reachable at the URL the docs/webapp actually expect.
Everything else is either
already done, gated on a future date, or a decision that can wait.
