PYTHON := python3
VENV   := venv
PY     := $(if $(wildcard $(VENV)/bin/python),$(VENV)/bin/python,$(PYTHON))

.PHONY: test parity-check daily-update build-dashboard-data backfill performance-report \
        model-report gate-self-test diagnose-2024 lock smoke-test validate help

help:
	@echo "MLS prediction system targets:"
	@echo "  make test                 Run the test suite (pytest)"
	@echo "  make parity-check         Verify research_model matches eval harness (|Δ| < 0.0015)"
	@echo "  make daily-update         Run the daily update pipeline"
	@echo "  make build-dashboard-data Rebuild webapp/data.js from the canonical research model"
	@echo "  make backfill             Backfill historical match data"
	@echo "  make performance-report   Print prediction + betting performance metrics"
	@echo "  make model-report         Standardized canonical-model report (metrics + slices)"
	@echo "  make gate-self-test       Verify the promotion gate rejects worse challengers"
	@echo "  make diagnose-2024        Run the 2024 distribution-shift diagnosis"
	@echo "  make lock                 Freeze exact deps to requirements.lock (run on deploy target)"
	@echo "  make smoke-test           Eval 2024-only; assert Brier within 0.001 of pinned reference"
	@echo "  make validate             DB-free CI gate: tests + smoke-test + gate self-test (see docs/PI_VALIDATION.md)"

test:
	$(PY) -m pytest tests/ -v
	$(PY) scripts/promotion_gate.py self-test

lock:
	@echo "Freezing exact dependency versions to requirements.lock ..."
	$(PY) -m pip freeze > requirements.lock
	@echo "Wrote requirements.lock (regenerate whenever requirements.txt changes)."

smoke-test:
	$(PY) scripts/eval_baseline.py --smoke-test

# DB-free validation gate (the part of Phase F that runs off-Pi). The full
# Pi E2E sequence (incl. daily-update) is documented in docs/PI_VALIDATION.md.
validate:
	$(PY) -m pytest tests/test_walk_forward.py tests/test_metrics.py \
	    tests/test_dixon_coles.py tests/test_config.py -q
	$(PY) scripts/promotion_gate.py self-test
	$(PY) scripts/eval_baseline.py --smoke-test

parity-check:
	$(PY) scripts/parity_check.py

daily-update:
	$(PY) scripts/daily_update.py

build-dashboard-data:
	$(PY) scripts/build_dashboard_data.py

backfill:
	$(PY) scripts/backfill_history.py

performance-report:
	$(PY) scripts/performance_report.py

model-report:
	$(PY) scripts/model_report.py --label challenger

gate-self-test:
	$(PY) scripts/promotion_gate.py self-test

diagnose-2024:
	$(PY) scripts/diagnose_2024.py
