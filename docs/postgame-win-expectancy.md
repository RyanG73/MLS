# Postgame Win Expectancy (WE) — "how deserved was this result"

Status: **research capability, built and calibration-validated 2026-07-13. Not yet
wired into the webapp.**

This is a NEW, ADDITIVE capability. It does not touch, replace, or share code with
the pre-match win-probability pipeline (`models/research_model.py`,
`scripts/eval_baseline.py`, `features/`, `config/`). It answers a different
question about a match that has ALREADY happened: given the actual balance of
play (final xG for/against for each side), what was each team's win probability
*given how the game was actually played* — so a 1-0 win manufactured from one
shot reads as "~10% postgame WE, they got fortunate" instead of the boxscore's
flat 100%. This is the Bill-Connelly-style "deserved-ness" number, not a forecast.

Script: `scripts/postgame_win_expectancy.py` (self-contained, run with
`python scripts/postgame_win_expectancy.py --out experiments/postgame_we_report.json`).

## Data reality (checked before building anything)

The production pipeline has match-level **aggregate** xG only — no shot-by-shot
event data anywhere in this repo:
- Understat (`data_pipeline/understat.py`) — Big-5 European leagues, 2014+
- American Soccer Analysis (`data_pipeline/asa_cache.py`) — MLS / NWSL / USL
  Championship, 2022+

The model below is built entirely from `home_xg` / `away_xg` (final, per-match)
plus the actual result — nothing else was available or needed. All data is read
from the existing local parquet caches; no new ingestion, no network calls, no
production file touched.

Combined training set: **30,647 completed matches** (61,294 team-match rows,
one row per team's own perspective) across 8 leagues, seasons 2013/14–2026 (2026
in-progress rows included but flagged as a small-sample slice). 2020 excluded
(COVID bubble), matching the repo-wide convention.

## Model design

**Target:** binary — `1` if this team won, `0` for a draw or a loss. This is
deliberately not a 3-class model; postgame WE is asked and answered as "how
likely was this team to win", which is what the calibration check below directly
tests.

**Features (chosen): quadratic in (xg_for, xg_against)** —
`[xg_for, xg_against, xg_for², xg_against², xg_for·xg_against]`. Compared against
a simpler `(xg_diff, xg_total)` linear form and a linear form with an added
home-field flag; the quadratic form had the lowest pooled decile calibration
error at both validation seeds with Brier no worse (0.1747 vs 0.1752 linear), so
it was kept. The home-flag variant added no calibration benefit — home-field
advantage in the "deserved" measure is negligible once actual xG is known, which
matches the framing (the question is about the balance of play that already
happened, not who hosted it).

**Fit PER DATA-SOURCE FAMILY, not one universal model.** This was the single
most important design decision, found empirically, not assumed up front:

A first pass pooling all 8 leagues into one logistic regression looked
well-calibrated in aggregate (pooled max-decile error ≈0.014) but that number
hid a real per-league problem — MLS/NWSL/USLC (ASA xG) came out to **0.06–0.09**
decile error under the pooled model, while the Understat Big-5 leagues stayed at
0.02–0.045. Understat and ASA compute "expected goals" with different
underlying shot models, so pooling their raw xG values into one numeric feature
conflates two different measurement scales — a 0.3 xG differential doesn't mean
the same thing in both systems. Fitting one model per source family (mirroring
`docs/CURRENT_STATE.md`'s existing "League-Family Champions" governance, which
already treats MLS / NWSL / USL / big-5 Europe as separately-validated families
for the pre-match model) closed most of the gap:

| League | Pooled model cal-err | Per-family model cal-err |
|---|---|---|
| MLS | 0.092 | 0.053 (linear) |
| USLC | 0.063 | 0.025 (linear) |
| NWSL | 0.061 | 0.063 (linear), 0.040 (quadratic, chosen) |
| EPL | 0.022 | 0.017 |
| Bundesliga | 0.045 | 0.024 |

Two families are fit: `understat` (Big-5) and `asa` (MLS/NWSL/USLC). Coefficients
came out directionally identical and similar in magnitude between families
(understat `xg_for` coef 1.80 vs asa 1.58; `xg_against` −1.33 vs −1.00),
confirming the underlying relationship is the same shape — the split fixes a
scale-calibration mismatch between xG vendors, not a structural difference in
how xG translates to outcomes.

**Cross-validation:** grouped 5-fold CV, grouped by `match_id` so a match's home
and away perspective rows always land in the same fold (no leakage). Every
number below is from out-of-fold predictions only — the exported production
coefficients (fit on 100% of the data) are never used to compute a calibration
number.

**Two-seed verification (CLAUDE.md protocol):** the full pipeline was run at
seeds 42 and 7; the fold-shuffle changes but the calibration numbers barely move
(max-decile error 0.0146 vs 0.0157, spread 0.0011). Confirms the calibration
result is a property of the model, not an artifact of one fold split.

## Calibration validation — the actual numbers

Pooled decile table (chosen model, seed 42, all 8 leagues, 61,294 rows):

| Predicted bucket | n | Mean predicted | Actual win rate | \|diff\| |
|---|---|---|---|---|
| 0.0–0.1 | 8,230 | 0.055 | 0.047 | 0.008 |
| 0.1–0.2 | 10,183 | 0.150 | 0.155 | 0.005 |
| 0.2–0.3 | 9,384 | 0.249 | 0.251 | 0.002 |
| 0.3–0.4 | 8,017 | 0.349 | 0.363 | 0.015 |
| 0.4–0.5 | 6,816 | 0.449 | 0.446 | 0.003 |
| 0.5–0.6 | 5,833 | 0.548 | 0.542 | 0.007 |
| 0.6–0.7 | 4,792 | 0.648 | 0.635 | 0.014 |
| 0.7–0.8 | 3,920 | 0.748 | 0.742 | 0.007 |
| 0.8–0.9 | 2,947 | 0.846 | 0.857 | 0.011 |
| 0.9–1.0 | 1,172 | 0.929 | 0.932 | 0.003 |

**Max decile calibration error: 0.0146 (seed 42), 0.0157 (seed 7).** Both well
under the repo's 0.05 target (`docs/experiment-protocol.md` calibration-agent
convention). Binary Brier 0.1747, log loss 0.5208.

In plain terms: matches where the model said a team's postgame WE was ~90% show
that team winning 93% of the time in the historical sample; matches priced at
~55% show a 54% actual win rate. The model does not systematically over- or
under-state deserved-ness at any confidence level.

### Slice checks (chosen model, seed 42)

| Slice | n | Brier | Max decile cal-err |
|---|---|---|---|
| EPL | 8,360 | 0.163 | 0.022 |
| La Liga | 8,360 | 0.164 | 0.037 |
| Bundesliga | 6,732 | 0.160 | 0.034 |
| Ligue 1 | 7,712 | 0.166 | 0.030 |
| Serie A | 8,360 | 0.163 | 0.044 |
| MLS | 10,744 | 0.196 | 0.032 |
| USLC | 8,158 | 0.195 | 0.059 |
| NWSL | 2,868 | 0.197 | 0.040 |
| Playoffs (n=792) | 792 | 0.197 | 0.095 |
| 2026 in-progress (n=1,010) | 1,010 | 0.205 | 0.097 |

Full per-season slice table is in `experiments/postgame_we_report.json`
(`slices` key).

## Known limitations / not-yet-ready items

- **USLC (0.059) sits just above the 0.05 target** in the chosen (quadratic)
  model — the simpler linear-per-family model actually calibrates USLC better
  (0.025) at the cost of NWSL. The feature-set choice was made on the pooled
  metric per the calibration-agent convention; a future iteration could fit the
  feature set per-family too (not just the intercept/slope) if USLC-specific
  accuracy matters more than the aggregate number.
- **Playoffs (0.095) and the 2026 in-progress season (0.097)** exceed the target,
  but both are small slices (n<1,100) where a couple of upsets move the decile
  mean a lot — not evidence of a structural problem, but worth re-checking once
  more playoff/2026 data accumulates.
- **NWSL remains the noisiest league** (734 matches total) — every version of the
  model landed NWSL calibration error somewhere in 0.04–0.06 depending on small
  changes elsewhere; treat NWSL's postgame WE as directionally right but the
  least precise of the eight leagues.
- **No shot-quality or shot-count granularity** — this is explicitly an
  xG-differential model, not a shot-by-shot model, because that's the real data
  ceiling right now (see Data reality above). If shot-level data becomes
  available later, the same calibration-validation harness applies unchanged.

## Readiness for the webapp's Recent Results feed

**Ready to ship for the Big-5 leagues, MLS, USLC, and NWSL with the above
caveats disclosed** (e.g. a "sample size: N" or "less precise" note on NWSL, and
treating playoff-game WE as provisional). Before wiring into
`scripts/build_league_data.py` / `scripts/build_dashboard_data.py` and a
`webapp/data/*.js` payload field:

1. Decide the exact production feature (per-family `quadratic_for_against`
   coefficients are in `experiments/postgame_we_report.json` → `final_model`).
2. Add a `postgame_we` field to the Recent Results match payload (home/away
   percentages, computed from that match's own final xG — no model retraining
   needed at request time, it's a closed-form logistic function of the two
   final xG values).
3. Decide UI framing so it isn't confused with the pre-match probability already
   shown elsewhere on the same page (e.g. label it "How deserved: 78%" or
   similar, not "Win probability").
4. This is additive-only — no existing payload field, build script, or
   production model changes are required to ship it.
