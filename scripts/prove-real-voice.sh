#!/usr/bin/env bash
# Prove a real-provider voice turn (Deepgram + OpenAI + Cartesia).
# Uses the programmatic onboarding sample call (no microphone required).
#
# Usage:
#   export DEEPGRAM_API_KEY=... OPENAI_API_KEY=... CARTESIA_API_KEY=...
#   export STT_PROVIDER=deepgram LLM_PROVIDER=openai TTS_PROVIDER=cartesia
#   export DEMO_ENABLED=false   # on the server under test
#   ./scripts/prove-real-voice.sh [base_url]
#
# Optional auth (auto-register if unset):
#   export PROVE_EMAIL=you@example.com PROVE_PASSWORD=... PROVE_ORG="My Org"
set -euo pipefail

BASE_URL="${1:-http://localhost:8000}"
PROVE_EMAIL="${PROVE_EMAIL:-prove-voice-$(date +%s)@example.com}"
PROVE_PASSWORD="${PROVE_PASSWORD:-VoxForgeProveVoice!1}"
PROVE_ORG="${PROVE_ORG:-Prove Voice Org}"

need_var() {
  if [[ -z "${!1:-}" ]]; then
    echo "ERROR: $1 is required" >&2
    exit 1
  fi
}

need_var DEEPGRAM_API_KEY
need_var OPENAI_API_KEY
need_var CARTESIA_API_KEY

echo "==> Health checks (${BASE_URL})"
curl -fsS "${BASE_URL}/api/v1/health" >/dev/null
ready="$(curl -sS "${BASE_URL}/api/v1/ready")"
echo "${ready}" | python3 -c 'import json,sys; d=json.load(sys.stdin); assert d.get("database")=="ok", d; assert d.get("redis")=="ok", d; print("ready:", d.get("status"))'

if [[ -z "${ACCESS_TOKEN:-}" ]]; then
  echo "==> Registering ${PROVE_EMAIL}"
  reg="$(curl -sS -X POST "${BASE_URL}/api/v1/auth/register" \
    -H "Content-Type: application/json" \
    -d "{\"email\":\"${PROVE_EMAIL}\",\"password\":\"${PROVE_PASSWORD}\",\"full_name\":\"Prove Voice\",\"org_name\":\"${PROVE_ORG}\"}")"
  ACCESS_TOKEN="$(echo "${reg}" | python3 -c 'import json,sys; print(json.load(sys.stdin)["tokens"]["access_token"])')"
fi

echo "==> Running onboarding sample call (real providers on server)"
resp="$(curl -fsS -X POST "${BASE_URL}/api/v1/onboarding/run-sample-call" \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  -H "Content-Type: application/json")"

session_id="$(echo "${resp}" | python3 -c '
import json,sys
data=json.load(sys.stdin)
assert data.get("status")=="test_call_passed", data
print(data["test_session_id"])
')"

echo "==> Session ${session_id}"
messages="$(curl -fsS "${BASE_URL}/api/v1/sessions/${session_id}/messages" \
  -H "Authorization: Bearer ${ACCESS_TOKEN}")"
echo "${messages}" | python3 -c '
import json,sys
data=json.load(sys.stdin)
msgs=data.get("messages", [])
print(f"messages: {len(msgs)}")
for m in msgs[-4:]:
    print(f"  - {m.get('role')}: {m.get('content','')[:120]}")
'

evals="$(curl -fsS "${BASE_URL}/api/v1/sessions/${session_id}/evaluations" \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" 2>/dev/null || echo '{"evaluations":[]}')"
echo "${evals}" | python3 -c '
import json,sys
data=json.load(sys.stdin)
ev=data.get("evaluations") or []
if not ev:
    print("evaluations: (none or disabled)")
else:
    last=ev[-1]
    print("evaluations:", len(ev), "last_score:", last.get("overall_score"))
' || true

echo ""
echo "OK: real-provider programmatic voice turn passed."
echo "Next: record mic demo — docs/demo/recording-checklist.md (real providers section)"
