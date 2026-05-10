#!/usr/bin/env bash
# Daily cron entry point for MLS Prediction System.
# Add to crontab: 0 6 * * * /home/pi/mls/scripts/daily_update.sh
# News poll:      0 */6 * * * /home/pi/mls/scripts/daily_update.sh --news-only
# Closing odds:   run near kickoff windows with --closing-odds

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="${REPO_DIR}/venv"
LOG_DIR="${REPO_DIR}/logs"
LOG_FILE="${LOG_DIR}/daily_$(date +%Y%m%d).log"
ENV_FILE="${REPO_DIR}/.env"

mkdir -p "${LOG_DIR}"

# Load environment variables from .env if it exists
if [[ -f "${ENV_FILE}" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "${ENV_FILE}"
  set +a
fi

# Activate Python virtual environment
if [[ -d "${VENV_DIR}" ]]; then
  # shellcheck disable=SC1091
  source "${VENV_DIR}/bin/activate"
else
  echo "WARNING: No venv found at ${VENV_DIR}. Using system Python." | tee -a "${LOG_FILE}"
fi

cd "${REPO_DIR}"

echo "=====================================" | tee -a "${LOG_FILE}"
echo "MLS Update started at $(date -u +%Y-%m-%dT%H:%M:%SZ)" | tee -a "${LOG_FILE}"
echo "=====================================" | tee -a "${LOG_FILE}"

if [[ "${1:-}" == "--news-only" ]]; then
  echo "Running news pipeline only..." | tee -a "${LOG_FILE}"
  python -c "
import sys; sys.path.insert(0, '.')
from data_pipeline.news_monitor import run_pipeline
n = run_pipeline()
print(f'Processed {n} news items.')
" 2>&1 | tee -a "${LOG_FILE}"
elif [[ "${1:-}" == "--closing-odds" ]]; then
  echo "Fetching closing odds snapshot..." | tee -a "${LOG_FILE}"
  python -c "
import sys; sys.path.insert(0, '.')
from data_pipeline import db_utils
from data_pipeline.odds_client import sync_to_db
db_utils.initialize_schema()
n = sync_to_db(snapshot_type='close')
print(f'Synced {n} closing odds rows.')
" 2>&1 | tee -a "${LOG_FILE}"
else
  echo "Running full daily update..." | tee -a "${LOG_FILE}"
  python scripts/daily_update.py 2>&1 | tee -a "${LOG_FILE}"
fi

echo "=====================================" | tee -a "${LOG_FILE}"
echo "MLS Update finished at $(date -u +%Y-%m-%dT%H:%M:%SZ)" | tee -a "${LOG_FILE}"
echo "=====================================" | tee -a "${LOG_FILE}"
