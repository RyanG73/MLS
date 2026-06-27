# DC Roster Prior Injection — Design Spec
_Date: 2026-06-26_

## Context

Section 4 of the Codex review (Brier Score and Player-Value Modeling) prescribed a three-pass roadmap for incorporating player market value into the model. The first pass (season-static TM features as XGB inputs) was completed 2026-06-26 and did not keep — all four roster-delta AB sets regressed Brier by −0.0027 to −0.0052 vs Base. Root cause: XGBoost already captures team strength via ELO, rolling xG, and `squad_value_diff_z`; season-static roster change data adds noise on top of correlated signals.

This spec covers the **third pass**: inject roster-value priors directly into Dixon-Coles attack/defense rate parameters, bypassing XGB entirely. This is architecturally different from feature engineering — DC rates lag because they require played match history to update; roster injection corrects that lag at the source.

## Goal

After fitting DC on historical match data, apply a position-aware roster-value adjustment to `atk` and `dfd` parameters before any prediction runs. The hypothesis: a team that signed a high-value striker has a higher true attack rate than DC's historical estimate; a team that signed a high-value GK/CB has a lower true defense-concession rate.

## DC Parameter Semantics

```
λ_home = exp(atk[home] + dfd[away] + ha)   ← expected home goals scored
μ_away = exp(atk[away] + dfd[home])         ← expected away goals scored
```

- `atk[team]` — attack strength (log-scale). Higher = more goals scored.
- `dfd[team]` — defense vulnerability (log-scale). Higher = more goals **allowed** against this team.
- `ha` — home advantage offset.
- `rho` — Dixon-Coles low-score correlation.

## Injection Formula

After `fit_dc(train_raw)` returns `(atk, dfd, ha, rho)`:

```
atk_adj[team] = atk[team]  +  clip(α * new_att_value_z[team, season],  −0.25, +0.25)
dfd_adj[team] = dfd[team]  −  clip(α * (new_def_value_z + new_gk_value_z)[team, season],  −0.25, +0.25)
```

**Sign rationale:**
- New attacker → push attack rate **up** → positive `atk` shift.
- New GK/CB → push defense vulnerability **down** → negative `dfd` shift (fewer goals allowed).

**Cap at ±0.25 (log-space):** corresponds to ≈±28% change in expected goals. Prevents extreme adjustments for teams with outlier z-scores.

**Single shared `α`:** Both `atk` and `dfd` use the same shrinkage coefficient. Reduces tuning surface; can split later if evidence warrants.

**Departures:** Not adjusted in this pass. DC's time-decay weighting naturally reduces the influence of matches played by a now-departed player. Position-split departure adjustment is a candidate follow-up.

## α Calibration

Per fold, after `fit_dc()`:

1. Grid search `α ∈ {0.0, 0.02, 0.05, 0.08, 0.12, 0.18}`.
2. For each candidate `α`: apply injection → compute raw DC Brier on the cal fold.
3. Select `α*` that minimises cal-fold Brier.
4. Apply `α*` to produce `atk_adj, dfd_adj` used for all test-season predictions.
5. Temperature scaling runs after, as today, on the adjusted DC predictions.

Raw (uncalibrated) Brier is used for tuning to keep the loop cheap and avoid overfitting the cal-fold temperature.

## Data Source

The roster-delta z-scores (`new_att_value_z`, `new_def_value_z`, `new_gk_value_z`) were computed in Section 6c (first-pass implementation, 2026-06-26) and stored in `_rd_z: dict[tuple[str, int], dict]`, keyed by `(short_code, season)`. These are available in the harness when `_HAS_ROSTER_DELTA` is True.

Lookup falls back one season (`season − 1`) if no current-season entry exists, preserving partial coverage.

## Code Structure

### New function: `apply_roster_dc_prior()` in `scripts/eval/dixon_coles.py`

```python
def apply_roster_dc_prior(
    atk: dict[str, float],
    dfd: dict[str, float],
    season: int,
    rd_z: dict[tuple, dict],
    hex_to_short: dict[str, str],
    alpha: float,
    max_adj: float = 0.25,
) -> tuple[dict[str, float], dict[str, float]]:
```

- Iterates over `atk.keys()` (all fitted teams).
- Looks up `(short_code, season)` in `rd_z`, falls back to `(short_code, season − 1)`.
- Applies capped adjustment to `atk` and `dfd` copies (does not mutate in-place).
- Returns `(atk_adj, dfd_adj)`.

### Integration point in `eval_baseline.py`

New `--roster-dc-prior` CLI flag (default off). When active and `_HAS_ROSTER_DELTA`:

```
# After fit_dc, before any dc_predict_batch calls:
alpha_star = _tune_dc_prior_alpha(cal_raw, y_cal_oh, atk, dfd, ha, rho,
                                   test_season, _rd_z, _hex_to_short)
atk, dfd = apply_roster_dc_prior(atk, dfd, test_season, _rd_z,
                                  _hex_to_short, alpha_star)
# Then dc_predict_batch runs as today on adjusted atk/dfd.
```

The tuning helper is a small inline function (not exported) that runs the α grid loop.

### Reporting additions

- Per-season table gains a `dc_prior_alpha` column showing the tuned `α*` for that fold.
- If `--roster-dc-prior` is active, prints raw DC Brier before and after adjustment for each fold so the effect is directly observable.

## Success Criterion

Keep if the 4-fold mean Brier improves vs Base by any amount (≥0.0000) on the AB report. The threshold is intentionally low given that season-static data has limited signal. Gate-reject if Brier regresses.

## Out of Scope

- Position-split departure adjustment (follow-up if this passes).
- Porting to `models/research_model.py` (happens only after harness validation).
- Weekly TM snapshot infrastructure (separate workstream — Layer C dated data).
- Dashboard changes (third-pass dashboard work per codex roadmap deferred until harness validates).
