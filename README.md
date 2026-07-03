# MLS Prediction Dashboard

A market-blind probabilistic model for MLS match outcomes (home win / draw /
away win) and a static web dashboard. The model is trained on xG and form — never
on betting odds — so that `edge = model_prob − market_prob` stays meaningful.

## Architecture (webapp-only)

```text
Data sources        Feature engineering        Model                Output
------------        -------------------        -----                ------
ASA API (xG)        ELO ratings                Dixon-Coles    ┐
ESPN scoreboard     Rolling xG / form          XGBoost (bag)  ├─► research_model ─► webapp/data/*.js ─► webapp/
ESPN box rosters    GK quality, availability   temperature cal│                       (built on a Mac;
Understat (Big-5)   DC + capped blend          capped blend   ┘                        served statically)
```

The active system is **database-free**: the research harness validates the model,
`models/research_model.py` is the single canonical implementation, and the build
scripts render per-league payloads under `webapp/data/*.js` for the static dashboard:

| Build script | Surface | Payload(s) |
|---|---|---|
| `scripts/build_dashboard_data.py` | MLS | `webapp/data/mls.js` |
| `scripts/build_league_data.py` | European / table leagues | `epl.js`, `la-liga.js`, `championship.js`, … |
| `scripts/build_continental_data.py` | Continental knockouts | `ucl.js`, `europa.js`, `concacaf-champions.js`, … |
| `scripts/fetch_league_teams.py` | "Coming soon" placeholders + `leagues.js` registry | `canadian-pl.js`, … |

Every payload carries a top-level `status` route-state field
(`live` / `preseason` / `completed` / `knockout_live` / `placeholder`) — see the
**Route State Taxonomy** and **Model Card Fields** in [`docs/CURRENT_STATE.md`](docs/CURRENT_STATE.md).
Run `python scripts/validate_payloads.py` after any build to enforce the data
contract (no `NaN`/`Infinity`, required fields per surface type).

Data-source terms, attribution, and redistribution rules are tracked in
[`docs/data-sources.md`](docs/data-sources.md).

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
python scripts/build_dashboard_data.py        # writes webapp/data/mls.js
python scripts/build_league_data.py           # European / table-league payloads
python scripts/build_continental_data.py      # continental knockout payloads
python scripts/validate_payloads.py           # enforce the data contract before serving
```

`mls.js` carries the current-season standings, per-match predictions and
projected scores, ELO ratings, playoff / Supporters' Shield / MLS Cup odds (from
a 20k-sim Monte-Carlo), an in-season Brier readout, and a model-health summary.
The dashboard (`webapp/index.html`) is a single static file — open it directly,
or serve `webapp/` with any static server (the `MLS Dashboard.command` launcher
does this). The sidebar league switcher loads one `webapp/data/<league>.js`
payload per route.

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
history and decisions are in `docs/PLAN.md` and `docs/PROJECT_HISTORY.md`.
The experiment contract and active plans live under `docs/experiment-protocol.md`
and `docs/superpowers/plans/`.

## Odds logging (opening lines)

```bash
python -m data_pipeline.odds_log --dry-run    # fetch + preview Pinnacle openers
python -m data_pipeline.odds_log              # append new fixtures to data/odds_log.parquet
```

No-ops cleanly without `ODDS_API_KEY`. Captures each fixture's **opening** line
once — the baseline for a future CLV / edge workstream and for measuring the
market's own MLS Brier.
