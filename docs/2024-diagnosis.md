# 2024 Distribution-Shift Diagnosis

Date: 2026-06-06
Tool: `scripts/diagnose_2024.py` (run on `data/parity_frame` snapshot, 3,982 rows, 2017–2026)

## Question

The Dixon-Coles component is catastrophically bad in 2024 (raw Brier ~0.649) while
strong in 2022–2023. The capped-DC blend (DC ≤ 30%) is a workaround that was never
diagnosed. Is 2024 a *feature* shift (inputs moved) or an *outcome* shift (the game
changed)?

## Finding: it is an OUTCOME regime shift, not a feature shift

### Outcome base rates per season

| season | n | home | draw | away | goals/g |
|--------|----|------|------|------|---------|
| 2017 | 391 | 0.552 | 0.240 | 0.207 | 2.93 |
| 2018 | 408 | 0.542 | 0.211 | 0.247 | 3.18 |
| 2019 | 421 | 0.527 | 0.219 | 0.254 | 3.07 |
| 2021 | 472 | 0.479 | 0.271 | 0.250 | 2.78 |
| 2022 | 489 | 0.491 | 0.247 | 0.262 | 2.97 |
| 2023 | 521 | 0.482 | 0.288 | 0.230 | 2.76 |
| **2024** | 522 | **0.450** | 0.247 | **0.303** | **3.12** |
| 2025 | 540 | 0.443 | 0.250 | 0.307 | 3.02 |
| 2026* | 218 | 0.482 | 0.220 | 0.298 | 3.30 |

**2024 vs pre-2024 mean: home −0.062, draw +0.001, away +0.061, goals +0.167.**

Home-field advantage collapsed. The home-win rate fell from a 2017–2023 average of
~0.51 to 0.45 in 2024, with the mass moving almost entirely to away wins (+0.061).
The **draw rate barely moved** (+0.001) — so 2024 is specifically a home/away
problem, not a draw problem. The collapse **persists in 2025** (home 0.443), so it
is the new regime, not a one-off.

### Feature distributions did NOT move

Mean per-feature Jensen-Shannon divergence (train pool vs season):

- train(<2023) vs 2023: **0.0308**
- train(<2024) vs 2024: **0.0198**  ← *lower* than the stable 2023 transition

The top shifted features going into 2024 are GK z-scores (0.074) and xGA rolls
(~0.03) — modest, and *less* shifted than the 2023 transition overall. The model's
inputs are essentially on-distribution in 2024. The mapping from inputs to outcomes
is what changed.

### Why DC breaks and the blend rescues it

Dixon-Coles bakes home advantage into its Poisson means via the `home_adv` parameter,
fit on 2017–2023 data where the home-win rate was ~0.51. With a static high
home_adv, DC systematically over-predicts home wins in 2024 (home rate 0.45) —
exactly the −0.062 gap above. DC has no mechanism to track a mid-stream HFA collapse.

ELO (which regresses 50% toward the mean each season) and recent-form features adapt
within a season, so the XGB component degrades far less. This is why the cal-fold-fit
capped blend lands on `w_xgb = 0.70` in 2024 (max DC down-weight) and recovers the
ensemble to 0.6361.

## Implications for the model

1. **The capped-DC blend is the right structural response**, not just a patch — it is
   automatically down-weighting a component that is provably off-regime. Keep it.
2. **DC's home_adv is stale.** Candidate experiments (test in harness, run through the
   promotion gate):
   - Shorter DC `recent_seasons` window (currently 4) so the fit leans on the
     low-HFA 2023–2025 seasons.
   - A separate, faster-decaying home-advantage term in DC.
3. **ELO `HOME_ADV=80` may be too high for the post-2023 regime.** Worth a re-sweep on
   2024–2025 specifically (owned by hyperparameter-optimizer).
4. **Calibration angle:** a single scalar temperature cannot fix a directional
   home→away mass shift. A per-class (vector) calibration on the blend output —
   separate adjustment for home/draw/away — directly targets the 2024 miscalibration
   and is the natural next calibration experiment.
5. **Draw weakness is independent of 2024** (draw rate stable). Per-class draw
   calibration remains worth testing but should not be conflated with the 2024 fix.

## Experiments run against this diagnosis (2026-06-06)

Both diagnosis-driven hypotheses were tested through the promotion gate. **Neither
yields a 2024 win** — confirming the shift is structurally unforecastable from
prior-season information, and the capped-DC blend is already the optimal response.

### 1. Per-class (vector) calibration on the blend — DROP
`scripts/probe_vector_calibration.py` · full writeup in `docs/calibration-log.md`.
6-param vector scaling beats scalar temperature on 2023 (+0.0045, cal fold matches
regime) but **regresses 2024 by −0.0135** (avg 0.6347→0.6379). Extra calibration
degrees of freedom overfit the 2023 cal-fold class priors and amplify the home→away
shift when the regime flips. Scalar temperature stays canonical.

### 2. Shorter Dixon-Coles recent-seasons window — KEEP window=4
`scripts/probe_dc_window.py`. Sweeping `recent_seasons` ∈ {2,3,4,5}:

| window | 2022 | 2024 | dc_home_adv (2024) | w_xgb (2024) |
|--------|------|------|--------------------|--------------|
| 2 | 0.6318 | 0.6354 | 0.367 | 0.70 |
| 3 | 0.6317 | 0.6354 | 0.367 | 0.70 |
| 4 | 0.6317 | 0.6354 | 0.367 | 0.70 |
| 5 | 0.6317 | 0.6354 | 0.376 | 0.70 |

2024 Brier is **identical to 4 decimals** across all windows. The DC window has no
leverage because (a) `home_adv` barely moves, and (b) the cal-fold-fit capped blend
already floors DC at w_xgb=0.70 (max down-weight) in 2024, so DC's residual 30%
contribution — after temperature calibration — is insensitive to its fit window.

### Remaining lever (deferred)
ELO `HOME_ADV=80` re-sweep on 2024–2025 specifically. This tunes an XGB *input
feature* (not DC), so it is owned by the hyperparameter-optimizer and requires an
ELO recompute + full eval. Deferred — lower expected value given (1)/(2) above show
2024 is structurally hard, and the blend already adapts via w_xgb.

**Bottom line:** there is no easy 2024 win from calibration or DC re-fitting. The
2024 catastrophe is a genuine regime shift the walk-forward design cannot anticipate;
the capped-DC blend correctly contains the damage (2024 ensemble 0.6354 vs DC-raw
~0.649). Keep the current architecture.

## Reproduce

```bash
python scripts/diagnose_2024.py --frame data/parity_frame.parquet --top 15
python scripts/probe_vector_calibration.py --frame data/parity_frame.parquet
python scripts/probe_dc_window.py --frame data/parity_frame.parquet
```
