# Outcome-Driven Model & UI Improvements Plan (2026-07-07)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the weaknesses the season-outcome baseline measured (MLS sim unwidened, bottom-table preseason location error, pooled playoff approximations) and ship the four user-selected UI surfaces (outcome-skill honesty, model-odds movers, mobile fixes, is-this-team-for-real).

**Architecture:** Model tasks are judged on the season-outcome replay (`scripts/eval_season_outcomes.py`, experiment-protocol §4 — NOT TDD; two-seed confirmation for gate-bound KEEPs) plus family match-Brier guards. UI tasks are additive rendering over data that exists or is produced by the model tasks, verified in-browser per the house convention.

**Tech Stack:** Existing only — Python 3.13 sim/eval stack, vanilla-JS single-file webapp, static `webapp/data/*.js` payloads.

**User decisions (2026-07-07):** full list approved; ODDS_API_KEY deferred — nothing here may depend on market odds.

**Compute:** one eval run at a time, background + full log redirect (house rules).

---

> **VERDICT M1 (2026-07-07): KEEP — MLS sim widened.** A/B on the outcome replay first
> corrected a replay/production divergence (the replay had assumed σ60·decay for MLS).
> Production-as-is vs widened, both seeds: preseason playoffs Brier −0.0109/−0.0088, shield
> −0.0013/−0.0012; cp0.25/cp0.5 flat within tolerance. Ported the σ_family·(1−f) block into
> build_dashboard_data's MC loop (mid-season today: σ=34); MLS rebuilt, 29 payloads valid.
> Bonus finding for M4: the MLS sim is ALREADY conference-aware (per-conference playoff
> slots + bracket) — M4 reduces to USL only.

### Task M1: Port strength-uncertainty widening to the MLS sim

The worst measured number: MLS Shield preseason skill +0.01. Discovered while scoping: the
outcome replay applied family-default widening (σ60·decay) to MLS while
`build_dashboard_data.py`'s sim has NONE — the +0.01 was measured under a config production
doesn't run. The A/B must first re-measure production-as-is.

**Files:**
- Modify: `scripts/build_dashboard_data.py` (season-sim MC loop — locate the fixed-probability sampling, mirror `build_league_data.py`'s `_sigma_eff` block)
- Modify: `scripts/eval_season_outcomes.py` only if the ASA sigma default needs a `--sigma 0` run flag (it doesn't — flag exists)

- [ ] **Step 1 (baseline honesty):** `venv/bin/python scripts/eval_season_outcomes.py --leagues mls --sigma 0 --no-sigma-decay --out <scratchpad>/mls-nowiden.json` — production-as-is MLS outcome Brier.
- [ ] **Step 2 (proposed):** same with defaults (σ60·decay) → compare shield/playoffs Brier at cp0/cp0.25. KEEP bar: no outcome regresses; confirm at `--seed 7`.
- [ ] **Step 3 (port):** in `build_dashboard_data.py`, before the sim loop: `_season_frac = played/(played+remaining)`; `_sigma_eff = preseason_sigma_for_source("asa") * (1-_season_frac)`; perturb per-sim via `scripts.eval.sim_variance.perturb_probs` exactly as `build_league_data.py:~880` does. Import both helpers.
- [ ] **Step 4:** rebuild MLS (`venv/bin/python scripts/build_dashboard_data.py`), validate payloads, spot-check playoff odds moved plausibly (mid-season σ≈30: small widening).
- [ ] **Step 5:** verdict to this file + `docs/feature-hunt-log.md` + `docs/CURRENT_STATE.md` (MLS no longer exempt); commit.

> **VERDICT U1 (2026-07-07): COMPLETE.** `outcome_skill_block()` in payload_utils reads the
> replay baseline per league; both builders attach it; Health tab renders a checkpoint×outcome
> skill table (red ≤0.05) + the ~25% honesty note; empty state verified on liga-mx; zero
> console errors. Chip dismissed. All payloads rebuilt.

> **VERDICT U3 (2026-07-07): COMPLETE — the two known failures are FIXED.** Culprit: the
> header's per-year accuracy tracks (46px year cells × up to 7 eval years = ~446px at a 390px
> viewport). `.acc-tracks` now scrolls inside its own box (`min-width:0;max-width:100%;
> overflow-x:auto`). Browser-smoke suite fully green for the first time since B1 (26 passed,
> including mls/epl mobile).

### Task U1: Outcome-skill surface in the Health tab

**Files:**
- Modify: `scripts/build_league_data.py` + `scripts/build_dashboard_data.py` — attach `outcome_skill` to payloads: per-checkpoint `{outcome: {brier, skill, p_actual_mean}}` read from `experiments/season-outcomes-baseline.report.json` `per_league[lid]` (skill = 1 − brier/(obs·(1−obs)); empty-safe when league absent; round 3dp)
- Modify: `webapp/index.html` `renderHealth()` — small table + one-line note ("Preseason relegation/promotion odds carry little skill — they sharpen by ~25% of the season."), B4 empty-state pattern

- [ ] Step 1: attach block in both builders (shared helper in `scripts/payload_utils.py`), rebuild ONE league + MLS, validate.
- [ ] Step 2: render; verify in-browser: a covered league (championship), an uncovered one (liga-mx → empty state), zero console errors, no mobile overflow.
- [ ] Step 3: rebuild remaining payloads (weekly CI covers stragglers), commit, dismiss the pending chip.

### Task U3: Fix the two known mobile overflows (mls, epl @390px)

Failing since B1 (pre-existing in every suite run): `tests/test_browser_smoke.py::TestNoHorizontalOverflow::test_no_overflow_mobile[chromium-mls|epl]`.

- [ ] Step 1: reproduce — `venv/bin/pytest tests/test_browser_smoke.py -k overflow -q`; then preview at 390px (`preview_resize`) and find the overflowing element (`document.querySelectorAll('*')` scan for `scrollWidth > clientWidth` culprits).
- [ ] Step 2: CSS fix in `webapp/index.html` (likely a table/scroll container needing `overflow-x:auto` or `min-width:0` on a flex child — diagnose, don't guess).
- [ ] Step 3: browser-smoke suite green including the two tests; commit.

### Task U2: Model-odds movers strip (market odds NOT required)

`data/odds_history.parquet` accrues one row per (league, team, build-date) since 2026-07-03 with title/playoff/releg/ucl odds + ELO. Movers = biggest deltas over the trailing window.

**Files:**
- Create: `scripts/build_movers.py` — read parquet, per league compute Δ over the last ≤14 snapshots for each odds column; emit top ±N across leagues to `webapp/data/movers.js` (`write_js_payload`; empty-safe when <2 snapshots)
- Modify: `webapp/index.html` — movers strip on the edge-board landing view (rising/falling chips: team crest, league badge, "title 12%→19%")
- Modify: `.github/workflows/refresh-daily.yml` + `refresh-leagues.yml` — run after `archive_odds_snapshot.py`
- Test: `tests/test_build_movers.py` — synthetic parquet: two dates → correct delta + sign; one date → empty payload

- [ ] Steps: failing test → implement builder → suite green → wire UI → browser check (strip renders; graceful "not enough history yet" state) → CI wiring → commit.

### Task M3: A8 deferred sweep — per-family season-boundary ELO regression rate

The 40% regress was promoted on MLS folds only. Judge per family on (a) the A8-style ELO-proxy
early-60d Brier (rebuild that scratchpad harness: big-5 + tiers FD frames, `compute_elo`
sweep regress ∈ {0.25, 0.33, 0.40, 0.50} with `club_prior_beta=0.75`, home-prob Brier on each
season's first 60 days) and (b) the outcome replay (regress enters via bridge ELO + seeds).
MLS champion config untouched (its own gate governs it).

- [ ] Step 1: scratchpad sweep script (pattern: the A10(b) replay script); run both families × 4 rates.
- [ ] Step 2: if a non-0.40 rate wins a family by more than noise, confirm at second seed via the outcome replay; port to `build_league_data.py`'s `compute_elo(..., regress=…)` call sites with a `regress_for_source()` helper in `scripts/eval/elo.py` or inline constant.
- [ ] Step 3: verdict (KEEP or validated null) to log/docs; rebuild affected payloads if KEEP; commit.

### Task M4: Conference-aware playoff odds (USL now; MLS check)

USL playoff odds are a pooled top-16 approximation of top-8-per-conference. MLS: verify
whether `build_dashboard_data.py` already counts playoffs per conference (its payload renders
conferences) — if yes, MLS is done and only the replay's `_ASA["mls"]` bucket needs a note.

**Files:**
- Modify: `scripts/build_league_data.py` — optional `conferences` cfg for `usl-championship`: fetch team→conference from ESPN standings (`site.api.espn.com/.../usa.usl.1/standings`, groups) at build time with a static fallback map; playoff bucket counts top-8 WITHIN each conference per sim iteration
- Modify: `scripts/eval_season_outcomes.py` `_ASA` buckets accordingly
- Test: `tests/test_conference_buckets.py` — synthetic 4-team, 2-conference sim: a team ranked 3rd overall but 1st in its conference qualifies

- [ ] Steps: failing test → conference-aware bucket counting (`_bucket_idx` gains a per-conference mode) → USL rebuild + browser check → replay re-run for USL slice → commit.

### Task M2: A10(a) Europe revival — leakage-clean TM value backfill probe, then the experiment

**Gate 0 (the probe decides everything):** TM's `saison_id=<year>` pages must serve
ERA-APPROPRIATE values, not current ones. Probe: fetch GB1 `saison_id=2019` team totals via
the A9 fetcher; compare vs the 2026 snapshot (e.g. Chelsea/Arsenal totals must differ
materially and match era reporting ~£600-900m, not 2026 values). If values are current →
STOP, log the negative, keep waiting on weekly-snapshot accrual.

- [ ] Step 1: probe (one league-season fetch, polite rate).
- [ ] Step 2 (if clean): backfill team-level totals big-5 2017–2025 (45 league-seasons, serial, cached); store `data/transfermarkt_backfill/` (team-level only per rights register).
- [ ] Step 3: experiment — `compute_elo(value_beta=…, season_values=…)` seeding in the outcome replay's `_seed_newcomers`/ELO path AND `build_league_data.py` seeding; grid β₂ ∈ {0.25, 0.5}; judged on preseason releg/promo/title Brier, two seeds; MLS untouched (A10a-MLS already DROPped).
- [ ] Step 4: verdict either way to log/docs; port + rebuild if KEEP; commit.

### Task U4: "Is this team for real?" team-profile panel

The Spurs story as product: does a team's position overstate or understate it?

**Files:**
- Modify: `scripts/build_league_data.py` — per-team `for_real` block: `club_prior_gap` (A7 helper over the league ELO history), `xg_delta` (season xG-for minus goals-for and against-counterpart, from the frame), `value_rank_gap` (squad-value rank − table rank, where squad values exist), all null-safe
- Modify: `webapp/index.html` team profile — panel with 3 gauge rows + a one-line verdict ("results ahead of underlying numbers", "market values this squad higher than the table does"), thresholds documented in a comment, null rows hidden like B9's convention

- [ ] Steps: builder block + payload contract check (numbers-or-null) → render → browser check on a high-gap team (Tottenham) and a null-value league → rebuild touched payloads → commit.

---

## Documentation obligations (per CLAUDE.md, every task)
- Verdict appended to THIS file after each task; experiments also to `docs/feature-hunt-log.md`; blockquote to `docs/PLAN.md` on eval/config changes; `docs/CURRENT_STATE.md` when config shifts.
- On completion: summary to `docs/PROJECT_HISTORY.md`, delete this file.

## Risks
- M2 probe likely fails (TM may serve current values on old saison pages) — that outcome is a logged negative, not a blocker for the rest.
- U2 has only ~5 snapshots of history — ship the machinery with the honest thin-history state.
- M4 ESPN standings-group fetch may lack conferences for USL — static map fallback is required, not optional.
