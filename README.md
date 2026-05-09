# MLS Prediction Dashboard

Production-grade MLS match prediction system with ensemble modeling and Streamlit dashboard.

---

## Architecture

```
Data Sources (free)          Feature Engineering        Models
──────────────────           ───────────────────        ──────
ASA API (itscalledsoccer) →  ELO ratings            →  Dixon-Coles (Python)
ESPN hidden API           →  xG rolling averages    →  XGBoost + LightGBM
The Odds API (Pinnacle)   →  Travel / rest          →  Bayesian (R/brms)
RSS feeds + Claude API    →  Referee tendencies     →  Stacking Ensemble
ESPN injury reports       →  DP availability        →  ↓
                                                       Predictions → DuckDB → Streamlit
```

---

## First-Time Setup (Raspberry Pi)

### 1. System Dependencies

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3.11 python3.11-venv python3-pip r-base r-base-dev \
    libssl-dev libcurl4-openssl-dev libxml2-dev libfontconfig1-dev \
    libharfbuzz-dev libfribidi-dev libfreetype6-dev libpng-dev libtiff5-dev libjpeg-dev \
    cmake git build-essential
```

### 2. Clone the Repository

```bash
cd /home/pi
git clone http://your-repo-url/mls.git mls
cd mls
git checkout claude/mls-prediction-dashboard-C2mQM
```

### 3. Python Environment

```bash
python3.11 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

> **Note:** On Raspberry Pi, `rpy2` and `lightgbm` may need extra build time. If lightgbm fails:
> `pip install lightgbm --prefer-binary`

### 4. R Packages

```bash
sudo Rscript r_requirements.R
```

Installs `brms`, `worldfootballR`, `posterior`, `tidyverse`, `jsonlite`, `lubridate`.
First-time Stan compilation takes 5–15 minutes.

### 5. API Keys

Create `/home/pi/mls/.env`:

```env
CLAUDE_API_KEY=sk-ant-...
ODDS_API_KEY=your_odds_api_key_here
MLS_DB_PATH=/home/pi/mls/data/mls.duckdb
```

- **Claude API key**: https://console.anthropic.com
- **The Odds API**: https://the-odds-api.com (free tier: 500 req/month)

### 6. Initial Data Backfill

```bash
source venv/bin/activate
python scripts/backfill_history.py
```

Expected runtime: 20–60 minutes. Pulls full MLS history, fits all models.

### 7. Run the Dashboard

```bash
source venv/bin/activate
streamlit run dashboard/app.py --server.port 8501 --server.address 0.0.0.0
```

Dashboard available at `http://[pi-ip]:8501`

---

## Cloudflare Tunnel (Remote Access)

### Install cloudflared

```bash
curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm64 \
    -o /usr/local/bin/cloudflared
chmod +x /usr/local/bin/cloudflared
```

### Authenticate and Create Tunnel

```bash
cloudflared tunnel login
cloudflared tunnel create mls-dashboard
```

### Configure Tunnel (`~/.cloudflared/config.yml`)

```yaml
tunnel: mls-dashboard
credentials-file: /home/pi/.cloudflared/<tunnel-id>.json

ingress:
  - hostname: mls.yourdomain.com
    service: http://localhost:8501
  - service: http_status:404
```

Add a CNAME DNS record in Cloudflare: `mls.yourdomain.com` → `<tunnel-id>.cfargotunnel.com`

### Streamlit as Systemd Service (`/etc/systemd/system/mls-dashboard.service`)

```ini
[Unit]
Description=MLS Prediction Dashboard (Streamlit)
After=network.target

[Service]
User=pi
WorkingDirectory=/home/pi/mls
EnvironmentFile=/home/pi/mls/.env
ExecStart=/home/pi/mls/venv/bin/streamlit run dashboard/app.py \
    --server.port 8501 --server.address 127.0.0.1 --server.headless true
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable mls-dashboard cloudflared
sudo systemctl start mls-dashboard cloudflared
```

---

## Cron Jobs

```bash
crontab -e
```

```cron
# Daily DB backup at 5 AM (Phase 2)
0 5 * * * /home/ryang/mls/scripts/backup_db.sh >> /home/ryang/mls/logs/backup.log 2>&1

# Full daily update at 6 AM (Sunday = full Optuna tune; weekdays = quick refit)
0 6 * * * /home/ryang/mls/scripts/daily_update.sh >> /home/ryang/mls/logs/daily.log 2>&1

# News polling every 6 hours
0 */6 * * * /home/ryang/mls/scripts/daily_update.sh --news-only >> /home/ryang/mls/logs/news.log 2>&1

# Pre-match high-frequency lineup refresh during likely match hours (Phase 2)
*/5 14-23 * * * /home/ryang/mls/venv/bin/python /home/ryang/mls/scripts/pre_match_update.py >> /home/ryang/mls/logs/prematch.log 2>&1

# Nightly drift detector (Phase 2)
30 6 * * * /home/ryang/mls/venv/bin/python /home/ryang/mls/scripts/check_drift.py >> /home/ryang/mls/logs/drift.log 2>&1
```

Add `NTFY_TOPIC=your-secret-topic-name` to `/home/ryang/mls/.env` for push notifications, then subscribe to the same topic in the ntfy iOS/Android app.

---

## Directory Structure

```
MLS/
├── config/
│   ├── __init__.py          # Settings loader
│   └── settings.yaml        # All tunable parameters
├── data_pipeline/
│   ├── asa_client.py        # American Soccer Analysis API
│   ├── schedule_client.py   # ESPN fixtures + results
│   ├── odds_client.py       # Pinnacle odds via The Odds API
│   ├── injury_scraper.py    # ESPN injury report
│   ├── news_monitor.py      # RSS feeds + Claude API
│   └── db_utils.py          # DuckDB helpers
├── features/
│   ├── elo_ratings.py       # ELO system
│   ├── xg_features.py       # Rolling xG with decay
│   ├── travel_features.py   # Distance + schedule congestion
│   ├── referee_features.py  # Referee tendency stats
│   └── feature_builder.py   # Master feature assembly
├── models/
│   ├── dixon_coles.py       # Poisson model (MLE)
│   ├── gradient_boost.py    # XGBoost + LightGBM
│   ├── stacking_ensemble.py # Stacking meta-learner
│   └── r_bridge/
│       ├── bayesian_elo.R   # Hierarchical Bayesian (Stan/brms)
│       └── run_bayes.py     # Python → R bridge
├── market/
│   ├── kelly.py             # Fractional Kelly sizing
│   └── clv_tracker.py       # Closing line value
├── dashboard/
│   ├── app.py               # Streamlit entry point
│   └── pages/
│       ├── 1_Predictions.py
│       ├── 2_Performance.py
│       ├── 3_Calibration.py
│       ├── 4_News_Overrides.py
│       └── 5_Betting_Tracker.py
├── scripts/
│   ├── backfill_history.py  # One-time historical load
│   ├── daily_update.py      # Daily pipeline orchestrator
│   └── daily_update.sh      # Cron entry point
├── data/                    # DuckDB + model artifacts (gitignored)
├── logs/                    # Daily log files (gitignored)
├── requirements.txt
└── r_requirements.R
```

---

## Model Details

| Model | Approach | Output |
|-------|----------|--------|
| Dixon-Coles | Poisson MLE with time-decay | Score matrix → P(H/D/A), P(O/U) |
| XGBoost | Multiclass gradient boosting | P(H/D/A) |
| LightGBM | Binary gradient boosting | P(Over 2.5) |
| Bayesian (brms) | Hierarchical Poisson + ELO prior | Posterior predictive probs |
| Stacking Ensemble | Calibrated logistic meta-learner | Final probabilities |

---

## Key Configuration (`config/settings.yaml`)

| Parameter | Default | Description |
|-----------|---------|-------------|
| `elo.k_factor` | 20 | ELO update speed |
| `elo.season_regression_pct` | 0.30 | Season-start regression to 1500 |
| `features.xg_half_life_days` | 60 | xG decay half-life |
| `dixon_coles.time_decay_half_life_days` | 180 | DC weight decay |
| `market.default_edge_threshold_pct` | 5.0 | Value-bet alert threshold |
| `market.kelly_fractions` | [0.25, 0.50] | Fractional Kelly options |
| `bayesian.chains` | 4 | MCMC chains |
| `news.claude_model` | claude-sonnet-4-6 | Claude model for news analysis |
