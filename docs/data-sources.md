# Data Sources Register

Canonical record of every data source used by the active build and model.
Update this file whenever a source is added, removed, or its terms change.

See also: [CURRENT_STATE.md](CURRENT_STATE.md) for model config, [PROJECT_HISTORY.md](PROJECT_HISTORY.md) for source lineage decisions.

---

## Active Sources

### ASA / itscalledsoccer

| Field | Value |
|---|---|
| **Owner** | American Soccer Analysis (ambiata.com) |
| **URL** | https://pypi.org/project/itscalledsoccer/ |
| **Access method** | Python package (`itscalledsoccer`) — no auth required |
| **Auth** | None |
| **Cache path** | `data/asa_cache/<endpoint>_<league>_<season>_<date>.parquet` |
| **Attribution requirement** | Credit "American Soccer Analysis" for derived public output |
| **Redistribution status** | Derived aggregate metrics (team Brier, model health) — **OK**. Raw game-by-game rows — **uncertain, treat as local-only**. |
| **Allowed derived outputs** | Team-level projections, model health metrics, probability payloads |
| **Risk level** | Low — maintained package, no auth, no scrape fragility |

**Endpoints used:**
- `get_games(leagues, seasons)` — canonical match frame (MLS primary source)
- `get_players(leagues)` — player identity
- `get_player_goals_added(leagues, split_by_seasons)` — player g+, xPoints
- `get_goalkeeper_goals_added(leagues, split_by_seasons)` — GK metrics
- `get_team_salaries(leagues, split_by_teams)` — MLS salary data

**Leakage rule:** Salary data must use the **public release date**, not just the season label. MLSPA salary data is released publicly mid-season and at year-end; do not treat the season label as equivalent to "available before matchday." Player g+ and team stats are available only after matches are played — safe to use for training but require the match date to be before the observation date.

**Version discipline:** Pin `itscalledsoccer` explicitly in `requirements.txt`. The installed version should match the pinned constraint. Do not let it float to the latest if a breaking API change would affect the build.

---

### ESPN Soccer (Liga MX)

| Field | Value |
|---|---|
| **Owner** | ESPN / The Walt Disney Company |
| **URL** | `https://site.api.espn.com/apis/site/v2/sports/soccer` |
| **Access method** | Public undocumented JSON API, no auth |
| **Auth** | None |
| **Adapter** | `data_pipeline/espn_soccer.py` |
| **Cache path** | `data/espn_soccer/<league>.parquet` |
| **Attribution requirement** | Logo/crest usage requires ESPN permission; do not display ESPN crests publicly without review |
| **Redistribution status** | ESPN-derived match IDs, team names, and score rows — **local/model use only**. Derived probability payloads (which do not include raw ESPN fields) — **OK**. |
| **Allowed derived outputs** | Match probability payloads, projected tables — **OK** as long as raw ESPN IDs/scores are not in the public payload |
| **Risk level** | Medium — undocumented API, no contractual stability guarantee |

**Leakage rule:** Completed match scores and results are available immediately. Future fixture data (date, home/away) is forward-safe. Do not use in-progress score data for training rows.

---

### ESPN Fixtures (European upcoming schedules)

| Field | Value |
|---|---|
| **Owner** | ESPN / The Walt Disney Company |
| **URL** | Same ESPN scoreboard API |
| **Adapter** | `data_pipeline/espn_fixtures.py` |
| **Cache path** | `data/espn_fixtures/<league_id>-<season>.parquet` |
| **Attribution requirement** | Same as ESPN Soccer above |
| **Redistribution status** | Same as ESPN Soccer above |
| **Risk level** | Medium — used as fallback when Understat hasn't published the new season yet |

**Leakage rule:** Future fixtures (date, teams) are forward-safe. Do not infer results from ESPN fixture data before Understat confirms the result.

---

### ESPN Rosters

| Field | Value |
|---|---|
| **Owner** | ESPN / The Walt Disney Company |
| **URL** | Same ESPN API base |
| **Adapter** | `data_pipeline/espn_rosters.py` |
| **Cache path** | `data/espn_rosters.csv` (flat, resumable CSV) |
| **Attribution requirement** | Same as ESPN Soccer above |
| **Redistribution status** | Raw roster rows — **local-only**. Derived availability/GK features in model payloads — **OK**. |
| **Risk level** | Medium — roster data freshness depends on ESPN update cadence |

**Leakage rule:** Roster availability data is a **current-state snapshot**, not a historical record. The `observed_at` of the roster fetch bounds when it can be used. Do not use today's roster to predict yesterday's match.

---

### ESPN Continental

| Field | Value |
|---|---|
| **Owner** | ESPN / The Walt Disney Company |
| **URL** | Same ESPN API base |
| **Adapter** | `data_pipeline/espn_continental.py` |
| **Cache path** | `data/espn_continental/<comp_id>.parquet` |
| **Attribution requirement** | Same as ESPN Soccer above |
| **Redistribution status** | Same as ESPN Soccer above |
| **Risk level** | Medium |

**Leakage rule:** Same as ESPN Fixtures — completed match data safe, future match data is schedule-only.

---

### Understat

| Field | Value |
|---|---|
| **Owner** | understat.com |
| **URL** | https://understat.com |
| **Access method** | `understatapi` Python library (scraping-backed) |
| **Auth** | None |
| **Adapter** | `data_pipeline/understat.py` |
| **Cache path** | `data/understat/<league_id>.parquet` |
| **Attribution requirement** | Credit Understat as the xG data source in documentation |
| **Redistribution status** | Raw xG rows — **local/model use only**. Derived probability payloads — **OK**. |
| **Allowed derived outputs** | Model training frames, probability payloads, health metrics |
| **Risk level** | Medium — library is scraping-backed; Understat page structure changes can break fetches |

**Leakage rule:** European seasons keyed by start year (e.g. `2023` = 2023–24). Only in-progress or completed matches have xG data; new seasons are empty until Understat publishes results. The ESPN fixtures adapter covers the gap for schedule-only prediction when Understat has no played matches yet.

**Source health:** Record latest played match date, total xG coverage, and cache freshness per league per run.

---

### football-data.co.uk

| Field | Value |
|---|---|
| **Owner** | football-data.co.uk |
| **URL** | https://www.football-data.co.uk/ |
| **Access method** | Direct CSV download (no auth, no rate limit stated) |
| **Auth** | None |
| **Adapter** | `data_pipeline/football_data.py` |
| **Cache path** | `data/football_data/<league>.parquet` + `data/football_data/raw/<div>-<season_code>.csv` |
| **Attribution requirement** | Credit football-data.co.uk when using data in publications or reports |
| **Redistribution status** | Historical match results — **OK with attribution**. Bookmaker odds columns — **uncertain; treat as local-only for redistribution**. |
| **Allowed derived outputs** | Market baseline Brier scores, de-vigged implied probabilities for evaluation reports |
| **Risk level** | Low — long-running service, simple CSV format, has been stable for years |

**CRITICAL LEAKAGE RULE:** This source provides **closing-line odds** (after markets sharpen). Use **only for evaluation and market comparison**, never as model training features. Including closing odds as training inputs would make the model market-correlated and collapse the edge signal.

---

### The Odds API (Pinnacle opening lines)

| Field | Value |
|---|---|
| **Owner** | The Odds API |
| **URL** | https://api.the-odds-api.com |
| **Access method** | REST API with key |
| **Auth** | `ODDS_API_KEY` environment variable |
| **Adapter** | `data_pipeline/odds_log.py` |
| **Cache path** | `data/odds_log.parquet` (append-only, one row per fixture opener) |
| **Attribution requirement** | None for derived metrics |
| **Redistribution status** | Derived model-vs-market metrics — **OK**. Raw odds rows — **uncertain; treat as local-only**. |
| **Risk level** | Medium — paid API (free tier is forward-only); key is required for collection |

**CRITICAL LEAKAGE RULE:** This source is **forward-only**. Opening lines are logged the first time a fixture is observed and never overwritten. Use **only for CLV evaluation and edge calculation**, never as training features. If `ODDS_API_KEY` is missing, the adapter is a no-op; source health must still record that odds were not collected for that run.

---

### Transfermarkt (via worldfootballR R bridge)

| Field | Value |
|---|---|
| **Owner** | Transfermarkt GmbH |
| **URL** | https://www.transfermarkt.com |
| **Access method** | R package `worldfootballR` (archived/read-only on GitHub) |
| **Auth** | None (scraping) |
| **Adapter** | `scripts/import_transfermarkt.py` + `models/r_bridge/transfermarkt_squad_values.R` |
| **Cache path** | `data/transfermarkt_squad_values_<season>.csv` (raw) + `data/transfermarkt_squad_values_<season>_mapped.csv` |
| **Attribution requirement** | Credit Transfermarkt.com as source; link to team/player pages if displaying values publicly |
| **Redistribution status** | Derived aggregate team-value features (total squad value z-score, positional share) — **OK with attribution**. Raw player market values — **uncertain; treat as local-only**. |
| **Allowed derived outputs** | Team-level squad value z-scores, positional balance metrics, age-weighted value — all in model payloads only after rights review |
| **Risk level** | **High** — `worldfootballR` is archived (no new releases); Transfermarkt pages are slow, brittle, and can fail by team/season/layout; scraping rate limits apply |

**CRITICAL LEAKAGE RULE:** Current Transfermarkt scrapes **cannot be retroactively joined to historical match dates**. Every row must carry `observed_at` (the scrape timestamp). A match may only use values where `observed_at < match_date`. Season-labeled historical pages are NOT equivalent to as-of values at match time — they reflect the *current state* of a historical season page, not the player value at kickoff.

**Snapshot layers:**
- **Layer A (current):** Live scrape with `observed_at` — usable for predictions after `observed_at`
- **Layer B (season-labeled):** Historical pages via `start_year` — research use only, not production backtesting
- **Layer C (true as-of):** Weekly/monthly snapshots saved over time — only valid approach for match-date backtesting; start saving now
- **Layer D (fallbacks):** Prior-season carryforward when current season has no value; must record `value_source` and `value_confidence`

**R setup:**
```r
install.packages(c("devtools", "dplyr", "readr", "stringr", "rvest", "httr"))
devtools::install_github("JaseZiv/worldfootballR")
```

---

## Proposed Sources (Not Yet Active)

### FBref via soccerdata

| Field | Value |
|---|---|
| **Owner** | FBref / Sports Reference |
| **URL** | https://fbref.com |
| **Access method** | `soccerdata` Python library (scraping-backed) |
| **Auth** | None |
| **Proposed cache path** | `data/fbref/<league>/<season>.parquet` |
| **Attribution requirement** | Sports Reference requires attribution when using FBref data |
| **Redistribution status** | Derived metrics — **OK with attribution**. Raw scraped rows — **uncertain; check Sports Reference terms** |
| **Risk level** | Medium — scraping, rate-limit sensitivity, coverage varies by league |

**Intended use:** Prior-club performance for incoming MLS players from well-covered European leagues. Transfer date must bound when prior-club data is used — do not use post-transfer FBref stats.

**Leakage rule:** Prior-club performance data must stop at the transfer date. A player's FBref stats from after they joined MLS cannot be used to predict their first MLS matches.

**A12 addendum (2026-07-06) — match xG for goals-only leagues.** Second use case:
per-match Opta xG (`home_xg`/`away_xg` from FBref schedule pages) for leagues Understat
lacks (Championship, League One/Two, Liga MX; C1 leagues when built). Rules:
- **Access:** `soccerdata`'s `FBref` reader only — it enforces Sports Reference's
  rate limits and caches every page on disk; never raw `requests` against fbref.com.
- **Cache path (actual):** `data/fbref_cache/` (soccerdata's own layout; gitignored,
  local-only, same treatment as `asa_cache`).
- **Publication:** raw match-xG rows stay local. Payloads may ship *derived rolling
  aggregates* (`xg_roll_*` in team inputs) — identical to the Understat treatment
  already in production. Attribution: FBref/Sports Reference added to the site footer
  when the first FBref-fed payload ships (feature is gate-bound, off by default).
- **Leakage:** match xG is stamped by match date (an as-played stat, not a
  retro-mutable page) — safe to join historically, unlike Transfermarkt values.
- **OUTCOME (2026-07-06): BLOCKED — FBref no longer serves xG publicly.**
  Verified in raw cached HTML across schedule pages and team match logs for
  Championship/League One/Liga MX/Eredivisie AND an EPL control: zero xG
  data-stat cells anywhere. The rules above stand if the data returns; see
  `docs/feature-hunt-log.md` A12 entry for the full probe record.

---

### StatsBomb Open Data

| Field | Value |
|---|---|
| **Owner** | StatsBomb Ltd |
| **URL** | https://github.com/statsbomb/open-data |
| **Access method** | Public GitHub repository (JSON files) |
| **Auth** | None (public repo) |
| **Proposed cache path** | `data/statsbomb/<competition>/<season>/` |
| **Attribution requirement** | **REQUIRED** — StatsBomb public data license requires attribution and use of their logo for any public output using this data |
| **Redistribution status** | Derived metrics with attribution — **OK per license**. Raw event/lineup JSON — **local research only**. |
| **Risk level** | Low for access; **medium for compliance** — attribution is a product requirement if used publicly |

**Intended use:** Event-model prototyping, player-value transform validation, feature design research. Not a production MLS feed.

**Leakage rule:** Use only for research/prototyping unless a production MLS data contract is established.

---

## Payload Publication Matrix

What can go into `webapp/data/*.js` public payloads:

| Data type | May publish | Notes |
|---|---|---|
| Team probability (H/D/A) | Yes | Model output, not source data |
| Fair odds (decimal) | Yes | Derived from model probabilities |
| Model Brier / calibration | Yes | Aggregate model metric |
| Projected standings | Yes | Monte Carlo output |
| ELO rating | Yes | Internal metric |
| xG rolling averages (team-level) | Yes | Derived aggregate |
| Raw ESPN fixture IDs | No | ESPN-derived, local only |
| Raw ASA game rows | No | ASA raw data, local only |
| Player market values (Transfermarkt) | No | Attribution/redistribution uncertain |
| Raw Understat xG per match | No | Understat raw data, local only |
| Football-data.co.uk odds | No | Local evaluation use only |
| Raw Pinnacle opening lines | No | Odds API redistribution uncertain |

---

## Raw Data Commit Rules

Files **allowed in git:**
- `config/team_name_to_asa_id.yaml` — manual mapping file
- `config/settings.yaml` — build configuration
- `data/parity_frame.parquet` + `data/parity_frame.meta.json` — champion parity checkpoint

Files **in local cache only (gitignored):**
- `data/understat/*.parquet`
- `data/espn_soccer/*.parquet`, `data/espn_fixtures/*.parquet`, `data/espn_continental/*.parquet`
- `data/football_data/*.parquet`, `data/football_data/raw/*.csv`
- `data/odds_log.parquet`
- `data/asa_cache/*.parquet`
- `data/source_health.parquet`
- `data/espn_rosters.csv`, `data/roster_profiles/`

Files **that must never be committed:**
- `data/transfermarkt_squad_values_*.csv` — raw Transfermarkt scrapes (redistribution uncertain, large binary-adjacent)
- `.env`, `*.key`, any file containing API keys
- Build logs containing local absolute paths

---

## Attribution Plan

**Dashboard footer** should credit:
- American Soccer Analysis (itscalledsoccer) for MLS data
- Understat for xG data on European leagues
- Transfermarkt (if squad value features appear in any public payload)
- StatsBomb (if StatsBomb open data is used in any public output)

**README** should list all active sources with links.

---

## Source Health Summary

Source health is recorded to `data/source_health.parquet` via `data_pipeline/source_health.py` after each adapter run. Fields: `source_name`, `endpoint`, `fetched_at`, `raw_count`, `parsed_count`, `success`, `error_message`.

The promotion gate (`scripts/promotion_gate.py`) checks source health coverage floors before allowing a model to be promoted as champion.
