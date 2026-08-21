#!/usr/bin/env bash
# Start the API, record /demo with Playwright, and write demo.gif assets.
#
# Requires: docker (postgres + redis), ffmpeg, playwright chromium
#
# Usage:
#   ./scripts/generate-demo-gif.sh
#
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PORT="${VOXFORGE_DEMO_PORT:-8765}"
BASE_URL="http://127.0.0.1:${PORT}"
WORK_DIR="$(mktemp -d "${TMPDIR:-/tmp}/voxforge-demo-gif.XXXXXX")"
PG_CONTAINER=""
REDIS_CONTAINER=""
PG_PORT="${VOXFORGE_PG_PORT:-5432}"
REDIS_PORT="${VOXFORGE_REDIS_PORT:-6379}"

cleanup() {
  kill "${SERVER_PID:-}" 2>/dev/null || true
  [[ -n "$PG_CONTAINER" ]] && docker rm -f "$PG_CONTAINER" >/dev/null 2>&1 || true
  [[ -n "$REDIS_CONTAINER" ]] && docker rm -f "$REDIS_CONTAINER" >/dev/null 2>&1 || true
  rm -rf "$WORK_DIR"
}
trap cleanup EXIT

port_open() {
  local port="$1"
  ! lsof -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1
}

start_ephemeral_db() {
  if port_open 5432 && port_open 6379; then
    echo "==> Starting postgres + redis via docker compose"
    docker compose up -d postgres redis >/dev/null
    for _ in $(seq 1 40); do
      if docker compose exec -T postgres pg_isready -U voxforge >/dev/null 2>&1 \
        && docker compose exec -T redis redis-cli ping 2>/dev/null | grep -q PONG; then
        return
      fi
      sleep 0.5
    done
    return
  fi

  PG_PORT=5433
  REDIS_PORT=6380
  while ! port_open "$PG_PORT"; do PG_PORT=$((PG_PORT + 1)); done
  while ! port_open "$REDIS_PORT"; do REDIS_PORT=$((REDIS_PORT + 1)); done

  echo "==> Default DB ports busy — ephemeral postgres:${PG_PORT} redis:${REDIS_PORT}"
  PG_CONTAINER="voxforge-demo-gif-pg-$$"
  REDIS_CONTAINER="voxforge-demo-gif-redis-$$"
  docker run -d --name "$PG_CONTAINER" \
    -e POSTGRES_USER=voxforge -e POSTGRES_PASSWORD=voxforge -e POSTGRES_DB=voxforge \
    -p "${PG_PORT}:5432" pgvector/pgvector:pg16 >/dev/null
  docker run -d --name "$REDIS_CONTAINER" -p "${REDIS_PORT}:6379" redis:7-alpine >/dev/null
  for _ in $(seq 1 60); do
    if docker exec "$PG_CONTAINER" pg_isready -U voxforge >/dev/null 2>&1 \
      && docker exec "$REDIS_CONTAINER" redis-cli ping 2>/dev/null | grep -q PONG; then
      break
    fi
    sleep 0.5
  done
}

start_ephemeral_db
export DATABASE_URL="postgresql+asyncpg://voxforge:voxforge@localhost:${PG_PORT}/voxforge"
export REDIS_URL="redis://localhost:${REDIS_PORT}/0"
export API_KEY_HASH_PEPPER="${API_KEY_HASH_PEPPER:-demo-gif-pepper-value}"

PYTHON="${ROOT}/.venv/bin/python"
if [[ ! -x "$PYTHON" ]]; then
  PYTHON="$(command -v python3)"
fi

export DEMO_ENABLED="${DEMO_ENABLED:-true}"
export STT_PROVIDER="${STT_PROVIDER:-mock}"
export LLM_PROVIDER="${LLM_PROVIDER:-mock}"
export TTS_PROVIDER="${TTS_PROVIDER:-mock}"
export EMBEDDING_PROVIDER="${EMBEDDING_PROVIDER:-mock}"
export MEMORY_ENABLED="${MEMORY_ENABLED:-false}"
export RATE_LIMIT_ENABLED="${RATE_LIMIT_ENABLED:-false}"
export JWT_SECRET_KEY="${JWT_SECRET_KEY:-demo-gif-secret-key-32-chars-min}"

echo "==> Running migrations"
"$PYTHON" -m alembic upgrade head

echo "==> Starting API on $BASE_URL"
"$PYTHON" -m uvicorn voxforge.main:app --host 127.0.0.1 --port "$PORT" --app-dir src &
SERVER_PID=$!

for _ in $(seq 1 40); do
  if curl -fsS "$BASE_URL/api/v1/health" >/dev/null 2>&1; then
    break
  fi
  sleep 0.5
done
curl -fsS "$BASE_URL/api/v1/health" >/dev/null

echo "==> Installing Playwright chromium (if needed)"
"$PYTHON" -m playwright install chromium

echo "==> Recording /demo quickstart"
export VOXFORGE_DEMO_BASE_URL="$BASE_URL"
RECORDING="$("$PYTHON" "$ROOT/scripts/record_demo_gif.py" --output-dir "$WORK_DIR")"

echo "==> Converting recording to GIF"
"$ROOT/scripts/capture-demo-gif.sh" "$RECORDING"

echo "==> Done — commit docs/assets/screenshots/demo.gif and public/assets/screenshots/demo.gif"
