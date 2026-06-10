# MLS Dashboard — Claude Instructions

## Plan document

The canonical project plan lives at `docs/PLAN.md`.

**Update it after every iteration** — whenever eval results change, a feature is added/dropped, a parameter is tuned, or a phase decision is made, update the "Live eval results" block at the top of `docs/PLAN.md` and any relevant section body. Commit the updated plan in the same commit as the code changes.

## Active branch

All development goes on `claude/mls-prediction-dashboard-C2mQM`. Never push to main without explicit instruction.

## Eval script

`scripts/eval_baseline.py` is the research harness. Changes here are validated before porting to the production pipeline (`features/`, `models/`, `config/`).

## Key decisions (do not re-litigate without being asked)

- Training data: 2017+ only, 2020 excluded (COVID bubble). 2021 is RETAINED in training and as the
  2022 cal fold — A/B-validated 2026-06-09 (excluding 2021 from training costs +0.0019 Brier on the
  3-seed mean, nearly all on 2023; the earlier "2021 excluded" wording was stale docs)
- Test seasons: 2022–2025 walk-forward (2022 evaluates with the 2021 cal fold). 2025 added as the 4th
  fold 2026-06-09 — the old "2025 in-progress, never in test window" rule lapsed when the season
  completed (540 matches). 2026 in-progress data: training only, never in the test window.
- Champion measurement basis: experiments/champion.json → champion-4fold report (avg 0.6335, 4 folds,
  per-match vectors for the gate's paired bootstrap). Gate challengers must also be 4-fold reports.
- Calibration: temperature scaling (single T parameter, minimise NLL on cal fold)
- ELO: K=25, HOME_ADV=80, REGRESS=40% (promoted 2026-06-07: whl=6 + regress=0.40 synergistic; avg Brier 0.6337, cal_err 0.0195; prior "50% wins" was measured at whl=4)
- DC time-decay: 120-day half-life
- xG windows: (3, 5, 10, 15) matches — eval harness default; champion feat_base includes all four
- Edge threshold: 8% before live betting
- Production timing: improve eval first, then port to production
