# External uptime monitoring

VoxForge exposes liveness and readiness for free uptime monitors (UptimeRobot, Healthchecks.io, Better Stack, etc.).

## Public status page

`GET /status` is a browser-facing status page that polls this host’s `/api/v1/health` and `/api/v1/ready` every 30 seconds. Use it for a human-readable check; point monitors at the JSON endpoints below.

Live example: https://voxforge.brohammad.tech/status

## Endpoints

| Path | Use |
|------|-----|
| `GET /status` | Human-readable status UI |
| `GET /api/v1/health` | Process is up (lightweight) |
| `GET /api/v1/ready` | Postgres + Redis reachable (prefer this for alerts) |

## Recommended setup

1. Create a check against `https://<your-domain>/api/v1/ready` every 1–5 minutes.
2. Alert to Slack/email/PagerDuty on 2 consecutive failures.
3. Optional: also watch TLS certificate expiry on the same host.

**Slack alerts:** See [uptime-slack.md](./uptime-slack.md) for UptimeRobot → Slack and `scripts/uptime-ready-check.sh`.

Example (Healthchecks.io cron-style):

```bash
curl -fsS -o /dev/null "https://voxforge.example.com/api/v1/ready" \
  && curl -fsS -o /dev/null "https://hc-ping.com/<uuid>"
```

## Load balancer semantics

| JSON `status` | Default HTTP | With `READY_FAIL_ON_DEGRADED=true` |
|---------------|--------------|-------------------------------------|
| `ok` | 200 | 200 |
| `degraded` | 200 | 503 |
| `unavailable` | 503 | 503 |

Uptime monitors that only check HTTP codes should either:
- Alert on non-200 **and** set `READY_FAIL_ON_DEGRADED=true` on the app, or
- Parse JSON and alert when `status != "ok"`.

## Monitor recipes

### Default — page only when Postgres or Redis is down

`/api/v1/ready` returns HTTP 200 for `status=ok` and `status=degraded`. Optional
dependencies (LiveKit, MCP, knowledge worker, provider credentials) can be
degraded without removing the host from a load balancer.

```bash
./scripts/uptime-ready-check.sh https://voxforge.example.com
```

The script treats JSON `status=ok` and `status=degraded` as success when
`database` and `redis` are `ok`. HTTP errors and `unavailable` still fail.

JSON fixture (same rules as `scripts/uptime_ready_eval.py`):

```json
{"status":"degraded","database":"ok","redis":"ok","mcp_registry":"degraded"}
```

Default check: OK. With `FAIL_ON_DEGRADED=true`: FAIL.

### Strict — page on optional-dep degradation too

**Option A — change the API HTTP code** (monitors that only look at status codes):

```bash
READY_FAIL_ON_DEGRADED=true
```

Then `status=degraded` is HTTP 503. `curl -fsS` and most uptime probes fail.

**Option B — keep HTTP 200 and fail in the checker** (no app restart):

```bash
FAIL_ON_DEGRADED=true ./scripts/uptime-ready-check.sh https://voxforge.example.com
```

`READY_FAIL_ON_DEGRADED=true` in the checker environment is accepted as an alias.
