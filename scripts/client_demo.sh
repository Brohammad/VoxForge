#!/usr/bin/env bash
# Client-facing full demo launcher for VoxForge.
# Prepares the stack, warms the pipeline, opens browser tabs, prints cue cards.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

BASE_URL="${BASE_URL:-http://127.0.0.1:8000}"
HOST_PORT="${HOST_PORT:-8000}"
OPEN_BROWSER="${OPEN_BROWSER:-1}"
DEMO_EMAIL="${DEMO_EMAIL:-demo@voxforge.io}"
DEMO_PASSWORD="${DEMO_PASSWORD:-VoxForgeDemo!}"

bold() { printf '\n\033[1m%s\033[0m\n' "$*"; }
ok()   { printf '  \033[32m✓\033[0m %s\n' "$*"; }
info() { printf '  → %s\n' "$*"; }
warn() { printf '  \033[33m!\033[0m %s\n' "$*"; }
fail() { printf '  \033[31m✗\033[0m %s\n' "$*"; exit 1; }

need() {
  command -v "$1" >/dev/null 2>&1 || fail "Missing dependency: $1"
}

need curl
need docker
need python3

[[ -d .venv ]] || fail "Missing .venv — run: uv sync"
[[ -f .env ]] || fail "Missing .env — run: cp .env.example .env"

# Ensure demo + mock providers (client-safe defaults)
ensure_env_key() {
  local key="$1" val="$2"
  if grep -q "^${key}=" .env 2>/dev/null; then
    # leave existing values
    return 0
  fi
  echo "${key}=${val}" >> .env
}

ensure_env_key DEMO_ENABLED true
ensure_env_key STT_PROVIDER mock
ensure_env_key LLM_PROVIDER mock
ensure_env_key TTS_PROVIDER mock
ensure_env_key EMBEDDING_PROVIDER mock

bold "1) Infrastructure"
info "Starting Postgres + Redis…"
docker info >/dev/null 2>&1 || fail "Docker is not running — open Docker Desktop, then re-run this script"
docker compose up -d postgres redis >/dev/null
for i in $(seq 1 40); do
  if docker compose exec -T postgres pg_isready -U voxforge >/dev/null 2>&1 \
     && docker compose exec -T redis redis-cli ping 2>/dev/null | grep -q PONG; then
    ok "Postgres + Redis healthy"
    break
  fi
  sleep 1
  [[ $i -eq 40 ]] && fail "Database/Redis did not become ready"
done

bold "2) Database + demo account"
.venv/bin/alembic upgrade head >/dev/null
.venv/bin/python scripts/ensure_demo_account.py >/dev/null || true
ok "Migrations + demo account ready ($DEMO_EMAIL)"

bold "3) API server"
if curl -sf "$BASE_URL/api/v1/health" >/dev/null 2>&1; then
  ok "Server already running at $BASE_URL"
else
  info "Starting uvicorn on :$HOST_PORT…"
  # shellcheck disable=SC2086
  nohup .venv/bin/uvicorn voxforge.main:app --host 127.0.0.1 --port "$HOST_PORT" --app-dir src \
    > /tmp/voxforge-client-demo.log 2>&1 &
  echo $! > /tmp/voxforge-client-demo.pid
  for i in $(seq 1 30); do
    if curl -sf "$BASE_URL/api/v1/health" >/dev/null 2>&1; then
      ok "Server up (pid $(cat /tmp/voxforge-client-demo.pid))"
      break
    fi
    sleep 0.5
    [[ $i -eq 30 ]] && fail "Server failed to start — see /tmp/voxforge-client-demo.log"
  done
fi

READY=$(curl -sf "$BASE_URL/api/v1/ready" || true)
echo "$READY" | python3 -c 'import json,sys; d=json.load(sys.stdin); assert d.get("status")=="ok" and d.get("database")=="ok"' \
  || fail "Ready check failed: $READY"
ok "Ready check passed"

bold "4) Warm the pipeline (so the live click is fast)"
WARM=$(curl -sf -X POST "$BASE_URL/api/v1/demo/quickstart" -H 'Content-Type: application/json' -d '{}')
echo "$WARM" | python3 -m json.tool
STATUS=$(echo "$WARM" | python3 -c 'import json,sys; print(json.load(sys.stdin)["status"])')
E2E=$(echo "$WARM" | python3 -c 'import json,sys; print(round(json.load(sys.stdin).get("e2e_ms") or 0, 1))')
[[ "$STATUS" == "test_call_passed" ]] || fail "Warm demo failed: $STATUS"
ok "Warm call passed in ${E2E}ms"

if [[ "$OPEN_BROWSER" == "1" ]]; then
  bold "5) Opening client tabs"
  if command -v open >/dev/null 2>&1; then
    open "$BASE_URL/"
    sleep 0.4
    open "$BASE_URL/demo"
    sleep 0.4
    open "$BASE_URL/dashboard"
    sleep 0.4
    open "$BASE_URL/api/v1/docs"
    ok "Opened landing · demo · dashboard · API docs"
  else
    warn "Could not auto-open browser — use the URLs below"
  fi
fi

bold "══════════════════════════════════════════════════════"
bold "  CLIENT DEMO — 8 MINUTE CUE CARD"
bold "══════════════════════════════════════════════════════"

cat <<EOF

  Login for dashboard:  $DEMO_EMAIL  /  $DEMO_PASSWORD
  Base URL:             $BASE_URL

  ────────────────────────────────────────────────────
  0:00  HOOK (landing — $BASE_URL/)
  ────────────────────────────────────────────────────
  Say: "VoxForge is self-hosted voice AI infrastructure —
        not a chatbot wrapper. One production pipeline for
        WebSocket, onboarding APIs, and LiveKit WebRTC,
        with evaluation and replay built in."

  Point at: brand hero, architecture section if scrolled.

  ────────────────────────────────────────────────────
  0:30  LIVE CALL (demo — $BASE_URL/demo)
  ────────────────────────────────────────────────────
  Do:   Click "Run one-click sample call" OR type a message in Live chat
  Show: assistant text + audio control plays Cartesia TTS
  Say:  "Same VoicePipelineService as production: LLM turn, then
         Cartesia speaks the reply in-browser. Type follow-ups for
         multi-turn. (Skip LiveKit Unmute on Safari locally — WebRTC
         through Docker is flaky; this /demo path is the reliable proof.)"

  ────────────────────────────────────────────────────
  2:00  OPERATOR CONSOLE (dashboard)
  ────────────────────────────────────────────────────
  Do:   Login → Overview → Sessions → open latest → Replay
  Show: messages, latency breakdown, evaluation scores, outcome
  Say:  "Operators get full session replay — not a black box.
         Every turn is scored for latency, quality, and cost."

  Also flash: Latency tab · Evaluations tab

  ────────────────────────────────────────────────────
  4:00  KNOWLEDGE (RAG)
  ────────────────────────────────────────────────────
  Do:   Knowledge Base → create/open collection → upload a TXT/PDF
  Say:  "Ground answers in your docs. Chunks + embeddings feed the
         agent mid-call so replies cite your policy, not invent it."

  ────────────────────────────────────────────────────
  5:30  HANDOFF
  ────────────────────────────────────────────────────
  Do:   Handoffs section
  Say:  "When confidence drops or policy says escalate, we queue a
         human handoff with signed replay context — agent picks up
         where the voice bot left off."

  ────────────────────────────────────────────────────
  6:30  ARCHITECTURE + TRUST
  ────────────────────────────────────────────────────
  Say:  "Transport → Pipeline → LangGraph orchestrator → tools/RAG
         → evaluation on every turn. Deploy with Docker Compose.
         Clone to first demo in ~15 minutes. Open source (MIT)."

  Optional: show $BASE_URL/api/v1/docs for API surface.

  ────────────────────────────────────────────────────
  7:30  CLOSE / CTA
  ────────────────────────────────────────────────────
  Say:  "RC is live. Looking for design partners.
         Next step: pilot on your stack — your LLM, your KB, your SSO."
  Offer: GitHub star · /demo link · schedule pilot kickoff

══════════════════════════════════════════════════════
  PRE-FLIGHT CHECKLIST (before the call)
══════════════════════════════════════════════════════
  [ ] Docker Desktop running
  [ ] This script finished green
  [ ] Tabs open: landing | demo | dashboard (logged in) | docs
  [ ] Run demo once yourself so the click is warm
  [ ] Hide bookmarks bar · zoom 110% · silence notifications
  [ ] Know audience: CTO → self-host/security · Ops → replay/handoff

  Re-warm only:   curl -X POST $BASE_URL/api/v1/demo/quickstart -H 'Content-Type: application/json' -d '{}'
  Stop API later: kill \$(cat /tmp/voxforge-client-demo.pid) 2>/dev/null

EOF

ok "You're ready — share your screen and start at 0:00"
