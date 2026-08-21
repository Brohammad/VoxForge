#!/usr/bin/env bash
# Start API server and run Playwright browser tests.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PORT="${VOXFORGE_BROWSER_PORT:-8765}"
BASE_URL="http://127.0.0.1:${PORT}"
export VOXFORGE_BROWSER_BASE_URL="$BASE_URL"

PYTHON="${ROOT}/.venv/bin/python"
if [[ ! -x "$PYTHON" ]]; then
  PYTHON="$(command -v python3)"
fi

export DATABASE_URL="${DATABASE_URL:-postgresql+asyncpg://voxforge:voxforge@localhost:5432/voxforge}"
export REDIS_URL="${REDIS_URL:-redis://localhost:6379/0}"
export DEMO_ENABLED="${DEMO_ENABLED:-true}"
export STT_PROVIDER="${STT_PROVIDER:-mock}"
export LLM_PROVIDER="${LLM_PROVIDER:-mock}"
export TTS_PROVIDER="${TTS_PROVIDER:-mock}"
export EMBEDDING_PROVIDER="${EMBEDDING_PROVIDER:-mock}"
export KNOWLEDGE_WORKER_ENABLED="${KNOWLEDGE_WORKER_ENABLED:-false}"
export JWT_SECRET_KEY="${JWT_SECRET_KEY:-browser-test-secret-key-32-chars-min}"
export API_KEY_HASH_PEPPER="${API_KEY_HASH_PEPPER:-browser-test-pepper-value}"
export AUTH_REQUIRED="${AUTH_REQUIRED:-true}"
export RATE_LIMIT_ENABLED="${RATE_LIMIT_ENABLED:-false}"

echo "==> Running migrations"
"$PYTHON" -m alembic upgrade head

echo "==> Starting API on $BASE_URL"
"$PYTHON" -m uvicorn voxforge.main:app --host 127.0.0.1 --port "$PORT" --app-dir src &
SERVER_PID=$!
trap 'kill "$SERVER_PID" 2>/dev/null || true' EXIT

for _ in $(seq 1 40); do
  if curl -fsS "$BASE_URL/api/v1/health" >/dev/null 2>&1; then
    break
  fi
  sleep 0.5
done

curl -fsS "$BASE_URL/api/v1/health" >/dev/null || {
  echo "ERROR: API failed to start on $BASE_URL" >&2
  exit 1
}

echo "==> Installing Playwright browser (chromium)"
"$PYTHON" -m playwright install chromium

echo "==> Running browser tests"
"$PYTHON" -m pytest tests/browser -v --tb=short -m browser
