# Premium site UX review — mobile then desktop

Reviewing every main page of the subscriber site at an iPhone viewport
(375x812) first, then desktop (1280x800), fixing layout order, wording, and
aesthetics as we go.

**Paused 2026-07-23 after Home.** Resume with the prompt at the bottom.

## How to run the review

The mirror is the local preview server, **not** an iOS Simulator — this Mac has
Command Line Tools only (no Xcode, so `xcrun simctl` is unavailable). Install
Xcode + `sudo xcode-select -s /Applications/Xcode.app` if a real simulator is
ever wanted; the browser pane at 375x812 has been faithful otherwise.

- Webapp: `.claude/launch.json` config `webapp` -> `http://localhost:8123`
- Intel (signed-in): `./scripts/intel_preview.sh` prints a one-time magic link.
  Sessions last 1 hour; magic-link tokens are single-use, so a lost session
  needs a fresh run — revisiting the old URL can never work.
- `./scripts/intel_preview.sh free` seeds a free account to see the gated view.

**Measure, do not eyeball.** Screenshots of this app lie: league tables render
async, so a capture taken at paint time showed "Biggest Movers" at y=760 when
`getBoundingClientRect()` moments later put it at y=1479. Every verdict below is
anchored to live DOM measurements.

Main pages (from the mobile tab bar): Home `/`, Matches `?league=command`,
Leagues `?league=leagues`, Intel `?league=intel`, Account `?league=account`,
plus Rankings `?league=power` and league detail `?league=epl`.

## Home — mobile — DONE 2026-07-23

Verdict: **shipped**. Measured before/after in the live DOM.

| | before | after |
|---|---|---|
| Upcoming Matches offset | y=1330 (below fold) | y=324 |
| Biggest Movers offset | y=1479 | y=573 |
| `--txt-3` contrast on `--ink-0` | 3.27:1 (188 elements, fails AA) | 4.58:1 |
| Smallest repeated label | 8px x76 (`.hx-scard .lg`) | 11px |
| Tap targets under 44px | 43 | 30 |
| Horizontal overflow | none | none (docW 375 = winW) |

Changes:
- `--txt-3` `#54665b` -> `#6b7d71`. Single token, lifts every page. `--txt-4`
  added holding the old value for decorative marks only.
- Mobile `grid-template-areas` reordered `tag odds table b fix movers news`
  -> `tag fix movers odds table b news`. Volatile content first, reference
  second, ambient last. Desktop grid untouched.
- `h1` tagline replaced by a live-state tape (`liveStateHTML`): fixture count in
  the next 48h, league count, and the largest probability move. Each clause
  drops independently when its data is missing. The tagline survives as
  `.hx-sub` using the lead copy `.interface-design/system.md` actually specifies
  ("Market-blind football probabilities, explained and audited"). A
  visually-hidden `h1` keeps the document outline valid.
- `.hx-strip` gained a right-edge fade that retracts at scroll end — the strip
  runs 4733px past its 317px mobile viewport with only a hairline scrollbar as
  a hint.
- `.mb-item>a` min-height 44px.

Two bugs found and fixed, both worth remembering:
- `escHTML` is **not** global (module/IIFE scoped) despite looking it. Calling
  it from the home render threw a ReferenceError that silently aborted the whole
  page render with nothing in the console. Helpers there now carry a local
  escape.
- An `<em>` opened and closed with `</span>` swallowed every following section
  into one node, collapsing the grid areas. HTML validity is load-bearing here
  because layout is driven by `grid-area` classes on siblings.

## Open questions for the user — not yet ratified

- **Georgia is undocumented drift.** `.interface-design/system.md` names
  Archivo / Inter / Spline Sans Mono. `--serif: Georgia` now carries the
  wordmark, section heads, news headlines and the old `h1`. It post-dates the
  system file — ratify it or remove it.
- **Type floor unfinished.** 73 elements still render below 11px
  (`.intel-tag` 7.5px, `.region-mark` 8px, `.mono` badges 8px, table `th` 9px).
  Worth one systematic pass after all pages are reviewed, not piecemeal.
- **The fixture strip contradicts `system.md`**, which says "no clipped
  horizontal cards" on mobile. The strip post-dates that rule. A scroll
  affordance was added rather than rebuilding it.

## Remaining

- [ ] Matches `?league=command` — mobile
- [ ] Leagues `?league=leagues` + a league detail page — mobile
- [ ] Intel `?league=intel` — mobile (needs `intel_preview.sh`)
- [ ] Account `?league=account` — mobile
- [ ] Rankings `?league=power` — mobile
- [ ] Desktop pass (1280x800) over all of the above

## Resume prompt

> Resume the premium-site UX review from
> `docs/superpowers/plans/premium-site-ux-review.md`. Home mobile is done — pick
> up at Matches. For each page: start the preview server, measure the live DOM
> (never trust screenshots, content renders async), and report layout order,
> wording, contrast, type scale, and tap targets before proposing changes. Work
> mobile-first at 375x812 across Matches, Leagues, Intel, Account and Rankings,
> then repeat the whole set at desktop 1280x800. Check
> `.interface-design/system.md` first — it is the design contract and the site
> has drifted from it in places. Ask before changing anything structural, and
> before committing check `git log` and running processes in case another
> session is live in this repo.
