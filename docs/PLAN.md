# MLS Prediction Dashboard — Implementation Plan

> **Live eval results (last run: 2026-05-10, branch `claude/mls-prediction-dashboard-C2mQM`)**
> Phase 6b eval (1X2 only). Test seasons: 2023–2024 (2022 skipped, COVID cal fold).
> Naive baseline: 0.6469. XGBoost +GKQuality: 0.6387 (+1.3%). Ensemble stacked: 0.6437 (+0.5%).
> Calibration error: 0.1829 (stacked, still poor; temperature scaling; target <0.05).
> ELO: K=25, HOME_ADV=80, REGRESS=40%. DC calibrated: −1.3% (hurts ensemble).
> A/B results (new Phase 6b): +GKQuality KEEP (Δ=+0.0034), +GoalsAdded DROP (−0.0025),
>   +Squad DROP (−0.0018), +DCParams DROP (−0.0016), +Games14d marginal (+0.0005).
> Base now = ELO + xG[5,15] + form[5,10] + GK quality. Feature importances still ~4% each.
> PPDA/possession: unavailable (no get_game_xpass). Set-piece xGA: unavailable.
> DC drag: stacked (0.6437) worse than XGB alone (0.6387). Consider XGB-only ensemble.
> Next: A/B test GK in new Base; explore lineup / injury signal sources for match-level data.
>
> **Phase 7 results (2026-05-16):**
> +ASA_TopN: Δ=−0.0021 → DROP (Top-3/Top-5 outfielder g+ concentration; hurts vs Base).
> +ASA_xPass: Δ=+0.0002 → marginal (minutes-weighted player passing over-expected).
> +ASA_xGSplit: Δ=+0.0006 → marginal (set-piece xG share + xG over-performance;
>   set-piece column unavailable, so this is xG over-performance only).
> +TM_SquadValue: not yet evaluated — run `python scripts/import_transfermarkt.py --seasons 2017-2025`,
>   then `FETCH_TRANSFERMARKT=True python scripts/eval_baseline.py`.
> Per-season: 2022 Brier 0.6284, 2023 0.6352, 2024 0.6493. Naive: 0.6406 avg. +0.5% over naive.
> Calibration still weak (stacked max err 0.1258).
> FotMob: deferred (see "Deferred features" section below).
> Feature-hunt log: `docs/feature-hunt-log.md` (auto-populated every 30 min via /loop).
> Multi-agent improvement workflow: see `docs/experiment-protocol.md` and `/improve-model`.

---

## Multi-agent improvement workflow (2026-05-29)

The serial `/loop` feature hunt is now backed by a **parallel multi-agent workflow** that dispatches four specialised subagents (feature engineering, calibration, hyperparameters, model architecture), each isolated in its own git worktree, against a shared instrumented harness.

### Key files
| File | Purpose |
|------|---------|
| `scripts/eval_baseline.py` | Research harness — now accepts `--ab-only`, `--calibration`, `--elo-k`, `--elo-home-adv`, `--regress`, `--dc-decay-hl`, `--weight-hl`, `--cache`, `--seed`, `--out` flags |
| `scripts/experiment.py` | Runner (`run`), registry (`compare`), baseline (`baseline`) |
| `scripts/run_improvement_cycle.sh` | Headless single-component cycle for autonomous/cron use |
| `docs/experiment-protocol.md` | Shared agent contract (KEEP/DROP rules, scope guards, logging) |
| `docs/experiment-schema.json` | JSON schema for harness result files |
| `experiments/registry.jsonl` | Append-only experiment history |
| `.claude/agents/feature-engineer.md` | Feature engineering agent definition |
| `.claude/agents/calibration-tuner.md` | Calibration agent definition |
| `.claude/agents/hyperparameter-optimizer.md` | Hyperparameter agent definition |
| `.claude/agents/model-architect.md` | Architecture agent definition |
| `.claude/commands/improve-model.md` | `/improve-model` orchestrator command |
| `docs/calibration-log.md` | Calibration experiment log |
| `docs/hyperparameter-log.md` | Hyperparameter experiment log |
| `docs/architecture-log.md` | Architecture experiment log |

### Quick start
```bash
# 1. Record baseline (pre-warms the ASA data cache)
python scripts/experiment.py baseline --cache

# 2. Run one agent (e.g. calibration sweep — no code changes, flags only)
python scripts/experiment.py run --name cal-platt --cache -- --calibration platt --ab-only "Base"

# 3. Compare all experiments
python scripts/experiment.py compare

# 4. Full parallel cycle via Claude Code
/improve-model
```

### Design decisions
- The KEEP threshold is Δ > 0.001 Brier (same rule as the existing AB_SETS framework)
- Greedy forward-merging (re-eval after each merge) rather than simultaneous because calibration, hyperparameter, and architecture agents all touch overlapping harness regions
- `--cache` freezes ASA data at the start of each cycle so deltas are from the same dataset
- Production port (features/, models/, config/) is a separate step; research harness is always the gate

---

## Deferred features

- **FotMob integration** — deferred 2026-05-16. No documented public API; `pyfotmob` is reverse-engineered against the mobile endpoint and can break silently on any FotMob frontend change. Revisit only if ASA player metrics + Transfermarkt squad value plateau; needs an explicit ADR on scraping cost/risk vs incremental signal. Likely candidates if revived: per-match player ratings (avg starter rating, top-3 starter mean, defensive line rating). Same one-time-fetch-cached-to-CSV pattern as weather.
- **Lineup-aware availability features** — predicted/actual lineups × player g+. Source data lives in the production `predicted_lineups` DB table and the eval harness is DB-free by design (`scripts/eval_baseline.py:3`). Would require lifting the eval-DB-free constraint; reconsider after Phase 7 results.

---

## Context

Build a production-grade MLS score prediction and betting-market tracking system from scratch. The system must predict Win/Draw/Loss and Over/Under outcomes for all MLS regular season and playoff matches using an ensemble of statistical and ML models, compare model probabilities to Pinnacle odds for edge detection, and present all of this through a Streamlit dashboard with live news integration. Everything runs on a Raspberry Pi (DuckDB storage + daily cron + Streamlit), exposed publicly via a free Cloudflare Tunnel.

---

## Repository Structure

```
MLS/
├── config/
│   └── settings.yaml              # All tunable parameters (half-life, Kelly fraction, edge threshold default, etc.)
├── data_pipeline/
│   ├── __init__.py
│   ├── asa_client.py              # American Soccer Analysis API (itscalledsoccer pkg)
│   ├── odds_client.py             # The Odds API → Pinnacle pre-match + closing odds
│   ├── schedule_client.py         # ESPN hidden API for fixtures + results
│   ├── injury_scraper.py          # Injury/suspension binary flags (scraping + RSS)
│   ├── news_monitor.py            # RSS feed polling + Claude API impact scoring
│   └── db_utils.py                # DuckDB read/write helpers
├── features/
│   ├── __init__.py
│   ├── elo_ratings.py             # Continuously-updated ELO (new team = league-average prior)
│   ├── xg_features.py             # Rolling xG, xGA, xGD windows (configurable)
│   ├── travel_features.py         # Great-circle distance, days rest, games-in-N-days
│   ├── referee_features.py        # Per-referee card rate, penalty rate, home-win rate
│   └── feature_builder.py         # Assembles all features into a single match-level dataframe
├── models/
│   ├── __init__.py
│   ├── dixon_coles.py             # Dixon-Coles Poisson with exponential time-decay
│   ├── gradient_boost.py          # XGBoost + LightGBM multiclass (1X2) + binary (O/U)
│   ├── stacking_ensemble.py       # Logistic regression meta-learner over all model probs
│   └── r_bridge/
│       ├── bayesian_elo.R         # brms hierarchical Poisson; ELO as informative prior
│       └── run_bayes.py           # rpy2 bridge: serialize features → R → return posteriors
├── market/
│   ├── __init__.py
│   ├── clv_tracker.py             # Closing Line Value vs Pinnacle
│   └── kelly.py                   # Fractional Kelly (25% / 50%) stake sizing
├── dashboard/
│   ├── app.py                     # Streamlit entry point (multi-page)
│   └── pages/
│       ├── 1_Predictions.py       # Upcoming game prediction cards + value bet alerts
│       ├── 2_Performance.py       # Brier, log-loss, CLV, ROI over time; segmented views
│       ├── 3_Calibration.py       # Reliability diagrams, calibration curves
│       ├── 4_News_Overrides.py    # RSS news feed, Claude summaries, manual adjustment panel
│       └── 5_Betting_Tracker.py   # Simulated bet log, Kelly P&L, edge threshold filter
├── scripts/
│   ├── daily_update.sh            # Cron entry point (activates venv, runs pipeline)
│   ├── daily_update.py            # Orchestrates full daily ETL + retrain
│   └── backfill_history.py        # One-time load of full MLS history into DuckDB
├── requirements.txt
├── r_requirements.R               # install.packages() script for R dependencies
└── README.md
```

---

## Phase 1: Data Layer

### 1a. DuckDB Schema (db_utils.py)

Tables:
- `matches` — match_id, date, season, home_team, away_team, home_goals, away_goals, home_xg, away_xg, conference_h, conference_a, is_playoff, referee_id
- `team_features` — match_id, team_id, role (home/away), elo_pre, xg_rolling_5, xg_rolling_10, xga_rolling_5, xga_rolling_10, travel_km, days_rest, games_in_14d, dp1_available, dp2_available, dp3_available, supporter_shield_locked, form_5
- `elo_history` — team_id, date, elo_rating
- `referee_stats` — referee_id, name, card_rate_per90, penalty_rate_per90, home_win_rate
- `predictions` — match_id, model (dixon_coles | xgboost | bayesian | ensemble), prob_home, prob_draw, prob_away, prob_over, prob_under, predicted_at
- `odds` — match_id, bookmaker, market, outcome, open_odds, close_odds, fetched_at
- `news_items` — item_id, published_at, source, headline, url, teams_mentioned, claude_summary, estimated_impact_home_atk, estimated_impact_home_def, estimated_impact_away_atk, estimated_impact_away_def, confirmed_by_user, applied_to_match_id
- `overrides` — match_id, applied_at, description, home_strength_adj, away_strength_adj
- `simulated_bets` — bet_id, match_id, market, outcome_backed, model_prob, market_prob, edge_pct, stake_kelly25, stake_kelly50, result, pnl_kelly25, pnl_kelly50

### 1b. Data Sources

| Source | Package / Method | Data |
|--------|-----------------|------|
| American Soccer Analysis | `itscalledsoccer` (Python) | xG, xA, goals added, possession, match results |
| FBref | `worldfootballR` (R, called via rpy2) | Referee data, advanced player stats |
| ESPN hidden API | `requests` + JSON | Schedules, scores, injury reports |
| The Odds API | `requests` | Pinnacle pre-match + closing 1X2 odds (500 req/month free tier) |
| Transfermarkt | `worldfootballR` (R) | Player market values, DP identification |
| RSS feeds | `feedparser` | ESPN MLS, MLSSoccer.com, team blogs for news |

### 1c. Historical Backfill (backfill_history.py)

- Pull all MLS seasons (1996–present) from ASA API
- Compute ELO ratings chronologically from season 1 forward
- Scrape historical referee assignments from FBref via worldfootballR
- Seed DuckDB with all historical match + feature data
- Expected runtime: 30–60 minutes on first run

---

## Phase 2: Feature Engineering

### ELO System (elo_ratings.py)
- Standard ELO formula with K-factor = 20 (tunable)
- Home advantage = +100 ELO points for expected score calculation
- Margin-of-victory multiplier: `1 + log(goal_diff + 1) * 0.1`
- New/expansion teams start at 1500 (league average)
- Update after every match; store full time series in `elo_history`

### xG Features (xg_features.py)
- Rolling windows: 5, 10, 20 matches for xG, xGA, xGD
- Exponential decay: each past match weighted by `exp(-λ * days_ago)` where λ = `ln(2) / half_life_days` (half_life_days configurable in settings.yaml, default = 60)
- Separate home and away rolling averages

### Travel Features (travel_features.py)
- Team stadium coordinates hardcoded (static MLS stadium list)
- Great-circle distance between stadiums using `haversine` formula
- Features: `travel_km`, `days_since_last_match`, `matches_in_14_days`, `cross_conference_game`

### Referee Features (referee_features.py)
- Pull referee assignment from FBref per match
- Rolling referee stats: cards/90, pens/90, home_win_rate over last 50 officiated games
- Fall back to league-average if referee is new

### MLS-Specific Features (feature_builder.py)
- `is_playoff`: binary flag
- `conference_matchup`: EW / EE / WW
- `expansion_team_flag`: first 2 seasons of existence
- `supporter_shield_locked`: both teams' shield seedings are mathematically set
- `dp_available_count`: number of DPs available (0–3) per team

---

## Phase 3: Models

### Model A — Dixon-Coles Poisson (dixon_coles.py)
- Attack (α) and defense (β) parameters per team, home advantage (γ) global
- Dixon-Coles low-score correction (ρ parameter) for 0-0, 1-0, 0-1, 1-1
- Exponential time-decay weights on historical matches
- Maximum likelihood estimation via `scipy.optimize.minimize`
- Output: full score probability matrix → P(home win), P(draw), P(away win), P(over 2.5), P(under 2.5)
- Retrain: nightly on all historical + current season data

### Model B — Gradient Boosting (gradient_boost.py)
- XGBoost multiclass for 1X2 (3 classes)
- LightGBM binary for O/U 2.5
- Features: all engineered features from Phase 2 + injury flags
- Time-series cross-validation (no future leakage): 5 folds on rolling windows
- SHAP values computed and stored for interpretability panel
- Hyperparameter tuning: `optuna` with Brier score objective
- Retrain: nightly (fast enough for daily cadence)

### Model C — Bayesian Hierarchical (r_bridge/bayesian_elo.R)
- Framework: `brms` (Stan backend)
- Likelihood: Bivariate Poisson for home_goals ~ Poisson(λ_h), away_goals ~ Poisson(λ_a)
- Linear predictor: `log(λ_h) = μ + home_adv + atk_h - def_a`, `log(λ_a) = μ + atk_a - def_h`
- Priors: team attack/defense drawn from Normal(elo_scaled, σ) — ELO used as informative prior mean
- Expansion teams: wider prior variance (more uncertainty)
- Posterior predictive: sample 4000 draws → compute match outcome + O/U probabilities
- Output written to temp CSV, read back by run_bayes.py
- Retrain: nightly (MCMC, ~5–10 min on Pi with 4 cores)

### Model D — Stacking Ensemble (stacking_ensemble.py)
- Level 0 inputs: prob_home, prob_draw, prob_away, prob_over from all 3 models (9 features for 1X2, 3 for O/U)
- Level 1 meta-learner: isotonic-calibrated logistic regression (preserves calibration)
- Training: time-series cross-validation; Level 0 preds generated on hold-out folds
- Calibration check: compare ensemble to individual models via Brier score on validation set
- This is the primary model output used for all market comparison

---

## Phase 4: Market Comparison & Betting Tracker

### CLV Tracker (market/clv_tracker.py)
- Fetch Pinnacle opening odds at prediction time, closing odds at match kickoff
- Model implied probability = `ensemble_prob`
- Market implied probability = `1 / (pinnacle_odds / vig_adjusted)` — use Pinnacle's low vig as reference
- Edge at open = `model_prob - open_implied_prob`
- CLV = `open_implied_prob - close_implied_prob` (positive CLV = beat closing line)
- Store both in `odds` and `simulated_bets` tables

### Kelly Sizing (market/kelly.py)
- Full Kelly: `f = (b * p - q) / b` where b = odds-1, p = model_prob, q = 1-p
- 25% Kelly: `f_25 = 0.25 * f`
- 50% Kelly: `f_50 = 0.50 * f`
- Only stake when `edge_pct >= configurable_threshold` (dashboard slider)
- Bankroll tracked separately for 25% and 50% Kelly simulations

---

## Phase 5: News Pipeline

### RSS Monitor + Claude Integration (data_pipeline/news_monitor.py)
- Poll these RSS feeds every 6 hours: ESPN MLS, MLSSoccer.com, team official blogs
- Filter articles containing keywords: injury, suspended, red card, out, available, return, doubt, questionable
- For each flagged article: call Claude API (claude-sonnet-4-6) with prompt asking to:
  1. Identify affected team(s) and player(s)
  2. Estimate % impact on team attack strength (-20% to +10% range)
  3. Estimate % impact on team defense strength
  4. Assign confidence level (high/medium/low)
- Store result in `news_items` table
- Dashboard (Page 4) shows unconfirmed items for user review
- User clicks "Apply" to write to `overrides` table; override factors applied at prediction time

---

## Phase 6: Streamlit Dashboard

### Page 1 — Predictions (Upcoming Games)
- Grid of prediction cards per upcoming match (next 7 days)
- Each card: home team logo, away team logo, date/time, win%/draw%/loss%, predicted xG H–A, score probability heatmap (top 5 scorelines)
- Value bet badge: if model edge > threshold, show "VALUE" tag with edge %
- Configurable edge threshold slider (default 5%)
- Toggle: show raw model probabilities vs. ensemble only

### Page 2 — Performance Tracker
- Line chart: Brier score, log-loss by week/month (rolling)
- Bar chart: simulated ROI by season and by edge threshold bucket (3%, 5%, 7%, 10%+)
- Table: model performance segmented by team (where is the model systematic?)
- Filters: season picker, home/away toggle, model picker (compare ensemble vs. components)

### Page 3 — Calibration
- Reliability diagram: predicted probability bins vs. actual outcome frequency
- Sharpness histogram: distribution of predicted probabilities
- Per-class calibration (home win / draw / away win separately)
- Brier score decomposition: reliability + resolution + uncertainty components

### Page 4 — News & Overrides
- Feed of Claude-processed news items (newest first)
- Each item: headline, source, Claude summary, estimated impact sliders (pre-populated)
- "Apply to Match" button → writes override to DB
- Applied overrides section: list of active adjustments with ability to remove
- Manual override form: pick match, enter custom strength adjustment manually

### Page 5 — Betting Tracker
- Simulated bet log table (match, market, model edge, odds, result, P&L)
- Cumulative P&L chart for 25% Kelly and 50% Kelly
- Total ROI, win rate, avg CLV, max drawdown stats
- Edge threshold filter slider (show bets above X%)
- Season filter

---

## Phase 7: Infrastructure (Raspberry Pi)

### Folder Layout on Pi
```
/home/pi/mls/          ← cloned repo
/home/pi/mls/data/mls.duckdb   ← DuckDB file
/home/pi/mls/.env      ← API keys (CLAUDE_API_KEY, ODDS_API_KEY)
/home/pi/mls/venv/     ← Python virtualenv
```

### Cron Job (crontab -e on Pi)
```
0 6 * * * /home/pi/mls/scripts/daily_update.sh >> /home/pi/mls/logs/daily.log 2>&1
0 */6 * * * /home/pi/mls/scripts/news_poll.sh >> /home/pi/mls/logs/news.log 2>&1
```

### daily_update.py Orchestration Order
1. `schedule_client.py` — fetch yesterday's results + update match table
2. `asa_client.py` — pull latest xG data
3. `injury_scraper.py` — refresh injury/suspension flags
4. `elo_ratings.py` — recalculate ELO after new results
5. `feature_builder.py` — rebuild feature snapshots for upcoming matches
6. `dixon_coles.py` — refit model, generate predictions
7. `gradient_boost.py` — refit model, generate predictions
8. `run_bayes.py` — call R/brms model, generate predictions
9. `stacking_ensemble.py` — refit meta-learner, generate ensemble predictions
10. `odds_client.py` — fetch latest Pinnacle odds for upcoming matches
11. `clv_tracker.py` — compute edges and update simulated bets with results
12. Write all predictions + odds to DuckDB

### Cloudflare Tunnel
- Install `cloudflared` on Pi
- Create free Cloudflare Tunnel: `cloudflared tunnel create mls-dashboard`
- Configure to route `https://mls-dashboard.yourdomain.com` → `localhost:8501`
- Run as systemd service for persistence after reboot

---

## Key Python Packages (requirements.txt)

```
itscalledsoccer         # ASA MLS stats API
rpy2                    # Call R from Python
duckdb                  # Embedded analytical DB
xgboost
lightgbm
scikit-learn
optuna                  # Hyperparameter tuning
shap                    # SHAP interpretability
scipy
numpy
pandas
streamlit
plotly
anthropic               # Claude API for news impact
feedparser              # RSS feed parsing
requests
beautifulsoup4
haversine               # Great-circle distance
pyyaml                  # Config loading
python-dotenv           # .env loading
APScheduler             # In-process scheduling fallback
```

## Key R Packages (r_requirements.R)

```r
install.packages(c("brms", "worldfootballR", "tidyverse", "jsonlite", "posterior"))
```

---

## Critical Files to Create (in order)

1. `config/settings.yaml` — parameters first, everything else reads from here
2. `data_pipeline/db_utils.py` — schema creation + helpers
3. `data_pipeline/asa_client.py` — primary historical data source
4. `data_pipeline/schedule_client.py` — fixture feeds
5. `data_pipeline/odds_client.py` — market data
6. `data_pipeline/injury_scraper.py`
7. `data_pipeline/news_monitor.py` — RSS + Claude API
8. `features/elo_ratings.py`
9. `features/xg_features.py`
10. `features/travel_features.py`
11. `features/referee_features.py`
12. `features/feature_builder.py`
13. `models/dixon_coles.py`
14. `models/gradient_boost.py`
15. `models/r_bridge/bayesian_elo.R`
16. `models/r_bridge/run_bayes.py`
17. `models/stacking_ensemble.py`
18. `market/kelly.py`
19. `market/clv_tracker.py`
20. `scripts/backfill_history.py`
21. `scripts/daily_update.py`
22. `scripts/daily_update.sh`
23. `dashboard/app.py`
24. `dashboard/pages/1_Predictions.py`
25. `dashboard/pages/2_Performance.py`
26. `dashboard/pages/3_Calibration.py`
27. `dashboard/pages/4_News_Overrides.py`
28. `dashboard/pages/5_Betting_Tracker.py`
29. `requirements.txt`
30. `r_requirements.R`
31. Pi setup instructions in README.md (Cloudflare Tunnel, crontab, systemd)

---

## Verification (Phase 1)

1. **Backfill**: Run `backfill_history.py` — DB contains all matches, ELO history, xG features
2. **Model fit**: Run `daily_update.py` — all 3 sub-models + ensemble generate probabilities for upcoming matches
3. **Calibration check**: Brier score on held-out 2023 season should be < 0.23 (vs naive baseline ~0.25)
4. **Dashboard**: `streamlit run dashboard/app.py` — all 5 pages load
5. **News pipeline**: Trigger `news_monitor.py` — Claude API returns impact scores
6. **Market comparison**: After a match, `clv_tracker.py` records CLV and updates bet P&L
7. **Cloudflare**: Dashboard accessible at tunnel URL externally
8. **Cron**: `daily_update.sh` runs cleanly at 6 AM

---

# PHASE 2 — MODEL REFINEMENTS

## Context

The Phase 1 system is built and pushed (37 files, 5,561 lines). Phase 2 adds 28 user-approved refinements organized into six work-streams: new features, MLS-specific competitions, news pipeline expansion, validation rigor, risk management, and operational polish. These refinements turn the baseline ensemble into a higher-performing, more robust production system.

## R1 — New Match Features

**File targets:** new modules in `features/`, additions to `feature_builder.py`, new columns in `team_features` table (or sibling tables).

| Feature | Source | Implementation |
|---------|--------|----------------|
| Weather (temp, wind, precip, humidity) | Open-Meteo API (free, no key) | New `features/weather_features.py`. Lookup by stadium lat/lon at kickoff timestamp. Cache by (stadium, date) to avoid refetch. |
| Pitch surface (turf/grass) | Static map per stadium | Add to `_STADIUMS` dict in `travel_features.py`. **A/B-test before keeping**: train ensemble with and without this feature; only retain if Brier-score delta on held-out fold is > 0.001. |
| High-altitude flag | Static (Colorado, RSL only) | Binary feature in `feature_builder.py`. |
| Rivalry / high-importance flag | Hardcoded list of MLS rivalries (Cascadia, Hudson River, El Tráfico, ATL-ORL, Texas Derby, Heritage Cup) + binary "high-importance match" (CCC knockouts, playoff spots) | New util `features/match_context.py`. |
| Kickoff hour + day-of-week | `matches.kickoff_time` (need to start storing this) | Cyclic encoding (sin/cos) for hour; one-hot for day-of-week. |
| Set-piece xG / open-play xG split | ASA `get_team_xgoals` already returns these | Add columns to `team_features`: `xg_setpiece_rolling_10`, `xg_openplay_rolling_10`, same for xGA. |
| PPDA + possession + field tilt | ASA `get_team_xpass` / xgoals | New `features/style_features.py`. **Train ensemble with/without; keep only if Brier improves**. |
| Manager change flag + tenure | Manual table seeded from FBref via worldfootballR | New `manager_history` table. Feature: `days_under_current_manager`, `is_first_5_under_new_mgr`. |
| Dynamic playoff implication score | Computed live from current standings | New `features/match_importance.py` — for each upcoming match, simulate remaining season 1k times and compute Δ playoff probability if team wins vs loses. Score = abs(win_pct - loss_pct). |
| Goalkeeper availability | ESPN injury report (extend existing scraper) | New columns: `home_starting_gk_available`, `away_starting_gk_available`. Map known starters per team. |
| Card accumulation tracking | New `card_log` table populated from FBref via worldfootballR | New `features/suspensions.py`. Yellow ≥5 in season → suspended next match. Surface to feature builder as `home_key_player_suspended`. |
| News sentiment | Claude API on team-specific news in past 7 days | New columns: `home_news_sentiment_7d`, `away_news_sentiment_7d` (continuous -1 to +1). Computed in news pipeline. |

## R2 — MLS-Specific Competitions

**File targets:** `data_pipeline/asa_client.py`, `scripts/backfill_history.py`, `features/feature_builder.py`.

- **Concacaf Champions Cup**: scrape match results from FBref/CCC site; add to `matches` table with `competition='ccc'`. Use for fatigue features (`games_in_14d`, `days_rest`) but exclude from MLS-only ensemble training set.
- **Leagues Cup**: include all matches in training data with new `is_non_mls_opponent` flag.
- **US Open Cup**: include in training with `is_usoc` flag.
- **FIFA International Breaks**: hardcoded calendar of FIFA windows; new feature `is_post_fifa_break` and `n_internationals_unavailable` (count from injury/news pipeline).

Required schema changes:
- `matches.competition` VARCHAR (mls / ccc / leagues_cup / usoc) — default 'mls'
- `matches.kickoff_time` TIMESTAMP

## R3 — Lineup & News Pipeline Expansion

**File targets:** new `data_pipeline/lineup_scraper.py`, expanded `data_pipeline/news_monitor.py`, new `scripts/pre_match_update.py`.

- **Predicted lineups**: scrape MLSSoccer.com match preview pages; parse predicted XI per team. Store in new `predicted_lineups` table.
- **Pre-match high-frequency check**: new cron `*/5 7-23 * * *` runs `pre_match_update.py`. Logic: for any match within 90 minutes of kickoff with no recent prediction refresh, re-pull lineups + injury news, regenerate prediction. Logs lineup-induced probability changes.
- **Claude match preview synthesis**: extend `news_monitor.py` with `synthesize_preview()` function. For each upcoming match within 24h, ask Claude to read all flagged articles + recent results and produce a 1-paragraph rationale. Store on `predictions` table.
- **Twitter/X**: deferred — add later if news pipeline gaps appear.

## R4 — Validation & Model Architecture Upgrades

**File targets:** new `models/backtest.py`, new `models/season_simulator.py`, new dashboard page `6_Backtest.py`.

- **Walk-forward backtest module**: parameterized framework that walks weekly through history, refits models on data up to week N, predicts week N+1, settles bets, advances. Outputs full ROI/CLV/Brier curves stored in new `backtest_results` table. Dashboard exposes parameter sliders (edge threshold, half-life, Kelly fraction, model subset) and re-runs on demand.
- **Monte Carlo season simulation**: 10k sims of remaining season using current model probabilities; output playoff probability + Supporters Shield odds + projected points table per team. New dashboard page `7_Season_Forecast.py`.
- **Profit-aware loss function**: implement custom objective `betting_logloss` that weights misclassifications by (1/decimal_odds) — penalizes being wrong on long shots more than favorites. Compare to standard log-loss in backtest; use whichever produces higher CLV.
- **Drift detection + alerts**: new `scripts/check_drift.py` runs nightly. If 4-week rolling Brier degrades by >5% vs prior 12-week baseline, send ntfy.sh alert.
- **Model versioning**: add `model_version` column to `predictions` table. Snapshot pickled models to `data/model_versions/<YYYYMMDD>/`. New dashboard view to compare versions side-by-side over time.

## R5 — Risk Management

**File targets:** `market/kelly.py`, `market/clv_tracker.py`, new `market/risk_rules.py`.

- **Drawdown stop-loss**: in `market/risk_rules.py`, if 30-day rolling drawdown exceeds 15% of starting bankroll, set a `betting_paused` flag in DB. Daily update checks flag and emits no new bets while active. Dashboard shows banner. User can manually clear via dashboard.
- **Hard bet cap**: in `kelly.py`, cap any single Kelly stake at 10% of current simulated bankroll regardless of edge.
- **Bet correlation**: skip per user input — treat games independent.
- **Real-bet tracker**: new `real_bets` table parallel to `simulated_bets`. Dashboard adds form to log actual placed bets (book, odds, stake, result). Performance page shows simulated vs real side-by-side.

## R6 — Operations & Dashboard Polish

**File targets:** new `scripts/notify.py`, additions to all dashboard pages, new `scripts/backup_db.sh`.

- **ntfy.sh push notifications**: free service, no signup. New `scripts/notify.py` POSTs to `https://ntfy.sh/<unique-topic>`. Triggers: value bet detected (edge > threshold), drift alert, daily update failure. User subscribes to topic on iOS/Android ntfy app.
- **Mobile-optimized layout**: refactor `dashboard/app.py` CSS with media queries; use Streamlit columns adaptively. Test on iPhone Safari.
- **CSV export buttons**: add `st.download_button` to every page exposing the rendered DataFrame.
- **Daily DB backups**: new `scripts/backup_db.sh` runs `pg_dump mls > /home/ryang/mls/backups/mls_YYYYMMDD.sql.gz` daily at 5 AM. Retains 30 days, deletes older.
- **Weekly hyperparameter tuning**: split `daily_update.py` cron into daily (refit with cached params) and Sunday-only (full Optuna run, cache new params). Saves ~5 min/day during the week.
- **Auth**: skip — Cloudflare Tunnel obscurity sufficient per user choice.

## New Files (Phase 2)

```
features/
├── weather_features.py
├── style_features.py            # PPDA, possession, field tilt
├── match_context.py             # rivalries, importance flags
├── match_importance.py          # dynamic playoff implication scoring
└── suspensions.py               # card accumulation tracker

data_pipeline/
├── lineup_scraper.py            # MLSSoccer.com predicted XIs
└── (news_monitor.py expanded with synthesize_preview + sentiment)

models/
├── backtest.py                  # walk-forward backtest framework
├── season_simulator.py          # Monte Carlo season sim
└── (gradient_boost.py + dixon_coles.py extended for profit-aware loss)

market/
└── risk_rules.py                # drawdown stop-loss, hard cap, real-bet tracking

scripts/
├── pre_match_update.py          # high-frequency lineup-driven refresh
├── check_drift.py               # nightly drift detector
├── notify.py                    # ntfy.sh push wrapper
└── backup_db.sh                 # daily pg_dump

dashboard/pages/
├── 6_Backtest.py                # walk-forward backtest visualization
├── 7_Season_Forecast.py         # Monte Carlo standings projection
└── 8_Real_Bets.py               # actual wager tracking
```

## Schema Additions (Phase 2)

```sql
ALTER TABLE matches
  ADD COLUMN competition       VARCHAR(20) DEFAULT 'mls',
  ADD COLUMN kickoff_time      TIMESTAMP,
  ADD COLUMN weather_temp_c    DOUBLE PRECISION,
  ADD COLUMN weather_wind_kph  DOUBLE PRECISION,
  ADD COLUMN weather_precip_mm DOUBLE PRECISION,
  ADD COLUMN pitch_surface     VARCHAR(10);

ALTER TABLE team_features
  ADD COLUMN xg_setpiece_rolling_10  DOUBLE PRECISION,
  ADD COLUMN xg_openplay_rolling_10  DOUBLE PRECISION,
  ADD COLUMN xga_setpiece_rolling_10 DOUBLE PRECISION,
  ADD COLUMN ppda_rolling_10         DOUBLE PRECISION,
  ADD COLUMN possession_rolling_10   DOUBLE PRECISION,
  ADD COLUMN gk_starting_available   BOOLEAN,
  ADD COLUMN key_player_suspended    BOOLEAN,
  ADD COLUMN days_under_mgr          INTEGER,
  ADD COLUMN news_sentiment_7d       DOUBLE PRECISION,
  ADD COLUMN match_importance_score  DOUBLE PRECISION;

ALTER TABLE predictions
  ADD COLUMN model_version       VARCHAR(20),
  ADD COLUMN claude_rationale    TEXT;

CREATE TABLE manager_history (
  team_id    VARCHAR(10) NOT NULL,
  manager    VARCHAR(80) NOT NULL,
  start_date DATE NOT NULL,
  end_date   DATE,
  PRIMARY KEY (team_id, start_date)
);

CREATE TABLE card_log (
  match_id   VARCHAR(20) NOT NULL,
  player     VARCHAR(80) NOT NULL,
  team_id    VARCHAR(10),
  card_color VARCHAR(10) NOT NULL,
  PRIMARY KEY (match_id, player, card_color)
);

CREATE TABLE predicted_lineups (
  match_id     VARCHAR(20) NOT NULL,
  team_id      VARCHAR(10) NOT NULL,
  source       VARCHAR(30),
  scraped_at   TIMESTAMP DEFAULT NOW(),
  predicted_xi TEXT,    -- JSON array of player names
  PRIMARY KEY (match_id, team_id, source)
);

CREATE TABLE backtest_results (
  run_id          VARCHAR(20) PRIMARY KEY,
  parameters      TEXT,    -- JSON of tested params
  brier_mean      DOUBLE PRECISION,
  roi_kelly25     DOUBLE PRECISION,
  avg_clv         DOUBLE PRECISION,
  max_drawdown    DOUBLE PRECISION,
  generated_at    TIMESTAMP DEFAULT NOW()
);

CREATE TABLE real_bets (
  bet_id      VARCHAR(20) PRIMARY KEY,
  match_id    VARCHAR(20) NOT NULL,
  bookmaker   VARCHAR(30),
  market      VARCHAR(10),
  outcome     VARCHAR(10),
  stake       DOUBLE PRECISION,
  odds        DOUBLE PRECISION,
  result      VARCHAR(10),
  pnl         DOUBLE PRECISION,
  placed_at   TIMESTAMP DEFAULT NOW()
);
```

## Implementation Order (Phase 2)

Build in dependency order so each step works in isolation:

1. **Schema migrations** — apply all `ALTER TABLE` and `CREATE TABLE` statements first.
2. **Feature additions** (R1) — start with weather (lowest risk), then surface, altitude, rivalry, time-of-day. Then set-piece/open-play split (uses ASA data we already pull). Add style features last (test if predictive).
3. **MLS competitions** (R2) — extend ASA/FBref pulls; backfill historical CCC, Leagues Cup, USOC matches.
4. **Lineup + news expansion** (R3) — lineup scraper, then `pre_match_update.py` cron, then Claude preview synthesis, then sentiment.
5. **Validation modules** (R4) — backtest framework first, then season simulator, then drift detector, then versioning.
6. **Risk management** (R5) — drawdown rules, hard cap, real-bet tracker.
7. **Ops polish** (R6) — backups (Day 1 priority despite ordering), then notifications, mobile CSS, CSV exports, weekly tuning split.

## Verification (Phase 2)

1. **Schema**: All ALTER/CREATE statements run cleanly; tables visible in DBeaver.
2. **Weather**: For one upcoming match, fetch weather and confirm reasonable values (e.g., ATL summer = warm).
3. **Surface A/B test**: Run backtest with surface feature on/off; record Brier delta in `backtest_results`. Keep feature only if delta > 0.001.
4. **CCC fatigue**: For team with recent CCC match, confirm `games_in_14d` reflects it.
5. **Lineup scraper**: For the next match, verify a predicted XI is fetched and stored.
6. **Pre-match cron**: Trigger manually 90 min before a kickoff; confirm predictions refresh and lineup-driven probability change is logged.
7. **Walk-forward backtest**: Run a backtest over the last completed season; confirm Brier, ROI, CLV are produced and visible in dashboard.
8. **Monte Carlo sim**: Run for current season; confirm playoff probabilities sum sensibly (each conference's playoff slots ≈ count).
9. **Drift detector**: Manually corrupt last week's predictions, run detector, confirm ntfy alert fires.
10. **Stop-loss**: Set bankroll to a state with simulated 20% drawdown; confirm `betting_paused` flag set and no new bets created next run.
11. **Real-bet form**: Submit a test real bet via dashboard form; confirm it appears in `real_bets` and on the dashboard.
12. **Backup**: Confirm `backup_db.sh` produces a `.sql.gz` file; restore to a temp DB to validate integrity.
13. **Mobile layout**: Open dashboard URL on phone; confirm prediction cards and pages render readably.
14. **Notification end-to-end**: Trigger a value bet manually; confirm push arrives on phone via ntfy app.

---

# PHASE 5 — MODEL IMPROVEMENTS (POST-EVAL)

## Context

Evaluation results (2022–2024 walk-forward, 3-way split with isotonic calibration):

| Model | Brier | vs Naive |
|---|---|---|
| Naive baseline | 0.6392 | — |
| DC calibrated | 0.6482 | -1.4% |
| XGB calibrated | 0.6447 | -0.9% |
| Ensemble avg | 0.6400 | -0.1% |
| Ensemble stacked | 0.6407 | -0.2% |
| O/U stacked | 0.2429 | +0.2% |

Critical issues identified:
1. **Calibration error severe**: max decile error 0.17 (target <0.05) — probabilities unfit for Kelly sizing
2. **O/U XGBoost worse than naive** even after calibration — DC's λ+μ goal rates are better signal
3. **Feature importances uniform** (~9% each of 11 features) — no dominant feature; signals too diffuse
4. **Isotonic calibration hurts log-loss** on small cal sets (~472 matches) — Platt scaling fits better
5. **Stacking meta-learner adds no value** over simple average at this signal level
6. **Draw class hardest** (Brier 0.197) — teams that draw structurally tend to draw; rolling draw rate needed

## User Goals

- **Primary target**: Brier score (probability accuracy)
- **Production threshold**: 8–12% Brier improvement over naive before real betting
- **Market focus**: 1X2 result only; edge threshold raised to 8%
- **Approach**: Improve eval_baseline.py first, port to production after confirmation

## All Changes to `scripts/eval_baseline.py`

### 1. Data Filtering (lines 70–76)

```python
_COVID_SEASONS = {2020, 2021}  # bubble season + partial-fan anomaly
df = df[(df["season"] >= 2017) & (~df["season"].isin(_COVID_SEASONS))]
# 2025 in-progress data included for training; eval stays on 2022–2024
```

Rationale: pre-2017 MLS is a different tactical era; 2020 bubble removes home advantage entirely; 2021 was irregular. Excludes ~700 anomalous rows.

### 2. ELO Grid Search (new section before walk-forward)

```python
ELO_GRID = itertools.product([20, 25, 30], [80, 100, 120])  # K × HOME_ADV
# Validate on 2019–2021 (pre-test window); pick combination with lowest avg Brier
# Season regression: 0.30 → 0.40 (user-specified; MLS parity increasing)
REGRESS = 0.40
```

Best (K, HOME_ADV) is selected before the main 2022–2024 walk-forward begins.

### 3. Rolling Features Overhaul

New features added to `add_rolling_features()`:
- `home_draw_rate_10`, `away_draw_rate_10` — rolling draw frequency (last 10 matches); addresses Draw Brier 0.197
- `home_xg_roll_5`, `home_xga_roll_5`, `away_xg_roll_5`, `away_xga_roll_5` — two windows (5 and 15) instead of one
- `home_xg_roll_15`, `home_xga_roll_15`, `away_xg_roll_15`, `away_xga_roll_15`
- `home_xg_sum` = `home_xg_roll_5 + away_xg_roll_5` — direct O/U signal
- `is_playoff` — binary flag (from ASA game data; column `stage_name` or equivalent)

Window of 20 removed (too collinear with 15; user approved simplification to [5, 15]).

Updated `FEAT_COLS`:
```python
FEAT_COLS = [
    "elo_diff", "home_elo", "away_elo",
    "home_xg_roll_5",  "home_xga_roll_5",  "away_xg_roll_5",  "away_xga_roll_5",
    "home_xg_roll_15", "home_xga_roll_15", "away_xg_roll_15", "away_xga_roll_15",
    "xg_diff", "form_diff", "home_form", "away_form",
    "home_draw_rate_10", "away_draw_rate_10",
    "home_xg_sum",
    "is_playoff",
    "dc_lam", "dc_mu",   # added after DC fit (see §4)
]
```

### 4. Dixon-Coles: Shorter Decay + Export λ/μ as Features

```python
# Change decay_hl: 180 → 120 days
atk, dfd, ha, rho = fit_dc(train, decay_hl=120)

# New helper to extract goal-rate parameters per match:
def dc_lam_mu_batch(split_df, atk, dfd, ha):
    lams, mus = [], []
    for _, r in split_df.iterrows():
        lam = math.exp(atk.get(r.home_team, 0) + dfd.get(r.away_team, 0) + ha)
        mu  = math.exp(atk.get(r.away_team, 0) + dfd.get(r.home_team, 0))
        lams.append(lam); mus.append(mu)
    return np.array(lams), np.array(mus)

# After DC fit, add to cal and test DataFrames before XGBoost training:
cal["dc_lam"],  cal["dc_mu"]  = dc_lam_mu_batch(cal,  atk, dfd, ha)
test["dc_lam"], test["dc_mu"] = dc_lam_mu_batch(test, atk, dfd, ha)
```

`dc_lam` and `dc_mu` give XGBoost DC's structured Poisson estimate of each team's current strength.

### 5. Calibration: Isotonic → Platt Scaling

```python
# Replace IsotonicRegression with LogisticRegression (1-D Platt scaling)
from sklearn.linear_model import LogisticRegression as PlattLR

def calibrate_multiclass(raw_cal, y_cal, raw_test):
    cal_out = np.zeros_like(raw_test)
    for c in range(3):
        platt = PlattLR(max_iter=300, C=1.0)
        platt.fit(raw_cal[:, c].reshape(-1, 1), (y_cal == c).astype(int))
        cal_out[:, c] = platt.predict_proba(raw_test[:, c].reshape(-1, 1))[:, 1]
    row_sums = cal_out.sum(axis=1, keepdims=True).clip(1e-9, None)
    return cal_out / row_sums

def calibrate_binary(raw_cal, y_cal, raw_test):
    platt = PlattLR(max_iter=300, C=1.0)
    platt.fit(raw_cal.reshape(-1, 1), y_cal.astype(int))
    return platt.predict_proba(raw_test.reshape(-1, 1))[:, 1]
```

Platt scaling is well-calibrated on ~500 samples. Isotonic needed 1,000+ per class.

### 6. XGBoost: Grid Search + Exponential Sample Weights

```python
# Small hyperparameter grid (inner CV on training fold):
from sklearn.model_selection import ParameterGrid
XGB_GRID = list(ParameterGrid({
    "max_depth": [3, 4, 5],
    "n_estimators": [200, 300, 500],
    "learning_rate": [0.03, 0.05, 0.10],
}))
# Pick params with lowest 3-fold CV Brier on training fold

# Exponential season weighting:
def season_weight(s, ref):
    return math.exp(-math.log(2) / 4 * (ref - s))  # half-life = 4 seasons
sample_weight = train["season"].map(lambda s: season_weight(s, train["season"].max())).values
clf.fit(X_tr, y_tr_r, sample_weight=sample_weight)
```

### 7. A/B Feature Testing (new output section)

Report Brier delta per new feature group by running eval in 4 modes:

| Run | Features | Purpose |
|-----|----------|---------|
| Base | ELO + xG[5,15] + form | Reference |
| +DrawRate | Base + draw_rate | Test draw signal |
| +DCParams | Base + dc_lam + dc_mu | Test DC param signal |
| +All | All features | Final result |

Keep a feature only if it improves avg Brier by >0.001 across 3 test seasons.

### 8. Updated Reporting

Add to output:
- ELO grid search winner and Brier vs default
- A/B Brier delta table for each new feature
- Calibration error comparison: Platt vs isotonic
- Per-class improvement (home/draw/away) from new features

---

## Critical Files to Reference (read-only)

- `scripts/eval_baseline.py` — the file being rewritten
- `features/xg_features.py` — EWM decay pattern to follow for draw_rate
- `config/settings.yaml` — post-eval, update `xg_windows: [5, 15]`, `time_decay_half_life_days: 120`, `edge_threshold: 8.0`

## Verification

1. **COVID exclusion confirmed** — print statement shows 2020/2021 row count = 0
2. **ELO grid** — winning (K, HOME_ADV) printed before walk-forward
3. **A/B table** — per-feature Brier delta shows draw_rate and DC params individually
4. **Platt calibration** — max decile error drops below 0.10 (vs isotonic 0.17)
5. **O/U** — LightGBM with xG_sum beats naive; DC O/U also reported for comparison
6. **Overall Brier** — best model improves vs naive by >3% (vs current ~0.1%)

---

# PHASE 3 — SIMPLIFICATION

## Context

User's guiding principle: "the model should be maximally predictive but otherwise as simple as possible." Until empirical model testing begins, the right feature set is unknown. Phase 3 applies three targeted simplifications without removing any code: (1) disable the Bayesian R/brms model until the Python baseline is validated, (2) gate Pages 6–8 (Backtest, Season Forecast, Real Bets) behind a settings flag since they're not essential on day 1, (3) update the stacking ensemble to handle the 2-model case (DC + GB only) without Bayesian inputs. All Phase 2 features remain enabled by default. Cloudflare Tunnel already handles phone/iMac dashboard access — no changes needed there.

## Changes

### 1. `config/settings.yaml`

Add two flags under existing sections:

```yaml
bayesian:
  enabled: false   # ← ADD THIS. Set true when R/Stan is installed and Python baseline is validated.
  chains: 4
  ...

dashboard:
  beta_pages_enabled: false   # ← ADD THIS. Set true to enable pages 6/7/8 (Backtest, Season Forecast, Real Bets).
  prediction_horizon_days: 14
  ...
```

### 2. `scripts/daily_update.py`

Wrap all Bayesian steps (R bridge) in a feature flag check. In `main()`:

```python
bayesian_enabled = SETTINGS.get("bayesian", {}).get("enabled", False)

# Step 8 — only runs if bayesian.enabled: true
if bayesian_enabled:
    if train_df is not None:
        run_step("Prepare Bayesian input data", prepare_train_data, train_df)
    if upcoming_df is not None and not upcoming_df.empty:
        run_step("Prepare Bayesian predict data", prepare_predict_data, upcoming_df)
    bayes_success = run_step("Run R Bayesian model", run_r_model)
    bayes_preds = run_step("Read Bayesian predictions", read_predictions) if bayes_success else None
else:
    logger.info("Bayesian model disabled (bayesian.enabled=false). Skipping R bridge.")
    bayes_preds = None
```

Move the `from models.r_bridge.run_bayes import ...` import inside the `if bayesian_enabled:` block so missing R/rpy2 doesn't break startup.

Also skip `snapshot_model_version` Bayesian argument when disabled — already graceful since `bayes_preds=None` is the fallback path.

**Critical file:** `scripts/daily_update.py` lines 120–125 (Bayesian block)

### 3. `models/stacking_ensemble.py`

The ensemble's `predict()` method currently receives `dc_probs, gb_probs, bayes_probs` and uses `bayes_probs or dc_probs` as fallback. This means when `bayes_probs=None`, it duplicates DC probs into the Bayes slot — the meta-learner still sees 9 features but 3 of them are identical to DC features. This works but wastes capacity and may over-weight DC.

**Better approach when Bayesian is disabled:** Use only 6 features (DC 3 + GB 3) and train the meta-learner on those. Add a `n_models` parameter or detect based on whether bayes columns are present in training data.

Concretely:
- `oof_predictions()` in `GradientBoostModels` produces: `gb_prob_home`, `gb_prob_draw`, `gb_prob_away`, `gb_prob_over` 
- The ensemble `fit()` currently expects DC OOF columns added manually with placeholder values (0.45/0.25/0.30/0.50) — those need to remain for the meta-learner shape
- When Bayesian is absent, don't add `dc_prob_*` placeholder Bayesian columns; the meta-learner trains on 8 features instead of 12 (4 DC + 4 GB + 4 Bayes → 4 DC + 4 GB)
- Add a `_with_bayesian: bool` attribute saved with the model pickle so `predict()` knows whether to expect 8 or 12 features

**Change in `_generate_and_store_predictions`** (`daily_update.py`): When `bayes_preds=None` and building the OOF fallback ensemble, don't add Bayesian placeholder columns; signal to `StackingEnsemble` that it's a 2-model fit.

**Critical file:** `models/stacking_ensemble.py` — `fit()`, `predict()`, `store_predictions()`

### 4. Dashboard Pages 6, 7, 8

Each of `dashboard/pages/6_Backtest.py`, `7_Season_Forecast.py`, `8_Real_Bets.py` should add at the top (after imports, before any data loading):

```python
from config import SETTINGS
if not SETTINGS.get("dashboard", {}).get("beta_pages_enabled", False):
    st.set_page_config(page_title="Coming Soon — MLS Dashboard")
    st.title("🚧 Coming Soon")
    st.info("This page is not yet enabled. Set `dashboard.beta_pages_enabled: true` in settings.yaml to activate.")
    st.stop()
```

This keeps the files in place, keeps the sidebar links visible, but prevents data loading errors until the user is ready to activate them.

**Critical files:** `dashboard/pages/6_Backtest.py`, `7_Season_Forecast.py`, `8_Real_Bets.py`

### 5. `requirements.txt`

Mark `rpy2` as optional with a comment so it doesn't block pip install when R is absent:

```
# R integration (optional — only needed when bayesian.enabled: true in settings.yaml)
# rpy2>=3.5.0
```

Comment it out. Users who want Bayesian can uncomment it after installing R + Stan.

**Critical file:** `requirements.txt`

## Implementation Order (Phase 3)

1. `config/settings.yaml` — add two flags first (everything else reads from here)
2. `requirements.txt` — comment out rpy2
3. `scripts/daily_update.py` — wrap Bayesian steps in feature flag
4. `models/stacking_ensemble.py` — handle 2-model case cleanly
5. `dashboard/pages/6_Backtest.py`, `7_Season_Forecast.py`, `8_Real_Bets.py` — add beta gate

## Verification (Phase 3)

1. **Bayesian flag**: Set `bayesian.enabled: false`, run `daily_update.py --dry-run` (or just import it); confirm no R-related import errors, no R model steps logged.
2. **2-model ensemble**: Run `_generate_and_store_predictions` with `bayes_preds=None`; confirm ensemble fits and predicts without error.
3. **Beta pages**: Open pages 6, 7, 8 in browser; confirm "Coming Soon" message appears, no traceback.
4. **Requirements**: Fresh `pip install -r requirements.txt` in a clean venv; confirm no rpy2/R error.
5. **Enabled path**: Set `bayesian.enabled: true` (with R installed); confirm full pipeline runs as before — Phase 3 must not break the future Bayesian upgrade path.

---

# PHASE 4 — MLS DOMAIN CORRECTIONS

## Context

Six questions surfaced three concrete model corrections and three confirmations of existing behavior:

**Confirmations (no code changes):**
- **Turf**: Effect is real but modest — keep the feature, let backtest calibrate weight.
- **Altitude**: Binary flag for both Colorado + RSL is correct as-is.
- **Late-season rotation**: Too inconsistent to model — no seeding-locked feature needed.

**Corrections (require code changes):**
1. **Dome stadiums** — Atlanta (Mercedes-Benz) and Vancouver (BC Place) have retractable roofs and are effectively climate-controlled. The weather pipeline currently fetches outdoor Open-Meteo data for these venues, which is meaningless and could create a spurious signal (e.g., "Atlanta matches have low precip" not because of anything meaningful but because the roof is closed). Fix: add a `_DOME_STADIUMS` set and skip weather fetching for those teams.
2. **Leagues Cup form** — Top clubs compete, smaller clubs rotate. Leagues Cup matches should always count toward fatigue (`games_in_14d`, `days_rest`), but should **not** feed the form rolling average (W/D/L points) or xG rolling averages, since intent varies by team. Simpler and more defensible than trying to detect per-team seriousness.
3. **Referee nulls for unassigned matches** — When no referee has been assigned to an upcoming match (typically 3+ days out), use `NULL` rather than the league-average fallback. XGBoost handles nulls natively. Applying league averages implies a known-average official, which is a false signal.

## Changes

### 1. `features/travel_features.py` and `features/weather_features.py`

Add `_DOME_STADIUMS` to `travel_features.py` (alongside `_STADIUMS`):

```python
_DOME_STADIUMS = {"ATL", "VAN"}  # retractable roof — weather data irrelevant
```

Export `is_dome(team_id: str) -> bool` function from `travel_features.py`.

In `weather_features.py`, `fetch_weather()` should short-circuit for dome teams:

```python
from features.travel_features import is_dome

def fetch_weather(home_team, match_date, kickoff_hour_local=19):
    if is_dome(home_team):
        logger.debug("Skipping weather fetch for dome stadium: %s", home_team)
        return None  # columns remain NULL in DB
    ...
```

Add `is_dome` as a binary feature in `build_match_context()` in `match_context.py` so the model knows the weather nulls are structural (not missing data):

```python
"is_dome": int(is_dome(home_team)),
```

**Critical files:** `features/travel_features.py`, `features/weather_features.py`, `features/match_context.py`

### 2. `features/xg_features.py` and `features/feature_builder.py`

Currently, when building rolling xG and form features, all completed matches for a team are included regardless of competition. Leagues Cup matches should be excluded from the form and xG rolling windows (since intent varies), but kept in the fatigue window.

In `feature_builder.py`, when querying for a team's recent matches to compute rolling xG and form, add a filter:

```python
# Exclude Leagues Cup from form/xG rolling (competitive intent varies)
# But DO include in games_in_14d / days_rest (fatigue is real regardless of intent)
form_matches = recent_matches[recent_matches["competition"] != "leagues_cup"]
fatigue_matches = recent_matches  # all competitions
```

The `build_training_dataset()` function should also exclude Leagues Cup rows from the training set entirely (they don't represent normal MLS competitive behavior and would confuse the model).

**Critical files:** `features/feature_builder.py`, `features/xg_features.py`

### 3. `features/referee_features.py`

The current fallback when no referee is assigned returns league-average stats. Change this: when a match has no referee assignment (i.e., `referee_id` is NULL or empty in the matches table), return `None` for all referee columns rather than league averages.

```python
def get_referee_features(referee_id: str | None) -> dict:
    if not referee_id:
        return {k: None for k in _REFEREE_FEATURE_COLS}  # not yet assigned
    ...
    # existing lookup + league-average fallback for *unknown* referees stays
```

The distinction: `None` referee_id = not assigned yet → return nulls. Known referee_id not in our DB = genuinely unknown tendency → league average is reasonable.

**Critical file:** `features/referee_features.py`

## Implementation Order (Phase 4)

1. `features/travel_features.py` — add `_DOME_STADIUMS` and `is_dome()`
2. `features/weather_features.py` — short-circuit `fetch_weather()` for dome teams
3. `features/match_context.py` — add `is_dome` as a binary feature
4. `features/referee_features.py` — return nulls when referee not assigned
5. `features/feature_builder.py` — split form/xG window vs fatigue window; exclude Leagues Cup from training set

## Verification (Phase 4)

1. **Dome weather skip**: Build features for an ATL home match; confirm `weather_temp_c`, `weather_wind_kph`, `weather_precip_mm` are NULL; confirm `is_dome=1`.
2. **Dome feature present**: Confirm `is_dome` column appears in training dataset for ATL/VAN home matches.
3. **Leagues Cup exclusion**: After backfill, query `SELECT competition, COUNT(*) FROM matches GROUP BY competition`; confirm leagues_cup rows exist. Then confirm `build_training_dataset()` result contains no leagues_cup rows; confirm `games_in_14d` for a team with a recent LC match is higher than it would be without it.
4. **Referee null vs average**: For an upcoming match 5 days out with no referee assigned, confirm referee feature columns are NULL. For a match with a known referee assignment, confirm their specific stats populate.
5. **No regression**: Run `daily_update.py` with flag guards active; confirm no errors, predictions still generated for upcoming matches.
