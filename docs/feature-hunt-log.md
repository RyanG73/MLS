# MLS Feature Hunt Log

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
