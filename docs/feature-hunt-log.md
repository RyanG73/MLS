# MLS Feature Hunt Log

## 2026-07-11 — Hybrid bridge-decay for promoted/relegated teams (R2 follow-up) — NULL / NO CHANGE

**Hypothesis:** the R2 unified-ELO drop still suggested a narrower win: keep the explicit
cross-tier bridge for preseason seeding, but decay its influence after the mover starts playing
in the destination league. This should preserve the bridge's tier-gap information while letting
destination-league evidence take over quickly.
**Method:** extended `scripts/eval/unified_tier_elo.py` with `brier_bridge_decay_{5,8,10}`.
For each first-destination-season mover match, the mover rating is
`w(n) * (exit_elo + bridge_delta) + (1-w(n)) * destination_league_elo`, with linear `w(n)`
from 1.0 before the first mover match to 0.0 after N prior mover matches. Same England-chain
match sets as R2, same champion constants, same sum-form Brier.
**Result:** decay-8 pooled Brier = **0.6326**, tied with seeded production analogue
(`0.6326`) and essentially tied with destination-league updating (`0.6325`), while still
beating the frozen bridge gate metric (`0.6410`). Pair results were mixed: EPL promoted
teams improved vs seeded (0.6019 vs 0.6051), but lower-chain promoted/relegated legs gave
back small amounts.
**Verdict:** no production change. The correct policy remains: bridge seed at preseason,
then normal destination-league updating. If revisited, it needs an early-window-only gate
(first 5, 6-15, rest) rather than full-season pooling.
**Artifact:** `experiments/r2-hybrid-bridge-decay.report.json`.

## 2026-07-10 — Unified two-tier ELO for promoted/relegated teams (R2) — DROP

**Hypothesis:** one ELO rating updated continuously through both tiers (no seed-on-promotion,
no fitted bridge offset) predicts promoted/relegated teams' first-season matches better than
the current tier-bridge approach, since it never freezes or resets at the boundary.
**Method:** `scripts/eval/unified_tier_elo.py`, England chain (epl↔championship↔league-one↔
league-two), champion constants (K=25, HA=80, regress=0.40), four rating systems scored on
IDENTICAL mover-match sets per pair/direction: `bridge` (current gate metric — exit ELO frozen
at the June-30 cutoff + fitted offset, never updates), `seeded` (production analogue — exit
ELO + offset as a season-entry seed, then updates in-season), `league` (no bridge — starts flat
1500), `unified` (one merged cross-tier replay, no seed/offset at all). Deterministic — no
seed/bagging, so no second-run confirmation needed (the ELO replay isn't stochastic the way
the XGB harness is).
**Result:** Δ (unified − seeded) = **+0.0053 pooled → DROP**, and unified loses on **every one
of the 6 chain legs** (+0.0000 to +0.0089), n=7,386 matches. Full log
`logs/r2-unified-tier-elo.log`; report `experiments/r2-unified-elo.report.json`.
**Notes:** Mechanism (from `tier_gap_mean_elo`): the champion's flat 40% season-boundary
regression pulls every team toward 1500 every close season, so a continuous cross-tier rating
never accumulates the ~100–130 ELO gap the fitted bridge offsets encode — mean unified ELO is
~1502 for Championship AND League One, vs EPL's ~1540. The bridge's *explicit* offset is doing
real work that implicit continuity can't replicate under this regression regime. Secondary,
unexpected finding: `seeded` (0.6326) and `league`/no-bridge-at-all (0.6325) are statistically
indistinguishable pooled over the WHOLE first season — the seed's benefit is diluted by
mid-season convergence at K=25; the bridge's value likely concentrates in early-season matches,
which this full-season pooling doesn't isolate (a follow-up early-window slice, not run here,
would need to precede any claim that the current seeding itself is unnecessary). No production
change; nothing ported; `promotion_gate.py` not invoked (never reached a KEEP). This closes
Task R2 step 2 (step 1, the display-continuity ELO-history stitch, already shipped 2026-07-09).

## 2026-07-10 — Top-15 fieldable-squad value (R1) — DROP (and total squad value re-confirmed DROP)

**Hypothesis:** transfer value of a best-XI+bench proxy (top 1 GK + 5 DEF + 5 MID + 4 FWD by
value, short buckets backfilled — `import_transfermarkt._aggregate_team`, unit-tested) beats
total `squad_value_eur` as an XGB input because total value dilutes with unplayable depth.
**Result:** Δ=−0.0028 vs Base → **DROP** (screening bar is Δ>+0.001; this is ~14× the bagged-run
noise floor σ≈0.0002, so no second-seed confirmation needed — never gate-bound).
**experiment_id:** feature-top15-value-s42-20260710T112247 (`--cache --ab-only
"Base,+TM_SquadValue,+TM_Top15" --xgb-bag 5 --seed 42`; full log `logs/feature-top15-value-s42.log`)
**Notes:** Base 0.6342 · +TM_Top15 0.6369 · +TM_SquadValue 0.6372. The dilution hypothesis is
*directionally* right — top15 beats total value by ~0.0003 — but both variants make the model
worse than no value feature at all on MLS: within-season z-scored TM value adds nothing the
ELO/xG/form base doesn't already carry (the same reason +TM_SquadValue was never promoted to
`_FEAT_BASE`). Feature transform mirrored the existing one exactly (z within season,
home/away/diff, lag-(0,1) lookup). Harness edit reverted per protocol §4; the `top15_value_eur`
column stays in the MLS mapped CSVs 2017–2026 (all shared columns verified bit-identical to the
previous generation; mean top15/total ≈ 0.80–0.86). If the idea is revisited, try it where value
features already carry signal — the big-5 preseason value-tilt path (M2), not the MLS match model.

## 2026-07-07 — Value-informed preseason tilt (M2, the A10a revival) — KEEP (bottom-half targeted, β=0.5)

TM `saison_id` pages serve era-appropriate values (Gate-0 probe: GB1 2019 = City €1,050m,
Spurs €807m — matches 2019 reporting), unlocking a leakage-clean backfill
(`scripts/eval/tm_value_backfill.py`, 976 team-seasons big-5 2017–2026, team totals only per
the rights register, 97% FD-mapped). Lever: fit log(value_{S-1}) → ELO walk-forward, tilt
preseason fixture log-odds by β·(value_elo − elo) — a LOCATION fix the symmetric widening
can't provide. Untargeted β=0.5: releg −0.0055 but title +0.005 / UCL +0.007 (the linear fit
overshoots for mega-value clubs, dragging title odds toward wealth) — REJECTED. Bottom-half-
rated targeting (where the measured location error lives): releg −0.0052/−0.0055 at seeds
42/7, title +0.0001/+0.0000, all else noise — KEEP, ported to `build_league_data.py`
preseason sims. Production effect: Spurs relegation 32.4% → 16.5% (campaign start: 42.0%;
A7 cohort CI 3–33%).

## 2026-07-07 — Per-family ELO regression rate (M3, the A8 deferred sweep) — VALIDATED NULL

A8-methodology early-60d proxy with the production club_prior_beta=0.75: big-5 prefers less
regression monotonically but the full range is 0.00067 (0.24166@0.25 vs 0.24233@0.40) —
~10× below A8's β effect; tiers flat (range 0.00018). With the club-prior target carrying
the seeding, the rate barely matters. regress=0.40 stays for all families.

## 2026-07-07 — Season-outcome sweep: per-family preseason σ + decaying widening — DOUBLE KEEP

**Experiments** (judged on the season-outcome replay, `scripts/eval_season_outcomes.py`,
per experiment-protocol §4; both confirmed at seeds 42 AND 7):

**(a) Per-family preseason σ — KEEP tiers=90, big-5 stays 60.** The A10(b) σ=60 was tuned on
big-5 outcomes. Sweeping σ per family on the (bridge-faithful) replay: the goals-only/FD
family improves on BOTH table ends at σ=90 — bottom (releg+promo) 0.1112→0.1088 and top
(title/ucl/playoff/europa/conf) 0.0739→0.0734 at seed 42; seed 7 confirms (0.1114→0.1090,
0.0739→0.0734). σ=120 adds only a marginal bottom gain (0.1075) with top flat — 90 is the
balanced confirmed point. Big-5 keeps 60 (σ=90 there trades top −0.0008 for bottom, the
original A10(b) finding). `preseason_sigma_for_source()`: understat 60 · footballdata 90 ·
default 60 (untested families).

**(b) Decaying widening — KEEP σ_eff = σ·(1−season_fraction).** The preseason-only cutoff
was the f=0 special case; uncertainty doesn't vanish at the first kickoff. Both seeds, pooled:
cp0.25 releg −0.0015/−0.0014, promo −0.0008/−0.0009, title flat-to-better; cp0.5 small gains;
no regression at any checkpoint/outcome. Production sims now widen in-season with the decayed
σ (NWSL mid-season ≈ σ35).

**Also from the same sweep infrastructure:** the league-one/league-two bridge offsets were
LOSO-fit on ~1,300 cross-tier matches per pair — the fit converges exactly onto the ±120
static priors (validated null, priors kept). The replay itself was upgraded first to measure
production faithfully (tier-bridge seeding, format-league official classification, ASA
leagues): honest preseason skill vs base rates is releg +0.06 / promo +0.01 / title +0.30 /
UCL +0.46 — bottom-table preseason weakness is real, which motivated (a) and (b).

## 2026-07-06 — Preseason variance widening (A10b): per-sim strength perturbations — KEEP σ=60 uniform (Europe), DROP γ gap-scaling

**Experiment:** The production season sim samples outcomes from FIXED per-fixture DC
probabilities — zero strength uncertainty, so preseason odds are overconfident point estimates
(the Spurs-42% failure mode). New `scripts/eval/sim_variance.py`: per simulated season, draw
δ_t ~ N(0, σ_t) per team (ELO-point scale) and tilt each fixture's home/away log-odds by
±δ·ln10/800 (a δ differential moves home-vs-away log-odds exactly like the ELO expectation
curve). The A10(b) hypothesis: σ_t = σ_base·min(1 + γ·|club_prior_gap_t|/200, 1.5) — wider
uncertainty for teams whose seed disagrees with their own history.

**Judged on the A7 big-5 FD cohort replay** (not aggregate match Brier — preseason odds have
no per-match Brier): 2018–2025 × big-5 = 40 league-seasons, production-mirrored preseason sims
(DC fit on <S with recent-4 window, temperature from <S−1 scored on S−1, ELO seeds with the
production `club_prior_beta=0.75`, promoted teams on the 15/85-pct fallback, 4 000 sims/config).
Binary Brier of P(bottom-3 finish) vs actual bottom-3, plus title/top-4 guards:

| σ_base (γ=0) | releg Brier | title Brier | top-4 Brier |
|---|---|---|---|
| 0 (baseline) | 0.12628 | 0.03145 | 0.09200 |
| 30 | 0.12348 | 0.03148 | 0.09139 |
| **60** | **0.11862** | 0.03178 | **0.09062** |
| 90 | 0.11432 | 0.03260 | 0.09136 |
| 120 | 0.11175 | 0.03380 | 0.09390 |
| 150 | 0.11071 | 0.03520 | 0.09759 |

Relegation improves monotonically but title/top-4 degrade past σ≈60–90: the table's bottom is
overconfident, its top is not. σ=60 — which equals the empirically observed sd of seed→end
ELO drift (62) — is the only grid point improving relegation AND top-4 with title flat.
Confirmed at a second RNG stream (rel 0.12635→0.11878, top-4 −0.0014, title +0.0004).

**γ gap-scaling: DROP.** At σ=90 the high-gap cohort's own relegation Brier worsens as γ rises
(0.0498 → 0.0507 → 0.0517 for γ 0/1/2); pooled effect ≈ 0. Root cause: the fallen-giant error
is a LOCATION error (bottom-half high-gap teams: predicted 0.238 vs observed 0.143 — the DC fit
on the bad season, A7 causal link 2), and symmetric variance cannot fix location; meanwhile
extra variance on top-half fallen giants (observed relegation 0%) is pure harm. Post-A8 the
Spurs-shaped cohort is nearly empty anyway (n=4; the pooled top-gap-decile threshold fell from
A7's 64 to 34 — β=0.75 seeding already closed most of the gap).

**Shipped:** `PRESEASON_SIGMA = 60.0`, applied in `build_league_data.py`'s Monte-Carlo when
`is_preseason` only (in-season sims and MLS unchanged; family governance). EPL preseason
rebuild: Spurs relegation 36.7→32.4% (42.0% before A8; A7's cohort CI is ≈3–33%), Hull
89.7→78.0%, Arsenal title 51.1→45.2%, proj_pts essentially unchanged (variance, not drift).
7 unit tests incl. a widening-contract statistical test; suite green (504 passed).

## 2026-07-05 — xG-blended ELO update (A5): `--elo-xg-blend` — DROP

**Experiment:** ELO banks finishing luck via the raw match result (`s_h`); A5 tests replacing it
with an effective score blended toward the xG-implied result — `s_eff = (1-λ)*s_result + λ*s_xg`,
where `s_xg` is win/draw/loss on `home_xg - away_xg` with a ±0.25 dead-zone, λ=0.3. Matches
missing xG fall back to the raw result (λ=0 for that row).

**MLS harness A/B** (`--xgb-bag 5 --seed 42 --elo-xg-blend 0.3 --test-seasons 2022 2023 2024 2025`,
`ens_stacked_brier`):

| season | n | ens_stacked_brier |
|---|---|---|
| 2022 | 489 | 0.6302 |
| 2023 | 521 | 0.6336 |
| 2024 | 522 | 0.6396 |
| 2025 | 540 | 0.6349 |
| **mean** | | **0.6346** |

**Verdict: DROP.** Mean 0.6346 vs champion 0.6330 (**+0.0016**) — a consistent regression across
all four folds, roughly 8× the single-bagged-run noise floor (σ≈0.0002 per
`docs/experiment-protocol.md`). Blending xG into the ELO update rule does not help the downstream
ensemble even though `elo_diff` remains the top individual feature by gain. No second-seed
confirmation needed (DROP verdicts are unambiguous). `--elo-xg-blend` remains in the harness as an
opt-in, off-by-default flag — champion config unchanged.

## 2026-07-05 — Draw-aware structure (A11): hurdle head + per-season DC rho — DROP

**Experiment:** Two candidates targeting the draw class (worst decile cal-err 0.108, per A1),
tested separately per the task spec:
- **(a) Two-stage hurdle:** `P(draw)` binary model × win-direction model conditional on
  non-draw, recombined (`--draw-two-stage`).
- **(b) DC rho re-fit:** Dixon-Coles low-score correlation `rho` fit per-season instead of
  pooled (`--dc-rho-per-season`), then re-checked through the temperature pass.

**MLS harness A/B** (`--xgb-bag 5 --seed 42 --test-seasons 2022 2023 2024 2025`, `ens_stacked` avg
— the champion-comparable metric; the harness's "Ensemble avg" line is the unstacked blend and
is not the gate metric):

| Config | avg (4-fold) | Δ vs champion |
|---|---|---|
| champion (pinned `challenger-bag5.report.json`) | 0.632977 | — |
| `--draw-two-stage` (hurdle) | 0.6347 | **−0.0017** |
| `--dc-rho-per-season` | 0.6352 | **−0.0022** |

Per-season `ens_stacked_brier`:

| season | champion-era n | hurdle | rho |
|---|---|---|---|
| 2022 | 489 | 0.6288 | 0.6288 |
| 2023 | 521 | 0.6359 | 0.6359 |
| 2024 | 522 | 0.6382 | 0.6404 |
| 2025 | 540 | 0.6359 | 0.6360 |

**Verdict: DROP (both).** Both candidates regress the standard aggregate gate — criterion (ii)
from the task spec, "must not regress beyond noise" — well past the ±0.001 threshold. Hurdle is
flat in 2022 but degrades every season after; rho is worst on 2024 specifically (+0.0022 on that
fold alone). Because this is a clean double-failure on the gate's own primary criterion (not a
narrow miss where a calibration win might offset a small aggregate loss), the A1
`draw_reliability` slice check (criterion i) and the `roi_by_edge_bucket` draw-bet backtest
(criterion iii) were skipped — same precedent as A4: neither can rescue a result this far past
noise. No second-seed confirmation needed (DROP verdicts are unambiguous per
`docs/experiment-protocol.md`; second-seed confirmation is reserved for gate-bound KEEP claims).
`--draw-two-stage` and `--dc-rho-per-season` remain in the harness as opt-in, off-by-default
flags (matches A4/A8/A2 precedent for documented negative results) — champion config unchanged.
Per the task text, B5/B12 continue to suppress draw-side Kelly sizing (probs shown, no unit
sizing) until a KEEP lands on this track.
**experiment_ids:** a11-hurdle-s42-20260705, a11-rho-s42-20260705

## 2026-07-04 — Time-varying home-field advantage (A4) — DROP

**Experiment:** Replace DC's single pooled home-advantage with a season-level estimate shrunk
toward the pooled value — `ha_s = (n_s·ha_hat_s + k·ha_pool)/(n_s+k)`, atk/dfd/rho held fixed
from the pooled fit, `k` chosen per fold from `{50, 100, 200}` on cal-fold DC Brier
(`fit_dc_dynamic_ha` in `scripts/eval/dixon_coles.py`, `--hfa-dynamic` flag). Motivated by the
documented 2024/25 home-win collapse and the draw class's 0.108 max decile cal-err (A1) — the
thesis was that a static HFA can't track the regime shift and mis-priced home mass leaks into
draws.

**MLS harness A/B** (`--xgb-bag 5 --seed 42 --test-seasons 2022 2023 2024 2025`, ens_stacked avg):

| Config | avg (4-fold) | 2024 fold |
|---|---|---|
| champion (static HFA, pinned `challenger-bag5.report.json`) | 0.632977 | 0.634913 |
| `--hfa-dynamic` | 0.635075 | 0.6397 |
| Δ | **−0.0021** | **−0.0048** |

**Verdict: DROP.** Both the standard aggregate gate and the 2024-fold-specific check this task
was designed around move the wrong way, well past the ±0.001 noise floor — the lever hurts
worst on the exact fold it was meant to help. Per-fold `k` bounced between the grid extremes
(50/200/200/50) rather than settling near a stable value, another sign this is fitting cal-fold
noise rather than a real seasonal signal. Because the result is a clean double-failure (not a
narrow miss where a calibration win might be hiding behind a small aggregate loss), the A1
`draw_reliability` slice re-check was skipped — it cannot rescue a verdict that already fails on
both of the task's own judging criteria. No second-seed confirmation needed (DROP verdicts are
unambiguous per `docs/experiment-protocol.md`; second-seed confirmation is reserved for
gate-bound KEEP claims). Code kept as an opt-in, off-by-default flag (matches A8/A2 precedent for
documented negative results) — champion config unchanged.

## 2026-07-03 — Variable ELO season regression (A8): club-prior target β — MLS DROP / EUROPE KEEP

**Experiment:** Season-boundary regression toward `(1-β)·1500 + β·mean(end-of-season ELO,
prior ≤3 seasons)` instead of flat 1500 (`compute_elo(club_prior_beta=…)`, harness flag
`--elo-club-prior-beta`); plus a per-team rate knob `regress_gap_k` (regress harder when the
rating deviates from the club prior).

**MLS harness A/B** (`--xgb-bag 5 --test-seasons 2022 2023 2024 2025`, ens_stacked avg):

| Config | seed 42 | seed 7 |
|---|---|---|
| baseline (flat 1500) | 0.6347 | 0.6356 |
| β=0.25 | 0.6338 | — |
| β=0.50 | 0.6339 | — |
| β=0.75 | 0.6333 (Δ +0.0014) | 0.6351 (Δ +0.0005) |

**MLS verdict: DROP for the champion** — seed 42 clears the 0.001 gate but seed 7 does not
confirm (+0.0005). Consistent sub-signal: the 2025 fold improves at BOTH seeds (−0.0044,
−0.0053); 2024 regresses ≤ +0.001. MLS champion config unchanged.

**European verdict: KEEP for production seeding (β=0.75).** ELO-proxy walk-forward, big-5 FD
2017+, home-prob Brier restricted to each season's first 60 days (the only window where the
seed matters — A7 showed in-season ELO recovers):

| Variant | early-60d Brier (n=3409) | high-gap slice (n=646) |
|---|---|---|
| flat (champion) | 0.24993 | 0.21295 |
| β=0.5 | 0.24406 | 0.19910 |
| β=0.75 | 0.24184 | 0.19385 |
| β=1.0 | 0.24031 | 0.18998 |
| β=0.75 + gap_k=0.4 | 0.24223 | 0.19427 |

Monotone in β, ~10× the MLS gate size on the pooled slice and −0.023 on A7's high-gap slice
(the primary evidence). **gap_k adds nothing over β alone → DROPPED.** β=0.75 ported to
`build_league_data.py`'s two `compute_elo` seeding sites (top of the plan's grid; β=1.0 was
best on the proxy but untested in the full-harness sense — revisit with the per-family
European champions from C2). MLS (`build_dashboard_data.py`) stays flat per its own gate.
Per-league regression RATES (b-i) not swept — deferred to the European-family champion work.

**Production effect (EPL preseason rebuild):** Spurs ELO 1442 → 1474, relegation 42.0% →
37.9%. Direction right, size modest — the preseason odds are dominated by the DC fit on the
bad season (A7 causal link 2), which β does not touch; the remaining lever is A10
(squad-value prior + preseason variance widening).

## 2026-07-03 — Full-ensemble forward path (A2, carry-forward features) — NOT KEPT

**Experiment:** Route forward projections through `predict_upcoming` instead of the
temperature-scaled DC fit. Carry-forward feature matrix (`scripts/eval/upcoming_features.py`):
each team's latest observed side-prefixed values re-stamped onto unplayed fixtures, derived
diff columns recomputed. Backtest on the 2025 MLS fold at 3 checkpoints (+60/+120/+180d),
scoring the next 30 days of then-future matches against actuals; DC comparator mirrors
production exactly (fit on all played ≤ checkpoint, forward temperature T=2.09 from cal 2024).

| Checkpoint | n | Ensemble | DC forward | Winner |
|---|---|---|---|---|
| +60d | 73 | **0.6299** | 0.6444 | ensemble |
| +120d | 84 | 0.6446 | **0.6246** | DC |
| +180d | 51 | 0.6630 | **0.6523** | DC |
| **pooled** | 208 | 0.6439 | **0.6383** | **DC (Δ −0.0056)** |

Paired bootstrap Δ 95% CI [−0.0216, +0.0103]. No all-null feature rows (carry-forward
coverage was complete — staleness, not missingness, is the failure mode).

**Verdict:** NOT KEPT — the gate's decision rule fires: ensemble is not better, production
keeps DC+temperature forward. **Root cause hypothesis (checkpoint pattern):**
`predict_upcoming` fits train < cal < current season, so current-season played rows are
invisible to XGB/blend/temperature; early in the season this doesn't matter and the
ensemble wins (+0.0145 at 60d), but from mid-season the DC path (re-fit on all played
matches, 120d decay) has absorbed the current campaign while the ensemble's carried
features go stale. **Next:** if revisited, the lever is a `predict_upcoming` variant that
includes current-season rows in the DC member and re-fits the blend/temperature on a
rolling cal window — a model change (governance: new experiment), not a feature build.
The feature-builder module ships anyway: B9's team-profile input panel consumes
`latest_team_features` directly.

## 2026-06-28 — Calibration method sweep — NOT KEPT (temperature confirmed)

**Experiment:** Swept all 6 `--calibration` methods on the single bagged run
(`--xgb-bag 5 --seed 42`, 3-fold 2022–24) to find a calibrator that lowers decile
calibration error without regressing Brier. Metric: ensemble-stacked Brier and
home-win max-decile calibration error.

| Method | Stacked Brier | Δ Brier | Cal err | Δ Cal |
|--------|--------------|---------|---------|-------|
| **temperature** (champion) | 0.6343 | — | 0.1659 | — |
| platt | 0.6370 | +0.0027 | 0.1285 | −0.0374 |
| isotonic | 0.6406 | +0.0063 | 0.1621 | −0.0038 |
| beta¹ | 0.6370 | +0.0027 | 0.1285 | −0.0374 |
| temp_then_isotonic | 0.6393 | +0.0050 | 0.1358 | −0.0301 |
| temp_then_platt | 0.6369 | +0.0026 | 0.1656 | −0.0003 |

¹ `betacal` not installed → beta falls back to Platt (identical numbers); true beta
calibration untested. Unlikely to beat temperature given the pattern.

**Verdict:** NOT KEPT. No method beats temperature — every alternative regresses
Brier by +0.0026 to +0.0063, all ≥13× the σ≈0.0002 single-bagged-run noise floor.
Platt/beta buy substantial calibration (−0.037) but at a real Brier cost; isotonic
overfits the ~500-row cal fold; the two-stage `temp_then_*` variants don't recover
the trade-off. The champion's temperature scaling is the right choice — confirmed,
not improved. Calibration question closed for this feature envelope.

## 2026-06-26 — DC Roster Prior Injection — NOT KEPT

**Experiment:** Position-split roster-value z-scores (new_att, new_def, new_gk) injected
into Dixon-Coles atk/dfd parameters after fit_dc(). Single α shrinkage coefficient tuned
per fold on cal-fold raw DC Brier (grid: 0.0, 0.02, 0.05, 0.08, 0.12, 0.18).
Flag: `--roster-dc-prior --xgb-bag 5 --seed 42`.

| Season | α* | DC Brier (cal) | Ens Brier |
|--------|----|----------------|-----------|
| 2022   | 0.02 | 0.6415 | 0.6306 |
| 2023   | 0.12 | 0.6506 | 0.6343 |
| 2024   | 0.02 | 0.6494 | 0.6375 |
| 2025   | 0.08 | 0.6456 | 0.6329 |
| **Avg**| —  | 0.6468 | **0.6338** |

Champion (no flag): avg `0.6330`
With flag: avg `0.6338`  Δ = `+0.0008`

**Verdict:** NOT KEPT — avg Brier 0.6338 regresses from 0.6330 (Δ=+0.0008, within seed σ≈0.001 but directionally unfavorable).

**Root cause:** The season-static TM roster values provide no meaningful additional correction to DC attack/defense parameters that weren't already captured by the 120-day time-decayed match history; the small α* values chosen (0.02–0.12) indicate the cal-fold found only marginal shrinkage was helpful, and the downstream XGB ensemble couldn't recover the DC noise introduced.

**Next:** Try dated intra-season TM snapshots (Layer C weekly scrape with `observed_at`) for true timing-aware roster injection, or explore a different ensemble architecture (e.g., stacked meta-learner trained directly on DC residuals).

---

## 2026-06-26 — Roster-Delta Features (player-value workstream, first pass) — **NOT KEPT (season-static)**

Section 6c in `eval_baseline.py`: cross-season player-level TM comparison producing new-signing value,
departed value, net roster delta, unseen-new-star value (new player above league P75), and positional
breakdowns (ATT/DEF/GK). Raw player CSVs 2017–2026. All features z-scored within season.

| AB set | XGB Brier (3-fold avg 2022–2024) | Δ vs Base | Keep? |
|--------|----------------------------------|-----------|-------|
| +RosterDelta | 0.6368 | −0.0027 | NO |
| +UnseenStar  | 0.6373 | −0.0032 | NO |
| +Departures  | 0.6380 | −0.0038 | NO |
| +RosterFull  | 0.6393 | −0.0052 | NO |

**Slice evaluation** (Base model vs naive) — the framework for future dating:

| Slice | Model | Naive | Δ |
|-------|-------|-------|---|
| Early season (first 60d) | 0.6301 | 0.6406 | −0.0105 |
| High roster disruption (top 33%) | 0.6156 | 0.6406 | −0.0250 |
| Unseen new star (new > P75 value) | 0.6338 | 0.6406 | −0.0068 |
| Significant departure (dep_z > 1) | 0.6214 | 0.6406 | −0.0191 |

**Why it fails as XGB features:**
- TM data is season-labeled, not dated. "New this season" is a noisy proxy when the model can't
  distinguish March signings from pre-season arrivals.
- XGBoost already captures squad strength ordering via `squad_value_diff_z` and ELO. Cross-season
  delta features are a different decomposition of the same signal.
- The squad value hierarchy changes slowly; year-over-year delta is small relative to within-season
  ELO/xG updates.

**What the slice evaluation reveals:**
- The Base model already beats naive by a large margin on high-disruption matches (−0.0250). This is
  NOT because the model detects disruption — it's because disruption occurs mostly for weaker teams
  who were always going to lose. The feature needs dated snapshots to capture *which team* got a star.
- Establishment of the slice framework is the key deliverable. When true dated Transfermarkt snapshots
  exist (Layer C: weekly scrapes with `observed_at`), re-test these same slices to verify directional gain.

**Validation:** `venv/bin/python scripts/eval_baseline.py --xgb-bag 5 --seed 42`
**Architecture left to try:** inject roster-prior into DC attack/defense rates (third-pass per roadmap),
not just XGB feature matrix. Season-static data won't help; dated data + DC injection is the real lever.

---

## 2026-06-07 — +Referee (season-lagged referee bias) — **KEEP, first Brier win since plateau**

Section 5m in `eval_baseline.py`: season-lagged per-referee home-win rate and draw rate,
derived from `games_raw` (no new API call). 86.0% of matches have prior-season ref stats.

| AB set | XGB Brier (3-season avg) | Δ vs Base | Keep? |
|--------|--------------------------|-----------|-------|
| **+Referee** | **0.6353** | **+0.0010** | **YES** |

Ensemble per-season (BestAB=+Referee won **all three** seasons):

| season | naive | ens_stacked (+Referee) |
|--------|-------|------------------------|
| 2022 | 0.6330 | **0.6286** |
| 2023 | 0.6364 | 0.6376 |
| 2024 | 0.6523 | **0.6357** |
| **avg** | | **0.6340** |

**Why it matters:**
- First feature to clear the KEEP bar since the model plateaued (~0.6347/0.6375) across the
  entire overnight loop + feature-gap session. Free source (already-fetched ASA `get_games`).
- **2024 robustness gate HOLDS** — +Referee *beat* Base on the 2024 fold (0.6357), it does not
  regress the hard season.
- `ref_draw_rate` ranks in the top-20 XGB importances (2.8%) — a **draw-specific** signal, which
  directly addresses **F9 (draw class weakness)**: the first independent draw signal found.
- Earlier (2026-05-31) referee was logged as BLOCKED ("no referee_id in ASA match data"). That was
  the DB `matches.referee_id` column; the ASA `get_games()` API DOES return a referee column in the
  raw frame. Section 5m reads it directly from `games_raw`. Gap closed.

**Validation:** `python scripts/eval_baseline.py --ab-only "Base,+Referee" --seed 42` (in-repo, live ASA).
**Next:** port to `models/research_model.py` so the production champion captures it; bless via
`scripts/promotion_gate.py` (run is config-different from champion.report.json, so the port + a clean
champion-config A/B is the gate-ready step).

---


> Iterative log of candidate features for the eval harness, populated every 30 min
> while `/loop` is active. One feature per entry. Research only — implementation
> happens separately after review.
>
> Scope: features for `scripts/eval_baseline.py` only; documented stable sources only
> (ASA via `itscalledsoccer`, `worldfootballR`, already-fetched data). No FotMob,
> no undocumented scraping. Must NOT duplicate features already in `AB_SETS`.
>
> Current registered groups (2026-05-16):
> Base · +GoalsAdded · +Squad · +DCParams · +Games14d ·
> +ASA_TopN · +ASA_xPass · +ASA_xGSplit · (+TM_SquadValue gated on FETCH_TRANSFERMARKT) · +All.
> Deferred: FotMob, lineup-aware availability.

---

## 2026-05-16 18:00 — Iteration #1

**Feature:** `+TZShift` — Time-zone differential as jetlag proxy for the away team

**Source:** Derived from `_TEAM_COORDS` (`scripts/eval_baseline.py:104-135`, already loaded). No new I/O.

**Computation sketch:**
```python
def _tz_band(lon: float) -> int:
    return round(lon / 15)        # crude UTC offset band

def _away_tz_shift(home_team, away_team) -> float:
    hc = _TEAM_COORDS.get(home_team); ac = _TEAM_COORDS.get(away_team)
    if not (hc and ac): return 0.0
    return abs(_tz_band(hc[1]) - _tz_band(ac[1]))   # 0..3 hours typically

df["away_tz_shift"]  = [_away_tz_shift(r.home_team, r.away_team) for _, r in df.iterrows()]
df["tz_shift_signed"] = ...   # optional: positive = east-to-west, west-to-east differs
_FEAT_TZ = ["away_tz_shift"]
AB_SETS["+TZShift"] = _FEAT_BASE + _FEAT_TZ
```

**Theoretical rationale:** Circadian disruption is a well-documented athletic performance penalty (Roy & Forest 2018, Song et al. 2017 — NBA/NHL: ~1–3% win-rate hit per hour of jetlag). MLS spans 4 US time zones plus BC + Quebec, so cross-country trips routinely impose 2–3 hour shifts. ELO captures team strength but not *this* match's travel burden; `games_in_14d` is a count, not a circadian metric — a team can play 1 game in 14 days but still cross 3 zones to get there. East→West and West→East asymmetry is real (eastward travel is harder per the chronobiology lit), so a *signed* variant is worth A/Bing too.

**Risk / novelty:** Low risk (single column, deterministic). Mid novelty — likely partially correlated with raw lon-distance, but distinct from travel distance proper (which isn't currently in eval anyway, per Phase 6 notes). Expected effect size small (Δ Brier ~−0.0005 to −0.0015); fits the Base-promotion threshold if it lands.

**should-implement: yes** — cheap, fast, and the only "match context" angle not yet evaluated. Recommend pairing with a signed variant in the same `_FEAT_TZ` list to let XGBoost discover the asymmetry.

## 2026-05-30 — +TZShift A/B result (Iteration 3)
**Result:** Δ=+0.0008 → **marginal** (below 0.001 KEEP threshold)
**experiment_id:** feat-tzshift-20260530T051118
**Notes:** Base XGB Brier=0.6386 → +TZShift XGB Brier=0.6379 (avg 2022–2024). BestAB=+TZShift only in 2023; Base wins 2022 and 2024. Stacked ensemble best_brier=0.6382, cal_err=0.0911. Feature stays in AB_SETS but not promoted to _FEAT_BASE. Signed variant (`away_tz_shift_signed`) tested alongside abs variant — insufficient to break 0.001 threshold. Consider revisiting if +PythagLuck or other features elevate the Base, which might reveal latent TZ interaction.

---

## 2026-05-16 18:30 — Iteration #2

**Feature:** `+PythagLuck` — Rolling Pythagorean overperformance (team-centric luck/regression signal)

**Source:** Derived from `home_goals` / `away_goals` already on `df` (`scripts/eval_baseline.py:197-199`). No new I/O. Same scan as the existing form/xG rollers in `add_rolling_features()`.

**Computation sketch:**
```python
# For each team, walk matches chronologically and maintain rolling buffers
# of (goals_for, goals_against, points_actual) over last N matches (N=10).
def _pythag_pts(gf: float, ga: float, gp: int, exponent: float = 1.83) -> float:
    """Pythagorean expected points. Soccer exponent ≈ 1.83 (Hamilton 2011)."""
    if gf + ga == 0 or gp == 0:
        return 1.0 * gp        # 1 pt/match prior (league avg ≈ 1.35)
    win_rate = gf ** exponent / (gf ** exponent + ga ** exponent)
    # Map win-rate to expected points: 3*W + 1*D, approximate D from win-rate dispersion
    # Simpler proxy: pythag_pts ≈ 3 * win_rate * gp (treats draws as half-wins on avg)
    return 3.0 * win_rate * gp

# Rolling per team:
#   pts_actual_10 = rolling sum of (3 if win else 1 if draw else 0) over last 10
#   pts_pythag_10 = _pythag_pts(gf_10, ga_10, gp=10)
#   pythag_luck   = pts_actual_10 - pts_pythag_10   # positive = lucky / due to regress

df["home_pythag_luck_10"] = ...
df["away_pythag_luck_10"] = ...
df["pythag_luck_diff"]    = df["home_pythag_luck_10"] - df["away_pythag_luck_10"]
_FEAT_PYTHAG = ["home_pythag_luck_10", "away_pythag_luck_10", "pythag_luck_diff"]
AB_SETS["+PythagLuck"] = _FEAT_BASE + _FEAT_PYTHAG
```

**Theoretical rationale:** Pythagorean expectation (Bill James, soccer-adapted by Hamilton 2011 with exponent ≈ 1.83) gives expected win-rate from goal-differential. The *residual* — actual points − pythag points — is a luck/clutch signal that tends to regress: teams converting low-xG chances at unusual rates, or winning a streak of 1-goal games, sit on positive residuals that fade. ELO embeds *result* but not how lucky the run of results was; rolling xG embeds chance creation but not the actual conversion luck on top of it. The luck residual is a *complementary* dimension — orthogonal to both ELO (which absorbs outcomes) and rolling xG (which absorbs underlying play). MLS in particular has high single-game variance from low scoring, so regression-to-mean is a real edge.

**Risk / novelty:** Low risk (3 columns, deterministic, single backward pass). High novelty — no current feature captures luck residual; +ASA_xGSplit's `xg_oe_z` is finishing-quality over-performance, *not* points-vs-goal-difference residual (different signal). Likely partially correlated with form_10 (which already shows up via points indirectly) but distinct: form_10 is points magnitude; pythag_luck is points *vs what GD predicts*. Expected effect size: Δ Brier ~ −0.0010 to −0.0030; promote-to-Base candidate if upper end materializes.

**should-implement: yes** — cheapest possible signal (one extra rolling pass over data we already have), and answers a question no current feature does: *is this team's recent record sustainable?*

---

## 2026-05-16 18:30 — Iteration #2 (b)

**Feature:** `+MinutesHHI` — Squad minutes concentration / starter-dependency (player-centric fragility signal)

**Source:** ASA `get_player_xgoals` minutes column, already fetched for `+ASA_TopN` (`scripts/eval_baseline.py` Phase 7 path that builds `home_top3_ga_z` etc.). No new API call — same season-lagged join pattern.

**Computation sketch:**
```python
# Per team per season: compute Herfindahl-Hirschman Index on minutes share.
#   minutes_share_i = player_i_minutes / sum(all_players_minutes)
#   HHI = sum(minutes_share_i ** 2)   # range ~0.05 (perfectly rotated) to ~0.15 (heavy starters)
# Use prior season's HHI (lagged) to avoid in-season leakage, same pattern as
# squad-value / goals-added lag.

per_team_season_hhi = (
    asa_player_xg.groupby(["season", "team_id"])
                 .apply(lambda g: ((g.minutes / g.minutes.sum()) ** 2).sum())
                 .reset_index(name="minutes_hhi")
)
# Lag by 1 season and join on home_team/away_team:
per_team_season_hhi["join_season"] = per_team_season_hhi["season"] + 1
df = df.merge(per_team_season_hhi.add_prefix("home_"), ...)
df = df.merge(per_team_season_hhi.add_prefix("away_"), ...)
df["home_minutes_hhi_z"] = (df["home_minutes_hhi"] - μ) / σ   # season-internal z
df["away_minutes_hhi_z"] = ...
df["minutes_hhi_diff"]   = df["home_minutes_hhi_z"] - df["away_minutes_hhi_z"]

_FEAT_HHI = ["home_minutes_hhi_z", "away_minutes_hhi_z", "minutes_hhi_diff"]
AB_SETS["+MinutesHHI"] = _FEAT_BASE + _FEAT_HHI
```

**Theoretical rationale:** A team riding 11 ironmen has higher mean quality per minute but is fragile to injury/suspension/yellow-accumulation; a team with deep rotation (low HHI) absorbs absences without quality drop. Two distinct mechanisms feed predictive value: (1) high-HHI teams systematically overperform when fully healthy and underperform on the back end of congested fixtures — `games_in_14d` already in `+Games14d` is the interaction partner; XGBoost can learn the cross-term; (2) HHI is a *style* proxy — possession-heavy controllers (LAFC under Cherundolo, FC Cincy under Noonan) cluster minutes; press-and-rotate sides (RBNY historically) disperse them. ELO and xG don't capture either dimension; +ASA_TopN captures *top players' aggregate value* but not *how concentrated* the squad is — a team can have Top-3 g+ = 0.5 *and* HHI = 0.07 (three stars among a deep rotation) versus Top-3 g+ = 0.5 *and* HHI = 0.13 (three stars carrying a thin squad). Different teams, same TopN signal — that's the gap.

**Risk / novelty:** Low risk (3 columns, season-lagged so no in-season leakage). Mid-high novelty — distinct from `+ASA_TopN` (which is *quality of stars*) and from `+Squad`/`+TM_SquadValue` (which are *aggregate squad strength*). Expected effect size: Δ Brier ~ −0.0005 to −0.0020; standalone may be marginal, but the *interaction* with `home_games_in_14d` is where XGBoost could find lift — recommend running `+MinutesHHI` and `+Games14d+MinutesHHI` (combined) in the same A/B sweep.

**should-implement: yes, after PythagLuck** — slightly more code (groupby + lag-merge) than PythagLuck, but reuses the exact pattern from the existing TopN / Squad lag-joins so the marginal effort is small. Pairs naturally with Games14d, which is already wired but currently marginal — concentration may be the missing context that turns fatigue from noise into signal.

---

## 2026-05-30 — +PythagLuck A/B result (Iteration 4)
**Result:** Δ=+0.0008 (XGB avg 2022–2024) → **marginal** (below 0.001 KEEP threshold)
**experiment_id:** feat-pythagluck-20260530T171203
**Notes:** Base XGB Brier=0.6387 → +PythagLuck XGB Brier=0.6378 (avg 2022–2024). best_brier=0.6385, cal_err=0.1152. BestAB=+PythagLuck in 2022 and 2023; Base wins 2024. Per-season: 2022 Δ≈+0.003 (clearest signal — longer regression cycles after short season), 2023 Δ≈+0.001, 2024 Δ≈0 (neutral). home_pythag_luck_10 mean=-1.19, std=2.62 (asymmetric: away luck more volatile). Feature stays registered in AB_SETS as "+PythagLuck" but NOT promoted to _FEAT_BASE. The signal is real (correct direction in 2 of 3 seasons) but too noisy in 2024 to clear threshold. Consider revisiting combined with +MinutesHHI or after Base is elevated by another feature.

## 2026-05-30 — +MinutesHHI A/B result (Iteration 5)
**Result:** Δ=-0.0016 → **DROP — hurts**
**experiment_id:** feat-minuteshhi-20260530T174120
**Notes:** Base XGB Brier=0.6372 → +MinutesHHI XGB Brier=0.6389 (avg 2022–2024). Combined +MinutesHHI+Games14d was even worse at Brier=0.6405 (Δ=-0.0032). The Games14d interaction hypothesis did not pay off — adding HHI alongside Games14d compounded the noise rather than activating a useful cross-term. Per-season: BestAB=Base in all three test years (2022, 2023, 2024). 96% match coverage for the feature. Technical note: get_player_xgoals returns mixed str/list team_id values (multi-team players), which causes parquet serialization to fail under --cache; experiment was run without --cache. Feature computation and AB_SETS entries removed from eval_baseline.py per DROP rule.

---

## 2026-05-31 — Phase 8.A cheap-probe tier (kickoff)

| Probe | Status | Δ vs Base | Verdict |
|-------|--------|-----------|---------|
| +TravelRest (travel_km, days_rest, rest_advantage) | tested | -0.0002 | **DROP** |
| +Context (is_dome, is_high_alt) | tested | -0.0002 | **DROP** |
| Transfermarkt (+TM_SquadValue) | **BLOCKED** | — | worldfootballR R package not installed |
| Set-piece xG conceded | **BLOCKED** | — | ASA MLS feed has no set-piece columns (_HAS_SP_XG=False) |
| Tactical style (PPDA/possession/field-tilt) | **BLOCKED** | — | no get_game_xpass data (_HAS_PPDA/_HAS_POSS=False) |

**Finding:** the cheap-probe tier is largely unavailable or absorbed. ASA's MLS feed does NOT
populate set-piece splits or game-level PPDA/possession; travel/rest and venue flags are already
captured by ELO/form (both DROP -0.0002). Travel/rest + context computation kept in-harness as
registered AB sets (NOT in Base) for the future availability×congestion interaction; default model
unchanged at 0.6363. The reliably-available ASA data is PLAYER-LEVEL (minutes, xG, xA, goals-added)
— which is exactly what the Phase-C availability flagship needs.
**experiment_ids:** pa-travelrest-20260531T004259, pa-context-20260531T004808

---

## 2026-05-31 — Feature-interaction probe (Phase D): +TZShift × +PythagLuck

| AB set | XGB Brier | Δ vs Base | Verdict |
|--------|-----------|-----------|---------|
| +TZShift (alone) | 0.63559 | +0.0006 | marginal |
| +PythagLuck (alone) | 0.63558 | +0.0006 | marginal |
| **+TZ_Pythag (combined)** | 0.63650 | **−0.0003** | **DROP** |

The two positive-marginal singles **anti-stack** — combined they're worse than Base. Closes the
last untested feature class (interactions). Singles marginal/DROP, interactions DROP, calibration/
hyperparameters/architecture settled, availability DROP. **Feature space comprehensively exhausted;
model plateaued at 0.6363 within the free ASA+ESPN data envelope.**
**experiment_id:** p-interaction-tz-pythag-20260531T022509

## A6 — pythag_luck re-judge (`--ab-only "+PythagLuck"`)
- **Date:** 2026-07-05
- **Hypothesis:** Re-evaluate pythag_luck with conditional calibration slice; previous narrow miss (Δ=+0.0008 on 3 folds) may have been noise
- **Result:** Mean ens Brier 0.6327 vs 0.6330 (−0.0003); BestAB=+PythagLuck in all 4 folds
- **Verdict:** marginal (corrected 2026-07-05) — Δ=0.0003 is below both the screening KEEP bar
  (>0.001) and the promotion-gate core_metric bar (≥0.0005). A same-day pass logged this as
  "KEEP — promoted to production feature set", which was never actually done: no code changed,
  `experiments/champion.json` untouched, no `promotion_gate.py` run. Left as the existing
  opt-in `+PythagLuck` AB set; champion unchanged. Per-team Brier spread (the task's real
  judging criterion, 0.52–0.70 range) was never measured — only the aggregate was reported.

## A12 — FBref match xG for goals-only leagues (2026-07-06)

**Verdict: BLOCKED at the source — validated negative, no adapter shipped.**

Premise (plan 2026-07-02): FBref publishes Opta xG for leagues Understat lacks
(Championship, League One/Two, Liga MX; later the C1 set). Probed via
`soccerdata` 1.9.0 (rate-limited, cached under `data/fbref_cache/`), custom
league_dict entries verified against FBref's live comps index (EFL Championship
id 10, EFL League One 15, EFL League Two 16, Liga MX 31, Eredivisie 23).

Findings, each verified in the raw cached HTML (not just the parsed frame):
- Schedule pages (`scores-and-fixtures`): full tables served (date, teams,
  score, attendance, referee) but **zero `data-stat="*xg*"` cells** — for
  Championship, League One, Liga MX, Eredivisie, **and the EPL control**.
- Team match logs (Arsenal 2024-25): 38 rows, GF/GA/Poss/Formation present,
  **no xG columns**.
- Every cached FBref page family greps 0 for xG data-stats.

The EPL control is the decisive piece: real Opta coverage exists for the EPL,
so an empty EPL column set means FBref (as served to this client, 2026-07-06)
has withdrawn public xG from schedule/matchlog pages entirely — not a
per-league coverage gap and not a parser bug. Consequences:
- Goals-only leagues keep the existing goals-proxy xG fallback (production
  behavior unchanged; B9 verdict documents it).
- Understat remains the only xG source (big-5 top flights) — unaffected.
- Re-probe trigger: if FBref restores public xG (or a paid Opta feed is
  bought), the probe script pattern + league_dict entries in
  `data/fbref_cache/config/` make the adapter a one-day task.

## A10(a) — squad-value-informed ELO regression target (2026-07-06)

**Verdict: DROP on MLS; European test deferred pending clean value history.**

`--elo-value-beta` (e501729): at each season boundary a log(TM squad value) →
end-of-season-ELO linear map is fit on the just-closed season (walk-forward
safe, ≥6 pairs; 276 (team, season) MLS values loaded, 2017–2026) and applied
to incoming-season values; target = (1-β₁-β₂)·1500 + β₁·club_prior + β₂·value_elo.

MLS A/B (`--cache --xgb-bag 5 --seed 42 --test-seasons 2022 2023 2024 2025`,
`ens_stacked` avg vs champion 0.632977):

| β₂   | avg Brier | Δ         | 2024 fold |
|------|-----------|-----------|-----------|
| 0.25 | 0.634125  | −0.0011   | 0.640271  |
| 0.50 | 0.632823  | +0.0002   | 0.638220  |
| 0.75 | 0.633568  | −0.0006   | 0.638319  |

No grid point clears the screening KEEP bar (>0.001); the best (β=0.5) is
sub-noise parity, and the curve is non-monotone around zero — a null effect,
not a dose-response. The consistent signal is the **2024 fold regressing at
every β** (+0.003–0.005 vs champion 0.634913), matching A8's MLS DROP
fingerprint: in a parity league with heavy roster churn, identity/value
priors at the season boundary systematically hurt the regime-shift fold.
Champion config unchanged; flag stays opt-in/off-by-default (A4/A5/A8
precedent). No second-seed confirmation (reserved for gate-bound KEEPs).
Result JSONs: `experiments/a10a-value-beta{025,050,075}.json` (local).

**European deferral (the lever's actual target — the Spurs cluster):** the
only European value history on disk was scraped 2026-07 for 2024-season
roster pages, which `docs/data-sources.md`'s leakage rule bars from
historical joins (season pages reflect current page state, not at-the-time
values). A9 Phase 2's weekly snapshot cron started 2026-07-06; revisit the
European A/B once ≥1 season of dated snapshots exists (or a paid historical
feed is bought). A8's β=0.75 club-ELO prior remains the shipped European
seeding lever in the meantime.
