# MLS Prediction Dashboard — Project History

> Newcomer reference. Covers what this project is, how it evolved, and the key decisions that
> shaped it. For current model state and run commands, see `docs/CURRENT_STATE.md`. For what's
> in progress, see the active `docs/superpowers/plans/` file and the top of `docs/PLAN.md`.

---

## What this project is

A **market-blind probabilistic model** for soccer match outcomes (home win / draw / away win),
built to identify betting edges as the gap between model probability and market probability:

```
edge = model_prob − market_prob
```

The central constraint: **betting odds are never used as model features**. Using closing lines
in training would teach the model to replicate the market, collapsing `edge` to near-zero by
construction. Pinnacle lines are stored only for CLV (Closing Line Value) analysis after the
fact. The 8% threshold on edge is the live-betting gate.

The platform now covers **17 leagues + 5 continental competitions** — the multi-league
expansion happened between 2026-06-14 and 2026-06-17.

---

## Architecture evolution

### Original architecture (archived 2026-06-11)
- **Postgres DB** on a Mac → **Raspberry Pi 4** running scheduled ingest jobs → **Streamlit**
  multi-page dashboard (`legacy/dashboard/`)
- Model stack: `dixon_coles.py` + `gradient_boost.py` + `stacking_ensemble.py` (LR meta-learner)
- All archived to `legacy/` on 2026-06-11. `legacy/README.md` covers the full stack.

### Current architecture (webapp-only)
- A Mac runs `scripts/build_dashboard_data.py` → writes `webapp/data.js`
- `webapp/index.html` is served statically (no server, no DB)
- Research model: `models/research_model.py` (the sole active model)
- Research harness: `scripts/eval_baseline.py` + `scripts/eval/` modules
- Gate before production: `scripts/promotion_gate.py` (6 criteria)
- No Raspberry Pi, no Postgres, no Streamlit in the active path

---

## Model lineage

### Baseline (pre-2026-05-30)
Dixon-Coles + unconstrained LR stacking ensemble. avg Brier ≈ 0.6392. Cal error ≈ 0.146.

### Capped-DC convex blend (KEEP 2026-05-30)
Replaced the LR meta-learner with a scalar convex blend `w·XGB + (1-w)·DC`, w ∈ [0.7, 1.0],
fitted by Brier minimisation on the cal fold. Rationale: Dixon-Coles was catastrophically
bad in 2024 (Brier ~0.6523) because its static `home_adv` parameter overestimates home wins
after the 2024 HFA collapse. The 30% DC cap limits the damage while retaining DC's structural
Poisson priors for low-data teams. avg Brier 0.6392 → 0.6372.

### Weight_hl 4 → 6 (KEEP 2026-05-30, synergistic with capped blend)
XGB season-weight half-life increase was a DROP in isolation (earlier cycle) but a KEEP once
the DC cap was in place — the DC drag had been masking the gain. avg Brier 0.6372 → 0.6363.

### ELO REGRESS 0.50 → 0.40 (promoted 2026-06-07)
Swept WEIGHT_HL × REGRESS together (not independently — they interact). At whl=6, REGRESS=0.40
beats 0.50 by ~0.0010 avg Brier, sharpens calibration (0.0306→0.0195). At whl=4 the old
sweep, REGRESS=0.50 won — different operating point. K=25, HOME_ADV=80 were grid-locked first.

### Second-pass temperature scaling (fixes calibration bug)
The initial calibration applied temperature scaling to DC and XGB separately before blending.
The blended output was itself miscalibrated (cal_err 0.1326). Adding a second temperature pass
directly on the blend output brought cal_err down to 0.0306 (champion). Temperature won the
calibration sweep (vs Platt, isotonic, beta) because its single degree of freedom cannot
overfit the cal fold's class distribution — critical during 2024 regime shift.

### Seed bagging (KEEP 2026-06-09, verification protocol)
`--xgb-bag 5` averages 5 XGB seeds (42, 1042, 2042, 3042, 4042) pre-calibration. Collapses
run variance from σ≈0.001 to σ≈0.0002. Adopted as the standard verification protocol —
judgements near the 0.0005 gate bar require bagged runs. Wide-grid was gate-rejected on
calibration.

### Champion (promoted 2026-06-10 by user override)
- avg Brier **0.6330** (sum-form, 2022–2025 four-fold), cal_err **0.0182**
- Sub-noise gate shortfalls (6×10⁻⁶ core, ~0.0001 on 2024) while calibration halved
- `experiments/champion.json` → `experiments/challenger-bag5.report.json`
- Config baked into `models/research_model.py`: `DEFAULT_N_BAGS = 5`, narrow grid

---

## The 2024 regime shift

**Finding (diagnosed 2026-06-06 using `scripts/diagnose_2024.py`):** an outcome regime shift,
not a feature shift.

| Period | Home win rate |
|--------|--------------|
| 2017–2023 | ~0.51 |
| 2024 | 0.45 |
| 2025 | 0.443 (confirmed persistent) |

Feature distributions did NOT move (Jensen-Shannon divergence: train→2024 was *lower* than
train→2023). The model's inputs were on-distribution; the mapping from inputs to outcomes changed.

Dixon-Coles breaks because its `home_adv` is fit on 2017–2023 data (avg home rate ~0.51) and
cannot track a mid-stream collapse. XGB degrades far less because ELO and recent-form features
adapt within-season. The capped blend automatically down-weights DC to w_xgb=0.70 (maximum)
in 2024, and is the correct structural response — not a patch.

**What was tried and failed:**
- Per-class (vector) calibration: helps 2023 (+0.0045) but catastrophically regresses 2024
  (−0.0135). Extra calibration degrees of freedom overfit the 2023 cal-fold class priors and
  amplify the home→away shift when the regime flips. This hard trilemma applies to referee
  features too — the draw-rate gain is real but cannot be released while the regime shift persists.
- Shorter DC `recent_seasons` window (2/3/4/5): 2024 Brier identical to 4 decimals across all
  windows. The blend already floors DC at w_xgb=0.70 in 2024; DC's fit window has no leverage.
- ELO HOME_ADV re-sweep on 2024–2025 specifically: deferred (lower expected value).

---

## What has been tried and doesn't work

The following features were formally tested through the promotion gate and rejected:

| Feature/Approach | Key finding |
|-----------------|-------------|
| Referee draw rate (`ref_draw_rate`) | Real Brier gain (+0.0010) but FAILS calibration gate — hard trilemma proven across 14 calibration variants |
| Referee hw-rate only (`ref_hw_rate`) | The gain lives in `ref_draw_rate`, not `ref_hw_rate`; fails both core metric and 2024 robustness |
| Detrended referee (`ref_draw_rate_rel`) | Detrending removes the very component that carries the gain; edge and calibration fragility are the same signal |
| Per-class (vector) calibration | −0.0135 on 2024; root cause: 2024 regime shift (see above) |
| DC draw probability as XGB feature | Deterministic function of λ/μ, which are deterministic functions of rolling xG — no new signal |
| Standings features | Collinear with ELO; season points are a noisy proxy for what ELO already encodes |
| H2H draw rate | Too sparse — MLS teams typically meet 3–6 times; insufficient to estimate stable draw propensity |
| Manager tenure (`+Manager`) | Real but tiny (Δ=−0.00027); ELO + rolling form already encode the quality shifts a manager change drives |
| Neutral-site flag (`+HFA2`) | 2.8% is too sparse — XGB overfits it as noise |
| Weather (`+Weather`, 89% coverage) | Definitive DROP at near-full coverage: rolling xG/form already absorb conditions |
| Extended training history (2015/2013) | Older seasons fit the old 2022 fold at the cost of the current regime; 2017 cutoff is right |
| Season-decayed rolling features | Non-monotonic and sub-noise; cross-season carryover is benign (cf. 2021 retention) |
| Roster construction (2024+ only) | Data-limited single-split; model unreliable at 522-match training depth |
| Dynamic per-season model selection | Anti-predictive: cal-fold signal consistently picks the wrong model for the test season |
| LightGBM bag members | Untuned members dilute the bag (+0.0021 Brier) |
| Train-on-cal refit | Cal-season holdout is load-bearing, not waste |
| DC-through-cal | Same lesson as train-on-cal |
| In-season scalar recalibration | Scalar T cannot move class priors |
| Wide XGB grid | Brier win coupled to calibration regression — gate-rejected; same pattern as referee feature |

**Structural conclusion:** the model is at its pre-match-feature ceiling. ELO + rolling xG/form
already absorb team quality, home advantage, manager effects, conditions, and roster investment.
The frontier is the betting/CLV workstream (edge against the market).

---

## Multi-league and continental expansion

### League expansion (2026-06-14)
The MLS champion pipeline (ELO + DC + bagged XGB + capped-DC blend + temperature) transfers
to European football with zero model branching — validated on big-5 walk-forward 2022–2025:

| League | avg Brier | vs naive |
|--------|-----------|---------|
| La Liga | 0.5863 | +8.5% |
| EPL | 0.5890 | +8.8% |
| Bundesliga | 0.5934 | +8.7% |
| Serie A | 0.5946 | +9.7% |
| Ligue 1 | 0.6035 | +6.8% |
| *MLS (ref)* | *0.6330* | *+1.2%* |

European leagues carry far more capturable signal (lower parity). Data sources: Understat
(big-5 xG, 2014+), ESPN scoreboard (Liga MX), football-data.co.uk (European 2nd-tier
goals-only + market odds).

The model trails Pinnacle by ~2% Brier — strong for a market-blind model. The value/edge
backtest (8% threshold, fair de-vigged odds) shows apparent edges but they don't clear the bar
vs. Pinnacle's sharp line — honest and expected.

### Continental competitions (2026-06-17)
The cross-league strength problem: a UCL tie pits teams from different leagues whose domestic
ELOs are each anchored to 1500 independently and so aren't comparable.

**Solution (Approach A):** common ELO-point cross-league scale. Modeled big-5 teams = domestic
ELO + per-league UEFA-coefficient offset. Unmodeled entrants = UEFA club coefficient mapped to
the same scale. `scripts/eval/cross_league.team_strength()` is the seam where a future
bridge-regression (Approach C) drops in.

**Approach C (implemented 2026-06-19, honest null):** fitted per-league ELO offsets from
continental results via ridge regression toward coefficient priors. UEFA: offsets barely moved
from priors (max 0.5 ELO points), adopted. Concacaf: rejected (4/10 seeds, small-sample
constraint — n=51 CC matches is the binding limit). UEFA 5-yr coefficient priors are already
optimal; historical-ELO-as-of-date is the next potential lever.

**Five active comps:** UCL, Europa, Conference (UEFA), Concacaf Champions Cup (pure-knockout),
Leagues Cup (two-table group, no draws/PK). Each has a different `bracket_sim` path.

**Known limits:** Concacaf trails naive (structural small-sample bound); no continental odds
source (football-data.co.uk is domestic-only); Europa/Conference modeled coverage is low (~28%
and ~11%) because most entrants are non-big-5 leagues.

---

## Improvement campaign summary (2026-05-29 through 2026-06-10)

The multi-agent parallel improvement loop ran across ~15+ iterations across multiple cycles.
Key scoreboard:

| Cycle | Net change | Source |
|-------|-----------|--------|
| 2026-05-30 (parallel) | 0.6392 → 0.6363 | capped-DC blend + whl=6 |
| 2026-05-30 (overnight) | 0.6363 → 0.6375 | +MargCore (soft KEEP, 2023 only) |
| Phase 11 / 2026-05-31 | 0.6363 → 0.6344 | +Availability (ESPN roster g+ share) |
| 2026-06-07 (ELO grid) | → 0.6337 (3-fold) | REGRESS=0.40, second-pass cal fix |
| 2026-06-09 (13-iter) | bagging adopted | seed noise floor confirmed σ≈0.001 |
| 2026-06-10 (promotion) | 0.6330 (4-fold) | bag-only promoted by override |

Note: the Phase 11 Availability KEEP (+0.0011) used a preliminary harness state and the
2021-excluded config; after 2021 was re-validated and REGRESS moved to 0.40, the champion
was rebuilt on a clean 4-fold basis. The champion's 0.6330 is the authoritative number.

---

## Section 8 maintainability cleanup (2026-06-27)

Addressed the Codex Section 8 findings without touching the champion model. Three changes shipped: a shared `data_pipeline/http.py` (`espn_get()`) eliminated 5 independent copies of the ESPN HTTP boilerplate (`urllib3.disable_warnings()`, `_HDR`, `verify=False`); a minimal `pyproject.toml` + `pip install -e .` replaced 11 `sys.path.insert` workarounds across scripts; and two stale README references to deleted docs (`HANDOFF.md`, `CODE_WALKTHROUGH.md`) were corrected. Parity check held at Δ=0.0000 throughout. The payload writer (`write_js_payload`) and health-block builder (`health_feature_stats`) from `scripts/payload_utils.py` were already in place from prior work and not changed.

---

## Webapp UI redesign — quant-terminal (2026-06-28)

Redesigned the single-file dashboard (`webapp/index.html`) onto a distinctive "quant-terminal" design system (near-black ink, monospace numerics, flat panels, a disciplined one-accent-per-role palette) to shed the generic "AI dashboard" look, plus several correctness fixes. Highlights: a data-driven **race strip** that scales the top summary boxes to any league's `outlook.cards`; a half-width dense table + **projected-finish range plot** for single-table leagues (eliminating the 770px empty club column), fed by a finishing-position histogram added non-invasively to the existing `runSimTable` loop; a global logo fallback (`scripts/build_logo_map.py` → `webapp/data/logos.js`) that fuzzy-resolves cross-competition name mismatches so continental brackets and promoted teams render real crests; league-aware trophies (fixing the MLS-only "US Open Cup" legend leaking into Europe and the `0.4ern Conference` profile bug, which stemmed from European payloads reusing the `conf` key for a Conference-League probability); and all tournament tables restyled from bare `<table>`s into heat panels + a round-reach heat matrix. The simulation math and JS↔Python porting contract were left untouched. Done as a presentation-layer overhaul on branch `feat/webapp-ui-redesign`; verified across every league archetype + mobile with zero console errors.

---

## Second-tier leagues + bidirectional cross-tier bridge (2026-06-29)

Completed second-tier coverage for the big-5 by adding Spanish **Segunda** and French **Ligue 2** as full goals-only dashboard leagues, and made cross-tier promotion/relegation seeding bidirectional and per-league calibrated. The original `tier_bridge` only seeded *promoted* teams into the top flight (and only for England/Italy/Germany); now every big-5 top flight seeds promoted teams from its second tier (fixing Ligue 1's flat-prior cliff — Le Mans/Troyes 97.8% → ~40%), and the bridge runs in reverse too: a team relegated into a second tier seeds from its top-flight ELO as a promotion favourite (`_identify_relegations` + `_collect_relegated_matches` mirror the promotion machinery; `fit_all` fits/validates both directions; `coefficients.tier1_offset` + a reverse seeding path in `build_league_data` consume it). This also carried the promoted-team seeding **cliff fix** — `_elo_to_dc_params` swapped a discrete percentile clamp for a smooth ELO→DC regression with a 25th-pct soft floor (Hull 99.9%→84% relegation, Coventry mid-table→lower-mid). Reverse direction validated offline; no champion-model changes. Branch `feat/second-tier-bidirectional-bridge`.

---

## Season rollover + preseason projection mode (2026-06-20 → 2026-06-23)

Flipped the European leagues to 2026-27 before Understat published any data: a new ESPN fixtures
adapter (`data_pipeline/espn_fixtures.py`) supplies the official schedule, carry-over ELO with
season regression seeds continuing teams, and a new `preseason` season-state renders full-season
Monte-Carlo projections labeled as such. Promoted teams initially seeded at a flat baseline —
superseded within the week by the tier-bridge work below.

---

## Roadmap round + data contracts (2026-06-21)

A prioritized roadmap doc whose Section 1 (data contracts) shipped immediately:
`scripts/payload_utils.py` (`write_js_payload`, `health_feature_stats`), NaN-free preseason
health blocks, and `scripts/validate_payloads.py` wired into `build_all.sh` as a post-build
gate. The remaining roadmap items (preseason prior calibration, promoted-team strength,
market/CLV) were absorbed into the subsequent dedicated plans rather than executed from this doc.

---

## DC roster prior injection (2026-06-26) — NOT KEPT

Position-split roster-value z-scores injected as a post-fit adjustment to DC attack/defence
parameters (`--roster-dc-prior`, α grid-tuned per fold on the cal fold). Rejected by the gate:
season-static Transfermarkt values add nothing the 120-day time-decayed match history hasn't
already priced in (α* landed at 0.02–0.12, i.e. near-zero shrinkage). Full record in
`docs/feature-hunt-log.md`; the follow-up idea (dated intra-season TM snapshots) lives on in
the 2026-07-02 plan's A9 Phase 2.

---

## Market evaluation + CLV primitives (2026-06-27)

Built the betting-measurement layer: `data_pipeline/market.py` (`devig`, `edge_pct`, `clv_pp`),
`odds_log.log_closers()` writing `data/odds_closers.parquet`, and `scripts/market_eval.py`
(`brier_vs_market`, `roi_by_edge_bucket`) reading European closing odds from existing payloads.
Headline: the model trails Pinnacle by ~2% Brier (strong for a market-blind model); EPL backtest
ROI at the 8% edge threshold was −4.6%. `model_report.py` gained `--market-eval` slices.

---

## Promoted teams + cross-league strength (2026-06-27)

`scripts/eval/tier_bridge.py` fits ELO offsets from 8 seasons × 3 promotion pairs (912/578/912
first-season promoted-team matches); fitted offsets ≈ static priors (ridge active, priors
well-calibrated), LOSO Brier 0.628–0.631 vs naive 0.667. Promoted teams now seed from their
actual second-tier ELO via `tier2_offset` (e.g. Ipswich 1625 → 1505 adjusted) instead of a flat
weak prior; power rankings gained a "UEFA Tier 2" group. Extended 2026-06-29 to bidirectional
seeding (see entry above).

---

## Testing and verification harness (2026-06-27)

Four tasks shipped: the walk-forward COVID-constant fix; Playwright + pytest-rerunfailures in
`requirements-dev.txt`; payload-contract tests (`tests/test_payload_contract.py`) with
parse-level NaN guards over every `webapp/data/*.js`; and browser smoke tests
(`tests/test_browser_smoke.py`) covering five route families, console errors, rendered-NaN
checks, and 390px mobile overflow. These gates are what later plans' "suite green" verdicts
refer to.

---

## Public hosting on GitHub Pages (2026-06-30 → 2026-07-01)

The dashboard went public: `deploy.yml` publishes `webapp/` to GitHub Pages on every push to
main, `refresh-mls.yml` rebuilds MLS daily at 7 AM ET, and `refresh-leagues.yml` refreshes the
European leagues weekly on Mondays (30-min timeout, failed leagues surfaced as Actions warning
annotations). Live at `https://ryang73.github.io/MLS/`.

---

## The 2026-07-02 improvement campaign (2026-07-02 → 2026-07-06, plan completed and deleted)

A 25-task campaign spanning model diagnostics, the betting-edge product pivot, and league
expansion. Model side: conditional-reliability slices (A1) became the judging framework; the
"fallen giant" cluster (A7–A10) produced the club-prior ELO seeding for Europe (β=0.75, Spurs
relegation 42→37.9%) and preseason sim variance widening (uniform σ=60 ELO — the gap-scaled
variant was disproven on the cohort replay), while time-varying HFA (A4), xG-ELO (A5), draw
restructuring (A11), value-informed seeds on MLS (A10a), and FBref xG (A12, source withdrew
public xG) were all validated negatives. Product side: edge board landing page, quarter-Kelly
paper ledger, odds-history accrual, model-vs-market views, trust/health surfaces. Expansion
(C1/C2): six football-data leagues shipped with format-aware classification
(`season_format.py` — Belgian points-halving, Scottish split, Greek playoff pools inferred
from the post-phase pairing graph), and NWSL + USL Championship shipped LIVE mid-season via a
new ASA canonical-frame source (ASA played games + ESPN scheduled remainder). Champion
governance became per-league-family: five pointers (MLS 0.6330 · NWSL 0.6458 XGB-only, the DC
leg is a validated liability there · USL 0.6246 · eur-big5 0.5934 · eur-tiers 0.6152), each
with its own walk-forward baseline and promotion gate (`--champion-ptr`). Platform at
completion: 21 league builds + 5 continental competitions, 29 valid payloads.

---

## Outcome-driven improvements campaign (2026-07-07, plan completed and deleted)

The first campaign judged end-to-end on the season-outcome replay rather than match Brier.
Model: MLS sim gained the strength-uncertainty widening (preseason playoffs Brier −0.011);
the A10(a) squad-value prior finally landed as a bottom-half-targeted preseason tilt after a
Gate-0 probe proved Transfermarkt's historical season pages are era-clean (relegation Brier
−0.0055 with title flat; the untargeted variant dragged title odds toward the richest club
and was rejected) — Tottenham's preseason relegation odds closed the campaign at 16.5% from
the original 42%; USL playoff odds became conference-aware (MLS already was); the per-family
ELO regression-rate sweep was a validated null (0.40 stays — with club-prior seeding the rate
barely matters). UI: the Health tab shows outcome-skill by checkpoint ("when to trust the
odds"), the edge-board landing gained a model-odds movers strip (works without market data),
the two mobile overflows known since B1 were fixed (browser-smoke fully green for the first
time), and team profiles gained the "Is this team for real?" panel (club-prior gap ·
goals−xG · value rank vs table rank). Outright-market betting policy stands: no
relegation/promotion recommendations before 25% of a season.

---

## UI feedback round 2 (2026-07-09, plan completed and deleted)

A 7-task follow-up QA batch. The headline find: the "missing West Ham/Lincoln logos" report
was a pipeline bug, not a data gap — `build_logo_map.py` harvests inline logos from league
files, but clubs that change divisions between builds ship `logo:null`, so every regeneration
silently dropped ~35 previously-mapped clubs; `fetch_foreign_logos.py` now harvests the
modeled domestic leagues too (map: 799 → 1082 entries) and `logos.js` is cache-busted like
the league payloads (heuristic browser caching had been serving week-old maps). Six clubs got
Wikipedia crests (no ESPN art exists); Universidad O&M keeps initials — no crest anywhere.
UI: moose icon replaces the green hollow-square header fallback; the News tab went from stub
to a live client-side ESPN news feed per league (the API is CORS-open, so the static site
needs no build step) with injury tagging and empty/error states; club columns are
canvas-measured to the longest name so tables never truncate (phones h-scroll inside the
panel); the projected-finish axis ticks were realigned to the bar track (a 104px grid-offset
bug put "1" over the team names); match-row expansions now show per-team model inputs rather
than bare differentials. 8 new Playwright regressions, fail-verified against pre-fix code;
suite 38 green.

---

## UI feedback batch + Entenser rebrand (2026-07-08 → 2026-07-09, plan completed and deleted)

An 18-task batch from a user QA pass on desktop and mobile. Branding: the site is now
**Entenser** (moose-head icon + wordmark, favicon, sidebar brand — assets matted to
transparency via `scripts/matte_brand_logo.py`, replacing the "Pitchside" placeholder).
Fixes: sub-1% odds show one decimal instead of rounding to "0"; the Projected Finish plot
is anchored to the server-baked rank (it previously re-simulated client-side and could
disagree with the League Table by ~5 ranks — the Tottenham 12th-vs-17th bug); 23 missing
team logos filled (8 more have no ESPN crest and correctly keep monogram fallback); dark
crests get a light backing plate. Features: MLS Cup joined Shield/East/West/Spoon as a 5th
top box; squad value now shows a 4-way Attack/Mid/Defense/GK split, open by default, live
for 15 leagues (`_aggregate_team()` emits `mid/gk_value_pct`; `scripts/patch_squad_value.py`
refreshes payloads without the full model rebuild); "Today's Edge" became "Matches", grouped
by date then league; News tab stub; the model-vs-market header shows its build date. Mobile:
team names restored in league tables, Next-5 inline+scrollable (MLS renderer only — the
single-table renderer used by ~19 leagues still clips Next-5 off-screen on mobile, a
pre-existing bug tracked as a follow-up, as is an edge-summary strip for the Matches view).
A pre-existing test-infra bug (session-scoped chdir in the browser-smoke fixture breaking
later repo-relative tests in full-suite runs) was found and fixed by the batch's final gate;
full suite green at 628 passed. Comprehensive per-league trophy history and squad-value
buildout for the 5 remaining uncovered leagues were explicitly deferred (see the 2026-07-08
design spec).

## UI feedback round 3 + two model-research campaigns (2026-07-09 → 2026-07-10, plan completed and deleted)

A 19-task batch covering rules correctness, MLS clarity, branding, news, match metadata, and
model-health UX, plus two flagged research campaigns run under `docs/experiment-protocol.md`.
Promotion playoffs are now actually simulated (a `promoted` composite bucket runs the bracket —
4-team England/Spain, 6-team Serie B with byes, cross-league barrages at a 0.33 base rate —
mirrored in the client what-if sim) with a per-league plain-language rules line. Multi-source
news (8 curated feeds baked per league + live ESPN, anti-gossip filter) and club-news cards
shipped for every registry league. Match cards gained kickoff/venue/weather (open-meteo).
Model Health was overhauled: feature definitions, live phase Brier vs market/naive across all
leagues, per-club Brier, and paired-bar decile calibration. A UEFA Spots tab explains the
coefficient-driven Champions League slot counts. Team-page ELO history now stitches across
tier boundaries (Hull City's line is continuous 2014–2026 instead of jumping at promotion).
Two research campaigns both concluded **DROP**: (R1) a top-15 fieldable-squad-value feature
(1 GK/5 DEF/5 MID/4 FWD by value) beat total squad value by ~0.0003 Brier but both made the
MLS model worse than no value feature at all — TM value adds nothing over the ELO/xG/form base
on MLS specifically (the harness edit was reverted; the `top15_value_eur` column itself stays
in the mapped CSVs). (R2) a unified two-tier ELO — one continuous rating instead of seed-on-
promotion — lost to the current tier-bridge approach on every leg of the England chain
(pooled Δ=+0.0053 worse): the champion's flat 40% season-boundary regression erases any
persistent cross-tier gap a continuous rating would need, so the bridge's explicit offset is
doing real work implicit continuity can't replace. Full detail in `docs/feature-hunt-log.md`
(2026-07-10 entries).

## Public-launch completion pass (2026-07-11, plan completed and deleted)

Assessed two Codex reports (a 2026-07-10 business/UI/model plan and its 2026-07-11 execution
report) against the actual codebase and found the reports already stale — nearly all their
infrastructure backlog had shipped. The pass closed the genuine remaining gaps rather than
re-building done work: greened three failing tests (all guardrails lagging shipped features —
`model-slices.js` missing from two payload-exclusion lists, and the browser smoke test still
asserting the pre-rename "Matches" landing title), then DRY'd the duplicated exclusion list so
both tests import the canonical `_NON_PAYLOAD` from `validate_payloads.py`. Shipped the P0
trust/legal content as four static routes (`?league=about|data-sources|responsible-gambling|
privacy`) with number-accurate copy, and fixed a real gap where the edge-board landing and
power route shipped with an empty footer (no attribution or legal links). Verified in-browser:
Command Center non-empty with zero horizontal overflow at 375px, corrected tab titles for
share/SEO. Drafted five preseason launch articles in `docs/content/` from live payload numbers.
No model change (feature hunt stays deferred; diagnostics showed no Brier gain). Remaining work
is external/decision-gated and catalogued in `docs/remaining-external-dependencies-2026-07-11.md`
— chiefly the still-uninstalled nightly build job, paid odds coverage, deploy, analytics, email
backend, and legal review.

## Race-delta chips + draw-calibration diagnostic (2026-07-11, plan completed and deleted)

U2 shipped per-race "since last build" delta chips with a why-changed cause label (result / model /
refresh) on league race cards, sourced from `data/odds_history.parquet` snapshots (commit 9fd57fd).
M2 diagnosed the hypothesized total-goals-conditioned draw miscalibration and returned **NO-GO**:
the champion's `draw_reliability` slice shows the well-sampled bulk already calibrated within ~1pp
(23.2%→24.1% n=568; 27.4%→27.2% n=1072), over-prediction confined to small-n tails, and the
motivating ~616-row total-goals signal self-contradictory against the reliability curve. The
deferred definitive per-match diagnostic (M2.3–M2.5) was approved by the user 2026-07-11 and became
Phase 0 of the follow-on draw-Brier campaign (below).

## Draw-Brier campaign — closed at Phase 0 with NO-GO (2026-07-11, plan completed and deleted)

User-approved campaign to lower draw-class Brier via diagnostic + cheap harness experiments (no
new architecture, no external data). Phase 0 built `scripts/probe_draw_decomposition.py`, which
reproduces the champion pipeline exactly (0.633117 / draw 0.191867, 6-decimal match to the pinned
report) and simulates candidate fixes offline against persisted per-match components. The verdict
closed the campaign with zero harness churn: the draw column has no resolution (it scores worse
than climatology; Murphy RES 0.0005 < REL 0.0009), per-class blend weights and soft-hurdle
recombination show only 0.0001–0.0002 draw gain even when oracle-fitted on the test fold (bar:
0.0005), and the M2 total-goals hypothesis was refuted at full n (the real residual is draw
OVER-prediction in high-scoring matchups, worth ~0.0003, sub-noise). Draw improvement now has one
credible path: new draw-discriminating data (T3b, deferred). Full write-up in
`docs/feature-hunt-log.md` (2026-07-11 entry); artifacts in `experiments/draw_probe/`.

---

## Permanent constraints (do not re-litigate without explicit instruction)

See `CLAUDE.md` for the full decision list with dates. Key ones with rationale:

- **Market-blind model:** using closing lines in training collapses `model_prob - market_prob`
  to zero. Odds are CLV-only, never features.
- **2020 excluded, 2021 retained:** COVID bubble (no crowds, no real HFA). 2021 A/B-validated:
  removing it costs +0.0019 avg Brier (mostly 2023, where 2021 is the most recent training season).
- **Test seasons 2022–2025:** 2025 added 2026-06-09 once the season completed (540 matches).
  2026 is training-only; never in the test window while in-progress.
- **4-fold reports for gate candidates:** challengers must use the same 4-fold basis
  (`model_report.py` defaults). 3-fold reports are not comparable.
- **Verification protocol:** judge harness experiments on a single `--xgb-bag 5 --seed 42`
  run (σ≈0.0002), confirm gate-bound claims at a second base seed.
- **Edge threshold 8%:** established across all leagues (MLS + European).

## League expansion round 4 (2026-07-11, plan completed and deleted)

Added 14 leagues in three dependency-ordered phases (spec + plan under
`docs/superpowers/{specs,plans}/2026-07-11-league-expansion-round4-*`, since deleted).
**Phase 1** (Tier 1, no new infra): Scottish Championship/League One/League Two (mmz4281
`SC1/SC2/SC3`, chained to scottish-prem for tier-bridge seeding) + Austria/Switzerland/Romania/
Ireland (footballdata_intl new-leagues CSVs; corrected the expansion report's Switzerland code to
`SWZ`). **Phase 2** (projection-only, user "not worried about betting edge"): China + Russia kept
on footballdata_intl (Pinnacle-odds backbone retained for a future edge layer) rendered
projection-only; Saudi Pro League / A-League Men / WSL on a new slug-generic
`espn_fixtures.espn_results_frame` (liga-mx keeps its torneo-specific frame). **Phase 3**: new
`data_pipeline/api_football.py` adapter (env/`.env` `API_FOOTBALL_KEY`). The api-sports.io FREE
plan only serves seasons 2022–2024, so Finland ships results-only off CURRENT football-data (2026,
like Poland — API-Football not needed) and Canadian PL ships results-only off 2024 (8/8 crests via
`team_logos`); a paid plan + wider `LEAGUE` season ranges makes both current and unlocks
Finland/Poland forward fixtures via the (now-empty) `FIXTURE_OVERRIDE` hook.

All 14 beat or match naive in-season (WSL 0.505 vs 0.630, Russia 0.579 vs 0.647, Saudi 0.552 vs
0.644). Split-round formats (Austria/Romania/Finland) are plain-table approximations with an honest
`rules` caveat. Two durable lessons: (1) `fetch_league_teams.py` rewrites every still-"soon" league
to a stub, so a freshly-built league must be flipped to `"live"` in REGISTRY before any later fetch
or its data is clobbered (correct batch order in the `league-build-workflow` memory + CURRENT_STATE);
(2) `source="espn"` leagues get 100% crest coverage (frame uses ESPN names directly) while
footballdata/intl leagues need `FD_ESPN`/`FDI_ESPN` short-name→displayName maps. Added a "Women"
sidebar group for WSL and guarded short-history leagues (CPL's 3 seasons) in the per-year diagnostic.

## NYT-style dark editorial redesign (2026-07-11, plan completed and deleted)

User supplied two New York Times screenshots (desktop front page + mobile app, both dark) and asked
for that layout language: the left sidebar was replaced site-wide by a three-row masthead (date,
serif Entenser wordmark, country/flag section bar with league dropdowns, LIVE fixtures strip) plus a
mobile bottom tab bar (Home · Matches · Leagues · Favorites), and the Home landing became an
editorial front page whose headlines are written deterministically from HOME_DATA (movers/races/
relegation, preseason rollover artifacts suppressed). New routes: `?league=leagues` (flag-grouped
index that inherits the sidebar's role and pin stars) and `?league=favorites` (pinned leagues plus
pinned clubs — new `pitchside.favTeams` key, star on the team-profile header, per-league lazy data
loads). `build_home.py` gained a tested `fixtures` array (next 10 days, prominence-first) for the
homepage rail; `home.js` joined the canonical `_NON_PAYLOAD` exclusion, fixing three contract-test
failures that had been latent since the first-draft home page a day earlier.

## NYT redesign feedback round (2026-07-11, plan completed and deleted)

Same-day follow-up to the NYT editorial redesign: a 16-item feedback batch covering search,
masthead structure, headline quality, a world map, MLS parity, and season-currency honesty.
The most consequential fix was structural rather than cosmetic — a `?team=` deep-link
silently failed because it ran before the tab-switch click handler was attached later in the
script, a reminder that this file is one large script block where execution order matters
even with function hoisting. The season-status work surfaced a real data-freshness problem:
14 leagues were rendering an ambiguous "season projection" label for seasons that had fully
concluded with no next-season fixtures published yet; a background rebuild queue confirmed
12 of them were genuinely between seasons (not a build failure) and the UI now says so
explicitly. MLS's finish-plot parity was implemented by extending the existing `runSim()`
simulation with a conference-relative rank histogram rather than writing a parallel sim, so
the what-if resimulation path updates the new panel for free.

## Intelligence Hub S0: historical flywheel hardening (2026-07-18, plan completed and deleted)

First foundation step of the Intelligence Hub paywall program (`docs/intelligence-hub-implementation-instructions.md`):
closed the five data-integrity gaps roadmap items F-1 through F-5
(`docs/product-roadmap-2026-07.md` §2) that every later event/attribution/receipt feature
depends on. `data/match_prob_history.parquet` had been silently discarded by CI every night
since it was introduced — written by `archive_odds_snapshot.py` but never allowlisted past
`.gitignore` or staged in either refresh workflow's commit step; both are now fixed and the
locally-accrued rows were seeded into the repo. Investigation found the roadmap's proposed new
`data/trajectory_history.parquet` would have duplicated data `data/odds_history.parquet`
already accrues indefinitely and already commits — the real gap was the *public*
`webapp/data/drift-traj/<league>.js` capping at 180 raw points with no season boundary, so a
league crossing a season rollover would eventually leak prior-season rows into an
unauthenticated payload; fixed by capturing each payload's `season` field on every archived
row and filtering the public trajectory to the league's current season (unknown-season rows,
accrued before this shipped, are kept rather than dropped). Weekly recaps and race-deltas now
archive to `data/weekly-archive/<date>.json` and `data/race_deltas_history.parquet`
respectively instead of being overwritten every run. A new `scripts/validate_history_growth.py`
runs as the last step of both refresh workflows, before the commit step, and fails the build
if any accrual parquet shrinks versus the version committed at HEAD, or if a public trajectory
file carries a season-mismatched point. Next: S1 (stable cross-season IDs), as its own plan file.

## Intelligence Hub S1: stable IDs for the MLS pilot (2026-07-18, plan completed and deleted)

Second foundation step. Investigation before writing code found that `scripts/build_dashboard_data.py`
already resolves a real, source-assigned stable team identifier (ASA's own `team_id`, e.g.
`"KAqBN0Vqbg"`) for every MLS team and game internally — it was simply being dropped before the
payload dict was built. Exposed it as `team_id` on every standings row and `home_id`/`away_id` on
every game card, verified against a real local rebuild (not just synthetic tests, since this file's
data-assembly body has no existing unit-test coverage — it depends on live ESPN/ASA calls). The one
genuinely new piece was `fixture_id`: no fixture identifier survives rebuilds today — the existing
`id` field on game cards is the client-side simulator's array index (the "SIM PORTING CONTRACT") and
must never be repurposed. Added `scripts/payload_utils.make_fixture_id()`, a versioned SHA-1 hash of
league+season+date+home_id+away_id, called alongside the untouched `id` field rather than replacing
it. Both new IDs were threaded into the archive layer (`data/odds_history.parquet` /
`data/match_prob_history.parquet`) as additive columns, and `validate_payloads.py` now gates the MLS
payload on their presence. Scoped to MLS only — `league_id` and `season_id` already satisfied the
spec as-is (no changes needed), and generalizing team_id/fixture_id to the other ~40 leagues in the
registry is separate follow-on work since each sources team names from a different upstream with no
equivalent stable-ID field yet. Next: S2 (extract and version the simulation engine), as its own plan
file.

## Intelligence Hub S2: shared simulation engine (2026-07-18, plan completed and deleted)

Third foundation step: extracted the Monte Carlo core duplicated between `runSim` (MLS conference
format) and `runSimTable` (single-table format, ~40 other leagues) in `webapp/index.html` into
`webapp/sim-engine.js` — fixture resolution, per-trial point/key sampling, a percentile helper, a
seedable PRNG (mulberry32), and a Monte Carlo standard-error helper. Unlike S0/S1, both league
formats were in scope together: the duplicated code already existed side by side in the same file,
so unifying only one would have defeated the point. The repo has no `package.json`/JS build tooling
anywhere, so the module is a dependency-free UMD file (works via `<script>` in the browser and
`require()` in Node) and its characterization tests use only Node's built-in `assert`, wrapped by a
thin pytest subprocess shim so `pytest tests/` stays the single CI entrypoint. The seeded PRNG was
threaded through *every* random draw in both formats, including the MLS playoff bracket
(`confBracket`) and the promotion-playoff bracket (`promoWinner`) — not just the outer trial loop —
so a seeded run is fully reproducible end-to-end (verified live: two `runSim(500, 12345)` calls
against the real MLS page returned byte-identical output), while an unseeded call draws a fresh seed
each time, preserving today's behavior exactly. Both `_meta` (engine version/n/seed) and per-metric
`_se` (standard error) fields are additive to the existing output shape. Verified against the real
running site (not just unit tests): loaded MLS and EPL, clicked a real force-result box on each,
confirmed the resimulation ran through the ported engine with zero console errors and correct
visual updates. Next: S3 (archive reproducible simulation states), as its own plan file.

## Intelligence Hub S3: archive reproducible simulation states (2026-07-18, plan completed and deleted)

Fourth foundation step: `scripts/archive_intelligence_state.py` archives a compact, replay-relevant
snapshot of the MLS payload after each build — standings, the client simulator's `sim.pmatrix`/team
order, upcoming fixtures (by S1's stable `fixture_id`, not display order), season-format rules, and
provenance — and fails closed (writes nothing) if any required field is missing. Compliance finding
before writing any code: `docs/intelligence-hub-implementation-instructions.md` rule 6 prohibits
committing private archives to a publicly readable repository, and `gh repo view` confirmed this repo
**is** public. Unlike `data/match_prob_history.parquet` (a pre-existing gap from before this rule
existed, fixed in S0), this was new work under a document stating the rule explicitly — so
`data/intelligence_snapshots/` is gitignored, not committed; the archiver still runs and validates on
every build, with durable storage deferred to S5's access-controlled infrastructure. Added
`replayMlsConferenceTargets` to `webapp/sim-engine.js`, reusing S2's `resolveFixedAndFree`/
`simulateTrialPoints` with zero new sampling logic to replay an archived snapshot and reconstruct
playoff/hfa/shield/spoon/conf_win/proj_pts (the bracket-dependent `cup` target is excluded — it needs
`confBracket`, which stays in `webapp/index.html`, not the Node-requirable engine file).

The replay test against the real MLS payload initially failed at the SIM PORTING CONTRACT's documented
±1.5pp tolerance. Investigated rather than loosened blindly: running the replay at both 20k and 200k
trials produced the *same* ~2-2.7pp gap on a handful of borderline metrics — a gap that doesn't shrink
with more trials isn't Monte Carlo noise. Traced to a real, pre-existing, undocumented-in-the-comment
asymmetry: `build_dashboard_data.py`'s "strength-uncertainty widening" (`scripts/eval/sim_variance.py`,
added 2026-07-07) perturbs each team's win probability per server-side trial to represent model
uncertainty; the browser's what-if simulator has never replicated this. Not a regression introduced by
S1-S3 — a previously-unquantified gap in an existing, already-shipped feature, now measured for the
first time (and expected to shrink automatically as the season progresses, since the perturbation
scales with `1 - season_fraction`). The replay test's tolerance was set to 3.0pp with this reasoning
documented inline, rather than silently widened with no explanation. Next: S4 (build canonical
intelligence events), as its own plan file.

## Intelligence Hub S4: canonical intelligence events (2026-07-18, plan completed and deleted)

Fifth foundation step: `scripts/build_intelligence_events.py` detects five event types (forecast_move,
threshold_crossing, result, model_change, data_health) between the two most recent snapshot dates. Key
architecture decision, made before writing any code: rather than depend on S3's
`data/intelligence_snapshots/` (gitignored, private, and empty on every fresh CI checkout — nothing
durable to diff against there), the detector reads `data/odds_history.parquet` and
`data/match_prob_history.parquet` (S0/S1 — already public, already committed, already accruing daily).
That choice means the detector's own output is also derived only from already-public data, so
`data/intelligence_events.parquet` and `data/intelligence_events_latest.json` are committed (unlike
S3's snapshots) — solving the "no persistent state across CI runs" problem structurally rather than
reaching for GitHub Actions cache or another workaround. Reused `build_race_deltas.py`'s existing
result/model/refresh classification instead of duplicating it; evidence links for "result" events are
found by diffing `match_prob_history.parquet`'s upcoming-fixture rows between the two snapshots (a
fixture present as upcoming yesterday and absent today resolved in between) using S1's `fixture_id`.
Attribution is observational only this pass (`attribution_quality`: `"observational"` or
`"unavailable"`, never `"counterfactual"`) — the deeper counterfactual/Shapley decomposition §4.6
describes needs S3's archived states to have accrued enough history to replay against, which they
haven't yet. Materiality scoring is a documented, deliberately simple heuristic (movement magnitude +
threshold-crossing + result bonus); fixture-impact and pinned-team/user-threshold factors are noted
inline as depending on features not built yet, not silently omitted. Run against the real repo: 17
real events detected on the first run, all `forecast_move` with `cause_class="model"` — correctly
reflecting that this session's own commits changed `code_rev` between builds without the champion
config itself changing (so the league-level `model_change` detector, which only checks `config_id`,
correctly stayed silent). One real mistake caught by git itself: the new parquet file was silently
blocked by the pre-existing broad `data/*.parquet` gitignore rule until `git add` warned about it —
fixed by adding it to the allowlist, same pattern as the other public accrual files. Next: S5 (secure
delivery — auth, entitlements, Stripe), as its own plan file. This is a materially larger, different
kind of step than S0-S4: new infrastructure (magic-link auth, Stripe webhooks, a preference store, an
entitlement middleware) rather than extending the existing static-site build pipeline.
