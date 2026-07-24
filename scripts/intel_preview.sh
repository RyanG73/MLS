#!/usr/bin/env bash
# Open a fresh signed-in Intel preview for design review.
#
# Why this exists: getting into Intel locally needs four things lined up — the
# API running, CORS allowing the webapp's port, a seeded account on a paid
# plan, and a magic-link token. Magic-link tokens are ONE-TIME USE
# (verify_magic_link deletes before returning), so a lost session can never be
# recovered by revisiting the old URL. This restarts the API and mints a new
# link every time.
#
#   ./scripts/intel_preview.sh              # creator plan, port 8123
#   ./scripts/intel_preview.sh free         # seed a free account instead
#   ./scripts/intel_preview.sh creator 8000 # different webapp port
#
# Sessions last 1 hour. Re-run when it expires.
set -euo pipefail

PLAN="${1:-creator}"
PORT="${2:-8123}"
SITE="http://localhost:${PORT}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG="${TMPDIR:-/tmp}/entenser-intel-preview.log"

cd "$ROOT"
PY="venv/bin/python"; [ -x "$PY" ] || PY="python3"

pkill -f dev_intelligence_server >/dev/null 2>&1 || true
sleep 1

ADMIN_TOKEN="${ADMIN_TOKEN:-local-dev-admin}" \
ALLOWED_ORIGINS="${SITE},http://127.0.0.1:${PORT},https://entenser.com" \
PYTHONPATH=. "$PY" scripts/dev_intelligence_server.py \
  --site-url "$SITE" --seed-plan "$PLAN" > "$LOG" 2>&1 &

for _ in $(seq 1 20); do sleep 0.5; [ -s "$LOG" ] && break; done

if ! grep -q preview_url "$LOG" 2>/dev/null; then
  echo "API failed to start. Log:" >&2; cat "$LOG" >&2; exit 1
fi

"$PY" - "$LOG" "$PLAN" <<'PYEOF'
import json, sys
d = json.load(open(sys.argv[1]))
print(f"\n  Plan:  {d['plan']}\n  API:   {d['url']}\n  Admin: ADMIN_TOKEN=local-dev-admin\n")
print("  Open this (one-time link, session lasts 1 hour):\n")
print(f"  {d['preview_url']}\n")
PYEOF
