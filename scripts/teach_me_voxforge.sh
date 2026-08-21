#!/usr/bin/env bash
# One-day hands-on teaching demo for VoxForge.
# Runs live against a local server and prints what each step teaches.
set -euo pipefail

BASE_URL="${BASE_URL:-http://127.0.0.1:8000}"
WORKDIR="${TMPDIR:-/tmp}/voxforge-teach-$$"
mkdir -p "$WORKDIR"
trap 'rm -rf "$WORKDIR"' EXIT

bold() { printf '\n\033[1m%s\033[0m\n' "$*"; }
ok()   { printf '  \033[32m✓\033[0m %s\n' "$*"; }
info() { printf '  → %s\n' "$*"; }
note() { printf '  \033[36mWhy:\033[0m %s\n' "$*"; }

need() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing dependency: $1" >&2
    exit 1
  fi
}

need curl
need python3

json_get() {
  python3 -c 'import json,sys; d=json.load(sys.stdin)
path=sys.argv[1].split(".")
cur=d
for p in path:
  if isinstance(cur, list):
    cur=cur[int(p)]
  else:
    cur=cur[p]
print(cur if cur is not None else "")' "$1"
}

bold "VoxForge — One-Day Teaching Demo"
info "Target: $BASE_URL"
info "This walks the full product spine with mock providers (no API keys)."

# ---------------------------------------------------------------------------
bold "STEP 0 — Health (is the platform alive?)"
note "Health = process up. Ready = DB + Redis connected."
curl -sS "$BASE_URL/api/v1/health" | tee "$WORKDIR/health.json" | python3 -m json.tool
STATUS=$(json_get status < "$WORKDIR/health.json")
[[ "$STATUS" == "ok" ]] && ok "Health OK" || { echo "Health failed"; exit 1; }
curl -sS "$BASE_URL/api/v1/ready" | tee "$WORKDIR/ready.json" | python3 -m json.tool
READY=$(json_get status < "$WORKDIR/ready.json")
[[ "$READY" == "ok" ]] && ok "Ready OK (Postgres + Redis)" || { echo "Ready failed — start docker compose postgres/redis"; exit 1; }

# ---------------------------------------------------------------------------
bold "STEP 1 — Public demo quickstart (visitor path, no login)"
note "POST /demo/quickstart runs STT → agent → TTS → evaluation on a scripted turn."
note "Same VoicePipelineService used by WebSocket and LiveKit."
curl -sS -X POST "$BASE_URL/api/v1/demo/quickstart" \
  -H 'Content-Type: application/json' \
  -d '{}' | tee "$WORKDIR/demo.json" | python3 -m json.tool
DEMO_STATUS=$(json_get status < "$WORKDIR/demo.json" 2>/dev/null || true)
SESSION_FROM_DEMO=$(json_get session_id < "$WORKDIR/demo.json" 2>/dev/null || true)
E2E_MS=$(json_get e2e_ms < "$WORKDIR/demo.json" 2>/dev/null || true)
ok "Demo status: ${DEMO_STATUS:-unknown}  e2e_ms=${E2E_MS:-n/a}"
info "Session: ${SESSION_FROM_DEMO:-n/a}"
info "Open UI: $BASE_URL/demo"

# ---------------------------------------------------------------------------
bold "STEP 2 — Register a real org (developer path)"
note "Auth creates a user + organization. JWT unlocks sessions, knowledge, dashboard."
EMAIL="teach-$(date +%s)@example.com"
curl -sS -X POST "$BASE_URL/api/v1/auth/register" \
  -H 'Content-Type: application/json' \
  -d "{\"email\":\"$EMAIL\",\"password\":\"TeachMeVox123!\",\"full_name\":\"Teach Me\",\"org_name\":\"Teach Org\"}" \
  | tee "$WORKDIR/register.json" | python3 -m json.tool
TOKEN=$(json_get tokens.access_token < "$WORKDIR/register.json")
ORG_ID=$(json_get org_id < "$WORKDIR/register.json")
USER_ID=$(json_get user_id < "$WORKDIR/register.json")
ok "Registered $EMAIL"
info "user=$USER_ID org=$ORG_ID"
export TOKEN

# ---------------------------------------------------------------------------
bold "STEP 3 — Onboarding sample call (programmatic voice turn)"
note "No microphone needed. Great for CI and first-call verification."
curl -sS -X POST "$BASE_URL/api/v1/onboarding/run-sample-call" \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  | tee "$WORKDIR/sample.json" | python3 -m json.tool
SAMPLE_STATUS=$(json_get status < "$WORKDIR/sample.json")
SESSION_ID=$(json_get test_session_id < "$WORKDIR/sample.json")
ok "Sample call: $SAMPLE_STATUS"
info "session_id=$SESSION_ID"

# ---------------------------------------------------------------------------
bold "STEP 4 — Inspect transcript + evaluations"
note "Every turn is scored (latency, quality, cost) and stored for replay."
curl -sS "$BASE_URL/api/v1/sessions/$SESSION_ID/messages" \
  -H "Authorization: Bearer $TOKEN" \
  | tee "$WORKDIR/messages.json" | python3 -m json.tool
ok "Messages fetched"

curl -sS "$BASE_URL/api/v1/sessions/$SESSION_ID/evaluations" \
  -H "Authorization: Bearer $TOKEN" \
  | tee "$WORKDIR/evals.json" | python3 -m json.tool || true
ok "Evaluations fetched (if enabled)"

curl -sS "$BASE_URL/api/v1/sessions/$SESSION_ID/replay" \
  -H "Authorization: Bearer $TOKEN" \
  | tee "$WORKDIR/replay.json" | python3 -m json.tool | head -80
ok "Replay payload ready for operators"

# ---------------------------------------------------------------------------
bold "STEP 5 — Knowledge base (RAG grounding)"
note "Upload docs → chunk/embed → search. Hits are injected into the voice pipeline."
curl -sS -X POST "$BASE_URL/api/v1/knowledge/collections" \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"name":"Teach FAQ"}' \
  | tee "$WORKDIR/collection.json" | python3 -m json.tool || true

COLLECTION_ID=$(json_get id < "$WORKDIR/collection.json" 2>/dev/null || true)
if [[ -n "${COLLECTION_ID:-}" ]]; then
  cat > "$WORKDIR/faq.txt" <<'EOF'
VoxForge refund policy: refunds within 30 days with order ID.
Billing support hours: Monday-Friday 9am-6pm IST.
To escalate, ask for a human agent and provide your account email.
EOF
  curl -sS -X POST "$BASE_URL/api/v1/knowledge/collections/$COLLECTION_ID/documents" \
    -H "Authorization: Bearer $TOKEN" \
    -F "file=@$WORKDIR/faq.txt" \
    -F "title=Teach FAQ" \
    | tee "$WORKDIR/doc.json" | python3 -m json.tool || true
  ok "Document uploaded to collection $COLLECTION_ID (async ingest job)"

  sleep 2
  curl -sS -X POST "$BASE_URL/api/v1/knowledge/search" \
    -H "Authorization: Bearer $TOKEN" \
    -H 'Content-Type: application/json' \
    -d "{\"query\":\"What is the refund policy?\",\"collection_id\":\"$COLLECTION_ID\",\"limit\":3}" \
    | tee "$WORKDIR/search.json" | python3 -m json.tool || true
  ok "Semantic search exercised (mock embeddings OK for local teaching)"
else
  info "Collection create failed — check response / dashboard Knowledge UI"
fi

# ---------------------------------------------------------------------------
bold "STEP 6 — Tools + handoff surface"
note "Agents can call tools; low confidence / policy can escalate to humans."
curl -sS "$BASE_URL/api/v1/tools" \
  -H "Authorization: Bearer $TOKEN" \
  | tee "$WORKDIR/tools.json" | python3 -m json.tool | head -60 || true
ok "Tools listed"

curl -sS "$BASE_URL/api/v1/handoffs" \
  -H "Authorization: Bearer $TOKEN" \
  | tee "$WORKDIR/handoffs.json" | python3 -m json.tool | head -40 || true
ok "Handoff queue readable"

# ---------------------------------------------------------------------------
bold "STEP 7 — Dashboard APIs (operator console)"
note "Dashboard UI at /dashboard is a static SPA over these endpoints."
for path in overview sessions latency evaluations activity; do
  CODE=$(curl -sS -o "$WORKDIR/dash-$path.json" -w '%{http_code}' \
    "$BASE_URL/api/v1/dashboard/$path" \
    -H "Authorization: Bearer $TOKEN" || true)
  info "/dashboard/$path → HTTP $CODE"
done
ok "Open UI: $BASE_URL/dashboard  (login with $EMAIL / TeachMeVox123!)"

# ---------------------------------------------------------------------------
bold "STEP 8 — What to click next in the browser"
cat <<EOF
  1. $BASE_URL/            Landing — product story
  2. $BASE_URL/demo        One-click pipeline (same as Step 1)
  3. $BASE_URL/dashboard   Login → Overview → Sessions → Replay
  4. $BASE_URL/api/v1/docs Interactive OpenAPI (try endpoints)
  5. Knowledge section     Upload more docs, search, reindex
  6. Handoffs              Accept/complete escalations
  7. Latency / Evaluations Per-turn quality & cost

Architecture spine to remember:
  Client → Transport (REST demo / WS / LiveKit)
        → VoicePipelineService (STT → Agent → TTS)
        → LangGraph orchestrator + tools + RAG + memory
        → Evaluation → Replay / Handoff / Dashboard
EOF

bold "DONE — teaching run complete"
info "Artifacts saved under $WORKDIR (copied summary below if needed)"
info "Re-run anytime: BASE_URL=$BASE_URL bash scripts/teach_me_voxforge.sh"
