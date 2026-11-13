# Hello Voice (no LiveKit)

Minimal curl walkthrough: register → create session → onboarding sample call.

## Prerequisites

```bash
# App running with mock providers (see README quick start)
export BASE_URL=http://localhost:8000
```

## 1. Register

```bash
curl -sS -X POST "$BASE_URL/api/v1/auth/register" \
  -H 'Content-Type: application/json' \
  -d '{
    "email": "hello@example.com",
    "password": "securepass123",
    "full_name": "Hello Voice",
    "org_name": "Hello Org"
  }' | tee /tmp/voxforge-register.json
```

Abbreviated success body (tokens are shortened; yours will differ):

```json
{
  "user_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "org_id": "550e8400-e29b-41d4-a716-446655440001",
  "email": "hello@example.com",
  "full_name": "Hello Voice",
  "org_name": "Hello Org",
  "tokens": {
    "access_token": "eyJ…",
    "refresh_token": "eyJ…",
    "token_type": "bearer"
  }
}
```

Mock providers work without paid API keys. The public `/demo` quick path still requires `DEMO_ENABLED=true` on the server.

```bash
export TOKEN=$(python3 -c 'import json; print(json.load(open("/tmp/voxforge-register.json"))["tokens"]["access_token"])')
```

## 2. Health

```bash
curl -sS "$BASE_URL/api/v1/health"
curl -sS "$BASE_URL/api/v1/ready"
```

## 3. Sample voice turn (programmatic pipeline)

```bash
curl -sS -X POST "$BASE_URL/api/v1/onboarding/run-sample-call" \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json'
```

Expect `"status": "test_call_passed"` and a `test_session_id`.

Example `run-sample-call` body:

```json
{
  "id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "status": "test_call_passed",
  "connected_at": null,
  "test_session_id": "550e8400-e29b-41d4-a716-446655440000",
  "completed_at": "2026-11-09T12:00:00+00:00"
}
```

## 4. Inspect the session

```bash
SESSION_ID=$(python3 -c 'import json,sys; print(json.load(sys.stdin)["test_session_id"])' \
  <<< "$(curl -sS -X POST "$BASE_URL/api/v1/onboarding/run-sample-call" \
        -H "Authorization: Bearer $TOKEN")")

curl -sS "$BASE_URL/api/v1/sessions/$SESSION_ID/messages" \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
```

## Next

- Browser demo: `$BASE_URL/demo`
- WebRTC: [../livekit-client](../livekit-client)
- Real providers: [../../scripts/prove-real-voice.sh](../../scripts/prove-real-voice.sh)
