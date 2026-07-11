# Public Launch Completion Plan

> **For agentic workers:** Execute task-by-task. Steps use checkbox (`- [ ]`) syntax. This plan is the resume point for a self-paced loop — after each task, check the box and commit.

**Goal:** Close the gap between the two Codex reports (2026-07-10 business plan, 2026-07-11 execution report) and the *actual* current codebase — green the test suite, ship the P0 trust/legal content, verify the launch UI end-to-end, produce launch content, and surface remaining external/decision-gated items honestly.

**Architecture:** Database-free static webapp. Python build scripts render `webapp/data/*.js`; `webapp/index.html` is served statically. All diagnostic/drift/edge infrastructure already exists and is wired into `build_all.sh`. This plan does NOT re-implement infrastructure — it fixes what regressed, completes what's half-done, and verifies what was claimed.

**Tech Stack:** Python 3.13, pytest, Playwright (browser smoke), static HTML/CSS/JS.

---

## Assessment Summary (2026-07-11)

Verified against disk, not the reports:

- **DONE & verified:** 37 payloads validate clean; slice/drift/edge/movers/ledger scripts exist and are wired into `build_all.sh`; Command Center, Trust cards, weak-spots, mobile media queries, market-disagreement card all present in `index.html`; 8-league expansion (Brazil/Japan/Nordics/Poland/Argentina/National League) shipped after the reports were written.
- **BROKEN (this plan fixes):** 3 failing tests — all test-hygiene lag, not product bugs.
- **INCOMPLETE P0:** legal/trust content pages (only an inline DISCLAIMER string exists).
- **UNVERIFIED claims:** mobile 390px overflow, Command Center non-empty state — reports claim done/needed; verify in browser.
- **DELIVERABLE-shaped:** 5 launch content articles (reports asked for them; none exist).
- **EXTERNAL / decision-gated (flag, do NOT auto-execute):** paid Odds API, email-send backend, production deploy, paid marketing, legal review sign-off.

---

## Task 1: Green the test suite

**Files:**
- Modify: `tests/test_payload_contract.py:21-22` (`_NON_PAYLOAD`)
- Modify: `tests/test_fetch_league_teams.py` (exclusion tuple)
- Modify: `tests/test_browser_smoke.py:297` (stale title assertion)

- [ ] **1a.** Add `"model-slices.js"` to `_NON_PAYLOAD` in `test_payload_contract.py`. Root cause: it is a cross-league diagnostic data file (`window.MODEL_SLICES`), not a league payload — same class as `drift.js`/`edge-board.js` already excluded.
- [ ] **1b.** Add `"model-slices"` to the excluded-stems tuple in `test_fetch_league_teams.py`.
- [ ] **1c.** Fix `test_browser_smoke.py` — landing route renamed "Matches" → "Command Center". Update the assertion to the current title (verify the actual `<h1>`/title text in `index.html` first; don't guess).
- [ ] **1d.** Run `venv/bin/python -m pytest -q` → expect 0 failures.
- [ ] **1e.** Commit.

## Task 2: DRY the payload-exclusion list (new-opportunity, prevents recurrence)

**Root cause of Task 1a/1b:** the "which .js files are NOT league payloads" list is duplicated in ≥2 test files and drifts every time a new cross-league data file ships.

**Files:**
- Modify: `scripts/validate_payloads.py` or a shared module — locate the single canonical definition of league-payload vs cross-league-data (validate_payloads already classifies these). Export one constant.
- Modify: both test files to import it.

- [ ] **2a.** Find where `validate_payloads.py` decides what is/isn't a league payload; expose a canonical `NON_LEAGUE_PAYLOADS` (or reuse existing).
- [ ] **2b.** Import it in both tests instead of hand-maintained literals. If a shared import is awkward, add a test that asserts the two exclusion lists agree, so drift fails loudly.
- [ ] **2c.** Run pytest → still green. Commit.

## Task 3: P0 trust/legal content pages

Reports P0: "About the model", "Data sources", "Responsible gambling", "Privacy". Only an inline DISCLAIMER exists. Add real content reachable from the UI (a `?league=about` / info-route pattern or a footer modal — match the existing routing idiom in `index.html`).

- [ ] **3a.** Inspect `index.html` routing to pick the least-invasive pattern for static info views.
- [ ] **3b.** Add **Responsible Gambling** content: 18+/begambleaware-style copy, "informational only, not betting advice, no guaranteed returns."
- [ ] **3c.** Add **About the Model**: market-blind, Brier/calibration explainer, "how to read the numbers," known limits (draws, underdogs, thin samples, preseason priors).
- [ ] **3d.** Add **Data Sources & Attribution**: ASA, ESPN, football-data, Transfermarkt (team-level aggregate only), Open-Meteo, UEFA coefficients — with the rights posture from the business report.
- [ ] **3e.** Add **Privacy**: what analytics are collected, no PII, static site.
- [ ] **3f.** Verify each renders in the browser preview. Commit.

## Task 4: Launch UI verification (reports' P0 claims)

- [ ] **4a.** Start preview, load no-query landing → confirm Command Center shows value with no live odds (7-day preseason window + season races), never an empty "no matches" screen.
- [ ] **4b.** Resize to 390px mobile → confirm no horizontal overflow on header accuracy/Trust chip and race cards. If overflow exists, fix the CSS and re-verify (memory: screenshots lie at depth — verify via DOM `scrollWidth`/`clientWidth`, not just eyeballing).
- [ ] **4c.** Confirm Trust card, weak-spots card, market-disagreement card render on a league page (e.g. EPL) without errors in console.
- [ ] **4d.** Screenshot the fixed states for the user. Commit any CSS fixes.

## Task 5: Launch content articles (deliverables)

Produce as markdown under `docs/content/` (safe artifacts; publishing is user-gated). Source all numbers from current payloads/champion reports — no invented stats.

- [ ] **5a.** `model-explainer.md` — how the market-blind model works, what Brier/calibration mean.
- [ ] **5b.** `epl-2026-27-priors.md` — title/UCL/relegation priors from `webapp/data/epl.js`.
- [ ] **5c.** `promoted-teams.md` — what the bridge-seeding does/doesn't know; the R2 no-change finding framed honestly.
- [ ] **5d.** `relegation-risk.md` — cross-league relegation priors + the ≥25% skill caveat.
- [ ] **5e.** `market-blind-edge.md` — why not training on odds is the credibility asset.
- [ ] **5f.** Commit.

## Task 6: Docs + honest remaining-work ledger

- [ ] **6a.** Update `docs/CURRENT_STATE.md` if anything model/metric changed (likely nothing — this plan is non-model).
- [ ] **6b.** Add a dated blockquote to `docs/PLAN.md` top.
- [ ] **6c.** Add a dated `docs/PROJECT_HISTORY.md` entry summarizing this completion pass.
- [ ] **6d.** Write `docs/remaining-external-dependencies-2026-07-11.md`: the decision-gated items (odds API, email backend, deploy, marketing, legal) with concrete recommended next actions for the user — NOT executed autonomously.
- [ ] **6e.** Delete this plan file (per CLAUDE.md: completed plans are deleted, story lives in PROJECT_HISTORY). Commit.

---

## Explicitly OUT OF SCOPE (do not auto-execute — outward-facing / spends money / needs user)

- Purchasing/expanding paid Odds API coverage.
- Standing up a live email-capture backend or sending any email (Resend is available but this is user-gated).
- Deploying to production / Vercel (outward-facing).
- Any paid marketing.
- Legal review sign-off or adding sportsbook affiliate links.
- Re-opening the model feature hunt (execution report deferred it; diagnostics showed no Brier gain — do not chase model changes in this launch-completion pass).
