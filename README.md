# MLS Prediction Dashboard

A market-blind probabilistic model for MLS match outcomes (home win / draw /
away win) and a static web dashboard. The model is trained on xG and form — never
on betting odds — so that `edge = model_prob − market_prob` stays meaningful.

## Architecture (webapp-only)

```text
Data sources        Feature engineering        Model                Output
------------        -------------------        -----                ------
ASA API (xG)        ELO ratings                Dixon-Coles    ┐
ESPN scoreboard     Rolling xG / form          XGBoost (bag)  ├─► research_model ─► webapp/data.js ─► webapp/
ESPN box rosters    GK quality, availability   temperature cal│                      (built on a Mac;
                    DC + capped blend          capped blend   ┘                       served statically)
```

The active system is **database-free**: the research harness validates the model,
`models/research_model.py` is the single canonical implementation, and
`scripts/build_dashboard_data.py` renders `webapp/data.js` for the static dashboard.

> The original Raspberry Pi + PostgreSQL + Streamlit production stack was archived
> on 2026-06-11 under `legacy/` (see `legacy/README.md`). It is recoverable but not
> part of the active path.

## Setup

```bash
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install -e .   # editable install — makes scripts/, data_pipeline/, and models/ importable
```

This is required once per checkout so that project packages are importable without path workarounds.

Optional environment (only needed for live odds logging):

```env
# .env in the repo root
ODDS_API_KEY=...                  # The Odds API — opening-line logging (data_pipeline/odds_log.py)
# MLS_CURRENT_SEASON=2026          # season pin; defaults to the calendar year
```

## Build the dashboard

```bash
source venv/bin/activate
python scripts/build_dashboard_data.py        # writes webapp/data.js
```

`data.js` carries the current-season standings, per-match predictions and
projected scores, ELO ratings, playoff / Supporters' Shield / MLS Cup odds (from
a 20k-sim Monte-Carlo), an in-season Brier readout, and a model-health summary.
The dashboard (`webapp/index.html`) is a single static file — open it directly,
or serve `webapp/` with any static server (the `MLS Dashboard.command` launcher
does this).

## Model workflow

```bash
make smoke-test          # fast 2024-only Base regression check
make test                # unit suite (DB-free)
make parity-check        # research_model reproduces the champion report
python scripts/eval_baseline.py --xgb-bag 5 --seed 42   # full walk-forward eval

# challenger → gate → promote
python scripts/model_report.py --label challenger --out experiments/chal.report.json
python scripts/promotion_gate.py evaluate --challenger experiments/chal.report.json
```

Canonical state and config live in `docs/CURRENT_STATE.md`; the full project
history and decisions are in `docs/PLAN.md`, `docs/HANDOFF.md`, and
`docs/CODE_WALKTHROUGH.md`.

## Odds logging (opening lines)

```bash
python -m data_pipeline.odds_log --dry-run    # fetch + preview Pinnacle openers
python -m data_pipeline.odds_log              # append new fixtures to data/odds_log.parquet
```

No-ops cleanly without `ODDS_API_KEY`. Captures each fixture's **opening** line
once — the baseline for a future CLV / edge workstream and for measuring the
market's own MLS Brier.
