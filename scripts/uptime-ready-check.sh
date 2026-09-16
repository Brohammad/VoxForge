#!/usr/bin/env bash
# Poll /api/v1/ready and optionally notify Slack on failure.
#
# Usage:
#   ./scripts/uptime-ready-check.sh https://your-domain.example
#   SLACK_WEBHOOK_URL=https://hooks.slack.com/... ./scripts/uptime-ready-check.sh
#   FAIL_ON_DEGRADED=true ./scripts/uptime-ready-check.sh https://your-domain.example
#
# Cron example (every 5 minutes):
#   */5 * * * * SLACK_WEBHOOK_URL=... /path/to/VoxForge/scripts/uptime-ready-check.sh https://voxforge.example.com
set -euo pipefail

BASE_URL="${1:-http://localhost:8000}"
READY_URL="${BASE_URL%/}/api/v1/ready"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

notify_slack() {
  local message="$1"
  if [[ -z "${SLACK_WEBHOOK_URL:-}" ]]; then
    return 0
  fi
  curl -fsS -X POST "${SLACK_WEBHOOK_URL}" \
    -H "Content-Type: application/json" \
    -d "$(python3 -c 'import json, sys; print(json.dumps({"text": sys.argv[1]}))' "$message")"
}

if ! response="$(curl -fsS "${READY_URL}" 2>&1)"; then
  notify_slack "VoxForge ready check failed (HTTP): ${READY_URL}"
  echo "FAIL: ${response}" >&2
  exit 1
fi

if ! echo "${response}" | python3 "${SCRIPT_DIR}/uptime_ready_eval.py"; then
  notify_slack "VoxForge ready check failed (JSON): ${READY_URL} — ${response}"
  echo "FAIL: ${response}" >&2
  exit 1
fi

echo "OK: ${READY_URL}"
