# Security Policy

## Supported versions

| Version | Supported          |
| ------- | ------------------ |
| 1.0.x   | :white_check_mark: |
| 0.1.x   | :x:                |

## Reporting a vulnerability

**Please do not open public GitHub issues for security vulnerabilities.**

Email security reports to the repository maintainer via GitHub private vulnerability reporting, or contact the owner listed on the repository profile.

Include:

- Description of the issue and potential impact
- Steps to reproduce
- Affected versions or commits
- Suggested fix (if any)

We aim to acknowledge reports within **72 hours** and provide a remediation plan within **14 days** for confirmed issues.

## Security practices in VoxForge

- JWT + scoped API keys for REST; WebSocket auth via bearer token.
- Production startup validation (`validate_production_settings`) blocks weak secrets, open metrics, mock providers (when demo is disabled), and missing CORS/hosts.
- Rate limiting on sensitive API categories (auth, voice, knowledge uploads, replay, etc.).
- Knowledge uploads: size limits, extension validation, basename-only filenames for blob storage.
- Handoff replay links: signed tokens with configurable TTL.
- Metrics endpoint protected in production (bearer token or IP allow-list).

Deployment hardening (NGINX TLS, HSTS, body size limits) is documented in [docs/deployment/security.md](docs/deployment/security.md).

## Secure deployment checklist

Before exposing a VPS to the internet:

1. Set `APP_ENV=production`
2. Generate strong `JWT_SECRET_KEY`, `API_KEY_HASH_PEPPER`, `HANDOFF_REPLAY_SIGNING_SECRET`
3. Set `TRUSTED_HOSTS`, `CORS_ORIGINS`, `PUBLIC_BASE_URL`
4. Set `METRICS_BEARER_TOKEN` (or IP allow-list)
5. Use real voice providers (`STT_PROVIDER`, `LLM_PROVIDER`, `TTS_PROVIDER`) unless `DEMO_ENABLED=true`
6. Run `./deploy.sh init` with `.env.production` — do not hand-edit containers

Validate configuration:

```bash
python scripts/validate_production_env.py
```
