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
- Alert on non-200 **and** set `READY_FAIL_ON_DEGRADED=true`, or
- Parse JSON and alert when `status != "ok"`.
