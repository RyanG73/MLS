#!/usr/bin/env bash
# Daily PostgreSQL backup. Add to cron:
#   0 5 * * * /home/ryang/mls/scripts/backup_db.sh
#
# Backups: /home/ryang/mls/backups/mls_YYYYMMDD.sql.gz
# Retains 30 days, deletes older.

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKUP_DIR="${REPO_DIR}/backups"
ENV_FILE="${REPO_DIR}/.env"
TODAY="$(date +%Y%m%d)"
RETENTION_DAYS=30

mkdir -p "${BACKUP_DIR}"

if [[ -f "${ENV_FILE}" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "${ENV_FILE}"
  set +a
fi

PG_HOST="${PG_HOST:-127.0.0.1}"
PG_PORT="${PG_PORT:-5432}"
PG_USER="${PG_USER:-ryang}"
PG_DBNAME="${PG_DBNAME:-mls}"

OUTPUT="${BACKUP_DIR}/mls_${TODAY}.sql.gz"
echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Backing up ${PG_DBNAME} → ${OUTPUT}"

PGPASSWORD="${PG_PASSWORD:-}" pg_dump \
  -h "${PG_HOST}" \
  -p "${PG_PORT}" \
  -U "${PG_USER}" \
  -d "${PG_DBNAME}" \
  --no-owner \
  --no-acl \
  | gzip > "${OUTPUT}"

# Remove backups older than retention period
find "${BACKUP_DIR}" -maxdepth 1 -name 'mls_*.sql.gz' -type f -mtime +${RETENTION_DAYS} -delete

echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Backup complete. Files retained: $(ls -1 "${BACKUP_DIR}" | wc -l)"
