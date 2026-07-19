# Legacy — archived Postgres + Streamlit production system

**Archived 2026-06-11.** This directory holds the original Phase 1/2 production
system, superseded by the DB-free research harness (`scripts/eval_baseline.py`
+ `scripts/eval/`), the canonical model (`models/research_model.py`), and the
static web dashboard (`scripts/build_dashboard_data.py` → `webapp/`).

The project is now **webapp-only**: the Mac builds `webapp/data.js` on a
schedule and serves the static `webapp/` folder. There is no Raspberry Pi, no
PostgreSQL, and no Streamlit in the active path.

## What's here

| Subtree | What it was |
|---------|-------------|
| `dashboard/` | Streamlit multi-page app (Predictions, Performance, Calibration, News, Betting, Backtest, Forecast, Real Bets) |
| `models/` | Legacy model stack: `dixon_coles`, `gradient_boost`, `stacking_ensemble`, `backtest`, `season_simulator` — replaced by `models/research_model.py` |
| `data_pipeline/` | Postgres-backed ingest clients: `asa_client`, `schedule_client`, `odds_client`, `news_monitor`, `injury_scraper`, `lineup_scraper` |
| `features/` | Postgres-backed feature builders (the harness uses `scripts/eval/feature_builders.py` instead) |
| `market/` | Betting layer: `clv_tracker`, `kelly`, `implied`, `risk_rules` — **kept for the future CLV/edge workstream** |
| `scripts/` | DB/cron-bound ops: `daily_update`, `backfill_history`, `pre_match_update`, `check_drift`, `performance_report`, `import_referee_stats`, `backup_db.sh` |
| `tests/` | Tests for the above (DB integration, prediction contracts, DB-backed features) |

## Running it

These files use **repo-root-absolute imports** (e.g. `from models.dixon_coles
import …`, `from market.kelly import …`) that no longer resolve from `legacy/`
in place. To run any of it again, either restore the files to their original
paths (`git mv legacy/<x> <x>`) or check out the pre-archive commit. It also
requires a PostgreSQL instance with the schema in
`legacy/data_pipeline/db_utils.py` (archived 2026-07-19 once `source_health`
went DB-free and nothing active imported it).

## Archived later (2026-07-19 dead-code audit)

These were still at the repo root after the 2026-06-11 archive but had no
active-tree references left, only imports from `legacy/` itself:

- `models/penaltyblog_baseline.py` → `legacy/models/` (benchmark model; the
  `penaltyblog` dep moved from `requirements.txt` to `requirements-legacy.txt`)
- `models/r_bridge/{bayesian_elo.R, run_bayes.py, referee_stats_worldfootballR.R}`
  → `legacy/models/r_bridge/` (the two Transfermarkt R scripts remain active)
- `scripts/notify.py` → `legacy/scripts/` (ntfy.sh wrapper; only legacy cron
  scripts called it)
- `data_pipeline/db_utils.py` → `legacy/data_pipeline/`
- `r_requirements.R` → `legacy/` (Raspberry Pi era R env installer; the active
  Transfermarkt workflow installs its own R packages inline)

## Why kept, not deleted

The `market/` betting layer and `odds_client` are directly relevant to the
planned **betting/CLV workstream** (edge = model_prob − market_prob vs Pinnacle
**opening** lines). Archiving preserves that work for adaptation rather than a
from-scratch rebuild. Everything here is also recoverable from git history.
