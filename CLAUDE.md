# MLS Dashboard — Claude Instructions

## Plan document

The canonical project plan lives at `docs/PLAN.md`.

**Update it after every iteration** — whenever eval results change, a feature is added/dropped, a parameter is tuned, or a phase decision is made, update the "Live eval results" block at the top of `docs/PLAN.md` and any relevant section body. Commit the updated plan in the same commit as the code changes.

## Active branch

All development goes on `claude/mls-prediction-dashboard-C2mQM`. Never push to main without explicit instruction.

## Eval script

`scripts/eval_baseline.py` is the research harness. Changes here are validated before porting to the production pipeline (`features/`, `models/`, `config/`).

## Key decisions (do not re-litigate without being asked)

- Training data: 2017+ only, 2020 and 2021 excluded (COVID)
- 2025 in-progress data: used for training, never in eval test window
- Test seasons: 2022–2024 walk-forward (2022 skips due to COVID cal fold)
- Calibration: temperature scaling (single T parameter, minimise NLL on cal fold)
- ELO: K=25, HOME_ADV=80, REGRESS=50% (empirically confirmed 2026-05-30: 0.40 regresses 2024; prior "40%" was wrong)
- DC time-decay: 120-day half-life
- xG windows: (3, 5, 10, 15) matches — eval harness default; champion feat_base includes all four
- Edge threshold: 8% before live betting
- Production timing: improve eval first, then port to production
