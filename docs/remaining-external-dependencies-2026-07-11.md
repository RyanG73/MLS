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

## The ledger

| # | Item | Why it's blocked | Recommended next action | Est. cost |
|---|---|---|---|---|
| 1 | **Production deploy** | Outward-facing; needs owner's hosting account + DNS. A `CNAME` for `entenser.com` already exists in the repo. | Owner connects the repo to Cloudflare Pages / Netlify / Vercel (all serve `webapp/` statically) and points `entenser.com` at it. Verify the static `<title>`/OG tags render on the live domain. | $0–20/mo |
| 2 | **Web analytics** | Requires an account + a script tag decision (privacy posture). | Pick a privacy-preserving analytics provider (Plausible / Fathom / PostHog), add its snippet to `webapp/index.html`, wire the events the report listed (league view, tab click, team open, match expand, signup). | $0–20/mo |
| 3 | **Email capture backend** | The landing already has a signup UI scaffold (`commandSignupHTML`/`bindCommandSignup`) but no backend. Standing up a list is user-gated. Resend is available as an integration. | Choose a form endpoint (Resend audiences, Buttondown, Beehiiv). Point the scaffold's submit at it. Do **not** send any email without explicit owner sign-off. | $0–30/mo |
| 4 | **Paid/live odds coverage** | The real cost center. Row-level model-vs-market depth and CLV history stay thin without broader odds. Archival/edge/ledger code is ready and waiting for the data. | Decide leagues + refresh frequency, buy an Odds API tier, let `data/odds_history.parquet` and the closers files accrue. CLV becomes meaningful after ~100+ settled fixtures. | $50–300+/mo |
| 5 | **Legal / compliance review** | Business risk decision. Required *before* any affiliate links, paid picks, or jurisdiction-specific betting calls. | Keep launch informational (already done). Commission a review before monetizing anything betting-adjacent. Add Terms + a contact page. | $500–2,500 one-time |
| 6 | **Paid acquisition** | Spends money; should follow, not precede, analytics + a strong landing state (both now in place). | Only after #2 ships: a $500–1,000 Reddit/X test around the mid-August Big-5 launch window, optimizing for email signup, not subscription. | $500–2,000 test |
| 7 | **Publish the launch content** | Five drafted articles live in `docs/content/`; publishing is outward-facing. | Owner reviews, refreshes any numbers if payloads changed, publishes on the chosen channel (site blog / newsletter). | Time |
| 8 | **Visual QA on the live host** | Can only be done against the deployed domain, not localhost. | After #1, repeat the 375px + desktop pass on the real URL; confirm OG/Twitter share cards preview correctly (they use `summary`, no image yet — consider adding an OG image). | Time |

## One concrete engineering follow-on worth flagging

- **OG share image.** `<meta name="twitter:card" content="summary">` has no image. A generated
  share card (title race / relegation race / biggest mover) would materially improve social
  CTR — the business report's Sprint 3 asked for chart cards. This *is* buildable in-repo
  (SVG→PNG from payload data) and is the best next code task once a deploy target exists.

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
