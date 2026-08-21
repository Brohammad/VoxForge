# VoxForge Security Overview

Security model and assumptions for the public production deployment.

## Threat model (Phase 5 scope)

| Asset | Risk | Mitigation |
|-------|------|------------|
| API credentials | Unauthorized access | JWT, API keys, RBAC |
| Demo abuse | Cost / DoS | Rate limiting, mock providers |
| Data at rest | DB breach | VPS disk encryption (provider-dependent) |
| Data in transit | MITM | TLS 1.2+, HSTS |
| Secrets in env | Leak via logs/commits | `.env.production` gitignored, validation |

Out of scope for Phase 5: SOC 2, penetration testing, WAF, DDoS scrubbing.

## Authentication

- **JWT** for user sessions (`Authorization: Bearer`)
- **API keys** with hashed storage (`API_KEY_HASH_PEPPER`)
- **RBAC** via organization roles (owner, admin, member)
- **SAML SSO** available but not required for public demo

Production requires `AUTH_REQUIRED=true`. Set `REGISTRATION_ENABLED=false` for invite-only pilots (recommended when `DEMO_ENABLED=false`). The demo quickstart endpoint is intentionally unauthenticated but rate-limited.

## Demo account assumptions

| Property | Value |
|----------|-------|
| Email | `demo@voxforge.io` |
| Password | `VoxForgeDemo!` (configurable via `DEMO_PASSWORD_HINT`) |
| Organization | VoxForge Demo (seeded migration 009) |
| Providers | Mock STT/LLM/TTS by default — no paid API spend |

**Assumption:** The demo account is public knowledge. It has no privileged access beyond its demo organization. Do not place production customer data in the demo org.

Password is re-synchronized on container start when `DEMO_ENABLED=true`.

## Transport security

NGINX production config provides:

- TLS 1.2 / 1.3
- HSTS (`max-age=63072000`)
- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: SAMEORIGIN`
- `Referrer-Policy: strict-origin-when-cross-origin`

## Application hardening

| Control | Implementation |
|---------|----------------|
| Host header validation | `TrustedHostMiddleware` |
| CORS | Explicit `CORS_ORIGINS` in production |
| Rate limiting | Redis-backed, per-IP, on `/api/v1/auth` and `/api/v1/demo` |
| Metrics exposure | Blocked at NGINX (`/api/v1/metrics` → 403) |
| Secret validation | Startup fails on weak `JWT_SECRET_KEY` / pepper |
| Non-root container | `appuser` (UID 10001) in `Dockerfile.prod` |

## Secret management

Phase 5 uses **environment file** secrets (`.env.production`):

```bash
openssl rand -hex 32   # JWT_SECRET_KEY
openssl rand -hex 32   # API_KEY_HASH_PEPPER
```

**Not committed to git.** For hardened deployments, migrate to:

- Docker secrets
- HashiCorp Vault
- Cloud provider secret managers (AWS SSM, GCP Secret Manager)

## Database security

- Postgres not exposed on host ports
- Credentials via `POSTGRES_PASSWORD` environment variable
- Application uses least-privilege DB user (single `voxforge` role)
- Backups stored on host filesystem — encrypt at rest per provider policy

## Redis security

- Internal Docker network only
- No authentication in default compose (acceptable for single-node; add `requirepass` for multi-tenant hosts)

## Provider API keys

When switching from mock to real providers:

- Keys stored in `.env.production` only
- Validated at startup in production mode
- Never logged or returned in API responses

## Logging and PII

- Structured logs may contain session IDs and user emails
- Voice transcripts stored in Postgres — treat as PII
- No automatic log redaction in Phase 5

## Known limitations (technical debt)

1. Single-node deployment — no HA failover
2. No WAF or bot protection beyond rate limiting
3. Demo password visible in `/api/v1/demo/info` and demo UI
4. Redis without auth on internal network
5. No automated secret rotation
6. Prometheus metrics require SSH tunnel in production

See [production-checklist.md](production-checklist.md) for pre-launch verification.
