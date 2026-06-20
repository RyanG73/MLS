# Season Rollover + Roadmap Round 2 (2026-06-20)

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use `- [ ]` tracking.

**Goal:** Flip the European league projections to 2026-27 (EPL's schedule has launched), and advance model/viz/ops quality. Sequenced so the EPL flip (steps 1–4, the urgent deliverable) lands and verifies first.

**Key data fact (discovered 2026-06-20):** Understat (our xG source) has **no 2026-27 data yet** (it publishes ~August). But ESPN **does** have the official 2026-27 schedule (eng.1: 20 teams incl. promoted Coventry City). So the pre-season flip pulls **fixtures from ESPN** + carry-over ELO + promoted-team seeding; xG-based projections resume when Understat publishes (the existing auto-detect handles that).

**Guardrails (every step):** MLS champion parity |Δ|=0.0000; full pytest suite green; in-browser regression-clean (MLS + a concluded league + a continental comp + the new pre-season league).

---

## Step 1 — ESPN European fixtures adapter
When Understat lacks the upcoming season, fetch its **schedule** from ESPN.
**Files:** `data_pipeline/espn_fixtures.py` (new); tests.
- [ ] `european_fixtures(league_id, season)` → canonical upcoming rows (date, season, home_team, away_team, home_goals=NaN, away_goals=NaN, is_result=False) via the ESPN scoreboard slug (eng.1 / esp.1 / ita.1 / ger.1 / fra.1). Map ESPN team displayNames → the league's Understat keys (reuse/extend a name map; promoted teams won't be in Understat — keep their ESPN name).
- [ ] Parquet-cache; smoke-test EPL 2026 returns 380 fixtures, 20 teams incl. Coventry City.

## Step 2 — Carry-over ELO + promoted-team seeding
**Files:** `scripts/eval/league_features.py` or `scripts/build_league_data.py`; tests.
- [ ] Compute current ELO from prior seasons' played matches (the build already runs `compute_elo`); apply season regression for the new season.
- [ ] Continuing teams keep their regressed ELO. **Promoted teams** (in the new fixtures but absent from prior top-flight ELO) seed at a documented "promoted baseline" (e.g. ~1430, below the relegation-zone average) — v1 simple; note the refinement: seed from their 2nd-tier strength via a Championship→top-flight offset (reuses the cross-league framework).
- [ ] Test: a promoted team gets the baseline; a continuing team keeps regressed ELO.

## Step 3 — Pre-season projection mode in build_league_data
**Files:** `scripts/build_league_data.py`, `scripts/eval/season_state.py`, `webapp/index.html`.
- [ ] Target season = latest with ANY fixtures (played OR upcoming), not just max-played. When that season has fixtures but 0 played → **pre-season**: project the full season from carry-over strengths (DC/ELO Monte-Carlo over all fixtures; the ensemble path already no-ops when `len(played)<1` → DC-only). Source fixtures from ESPN (Step 1) when Understat is empty.
- [ ] Add a `preseason` state to `season_state` (played==0 AND upcoming>0 → distinguish from `between`); set `outlook.preseason=True` + `outlook.season_label`.
- [ ] Webapp: a "2026-27 · pre-season projection" subtitle (don't imply in-progress).

## Step 4 — Flip EPL to 2026-27 + verify
- [ ] Wire Steps 1–3; build EPL targeting 2026 → `webapp/data/epl.js` shows a 2026-27 pre-season table (all teams 0 pts, full-season title/UCL/releg odds, promoted teams present).
- [ ] In-browser: EPL shows 2026-27 pre-season; promoted teams listed; MLS + concluded leagues + continental regression-clean. parity |Δ|=0.0000; tests green.

## Step 5 — Generalize rollover to the other big-5 (+ 2nd tiers)
- [ ] Apply the Step 1–3 path to la-liga/serie-a/bundesliga/ligue-1 (and the football-data 2nd tiers via their schedule source). Each flips when ESPN has its next-season schedule; until then stays on the finished 2025-26 table. Build whichever already have 2026-27 fixtures; leave the rest auto-detecting.

## Step 6 — Pre-season UI treatment
**Files:** `webapp/index.html`.
- [ ] Promoted/relegated badges in the table; show prior-season finish alongside the projection where available; a clear pre-season banner. Verify across a pre-season league + a concluded league.

## Step 7 — Historical-ELO-as-of-date for Approach C (the R2 deferred lever)
**Files:** `scripts/eval/league_bridge.py`.
- [ ] Replay each league's ELO sequence and index by date so the cross-league offset fit uses each team's strength AS OF the match (not current ELO). Re-run the validated fit; adopt only if it beats the coefficient prior on held-out (same guardrail as R2). Honest null is an acceptable outcome.

## Step 8 — Continental odds feed (the R3/R5 blocker)
**Files:** `data_pipeline/odds_log.py` or new `data_pipeline/continental_odds.py`; `build_continental_data.py`.
- [ ] Wire the Odds API (ODDS_API_KEY, already used for MLS) to continental comps; populate `value_layer.value_bets` (edge ≥ 8%) for upcoming ties when a comp is in-season with a draw. All comps are concluded now → build the path, verify it no-ops cleanly, document activation. If the API/key doesn't cover continental, report honestly and leave the scaffold.

## Step 9 — Model report-card view
**Files:** `webapp/index.html`.
- [ ] Summarize the `games` retrospective (R5) into a per-comp accuracy panel: model hit rate, Brier vs naive, calibration — a "how did the model do" card on the Model Health tab for continental/leagues.

## Step 10 — Rollover test coverage
**Files:** `tests/`.
- [ ] Tests for the season-rollover paths: pre-season state detection, promoted-team seeding, ESPN-fixtures parsing, and the build's season-selection (latest-with-fixtures). Lock the rollover behavior so future seasons don't regress it.

---

## Notes / risks
- Steps 1–4 are the urgent EPL flip; verify it works before 5–10.
- Pre-season projections are high-variance (no current-season form, promoted teams seeded coarsely) — present them as pre-season, not certainty.
- Step 8 likely partially blocked (odds API coverage / out-of-season) — build the path, document honestly.
- Keep the MLS model untouched throughout (parity |Δ|=0.0000).
