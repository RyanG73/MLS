# MLS Prediction Dashboard — Implementation Plan

> **2026-07-06 — Preseason variance widening (A10b) ▶ KEEP uniform σ=60 (Europe), DROP γ gap-scaling**
> The season sim had NO strength uncertainty (fixed per-fixture DC probs). New
> `scripts/eval/sim_variance.py`: per-sim δ_t ~ N(0, σ) ELO-scale perturbations tilting fixture
> log-odds. Big-5 FD cohort replay (2018–2025, 40 league-seasons, production-mirrored preseason
> sims): uniform σ=60 (= observed seed→end ELO drift sd 62) improves relegation Brier 0.1263→0.1186
> and top-4 0.0920→0.0906 with title flat (+0.0003); confirmed at a second RNG stream. The
> hypothesized γ·|club_prior_gap| scaling is a null-to-negative on the very cohort it targets
> (σ90: 0.0498→0.0517 as γ 0→2) — symmetric variance can't fix the location error on fallen
> giants (that's the DC fit, A7 link 2). Wired into `build_league_data.py` preseason sims only;
> EPL rebuilt: Spurs releg 36.7→32.4% (42.0 pre-A8), Hull 89.7→78.0%, Arsenal title 51.1→45.2%.

> **2026-07-06 — Squad-value-informed ELO seed (A10a) ▶ DROP on MLS, Europe deferred**
> `--elo-value-beta` grid {0.25, 0.5, 0.75}, bag-5 seed 42, 4 folds: Δ −0.0011 / +0.0002 /
> −0.0006 vs champion 0.632977 — best point sub-noise, non-monotone (null effect); 2024 fold
> regresses at every β (A8-MLS fingerprint). Champion unchanged, flag opt-in. European test
> (the real target) deferred until A9 Phase 2 snapshots accrue leakage-clean value history.

> **2026-07-06 — FBref match xG for goals-only leagues (A12) ▶ BLOCKED at source**
> FBref has withdrawn public xG: schedule pages and team match logs carry zero xG cells in
> raw HTML for Championship/League One/Liga MX/Eredivisie AND an EPL control (the control
> proves source-side withdrawal, not a coverage gap). No adapter shipped; goals-proxy
> fallback stays; Understat unaffected. Probe record in `docs/feature-hunt-log.md`.

> **2026-07-06 — Squad-value rights conformance (user decision) ▶ MLS player table removed**
> `docs/data-sources.md` rules player-level TM values local-only; the MLS payload's public
> top-10 player table contradicted it. Code now conforms everywhere: team aggregates +
> positional split only, attribution per panel + footer. Bonus fix: MLS squad values no
> longer depend on the local-only raw CSV, so CI rebuilds carry them correctly.

> **2026-07-06 — Transfermarkt squad values, all covered leagues (A9) ▶ SHIPPED**
> `import_transfermarkt.py` league-parameterized (`--league <TM_CODE>` / `--all-leagues`, 14
> leagues; CanPL code corrected KAN1→CDN1 — the spec's guess doesn't resolve on TM). Canonical
> name resolution: exact → explicit alias table → FD_ESPN → `norm()` → unique token-subset
> (ambiguous hits refuse to guess); canonical list reads the payload's **standings** roster
> (team_inputs misses promoted teams with zero played rows — the Coventry case). 2026-27
> preseason snapshots fetched (GB1 20/20 teams, 99% valued); `build_league_data.py` now emits
> `squad_value` (team-level aggregates only — player values local-only per
> `docs/data-sources.md`; attribution footer added). Weekly snapshot cron
> (`refresh-transfermarkt.yml`, Mondays 02:00 UTC) accrues dated snapshots into
> `data/transfermarkt_snapshots/` for future roster-timing experiments. Coverage test:
> every current EPL payload team resolves to a TM row (green). Unblocks A10 (value-informed
> prior) and B9's European squad-value panels (EPL + League Two rebuilt; rest pick it up on
> the weekly refresh).

> **2026-07-05 — `pythag_luck` re-judge (A6) ▶ marginal (correction 2026-07-05)**
> Re-ran `--ab-only "+PythagLuck"` (previously dropped at Δ+0.0008 on 3 folds) now that A1's
> conditional slices exist, 4-fold walk-forward bag-5 seed 42. Mean ensemble Brier 0.6327 vs
> champion 0.6330 (**−0.0003**), selected as BestAB in all 4 folds. **Corrected verdict**: a
> same-day pass had marked this KEEP and logged "promoted to production feature set" — false;
> no code changed in that commit, `experiments/champion.json` is untouched, and Δ=0.0003 is
> below both the screening KEEP bar (>0.001, `docs/experiment-protocol.md` §4) and the
> promotion-gate core_metric bar (≥0.0005, §10). Per the protocol table this is **marginal**
> (0 < Δ ≤ 0.001): code stays available as the existing opt-in `+PythagLuck` AB set, not
> promoted, champion unchanged. The task's own per-team Brier spread check (0.52–0.70 range)
> was never actually run — only the aggregate number was reported. Full numbers in
> `docs/feature-hunt-log.md`.

> **2026-07-05 — xG-blended ELO update (A5) ▶ DROP**
> Effective ELO update score blended toward the xG-implied result (`--elo-xg-blend 0.3`,
> `s_eff = (1-λ)·s_result + λ·s_xg`) vs champion, 4-fold walk-forward bag-5 seed 42. Mean
> `ens_stacked_brier` 0.6346 vs champion 0.6330 (**+0.0016**), a consistent regression across all
> four folds (~8× the noise floor) despite `elo_diff` remaining the top feature by gain. Kept as
> an opt-in flag; champion config unchanged. Full numbers in `docs/feature-hunt-log.md`.

> **2026-07-05 — Draw-aware structure (A11) ▶ DROP (both candidates)**
> Two-stage draw hurdle (`--draw-two-stage`) and per-season DC rho re-fit (`--dc-rho-per-season`)
> both underperform champion on the standard aggregate gate — `ens_stacked` avg 0.6347 (hurdle)
> and 0.6352 (rho) vs champion 0.632977 (Δ −0.0017 / −0.0022), both past the ±0.001 noise floor.
> Clean double-failure on the primary aggregate criterion; the A1 draw-reliability slice and
> draw-bet ROI checks were skipped (can't rescue a regression this far past noise). B5/B12
> continue to suppress draw-side Kelly sizing. Full numbers in `docs/feature-hunt-log.md`.

> **2026-07-04 — Time-varying home-field advantage (A4) ▶ DROP**
> Season-level DC home-advantage shrunk toward the pooled estimate (`--hfa-dynamic`,
> `fit_dc_dynamic_ha`) tested against the champion on both the standard aggregate gate and the
> 2024 fold specifically (the regime-shift fold this lever targets). Both move the wrong way,
> past noise: aggregate Δ −0.0021, 2024-fold Δ −0.0048. Champion config unchanged; full numbers
> in `docs/feature-hunt-log.md`.

> **2026-07-03 — "Why this pick" attribution (B3) ▶ DONE**
> Match rows expand (click) to a 4-row delta strip (ELO/xG form/GK z/availability, home minus
> away, color-coded by sign), pure render over the already-shipped `D.team_inputs` — no model
> math. Rows hide (not zero/undefined) when a league lacks that input, verified on MLS (full)
> vs Championship (ELO + xG form only).

> **2026-07-03 — Uncertainty cues on odds (B2) ▶ PARTIAL — standings tooltip shipped, match-card
> chip blocked on A2**
> Standings odds cells get a p10–p90 projected-finish tooltip, reusing the existing
> `finishVals`/`ensureFinish()` base sim (already backs the "Projected finish" panel) rather than
> adding a duplicate. The match-card bag-spread chip could not ship: it needs 5-seed disagreement
> on upcoming matches, but A2 confirmed the production forward path is DC-only for unplayed
> fixtures — there is no bagged prediction to source a spread from. Declined to fabricate one.

> **2026-07-03 — Promoted-team Brier advisory gate (A3) ▶ DONE**
> `scripts/eval/promoted_team_brier.py` gains `pooled_summary()` (match-weighted Brier across
> all 5 European tier2→tier1 pairs vs naive 2/3); wired into `model_report.py` (best-effort,
> attached to every report — MLS has no promotion, so this is an independent diagnostic like
> `source_health`) and `promotion_gate.py` as a non-blocking advisory. Current real value: pooled
> 0.6304 vs naive 0.6667 — clear, doesn't fire today. 6 new tests, suite green.

> **2026-07-03 — Sidebar country/region groups + favorites (B13) ▶ DONE**
> League registry gains a `group` field (Americas/England/Spain/Italy/Germany/France/Cups);
> sidebar now groups by country instead of confederation, collapsible per group, plus a
> star-to-pin Favorites section — both `localStorage`-persisted, mobile drawer included for
> free. Found `ligue-2`/`segunda` had drifted out of the Python `REGISTRY` while staying in the
> committed `webapp/leagues.js` — regenerating would have silently dropped two live leagues from
> the sidebar. Fixed + added a regression test (`tests/test_fetch_league_teams.py`) so a future
> registry regen can't silently drop a league again.

> **2026-07-03 — "Today's Edge" cross-league board (B12) ▶ DONE**
> New `scripts/build_edge_board.py` aggregates every upcoming match (next 48h) across all live,
> non-knockout league payloads into `webapp/data/edge-board.js`, ranked by model edge over the
> market; no-`?league=` is now the site's landing route (deep links unchanged). Currently
> edge-empty everywhere (no payload carries forward market odds yet — same root cause B10
> already flagged), so the empty-state / next-kickoffs fallback is what actually ships live.
> Along the way, fixed a real scoping bug: `ledgerStripHTML`/`BET_DISCLAIMER` were trapped
> inside the per-league render branch (Annex B block-scoped `function` hoisting only assigns on
> block execution) so the edge board's separate script tag couldn't see them — moved both to
> shared scope. 7 new tests; suite green.

> **2026-07-03 — Variable ELO season regression, club-prior target (A8) ▶ PARTIAL KEEP — Europe only**
> `compute_elo` gains `club_prior_beta` (regress toward `(1-β)·1500 + β·mean(prior ≤3-season
> end-of-season ELO)` instead of flat 1500). MLS harness A/B: β=0.75 clears the gate at seed 42
> (Δ+0.0014) but not seed 7 (Δ+0.0005) — **MLS DROP**, champion untouched. European proxy
> walk-forward: monotone in β, −0.023 on A7's high-gap slice (0.213→0.194, n=646), ~10× the MLS
> gate size — **KEEP for production seeding**. Ported to `build_league_data.py`'s two
> `compute_elo` sites; 10 European payloads rebuilt. Spurs preseason relegation 42.0% → 37.9%.
> `regress_gap_k` (per-team rate modulation) tested and dropped — no gain over β alone. Full
> detail in `docs/superpowers/plans/2026-07-02-model-and-ui-improvements.md` and
> `docs/feature-hunt-log.md`.

> **2026-07-03 — Full-ensemble forward path (A2) ▶ DONE — GATE FAILED, DC forward retained**
> The 2026-06-29 deep-dive headline item closes with a validated negative. Built the carry-forward feature builder (`scripts/eval/upcoming_features.py`: latest side-prefixed values per team re-stamped onto unplayed fixtures, derived diff columns recomputed; 4 tests) and backtested `predict_upcoming` vs the production temperature-scaled DC forward path on the 2025 fold at 3 checkpoints (next-30-days matches, n=208 pooled): ensemble **0.6439** vs DC **0.6383** (Δ −0.0056, paired-bootstrap CI [−0.0216, +0.0103]). The ensemble wins at +60d then loses from mid-season — `predict_upcoming` fits train<cal<current so current-season rows are invisible to it, while production DC re-fits on all played matches. Production forward numbers stay DC+temperature; the module ships anyway (B9 consumes `latest_team_features`). Full table in `docs/feature-hunt-log.md`. Same session: A1 conditional reliability slices + A7 club-prior-gap slice/cohort study (Spurs 42% relegation = miscalibration; high-gap bottom-half cohort base rate ≈11%), B1 status-required payloads, B10 odds-history archiver accruing from 2026-07-03.

> **2026-06-29 — Second-tier leagues + bidirectional cross-tier bridge ▶ DONE**
> Added Spanish **Segunda** (SP2, 22 teams) and French **Ligue 2** (F2, 18 teams) as full second-tier dashboard leagues (football-data goals-only source, OUTLOOK buckets, sidebar, FD→ESPN name maps, logos via esp.2/fra.2) — completing second-tier coverage for all big-5. Wired the **forward** tier-2→tier-1 bridge for Spain/France (`_TIER2_PAIRS`, `_TIER2_FOR`, priors), so all big-5 top flights now seed promoted teams from real second-tier ELO instead of the flat prior — fixing Ligue 1's Le Mans/Troyes (relegation 97.8% → 38.6%/45.5%). Made the bridge **bidirectional**: new `_identify_relegations` + `_collect_relegated_matches` mirror the promotion machinery; `fit_all` now fits and LOSO-validates both directions per pair (10 offsets in `tier2_offsets.json`, forward negative / reverse positive, all beating naive); `coefficients.tier1_offset` reads the reverse key; `build_league_data` gains a reverse seeding path (`_TIER1_FOR_BUILD`, generalised `_get_tier_elo_map`) so a team relegated into a second tier seeds from its top-flight ELO as a promotion favourite (validated offline: Leeds 61% / Leicester 46% / Ipswich 45% Championship strength vs field median 40). Also landed the earlier **promoted-team seeding cliff fix** (smooth ELO→DC regression + 25th-pct soft floor in `_elo_to_dc_params`; Hull 99.9%→84%, Coventry mid-table→lower-mid) and excluded `logos.js` from the league-payload contract test. New build step: `python3 -m scripts.eval.tier_bridge` (fits both directions). Branch `feat/second-tier-bidirectional-bridge`; 423 tests pass (the 2 mobile-overflow browser-smoke pins are a pre-existing documented known issue, not from this work).

> **2026-06-28 — Webapp UI redesign (quant-terminal) ▶ DONE**
> Full presentation-layer redesign of `webapp/index.html` onto a distinctive "quant-terminal" system (near-black ink, mono numerics via Spline Sans Mono, flat panels, one-accent-per-role palette — killing the generic dark-dashboard look). Eight user-flagged issues addressed: (1) new design system across every view; (2) relegation is now its own labeled heat column; (3) **race strip** top boxes — one card per race from `outlook.cards`, leader + 2 contenders, auto-fit ≤2 rows, scales to any league; (4) single-table leagues drop the 770px empty club column → dense half-width table + **projected-finish range plot** (538-style P10–median–P90, fed by a finishing-position histogram added to the existing `runSimTable` loop); (5) global logo fallback — new `scripts/build_logo_map.py` → `webapp/data/logos.js`, harvest + diacritic/club-token fuzzy match + alias, consumed by `crest()` (fixes UCL/Leagues Cup/Concacaf + promoted-team gaps; sourceless foreign clubs keep monograms); (6) league-aware trophy legend (no more US Open Cup in Europe) + fixed the `0.4ern Conference` bug (table leagues reuse `conf` for a Conference-League %, now show overall rank); (7) knockout/group/round-reach tables move from bare `<table>`s to panels + heat cells + crests, round-odds becomes a heat matrix, bracket restyled; (8) chrome/matches/power/health restyled. **Simulation math and the JS↔Python porting contract unchanged** — only three accumulator lines added to `runSimTable`. New build step: `python3 scripts/build_logo_map.py`. Verified across mls/epl/serie-a/liga-mx/championship/ucl/europa/leagues-cup/concacaf-champions/power/canadian-pl + 375px mobile, zero console errors.

> **2026-06-28 — Calibration method sweep ▶ DONE — NOT KEPT (temperature confirmed)**
> Swept all 6 harness calibration methods (`--calibration`) on the single bagged run (`--xgb-bag 5 --seed 42`, 3-fold 2022–24). Ensemble-stacked Brier / home-win max-decile cal-err vs champion temperature (0.6343 / 0.1659): platt 0.6370/0.1285 (+0.0027 Brier, −0.0374 cal); isotonic 0.6406/0.1621 (+0.0063, overfits ~500-row cal fold); beta 0.6370/0.1285 (identical to platt — `betacal` not installed, falls back to Platt); temp_then_isotonic 0.6393/0.1358 (+0.0050); temp_then_platt 0.6369/0.1656 (+0.0026, no cal gain). **Verdict: NO method beats temperature** — every alternative regresses Brier by +0.0026 to +0.0063, all ≥13× the σ≈0.0002 noise floor. Platt/beta buy real calibration (−0.037) but at a Brier cost; no free lunch. Champion temperature calibration confirmed by evidence. No code change.

> **2026-06-28 — Mobile what-if mode (Section 3 UI) ▶ DONE**
> Brought the signature next-5 what-if interaction to mobile (was desktop-only — the `.wgroup` column was `display:none` at ≤760px / ≤620px because the narrow 13px-square column couldn't fit inline). Presentation-only change: on mobile the `.wgroup` reflows to a full-width tappable sub-row under each team (`grid-column:1/-1`) with 36px touch targets, a "Next 5 — tap to force W / D / L" label, and per-box opponent labels (`v`/`@` + monogram, via new `.wb-l` span hidden on desktop). Reuses the existing `forced` map, `scheduleSim()`, and `#ladders` click delegation — zero simulation-logic change. Verified at 375px: 30 sub-rows render, taps cycle W/D/L and trigger the 10k-run resim + banner, no console errors, no horizontal overflow; desktop unregressed (13px squares, labels hidden, inline column). Covers both MLS conference ladders and European table ladders.

> **2026-06-27 — Section 11 Documentation & Product State ▶ DONE**
> Made route/product state an explicit data contract. Every payload now carries a top-level `status` field (`live` / `preseason` / `completed` / `knockout_live` / `placeholder`): `build_dashboard_data.py` (MLS=`live`), `build_league_data.py` (derived from `season_state`: PRESEASON→`preseason`, IN_PROGRESS→`live`, CONCLUDED→`completed`), `build_continental_data.py` (`completed`/`knockout_live`), `fetch_league_teams.py` (`placeholder` + a human-readable `reason` string). Webapp "coming soon" view now renders the payload's `reason` instead of hardcoded copy; `canadian-pl.js` patched in place. Docs: `CURRENT_STATE.md` gains **Route State Taxonomy** + **Model Card Fields** reference sections and a corrected multi-script Production Path table; `README.md` fixed to reflect `webapp/data/*.js` (was stale singular `data.js`), links `docs/data-sources.md`. No model behavior changed; payloads validate clean.

> **2026-06-27 — Section 9 Market Evaluation & CLV ▶ DONE**
> Added DB-free market evaluation pipeline. `data_pipeline/market.py` is now the canonical vig/CLV math module (`devig`, `edge_pct`, `clv_pp`). `odds_log.py` gained `log_closers()` for near-kickoff closing-line capture. New `scripts/market_eval.py` generates `experiments/market_eval.json` with per-season model vs market Brier (European Big-5 reads from existing webapp payloads; MLS reads from `odds_log.parquet`, reports `no_odds_data` until lines accumulate). `model_report.py` gains `--market-eval` flag to fill the previously-deferred `market_slices` field. Market odds remain strictly evaluation-only — never added to `parity_frame.parquet` or training features. 22 tests pass.

> **2026-06-27 — Section 5 Source Health & Model Governance ▶ DONE**
> Wired source health tracking across all three active adapters (ASA, ESPN/Liga MX, Understat). Fixed `coverage_gate_status()` to use per-source significant-endpoint filtering so auxiliary calls like `get_teams` can't mask missing match-data records. Added `understat` and `football_data` to coverage floors. Champion reports now include `feature_completeness` (per-season null rates for key features: GK, xG-OE, ELO, form, availability) and `asa_cache_freshness`. Promotion gate gains an advisory `feature_completeness` check (non-blocking, flags >20% null features). Gate self-test extended to 7 cases. 209 tests pass; no model behavior changed.

> **2026-06-26 — Section 4 DC Prior Injection ▶ DONE — NOT KEPT**
> Per-fold α*: 2022:0.02, 2023:0.12, 2024:0.02, 2025:0.08. 4-fold avg Brier: 0.6338 vs champion 0.6330 (Δ=+0.0008).
> Season-static TM data added only marginal DC correction; the tiny α* values confirm the cal-fold found almost no shrinkage signal, and the regression sits within seed noise (σ≈0.001) but is directionally unfavorable — NOT KEPT. Next: dated intra-season TM snapshots (Layer C weekly scrape + `observed_at`) for timing-aware roster injection.

> **Section 4 — Roster-Delta First Pass (2026-06-26) ▶ DONE — NOT KEPT**
> Added section 6c to `eval_baseline.py`: cross-season TM player comparison → 7 new feature families
> (new_player_value_z, departed_value_z, net_roster_delta_z, unseen_new_star_z, positional ATT/DEF/GK).
> AB result: all regress Brier (−0.0027 to −0.0052). Root cause: season-static TM data can't capture
> mid-season signing timing that the feature is designed for. Slice evaluation framework established
> (early_season, roster_change, unseen_star, departure slices print after per-season Brier table).
> Positive finding: Base model already beats naive by −0.0250 on high-disruption matches.
> Next lever: true dated TM snapshots (weekly scrape + `observed_at`) + DC rate injection (third pass).

> **Section 2 — Data Acquisition & Source Ingestion (2026-06-21) ▶ DONE** — Created `docs/data-sources.md` register (all active + proposed sources, payload matrix, commit rules). Rewrote `data_pipeline/source_health.py` to be DB-free (parquet-backed; was dead code against Postgres). Added `observed_at` stamping + validation gates to `scripts/import_transfermarkt.py`. Created `data_pipeline/asa_cache.py` caching all ASA endpoints by mtime; wired into `build_dashboard_data.py`, `build_continental_data.py`, `eval/league_bridge.py`. 199/199 tests pass.

> **Season rollover + roadmap round 2 (2026-06-20) ▶ IN PROGRESS**
>
> Full detail: `docs/superpowers/plans/2026-06-20-season-rollover-roadmap.md`. Trigger: EPL's 2026-27
> schedule launched. **Key fact:** Understat has no 2026-27 data yet (publishes ~Aug); ESPN has the
> official schedule (20 teams incl. promoted Coventry City). So the flip = ESPN fixtures + carry-over
> ELO + promoted-team seeding + a pre-season projection mode. 10 steps:
> 1. ESPN European fixtures adapter (next-season schedule when Understat lacks it).
> 2. Carry-over ELO + promoted-team seeding (continuing teams regress; promoted seed at a baseline).
> 3. Pre-season projection mode (target latest season with ANY fixtures; 0-played → full-season DC sim).
> 4. **Flip EPL to 2026-27** + verify in-browser.
> 5. Generalize rollover to the other big-5 / 2nd tiers (auto-detect per league).
> 6. Pre-season UI treatment (banner, promoted/relegated badges, prior-season finish).
> 7. Historical-ELO-as-of-date for Approach C (the R2 deferred lever; validate-before-adopt).
> 8. Continental odds feed (Odds API) → value_bets (the R3/R5 blocker; build path, may be partial).
> 9. Model report-card view (summarize the games retrospective: hit rate / Brier-vs-naive / calibration).
> 10. Rollover test coverage (lock pre-season state + seeding + fixtures parsing).
> Verdicts appended per step.

> **Improvement roadmap — model / viz / performance / efficiency (2026-06-19) ✅ COMPLETE (8/8)**
>
> Full detail: `docs/superpowers/plans/2026-06-19-improvement-roadmap.md`. All 8 executed
> subagent-driven; MLS parity |Δ|=0.0000 throughout; 171 tests pass. **Verdicts:**
> 1. **Vectorize bracket_sim — DONE.** Batched the league/group Poisson draws → **8.5×** (UCL 20k sims
>    5.73s→0.67s); round-size invariants exact; champion odds within MC noise.
> 2. **Approach C — DONE, honest NULL.** Validate-before-adopt: fitted offsets barely move from the
>    coefficient prior (max 0.5 ELO UEFA, adopted at sub-noise gain; Concacaf rejected, 40% robustness).
>    UEFA 5-yr coefficient priors vindicated; framework + harness in place. Historical-ELO-as-of-date =
>    future lever. Continental odds effectively unchanged.
> 3. **ELO-wired validation — DONE.** Real strength, per-comp model-vs-naive: UCL BEATS (0.6032 vs
>    0.6217); Europa/Conference trail (low modeled coverage); Concacaf trails (see #4). No continental
>    market source (football-data domestic-only) → market track deferred (data-acquisition item).
> 4. **Calibration — DONE (partial).** Confederation-aware constants (UEFA unchanged); Concacaf deficit
>    cut (CC gap 0.038→0.007) but still TRAILS — STRUCTURAL small-sample limit (n=51, 58.8% home), no
>    sane constants beat it (T7 insane-constant rule held). Explicit UEFA knockout-playoff round added
>    (fixes ~1.5× R16 inflation; KOplayoff=16 invariant exact).
> 5. **Continental value layer — DONE (scoped).** `model−market` BLOCKED (no continental odds source).
>    Populated `games` (model probs + results) → Match Projections is now a model report card; value
>    scaffold + documented blocker.
> 6. **Bracket visualization — DONE.** Round-column knockout bracket (Playoff→Final) from games;
>    aggregate scores, winners bolded, champion 🏆 (incl. PK finals). Verified in-browser.
> 7. **Refresh pipeline — DONE.** build_all.sh covers all 17 surfaces + continental; cache merge-on-
>    refetch (history retained); Liga MX Apertura 2026 window; launchd plist template.
> 8. **Unified season_state — DONE.** Shared between/in_progress/concluded detector; both builds
>    refactored behavior-preserving (concluded views + league tables byte-unchanged).
>
> **Net:** 8.5× faster sims; honest model findings (priors good, Concacaf small-sample-bound, no
> continental market data); a real bracket viz; ops pipeline ready for the July/Aug rollovers.

> **Approach C — Bridge-Regression Cross-League Offsets (2026-06-19) ✅**
>
> Implemented `scripts/eval/league_bridge.py` — `fit_offsets()` collects cross-modeled-league
> continental matches, fits per-league ELO offsets minimizing NLL + ridge penalty toward priors,
> validates with 70/30 train/test split + 10-seed robustness check, and writes
> `experiments/league_offsets.json` only if fitted offsets beat prior held-out Brier AND pass
> the robustness gate. `data_pipeline/coefficients.league_offset()` now lazy-reads the JSON
> (Approach C values when present; prior fallback otherwise). No import cycles; read-only wire-in.
>
> **Results (λ=0.0001, seed=42, 10 robustness seeds):**
>
> | League | Prior | Fitted | Δ |
> |--------|-------|--------|---|
> | EPL (anchor) | 0.0 | 0.0 | +0.0 |
> | La Liga | -45.0 | -45.0 | +0.0 |
> | Serie A | -54.0 | -54.4 | -0.4 |
> | Bundesliga | -60.0 | -60.5 | -0.5 |
> | Ligue-1 | -81.0 | -80.8 | +0.2 |
> | MLS (anchor) | 0.0 | 0.0 | +0.0 |
> | Liga MX | 30.0 | 30.0 (prior, rejected) | -0.8 (unstable) |
>
> UEFA: 263 matches, fitted ADOPTED (7/10 seeds, Brier Δ=-0.00004).
> Concacaf: 130 matches, fitted REJECTED (4/10 seeds < 70% threshold — signal too noisy).
> MLS parity |Δ|=0.0000; 147 tests pass (10 new in `tests/test_league_bridge.py`).
> Continental odds effectively unchanged: max fitted correction = 0.5 ELO (sub-noise).
> Future: historical ELO-as-of-match-date would sharpen the signal (noted in docstring).

> **Fix — Continental "concluded edition" handling (2026-06-17) ✅**
>
> Bug: the continental build always ran a fresh Monte-Carlo projection, so finished editions showed
> live-style champion odds (e.g. "Arsenal 7.6%") when the tournament was long over. Root causes:
> `continental_results` returned the whole cache (season-mix risk); the build hardcoded `--season 2024`;
> and there was no concluded detection. Fix (matches the European leagues' finished-season pattern):
> - `espn_continental`: `continental_results` now **filters to the requested season(s)** and `seasons`
>   defaults to None=all; added `latest_season()`; `_parse` now captures the ESPN `winner` flag so
>   **penalty-decided finals resolve** (UCL PSG, Concacaf CC Toluca). UCL cache refreshed to 2025-26.
> - `build_continental_data`: defaults to the **latest** cached edition; `_is_concluded` (final played +
>   no upcoming fixtures) → `_resolve_actual` emits the **real result** — champion + each team's actual
>   furthest round, and the actual final league/group table (real points) — instead of a projection.
> - `webapp`: a green "🏆 X won the YYYY-YY <comp> · final result, not a projection" banner +
>   "Completed · Champion" subtitle; the `~` coefficient marker is suppressed for finished editions.
> - Rebuilt all 5 live continental comps as concluded with verified champions: UCL 2025-26 **PSG**,
>   Europa 2025-26 **Aston Villa**, Conference 2025-26 **Crystal Palace**, Concacaf CC 2026 **Toluca**,
>   Leagues Cup 2025 **Seattle Sounders**. Projections resume automatically when the next edition is drawn
>   (build flips back to the Monte-Carlo path once fixtures appear). 137 tests pass; parity |Δ|=0.0000.

> **Phase 7 — Continental expansion: Europa / Conference / Concacaf CC / Leagues Cup (2026-06-17) ✅ COMPLETE**
>
> Generalized the UCL vertical slice to the four remaining active continental comps, each with a
> genuinely different current format (researched, not assumed). **17 leagues now live.** The defunct
> **Concacaf League** (last edition 2023, absorbed into the Champions Cup) was **removed** from the
> registry. MLS champion untouched (parity |Δ|=0.0000); 137 tests pass. Plan:
> `docs/superpowers/plans/2026-06-17-continental-expansion.md`. Built subagent-driven (8 tasks).
>
> **Formats + engine work:**
> - **Europa / Conference (UEFA):** config-only on the existing league-phase engine. Europa = UCL clone
>   (8 league games each); Conference = 6 games each. Same R16/QF/SF/Final knockout.
> - **Concacaf Champions Cup:** **new pure-knockout `bracket_sim` path** — 27 teams, top-5 by strength
>   bye to R16, the other 22 play Round One (two-leg), then R16/QF/SF two-leg + single-leg Final. No
>   league phase (`standings=[]`). Round-size invariant exact (RoundOne=22, R16=16, QF=8, SF=4, Final=2).
> - **Leagues Cup:** **new two-table group `bracket_sim` path** — 18 MLS + 18 Liga MX in two parallel
>   league tables, 3 cross-league games each, NO DRAWS (PK), top-4 per table → 8-team single-elim. The
>   shared `_run_ko` helper was generalized to single-leg multi-team rounds (backward-compatible).
>
> **Strength:** UEFA comps reuse the UEFA coefficient anchor. Concacaf comps use Concacaf-INTERNAL league
> offsets (MLS=0 ref, Liga MX +30) — relative-only (the two confederations never meet; match_lambdas uses
> differences). MLS ELO loads from `data/parity_frame.parquet` (ASA hashes remapped to names via
> `asa.get_teams`); Liga MX from `espn_soccer.liga_mx_frame()`. Concacaf fields auto-resolve modeled teams
> by membership in the MLS/Liga MX ELO dicts (+ a 4-entry MLS alias map); UEFA comps use the hand `_ESPN_TO_MODELED`.
>
> **Verified in-browser (all 4):** Leagues Cup shows two side-by-side MLS/Liga MX tables + knockout
> (favorites Cruz Azul/Inter Miami/LAFC); Concacaf CC a 27-team bracket leaderboard, no sub-tabs
> (Vancouver/Inter Miami/Pumas); Europa/Conference the League Phase + Knockout layout (Man Utd/Roma,
> Real Betis/Chelsea). Champion odds sum to 1.0; coefficient-only clubs marked `~`; MLS/UCL/table leagues
> regression-clean; no console errors.
>
> **Known v1 limitations carry over** (flat champion odds from Approach-A coarseness; playoff-skip
> inflating mid-table R16 on the UEFA comps; Europa/Conference modeled ratios are low — 28%/11% — because
> most entrants are non-big-5 leagues we don't model, so they lean on the coarser coefficient anchor).

> **Phase 6 — UEFA Champions League continental vertical slice (2026-06-17) ✅ COMPLETE (UCL live)**
>
> First cross-league knockout competition on the platform. Design spec:
> `docs/superpowers/specs/2026-06-16-continental-competitions-design.md`; implementation plan:
> `docs/superpowers/plans/2026-06-16-continental-ucl-vertical-slice.md`. Built subagent-driven
> (10 TDD tasks, two-stage review each). The MLS champion is UNTOUCHED (parity |Δ|=0.0000).
>
> **Approach (A — external-coefficient anchor, C-ready seam):** every team gets one cross-league
> strength on a common ELO-point scale. Modeled big-5 entrants = domestic ELO + per-league offset
> (`Δ_league = k·(UEFA_coeff − EPL_coeff)`); unmodeled entrants = UEFA club coefficient mapped to the
> same scale. `team_strength()` is the seam where a future bridge-regression (Approach C) swaps in.
>
> **New components (all new files except the webapp branch + registry flip):**
> - `data_pipeline/coefficients.py` — UEFA league/club anchor tables → ELO points.
> - `scripts/eval/cross_league.py` — `team_strength`, Poisson `match_lambdas`/`match_probs`,
>   `compute_league_elos`. Calibrated constants: BASE_GOALS=1.35, GOAL_SCALE=3000, HOME_ADV_ELO=80.
> - `scripts/eval/bracket_sim.py` — format-spec engine: balanced circulant league phase + two-leg KO
>   (away-goals/ET/pens) + neutral final → standings + advance/champion odds.
> - `data_pipeline/espn_continental.py` — ESPN results/fixtures adapter (slug `uefa.champions`).
> - `scripts/validate_continental.py` — walk-forward Brier vs naive (calibration harness).
> - `scripts/build_continental_data.py` — `--comp ucl` → `webapp/data/ucl.js` (modeled ELO + fallback).
> - `webapp/index.html` — `outlook.mode==='knockout'` → `renderKnockout()` two sub-tabs
>   (League Phase table + Knockout bracket/champion-odds), plus robustness guards so the minimal
>   knockout payload doesn't trip the MLS/table-assuming top-level script.
>
> **Validation:** coefficient-only walk-forward (UCL 2021–24, n=564): model **0.5998 vs naive 0.6217**
> (BEATS naive). 130 tests pass (10 new across coefficients/cross_league/bracket_sim). In-browser
> verified: UCL live in sidebar; both sub-tabs render (Bayern/Arsenal lead the league phase; Arsenal
> 7.6% / Bayern 7.6% / Barcelona 7.0% champion odds; ~ marks the 14 coefficient-only clubs); all 4
> tabs error-free; MLS + 12 leagues regression-clean.
>
> **Known v1 limitations (documented, deferred to follow-on):**
> - Champion odds are flat (favorite ~7.6%) — Approach-A coarseness + moderate strength spread; real
>   UCL favorites run ~15–20%. Honest under-confidence, not a bug.
> - The bracket skips the explicit knockout-playoff round (top-24 → top-16 directly), inflating
>   mid-table **R16** advance odds ~1.5×; champion odds are unaffected.
> - Validation is coefficient-only (~48% of matches are baseline-vs-baseline); a true edge demonstration
>   needs ELO-wired validation. The build itself DOES use real ELO for big-5 teams.
>
> **Next (separate plan):** generalize to Europa/Conference (same UEFA format + coefficients) and the
> Concacaf comps (Concacaf index; resolve the Leagues Cup ESPN slug); Approach C bridge regression;
> live `games` cards + edges from `continental_fixtures` once a draw exists; vectorize `bracket_sim`.

> **Phase 4 data rebuild + Dixon-Coles fit 24× speedup (2026-06-16) ✅ COMPLETE**
>
> Rebuilt the 8 remaining European leagues (serie-a, bundesliga, ligue-1, championship,
> league-one, league-two, bundesliga-2, serie-b) with the Phase 4 value/edge layer — all 9
> non-EPL European leagues now carry `value_layer.backtest`. EPL was already done.
>
> **Root-caused + fixed a severe perf cliff that made 24-team builds appear to hang.**
> `_dc_nll` (Dixon-Coles negative-log-likelihood) was a pure-Python per-match loop calling
> `scipy.stats.poisson.logpmf` twice per match per L-BFGS iteration — ~1.3M high-overhead
> scipy calls per fit on a 24-team league → **`fit_dc` took 215s**. Phase 4's backtest calls
> `fit_dc` once per fold × 7 folds, so each 24-team 2nd-tier league (Championship/League
> One/League Two) needed ~26 min for the backtest alone; the 18-team leagues squeaked by.
>
> **Fix:** vectorized the NLL with numpy using the closed form
> `poisson.logpmf(k,λ)=k·ln(λ)−λ−lgamma(k+1)` (`scipy.special.gammaln`) and boolean masks for
> the four Dixon-Coles τ cases. The slow loop existed in **two** copies — `models/research_model.py`
> `_dc_nll` (the build + parity path) AND `scripts/eval/dixon_coles.py` `dc_nll` (the harness
> path) — both fixed identically.
> - `fit_dc` (Championship, real data): **215s → 0.42s (482×)**
> - Full 7-fold backtest (build path): **1458s → 59.6s (24×)**
> - All 5 remaining 24/20/18-team builds: **5 min 36 s total** (was 80+ min, hanging)
> - **MLS champion parity PASS, |Δ|=0.0000** (0.6330 exact, per-season + w_xgb unchanged) —
>   numerically identical to ~1e-12; behavior-preserving. 109/109 tests pass; 13 DC unit tests pass.
> - Also bounded the football-data.co.uk fetch with `timeout=(10,30)` (connect, read) so a
>   stalled server fails fast and falls back to the raw-CSV disk cache.
>
> Edge backtests (fair odds, ≥8% model edge): Championship 1387 bets −7.7%, League One 1485
> −7.5%, League Two 1458 −2.5%, 2.Bundesliga 885 **+1.5%**, Serie B 916 −7.5%. Same honest
> read as EPL — Pinnacle's line is sharp; goals-only leagues only narrowly beat naive.

> **Phase 3A — 5 European 2nd-tier leagues (goals-only, 2026-06-14) ✅ COMPLETE**
>
> Added Championship, League One, League Two, 2.Bundesliga, Serie B as live leagues.
> All 5 use football-data.co.uk goals-only + market odds (same CSV), same pipeline as big-5.
>
> **Key changes:**
> - `data_pipeline/football_data.py`: `match_results()` adapter → canonical frame (xG=NaN, parquet-cached);
>   `DIV` extended with E1/E2/E3/D2/I2. `data/football_data/` added to `.gitignore`.
> - `scripts/build_league_data.py`: `OUTLOOK` dict with generic bucket system (`_TOP()` for top-flight,
>   `_PROMO()` for 2nd tiers); source-routing via `_load_frame()`; `FD_ESPN` name maps (football-data→ESPN);
>   Monte-Carlo generalized to arbitrary bucket keys; payload `outlook` block now dynamic (no hardcoded
>   `ucl_slots`/`releg_slots`); `has_xg` flag conditionalizes xGD display.
> - `webapp/index.html`: `tableLadder` renders columns from `ol.columns` (loop, not hardcoded Title/UCL/Releg);
>   `runSimTable` generalized to bucket range spec in `ol.columns`; `renderTableOutlook` laddernote dynamic;
>   xGD sub-line hidden when `ol.has_xg=false`; bucket colors extended for promo/playoff keys.
> - `scripts/fetch_league_teams.py`: 5 leagues flipped `soon→live`; `leagues.js` regenerated (11 live).
>
> **Goals-only sanity gate (walk-forward 2022–2025):**
> | League | Model | Naive | Market | Beat naive | Trail market |
> |---|---|---|---|---|---|
> | Championship | 0.647 | 0.652 | 0.630 | ✓ | as expected |
> | League One | 0.632 | 0.650 | 0.613 | ✓ | as expected |
> | League Two | 0.649 | 0.657 | 0.628 | ✓ | as expected |
> | 2.Bundesliga | 0.657 | 0.659 | 0.627 | ✓ | as expected |
> | Serie B | 0.658 | 0.662 | 0.634 | ✓ | as expected |
>
> Verified in-browser: PROMO/PLAYOFF/RELEG columns, top-6/bottom-3 cut-lines, no xGD on goals-only leagues,
> MLS + big-5 regression-clean. 109/109 tests green.
>
> **Next: Phase 4 betting/value layer (now unblocked — historical odds in all 10 European leagues).**

> **Phase 3B — Liga MX (ESPN goals-only, 2026-06-14) ✅ COMPLETE**
>
> FBref/soccerdata only covers the Big 5 + tournaments (Selenium + Chrome required; Liga MX not in
> available_leagues). Pivoted to ESPN free scoreboard API (mex.1) — same goals-only approach as
> European 2nd tiers, no model changes needed.
>
> **Key changes:**
> - `data_pipeline/espn_soccer.py` (new): ESPN goals-only adapter for Liga MX. Season encoding:
>   sequential integers (Clausura 2017=1, Apertura 2017=2, …, Clausura 2026=19) via
>   `(year-2017)*2 + (1 if clausura else 2)`. Parquet-cached. 2,767 matches across 18 torneos fetched.
>   Clausura 2020 excluded (COVID cancellation). `season_label(sid)` → "Cl.2026" / "Ap.2025".
> - `scripts/build_league_data.py`: added `_LIGUILLA()` bucket (top-8 of 18); `"liga-mx"` entry in
>   OUTLOOK (`source="espn"`, `confederation="Concacaf"`, `eval_seasons=None`); `_load_frame` handles
>   `source=="espn"`; `_pyears` is now dynamic for ESPN leagues (all torneos from index 2 onward);
>   `perf_by_year` records now carry a `label` field for human-readable accuracy card columns;
>   `confederation` and `data_source` pulled from `cfg` (not hardcoded "UEFA").
> - `webapp/index.html`: `BRGB` extended with `liguilla` (same gold as `promo`); accuracy card builds
>   `labelMap` from `p.label` and uses `seasonLbl=y=>labelMap[y]??...` — Liga MX shows "Ap.2022",
>   "Cl.2023", etc.; year filter generalized (`>=2022` for calendar leagues, last-8 for sequential-ID).
> - `scripts/fetch_league_teams.py`: `liga-mx` flipped `soon→live`; `leagues.js` regenerated (12 live).
> - `.gitignore`: `data/espn_soccer/` added.
>
> **Goals-only sanity gate (sequential walk-forward, all torneos):**
> | Torneo | Model | Naive | Beat naive |
> |---|---|---|---|
> | Current (Cl.2026) | 0.6161 | 0.6453 | ✓ (+4.5%) |
> | Range Ap.2018–Cl.2026 | 0.57–0.67 | 0.63–0.65 | ✓ mostly |
>
> Verified in-browser: "LIGUILLA" card in gold, accuracy card shows torneo labels, "18-team table ·
> top 8 qualify", cut-line between 8th and 9th, team logos loaded, no console errors.
> MLS + big-5 regression-clean. 109/109 tests green.

> **Phase 4 — Betting/value layer (2026-06-14) ✅ COMPLETE (code); data rebuild pending**
>
> Adds per-match edge display and a walk-forward edge backtest to all 10 European leagues (where
> historical betting market data exists via football-data.co.uk).
>
> **Key changes:**
> - `scripts/build_league_data.py`: imports `walk_forward_predictions` + `attach_market`; computes
>   `_game_mkt` lookup for the current season (per-match `mkt_home/draw/away`); adds edge fields
>   (`edge_home/draw/away`) to each game card entry; runs edge backtest (≥8% model edge, flat stake,
>   fair/de-vigged odds) over all walk-forward seasons; `value_layer.backtest` + `value_layer.value_bets`
>   added to payload.
> - `webapp/index.html`: `edgePick()` updated to accept both legacy `g.mkt=[h,d,a]` and new
>   `g.mkt_home/draw/away` separate fields; `renderHealth()` gains a "Value edge backtest" card showing
>   N bets / hit rate / flat ROI + per-season breakdown when `D.value_layer.backtest` is present.
>
> **Design decisions:**
> - Fair odds = `1/mkt_p` (de-vigged, ~3-5% more conservative than real Pinnacle decimal odds).
>   Actual ROI vs. Pinnacle would be slightly better.
> - Edge threshold: 8% (established project gate, same as live betting threshold).
> - `value_bets` field reserved for upcoming matches with live odds (empty until live odds pipeline added).
> - Backtest uses walk-forward held-out predictions — no look-ahead bias.
>
> **EPL verified (2026-06-15):** 1,085 backtest bets, win_rate=0.287, roi=−0.058 at fair odds.
> The model identifies apparent edges but they don't clear the bar vs. Pinnacle's sharp closing line —
> honest and expected for a market-blind model. Per-game `mkt_home/draw/away` and `edge_*` fields
> populate the match card "Pick" column with real edge percentages for EPL.
>
> **Pending data rebuild:** la-liga, serie-a, bundesliga, ligue-1, championship, league-one,
> league-two, bundesliga-2, serie-b need `build_league_data.py --sims 5000` run to pick up Phase 4
> fields. Command:
> ```bash
> for league in la-liga serie-a bundesliga ligue-1 championship league-one league-two bundesliga-2 serie-b; do
>   venv/bin/python scripts/build_league_data.py --league $league --sims 5000
> done
> ```
>
> **Next: Phase 5 — 2026-27 season rollover + live value_bets (see below)**

> **Phase 5 — Open roadmap (not yet started)**
>
> Three tracks in priority order:
>
> **Track A — Data rebuild (immediate):** Rebuild 9 European leagues with Phase 4 code (see command above).
> Once done, commit the 9 rebuilt `.js` files. ~3–4 hours sequential CPU.
>
> **Track B — 2026-27 season rollover (Aug 2026):** European leagues restart in August 2026. The
> Understat cache needs a fresh fetch (per-league `python -m data_pipeline.understat --league <id>`)
> once the 2026-27 season begins. `build_league_data.py` will auto-detect new fixtures vs. completed
> matches. Liga MX Apertura 2026 starts ~July 2026 and is already handled by the ESPN adapter
> (add Apertura 2026 torneo window to `_LIGA_MX_WINDOWS` in `data_pipeline/espn_soccer.py`).
>
> **Track C — Live value_bets:** Populate `value_layer.value_bets` for upcoming matches where model
> edge ≥ 8%. Requires a live odds source. football-data.co.uk publishes upcoming-season opening odds
> (downloadable CSV) — the same adapter already used for historical odds. The build script would
> fetch the current-season CSV, de-vig, and filter upcoming matches by edge threshold. This is the
> only remaining step to make Phase 4 actionable for real-time betting decisions.

> **Phase 2 — market comparison + operationalisation + league expansion (2026-06-14)**
> After Phase 1 put the big-5 European leagues live, this phase adds the betting-market benchmark the
> accuracy card was missing, operationalises the European builds for the 2026-27 season, and probes the
> next league tier. User directives: (1) the header accuracy grid was conflating two different "naive"
> baselines — make it **two rows: model-vs-naive and model-vs-market**, each consistent; (2) source the
> market row from **real betting markets**.
>
> - **P2-1 ✅ — Market comparison (`data_pipeline/football_data.py`).** Source = **football-data.co.uk**
>   (free historical 1X2 odds — Bet365 / **Pinnacle** / market-avg — for all big-5 back to ~2014; div
>   codes E0/SP1/I1/D1/F1). Adapter de-vigs Pinnacle (→ market-avg → B365 fallback) to implied [H,D,A],
>   merges to the canonical frame on **(season, home, away)** — unique in a double round-robin, so no
>   date/timezone matching (100% coverage after a ~31-name map). The build scores **model / naive /
>   market** Brier on the SAME matched matches per season (`perf_by_year[].edge_pct`, `market_brier`
>   block). The webapp accuracy card is now **two consistent tracks** (vs naive, vs market) + a headline
>   that reconciles with row 2 — the confusing champion-vs-uniform "+1.19% vs naive" is gone. Result:
>   market Brier **0.571–0.579** (sharper than our 0.586–0.604); the model trails Pinnacle by only
>   **~2–2.5%** — strong for a market-blind model. MLS keeps its forward-logging opening-odds path.
> - **P2-2 ✅ — Operationalise (`scripts/build_all.sh`).** Rebuilds all live leagues (MLS + big-5);
>   European season auto-detect picks up 2026-27 automatically (~Aug 2026). Until then: completed 2025-26
>   final tables.
> - **P2-3 ✅ — Table-league what-if simulator.** `runSimTable()` ports the MLS client sim to a single
>   table (force results → resimulate → Title/UCL/Relegation); what-if Next-5 cells render only when the
>   league has upcoming fixtures, so it is inert now and activates with 2026-27.
> - **P2-4 ✅ — `n_bags=5` confirmation.** EPL **0.5897** / La Liga **0.5861** at the champion bag size
>   (vs 0.5890 / 0.5863 at `n_bags=1`) — within seed noise; directional sweep confirmed. (Remaining 3
>   not run to completion — CPU; the two confirmations + sub-0.001 deltas suffice.)
> - **P2-5 ✅ — Phase 3 feasibility (FBref).** `soccerdata` FBref ships **only the big-5 + tournaments**
>   out of the box (same coverage as Understat, no gain). Next-tier leagues need custom league config AND
>   FBref's Opta xG, which is **absent for most 2nd divisions** (Championship, 2.Bundesliga, Serie B,
>   Ligue 2). Liga MX **is** covered with xG (viable Concacaf addition). Verdict: Phase 3 = Liga MX via
>   FBref + a **goals-only model variant** (no xG features) for xG-less divisions. Cups remain a separate
>   cross-league knockout effort.
>
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
