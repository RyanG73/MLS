# Pi E2E Validation Runbook (Phase F)

This is the production validation sequence for the Raspberry Pi (where Postgres
and the full `daily_update.py` pipeline live). The research harness and the
production model are validated separately:

- **Research harness** (`eval_baseline.py`) — runs anywhere with ASA access; no DB.
- **Production model** (`research_model.py`) — validated DB-free via the parity
  frame + `model_report.py` + `promotion_gate.py`; only DB read/write IO differs
  on the Pi.
- **Pipeline E2E** (`daily_update.py`) — requires Postgres; Pi-only.

## 0. Environment

```bash
cd ~/MLS
pyenv local 3.11            # or: mise use python@3.11   (matches .python-version)
pip install -r requirements.txt
make lock                   # freeze exact versions → requirements.lock
python -c "import psycopg2; print('DB driver OK')"
```

## 1. Unit + contract tests (no DB needed for most)

```bash
make test                   # pytest tests/ + promotion_gate self-test
```

Expected: `test_walk_forward`, `test_metrics`, `test_dixon_coles`, `test_config`
green. DB-backed tests (`test_features`, `test_market_contracts`,
`test_prediction_contracts`) require Postgres reachable.

## 2. Research-harness smoke gate (ASA, no DB)

```bash
make smoke-test             # eval_baseline.py --smoke-test
```

Expected: `[smoke-test] PASS: 2024 ens_stacked_brier ≈ 0.6354 (within 0.001)`.

## 3. Production-model parity (frame-based, no DB)

```bash
# Build the parity frame (includes all feature columns incl. referee)
python scripts/eval_baseline.py --cache --seed 42 --dump-frame data/parity_frame.parquet
make parity-check           # research_model on the frame vs TARGET_BRIER (|Δ|<0.0015)
```

## 4. Champion vs challenger gate (the +Referee promotion decision)

Run the standardized report twice on the SAME frame — Base (champion) and
Base+referee (challenger) — then run the gate:

```bash
python scripts/model_report.py --frame data/parity_frame.parquet \
    --label champ-base --out experiments/champ_base.report.json
python scripts/model_report.py --frame data/parity_frame.parquet \
    --extra-feats ref_hw_rate,ref_draw_rate \
    --label chal-referee --out experiments/chal_referee.report.json
python scripts/promotion_gate.py evaluate \
    --challenger experiments/chal_referee.report.json \
    --champion  experiments/champ_base.report.json
```

If the gate prints `PROMOTE ✓`, the referee feature is a validated production
improvement. Promote and rebuild the dashboard:

```bash
python scripts/promotion_gate.py promote --challenger experiments/chal_referee.report.json
make build-dashboard-data
```

> NOTE: to make the referee feature available to the LIVE pipeline (not just the
> frame), it must also be produced by the production feature path
> (`features/referee_features.py` → `team_features`/match features → `feat_base`).
> The frame-based gate above proves the model VALUE; the feature-pipeline wiring
> is the remaining production-port task.

## 5. Pipeline E2E (Pi-only, Postgres required)

```bash
make daily-update           # full pipeline incl. step 9b data-quality report
```

Verify:
- `source_runs` table gets one row per feed (asa/espn/pinnacle) with raw/parsed/
  matched counts (Phase A).
- Step 9b logs odds 1X2 coverage + any missing-draw WARNING + feature null rates.
- `predictions` table updated by the research model (canonical path).

## 6. Provenance

```bash
make build-dashboard-data
# confirm webapp/data.js carries: build timestamp, git commit, model file,
# metric convention (brier_sum_form).
```

---

### Acceptance checklist

- [ ] `make test` green (non-DB suites)
- [ ] `make smoke-test` PASS (2024 within 0.001 of 0.6354)
- [ ] `make parity-check` PASS (|Δ| < 0.0015)
- [ ] Referee gate: `PROMOTE ✓` (or documented REJECT with reason)
- [ ] `make daily-update` writes `source_runs` rows + predictions
- [ ] `webapp/data.js` provenance stamp present
