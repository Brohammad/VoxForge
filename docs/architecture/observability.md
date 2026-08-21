# Observability Stack

VoxForge ships with Prometheus and Grafana in Docker Compose for pipeline metrics, structured JSON logging, and OpenTelemetry tracing.

## Services

| Service | URL | Credentials |
|---------|-----|-------------|
| VoxForge API | http://localhost:8000 | JWT / API key |
| Dashboard | http://localhost:8000/dashboard | JWT in connect bar |
| Prometheus | http://localhost:9090 | — |
| Grafana | http://localhost:3000 | admin / voxforge |

## Metrics access

`GET /api/v1/metrics` exposes the Prometheus registry.

| Environment | Default behavior |
|-------------|------------------|
| Development | Anonymous access allowed |
| Production | Requires auth — API key with `metrics:read`, `METRICS_BEARER_TOKEN`, or IP allow-list |

Configuration:

| Variable | Purpose |
|----------|---------|
| `METRICS_ALLOW_ANONYMOUS` | Override auto-detect (`true`/`false`; unset = dev-only anonymous) |
| `METRICS_BEARER_TOKEN` | Static bearer for Prometheus scrape |
| `METRICS_ALLOWED_IPS` | Comma-separated IPs/CIDRs (e.g. `10.0.0.0/8`) |

Prometheus scrape config (`infra/prometheus/prometheus.yml`) targets `app:8000/api/v1/metrics` every 15s. In production, configure scrape auth:

```yaml
authorization:
  credentials: ${METRICS_BEARER_TOKEN}
```

NGINX still blocks public `/api/v1/metrics` in production (defense in depth).

Full metric catalog: [metrics.md](./metrics.md).

## Health endpoints

| Endpoint | Purpose | HTTP codes |
|----------|---------|------------|
| `GET /api/v1/health` | Liveness — process alive | Always `200` |
| `GET /api/v1/ready` | Readiness — dependency checks | `200` ok/degraded (default), `503` unavailable; optional `READY_FAIL_ON_DEGRADED=true` → `503` on degraded |

Readiness checks (2s timeout each):

| Check | Critical? | Values |
|-------|-----------|--------|
| `database` | Yes | `ok` / `error: …` |
| `redis` | Yes | `ok` / `error: …` |
| `knowledge_worker` | No | `ok` / `disabled` / `error: …` |
| `livekit` | No | `configured` / `disabled` / `error: …` |
| `mcp_registry` | No | `ok` / `degraded` / `disabled` |
| `embedding_provider` | No | `ok` / `configured` / `error: …` |
| `llm_provider` | No | `ok` / `configured` / `error: …` |

Status aggregation:

- **unavailable** — PostgreSQL or Redis down → HTTP 503
- **degraded** — non-critical dependency unhealthy → HTTP 200
- **ok** — all checks pass or optional components disabled

## Structured logging

JSON logs via structlog to stdout. Every HTTP request receives an `X-Request-ID` header; the value is bound as `request_id` in log context.

Automatic sanitization redacts JWTs, API keys (`vxf_…`), bearer tokens, and `password`/`secret`/`token` fields before emit.

Bind additional context at operation boundaries:

- `session_id` — voice pipeline, WebSocket, handoff
- `org_id` — multi-tenant operations
- `handoff_id`, `replay_id` — escalation and replay paths

Active OpenTelemetry spans inject `trace_id` and `span_id` into log records.

**Never log:** JWTs, raw API keys, replay tokens, uploaded document bodies, or full conversation transcripts.

## Tracing model

Service name: `voxforge`. Export via `OTEL_EXPORTER_OTLP_ENDPOINT` (OTLP gRPC). Console exporter in development when OTLP is unset.

| Span | Component |
|------|-----------|
| `voice_pipeline.run_listening` | WebSocket/LiveKit audio path |
| `voice_pipeline.run_text_turn` | Programmatic/onboarding text turns |
| `agent_orchestrator.generate` | LangGraph multi-agent run |
| `tool.router.execute` | MCP tool router |
| `mcp.registry.discover_all` / `mcp.registry.invoke` | MCP runtime |
| `knowledge.search` / `knowledge.ingest` | Knowledge retrieval and ingestion |
| `handoff.orchestrate` / `handoff.tool.invoke` | Human handoff |
| `replay.get_session` | Session replay reads |
| `livekit.room.join` / `livekit.session.prepare` / `livekit.session.reconnect` | LiveKit transport |
| `session.reconcile_ephemeral` | Postgres/Redis reconciliation |

Sub-spans for individual STT/LLM/TTS provider calls are intentionally omitted to avoid nesting noise; latency is captured in Prometheus histograms.

## Grafana dashboard

Bundled dashboard (`infra/grafana/dashboards/voxforge.json`) includes:

- E2E turn latency, active sessions, WS connections
- Provider errors, tool call rate, rate limit blocks
- Handoff queue depth, session consistency
- Knowledge ingest jobs, LiveKit lifecycle, evaluation score

**Not in bundled dashboard (query Prometheus directly):**

- Per-org handoff initiation rates (high cardinality)
- MCP server-level breakdown (use `voxforge_mcp_servers_total`)
- Onboarding funnel (use `voxforge_onboarding_steps_total`)

## Quick start

```bash
docker compose up -d
```

Grafana auto-provisions the Prometheus datasource and VoxForge dashboard from `infra/grafana/`.

## Related

- [metrics.md](./metrics.md) — full metric catalog
- [failure-recovery.md](./failure-recovery.md) — operational failure modes
- [operations.md](../deployment/operations.md) — day-two runbook
