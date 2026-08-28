# Configuration Reference

Environment variables for local development (`.env`) and production (`.env.production`).

**Templates:** `.env.example` · `.env.production.example`  
**Generate production secrets:** `./scripts/setup-production-env.sh your-domain.example`  
**Validate production:** `python scripts/validate_production_env.py`

---

## Core

| Variable | Default | Description |
|----------|---------|-------------|
| `APP_ENV` | `development` | `development` or `production` |
| `DATABASE_URL` | local postgres | Async SQLAlchemy URL |
| `REDIS_URL` | `redis://localhost:6379/0` | Session cache and rate limits |
| `LOG_LEVEL` | `INFO` | Python log level |
| `PUBLIC_BASE_URL` | `http://localhost:8000` | Canonical URL (required in prod) |
| `TRUSTED_HOSTS` | `localhost,127.0.0.1` | Host header allowlist |
| `CORS_ORIGINS` | `http://localhost:8000` | Comma-separated origins |

---

## Voice providers

| Variable | Default | Options |
|----------|---------|---------|
| `STT_PROVIDER` | `mock` | `mock`, `deepgram` |
| `LLM_PROVIDER` | `mock` | `mock`, `openai` |
| `TTS_PROVIDER` | `mock` | `mock`, `cartesia` |
| `EMBEDDING_PROVIDER` | `mock` | `mock`, `openai` |
| `DEEPGRAM_API_KEY` | — | Required when `STT_PROVIDER=deepgram` |
| `OPENAI_API_KEY` | — | Required for OpenAI LLM/embeddings |
| `CARTESIA_API_KEY` | — | Required when `TTS_PROVIDER=cartesia` |

Production with `DEMO_ENABLED=false` requires real providers (not `mock`).

---

## Auth cookies

| Variable | Default | Description |
|----------|---------|-------------|
| `AUTH_COOKIES_ENABLED` | `true` | Set HttpOnly cookies on login/register/refresh |
| `AUTH_COOKIE_NAME` | `voxforge_access` | Access token cookie name |
| `AUTH_COOKIE_SECURE` | auto | `true` in production when unset |
| `READY_FAIL_ON_DEGRADED` | `false` | Return HTTP 503 when optional deps are degraded |

Cookie-authenticated mutating requests require `X-CSRF-Token` matching the `voxforge_csrf` cookie (Bearer / API key exempt).

## Org invites

`POST /api/v1/orgs/{org_id}/invites` with `{ "email", "role" }` creates a one-time invite. Accept via `POST /api/v1/auth/invites/accept`.

| Variable | Default | Description |
|----------|---------|-------------|
| `EMAIL_PROVIDER` | `log` | `log` (dev), `resend`, or `smtp` |
| `EMAIL_FROM` | `VoxForge <invites@voxforge.local>` | From address |
| `RESEND_API_KEY` | — | Required when `EMAIL_PROVIDER=resend` |
| `SMTP_HOST` | — | SMTP server hostname |
| `SMTP_PORT` | `587` | SMTP port |
| `SMTP_USER` | — | SMTP username (optional) |
| `SMTP_PASSWORD` | — | SMTP password (optional) |
| `SMTP_USE_TLS` | `true` | STARTTLS for SMTP |
| `INVITE_TTL_HOURS` | `72` | Invite expiry |

When email delivery succeeds, the API omits the raw `token` in production; in `log` mode the token is returned for local testing.

---

## Authentication

| Variable | Default | Description |
|----------|---------|-------------|
| `JWT_SECRET_KEY` | `change-me` | Min 32 bytes in production |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | `60` | Access token TTL |
| `JWT_REFRESH_TOKEN_EXPIRE_DAYS` | `7` | Refresh token TTL |
| `API_KEY_HASH_PEPPER` | `change-me` | API key hashing secret |
| `AUTH_REQUIRED` | `true` | Require auth on protected routes |
| `REGISTRATION_ENABLED` | `true` (local) / `false` (prod example) | Allow `POST /auth/register`. When false, new users join via org invite only |

---

## Demo

| Variable | Default | Description |
|----------|---------|-------------|
| `DEMO_ENABLED` | `true` (local) | Enable `/demo` and quickstart API |
| `DEMO_ORG_ID` | fixed UUID | Demo organization |
| `DEMO_EMAIL` | `demo@voxforge.io` | Demo account email |

---

## Knowledge base

| Variable | Default | Description |
|----------|---------|-------------|
| `KNOWLEDGE_ENABLED` | `true` | Enable knowledge module |
| `KNOWLEDGE_WORKER_ENABLED` | `false` local / `true` production | Background ingestion worker |
| `KNOWLEDGE_BLOB_PATH` | `/tmp/voxforge-knowledge` local / `/data/knowledge` production | Filesystem blob root; production must not use `/tmp` |
| `KNOWLEDGE_SEARCH_MIN_SIMILARITY` | `0.65` | Search threshold (0.0 for mock) |
| `KNOWLEDGE_CONTEXT_ENABLED` | `true` | Inject KB into agent context |

---

## Tools & MCP

| Variable | Default | Description |
|----------|---------|-------------|
| `TOOLS_ENABLED` | `true` | Enable tool router |
| `MCP_SERVERS_CONFIG` | — | JSON array of MCP server configs |
| `MCP_STARTUP_DISCOVER` | `true` | Discover MCP tools at startup |

---

## Handoff

| Variable | Default | Description |
|----------|---------|-------------|
| `HANDOFF_ENABLED` | `true` | Human escalation queue |
| `HANDOFF_REPLAY_SIGNING_SECRET` | — | Required in production |
| `HANDOFF_MIN_CONFIDENCE` | `0.55` | Auto-escalation threshold |

---

## LiveKit (optional)

| Variable | Description |
|----------|-------------|
| `LIVEKIT_URL` | e.g. `wss://your-project.livekit.cloud` |
| `LIVEKIT_API_KEY` | LiveKit API key |
| `LIVEKIT_API_SECRET` | LiveKit API secret |
| `LIVEKIT_AGENT_NAME` | Worker dispatch name |

---

## Observability

| Variable | Description |
|----------|-------------|
| `OTEL_EXPORTER_OTLP_ENDPOINT` | OpenTelemetry collector URL |
| `METRICS_BEARER_TOKEN` | Protects `/api/v1/metrics`; enables Prometheus/Grafana profile |

---

## Rate limiting

| Variable | Default | Description |
|----------|---------|-------------|
| `RATE_LIMIT_ENABLED` | `true` | Global rate limit toggle |
| `RATE_LIMIT_MULTIPLIER` | `1.0` | Scale all limits |

See [architecture/rate-limiting.md](architecture/rate-limiting.md) for per-route policies.

---

## Production-only

| Variable | Description |
|----------|-------------|
| `POSTGRES_PASSWORD` | Database password (compose) |
| `CERTBOT_EMAIL` | Let's Encrypt contact |
| `GRAFANA_ADMIN_PASSWORD` | Grafana admin (monitoring profile) |
| `COMPOSE_CPU_APP` | App container CPU limit |
| `COMPOSE_MEM_APP` | App container memory limit |

---

## See also

- [deployment/guide.md](deployment/guide.md) — production setup
- [deployment/security.md](deployment/security.md) — security assumptions
- [FAQ.md](FAQ.md) — common configuration questions
