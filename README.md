# MLS Prediction Dashboard

End-to-end MLS match prediction and market-tracking system for a Raspberry Pi
deployment backed by PostgreSQL and a Streamlit dashboard.

## Architecture

```text
Data sources             Feature engineering       Models
------------             -------------------       ------
ASA API                  ELO ratings               Dixon-Coles
ESPN scoreboard          Rolling xG/form           XGBoost/LightGBM
The Odds API             Travel/rest               Bayesian Stan/R
RSS + Claude             Injury/news overrides     Stacking ensemble
FBref/worldfootballR     Referee tendencies        penaltyblog benchmark

Predictions, odds, bets, overrides, and run status are stored in PostgreSQL.
```

## Setup

### System Packages

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3.11 python3.11-venv python3-pip postgresql \
    r-base r-base-dev libssl-dev libcurl4-openssl-dev libxml2-dev \
    libfontconfig1-dev libharfbuzz-dev libfribidi-dev libfreetype6-dev \
    libpng-dev libtiff5-dev libjpeg-dev cmake git build-essential
```

### Python And R

```bash
python3.11 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
sudo Rscript r_requirements.R
```

The Bayesian model is optional at runtime. If R, Stan, or the required packages
are unavailable, the daily pipeline records that status and continues with the
Python models.

### Environment

Create `.env` in the repo root:

```env
PG_HOST=127.0.0.1
PG_PORT=5432
PG_DBNAME=mls
PG_USER=ryang
PG_PASSWORD=...
ODDS_API_KEY=...
CLAUDE_API_KEY=...
# Optional Claude model override.
# CLAUDE_MODEL=...
# Optional season pin. If omitted, the current calendar year is used.
# MLS_CURRENT_SEASON=2026
```

Database defaults live in `config/settings.yaml`, but environment variables are
the source of truth for deployment secrets.

## Data And Model Runs

Initial backfill:

```bash
source venv/bin/activate
python scripts/backfill_history.py
```

Daily update:

```bash
source venv/bin/activate
python scripts/daily_update.py
```

The daily run initializes schema, syncs results/fixtures, refreshes features,
fits models, stores latest predictions deterministically, fetches opening odds,
creates simulated value bets, settles recent bets, and records status in
`pipeline_runs`.

Optional referee-stat refresh from FBref/worldfootballR:

```bash
source venv/bin/activate
python scripts/import_referee_stats.py --season 2026
```

Performance report:

```bash
source venv/bin/activate
python scripts/performance_report.py
```

## Streamlit Dashboard

```bash
source venv/bin/activate
streamlit run dashboard/app.py --server.port 8501 --server.address 0.0.0.0
```

Pages:

- Predictions: upcoming match probabilities and value-bet flags.
- Performance: Brier/log-loss, CLV, ROI, and team breakdowns.
- Calibration: reliability and sharpness views.
- News & Overrides: reviewed Claude/RSS news and manual strength adjustments.
- Betting Tracker: simulated fractional-Kelly P&L and CLV.

## Cron

```cron
# Full daily update at 6 AM
0 6 * * * /home/pi/mls/scripts/daily_update.sh >> /home/pi/mls/logs/daily.log 2>&1

# News polling every 6 hours
0 */6 * * * /home/pi/mls/scripts/daily_update.sh --news-only >> /home/pi/mls/logs/news.log 2>&1

# Closing odds snapshots near common kickoff windows
45 18,19,20,21,22 * * * /home/pi/mls/scripts/daily_update.sh --closing-odds >> /home/pi/mls/logs/odds.log 2>&1
```

## Configuration

Important settings in `config/settings.yaml`:

| Setting | Purpose |
| --- | --- |
| `data.backfill_start_season` | First season to load from ASA history. |
| `data.current_season` | Optional override; defaults to current year or `MLS_CURRENT_SEASON`. |
| `elo.*` | ELO home advantage, K factor, and season regression. |
| `features.*` | xG decay windows, form windows, expansion-team priors. |
| `dixon_coles.*` | Score truncation, time decay, and over/under line. |
| `gradient_boost.*` | Time-series CV and Optuna tuning controls. |
| `bayesian.*` | Stan chains, iterations, cores, and ELO prior scale. |
| `market.*` | Bookmaker, odds market, edge threshold, and Kelly fractions. |
| `dashboard.*` | Streamlit display defaults. |

## Development Checks

```bash
python -m compileall -q .
pytest
```

Tests use mocked API fixtures for fast, network-free checks of normalization,
feature leakage boundaries, odds contracts, Kelly sizing, and probability
invariants.
