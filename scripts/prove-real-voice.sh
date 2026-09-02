#!/usr/bin/env bash
# Prove a real-provider voice turn (Deepgram + OpenAI + Cartesia).
# Uses the programmatic onboarding sample call (no microphone required).
# If the host has DEMO_ENABLED=true, also runs POST /api/v1/demo/trust-loop.
#
# Usage:
#   # Configure Deepgram, OpenAI, and Cartesia on the target host first.
#   ./scripts/prove-real-voice.sh [base_url]
#
# Optional auth:
#   export ACCESS_TOKEN=...
#   # Or let auto mode try login, then registration:
#   export PROVE_EMAIL=you@example.com PROVE_PASSWORD=... PROVE_ORG="My Org"
#   export PROVE_AUTH_MODE=auto  # auto | login | register
set -euo pipefail

BASE_URL="${1:-http://localhost:8000}"
PROVE_EMAIL="${PROVE_EMAIL:-prove-voice-$(date +%s)@example.com}"
PROVE_PASSWORD="${PROVE_PASSWORD:-VoxForgeProveVoice!1}"
PROVE_ORG="${PROVE_ORG:-Prove Voice Org}"
PROVE_AUTH_MODE="${PROVE_AUTH_MODE:-auto}"
PROVE_REQUIRE_LIVE_MODE="${PROVE_REQUIRE_LIVE_MODE:-true}"

case "${PROVE_AUTH_MODE}" in
  auto|login|register) ;;
  *)
    echo "ERROR: PROVE_AUTH_MODE must be auto, login, or register" >&2
    exit 1
    ;;
esac
case "${PROVE_REQUIRE_LIVE_MODE}" in
  true|false) ;;
  *)
    echo "ERROR: PROVE_REQUIRE_LIVE_MODE must be true or false" >&2
    exit 1
    ;;
esac

echo "==> Health checks (${BASE_URL})"
curl -fsS "${BASE_URL}/api/v1/health" >/dev/null
ready="$(curl -sS "${BASE_URL}/api/v1/ready")"
echo "${ready}" | python3 -c 'import json,sys; d=json.load(sys.stdin); assert d.get("database")=="ok", d; assert d.get("redis")=="ok", d; print("ready:", d.get("status"))'

if demo_info="$(curl -fsS "${BASE_URL}/api/v1/demo/info" 2>/dev/null)"; then
  providers_mode="$(echo "${demo_info}" | python3 -c 'import json,sys; print(json.load(sys.stdin)["providers_mode"])')"
  echo "providers mode: ${providers_mode}"
  if [[ "${PROVE_REQUIRE_LIVE_MODE}" == "true" && "${providers_mode}" != "live" ]]; then
    echo "ERROR: Target reports providers_mode=${providers_mode}; expected live." >&2
    exit 1
  fi
elif [[ "${PROVE_REQUIRE_LIVE_MODE}" == "true" ]]; then
  echo "ERROR: Cannot verify live provider mode because /api/v1/demo/info is unavailable. Set PROVE_REQUIRE_LIVE_MODE=false only for a locked-down host whose provider configuration was verified separately." >&2
  exit 1
fi

if [[ -z "${ACCESS_TOKEN:-}" ]]; then
  login_payload="$(python3 -c 'import json,sys; print(json.dumps({"email":sys.argv[1],"password":sys.argv[2]}))' "${PROVE_EMAIL}" "${PROVE_PASSWORD}")"
  register_payload="$(python3 -c 'import json,sys; print(json.dumps({"email":sys.argv[1],"password":sys.argv[2],"full_name":"Prove Voice","org_name":sys.argv[3]}))' "${PROVE_EMAIL}" "${PROVE_PASSWORD}" "${PROVE_ORG}")"

  if [[ "${PROVE_AUTH_MODE}" != "register" ]]; then
    echo "==> Logging in as ${PROVE_EMAIL}"
    login="$(curl -sS -w $'\n%{http_code}' -X POST "${BASE_URL}/api/v1/auth/login" \
      -H "Content-Type: application/json" \
      -d "${login_payload}")"
    login_status="${login##*$'\n'}"
    login_body="${login%$'\n'*}"
    if [[ "${login_status}" =~ ^2 ]]; then
      ACCESS_TOKEN="$(echo "${login_body}" | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')"
    elif [[ "${PROVE_AUTH_MODE}" == "login" ]]; then
      echo "ERROR: Login failed with HTTP ${login_status}. Set valid PROVE_EMAIL/PROVE_PASSWORD or ACCESS_TOKEN." >&2
      exit 1
    else
      echo "==> Login unavailable (HTTP ${login_status}); trying registration"
    fi
  fi

  if [[ -z "${ACCESS_TOKEN:-}" ]]; then
    registration="$(curl -sS -w $'\n%{http_code}' -X POST "${BASE_URL}/api/v1/auth/register" \
      -H "Content-Type: application/json" \
      -d "${register_payload}")"
    registration_status="${registration##*$'\n'}"
    registration_body="${registration%$'\n'*}"
    if [[ ! "${registration_status}" =~ ^2 ]]; then
      echo "ERROR: Registration failed with HTTP ${registration_status}. Production may be invite-only; set ACCESS_TOKEN or use PROVE_AUTH_MODE=login with an existing account." >&2
      exit 1
    fi
    ACCESS_TOKEN="$(echo "${registration_body}" | python3 -c 'import json,sys; print(json.load(sys.stdin)["tokens"]["access_token"])')"
  fi
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
    print("  - {}: {}".format(m.get("role"), m.get("content", "")[:120]))
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

if curl -fsS "${BASE_URL}/api/v1/demo/info" >/dev/null 2>&1; then
  echo "==> Public trust loop (demo enabled on host)"
  loop="$(curl -sS -X POST "${BASE_URL}/api/v1/demo/trust-loop")"
  echo "${loop}" | python3 -c '
import json,sys
data=json.load(sys.stdin)
assert data.get("status")=="trust_loop_ok", data
assert data.get("session_id"), data
assert data.get("citations"), "expected citations"
assert data.get("handoff_id") or data.get("replay_url"), data
print("trust-loop session:", data["session_id"])
print("citations:", len(data.get("citations") or []))
print("replay:", data.get("replay_url"))
'
else
  echo "==> Skipping public trust loop (DEMO_ENABLED is off on host)"
fi

echo "Next: record mic demo — docs/demo/recording-checklist.md (Start talking + trust loop)"
