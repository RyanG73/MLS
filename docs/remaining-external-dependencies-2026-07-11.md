# Remaining External / Decision-Gated Work — 2026-07-11

This is the honest accounting of what the public launch still needs that **could not be done
autonomously in-repo** — because it spends money, stands up an external account, publishes
outward-facing content, or is a business/legal decision. Everything code-shaped that the two
Codex reports (2026-07-10 business plan, 2026-07-11 execution report) called for is either
already shipped or was completed in the 2026-07-11 completion pass (see
`docs/PROJECT_HISTORY.md`). What remains is genuinely a set of *decisions and spends* for the
owner, not engineering tasks.

## Status headline

The repo is **launch-ready as a free, static, informational product today.** 37 payloads
validate clean; the full test suite is green; the landing Command Center shows value with no
live odds; trust/legal pages exist; mobile has no overflow at 375px. The items below are what
separate "deployable" from "marketed, monetized, and legally reviewed."

## Update — 2026-07-11 (A/C/B pass)

Since the original ledger, the owner **deployed the site** and confirmed the product stays
**informational (no gambling picks/touts)** — which lowers the legal-review urgency (item 5).
Three engineering items were then completed in-repo:

- **(A) OG share images — DONE.** `scripts/build_share_cards.py` generates four 1200×630 cards
  (branded OG + title-race/relegation/movers), wired into `<head>` as `og:image` +
  `twitter:summary_large_image`, and into `build_all.sh` for nightly refresh.
- **(C) Nightly build job — INSTALLED & VALIDATED.** `com.mls.buildall.plist` was found already
  loaded but with `runs=0` (never fired). Triggered one run through launchd
  (`launchctl kickstart gui/501/com.mls.buildall`): `runs=1`, `state=running`, clean startup —
  the only stderr is the expected `ODDS_API_KEY not set`. The 06:00 daily schedule is now proven
  to work in launchd's environment.
- **(B) Analytics instrumentation — SHIPPED (provider account still needed).** A Plausible
  `track()` layer + 8 tagged events are wired in, active only on `entenser.com`. **Remaining
  owner step:** create the (free-trial/paid or self-hosted) Plausible site for `entenser.com`
  so events are recorded — no code change needed when it exists.

## The ledger

| # | Item | Why it's blocked | Recommended next action | Est. cost |
|---|---|---|---|---|
| 1 | **Production deploy** — ✅ DONE | — | Site is live. Re-run visual/OG QA on the domain (item 8). | $0–20/mo |
| 2 | **Web analytics** — instrumentation ✅ shipped | Only the provider account remains. | Create the Plausible site for `entenser.com` (or self-host / switch `ANALYTICS.provider` in `index.html`). Events flow automatically once the domain is registered. | $0–20/mo |
| 3 | **Email capture backend** | The landing already has a signup UI scaffold (`commandSignupHTML`/`bindCommandSignup`) but no backend. Standing up a list is user-gated. Resend is available as an integration. | Choose a form endpoint (Resend audiences, Buttondown, Beehiiv). Point the scaffold's submit at it. Do **not** send any email without explicit owner sign-off. | $0–30/mo |
| 4 | **Paid/live odds coverage** | The real cost center. Row-level model-vs-market depth and CLV history stay thin without broader odds. Archival/edge/ledger code is ready and waiting for the data. | Decide leagues + refresh frequency, buy an Odds API tier, let `data/odds_history.parquet` and the closers files accrue. CLV becomes meaningful after ~100+ settled fixtures. | $50–300+/mo |
| 5 | **Legal / compliance review** | Business risk decision. Required *before* any affiliate links, paid picks, or jurisdiction-specific betting calls. | Keep launch informational (already done). Commission a review before monetizing anything betting-adjacent. Add Terms + a contact page. | $500–2,500 one-time |
| 6 | **Paid acquisition** | Spends money; should follow, not precede, analytics + a strong landing state (both now in place). | Only after #2 ships: a $500–1,000 Reddit/X test around the mid-August Big-5 launch window, optimizing for email signup, not subscription. | $500–2,000 test |
| 7 | **Publish the launch content** | Five drafted articles live in `docs/content/`; publishing is outward-facing. | Owner reviews, refreshes any numbers if payloads changed, publishes on the chosen channel (site blog / newsletter). | Time |
| 8 | **Visual QA on the live host** | Can only be done against the deployed domain, not localhost. | Repeat the 375px + desktop pass on the real URL; confirm the new `og:image` (`summary_large_image`) previews correctly in a debugger (Facebook Sharing Debugger / Twitter Card Validator). | Time |

## Engineering follow-ons

- **OG share image — ✅ DONE** (see the 2026-07-11 update above).
- **Email backend (item 3)** and **paid odds (item 4)** remain the highest-value external
  unblocks; both have code waiting for them.

## What is explicitly NOT blocked (already done, don't re-do)

- Slice/drift/edge-board/movers/paper-ledger infrastructure — shipped and wired into
  `build_all.sh`.
- League expansion (Brazil/Japan/Nordics/Poland/Argentina/England National League) — live.
- Command Center landing, Trust cards, weak-spots, market-disagreement card, mobile layout —
  present and verified.
- Trust/legal content (About / Data sources / Responsible gambling / Privacy) + attribution
  footer — shipped 2026-07-11.
- Model feature hunt — deliberately deferred; diagnostics showed no Brier gain, so there is no
  pending model change to chase for launch.
