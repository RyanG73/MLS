# MLS Prediction Dashboard — Implementation Plan

> **Big-5 European model program (2026-06-14) — first non-MLS leagues**
> User decisions: build the **5 big European leagues in parallel** (EPL, La Liga, Serie A, Bundesliga,
> Ligue 1), **Tier-1 scope** (league-table leagues with xG), **Understat first** (FBref leagues later).
>
> **Feasibility (verified 2026-06-14):** `understatapi` fetches per-match xG for all big-5 back to **2014**
> (more history than MLS's 2017+); ASA covers MLS only; direct Understat scraping is walled but the library's
> fetch path works. Model architecture (ELO + Dixon-Coles + bagged XGBoost on rolling xG/form) is
> league-agnostic below the data-fetch layer (DataFrame-in), so the work is data-adapter + per-league
> validation + webapp generalization for league-table semantics (promotion/relegation, no conferences/playoffs).
>
> **Work streams / phasing:**
> 1. **Understat data adapter** (`data_pipeline/understat.py`): per-league fetch → canonical match frame
>    (match_id, date, season, home/away_team, home/away_goals, home/away_xg) matching the ASA schema; cache;
>    team-name → ESPN-name map for logos.
> 2. **Per-league model validation:** parameterize the harness/research_model to load a league's frame; run
>    walk-forward + promotion gate per league (start from the MLS champion config; tune if needed). European
>    COVID note: 2019-20 + 2020-21 were played to completion (no MLS-style bubble) but behind closed doors —
>    keep in training, flag the home-advantage dip. No conferences; single table.
> 3. **Dashboard build generalization:** `build_dashboard_data.py` takes a league + source → `webapp/data/
>    <id>.js` with the generic payload but league-appropriate outlook (Title / Top-4 UCL / Relegation, no
>    playoff bracket; season sim = simulate remaining fixtures → final table odds). Per-league trophies.
> 4. **Webapp generalization:** config-driven outlook boxes + table semantics (relegation zone vs playoff
>    line) from a per-league `outlook` block; what-if sim generalized to table outcomes. Teams/History/Health
>    already league-agnostic.
> 5. Flip the 5 leagues `soon`→`live`; verify each in-browser.
>
> **Status (2026-06-14):**
> - **WS1 ✅** `data_pipeline/understat.py` — 21,588 played matches (2014–2025), 100% xG coverage,
>   parquet-cached per league. 6 contract tests. (commit `4011c09`)
> - **WS2 ✅ — the champion pipeline transfers UNCHANGED.** `scripts/eval/league_features.py` composes
>   the league-agnostic 31-feature subset (ELO + rolling xG/xGA + form; the 6 MLS-only gk_z/avail
>   features are simply absent — `walk_forward` intersects feat_base with present columns). Walk-forward
>   (champion config: ELO 25/80/0.40, DC 120d, whl 6) on 2022–2025, `n_bags=1` directional sweep:
>
>   | League | Matches | avg Brier | naive | edge |
>   |---|---|---|---|---|
>   | La Liga | 4,560 | **0.5863** | 0.6410 | +8.5% |
>   | EPL | 4,560 | **0.5890** | 0.6455 | +8.8% |
>   | Bundesliga | 3,672 | **0.5934** | 0.6503 | +8.7% |
>   | Serie A | 4,560 | **0.5946** | 0.6586 | +9.7% |
>   | Ligue 1 | 4,236 | **0.6035** | 0.6478 | +6.8% |
>   | _MLS champion (ref)_ | _—_ | _0.6330_ | _0.6406_ | _+1.2%_ |
>
>   All five beat the MLS champion's Brier and beat naive by 6.8–9.7% (vs MLS's ~1.2%): European
>   leagues carry far more capturable signal (lower parity → xG-visible hierarchies). Model untouched.
>   COVID handled as planned: 2019-20/2020-21 kept in training; Ligue 1's cancelled 2019-20 (~100
>   unplayed matches) is simply absent. `n_bags=5` confirmation optional (directional signal unambiguous).
> - **WS3 ✅** `scripts/build_league_data.py` — single-table builder emitting the MLS payload schema
>   with Title/Top-4(UCL)/Relegation outcomes + a config-driven `outlook` block; single source (Understat
>   matches+xG+fixtures), crests from the ESPN stubs. European 2025-26 seasons are complete → launches as
>   a finished final table; live projections resume when 2026-27 starts (Aug 2026). Verified on EPL
>   (in-season Brier 0.6219, perf-by-year 2017–2025, logos/colors resolve). (commit `53c2a66`)
> - **WS4 ✅** webapp renders single-table leagues. When `outlook.mode==='table'`, League Projections shows
>   config-driven favorite cards + a single isolated table ladder (`.tlad`) with UCL/relegation cut-lines;
>   MLS conference/playoff/cup view untouched (`isTable=false`). Verified in-browser: EPL all 4 tabs, zero
>   console errors; MLS regression-clean. (commit `c98151a`)
> - **WS5 ▶** flip the 5 European leagues `soon`→`live` (`fetch_league_teams.py` REGISTRY → `leagues.js`),
>   regenerate all 5 data files via `build_league_data.py`, verify each in-browser. **Phase 1 = big-5
>   European leagues LIVE on the platform.**
>
> **Deferred (Phase 2+):** FBref leagues (Championship, 2.Bundesliga, Serie B, Ligue 2, Liga MX); goals-only
> lower divisions (League One/Two, Canadian PL); cup competitions (UCL/Europa/Conference/Concacaf/Leagues Cup
> — cross-league knockout models, a separate effort). Champion 0.6330 MLS model untouched.

> **Multi-league platform (2026-06-12) — MLS becomes one league behind a left sidebar**
> Pivot from single-league dashboard to a multi-league platform template (MLS live; ~18 Concacaf/UEFA
> leagues scaffolded, models not built). Webapp + data-plumbing only — model/champion (0.6330) untouched.
> - **Data:** `window.MLS_DATA`→`window.LEAGUE_DATA`, lazy-loaded per league via `?league=<id>`.
>   `scripts/fetch_league_teams.py` pulls teams+crest+league logos from ESPN (19 leagues) → `webapp/leagues.js`
>   registry + `webapp/data/<id>.js` coming-soon stubs. `build_dashboard_data.py` writes `webapp/data/mls.js`
>   (full) + a `league` meta block (name/logo/`pct_complete`) + `perf_by_year` (model vs naive 2019,2022-2025
>   via `research_model.walk_forward`, n_bags=1; 2020/2021 skipped — COVID cal gap).
> - **UI:** permanent confederation-grouped sidebar (MLS live, rest "soon" with real teams/logos, no model);
>   header = league name + ESPN league logo + "{season} is X% complete"; simplified accuracy card (no bars) +
>   per-year readout. Tabs: League Projections (heading "League Table"), Match Projections (compact skimmable
>   38px rows), **Teams** (Team Profile+History merged: interactive ELO mini-chart grid + hover tooltips + SVG
>   trophy glyphs [MLS Cup/Shield/US Open Cup, conference dropped] + profile-below-on-select + table name
>   cross-links), Model Health. Crest monogram hidden behind logos (`:has` fix); "Capped DC" footnote removed.
> - Platform name "Pitchside" is a placeholder (sidebar brand) — easy to rename. Favorites boxes stay
>   MLS-specific (Shield/East/West/Spoon); flagged league-configurable for future non-conference leagues.
> - Verified in-browser (MLS full + EPL coming-soon, no console errors); tests 101 pass; data/mls.js 281 KB.

> **Webapp round 2 (2026-06-12) — market-Brier, Team Profile, History tabs**
> - **Market (opening-line) Brier comparison.** `build_dashboard_data` computes a de-vigged opening-line
>   market Brier on played games that have a logged opener, shown in the header beside model & naive with the
>   model's edge%. Source = `data/odds_log.parquet` (`data_pipeline/odds_log.py`, opening lines only). **Setup
>   needed:** add `ODDS_API_KEY` to `.env`; the daily build's `make odds-log` then captures each future game's
>   opener (free tier: one ~daily poll, ~30 req/mo). Shows "awaiting odds" until openers overlap results — the
>   free tier cannot backfill the ~218 already-played 2026 games (paid historical endpoint only). Model stays
>   market-blind; odds are post-prediction only.
> - **Team Profile tab.** Team selector → model inputs (ELO, rolling xG for/against, form, GK z, availability),
>   2026 season summary (record, pts, GD/xGD, conf rank, playoff/Shield/Cup odds), next-5 fixtures with model
>   win prob, and recent results with model hit/miss.
> - **History tab.** Per-team ELO trajectory 2013–2026 (computed over the full ASA game history, hand-rolled
>   SVG) annotated with trophy markers — MLS Cup, Supporters' Shield, US Open Cup, Conference championship —
>   from `data_pipeline/trophies.py` (Wikipedia-verified 2013–2025). data.js 281 KB; tests 101 pass.

> **Webapp + production roadmap (2026-06-11) — 19-item user roadmap; webapp-first, then model loop**
> Plan file: `~/.claude/plans/i-skimmed-code-walkthrough-plan-buzzing-badger.md`. User decisions: webapp-only
> production (deprecate Streamlit/Postgres/Pi), retest flagged DROPs (weather/salary/HFA) through the gate,
> rolling-feature change via the gate, webapp first.
>
> **Phase A — webapp (DONE 2026-06-11, A1–A4; verified in-browser):**
> - **A1 — data.js payload.** `build_dashboard_data.py` now emits: per-game `id` (sim-array index, not display
>   order) + `lam`/`mu` DC expected goals; per-team `elo` (via new `compute_elo(return_ratings=True)` in
>   scripts/eval/elo.py) + `cup` %; top-level `sim:{teams,pmatrix}` (30×30×3 DC probs, ints×1000, row=host),
>   `in_season_brier` (2026: model 0.6298 vs naive 0.6339, n=218, +0.64%), and `health` (feature-family
>   completeness + non-default % over 2026 frame rows, frame mtime, ESPN status). data.js 162→185 KB.
> - **A2 — webapp static features.** "Proj Pts"→"Proj"; projected score (lam–mu) on every match card; second
>   header card "2026 LIVE" Brier-vs-naive beside the champion benchmark; ELO column; new **Model Health** tab.
> - **A3 — MLS Cup odds.** Python `simulate_bracket()` in the MC loop (wild card 8v9 PK 50/50; Bo3 round one;
>   single-elim semis/final/Cup with proportional no-draw; tiebreak pts·10000+GD·10+U(0,10)); `cup` column +
>   favorites integration. Verified: cup sums to ~100%, conference top seeds rank highest.
> - **A4 — client-side what-if simulator.** Next-5 clickable boxes per team (W/D/L cycling, opponent-mirrored
>   via one `forced` map); JS `runSim(10000)` typed-array Monte-Carlo keyed by `g.id`, full bracket ported per
>   a SIM PORTING CONTRACT duplicated verbatim in both files. **Acceptance PASS: unforced JS@10k within
>   ±1.2pp of server@20k on every cell** (bound 1.5pp); ~debounced, sub-second; forcing 5 wins on the worst
>   team moved playoff 6.1%→43.1% with opponent boxes mirroring. Suite 108 passed; responsive 480/760/1280px.
> - **A5 — Pi removal + webapp-only production: DONE 2026-06-11.** Archived (not deleted) the entire
>   Postgres/Streamlit/Pi system under `legacy/` (36 files: `dashboard/`, legacy `models/`, DB-backed
>   `data_pipeline/` + `features/` + `market/`, ops `scripts/`, + 4 DB tests) — `legacy/README.md` documents
>   it; recoverable, kept the `market/` betting layer for the CLV workstream. Active surface = harness +
>   `research_model` + `webapp/`, all DB-free. Kept in place: `data_pipeline/{team_metadata,source_health,
>   db_utils,espn_rosters}` (gate/harness need them). New `data_pipeline/odds_log.py` logs Pinnacle **opening**
>   lines → `data/odds_log.parquet` (no-ops without `ODDS_API_KEY`). Scrubbed Pi refs from README (full
>   rewrite), CURRENT_STATE, HANDOFF, Makefile, settings.yaml; deleted `docs/PI_VALIDATION.md`. Verified:
>   `make test` 101 passed, gate self-test 6/6, parity PASS 0.6330. Daily-build launchd plist: pending.
>
> **Phase B — model experiment loop (gate-governed; verdicts below):**
> - **B1 — season-aware rolling: DROP (2026-06-11).** New `season_decay` weight on xG/xGA/form rolling means
>   (prior-season matches count `decay^seasons_ago`; 1.0 = exact no-op, smoke + 20 unit tests confirm). Bagged
>   4-fold sweep: decay 1.0=0.63298 (control), 0.85=**0.63325 (+0.0003, worse)**, 0.6=0.63284 (−0.0001,
>   sub-noise, fails the −0.0005 gate bar); non-monotonic and cal_err degrades monotonically (0.134→0.152).
>   Empirical answer to the user's hypothesis: down-weighting prior-season rolling data does NOT help — the
>   early-season "stale data" cost is outweighed by having any signal; cross-season carryover is benign
>   (consistent with I1: 2021-in-training helped 2023). Flag retained (`--season-decay`), default 1.0.
> - **B2 — manager tenure: MARGINAL (2026-06-11), not promoted.** Feasible (unlike referee): ASA get_games
>   carries `home/away_manager_id` at 100% coverage. Built walk-forward `home/away_mgr_new` (first 5 games of
>   a stint), `_mgr_tenure` (games in charge, capped 100), + diffs. Bagged 4-fold AB: **+Manager 0.634136 vs
>   Base 0.634403, Δ=−0.00027** — directionally positive (managers carry a sliver of signal) but below the
>   0.001 screening bar. Joins the registered-not-ensemble-capturing pile (+HomeAdv/+TZ_Pythag): ELO+form
>   already encode most team quality. `+Manager` AB set retained.
> - **B3 — neutral-site DROP; per-team HFA marginal (2026-06-11).** Threaded `stadium_id`; neutral-site flag =
>   home game at a non-modal stadium for that team-season (2.8%, isolates true relocations), damping the HFA
>   tilt at neutral venues. Bagged 4-fold AB: **+HomeAdv (tilt only) 0.633835 (Δ−0.00057, best), +HFA2 (tilt +
>   neutral) 0.634542 (Δ+0.00014 — WORSE than Base AND than +HomeAdv).** The neutral-site signal is too sparse
>   (2.8%) — XGB overfits it as noise. Neutral-site = DROP; the per-team HFA tilt re-confirmed marginal
>   (strongest marginal yet but below the 0.001 bar). Features retained as `+HomeAdv`/`+HFA2` AB sets.
> - **B4 — weather retest: DROP, now definitive (2026-06-11).** Re-ran `--weather` (Open-Meteo archive);
>   coverage **89%** (the prior 45% was an incomplete fetch; the remaining 11% is dome teams correctly →
>   NULL — outdoor alignment already structural). Bagged 4-fold AB: **+Weather 0.634711 vs Base 0.634403,
>   Δ=+0.00031 (worse).** The retest premise ("full coverage changes the answer") is falsified — weather still
>   hurts at near-full coverage; rolling xG/form already absorb condition effects on 1X2 outcomes.
> - **B5 — salary retest: BLOCKED/predetermined (pause for user).** User's named source `itscalledsoccer
>   get_player_salaries` IS the ASA data DROPped twice (player −0.0008, team −0.0045). mls-roster-profiles repo
>   is genuinely different (roster construction: DP/TAM/U22) but 2024+ only → no pre-2024 training history →
>   single-fold (train 2024 → test 2025) low-power test (same confound that voided the original roster A/B).
>   Awaiting user direction before spending the build.
> - **B5 — roster profiles (single-fold probe): INCONCLUSIVE / data-limited (2026-06-11, user chose to try).**
>   Built `scripts/probe_roster_profiles.py` — DP/U22/TAM/GAM/intl-slot counts from the ASA mls-roster-profiles
>   repo (team `id` = ASA team_id, trivial join), train-2024 → test-2025 single split. Result: the 2024-only
>   training (522 matches, no valid cal fold) yields an **unreliable model (Brier ~1.0, worse than random)**,
>   so the roster Δ (−0.013) is noise on a broken baseline. Confirms the structural blocker: the repo's
>   2024+ depth is too thin for any fair test. Revisit once 2024+ accumulates ≥3 seasons. Probe + snapshots
>   retained for that future re-run.
> - **B6 — history depth 2013+: PROMISING, confirming (2026-06-11).** xG is 100% back to 2013 (ASA MLS games
>   start 2013; 2017 cutoff was a deliberate league-composition choice, not a data limit). `--start-season`
>   sweep bagged 4-fold: 2017=0.63298 (ctrl), **2015=0.63231 (Δ−0.00067, clears screening bar)**,
>   2013=0.63293 (−0.00005, neutral). **DROP after seed-1 confirm:** seed-1 start=2015 = 0.63358 (WORSE
>   than control), so the 2-seed mean 0.63295 ≈ control — the seed-42 gain was luck. AND 2024 regresses both
>   seeds (0.6357/0.6363 > 0.6348 limit, FAIL robustness) and 2025 too (+0.0024 at seed-1). Extending history
>   fits the old 2022 fold (−0.0037) at the cost of current-regime folds (2024, 2025) — the wrong tradeoff for
>   forward-looking prediction. **The 2017 cutoff is empirically vindicated.** (Also a clean bagging-protocol
>   lesson: single-seed would have falsely promoted this.) `--start-season` flag retained, default 2017.
>
> **PHASE B COMPLETE (2026-06-11, B1–B7).** Champion unchanged at 0.6330 throughout. Verdicts: B1 season-decay
> DROP · B2 manager MARGINAL · B3 neutral-site DROP (per-team HFA marginal) · B4 weather DROP (89% cov,
> definitive) · B5 roster-profiles INCONCLUSIVE (2024-only too thin) · B6 history-depth DROP (vindicates 2017
> cutoff) · B7 SATISFIED by A1. **Unanimous finding: the model is at its pre-match-feature ceiling — ELO +
> rolling xG/form already absorb team quality, home advantage, manager effects, conditions, and roster
> investment.** The frontier is no longer features but the betting/CLV workstream (measuring edge vs the
> market; opening-line logging now in place via `data_pipeline/odds_log.py`).
> - **B7 — 2026 reporting: SATISFIED by A1.** The webapp header shows live 2026 Brier (0.6298 model vs 0.6339
>   naive, +0.64%, n=218); `build_dashboard_data` prints it each run. No separate work needed.

> **Promotion cycle (2026-06-09 evening) — bag + wide-grid combo toward a new champion (loop 2 queue)**
>
> User decisions (AskUserQuestion): pursue the combined banked marginals toward formal promotion;
> auto-promote if the full gate passes (with a 2-base-seed confirm); full refresh of CODE_WALKTHROUGH +
> HANDOFF now and **every iteration updates PLAN + CODE_WALKTHROUGH + HANDOFF together**; self-paced loop.
>
> **Queue:**
> - **P1 — docs refresh:** bring CODE_WALKTHROUGH.md + HANDOFF.md current (4-fold basis, new flags
>   --xgb-bag/--lgbm-bag/--xgb-wide-grid/--train-on-cal/--inseason-recal/--inseason-prior/--dc-train-on-cal/
>   --draw-hurdle/--exclude-train-seasons, bagged verification protocol, gate paired-bootstrap advisory,
>   champion pointer resolution, 2021/2025 season-status corrections).
> - **P2 — combo screening:** harness `--xgb-bag 5 --xgb-wide-grid`, 4 folds, base seeds 42 AND 1, vs
>   4-fold bagged controls (s42 control exists: 0.63298; s1 control to run). KEEP toward port iff 2-seed
>   mean gain vs control ≥ ~0.0004 and no 2024/2025 regression beyond tolerance.
> - **P3 — port to research_model.py:** n_bags + wide-grid axes in fit_xgb, threaded through walk_forward
>   and predict_upcoming; parity expectations updated.
> - **P4 — formal gate:** model_report challenger (4-fold, per-match vectors) → promotion_gate evaluate
>   (incl. advisory paired bootstrap) → **auto-promote on PASS** → re-baseline champion.json + all docs +
>   `make validate`.
> - **P5 — wrap:** push branch, loop summary, PLAN verdicts complete.
>
> **Verdicts:** (appended per iteration)
> - **P1 — DONE (iter 1): full docs refresh.** HANDOFF: exec summary + champion metrics rewritten to the
>   4-fold basis (0.6335/cal 0.0360, pointer, 2025-fold finding), gate section now lists all 6 criteria +
>   advisory bootstrap + bagged verification protocol, 13-iteration loop summary table added, gate-threshold
>   arithmetic recomputed vs the 4-fold champion, "What's Next #0" = this promotion cycle. CODE_WALKTHROUGH:
>   w_xgb/cal/report-JSON examples updated to 4-fold, paired_significance documented, harness-vs-gate fold
>   bases clarified, sanity-check numbers updated, new variant-flags table with loop verdicts, harness-vs-
>   model_report cal-measure footnote. P2 screening runs launched concurrently (s1 4-fold control + combo at
>   both base seeds, sequential).
> - **P2 — PASS (iter 2): combo screening clears the pre-registered rule.** 4-fold bagged: s42 ctrl 0.63298 →
>   combo **0.63236** (Δ−0.00062); s1 ctrl 0.63304 → combo 0.63288 (Δ−0.00016). Two-seed mean 0.63262,
>   Δ−0.00039 ≈ the −0.0004 rule, direction consistent; vs champion 0.633471 the combined gain is
>   **−0.00085** (core bar 0.0005). 2024 non-regressing in the paired sense (+0.0000/+0.0003 vs own control);
>   formal 2024 gate decided at P4 on like-for-like research_model reports. → proceed to P3.
> - **P3 — DONE (iter 2): ported to research_model.py.** `fit_xgb(wide_grid=, n_bags=)` now returns a LIST of
>   classifiers + `bag_proba()` helper; threaded through `walk_forward_predictions`, `walk_forward`,
>   `predict_upcoming` (defaults n_bags=1/wide_grid=False are exact no-ops — suite 108 passed). All four
>   external `fit_xgb` callers migrated (build_dashboard_data + 3 probes). `model_report.py` gains
>   `--n-bags/--wide-grid` and records `model_config` in the report JSON. Challenger report
>   (`challenger-bag5-wide`, 4-fold, per-match vectors) building in background → P4 gate next.
> - **P4 — GATE REJECT (iter 3): real Brier gain, but calibration + 2024 guardrails trip.**
>   Challenger `challenger-bag5-wide-16bcf876` (research_model, n_bags=5, wide_grid): avg **0.632623**
>   (core PASS, gain +0.0008; paired bootstrap n=2072, mean Δ+0.00088, **P(better)=0.921**). FAILS:
>   calibration **0.0584 vs limit 0.0410** (champion 0.0360 — the combo is sharper but less calibrated);
>   robustness_2024 0.6349 vs limit 0.6348 (over by 0.0001 — borderline noise); slices >60%-bucket +0.0594
>   (n≈16). Per approved scope (auto-promote only on clean PASS) → **NOT promoted**; champion stays
>   0.633471. The gate did its job — same shape as the referee rejection: Brier edge coupled to a
>   calibration cost. Decision returned to user: accept reject / try bag-only challenger (calibration was
>   harness-better without the wide grid) / pursue calibration fix / override.
> - **P4 retry — bag-only: REJECT by six millionths (iter 4, user-directed).** `challenger-bag5-07c8442c`
>   (n_bags=5, narrow grid): avg **0.632977**, gain +0.000494 vs required 0.0005 (**core FAIL by 6e-6**);
>   2024 0.6349 vs limit 0.6348 (FAIL by ~0.0001); **calibration HALVED 0.0360→0.0182 (PASS)**; slices PASS;
>   paired bootstrap P(better)=0.858. Note: champion's 2024 is a single-seed figure (luck included) while the
>   challenger's is the de-noised bagged estimate — part of the "2024 regression" is luck removal. Both
>   failures are sub-noise; per the clean-PASS-only rule this is NOT auto-promoted. Override decision → user.
> - **P4 resolution — PROMOTED by user override (iter 5, 2026-06-10).** User decision: promote bag-only.
>   `promotion_gate.py promote --force` → champion = `challenger-bag5-07c8442c` (**avg 0.632977, cal 0.0182**,
>   per-season 0.6308/0.6347/0.6349/0.6315); `override_note` recorded in champion.json. Config baked into
>   `models/research_model.py` (**DEFAULT_N_BAGS=5** across walk_forward/predict_upcoming; model_report
>   --n-bags default 5) so production daily updates inherit it. wide_grid stays opt-in (gate-rejected).
>   Suite 108 passed; parity check (bagged defaults vs new champion target) running as final verification.
>   CURRENT_STATE / CLAUDE.md / HANDOFF / CODE_WALKTHROUGH all updated to the bag-5 champion.
> - **P5 — WRAP (iter 6): parity PASS |Δ|=0.0000 (bagged defaults reproduce champion 0.6330 exactly);
>   branch pushed. PROMOTION CYCLE COMPLETE.** Net result: champion 0.633471 → **0.632977** (−0.0005 Brier),
>   calibration 0.0360 → **0.0182**, production deterministic (5-seed bag baked into research_model
>   defaults). Wide grid remains opt-in/gate-rejected; future revisit path = calibration-aware grid
>   selection. Next open fronts: the betting/CLV workstream (opening-line logging now in place).

> **Codebase evaluation (2026-06-09) — integrity findings + ranked Brier opportunities (improvement-loop queue)**
>
> Full read of CODE_WALKTHROUGH / HANDOFF / CURRENT_STATE + harness/model code. Champion 0.6337 confirmed.
> Findings drive the active improvement loop; each item below is resolved one loop iteration at a time and
> annotated here with its verdict when done.
>
> **Integrity findings (fix before/alongside experiments):**
> - **I1 — COVID exclusion drift:** `_COVID = {2020}` since commit 117640c (2026-05-29, message claimed
>   "behavior-preserving"). 2021 is IN training for tests 2023/2024 and IS the cal fold for test 2022 —
>   contradicting CLAUDE.md ("2020 and 2021 excluded", "2022 skips"). Every number since 0.6381 rests on this.
>   → A/B: exclude 2021 from train (keep as 2022 cal fold) vs status quo; align code+docs to the winner.
> - **I2 — `--seed` never reaches XGBoost:** `random_state=42` hardcoded (eval_baseline.py:2231,2263), so all
>   "seed-stability" results were tautological and the gate's 0.0005 threshold has an unmeasured noise floor.
>   → Wire seed through; run 5-seed spread of champion config; record σ.
> - **I3 — Stale champion artifacts:** `data/parity_frame.meta.json` says regress=0.5 (champion is 0.40; report
>   built from uncommitted challenger_r40.pkl) → `make parity-check` guards a stale frame. CURRENT_STATE config
>   table still shows 0.50; HANDOFF says XGB grid fits "on the calibration fold" (code: last 2 train seasons);
>   KEEP bar stated as 0.001 in experiment-protocol.md vs 0.0005 in promotion_gate.py.
>   → Rebuild parity frame at regress=0.40; sync docs.
>
> **Ranked Brier opportunities (T1 = highest (gain × confidence)/effort):**
> - **T1a — Train on the cal season for the final fit.** `train = seasons < cal_season` means the most recent
>   completed season is NEVER training data (test-2024 trains on ≤2022). Fit T/blend-w on cal fold as now, then
>   refit final DC+XGB on train+cal with frozen calibration params. Same waste exists in production
>   `predict_upcoming` (2026 predictions train on ≤2024). Largest untouched lever.
> - **T1b — In-season adaptive recalibration.** Expanding within-season refit of T (and optionally w) on the
>   test season's completed matches, shrunk toward the cal-fold fit. Leakage-safe; escapes the proven
>   "cal-fold-fit calibrator can't anticipate same-year regime shift" trilemma; if it lands, re-test the gated
>   `+Referee` (+0.0010 Brier parked solely on calibration).
> - **T1c — Seed bagging + LightGBM sibling.** Average XGB over 3–5 seeds (uses I2 wiring); test XGB+LGBM
>   average as a blend member (lightgbm already in requirements, never evaluated).
> - **T2a — Time-varying DC home advantage.** DC's static `ha` is the root-caused 2024 failure; give `ha`
>   recency weighting (or time trend) in scripts/eval/dixon_coles.py. Could justify loosening the 30% DC cap.
> - **T2b — NaN-vs-0 missing handling.** All feature matrices use `fillna(0)`; season-opening rolling windows
>   become "0.0 xG", not "unknown". XGB handles NaN natively. One-line A/B.
> - **T2c — Widen XGB search:** min_child_weight / reg_lambda / gamma / early stopping (never swept).
> - **T3a — Draw hurdle architecture** (binary P(draw) + conditional H/A recombination) — low confidence.
> - **T3b — New data (StatsBomb open / FBref-soccerdata)** — lowest priority given the feature graveyard.
>
> **Gate strengthening:** add 2025 completed matches as a 4th test fold (cal=2024); paired bootstrap p-value on
> per-match Brier diffs in promotion_gate.py; commit the rebuilt champion parity frame.
>
> **Loop order:** I3 → I2 → I1 → T1a → T1b → T1c → T2a/T2b/T2c → gate items → T3 (only if plateau persists).
> Verdicts are appended to this block as each iteration completes.
>
> **Verdicts:**
> - **I3 — DONE (2026-06-09, iter 1).** Parity frame rebuilt at regress=0.40 (`--cache --seed 42 --dump-frame`,
>   meta now regress:0.4, 3,982 rows, 2017–2026; frame stays gitignored/regenerable). `parity_check.py` now reads
>   its target from `experiments/champion.report.json` (fallback 0.63369) instead of the stale 0.6347 constant.
>   **Parity PASS: avg 0.6331 vs target 0.63369, |Δ|=0.0006 (tol 0.0015)**; per-season 2022=0.6304/w=0.70,
>   2023=0.6345/w=0.92, 2024=0.6343/w=0.70. Docs synced: CURRENT_STATE config table 0.50→0.40; HANDOFF inner-grid
>   wording (fits on last 2 train seasons, not cal fold); CODE_WALKTHROUGH §7 expected regress 0.5→0.4;
>   experiment-protocol now distinguishes the 0.001 A/B screening bar from the 0.0005 promotion-gate bar.
> - **I2 — DONE (2026-06-09, iter 2). Seed wired; noise floor measured — gate threshold is sub-noise.**
>   `--seed` now reaches both XGB fits (`_XGB_SEED`, default 42 → published references unchanged).
>   5-seed sweep (42,1,2,3,4; Base-only, cached, 2022–24): best_brier mean **0.63372, σ=0.00096, range 0.00242**
>   (seed42=0.63305, worst seed1=0.63519). Per-season 2024 alone ranges 0.6343–0.6381 across seeds.
>   **Implication: the gate's MIN_GAIN (0.0005) ≈ 0.5σ of pure seed noise and the +0.0005 2024 tolerance is
>   swamped — single-seed promotions at the threshold are noise.** Loop policy from iter 3 on: judge experiments
>   on the mean over seeds {42,1,2} (Δ must exceed ~0.0011 ≈ σ·√(2/3)·t to be credible); paired per-match
>   bootstrap in promotion_gate.py stays queued under gate items. Harness cal_err is also seed-volatile
>   (0.130–0.170), so calibration verdicts need the same treatment.
> - **I1 — RESOLVED (2026-06-09, iter 3): keep 2021 in training; docs corrected, not the code.**
>   New `--exclude-train-seasons` flag (training rows only; frame/features/cal folds untouched).
>   3-seed A/B (42/1/2, Base, cached): excluding 2021 = **+0.00190 mean Brier (worse), same direction all
>   seeds** (+0.0022/+0.0007/+0.0028); damage almost entirely on 2023 (Δ+0.0055 — 2021 is its most recent
>   training season); 2022 unchanged (2021 was never in its train), 2024 flat (+0.0002). The accidental
>   2026-05-29 retention of 2021 is empirically right — plausibly because 2021's compressed home advantage
>   resembles the 2024+ regime. CLAUDE.md / HANDOFF / CURRENT_STATE / CODE_WALKTHROUGH all corrected
>   ("2020 excluded; 2021 retained, A/B-validated"). Side-benefit: confirms recent-season training value →
>   raises confidence in T1a (train on the cal season).
> - **T1a — DROP (2026-06-09, iter 4): refit-on-train+cal with frozen calibration is WORSE, Δ=+0.0027.**
>   New `--train-on-cal` flag (kept as a diagnostic): fits T_dc/T_xgb/blend-w/2nd-pass-T on the held-out cal
>   fold exactly as standard, then refits DC+XGB on train+cal and applies the frozen constants
>   (`ens_toc_brier`; `fit_temperature`/`apply_temperature` split added to scripts/eval/calibration.py).
>   Paired 3-seed result: **+0.00372 / +0.00154 / +0.00294 (mean +0.0027, 8/9 season-folds worse)** — far
>   outside seed noise (σ≈0.001). Notably toc cal_err improved (0.13→0.09–0.12) while Brier regressed: the
>   refit model is better-calibrated but less sharp. Interpretation: the calibration constants don't transfer
>   to a model whose season-weighting re-centers on the cal season (ref_s becomes cal_season, hyperparams were
>   tuned for the old reference); the cal-season holdout is load-bearing, not waste. The 2023 gain seen in I1
>   comes from 2021-in-train, NOT from "more recent data always helps". Untested variant (deprioritised, bigger
>   build): season-blocked OOF calibration so constants are fit on predictions from a model that trained on all
>   seasons. Next: T1b (in-season adaptive recalibration).
> - **T1b (scalar T) — DROP (2026-06-09, iter 5), but mechanism identified.** New `--inseason-recal` flag:
>   per-match 2nd-pass temperature refit on cal-fold ∪ strictly-earlier completed test-season matches
>   (leakage-safe expanding pool). Paired 3-seed result: **+0.00048 worse, uniformly** (+0.0004…+0.0006 on
>   every fold × every seed, 2024 included — no regime-tracking benefit, just early-season T noise).
>   **Insight: scalar temperature adjusts sharpness only — it cannot shift class priors, and the 2024 regime
>   shift IS a class-prior problem (home 0.51→0.45).** The trilemma's missing exit is therefore an in-season
>   CLASS-PRIOR correction, not T: queue **T1b′ — per-match shrunk prior reweighting**
>   (p·(π_inseason/π_cal)^λ or Dirichlet-smoothed π, fit on the same expanding pool) as next iteration,
>   before T1c.
> - **T1b′ — DROP (2026-06-09, iter 6), mechanism confirmed real but not net-positive.** New `--inseason-prior`
>   flag: per-match prior-shift correction p′∝p·(π_target/π_cal) on the final ensemble, π_target =
>   Dirichlet-shrunk in-season observed class rates (α∈{50,150,300} pseudo-counts, one pass). Paired 3-seed:
>   **α50 Δ+0.0016, α150 Δ+0.0006, α300 Δ+0.0001 — monotone convergence to no-op; no α beats standard.**
>   BUT at α300, 2024 improves −0.0005…−0.0006 on ALL three seeds (regime tracking works in the regime year)
>   while 2022 pays +0.0011 (prior noise in a reverted year). The trilemma now has a complete map: scalar-T
>   tracks nothing, vector-cal overfits the cal fold, in-season priors trade non-regime years for regime years
>   ~1:1. A regime-CONDITIONAL prior correction (activate only on detected shift) is the only remaining door;
>   parked as multiple-testing-prone. Next: T1c (XGB seed bagging, then LightGBM sibling).
> - **T1c/bagging — INFRASTRUCTURE KEEP (2026-06-09, iter 7).** New `--xgb-bag N`: BestAB XGB refit N times
>   (base seed +1000i), raw probs averaged pre-calibration; AB selection untouched. Paired 3-seed, N=5:
>   **mean 0.63337 vs control 0.63390 (Δ−0.00053); inter-seed σ collapses 0.00111 → 0.00018** (0.63347/
>   0.63349/0.63316). Bagging removes seed luck (unlucky seed 1: −0.0017; lucky seed 42: +0.0004) and lands at
>   the true expected performance. Vs champion 0.63369 the gain is −0.00032 → **fails formal core_metric
>   (needs ≤0.63319), so NOT a champion promotion** — but adopted as the loop's verification protocol:
>   **future experiments are judged on a single `--xgb-bag 5 --seed 42` run (σ≈0.0002) instead of 3-seed
>   means**, cheaper AND tighter. Production port of bagging = open user decision (real ~−0.0004 expected
>   gain + determinism, formally sub-gate). Bagged-control reference: **0.63347** (seed-42, bag-5).
>   Also fixed this iter: a 2026-06-09 edit had orphaned `cal_stage_*` collection into the variant-flag
>   branches (plain runs lost `max_decile_calibration_error`; no verdicts affected — every variant run had its
>   flag on). Restored to the meta block; smoke-test PASS (0.6349 vs ref 0.6346).
> - **T1c/LGBM — DROP (2026-06-09, iter 8).** New `--lgbm-bag N` adds LightGBM members (fixed modest params,
>   same features/weights) to the bag. Single-bagged-run protocol: mix(5 XGB + 5 LGBM) = **0.63556 vs
>   xgb-bag5 control 0.63347 (Δ+0.0021; 2023 +0.0045)**. Untuned LGBM members are weaker and dilute the
>   average. Per-fold-tuned LGBM possible but deprioritised. T1c complete: bagging=KEEP(infra), LGBM=DROP.
> - **T2b — CLOSED without a run (2026-06-09, iter 9): premise invalidated.** Code inspection of
>   `scripts/eval/feature_builders.py`: rolling windows use whatever history exists (15-window with 3 matches
>   averages 3) and empty histories get league-typical priors (xG→1.3, form→1.0 ppg, PPDA→10, poss→50) — there
>   are no destructive season-start zeros. Model-side `fillna(0)` only touches aux features whose neutral IS 0
>   (gk_z etc.). CODE_WALKTHROUGH's "filled with 0" line corrected. Expected gain ≈ nil; no eval spent.
> - **T2a — DROP (2026-06-09, iter 9, redesigned).** ha-trend idea superseded by a decay insight: with the
>   120d half-life, DC's effective sample already ends near train-max — its true handicap is the cal-season
>   gap (predicting T from data ending late T-2). New `--dc-train-on-cal`: refit ONLY DC on train+cal, frozen
>   T_dc/w/2nd-pass-T, bagged XGB. Single-bagged-run: **ens 0.63389 vs control 0.63347 (Δ+0.0004; 2022 +0.0014,
>   2024 +0.0003); DC-alone 0.64504 (no gain)**. In-run standard reproduced control EXACTLY (0.63347 —
>   protocol confirmed deterministic). **Cross-experiment pattern (T1a + T2a): adding recent data to fitted
>   models under frozen calibration consistently loses — the cal-season holdout is what keeps the calibration
>   constants valid.** Next: T2c (wider XGB hyperparameter search).
> - **T2c — SCREENING KEEP (2026-06-09, iter 10): first Brier win of the loop.** New `--xgb-wide-grid`
>   (inner grid + min_child_weight {1,5} × reg_lambda {1,5}, 12→48 combos; non-wide behavior unchanged).
>   Bagged single-run: **0.63299 vs bagged control 0.63347 (Δ−0.00048 ≈ 2.7σ); 2022 −0.0007, 2023 −0.0008,
>   2024 +0.0000 (robustness OK)**. Vs champion 0.63369: −0.00070 → clears formal core_metric (≤0.63319).
>   Harness cal_err 0.1494 (vs 0.1400 in-run control; gate's calibration criterion uses model_report's
>   measure, TBD at port). Seed-1 confirm run in flight; if confirmed → port wide grid (+ optionally bag) to
>   models/research_model.py, build challenger report, run promotion_gate.py.
>   **CONFIRM (iter 11): downgraded to MARGINAL.** Seed-1 bagged confirm: Δ−0.00009 (vs seed-42's −0.00048);
>   two-base-seed mean −0.00029, below the 0.0005 gate bar. Both directions positive → real but small effect.
>   Flag retained; NOT ported/promoted. Lesson reinforced: even bagged single runs need a second base seed
>   before gate claims (the grid *selection* is seed-sensitive even when fits are bagged).
> - **Gate items — DONE (2026-06-09, iter 12): 4-fold re-baseline + paired bootstrap.**
>   (a) **2025 added as 4th test fold** — season is complete (540 matches, cal=2024; the old "2025 never in
>   test window" rule lapsed). Harness 4-fold bagged: 2025=**0.63150**, best season yet → the 2024 regime
>   shift was largely a one-season transition cost; once the cal fold represents the new regime the model
>   handles it. Champion **re-baselined** (same model, new measurement): `champion.json` →
>   `champion-4fold.report.json`, avg **0.633471**, cal 0.0360, per-season 0.6304/0.6345/0.6343/0.6347,
>   n=2,072. Prior 3-fold report retained. `parity_check` follows the pointer; **parity PASS |Δ|=0.0000**.
>   Frame meta test_seasons now [2021–2025] so model_report defaults produce 4-fold challenger reports.
>   (b) **Paired bootstrap in the gate** — model_report embeds per-match Brier vectors; promotion_gate adds an
>   ADVISORY `paired_significance` check (n-paired, mean Δ, P(challenger better); never blocks — tightening it
>   into a hard criterion is a user decision). Gate self-test 6/6; suite 108 passed.
>   CLAUDE.md + CURRENT_STATE updated (test seasons 2022–2025; 2026 = training only).
> - **T3a — DROP (2026-06-09, iter 13).** New `--draw-hurdle`: binary P(draw) XGB owns the draw column;
>   3-class model decides home-vs-away conditionally; standard calibration/blend/2nd-pass downstream.
>   4-fold bagged: **0.63437 vs control 0.63298 (Δ+0.0014; 2022 −0.0012, 2023/24/25 +0.002…+0.003)**.
>   Wrinkle: draw-class Brier IMPROVED (0.19254 vs 0.1934 — first architecture ever to beat the draw column
>   here), but the conditional H/A renormalisation costs more than the draw gain. Draw door now closed at
>   both the feature AND architecture level. T3b (StatsBomb/FBref data acquisition) left as a future project,
>   per its lowest-priority ranking.
>
> **LOOP COMPLETE (2026-06-09, 13 iterations).** Queue exhausted. Durable outcomes: 4-fold re-baselined
> champion (avg 0.6335, parity |Δ|=0.0000), seed-bagged verification protocol (σ 0.0011→0.0002), advisory
> paired bootstrap in the gate, seed wiring, 2021-retention validated + docs corrected, stale-artifact fixes,
> and seven cleanly-refuted hypotheses with mechanisms documented (T1a, T1b, T1b′, T2a, T2b, T3a, LGBM-bag).
> Marginal-positive levers banked, unpromoted: --xgb-wide-grid (−0.0003), --xgb-bag for production
> (−0.0004 expected + determinism — user decision pending).

> **Phase D/E/F (2026-06-07) — monolith split, review loop, production validation**
>
> **Phase D (F4 monolith split) — COMPLETE, behavior-preserving.** Extracted the
> pure Dixon-Coles engine → `scripts/eval/dixon_coles.py` and calibration/metric
> helpers → `scripts/eval/calibration.py` (--calibration threaded as a param;
> eval_baseline keeps thin wrappers so call sites are unchanged). 13 new DC unit
> tests. VERIFIED: `--smoke-test --ab-only Base` → 2024=0.6354, EXACT match to ref
> (|Δ|=0.0000). The 2000-line feature section stays for incremental extraction. (2d011c3)
>
> **Phase E (F1 + circular loop) — COMPLETE.** promotion_gate gains a
> `data_source_health` criterion consuming Phase A's `coverage_gate_status()`
> (self-test now 6/6 incl. degraded-source→reject); model_report embeds a
> source_health snapshot. Legacy `models/{stacking_ensemble,gradient_boost,
> dixon_coles}.py` carry deprecation banners → research_model.py is canonical
> (removal deferred to the production-validated migration). (c5506d6)
>
> **Phase F (production validation) — COMPLETE; referee GATED OUT on calibration.**
> parity_check/model_report are DB-free (frame-based), so the production model was
> validated here, not just on the production host. champ-base report reproduces the champion
> EXACTLY (avg 0.63465, 2024 0.635364, cal 0.0306). Referee challenger via
> research_model (Base + ref_hw_rate + ref_draw_rate):
>   | metric | champion | challenger | gate verdict |
>   |--------|----------|------------|--------------|
>   | avg_brier | 0.63465 | **0.63397** (gain +0.00068) | PASS core_metric |
>   | 2024 | 0.635364 | 0.635662 (Δ+0.0003) | PASS robustness_2024 |
>   | cal_err | 0.0306 | **0.0394** (Δ+0.0088) | **FAIL calibration (tol 0.005)** |
> **RESULT: REJECT ✗.** The review loop did its job — it caught a calibration
> regression that a naive "Brier improved!" promotion would have shipped. Referee
> is a real Brier signal in BOTH harnesses, but `ref_draw_rate` shifts the draw
> distribution in a way scalar second-pass temperature can't recalibrate. Follow-up
> experiment in flight: `ref_hw_rate`-only (drop the draw-rate feature) to try to
> land the Brier gain without the calibration cost. Runbook: docs/PI_VALIDATION.md;
> `make validate` is the DB-free CI gate. (f1c6490)
>
> **Brier-hunt conclusion (referee).** Follow-up `ref_hw_rate`-only challenger:
> avg 0.634537 (gain +0.0001, FAILS core_metric), 2024 0.63812 (Δ+0.0028, FAILS
> robustness), cal 0.0454. So the Brier value lives in **`ref_draw_rate`** (the
> draw signal, F9) — but that is precisely what regresses calibration; the two are
> coupled and inseparable via feature pruning. Per-class/vector calibration (the
> natural fix for a draw-distribution shift) was already tested → DROP (regressed
> 2024). **Net: referee is a genuine Brier signal that is correctly GATED OUT of
> production today** — it needs a calibration method that absorbs the draw shift
> without the vector-cal 2024 penalty (open research item). The signal stays
> available as the eval_baseline `+Referee` AB set + in `+All`; NOT promoted to
> the champion. The headline harness number (0.6327 in champion-config eval) is a
> harness-only figure; the production-faithful number is the gated 0.63397.
>
> **Calibration deep-dive + referee resolution (2026-06-07) — question CLOSED.**
> Built `scripts/probe_referee_calibration.py` (runs research_model walk-forward
> once, caches blends, sweeps 14 calibration variants instantly). Proved a hard
> **trilemma**: across the full scalar↔vector spectrum (tempbias λ / vshrink λ),
> every gain in draw-calibration monotonically worsens 2024 — no cal-fold-fit
> calibration clears gain+2024+cal. Root cause = 2024 HFA regime shift (draw
> correction fit on 2023 misfires on 2024). Then attacked the root cause at the
> FEATURE: season-detrended referee (`+RefereeRel`, ref deviation from league
> prior-season rate). Result via research_model gate: detrended **fixes
> calibration (0.0394→0.0332 PASS) and 2024 (PASS) but the Brier edge vanishes**
> (−0.0003 vs champion → REJECT on core_metric). **Definitive finding: the referee
> edge and its calibration/2024 fragility are the same regime-coupled component;
> there is no robust, promotable referee Brier win.** Champion stays 0.63465.
> Detail: docs/calibration-log.md. (commits 7b9c616 + this)
>
> **8-hour phase loop (2026-06-07) — review findings F1–F9 + Brier hunt**
> Continuous mode, one phase per checkpoint, full eval runs in-repo (live ASA).
>
> **Phase A (F5 data-quality wiring) — COMPLETE.** `daily_update.py` step 9b
> `_data_quality_report()` logs source fetch health + odds 1X2 coverage (WARNING on
> missing-draw, never infer draw_prob=0) + feature null rates. `source_health.py`
> gains `coverage_gate_status()` for the Phase E promotion gate. (commit df6e299)
>
> **Phase B (F7 lockfile/deps) — COMPLETE.** `requirements.txt` upper-bound caps on
> every dep (stops silent major-version drift); `make lock`/`make smoke-test`;
> CURRENT_STATE.md documents Python-3.11 pin + target-side lockfile generation. (a20d076)
>
> **Phase C (referee signal / Brier hunt) — COMPLETE, FIRST BRIER WIN SINCE PLATEAU.**
> `+Referee` (section 5m, season-lagged referee home-win + draw rate from games_raw,
> 86% coverage, zero new API calls) validated as a robust KEEP across two configs:
>   | config | +Referee Δ vs Base | ens avg | 2022 | 2023 | 2024 |
>   |--------|-------------------|---------|------|------|------|
>   | default (xg 3,5,10,15) | **+0.0010** | 0.6340 | 0.6286 | 0.6376 | 0.6357 |
>   | champion (xg 5,15; form 5,10) | **+0.0022** | **0.6327** | 0.6259 | 0.6349 | 0.6374 |
> BestAB=+Referee on ALL three seasons in both runs → improves 2024 vs Base (does not
> regress the hard season). `ref_draw_rate` ranks top-20 XGB importance (2.8%) — the
> **first independent draw signal**, also addressing **F9**. Draw Brier 0.1943→0.1936.
> The 2026-05-31 "referee BLOCKED" note referred to the empty DB `matches.referee_id`;
> the ASA `get_games()` API returns a referee column in the raw frame — gap now closed.
> **Production promotion (port to `models/research_model.py` + parity frame + promotion
> gate) is the production host step** — eval_baseline↔research_model parity gap (~0.002) means the
> gate-quality 2024 number must come from research_model, not the harness. (commits 38d1560, d8bc06f)
>
> **Phase 5 free-source work + leakage tests (2026-06-07)**
>
> **F6/F7 — Security + dependency hygiene (COMPLETE)**
> - F6: Removed three global SSL env-var bypass lines from `eval_baseline.py`
>   (`PYTHONHTTPSVERIFY=0`, `CURL_CA_BUNDLE=""`, `REQUESTS_CA_BUNDLE=""`).
>   The scoped `asa.session.verify = False` already on the ASA client object handles the
>   ASA cert issue; global env-var disablement was disabling TLS for the entire process.
>   `build_dashboard_data.py` already used scoped `verify=False` — no change needed.
> - F7: Added `.python-version` (3.11) so pyenv/mise/uv auto-select the correct interpreter.
>
> **Phase 5m — Referee bias features (COMPLETE)**
> - Added section 5m to `eval_baseline.py`: season-lagged per-referee home-win rate and draw
>   rate derived from `games_raw` (no new API call). Falls back to league-wide averages when
>   the referee column is absent from `games_raw` (graceful, zero-crash).
> - New AB set: `+Referee`. Also included in `_ALL_EXTRA` (and therefore `+All`).
> - Requires `referee` / `referee_id` / `official` column in ASA `get_games()` response.
>   Prior session confirmed ASA `matches` table has `referee_id=None` — the feature will
>   silently fall back to league averages until the column is populated.
>
> **Leakage tests (COMPLETE — prerequisite for Phase 3a split)**
> - Created `tests/test_walk_forward.py`: 10 tests across 4 test classes:
>   - `TestSplitDisjointness`: train/cal/test match-id sets are disjoint; all seasons in train.
>   - `TestNoFutureLeakage`: train dates < cal season start; cal dates < test season start.
>   - `TestRollingFeatureLeakage`: rolling xG excludes the current match and future matches.
>   - `TestRefereeFeatureLeakage`: referee stats use season−1 only; debut-season refs absent.
> - Fixed `pytest.ini` to add `-p no:seleniumbase` (suppresses system-installed seleniumbase
>   conflict that caused INTERNALERROR on all pytest runs without the flag).
> - All 20 tests (10 leakage + 10 metrics) pass: `pytest tests/test_walk_forward.py tests/test_metrics.py`.
> - **These tests are the direct prerequisite for Phase 3a (eval_baseline.py monolith split).**
>
> **Phase 2 + Phase 3 execution (2026-06-07) — data quality accounting + code simplification**
>
> **Phase 2 — Data quality accounting (COMPLETE)**
> - Created `data_pipeline/source_health.py`: `record_source_run()` (writes to source_runs table),
>   `get_source_health_report()` (latest per-source stats), `feature_null_report()` (null rates for
>   key team_features columns). All internal errors swallowed — never crashes a caller.
> - Added `source_runs` table DDL to `db_utils.initialize_schema()` with index on (source_name, fetched_at).
> - Integrated `record_source_run()` into all three primary data clients:
>   `asa_client.sync_to_db()`, `schedule_client.sync_to_db()`, `odds_client.sync_to_db()`.
>   Each records raw_count, parsed_count, matched_count, and error_message.
> - Added `odds_client.odds_matching_report()`: checks upcoming 14-day matches for complete 1X2
>   coverage (home+draw+away). Reports upcoming/matched_all_3/missing_draw/unmatched/coverage_pct.
>   Missing draw odds logged as WARNING — callers must NOT infer draw_prob=0 from absence.
>
> **Phase 3b — Team metadata consolidation (COMPLETE)**
> - Created `data_pipeline/team_metadata.py` as single source of truth:
>   `TEAM_NAME_MAP` (ASA names), `ESPN_TO_TEAM` (ESPN names), `CONFERENCE_MAP`,
>   `FIRST_SEASON`, `TEAM_COORDS` (ASA team_id → lat/lon), `DOME_TEAM_IDS`.
>   Public functions: `resolve_team_id`, `get_conference`, `is_expansion`, `is_dome`, `get_coords`.
> - `asa_client.py` now imports from team_metadata (removed 30-line inline map + conference/expansion defs).
> - `schedule_client.py` now imports from team_metadata (removed 30-line inline ESPN map).
> - `eval_baseline.py` now imports `_TEAM_COORDS` and `_DOME_TEAM_IDS` from team_metadata
>   (removed ~37-line inline definitions).
>
> **Phase 3c — Dashboard config consolidation (COMPLETE)**
> - Added `market.max_edge_threshold_pct: 20.0` to `config/settings.yaml`.
> - Pages 2 and 6 now use `_MKT_CFG["max_edge_threshold_pct"]` instead of hardcoded `15.0`.
> - Page 6 (Backtest) also uses `_MKT_CFG["default_edge_threshold_pct"]` for slider default (was hardcoded 5.0).
> - Pages 6/7/8 beta gate already wired via `dashboard.beta_pages_enabled` in settings.yaml.
>
> **Phase 3a — eval_baseline.py smoke-test gate (COMPLETE)**
> - Added `--smoke-test` CLI flag to `eval_baseline.py`.
> - When set: forces 2024-only test season, then asserts `ens_stacked_brier` ≤ 0.6354 ± 0.001.
>   Pinned reference: champion.report.json (2026-06-06). Exits 0 on PASS, non-zero on FAIL.
> - This is the prerequisite gate before doing the full eval_baseline.py split (Phase 3a main).
> - Full 3a split (eval/{data_builder,feature_registry,...}) deferred — still high-risk without
>   more test coverage; smoke-test gate is now the prerequisite blocker.

> **Standings leverage investigation + F4 feature_registry extraction (2026-06-07)**
>
> **Standings leverage (section 5n) — INVESTIGATED, DROP.**
> Added `_add_standings_features()` to eval_baseline (section 5n): cumulative season pts,
> games played, ppg, pts-vs-median for each team before each match. New AB sets:
>   - `+Standings` (11 features): Δ=-0.0015 → DROP
>   - `+StandingsCore` (3 features: pts_vs_median_diff, season_pts_diff, season_ppg_diff): Δ=-0.0004 → DROP
> Root cause: ELO already captures cumulative season strength; season pts are a noisy
> collinear proxy. The "bubble motivation" asymmetry is structurally present but too
> small/noisy to extract over ELO + form. Standings features remain in parity_frame for
> future exploration but are NOT promoted to Base or champion config.
>
> **F4 feature_registry extraction — COMPLETE (2026-06-07).**
> Created `scripts/eval/feature_registry.py` — pure constants and helper functions
> extracted from eval_baseline.py (behavior-preserving, verified by smoke-test):
>   - Constants: `FIFA_BREAKS`, `HIGH_ALT_IDS`, `PYTHAG_EXP`, `PYTHAG_WIN`
>   - Geometry: `haversine_km`
>   - Feature helpers: `pythag_expected_pts`, `is_post_fifa`, `tz_band`,
>     `away_tz_shift_abs`, `away_tz_shift_signed`
>   - Generic helpers: `zs_within_season`, `lagged_lookup`, `pos_is_att`, `pos_is_def`
> 31 new unit tests in `tests/test_feature_registry.py`. eval_baseline.py now imports
> these from the registry (removes ~75 lines of inline definitions). Smoke-test fixed to
> force `--ab-only Base` when in smoke-test mode (prevents new AB additions from shifting
> the reference). `make smoke-test` PASS (0.6354). Total non-DB tests: 64 pass.
>
> **F3 config alignment + F4 ELO/rolling extraction + F9 H2H draw signal (2026-06-07)**
>
> **F3 — Critical config discrepancy fixed.**
> The champion feat_base (parity_frame.meta.json) uses ALL FOUR xG windows (3, 5, 10, 15)
> and form windows (3, 5, 10, 15). CLAUDE.md said "5 and 15"; config/settings.yaml said
> "[5, 15]"; CURRENT_STATE.md had "[5, 15]". Production feature_builder was therefore
> generating only 2 xG windows while the champion model expects 4. All fixed:
> - CLAUDE.md: "xG windows: (3, 5, 10, 15) matches"
> - config/settings.yaml: `xg_windows: [3, 5, 10, 15]`, `form_windows: [3, 5, 10, 15]`
> - CURRENT_STATE.md: both window lists updated
> - PLAN.md: archived original DuckDB design section with migration note
>
> **F4 — compute_elo() extracted → scripts/eval/elo.py.**
> 14 new unit tests in `tests/test_elo.py` (update direction, season regression, MoV
> multiplier, home advantage, expected probability). eval_baseline.py imports `compute_elo`
> from the module; inline definition removed. Smoke-test PASS.
>
> **F4 — add_rolling_features() extracted → scripts/eval/feature_builders.py (MAJOR).**
> 176 inline lines removed from eval_baseline.py. Function refactored to accept explicit
> parameters (`xg_windows`, `form_windows`, `games_14d_days`, `xpass_by_game`, `has_ppda`,
> `has_poss`, `has_sp_xg`) instead of script-level globals. eval_baseline.py passes those
> explicitly. 34 new unit tests in `tests/test_feature_builders.py` covering output schema,
> walk-forward leakage safety, window correctness, congestion. Smoke-test PASS (0.6354).
>
> **F9 — H2H draw rate (section 5o) — INVESTIGATED, DROP.**
> `add_h2h_draw_features()` added to feature_builders (also section 5o in eval_baseline):
> prior-meeting draw fraction for each team pair (min 3 meetings, direction-agnostic,
> walk-forward safe). AB result: `+H2HDrawRate` Δ=-0.0027 → DROP. Draw class remains at
> 0.1940 Brier. **F9 is now CLOSED**: referee draw signal (gated on calibration), vector
> calibration (gated on 2024), H2H draw rate (DROP) — no free-source draw signal found
> that clears the promotion gate. The draw class weakness is structural.
>
> **Summary of scripts/eval/ package after this session:**
> - `dixon_coles.py` — DC engine (extracted earlier)
> - `calibration.py` — calibration + cal-error metrics (extracted earlier)
> - `elo.py` — ELO model (NEW)
> - `feature_registry.py` — pure constants + helpers (extracted earlier)
> - `feature_builders.py` — add_rolling_features + add_h2h_draw_features (NEW)
> Total non-DB tests: 98 pass.
>
> **dc_p_draw feature + docs (2026-06-07)**
>
> **+DCDrawProb AB test — DROP.**
> `dc_draw_prob_batch()` added to `scripts/eval/dixon_coles.py`: computes the DC analytical
> draw probability (diagonal-only sum, O(max_g) per row, unnormalised) as a new XGB feature.
> Three AB sets tested:
>   - `+DCDrawProb` (dc_p_draw only): Δ=-0.0005 → DROP
>   - `+DCParams`   (dc_lam + dc_mu): Δ=-0.0016 → DROP
>   - `+DCAll`      (all three):      Δ=-0.0026 → DROP
> Root cause: dc_p_draw = f(λ, μ) is a deterministic function of the Poisson parameters,
> which themselves are deterministic functions of team attack/defense strength — already
> captured by rolling xG features in Base. No new signal. Function kept in module for
> reference; dc_p_draw column computed each fold (zero cost) but NOT in Base or _FEAT_ALL.
>
> **Code walkthrough + handoff documents — COMPLETE.**
> - `docs/CODE_WALKTHROUGH.md` (574 lines): guided inspection map — repo orientation,
>   step-by-step prediction trace with file:line refs, eval harness section tour, gate
>   criteria, parity frame columns, sanity check commands, "what looks wrong" table.
> - `docs/HANDOFF.md` (409 lines): standalone technical handoff — champion metrics,
>   architecture rationale, 9 key design decisions, failed feature log with root causes,
>   2024 HFA regime shift explanation, open questions, known limitations, next steps.
>
> **REGRESS=0.40 PROMOTED to champion (2026-06-07)**
> Hyperparameter sweep found that `regress=0.40` with `whl=6` (current default) produces
> a genuine improvement over `regress=0.50`, contradicting the 2026-05-30 finding (which
> used whl=4). Interaction: longer season-weight memory + lower ELO regression is synergistic.
> Harness: avg_brier=0.63367 (Δ=-0.00100 vs champion), 2024=0.6346 (PASS), all three
> test seasons improve. Production validation via `model_report.py`:
>   - avg_brier: **0.6337** (Δ=-0.00095 vs prior champion 0.63465)
>   - cal_err: **0.0195** (was 0.0306 — dramatic improvement, well under gate 0.0356)
>   - 2024: **0.6346** (PASS, tol 0.0005)
> Gate: all 6 criteria PASS → `promotion_gate.py promote` run, champion pointer updated.
> Parity frame rebuilt with regress=0.40 ELO features. CLAUDE.md updated: REGRESS=40%.
> Harness aligned to the new champion: `eval_baseline.py` default REGRESS 0.50→0.40,
> `elo.py` DEFAULT_REGRESS 0.50→0.40, `settings.yaml` season_regression_pct 0.50→0.40,
> smoke-test pin 0.6354→0.6346 (2024 Base). Smoke-test PASS (0.6346±0.001); 98 tests green.
> CODE_WALKTHROUGH.md and HANDOFF.md refreshed to the new champion numbers throughout.
>
> **Remaining review items:**
> - Legacy model deletion (F1): stacking_ensemble.py, gradient_boost.py,
>   models/dixon_coles.py carry banners; deletion deferred to production E2E validation.
> - F4 section 5a–5n builders: inline but rely on live ASA fetches; lower priority now
>   that the two largest functions (ELO, rolling) are extracted and tested.
> - Phase 5 (better data sources): not started; long-horizon exploratory.

> **Phase 4d (2026-06-06) — 2024 distribution-shift diagnosis + calibration unification**
> Built `scripts/diagnose_2024.py`; full writeup in `docs/2024-diagnosis.md`.
> **Finding: 2024 is an OUTCOME regime shift, not a feature shift.** Home-win rate collapsed
> 0.51 (2017–2023 avg) → 0.45 (2024); away-win rose 0.24 → 0.30; goals +0.167/game; draw rate
> stable (+0.001). Feature JS-divergence in 2024 (0.0198) is *lower* than the stable 2023
> transition (0.0308) — inputs on-distribution, home-field advantage eroded. Persists in 2025
> (home 0.443) → new regime, not a one-off. DC bakes static historical HFA into its Poisson
> means and cannot track the drop (root cause of its 2024 catastrophe); the cal-fold-fit capped
> blend correctly down-weights DC to w_xgb=0.70. **Conclusion: capped-DC blend is the right
> structural response, keep it.** Next experiments (run through the gate): shorter DC recent-
> seasons window, ELO HOME_ADV re-sweep on 2024–25, per-class (vector) calibration on the blend.
> Also unified the second-pass blend calibration across walk_forward / predict_upcoming /
> eval_baseline; parity re-confirmed PASS at 0.6353 (target 0.6347, |Δ|=0.0006).
> **Per-class (vector) calibration tested → DROP** (`scripts/probe_vector_calibration.py`,
> `docs/calibration-log.md`): helps 2023 (+0.0045) but regresses 2024 by −0.0135 (avg
> 0.6347→0.6379). Confirms the diagnosis — extra calibration DOF overfit the cal-fold class
> priors and amplify the regime shift; scalar temperature stays canonical. Structural finding:
> no cal-fold-fit calibrator can anticipate a same-year HFA collapse.
> **Shorter DC recent-seasons window tested → KEEP window=4** (`scripts/probe_dc_window.py`):
> 2024 Brier identical (0.6354) across windows 2/3/4/5 — DC home_adv barely moves and the blend
> already floors DC at w_xgb=0.70. No leverage. **Phase 4d model thread closed: no easy 2024 win
> from calibration or DC re-fitting; 2024 is a structurally unforecastable regime shift and the
> capped-DC blend is the optimal response (contains DC-raw 0.649 → ensemble 0.6354).** Remaining
> lever (ELO HOME_ADV re-sweep on 2024–25, owned by hyperparameter-optimizer) deferred — low EV.
>
> **Phase 1 execution (2026-06-06) — metric standardization + canonical path + calibration fix**
> External codebase review (docs/codebase-deep-dive-review.md) commissioned and executed.
> Key findings: two competing production paths (research_model vs old stack), Brier computed
> two incompatible ways (sum-form vs half-form), eval_baseline monolith, config/docs inconsistencies.
> **Phase 1 work completed:**
>   - Created `models/metrics.py` with single authoritative Brier/log-loss functions (10 tests green).
>   - Wired `research_model.py` and `eval_baseline.py` to delegate to `models/metrics.py`.
>   - Labeled all half-form display usage in dashboard/check_drift/performance_report.
>   - **Calibration fix:** temperature was fit on XGB output *before* blending with DC — the blend
>     output was never calibrated (root cause of cal_err 0.1326). Fixed: second-pass temperature on
>     blend output. Result: Brier 0.6381→**0.6347** (+0.0034), cal_err 0.1567→**0.1490**.
>     Per-season: 2022=0.6317, 2023=0.6369, 2024=0.6354 (all improved; 2024 gate holds).
>   - Wired `daily_update.py` step 10 to `research_model.predict_upcoming` (canonical path).
>     Legacy StackingEnsemble kept as dead code; not deleted.
>   - Fixed `config/settings.yaml`: xg_windows [5,15] (was [5,10,20]), edge_threshold 8% (was 5%).
>   - Created `docs/CURRENT_STATE.md` (single source of truth), `Makefile`, updated README.
>   - Added provenance stamp (git commit, model file, metric convention, build time) to `webapp/data.js`.
> **New canonical metric: sum-form Brier 0.6347** (vs naive 0.6406; ~+0.9% over naive).
> All half-form display values (~0.25) now explicitly labeled as ÷2 convention.
>
> **Feature-gap session (2026-06-06) — close the "ideal feature list" gaps · ensemble flat at 0.6375**
> Decision: **market odds stay OUT of the model** — training on closing lines would teach the model to
> echo Pinnacle, collapsing the `model_prob − market_prob` edge we exist to find. Odds remain betting-CLV only.
> Results (all standalone AB sets, NOT added to `_ALL_EXTRA`, so `+All` and the 2024 gate are untouched):
>   - **Untested AB sweep** (`+ASA_TopN`, `+ASA_xPass`, `+TM_SquadValue`, `+TM_Positional`, `+TM_Stars`): **all DROP**
>     (Δ −0.0008…−0.0029). `+SeasonPPDA`/`+SalaryRoster`/`+AvailCongestion` untestable — source data absent
>     (ASA `get_game_xpass` gone; `data/espn_rosters.csv` missing).
>   - **+Weather** (Open-Meteo, `--weather` flag): **DROP** (Δ −0.0013, only 45% archive coverage). Standalone set added.
>   - **+HomeAdv** (per-team home pts-rate − away pts-rate over 20-game window): **marginal +0.0006**, wins BestAB
>     in its own pool (2022 fold 0.6312) but **not selected over `+All`** in full competition → ensemble flat 0.6375,
>     2024 gate holds (0.6389). Registered alongside +TZ_Pythag/+VenueGoalDiff as a real-but-not-ensemble-capturing signal.
>   - **Referee stats: BLOCKED** — no referee_id in ASA match data, no CSV present; the R bridge needs worldfootballR
>     FBref scraping + a Postgres DB and even then returns NA tendencies. Not feasible without a new data-acquisition build.
>   - **Standings leverage**: buildable in-harness (Monte Carlo from the frame) but deprioritised — weak outcome predictor
>     (late-season motivation) for a medium build; pending user go/no-go.
> Net: no headline change (0.6375); ruled out 6 candidate groups, banked one positive-signal feature, documented referee gap.
>
> **Overnight improvement loop (started 2026-06-06) — goal: lower Brier · KEEP bar +0.0005 · 5 hourly iterations**
> Iteration log lives in `docs/improvement-progress.md`; architecture detail in `docs/architecture-log.md`.
> Projections republished to `webapp/data.js` each iteration (pushed to GitHub Pages).
>   - Iter 1 (ensemble blend cap sweep): **DROP** — cap=0.20 vs existing 30%-cap = Δ+0.0001 (within noise).
>   - Iter 2 (hyperparameter sweep: REGRESS, DC-decay): **DROP** — REGRESS=0.5 + DC-decay=120 confirmed 2024-robust.
>   - Iter 3 (stack marginal keepers): **SOFT KEEP** — `+MargCore` added; ensemble 0.6381 → **0.6375** (+0.0006).
>   - Iter 4 (new features: venue-split form + goal-diff form): **REGISTERED, no ensemble gain** —
>     `+VenueGoalDiff` (Δ=+0.0013 KEEP in A/B) registered but never selected over `+All`; ensemble flat 0.6375.
>   - Iter 5 (CuratedAll — positive-only features): **DROP** — +CuratedAll Δ=+0.0007 marginal; XGB handles DROP
>     features internally; removing them doesn't help. BestAB unchanged. Ensemble flat 0.6375.
>   **Loop complete (5/5). Net gain: 0.6381 → 0.6375 (+0.0006, iter 3 only).**
>
> **Live eval results (updated 2026-06-06, overnight loop COMPLETE — 5/5 iterations)**
> Best model: **Ensemble stacked** (DC + XGBoost capped convex blend, DC≤30%) + Base + `+MargCore` candidate + temperature cal.
> best_brier **0.6375** (naive 0.6406; ~+0.5% over naive).
> Net loop gain: 0.6381 → 0.6375 (+0.0006), sole source: iter 3 `+MargCore` BestAB selection for 2023 fold.
> Confirmed KEEP A/B sets: +TZ_Pythag (Δ=+0.0013), +VenueGoalDiff (Δ=+0.0013), +HomeAdv (Δ=+0.0006) — real signals, not yet ensemble-capturing.
> Structural finding: XGB's internal feature selection handles noise effectively — +All consistently wins BestAB.
> Further gains require either new independent signal sources or architecture changes (e.g. DC-free 2024, adaptive cap).
> (Calibration default is `temperature`; `temp_then_platt` exists but is a no-op on the blend — corrected cycle #3. Knob-tuning has plateaued; next gains need new signal.)
> KEPT: (1) capped-DC blend replaces unconstrained LR meta-learner — fixes 2024 (DC stacked 0.6523→0.6378); (2) weight_hl 4→6,
>   a DROP in isolation but unlocked once capped-DC removed the DC drag (greedy re-eval surfaced the interaction). best_brier 0.6388→0.6372→0.6363.
> Trade-off: calibration regressed 0.1015→0.1326 (Platt 2nd-pass is a no-op on the blend); Brier is the stated primary, so accepted.
> Crash fix: XGBoost `n_jobs` capped (default 2, env EVAL_XGB_NJOBS) — 4 parallel all-cores evals OOM-crashed the 16 GB machine.
> DROP this cycle: +MinutesHHI (queue exhausted), larger cal fold (COVID gap), longer DC decay 150/180.
> Open: (1) recover calibration on the blended output; (2) push <0.05 cal via raw-model changes.
>
> **Live eval results (prior, 2026-05-30, parallel cycle #1 — 2-stage post-stack Platt)**
> Best model: stacked ensemble, Base features, **2-stage post-stack Platt calibration** (`--calibration temp_then_platt`).
> best_brier 0.6385 (naive 0.6406; ~+0.3% over naive) · max decile cal_err ~0.0917–0.1015 (was 0.1130; target <0.05 still unmet).
> KEPT: 2-stage post-stack Platt — corrects systematic meta-learner miscalibration at negligible Brier cost (+0.0004, within veto).
> DROP/resolved: REGRESS=0.40 worse than 0.50 (settled; CLAUDE.md "40%" corrected to 50%); weight_hl=2 worse (2024 ≠ stale data);
>   betting-loss blocked (needs real odds column); XGB-only & dynamic ensemble (2024 distribution shift). +PythagLuck/+TZShift marginal (registered).
> Open: (1) cal_err <0.05 needs raw-model changes, not post-hoc calibration; (2) 2024 distribution shift (DC catastrophic in 2024, great 2022-23).
> Detail: `docs/improvement-progress.md`, per-component logs, `docs/future-exploration.md`.
>
> **Live eval results (last run: 2026-05-30, branch `claude/mls-prediction-dashboard-C2mQM`)**
> Improvement loop Iteration 5: calibration (beta + seed-stability test).
> cal-beta → **DROP** (best_brier=0.6377, cal_err=0.1544; Brier marginal +0.0004 vs temp, cal_err regressed +0.0414).
> cal-temperature-seed42 → reference (identical to unseeded: 0.6381/0.1130; confirms structural stability).
> All 4 calibration methods tested: temperature wins both metrics. cal_err=0.1130 is a structural floor.
> No calibration method can reach < 0.05 cal_err from the current model architecture.
> Current best: temperature cal, Base features, DC decay=120d → best_brier=0.6381, cal_err=0.1130.
> Next up: Iteration 6 (hyperparameters) — REGRESS=0.40 (incomplete from Iter 2) + weight_hl=2 to address 2024 weakness.
>
> **Previous live eval results (2026-05-10):**
> Phase 6b eval (1X2 only). Test seasons: 2023–2024 (2022 skipped, COVID cal fold).
> Naive baseline: 0.6469. XGBoost +GKQuality: 0.6387 (+1.3%). Ensemble stacked: 0.6437 (+0.5%).
> Calibration error: 0.1829 (stacked, still poor; temperature scaling; target <0.05).
> ELO: K=25, HOME_ADV=80, REGRESS=40%. DC calibrated: −1.3% (hurts ensemble).
> A/B results (new Phase 6b): +GKQuality KEEP (Δ=+0.0034), +GoalsAdded DROP (−0.0025),
>   +Squad DROP (−0.0018), +DCParams DROP (−0.0016), +Games14d marginal (+0.0005).
> Base now = ELO + xG[5,15] + form[5,10] + GK quality. Feature importances still ~4% each.
> PPDA/possession: unavailable (no get_game_xpass). Set-piece xGA: unavailable.
> DC drag: stacked (0.6437) worse than XGB alone (0.6387). Consider XGB-only ensemble.
> Next: A/B test GK in new Base; explore lineup / injury signal sources for match-level data.
>
> **Phase 7 results (2026-05-16):**
> +ASA_TopN: Δ=−0.0021 → DROP (Top-3/Top-5 outfielder g+ concentration; hurts vs Base).
> +ASA_xPass: Δ=+0.0002 → marginal (minutes-weighted player passing over-expected).
> +ASA_xGSplit: Δ=+0.0006 → marginal (set-piece xG share + xG over-performance;
>   set-piece column unavailable, so this is xG over-performance only).
> +TM_SquadValue: not yet evaluated — run `python scripts/import_transfermarkt.py --seasons 2017-2025`,
>   then `FETCH_TRANSFERMARKT=True python scripts/eval_baseline.py`.
> Per-season: 2022 Brier 0.6284, 2023 0.6352, 2024 0.6493. Naive: 0.6406 avg. +0.5% over naive.
> Calibration still weak (stacked max err 0.1258).
> FotMob: deferred (see "Deferred features" section below).
> Feature-hunt log: `docs/feature-hunt-log.md` (auto-populated every 30 min via /loop).
> Multi-agent improvement workflow: see `docs/experiment-protocol.md` and `/improve-model`.
>
> **Phase 12 results (2026-06-04): minutes-weighted full-roster metrics — ALL DROP**
> +RosterXPA: Δ=−0.0008 → DROP (roster xpoints_added per 90 team-min, full squad ≥90 min).
> +PosGA:     Δ=−0.0032 → DROP (ATT g+ rate + DEF g+ rate per 90 team-min, separate groups).
> +RosterAll: Δ=−0.0045 → DROP (worst combined — features compete and hurt each other).
> soccerdata/FBref: not installed on this machine; +FBref not evaluated.
> Base (3-season avg): 0.6363. Ensemble stacked avg: 0.6386 (+0.3% vs naive 0.6406).
>
> CONCLUSION: Season-lagged player-level ASA data consistently hurts regardless of aggregation method.
>   All tested: raw sum (+Squad −0.0011), top player (+GoalsAdded −0.0013), top-N (+ASA_TopN −0.0029),
>   minutes-weighted xpass (+ASA_xPass −0.0008), minutes-weighted rate (+RosterXPA −0.0008),
>   position-group split (+PosGA −0.0032). ELO + rolling xG already encodes team quality at the
>   match level — season-lagged player metrics are redundant/noise on top of that.
>   EXCEPT contextual/situational features: +TZ_Pythag KEEP (Δ=+0.0013); these carry
>   information the match-level rolling features don't capture.
>
> **Phase 13 (2026-06-06): PELE-style Transfermarkt market-value features — definitive results**
> Inspired by Nate Silver's PELE model. Three iterations to get correct data:
>   Run A — season-lagged (lag=1,2): coverage=90%, all DROP
>   Run B — current-season (lag=0,1): coverage=95%, all DROP or worse
>   Run C — individual player lookup: coverage=100%, player's own most-recent value
>             regardless of which team they were on (mid-season signings, transfers)
>
> Final results (Run C, individual player lookup, 276 team-seasons):
>   +TM_SquadValue:  Δ=−0.0022 → DROP
>   +TM_Positional:  Δ=−0.0021 → DROP
>   +TM_Age:         Δ=+0.0002 → marginal (rescued by player lookup; was −0.0028 in Run B)
>   +TM_Stars:       Δ=−0.0010 → DROP
>   +TM_PELE:        Δ=−0.0019 → DROP
>
> Notable: value-weighted age improved dramatically (+0.0030) when using actual player
>   values rather than stale team aggregates. Intuition: age trajectory is roster-specific.
>   Still below KEEP threshold but no longer hurting.
>
> 2025 added (30 teams, 12% gap filled via lookup).
> 2026 added (30 teams, 100% filled via 2025 player valuations — TM hasn't published 2026).
>
> Best model (Run C): Ensemble stacked Brier=0.6381 (+0.4% vs naive 0.6406).
> Only confirmed KEEP since Phase 12: +TZ_Pythag (Δ=+0.0013).
>
> Infrastructure built:
>   1. worldfootballR R script with kader-page EUR value scraping + 2-year URL fallback
>   2. Cross-season player valuation index in import_transfermarkt.py
>   3. Eval hex→short code mapping (4 overrides: DCU→DC, FCD→DAL, NER→NE, SJE→SJ)
>
> CONCLUSION: TM market values do not improve over ELO + rolling xG in aggregate.
>   Value-weighted age is the only signal worth watching (marginal, not KEEP yet).
>   ELO already captures team quality; raw squad value is collinear noise on top.

---

## Multi-agent improvement workflow (2026-05-29)

The serial `/loop` feature hunt is now backed by a **parallel multi-agent workflow** that dispatches four specialised subagents (feature engineering, calibration, hyperparameters, model architecture), each isolated in its own git worktree, against a shared instrumented harness.

### Key files
| File | Purpose |
|------|---------|
| `scripts/eval_baseline.py` | Research harness — now accepts `--ab-only`, `--calibration`, `--elo-k`, `--elo-home-adv`, `--regress`, `--dc-decay-hl`, `--weight-hl`, `--cache`, `--seed`, `--out` flags |
| `scripts/experiment.py` | Runner (`run`), registry (`compare`), baseline (`baseline`) |
| `scripts/run_improvement_cycle.sh` | Headless single-component cycle for autonomous/cron use |
| `docs/experiment-protocol.md` | Shared agent contract (KEEP/DROP rules, scope guards, logging) |
| `docs/experiment-schema.json` | JSON schema for harness result files |
| `experiments/registry.jsonl` | Append-only experiment history |
| `.claude/agents/feature-engineer.md` | Feature engineering agent definition |
| `.claude/agents/calibration-tuner.md` | Calibration agent definition |
| `.claude/agents/hyperparameter-optimizer.md` | Hyperparameter agent definition |
| `.claude/agents/model-architect.md` | Architecture agent definition |
| `.claude/commands/improve-model.md` | `/improve-model` orchestrator command |
| `docs/calibration-log.md` | Calibration experiment log |
| `docs/hyperparameter-log.md` | Hyperparameter experiment log |
| `docs/architecture-log.md` | Architecture experiment log |

### Quick start
```bash
# 1. Record baseline (pre-warms the ASA data cache)
python scripts/experiment.py baseline --cache

# 2. Run one agent (e.g. calibration sweep — no code changes, flags only)
python scripts/experiment.py run --name cal-platt --cache -- --calibration platt --ab-only "Base"

# 3. Compare all experiments
python scripts/experiment.py compare

# 4. Full parallel cycle via Claude Code
/improve-model
```

### Design decisions
- The KEEP threshold is Δ > 0.001 Brier (same rule as the existing AB_SETS framework)
- Greedy forward-merging (re-eval after each merge) rather than simultaneous because calibration, hyperparameter, and architecture agents all touch overlapping harness regions
- `--cache` freezes ASA data at the start of each cycle so deltas are from the same dataset
- Production port (features/, models/, config/) is a separate step; research harness is always the gate

---

## Phase 11 — Data Expansion toward +5% (opened 2026-05-31)

**Goal (user):** best_brier ≤ **0.6086** (5% better than naive 0.6406). Current 0.6363 (+0.67%). Pursue richer data: team/player/manager/conditions, and especially **lineup/roster state**. Market-blind (model must stay blind to betting odds to preserve edge — the production purpose).

**Honest ceiling (research):** peer benchmarks ([Wilkens 2026, Bundesliga](https://journals.sagepub.com/doi/10.1177/22150218261416681)) — a strong xG model scores Brier ~0.63, the **bookmaker market ~0.59**, in a *more predictable* league than MLS. +5% (0.6086) is below the market's own Brier; market-blind in high-variance MLS it is likely **beyond the achievable frontier**. Realistic ambitious target: close the gap toward the MLS market-implied Brier (~0.61–0.63). Pursue hard; report the true frontier rather than spin on an impossible number.

**New data sources found (all free):**
- **ASA player salaries** (`get_player_salaries`) — `guaranteed_compensation` per player/season, **100% coverage 2017-2024**, set pre-season (leakage-safe same-season), captures DP/star structure. The right roster-quality weight (fixes the g+ coverage gap that sank +Availability).
- **ASA managers** (`get_managers`), **team salaries**, **GK goals-added** — unused, queued.
- **ESPN box-score rosters back to 2017** (verified) — enables full-history lineup features.

**Task log:**
- **T1 — salary-weighted roster** (`+SalaryRoster`: payroll-share active + DP-available; `+RosterState`: g+ avail + salary): **DROP** (Δ−0.0008 / −0.0012) — **but CONFOUNDED**: roster data only existed 2022-2024, so the walk-forward had ≤1 roster-populated training season; the feature was untrainable on most folds. Not a valid verdict.
- **T2 — backfill ESPN rosters 2017-2021** ✅ DONE: full 2017-2024 roster history (3,227 matches, 123k player-rows; 2017 join 96%).
- **T3 — FAIR roster A/B (Iteration 1)** ✅ **KEEP**: with full training history, `+Availability` (g+ roster-share, expanding-mean normalized) Δ=**+0.0011 → KEEP**; salary-share variants DROP. **Promoted to Base: best_brier 0.6363 → 0.6344 (+0.97% over naive).** The lineup hypothesis holds once given history; the earlier DROP was a 3-season-history confound. **Goal 0.6086 still ~4% away.**
- **T4 — team salary (Iteration 2)** ❌ DROP (Δ=−0.0045): payroll/DP-concentration redundant with ELO. Talent-investment proxies (player salary-share + team payroll) now both confirmed redundant. Default unchanged 0.6344.
- **T5 — starter-weighted availability (Iteration 3)** ❌ DROP (Δ=−0.0013): redundant with active-squad availability already in Base. The lineup signal is one feature, not deepenable.
- **T6 — GK distribution g+ (Iteration 4)** ❌ DROP (Δ=−0.0014): non-shotstopping GK g+ redundant with GK quality in Base.
- **T4+ (loop iterations 2-5, hourly):** next data sources — ASA managers/team-salaries/GK-goals-added, weather, FBref richer signals; and refine the availability feature (starter-XI vs matchday-squad weighting).

---

## Phase 10 — Production Port (opened 2026-05-31)

**Why:** the research harness validated a materially better model (0.6392→0.6363) but the live pipeline (`features/`, `models/`, `config/`) still runs an older, unvalidated config. Per CLAUDE.md ("improve eval first, then port"), this port is overdue. **Constraint discovered: no DuckDB in this env, so the production pipeline can't be run end-to-end here** — verification is unit tests + clean imports + config-flow checks; full E2E must run on the production host/production box.

**DONE (verified here):**
- **Fixed the long-standing `datetime` NameError** in `models/stacking_ensemble.py` (missing import) → test suite now **10 passed / 1 skipped** (was 9/1-fail all session).
- **Aligned wired+validated config** in `config/settings.yaml` to CLAUDE.md decisions, confirmed consumed by production modules: ELO `k_factor 20→25`, `home_advantage_elo 100→80`, `season_regression_pct 0.30→0.50`; Dixon-Coles `time_decay_half_life_days 180→120`.

**DEFERRED — structural sub-step (needs CODE changes + production-env E2E validation):**
- **Capped-DC convex blend** — replace the LR+isotonic meta-learner in `models/stacking_ensemble.py` `fit/predict` with the validated `w*XGB+(1-w)*DC, w∈[0.7,1.0]` blend.
- **Temperature calibration** — code hardcodes `CalibratedClassifierCV(method="isotonic")`; wire it to the validated temperature method (the `calibration_method` YAML is currently ignored).
- **XGB season weighting `weight_hl=6`** — add to `models/gradient_boost.py` (absent in prod).
- **xg_windows [5,10,20]→[5,15]** and **drop the O/U model** (research is 1X2-only) — feature/structural changes.
- These change prediction behavior and must be validated on the production host (DuckDB + data) before deploy; the unit tests don't exercise the blend math.

**STATUS: config + bug-fix ported and verified; structural model port specified.**

### Phase 10b — CSV-backed local validation (no host needed) — 2026-05-31

**Key finding:** the production model classes are **DataFrame-in and DB-agnostic** (`DixonColesModel.fit(df)`, `GradientBoostModels` uses *dynamic* `get_feature_columns(df)`, `StackingEnsemble.fit(oof_df)`). The DB (Postgres) only feeds `feature_builder.build_training_dataset()` and stores predictions — **not the model logic**. So the structural port can be validated **locally on a CSV frame**; only the DB read/write IO waits for the production host.

**Built:** `scripts/eval_baseline.py --dump-frame` exports the validated feature frame → `data/parity_frame.parquet`; `scripts/parity_check.py` runs production model classes on it, no DB. **Proven:** production `DixonColesModel` runs DB-free on the CSV frame (DC-alone Brier ~0.654, expected ballpark) ✓ — the local validation loop works.

**DONE — shared validated model module + parity gate (2026-05-31):**
- `models/research_model.py` — single, importable, DataFrame-in implementation of the validated 1X2 pipeline (DC fit + season-weighted XGB grid + temperature calibration + capped-DC convex blend; weight_hl=6, dc_decay_hl=120, no O/U). The production-bound model logic, decoupled from Postgres.
- `scripts/parity_check.py` — runs it on `data/parity_frame.parquet` (+ `.meta.json` sidecar from `--dump-frame`) and asserts parity with the research headline. **RESULT: avg_brier 0.6353 vs target 0.6363, |Δ|=0.0010 → PASS**, fully DB-free.

**Remaining (production-side IO only):** wire the production pipeline (`scripts/daily_update.py`) to fit/predict via `models/research_model.py` instead of the divergent `GradientBoostModels`/`StackingEnsemble`, and store predictions to Postgres. The model is validated; the production host sees only the DB read/write wiring. This eliminates the two-divergent-stacks drift — there is now ONE validated model implementation.

---

## Phase 9 — Match-level Availability via ESPN box scores (opened 2026-05-31)

**Why:** Phase 8 closed because match-level availability (the one lever with real upside) wasn't reachable from ASA. Per the documented re-entry condition, Phase 9 verifies + builds the ESPN box-score integration.

**Feasibility — VERIFIED (2026-05-31):** ESPN hidden API `summary?event={id}` (`site.api.espn.com/apis/site/v2/sports/soccer/usa.1`) returns full per-match **rosters back to 2022**: each player has `starter`, `subbedIn`, `subbedOut`, `active`, `position`, `athlete.displayName`. Match-level participation EXISTS, is free, and covers the 2022-2024 eval window. The data-availability blocker that killed the ASA approach is resolved.

**Build plan:**
1. **Scraper** (`data_pipeline/` + cache to CSV like weather/TM): enumerate MLS event IDs per date via `scoreboard?dates=YYYYMMDD`, fetch `summary` per event (~1,530 matches over 2022-2024), extract per-team matchday roster (active players + starter/sub flags). Cache to `data/espn_rosters_*.csv`; polite rate-limiting.
2. **Name-join (THE RISK):** match ESPN `displayName` → ASA player (which holds g+/xG/xA quality). Needs a fuzzy/normalized name map + a coverage report; unmatched players degrade the index. De-risk this on one season before the full scrape.
3. **Availability index:** per match, `avail_g+_share = Σ(season g+ of active players) / Σ(season g+ of full squad)`, computed for attackers (xG/xA) and GK. Leakage-safe (uses the matchday roster, known at kickoff, × prior-season quality).
4. **AB set** `+Availability` → `experiment.py run --cache --seed 42 -- --ab-only "Base,+Availability"` → KEEP if Δ>0.001.

**Risks:** name-join coverage; ESPN scrape fragility/rate limits; whether availability adds signal beyond ELO/form (the empirical question). Free throughout (ESPN no-key).

**Name-join — VERIFIED (2026-05-31):** on a 25-match 2023 sample (452 ESPN active players), ESPN→ASA normalized name match = **91% exact / 97% with last-name fallback**. The 13 unmatched are backup/3rd-choice GKs + fringe players (near-zero g+) → effective quality-weighted coverage is higher. The join risk is resolved.

**Build — COMPLETE (2026-05-31):** scraped 1,534 matches / 60.7k player-rows (`data/espn_rosters.py` → `data/espn_rosters.csv`, gitignored/regenerable); team-join 100% (suffix+alias map); player-name→ASA-quality join ~70% appearance-weighted; built `+Availability` = avail-weighted xG+xA share (prior-season quality, expanding-mean normalized, leakage-safe). Hardened `_cf` (tolerates ASA list-columns) + retry on quality fetch.

**VERDICT: +Availability → DROP (Δ=−0.0001, seed=42, 73% test-season coverage).** Match-level availability does NOT measurably improve Brier on 2022-2024. Best model unchanged at **0.6363** (Base; +Availability registered, not promoted).

**Why (likely):** recent form (rolling xG/xGA + ELO) already absorbs availability — a team missing key players has been producing worse recent results, which the rolling features encode. Availability is largely redundant with form. Caveats: only 3 seasons of roster data; prior-season quality weights miss ~30% of playing time (new signings); the 2022 test fold has no availability variation in its training window. Even granting these, the signal is absent (not even marginally positive).

**STATUS: Phase 9 CLOSED — availability tested and DROPPED.** This was the last identified lever with plausible upside; the model is genuinely plateaued at 0.6363 (+0.67% vs naive). Durable assets banked: ESPN roster scraper, the availability feature (registered), `_cf` robustness fix. The improvement program has an earned conclusion.

---

## Phase 8 — Feature Expansion & Subagent Roster Expansion (planned 2026-05-30)

> **STATUS: CLOSED 2026-05-31 — Option A (stop & bank).** The ASA-only feature hunt is concluded.
> Two phases blocked at the *data layer* (not modeling): the cheap tier is absorbed/unavailable and
> the availability flagship needs per-game data ASA doesn't provide. **Banked best model: best_brier
> 0.6363 / cal_err 0.1326 (~+0.67% over naive)** — capped-DC convex blend + weight_hl=6 + temperature,
> Base features. This is judged near the ceiling for free, season-aggregate, ASA-only data.
> **Re-entry condition:** reopen only by committing to an **ESPN box-score / lineup scraping integration**
> (per-game participation → match-level availability), after first verifying 2022-2024 historical depth.
> Durable deliverables retained: instrumented harness + `experiment.py`, multi-agent `/improve-model`
> workflow, capped-DC architecture, XGBoost thread cap, and this realistic, annotated plan.

**Why:** Knob-tuning has plateaued at **best_brier 0.6363 / cal_err 0.1326** (~+0.67% over naive). Every parameter sweep + post-hoc calibration tweak now DROPs; the only KEEPs were structural (capped-DC blend, weight_hl unlocked by it). Further gains require **new signal — richer team/player features**, not more sweeps. Plan built from a 28-question requirements deep-dive.

**Hard constraints:** all sources **free** (ASA, ESPN, Open-Meteo, Transfermarkt-via-R); **Brier sole KEEP metric** (Δ>0.001, calibration reported not gated); venue **cloud-when-free-credits else local-sequential** (thread-capped).

**Design decisions:** roster/injury-aware (not full XI) · in-season rolling preferred (as-of cutoffs) · opt-in DB reads behind a flag (default DB-free) · feature-**family** discovery (sweep a family, isolate winner) · breadth-first (cheap probes first, then deepen).

**Keystone unlock — availability from ASA minutes:** proxy historical absences from per-player minutes (a regular starter whose minutes collapse to ~0 was likely out). Reconstructs availability for 2017-2024 free, no scraping, leakage-safe (as-of match date). ESPN injuries handle live/forward; minutes-proxy handles backtest.

> **⚠️ EXECUTION FINDINGS (2026-05-31) — major data-feasibility blocks discovered on kickoff:**
> - **Phase A cheap tier is a dead end:** +TravelRest and +Context both DROP (−0.0002, absorbed by ELO/form). Set-piece xG splits and game-level PPDA/possession are **not populated in ASA's MLS feed** (so +ASA_xGSplit-conceded and rolling tactical-style are impossible, not just untested).
> - **Phase C keystone is INFEASIBLE as designed:** ASA player endpoints are **season-aggregate only — no per-game minutes**. The "injury proxy from ASA minutes" cannot work (a season total can't reveal which matches a player missed). Match-level availability would require **ESPN box-score/lineup scraping per game** (heavier build; 2022-2024 historical-depth unverified) — a different, larger project than planned.
> - **Transfermarkt:** `worldfootballR` install **failed** on macOS (system-dep issue); still blocked.
> - **Implication:** 0.6363 (+0.67% vs naive) may be near the genuine ceiling for free, season-aggregate, ASA-only data. The remaining real lever (match-level availability via ESPN box scores) is a scraping-integration decision, not a quick feature. Revisit the family list below only after that decision.

**Feature families (ORIGINAL plan — superseded in part by the findings above):**
- *Phase A — cheap probes:* travel/rest + context = DROP; set-piece-conceded + tactical-style = data-unavailable. Tier exhausted.
- *Phase B — data layer:* the ASA-minutes injury proxy is infeasible (see findings); ESPN forward-injuries + opt-in DB + referee remain *possible* but unvalidated.
- *Phase C — flagship:* availability-weighted g+ requires **per-game** participation data ASA does not provide → blocked pending an ESPN box-score integration decision.
- *Phase D — interactions:* matchup style×style + availability×congestion — depends on the above data, currently blocked.
- *Parked:* 2024 distribution-shift (capped-DC masks it); FBref/R (fragility).

**New subagents (`.claude/agents/`):** `data-integrator` (free-source wiring, minutes-proxy, opt-in DB), `availability-modeler` (avail-g+ family end-to-end), `feature-interaction` (marginal×marginal + matchup sweeps). Existing 4 agents move to family-discovery mode.

**Files:** `scripts/eval_baseline.py` (per-player extraction helpers, minutes-availability index, rolling style features, new `AB_SETS`, opt-in DB flag); `scripts/import_transfermarkt.py`; port from `features/{travel_features,match_context,referee_features}.py`; `data_pipeline/injury_scraper.py` + minutes-proxy helper; new agent defs + `.claude/commands/improve-model.md` (family discovery + venue policy).

**Verification:** each family → `+Family` AB set → `experiment.py run --cache --seed 42 -- --ab-only "Base,+Family"` → KEEP if Δ>0.001 → promote to `_FEAT_BASE`; minutes-proxy leakage test (as-of cutoff; spot-check a known injury reduces `avail_g+_share`); opt-in DB flag OFF reproduces 0.6363 exactly; `pytest` green; runs stay local-sequential / free-credit cloud.

---

## Deferred features

- **FotMob integration** — deferred 2026-05-16. No documented public API; `pyfotmob` is reverse-engineered against the mobile endpoint and can break silently on any FotMob frontend change. Revisit only if ASA player metrics + Transfermarkt squad value plateau; needs an explicit ADR on scraping cost/risk vs incremental signal. Likely candidates if revived: per-match player ratings (avg starter rating, top-3 starter mean, defensive line rating). Same one-time-fetch-cached-to-CSV pattern as weather.
- **Lineup-aware availability features** — predicted/actual lineups × player g+. Source data lives in the production `predicted_lineups` DB table and the eval harness is DB-free by design (`scripts/eval_baseline.py:3`). Would require lifting the eval-DB-free constraint; reconsider after Phase 7 results.

---

## Context

> **NOTE (2026-06-07): The sections below this line are the ORIGINAL DESIGN DOCUMENT**
> **(DuckDB era). The production stack migrated to PostgreSQL; daily_update.py and**
> **db_utils.py use Postgres exclusively. DuckDB references below are historical only.**

Build a production-grade MLS score prediction and betting-market tracking system from scratch. The system must predict Win/Draw/Loss and Over/Under outcomes for all MLS regular season and playoff matches using an ensemble of statistical and ML models, compare model probabilities to Pinnacle odds for edge detection, and present all of this through a Streamlit dashboard with live news integration. Everything runs on a the production host (DuckDB storage + daily cron + Streamlit), exposed publicly via a free Cloudflare Tunnel.

---

## Repository Structure

```
MLS/
├── config/
│   └── settings.yaml              # All tunable parameters (half-life, Kelly fraction, edge threshold default, etc.)
├── data_pipeline/
│   ├── __init__.py
│   ├── asa_client.py              # American Soccer Analysis API (itscalledsoccer pkg)
│   ├── odds_client.py             # The Odds API → Pinnacle pre-match + closing odds
│   ├── schedule_client.py         # ESPN hidden API for fixtures + results
│   ├── injury_scraper.py          # Injury/suspension binary flags (scraping + RSS)
│   ├── news_monitor.py            # RSS feed polling + Claude API impact scoring
│   └── db_utils.py                # DuckDB read/write helpers
├── features/
│   ├── __init__.py
│   ├── elo_ratings.py             # Continuously-updated ELO (new team = league-average prior)
│   ├── xg_features.py             # Rolling xG, xGA, xGD windows (configurable)
│   ├── travel_features.py         # Great-circle distance, days rest, games-in-N-days
│   ├── referee_features.py        # Per-referee card rate, penalty rate, home-win rate
│   └── feature_builder.py         # Assembles all features into a single match-level dataframe
├── models/
│   ├── __init__.py
│   ├── dixon_coles.py             # Dixon-Coles Poisson with exponential time-decay
│   ├── gradient_boost.py          # XGBoost + LightGBM multiclass (1X2) + binary (O/U)
│   ├── stacking_ensemble.py       # Logistic regression meta-learner over all model probs
│   └── r_bridge/
│       ├── bayesian_elo.R         # brms hierarchical Poisson; ELO as informative prior
│       └── run_bayes.py           # rpy2 bridge: serialize features → R → return posteriors
├── market/
│   ├── __init__.py
│   ├── clv_tracker.py             # Closing Line Value vs Pinnacle
│   └── kelly.py                   # Fractional Kelly (25% / 50%) stake sizing
├── dashboard/
│   ├── app.py                     # Streamlit entry point (multi-page)
│   └── pages/
│       ├── 1_Predictions.py       # Upcoming game prediction cards + value bet alerts
│       ├── 2_Performance.py       # Brier, log-loss, CLV, ROI over time; segmented views
│       ├── 3_Calibration.py       # Reliability diagrams, calibration curves
│       ├── 4_News_Overrides.py    # RSS news feed, Claude summaries, manual adjustment panel
│       └── 5_Betting_Tracker.py   # Simulated bet log, Kelly P&L, edge threshold filter
├── scripts/
│   ├── daily_update.sh            # Cron entry point (activates venv, runs pipeline)
│   ├── daily_update.py            # Orchestrates full daily ETL + retrain
│   └── backfill_history.py        # One-time load of full MLS history into DuckDB
├── requirements.txt
├── r_requirements.R               # install.packages() script for R dependencies
└── README.md
```

---

## Phase 1: Data Layer

### 1a. DuckDB Schema (db_utils.py)

Tables:
- `matches` — match_id, date, season, home_team, away_team, home_goals, away_goals, home_xg, away_xg, conference_h, conference_a, is_playoff, referee_id
- `team_features` — match_id, team_id, role (home/away), elo_pre, xg_rolling_5, xg_rolling_10, xga_rolling_5, xga_rolling_10, travel_km, days_rest, games_in_14d, dp1_available, dp2_available, dp3_available, supporter_shield_locked, form_5
- `elo_history` — team_id, date, elo_rating
- `referee_stats` — referee_id, name, card_rate_per90, penalty_rate_per90, home_win_rate
- `predictions` — match_id, model (dixon_coles | xgboost | bayesian | ensemble), prob_home, prob_draw, prob_away, prob_over, prob_under, predicted_at
- `odds` — match_id, bookmaker, market, outcome, open_odds, close_odds, fetched_at
- `news_items` — item_id, published_at, source, headline, url, teams_mentioned, claude_summary, estimated_impact_home_atk, estimated_impact_home_def, estimated_impact_away_atk, estimated_impact_away_def, confirmed_by_user, applied_to_match_id
- `overrides` — match_id, applied_at, description, home_strength_adj, away_strength_adj
- `simulated_bets` — bet_id, match_id, market, outcome_backed, model_prob, market_prob, edge_pct, stake_kelly25, stake_kelly50, result, pnl_kelly25, pnl_kelly50

### 1b. Data Sources

| Source | Package / Method | Data |
|--------|-----------------|------|
| American Soccer Analysis | `itscalledsoccer` (Python) | xG, xA, goals added, possession, match results |
| FBref | `worldfootballR` (R, called via rpy2) | Referee data, advanced player stats |
| ESPN hidden API | `requests` + JSON | Schedules, scores, injury reports |
| The Odds API | `requests` | Pinnacle pre-match + closing 1X2 odds (500 req/month free tier) |
| Transfermarkt | `worldfootballR` (R) | Player market values, DP identification |
| RSS feeds | `feedparser` | ESPN MLS, MLSSoccer.com, team blogs for news |

### 1c. Historical Backfill (backfill_history.py)

- Pull all MLS seasons (1996–present) from ASA API
- Compute ELO ratings chronologically from season 1 forward
- Scrape historical referee assignments from FBref via worldfootballR
- Seed DuckDB with all historical match + feature data
- Expected runtime: 30–60 minutes on first run

---

## Phase 2: Feature Engineering

### ELO System (elo_ratings.py)
- Standard ELO formula with K-factor = 20 (tunable)
- Home advantage = +100 ELO points for expected score calculation
- Margin-of-victory multiplier: `1 + log(goal_diff + 1) * 0.1`
- New/expansion teams start at 1500 (league average)
- Update after every match; store full time series in `elo_history`

### xG Features (xg_features.py)
- Rolling windows: 5, 10, 20 matches for xG, xGA, xGD
- Exponential decay: each past match weighted by `exp(-λ * days_ago)` where λ = `ln(2) / half_life_days` (half_life_days configurable in settings.yaml, default = 60)
- Separate home and away rolling averages

### Travel Features (travel_features.py)
- Team stadium coordinates hardcoded (static MLS stadium list)
- Great-circle distance between stadiums using `haversine` formula
- Features: `travel_km`, `days_since_last_match`, `matches_in_14_days`, `cross_conference_game`

### Referee Features (referee_features.py)
- Pull referee assignment from FBref per match
- Rolling referee stats: cards/90, pens/90, home_win_rate over last 50 officiated games
- Fall back to league-average if referee is new

### MLS-Specific Features (feature_builder.py)
- `is_playoff`: binary flag
- `conference_matchup`: EW / EE / WW
- `expansion_team_flag`: first 2 seasons of existence
- `supporter_shield_locked`: both teams' shield seedings are mathematically set
- `dp_available_count`: number of DPs available (0–3) per team

---

## Phase 3: Models

### Model A — Dixon-Coles Poisson (dixon_coles.py)
- Attack (α) and defense (β) parameters per team, home advantage (γ) global
- Dixon-Coles low-score correction (ρ parameter) for 0-0, 1-0, 0-1, 1-1
- Exponential time-decay weights on historical matches
- Maximum likelihood estimation via `scipy.optimize.minimize`
- Output: full score probability matrix → P(home win), P(draw), P(away win), P(over 2.5), P(under 2.5)
- Retrain: nightly on all historical + current season data

### Model B — Gradient Boosting (gradient_boost.py)
- XGBoost multiclass for 1X2 (3 classes)
- LightGBM binary for O/U 2.5
- Features: all engineered features from Phase 2 + injury flags
- Time-series cross-validation (no future leakage): 5 folds on rolling windows
- SHAP values computed and stored for interpretability panel
- Hyperparameter tuning: `optuna` with Brier score objective
- Retrain: nightly (fast enough for daily cadence)

### Model C — Bayesian Hierarchical (r_bridge/bayesian_elo.R)
- Framework: `brms` (Stan backend)
- Likelihood: Bivariate Poisson for home_goals ~ Poisson(λ_h), away_goals ~ Poisson(λ_a)
- Linear predictor: `log(λ_h) = μ + home_adv + atk_h - def_a`, `log(λ_a) = μ + atk_a - def_h`
- Priors: team attack/defense drawn from Normal(elo_scaled, σ) — ELO used as informative prior mean
- Expansion teams: wider prior variance (more uncertainty)
- Posterior predictive: sample 4000 draws → compute match outcome + O/U probabilities
- Output written to temp CSV, read back by run_bayes.py
- Retrain: nightly (MCMC, ~5–10 min with 4 cores)

### Model D — Stacking Ensemble (stacking_ensemble.py)
- Level 0 inputs: prob_home, prob_draw, prob_away, prob_over from all 3 models (9 features for 1X2, 3 for O/U)
- Level 1 meta-learner: isotonic-calibrated logistic regression (preserves calibration)
- Training: time-series cross-validation; Level 0 preds generated on hold-out folds
- Calibration check: compare ensemble to individual models via Brier score on validation set
- This is the primary model output used for all market comparison

---

## Phase 4: Market Comparison & Betting Tracker

### CLV Tracker (market/clv_tracker.py)
- Fetch Pinnacle opening odds at prediction time, closing odds at match kickoff
- Model implied probability = `ensemble_prob`
- Market implied probability = `1 / (pinnacle_odds / vig_adjusted)` — use Pinnacle's low vig as reference
- Edge at open = `model_prob - open_implied_prob`
- CLV = `open_implied_prob - close_implied_prob` (positive CLV = beat closing line)
- Store both in `odds` and `simulated_bets` tables

### Kelly Sizing (market/kelly.py)
- Full Kelly: `f = (b * p - q) / b` where b = odds-1, p = model_prob, q = 1-p
- 25% Kelly: `f_25 = 0.25 * f`
- 50% Kelly: `f_50 = 0.50 * f`
- Only stake when `edge_pct >= configurable_threshold` (dashboard slider)
- Bankroll tracked separately for 25% and 50% Kelly simulations

---

## Phase 5: News Pipeline

### RSS Monitor + Claude Integration (data_pipeline/news_monitor.py)
- Poll these RSS feeds every 6 hours: ESPN MLS, MLSSoccer.com, team official blogs
- Filter articles containing keywords: injury, suspended, red card, out, available, return, doubt, questionable
- For each flagged article: call Claude API (claude-sonnet-4-6) with prompt asking to:
  1. Identify affected team(s) and player(s)
  2. Estimate % impact on team attack strength (-20% to +10% range)
  3. Estimate % impact on team defense strength
  4. Assign confidence level (high/medium/low)
- Store result in `news_items` table
- Dashboard (Page 4) shows unconfirmed items for user review
- User clicks "Apply" to write to `overrides` table; override factors applied at prediction time

---

## Phase 6: Streamlit Dashboard

### Page 1 — Predictions (Upcoming Games)
- Grid of prediction cards per upcoming match (next 7 days)
- Each card: home team logo, away team logo, date/time, win%/draw%/loss%, predicted xG H–A, score probability heatmap (top 5 scorelines)
- Value bet badge: if model edge > threshold, show "VALUE" tag with edge %
- Configurable edge threshold slider (default 5%)
- Toggle: show raw model probabilities vs. ensemble only

### Page 2 — Performance Tracker
- Line chart: Brier score, log-loss by week/month (rolling)
- Bar chart: simulated ROI by season and by edge threshold bucket (3%, 5%, 7%, 10%+)
- Table: model performance segmented by team (where is the model systematic?)
- Filters: season picker, home/away toggle, model picker (compare ensemble vs. components)

### Page 3 — Calibration
- Reliability diagram: predicted probability bins vs. actual outcome frequency
- Sharpness histogram: distribution of predicted probabilities
- Per-class calibration (home win / draw / away win separately)
- Brier score decomposition: reliability + resolution + uncertainty components

### Page 4 — News & Overrides
- Feed of Claude-processed news items (newest first)
- Each item: headline, source, Claude summary, estimated impact sliders (pre-populated)
- "Apply to Match" button → writes override to DB
- Applied overrides section: list of active adjustments with ability to remove
- Manual override form: pick match, enter custom strength adjustment manually

### Page 5 — Betting Tracker
- Simulated bet log table (match, market, model edge, odds, result, P&L)
- Cumulative P&L chart for 25% Kelly and 50% Kelly
- Total ROI, win rate, avg CLV, max drawdown stats
- Edge threshold filter slider (show bets above X%)
- Season filter

---

## Phase 7: Infrastructure (original deployment — SUPERSEDED 2026-06-11 by webapp-only; see top of file + legacy/)

### Folder Layout (original deployment)
```
/path/to/mls/          ← cloned repo
/path/to/mls/data/mls.duckdb   ← DuckDB file
/path/to/mls/.env      ← API keys (CLAUDE_API_KEY, ODDS_API_KEY)
/path/to/mls/venv/     ← Python virtualenv
```

### Cron Job (crontab -e)
```
0 6 * * * /path/to/mls/scripts/daily_update.sh >> /path/to/mls/logs/daily.log 2>&1
0 */6 * * * /path/to/mls/scripts/news_poll.sh >> /path/to/mls/logs/news.log 2>&1
```

### daily_update.py Orchestration Order
1. `schedule_client.py` — fetch yesterday's results + update match table
2. `asa_client.py` — pull latest xG data
3. `injury_scraper.py` — refresh injury/suspension flags
4. `elo_ratings.py` — recalculate ELO after new results
5. `feature_builder.py` — rebuild feature snapshots for upcoming matches
6. `dixon_coles.py` — refit model, generate predictions
7. `gradient_boost.py` — refit model, generate predictions
8. `run_bayes.py` — call R/brms model, generate predictions
9. `stacking_ensemble.py` — refit meta-learner, generate ensemble predictions
10. `odds_client.py` — fetch latest Pinnacle odds for upcoming matches
11. `clv_tracker.py` — compute edges and update simulated bets with results
12. Write all predictions + odds to DuckDB

### Cloudflare Tunnel
- Install `cloudflared` on the host
- Create free Cloudflare Tunnel: `cloudflared tunnel create mls-dashboard`
- Configure to route `https://mls-dashboard.yourdomain.com` → `localhost:8501`
- Run as systemd service for persistence after reboot

---

## Key Python Packages (requirements.txt)

```
itscalledsoccer         # ASA MLS stats API
rpy2                    # Call R from Python
duckdb                  # Embedded analytical DB
xgboost
lightgbm
scikit-learn
optuna                  # Hyperparameter tuning
shap                    # SHAP interpretability
scipy
numpy
pandas
streamlit
plotly
anthropic               # Claude API for news impact
feedparser              # RSS feed parsing
requests
beautifulsoup4
haversine               # Great-circle distance
pyyaml                  # Config loading
python-dotenv           # .env loading
APScheduler             # In-process scheduling fallback
```

## Key R Packages (r_requirements.R)

```r
install.packages(c("brms", "worldfootballR", "tidyverse", "jsonlite", "posterior"))
```

---

## Critical Files to Create (in order)

1. `config/settings.yaml` — parameters first, everything else reads from here
2. `data_pipeline/db_utils.py` — schema creation + helpers
3. `data_pipeline/asa_client.py` — primary historical data source
4. `data_pipeline/schedule_client.py` — fixture feeds
5. `data_pipeline/odds_client.py` — market data
6. `data_pipeline/injury_scraper.py`
7. `data_pipeline/news_monitor.py` — RSS + Claude API
8. `features/elo_ratings.py`
9. `features/xg_features.py`
10. `features/travel_features.py`
11. `features/referee_features.py`
12. `features/feature_builder.py`
13. `models/dixon_coles.py`
14. `models/gradient_boost.py`
15. `models/r_bridge/bayesian_elo.R`
16. `models/r_bridge/run_bayes.py`
17. `models/stacking_ensemble.py`
18. `market/kelly.py`
19. `market/clv_tracker.py`
20. `scripts/backfill_history.py`
21. `scripts/daily_update.py`
22. `scripts/daily_update.sh`
23. `dashboard/app.py`
24. `dashboard/pages/1_Predictions.py`
25. `dashboard/pages/2_Performance.py`
26. `dashboard/pages/3_Calibration.py`
27. `dashboard/pages/4_News_Overrides.py`
28. `dashboard/pages/5_Betting_Tracker.py`
29. `requirements.txt`
30. `r_requirements.R`
31. Host setup instructions in README.md (Cloudflare Tunnel, crontab, systemd)

---

## Verification (Phase 1)

1. **Backfill**: Run `backfill_history.py` — DB contains all matches, ELO history, xG features
2. **Model fit**: Run `daily_update.py` — all 3 sub-models + ensemble generate probabilities for upcoming matches
3. **Calibration check**: Brier score on held-out 2023 season should be < 0.23 (vs naive baseline ~0.25)
4. **Dashboard**: `streamlit run dashboard/app.py` — all 5 pages load
5. **News pipeline**: Trigger `news_monitor.py` — Claude API returns impact scores
6. **Market comparison**: After a match, `clv_tracker.py` records CLV and updates bet P&L
7. **Cloudflare**: Dashboard accessible at tunnel URL externally
8. **Cron**: `daily_update.sh` runs cleanly at 6 AM

---

# PHASE 2 — MODEL REFINEMENTS

## Context

The Phase 1 system is built and pushed (37 files, 5,561 lines). Phase 2 adds 28 user-approved refinements organized into six work-streams: new features, MLS-specific competitions, news pipeline expansion, validation rigor, risk management, and operational polish. These refinements turn the baseline ensemble into a higher-performing, more robust production system.

## R1 — New Match Features

**File targets:** new modules in `features/`, additions to `feature_builder.py`, new columns in `team_features` table (or sibling tables).

| Feature | Source | Implementation |
|---------|--------|----------------|
| Weather (temp, wind, precip, humidity) | Open-Meteo API (free, no key) | New `features/weather_features.py`. Lookup by stadium lat/lon at kickoff timestamp. Cache by (stadium, date) to avoid refetch. |
| Pitch surface (turf/grass) | Static map per stadium | Add to `_STADIUMS` dict in `travel_features.py`. **A/B-test before keeping**: train ensemble with and without this feature; only retain if Brier-score delta on held-out fold is > 0.001. |
| High-altitude flag | Static (Colorado, RSL only) | Binary feature in `feature_builder.py`. |
| Rivalry / high-importance flag | Hardcoded list of MLS rivalries (Cascadia, Hudson River, El Tráfico, ATL-ORL, Texas Derby, Heritage Cup) + binary "high-importance match" (CCC knockouts, playoff spots) | New util `features/match_context.py`. |
| Kickoff hour + day-of-week | `matches.kickoff_time` (need to start storing this) | Cyclic encoding (sin/cos) for hour; one-hot for day-of-week. |
| Set-piece xG / open-play xG split | ASA `get_team_xgoals` already returns these | Add columns to `team_features`: `xg_setpiece_rolling_10`, `xg_openplay_rolling_10`, same for xGA. |
| PPDA + possession + field tilt | ASA `get_team_xpass` / xgoals | New `features/style_features.py`. **Train ensemble with/without; keep only if Brier improves**. |
| Manager change flag + tenure | Manual table seeded from FBref via worldfootballR | New `manager_history` table. Feature: `days_under_current_manager`, `is_first_5_under_new_mgr`. |
| Dynamic playoff implication score | Computed live from current standings | New `features/match_importance.py` — for each upcoming match, simulate remaining season 1k times and compute Δ playoff probability if team wins vs loses. Score = abs(win_pct - loss_pct). |
| Goalkeeper availability | ESPN injury report (extend existing scraper) | New columns: `home_starting_gk_available`, `away_starting_gk_available`. Map known starters per team. |
| Card accumulation tracking | New `card_log` table populated from FBref via worldfootballR | New `features/suspensions.py`. Yellow ≥5 in season → suspended next match. Surface to feature builder as `home_key_player_suspended`. |
| News sentiment | Claude API on team-specific news in past 7 days | New columns: `home_news_sentiment_7d`, `away_news_sentiment_7d` (continuous -1 to +1). Computed in news pipeline. |

## R2 — MLS-Specific Competitions

**File targets:** `data_pipeline/asa_client.py`, `scripts/backfill_history.py`, `features/feature_builder.py`.

- **Concacaf Champions Cup**: scrape match results from FBref/CCC site; add to `matches` table with `competition='ccc'`. Use for fatigue features (`games_in_14d`, `days_rest`) but exclude from MLS-only ensemble training set.
- **Leagues Cup**: include all matches in training data with new `is_non_mls_opponent` flag.
- **US Open Cup**: include in training with `is_usoc` flag.
- **FIFA International Breaks**: hardcoded calendar of FIFA windows; new feature `is_post_fifa_break` and `n_internationals_unavailable` (count from injury/news pipeline).

Required schema changes:
- `matches.competition` VARCHAR (mls / ccc / leagues_cup / usoc) — default 'mls'
- `matches.kickoff_time` TIMESTAMP

## R3 — Lineup & News Pipeline Expansion

**File targets:** new `data_pipeline/lineup_scraper.py`, expanded `data_pipeline/news_monitor.py`, new `scripts/pre_match_update.py`.

- **Predicted lineups**: scrape MLSSoccer.com match preview pages; parse predicted XI per team. Store in new `predicted_lineups` table.
- **Pre-match high-frequency check**: new cron `*/5 7-23 * * *` runs `pre_match_update.py`. Logic: for any match within 90 minutes of kickoff with no recent prediction refresh, re-pull lineups + injury news, regenerate prediction. Logs lineup-induced probability changes.
- **Claude match preview synthesis**: extend `news_monitor.py` with `synthesize_preview()` function. For each upcoming match within 24h, ask Claude to read all flagged articles + recent results and produce a 1-paragraph rationale. Store on `predictions` table.
- **Twitter/X**: deferred — add later if news pipeline gaps appear.

## R4 — Validation & Model Architecture Upgrades

**File targets:** new `models/backtest.py`, new `models/season_simulator.py`, new dashboard page `6_Backtest.py`.

- **Walk-forward backtest module**: parameterized framework that walks weekly through history, refits models on data up to week N, predicts week N+1, settles bets, advances. Outputs full ROI/CLV/Brier curves stored in new `backtest_results` table. Dashboard exposes parameter sliders (edge threshold, half-life, Kelly fraction, model subset) and re-runs on demand.
- **Monte Carlo season simulation**: 10k sims of remaining season using current model probabilities; output playoff probability + Supporters Shield odds + projected points table per team. New dashboard page `7_Season_Forecast.py`.
- **Profit-aware loss function**: implement custom objective `betting_logloss` that weights misclassifications by (1/decimal_odds) — penalizes being wrong on long shots more than favorites. Compare to standard log-loss in backtest; use whichever produces higher CLV.
- **Drift detection + alerts**: new `scripts/check_drift.py` runs nightly. If 4-week rolling Brier degrades by >5% vs prior 12-week baseline, send ntfy.sh alert.
- **Model versioning**: add `model_version` column to `predictions` table. Snapshot pickled models to `data/model_versions/<YYYYMMDD>/`. New dashboard view to compare versions side-by-side over time.

## R5 — Risk Management

**File targets:** `market/kelly.py`, `market/clv_tracker.py`, new `market/risk_rules.py`.

- **Drawdown stop-loss**: in `market/risk_rules.py`, if 30-day rolling drawdown exceeds 15% of starting bankroll, set a `betting_paused` flag in DB. Daily update checks flag and emits no new bets while active. Dashboard shows banner. User can manually clear via dashboard.
- **Hard bet cap**: in `kelly.py`, cap any single Kelly stake at 10% of current simulated bankroll regardless of edge.
- **Bet correlation**: skip per user input — treat games independent.
- **Real-bet tracker**: new `real_bets` table parallel to `simulated_bets`. Dashboard adds form to log actual placed bets (book, odds, stake, result). Performance page shows simulated vs real side-by-side.

## R6 — Operations & Dashboard Polish

**File targets:** new `scripts/notify.py`, additions to all dashboard pages, new `scripts/backup_db.sh`.

- **ntfy.sh push notifications**: free service, no signup. New `scripts/notify.py` POSTs to `https://ntfy.sh/<unique-topic>`. Triggers: value bet detected (edge > threshold), drift alert, daily update failure. User subscribes to topic on iOS/Android ntfy app.
- **Mobile-optimized layout**: refactor `dashboard/app.py` CSS with media queries; use Streamlit columns adaptively. Test on iPhone Safari.
- **CSV export buttons**: add `st.download_button` to every page exposing the rendered DataFrame.
- **Daily DB backups**: new `scripts/backup_db.sh` runs `pg_dump mls > /home/ryang/mls/backups/mls_YYYYMMDD.sql.gz` daily at 5 AM. Retains 30 days, deletes older.
- **Weekly hyperparameter tuning**: split `daily_update.py` cron into daily (refit with cached params) and Sunday-only (full Optuna run, cache new params). Saves ~5 min/day during the week.
- **Auth**: skip — Cloudflare Tunnel obscurity sufficient per user choice.

## New Files (Phase 2)

```
features/
├── weather_features.py
├── style_features.py            # PPDA, possession, field tilt
├── match_context.py             # rivalries, importance flags
├── match_importance.py          # dynamic playoff implication scoring
└── suspensions.py               # card accumulation tracker

data_pipeline/
├── lineup_scraper.py            # MLSSoccer.com predicted XIs
└── (news_monitor.py expanded with synthesize_preview + sentiment)

models/
├── backtest.py                  # walk-forward backtest framework
├── season_simulator.py          # Monte Carlo season sim
└── (gradient_boost.py + dixon_coles.py extended for profit-aware loss)

market/
└── risk_rules.py                # drawdown stop-loss, hard cap, real-bet tracking

scripts/
├── pre_match_update.py          # high-frequency lineup-driven refresh
├── check_drift.py               # nightly drift detector
├── notify.py                    # ntfy.sh push wrapper
└── backup_db.sh                 # daily pg_dump

dashboard/pages/
├── 6_Backtest.py                # walk-forward backtest visualization
├── 7_Season_Forecast.py         # Monte Carlo standings projection
└── 8_Real_Bets.py               # actual wager tracking
```

## Schema Additions (Phase 2)

```sql
ALTER TABLE matches
  ADD COLUMN competition       VARCHAR(20) DEFAULT 'mls',
  ADD COLUMN kickoff_time      TIMESTAMP,
  ADD COLUMN weather_temp_c    DOUBLE PRECISION,
  ADD COLUMN weather_wind_kph  DOUBLE PRECISION,
  ADD COLUMN weather_precip_mm DOUBLE PRECISION,
  ADD COLUMN pitch_surface     VARCHAR(10);

ALTER TABLE team_features
  ADD COLUMN xg_setpiece_rolling_10  DOUBLE PRECISION,
  ADD COLUMN xg_openplay_rolling_10  DOUBLE PRECISION,
  ADD COLUMN xga_setpiece_rolling_10 DOUBLE PRECISION,
  ADD COLUMN ppda_rolling_10         DOUBLE PRECISION,
  ADD COLUMN possession_rolling_10   DOUBLE PRECISION,
  ADD COLUMN gk_starting_available   BOOLEAN,
  ADD COLUMN key_player_suspended    BOOLEAN,
  ADD COLUMN days_under_mgr          INTEGER,
  ADD COLUMN news_sentiment_7d       DOUBLE PRECISION,
  ADD COLUMN match_importance_score  DOUBLE PRECISION;

ALTER TABLE predictions
  ADD COLUMN model_version       VARCHAR(20),
  ADD COLUMN claude_rationale    TEXT;

CREATE TABLE manager_history (
  team_id    VARCHAR(10) NOT NULL,
  manager    VARCHAR(80) NOT NULL,
  start_date DATE NOT NULL,
  end_date   DATE,
  PRIMARY KEY (team_id, start_date)
);

CREATE TABLE card_log (
  match_id   VARCHAR(20) NOT NULL,
  player     VARCHAR(80) NOT NULL,
  team_id    VARCHAR(10),
  card_color VARCHAR(10) NOT NULL,
  PRIMARY KEY (match_id, player, card_color)
);

CREATE TABLE predicted_lineups (
  match_id     VARCHAR(20) NOT NULL,
  team_id      VARCHAR(10) NOT NULL,
  source       VARCHAR(30),
  scraped_at   TIMESTAMP DEFAULT NOW(),
  predicted_xi TEXT,    -- JSON array of player names
  PRIMARY KEY (match_id, team_id, source)
);

CREATE TABLE backtest_results (
  run_id          VARCHAR(20) PRIMARY KEY,
  parameters      TEXT,    -- JSON of tested params
  brier_mean      DOUBLE PRECISION,
  roi_kelly25     DOUBLE PRECISION,
  avg_clv         DOUBLE PRECISION,
  max_drawdown    DOUBLE PRECISION,
  generated_at    TIMESTAMP DEFAULT NOW()
);

CREATE TABLE real_bets (
  bet_id      VARCHAR(20) PRIMARY KEY,
  match_id    VARCHAR(20) NOT NULL,
  bookmaker   VARCHAR(30),
  market      VARCHAR(10),
  outcome     VARCHAR(10),
  stake       DOUBLE PRECISION,
  odds        DOUBLE PRECISION,
  result      VARCHAR(10),
  pnl         DOUBLE PRECISION,
  placed_at   TIMESTAMP DEFAULT NOW()
);
```

## Implementation Order (Phase 2)

Build in dependency order so each step works in isolation:

1. **Schema migrations** — apply all `ALTER TABLE` and `CREATE TABLE` statements first.
2. **Feature additions** (R1) — start with weather (lowest risk), then surface, altitude, rivalry, time-of-day. Then set-piece/open-play split (uses ASA data we already pull). Add style features last (test if predictive).
3. **MLS competitions** (R2) — extend ASA/FBref pulls; backfill historical CCC, Leagues Cup, USOC matches.
4. **Lineup + news expansion** (R3) — lineup scraper, then `pre_match_update.py` cron, then Claude preview synthesis, then sentiment.
5. **Validation modules** (R4) — backtest framework first, then season simulator, then drift detector, then versioning.
6. **Risk management** (R5) — drawdown rules, hard cap, real-bet tracker.
7. **Ops polish** (R6) — backups (Day 1 priority despite ordering), then notifications, mobile CSS, CSV exports, weekly tuning split.

## Verification (Phase 2)

1. **Schema**: All ALTER/CREATE statements run cleanly; tables visible in DBeaver.
2. **Weather**: For one upcoming match, fetch weather and confirm reasonable values (e.g., ATL summer = warm).
3. **Surface A/B test**: Run backtest with surface feature on/off; record Brier delta in `backtest_results`. Keep feature only if delta > 0.001.
4. **CCC fatigue**: For team with recent CCC match, confirm `games_in_14d` reflects it.
5. **Lineup scraper**: For the next match, verify a predicted XI is fetched and stored.
6. **Pre-match cron**: Trigger manually 90 min before a kickoff; confirm predictions refresh and lineup-driven probability change is logged.
7. **Walk-forward backtest**: Run a backtest over the last completed season; confirm Brier, ROI, CLV are produced and visible in dashboard.
8. **Monte Carlo sim**: Run for current season; confirm playoff probabilities sum sensibly (each conference's playoff slots ≈ count).
9. **Drift detector**: Manually corrupt last week's predictions, run detector, confirm ntfy alert fires.
10. **Stop-loss**: Set bankroll to a state with simulated 20% drawdown; confirm `betting_paused` flag set and no new bets created next run.
11. **Real-bet form**: Submit a test real bet via dashboard form; confirm it appears in `real_bets` and on the dashboard.
12. **Backup**: Confirm `backup_db.sh` produces a `.sql.gz` file; restore to a temp DB to validate integrity.
13. **Mobile layout**: Open dashboard URL on phone; confirm prediction cards and pages render readably.
14. **Notification end-to-end**: Trigger a value bet manually; confirm push arrives on phone via ntfy app.

---

# PHASE 5 — MODEL IMPROVEMENTS (POST-EVAL)

## Context

Evaluation results (2022–2024 walk-forward, 3-way split with isotonic calibration):

| Model | Brier | vs Naive |
|---|---|---|
| Naive baseline | 0.6392 | — |
| DC calibrated | 0.6482 | -1.4% |
| XGB calibrated | 0.6447 | -0.9% |
| Ensemble avg | 0.6400 | -0.1% |
| Ensemble stacked | 0.6407 | -0.2% |
| O/U stacked | 0.2429 | +0.2% |

Critical issues identified:
1. **Calibration error severe**: max decile error 0.17 (target <0.05) — probabilities unfit for Kelly sizing
2. **O/U XGBoost worse than naive** even after calibration — DC's λ+μ goal rates are better signal
3. **Feature importances uniform** (~9% each of 11 features) — no dominant feature; signals too diffuse
4. **Isotonic calibration hurts log-loss** on small cal sets (~472 matches) — Platt scaling fits better
5. **Stacking meta-learner adds no value** over simple average at this signal level
6. **Draw class hardest** (Brier 0.197) — teams that draw structurally tend to draw; rolling draw rate needed

## User Goals

- **Primary target**: Brier score (probability accuracy)
- **Production threshold**: 8–12% Brier improvement over naive before real betting
- **Market focus**: 1X2 result only; edge threshold raised to 8%
- **Approach**: Improve eval_baseline.py first, port to production after confirmation

## All Changes to `scripts/eval_baseline.py`

### 1. Data Filtering (lines 70–76)

```python
_COVID_SEASONS = {2020, 2021}  # bubble season + partial-fan anomaly
df = df[(df["season"] >= 2017) & (~df["season"].isin(_COVID_SEASONS))]
# 2025 in-progress data included for training; eval stays on 2022–2024
```

Rationale: pre-2017 MLS is a different tactical era; 2020 bubble removes home advantage entirely; 2021 was irregular. Excludes ~700 anomalous rows.

### 2. ELO Grid Search (new section before walk-forward)

```python
ELO_GRID = itertools.product([20, 25, 30], [80, 100, 120])  # K × HOME_ADV
# Validate on 2019–2021 (pre-test window); pick combination with lowest avg Brier
# Season regression: 0.30 → 0.40 (user-specified; MLS parity increasing)
REGRESS = 0.40
```

Best (K, HOME_ADV) is selected before the main 2022–2024 walk-forward begins.

### 3. Rolling Features Overhaul

New features added to `add_rolling_features()`:
- `home_draw_rate_10`, `away_draw_rate_10` — rolling draw frequency (last 10 matches); addresses Draw Brier 0.197
- `home_xg_roll_5`, `home_xga_roll_5`, `away_xg_roll_5`, `away_xga_roll_5` — two windows (5 and 15) instead of one
- `home_xg_roll_15`, `home_xga_roll_15`, `away_xg_roll_15`, `away_xga_roll_15`
- `home_xg_sum` = `home_xg_roll_5 + away_xg_roll_5` — direct O/U signal
- `is_playoff` — binary flag (from ASA game data; column `stage_name` or equivalent)

Window of 20 removed (too collinear with 15; user approved simplification to [5, 15]).

Updated `FEAT_COLS`:
```python
FEAT_COLS = [
    "elo_diff", "home_elo", "away_elo",
    "home_xg_roll_5",  "home_xga_roll_5",  "away_xg_roll_5",  "away_xga_roll_5",
    "home_xg_roll_15", "home_xga_roll_15", "away_xg_roll_15", "away_xga_roll_15",
    "xg_diff", "form_diff", "home_form", "away_form",
    "home_draw_rate_10", "away_draw_rate_10",
    "home_xg_sum",
    "is_playoff",
    "dc_lam", "dc_mu",   # added after DC fit (see §4)
]
```

### 4. Dixon-Coles: Shorter Decay + Export λ/μ as Features

```python
# Change decay_hl: 180 → 120 days
atk, dfd, ha, rho = fit_dc(train, decay_hl=120)

# New helper to extract goal-rate parameters per match:
def dc_lam_mu_batch(split_df, atk, dfd, ha):
    lams, mus = [], []
    for _, r in split_df.iterrows():
        lam = math.exp(atk.get(r.home_team, 0) + dfd.get(r.away_team, 0) + ha)
        mu  = math.exp(atk.get(r.away_team, 0) + dfd.get(r.home_team, 0))
        lams.append(lam); mus.append(mu)
    return np.array(lams), np.array(mus)

# After DC fit, add to cal and test DataFrames before XGBoost training:
cal["dc_lam"],  cal["dc_mu"]  = dc_lam_mu_batch(cal,  atk, dfd, ha)
test["dc_lam"], test["dc_mu"] = dc_lam_mu_batch(test, atk, dfd, ha)
```

`dc_lam` and `dc_mu` give XGBoost DC's structured Poisson estimate of each team's current strength.

### 5. Calibration: Isotonic → Platt Scaling

```python
# Replace IsotonicRegression with LogisticRegression (1-D Platt scaling)
from sklearn.linear_model import LogisticRegression as PlattLR

def calibrate_multiclass(raw_cal, y_cal, raw_test):
    cal_out = np.zeros_like(raw_test)
    for c in range(3):
        platt = PlattLR(max_iter=300, C=1.0)
        platt.fit(raw_cal[:, c].reshape(-1, 1), (y_cal == c).astype(int))
        cal_out[:, c] = platt.predict_proba(raw_test[:, c].reshape(-1, 1))[:, 1]
    row_sums = cal_out.sum(axis=1, keepdims=True).clip(1e-9, None)
    return cal_out / row_sums

def calibrate_binary(raw_cal, y_cal, raw_test):
    platt = PlattLR(max_iter=300, C=1.0)
    platt.fit(raw_cal.reshape(-1, 1), y_cal.astype(int))
    return platt.predict_proba(raw_test.reshape(-1, 1))[:, 1]
```

Platt scaling is well-calibrated on ~500 samples. Isotonic needed 1,000+ per class.

### 6. XGBoost: Grid Search + Exponential Sample Weights

```python
# Small hyperparameter grid (inner CV on training fold):
from sklearn.model_selection import ParameterGrid
XGB_GRID = list(ParameterGrid({
    "max_depth": [3, 4, 5],
    "n_estimators": [200, 300, 500],
    "learning_rate": [0.03, 0.05, 0.10],
}))
# Pick params with lowest 3-fold CV Brier on training fold

# Exponential season weighting:
def season_weight(s, ref):
    return math.exp(-math.log(2) / 4 * (ref - s))  # half-life = 4 seasons
sample_weight = train["season"].map(lambda s: season_weight(s, train["season"].max())).values
clf.fit(X_tr, y_tr_r, sample_weight=sample_weight)
```

### 7. A/B Feature Testing (new output section)

Report Brier delta per new feature group by running eval in 4 modes:

| Run | Features | Purpose |
|-----|----------|---------|
| Base | ELO + xG[5,15] + form | Reference |
| +DrawRate | Base + draw_rate | Test draw signal |
| +DCParams | Base + dc_lam + dc_mu | Test DC param signal |
| +All | All features | Final result |

Keep a feature only if it improves avg Brier by >0.001 across 3 test seasons.

### 8. Updated Reporting

Add to output:
- ELO grid search winner and Brier vs default
- A/B Brier delta table for each new feature
- Calibration error comparison: Platt vs isotonic
- Per-class improvement (home/draw/away) from new features

---

## Critical Files to Reference (read-only)

- `scripts/eval_baseline.py` — the file being rewritten
- `features/xg_features.py` — EWM decay pattern to follow for draw_rate
- `config/settings.yaml` — post-eval, update `xg_windows: [5, 15]`, `time_decay_half_life_days: 120`, `edge_threshold: 8.0`

## Verification

1. **COVID exclusion confirmed** — print statement shows 2020/2021 row count = 0
2. **ELO grid** — winning (K, HOME_ADV) printed before walk-forward
3. **A/B table** — per-feature Brier delta shows draw_rate and DC params individually
4. **Platt calibration** — max decile error drops below 0.10 (vs isotonic 0.17)
5. **O/U** — LightGBM with xG_sum beats naive; DC O/U also reported for comparison
6. **Overall Brier** — best model improves vs naive by >3% (vs current ~0.1%)

---

# PHASE 3 — SIMPLIFICATION

## Context

User's guiding principle: "the model should be maximally predictive but otherwise as simple as possible." Until empirical model testing begins, the right feature set is unknown. Phase 3 applies three targeted simplifications without removing any code: (1) disable the Bayesian R/brms model until the Python baseline is validated, (2) gate Pages 6–8 (Backtest, Season Forecast, Real Bets) behind a settings flag since they're not essential on day 1, (3) update the stacking ensemble to handle the 2-model case (DC + GB only) without Bayesian inputs. All Phase 2 features remain enabled by default. Cloudflare Tunnel already handles phone/iMac dashboard access — no changes needed there.

## Changes

### 1. `config/settings.yaml`

Add two flags under existing sections:

```yaml
bayesian:
  enabled: false   # ← ADD THIS. Set true when R/Stan is installed and Python baseline is validated.
  chains: 4
  ...

dashboard:
  beta_pages_enabled: false   # ← ADD THIS. Set true to enable pages 6/7/8 (Backtest, Season Forecast, Real Bets).
  prediction_horizon_days: 14
  ...
```

### 2. `scripts/daily_update.py`

Wrap all Bayesian steps (R bridge) in a feature flag check. In `main()`:

```python
bayesian_enabled = SETTINGS.get("bayesian", {}).get("enabled", False)

# Step 8 — only runs if bayesian.enabled: true
if bayesian_enabled:
    if train_df is not None:
        run_step("Prepare Bayesian input data", prepare_train_data, train_df)
    if upcoming_df is not None and not upcoming_df.empty:
        run_step("Prepare Bayesian predict data", prepare_predict_data, upcoming_df)
    bayes_success = run_step("Run R Bayesian model", run_r_model)
    bayes_preds = run_step("Read Bayesian predictions", read_predictions) if bayes_success else None
else:
    logger.info("Bayesian model disabled (bayesian.enabled=false). Skipping R bridge.")
    bayes_preds = None
```

Move the `from models.r_bridge.run_bayes import ...` import inside the `if bayesian_enabled:` block so missing R/rpy2 doesn't break startup.

Also skip `snapshot_model_version` Bayesian argument when disabled — already graceful since `bayes_preds=None` is the fallback path.

**Critical file:** `scripts/daily_update.py` lines 120–125 (Bayesian block)

### 3. `models/stacking_ensemble.py`

The ensemble's `predict()` method currently receives `dc_probs, gb_probs, bayes_probs` and uses `bayes_probs or dc_probs` as fallback. This means when `bayes_probs=None`, it duplicates DC probs into the Bayes slot — the meta-learner still sees 9 features but 3 of them are identical to DC features. This works but wastes capacity and may over-weight DC.

**Better approach when Bayesian is disabled:** Use only 6 features (DC 3 + GB 3) and train the meta-learner on those. Add a `n_models` parameter or detect based on whether bayes columns are present in training data.

Concretely:
- `oof_predictions()` in `GradientBoostModels` produces: `gb_prob_home`, `gb_prob_draw`, `gb_prob_away`, `gb_prob_over` 
- The ensemble `fit()` currently expects DC OOF columns added manually with placeholder values (0.45/0.25/0.30/0.50) — those need to remain for the meta-learner shape
- When Bayesian is absent, don't add `dc_prob_*` placeholder Bayesian columns; the meta-learner trains on 8 features instead of 12 (4 DC + 4 GB + 4 Bayes → 4 DC + 4 GB)
- Add a `_with_bayesian: bool` attribute saved with the model pickle so `predict()` knows whether to expect 8 or 12 features

**Change in `_generate_and_store_predictions`** (`daily_update.py`): When `bayes_preds=None` and building the OOF fallback ensemble, don't add Bayesian placeholder columns; signal to `StackingEnsemble` that it's a 2-model fit.

**Critical file:** `models/stacking_ensemble.py` — `fit()`, `predict()`, `store_predictions()`

### 4. Dashboard Pages 6, 7, 8

Each of `dashboard/pages/6_Backtest.py`, `7_Season_Forecast.py`, `8_Real_Bets.py` should add at the top (after imports, before any data loading):

```python
from config import SETTINGS
if not SETTINGS.get("dashboard", {}).get("beta_pages_enabled", False):
    st.set_page_config(page_title="Coming Soon — MLS Dashboard")
    st.title("🚧 Coming Soon")
    st.info("This page is not yet enabled. Set `dashboard.beta_pages_enabled: true` in settings.yaml to activate.")
    st.stop()
```

This keeps the files in place, keeps the sidebar links visible, but prevents data loading errors until the user is ready to activate them.

**Critical files:** `dashboard/pages/6_Backtest.py`, `7_Season_Forecast.py`, `8_Real_Bets.py`

### 5. `requirements.txt`

Mark `rpy2` as optional with a comment so it doesn't block pip install when R is absent:

```
# R integration (optional — only needed when bayesian.enabled: true in settings.yaml)
# rpy2>=3.5.0
```

Comment it out. Users who want Bayesian can uncomment it after installing R + Stan.

**Critical file:** `requirements.txt`

## Implementation Order (Phase 3)

1. `config/settings.yaml` — add two flags first (everything else reads from here)
2. `requirements.txt` — comment out rpy2
3. `scripts/daily_update.py` — wrap Bayesian steps in feature flag
4. `models/stacking_ensemble.py` — handle 2-model case cleanly
5. `dashboard/pages/6_Backtest.py`, `7_Season_Forecast.py`, `8_Real_Bets.py` — add beta gate

## Verification (Phase 3)

1. **Bayesian flag**: Set `bayesian.enabled: false`, run `daily_update.py --dry-run` (or just import it); confirm no R-related import errors, no R model steps logged.
2. **2-model ensemble**: Run `_generate_and_store_predictions` with `bayes_preds=None`; confirm ensemble fits and predicts without error.
3. **Beta pages**: Open pages 6, 7, 8 in browser; confirm "Coming Soon" message appears, no traceback.
4. **Requirements**: Fresh `pip install -r requirements.txt` in a clean venv; confirm no rpy2/R error.
5. **Enabled path**: Set `bayesian.enabled: true` (with R installed); confirm full pipeline runs as before — Phase 3 must not break the future Bayesian upgrade path.

---

# PHASE 4 — MLS DOMAIN CORRECTIONS

## Context

Six questions surfaced three concrete model corrections and three confirmations of existing behavior:

**Confirmations (no code changes):**
- **Turf**: Effect is real but modest — keep the feature, let backtest calibrate weight.
- **Altitude**: Binary flag for both Colorado + RSL is correct as-is.
- **Late-season rotation**: Too inconsistent to model — no seeding-locked feature needed.

**Corrections (require code changes):**
1. **Dome stadiums** — Atlanta (Mercedes-Benz) and Vancouver (BC Place) have retractable roofs and are effectively climate-controlled. The weather pipeline currently fetches outdoor Open-Meteo data for these venues, which is meaningless and could create a spurious signal (e.g., "Atlanta matches have low precip" not because of anything meaningful but because the roof is closed). Fix: add a `_DOME_STADIUMS` set and skip weather fetching for those teams.
2. **Leagues Cup form** — Top clubs compete, smaller clubs rotate. Leagues Cup matches should always count toward fatigue (`games_in_14d`, `days_rest`), but should **not** feed the form rolling average (W/D/L points) or xG rolling averages, since intent varies by team. Simpler and more defensible than trying to detect per-team seriousness.
3. **Referee nulls for unassigned matches** — When no referee has been assigned to an upcoming match (typically 3+ days out), use `NULL` rather than the league-average fallback. XGBoost handles nulls natively. Applying league averages implies a known-average official, which is a false signal.

## Changes

### 1. `features/travel_features.py` and `features/weather_features.py`

Add `_DOME_STADIUMS` to `travel_features.py` (alongside `_STADIUMS`):

```python
_DOME_STADIUMS = {"ATL", "VAN"}  # retractable roof — weather data irrelevant
```

Export `is_dome(team_id: str) -> bool` function from `travel_features.py`.

In `weather_features.py`, `fetch_weather()` should short-circuit for dome teams:

```python
from features.travel_features import is_dome

def fetch_weather(home_team, match_date, kickoff_hour_local=19):
    if is_dome(home_team):
        logger.debug("Skipping weather fetch for dome stadium: %s", home_team)
        return None  # columns remain NULL in DB
    ...
```

Add `is_dome` as a binary feature in `build_match_context()` in `match_context.py` so the model knows the weather nulls are structural (not missing data):

```python
"is_dome": int(is_dome(home_team)),
```

**Critical files:** `features/travel_features.py`, `features/weather_features.py`, `features/match_context.py`

### 2. `features/xg_features.py` and `features/feature_builder.py`

Currently, when building rolling xG and form features, all completed matches for a team are included regardless of competition. Leagues Cup matches should be excluded from the form and xG rolling windows (since intent varies), but kept in the fatigue window.

In `feature_builder.py`, when querying for a team's recent matches to compute rolling xG and form, add a filter:

```python
# Exclude Leagues Cup from form/xG rolling (competitive intent varies)
# But DO include in games_in_14d / days_rest (fatigue is real regardless of intent)
form_matches = recent_matches[recent_matches["competition"] != "leagues_cup"]
fatigue_matches = recent_matches  # all competitions
```

The `build_training_dataset()` function should also exclude Leagues Cup rows from the training set entirely (they don't represent normal MLS competitive behavior and would confuse the model).

**Critical files:** `features/feature_builder.py`, `features/xg_features.py`

### 3. `features/referee_features.py`

The current fallback when no referee is assigned returns league-average stats. Change this: when a match has no referee assignment (i.e., `referee_id` is NULL or empty in the matches table), return `None` for all referee columns rather than league averages.

```python
def get_referee_features(referee_id: str | None) -> dict:
    if not referee_id:
        return {k: None for k in _REFEREE_FEATURE_COLS}  # not yet assigned
    ...
    # existing lookup + league-average fallback for *unknown* referees stays
```

The distinction: `None` referee_id = not assigned yet → return nulls. Known referee_id not in our DB = genuinely unknown tendency → league average is reasonable.

**Critical file:** `features/referee_features.py`

## Implementation Order (Phase 4)

1. `features/travel_features.py` — add `_DOME_STADIUMS` and `is_dome()`
2. `features/weather_features.py` — short-circuit `fetch_weather()` for dome teams
3. `features/match_context.py` — add `is_dome` as a binary feature
4. `features/referee_features.py` — return nulls when referee not assigned
5. `features/feature_builder.py` — split form/xG window vs fatigue window; exclude Leagues Cup from training set

## Verification (Phase 4)

1. **Dome weather skip**: Build features for an ATL home match; confirm `weather_temp_c`, `weather_wind_kph`, `weather_precip_mm` are NULL; confirm `is_dome=1`.
2. **Dome feature present**: Confirm `is_dome` column appears in training dataset for ATL/VAN home matches.
3. **Leagues Cup exclusion**: After backfill, query `SELECT competition, COUNT(*) FROM matches GROUP BY competition`; confirm leagues_cup rows exist. Then confirm `build_training_dataset()` result contains no leagues_cup rows; confirm `games_in_14d` for a team with a recent LC match is higher than it would be without it.
4. **Referee null vs average**: For an upcoming match 5 days out with no referee assigned, confirm referee feature columns are NULL. For a match with a known referee assignment, confirm their specific stats populate.
5. **No regression**: Run `daily_update.py` with flag guards active; confirm no errors, predictions still generated for upcoming matches.
