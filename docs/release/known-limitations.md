# Known Limitations (RC-1)

## Voice

- **Microphone / real STT streaming** — Public `/demo` has Start talking (PCM16 WAV + optional Web Speech). WebSocket lifecycle is tested; live microphone capture is not automated in CI.
- **Barge-in** — Not exercised in automated browser tests.
- **LiveKit worker** — Requires external LiveKit Cloud or self-hosted server; optional compose profile.
- **Real-provider proof** — Public demo uses mock providers by default; run [scripts/prove-real-voice.sh](../../scripts/prove-real-voice.sh) with API keys for a real stack check.

## Integrations

- **Zendesk / Freshdesk** — Removed from the provider factory until implemented; use `mock` ticketing or export handoffs via replay/API.
- **Invite email** — Resend and SMTP are supported via `EMAIL_PROVIDER`; default `log` mode returns the token in the API for local dev.
- **MCP servers** — Require `pip install -e ".[mcp]"` in production image when `MCP_SERVERS_CONFIG` is set.

## Operations

- **Single uvicorn worker** — Production compose uses one worker by design; see scaling notes before multi-instance deploy.
- **Grafana** — Bound to localhost; requires SSH tunnel for remote access.
- **Degraded readiness** — `/api/v1/ready` returns HTTP 200 when optional deps fail unless `READY_FAIL_ON_DEGRADED=true`.

## Security

- **Dashboard auth** — Login uses HttpOnly cookies + CSRF for mutating requests. Pasting a JWT still stores it in `localStorage` as a Bearer override for API debugging only.
- **Open registration** — No email verification. Disable with `REGISTRATION_ENABLED=false` (default in `.env.production.example`); new users join via org invite. Production validation rejects open registration when `DEMO_ENABLED=false`.

## Documentation

- Screenshots and demo GIF should be refreshed after a real-provider voice recording is captured.
