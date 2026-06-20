# Improvement Roadmap — Model / Visualizations / Performance / Efficiency (2026-06-19)

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use `- [ ]` tracking.

**Goal:** Sharpen the continental model, make it actionable (betting edge), improve the visualizations, and lock the operational pipeline before the July/August 2026 season rollovers.

**Architecture principle:** Most of this is cheap because the seams are clean — `team_strength()` is the cross-league swap point, the leagues' de-vig path is reusable, and the validation harness doubles as the calibration harness. The two genuinely new builds are the vectorization (mechanical) and the bracket visualization (frontend).

**Sequence:** 1→2→3→4 (accuracy spine, each enables the next); 5→6 (betting-edge + viz payoff on sharper odds); 7→8 (operational layer, pull forward if the calendar is the priority).

**Guardrails (every step):** MLS champion parity |Δ|=0.0000; full pytest suite green; in-browser regression-clean for MLS + a table league + a continental comp.

---

## Step 1 — Vectorize `bracket_sim` (performance)

**Why first:** the league/group/bracket Monte-Carlo loops match-by-match in Python (`_sim_match` → scalar `rng.poisson`) per run — millions of scalar draws at 20k sims. Same class as the Dixon-Coles 215s→0.4s fix. Speeding it compounds across every validation/calibration sweep below.

**Files:** `scripts/eval/bracket_sim.py`; `tests/test_bracket_sim.py`.

- [ ] Batch the league/group phase: draw `rng.poisson(lam_matrix, size=(N, n_matches))` once; vectorize points/GD accumulation and ranking across the N axis.
- [ ] Keep the knockout rounds correct (they're sequential per run, but the per-round match draws can batch across surviving ties).
- [ ] **Invariant regression:** the round-size sums must hold exactly (UCL R16=16/QF=8/SF=4/Final=2; CC RoundOne=22; LeaguesCup advance=8). Champion odds sum to 1.0. Existing tests stay green.
- [ ] Benchmark before/after (target: ≥10× on a 20k-sim UCL build).

## Step 2 — Approach C: bridge-regression cross-league offsets (model) — KEYSTONE

**Why:** `Δ_league` is coarse UEFA-coefficient-derived today → flat continental odds (~7.6% favorites vs ~15–20% real) and Europa/Conference lean on the coefficient anchor. Learn the offsets from real cross-league results.

**Files:** `scripts/eval/cross_league.py` (the `team_strength` seam — and a new offset-fitting module), `data_pipeline/coefficients.py` (offsets become fitted, prior retained).

- [ ] New `scripts/eval/league_bridge.py`: fit per-league additive ELO offsets by max-likelihood on historical continental match outcomes (logistic on strength_diff + offset terms), shrunk toward the coefficient prior (ridge / Bayesian shrinkage so thin-data leagues fall back gracefully).
- [ ] Wire `team_strength()` to use the fitted offsets when available, else the coefficient prior — **the only function that changes**. Concacaf offsets fit the same way from Concacaf results.
- [ ] Unit tests: fitted offsets monotonic with league strength; thin-data league ≈ prior; EPL anchor preserved.

## Step 3 — ELO-wired continental validation + market benchmark (model/efficiency)

**Why:** `validate_continental.py` is coefficient-only (~48% no-signal matches) → can't prove edge. Wire real strengths + a market benchmark; this validates Step 2 and is Step 4's calibration harness.

**Files:** `scripts/validate_continental.py`.

- [ ] Resolve each historical match's teams to real ELO + (fitted) offsets, not coefficient-only.
- [ ] Score model vs naive **vs market** (football-data.co.uk de-vig path, where continental odds exist).
- [ ] Report per-comp Brier + edge vs market; success = beats naive and isn't embarrassed by the market.

## Step 4 — Tournament calibration + knockout-playoff round (model)

**Why:** Monte-Carlo champion odds run flat; and the UCL/Europa builds skip the explicit knockout-playoff round (inflating mid-table R16 ~1.5×).

**Files:** `scripts/eval/bracket_sim.py`, `scripts/eval/cross_league.py`.

- [ ] Fit a single tournament-level sharpness parameter (temperature on per-tie win probs, or a favorite-longshot correction) against historical bracket outcomes from Step 3.
- [ ] Add the explicit 9–24 knockout-playoff round to the UEFA league→bracket path (8 playoff winners + 8 auto = 16 → R16), replacing the top-16 shortcut.
- [ ] Re-validate champion-odds calibration vs historical winners.

## Step 5 — Continental value/edge layer + live odds (model + visualization) — THE MISSION

**Why:** the platform finds `model − market` edge; leagues have a `value_layer`, continental comps don't.

**Files:** `scripts/build_continental_data.py`, `data_pipeline/football_data.py` (reuse de-vig), `webapp/index.html`.

- [ ] Per-tie market edge + a flat-stake backtest in the continental build (mirror the league `value_layer.backtest`).
- [ ] Populate `value_bets` for upcoming fixtures (edge ≥ 8%) once a draw exists (`continental_fixtures`).
- [ ] Fill the empty `games` array with per-tie probabilities + edge fields (the webapp `edgePick` already reads these).

## Step 6 — Bracket-tree visualization + per-tie match cards (visualizations)

**Why:** the Knockout sub-tab is a leaderboard table; a left-to-right bracket tree is far more legible for a knockout.

**Files:** `webapp/index.html`.

- [ ] Add a bracket-tree render (SVG or CSS grid) for the Knockout sub-tab, fed by the field odds + (when live) the drawn ties.
- [ ] Wire the Step-5 `games`/edge fields into per-tie match cards.
- [ ] Keep the leaderboard as a toggle/secondary view; verify all comps + concluded views.

## Step 7 — Automated rebuild/refresh pipeline (efficiency) — TIME-SENSITIVE

**Why:** builds are manual; Liga MX Apertura ~July 2026 and European 2026-27 + Leagues Cup 2026 ~August 2026 are close.

**Files:** `scripts/build_all.sh` (extend), a `launchd` plist or cron, possibly `scripts/refresh_continental.py`.

- [ ] A job that refreshes ESPN/Understat caches, detects state transitions (concluded → next-edition-drawn), and rebuilds only what changed.
- [ ] Add the Liga MX Apertura 2026 window (`_LIGA_MX_WINDOWS`) and the 2026-27 Understat fetches.
- [ ] Log a build report; no-op cleanly when nothing changed.

## Step 8 — Unified season-state detector (efficiency/correctness)

**Why:** concluded/in-progress/not-drawn logic now lives in the continental build; the league builds have separate finished-season handling — risk of drift.

**Files:** new `scripts/eval/season_state.py`; `build_league_data.py`, `build_continental_data.py`.

- [ ] Factor `season_state(...) -> {in_progress | concluded | between}` used by both builds.
- [ ] Both builds branch on it consistently (projection / actual-result / next-edition placeholder).
- [ ] Tests for the three states.

---

## Notes / risks
- Steps 1, 5, 6 touch user-facing output → verify in-browser each.
- Steps 2–4 change continental odds → keep MLS/league builds untouched; parity |Δ|=0.0000 throughout.
- Market data for continental ties may be sparse on football-data.co.uk → report coverage honestly in Step 3/5.
- Pull Steps 7–8 forward if the July/August rollover is the priority over the accuracy/viz work.
