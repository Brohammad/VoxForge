# Production Deployment Verification Checklist

Use this checklist after `./deploy.sh init` on a fresh Ubuntu 24.04 VPS.

## Pre-flight

- [ ] DNS A record points to VPS public IP
- [ ] Ports 80 and 443 open in cloud firewall + UFW
- [ ] Docker Engine and Compose v2 installed (`scripts/bootstrap-server.sh`)
- [ ] `.env.production` created via `./scripts/setup-production-env.sh your-domain.example`
- [ ] `python scripts/validate_production_env.py` passes

## Deploy

```bash
git clone https://github.com/Brohammad/VoxForge.git
cd VoxForge
./scripts/setup-production-env.sh your-domain.example
# Edit LIVEKIT_* if using WebRTC
./deploy.sh init
```

## Post-deploy verification

| Check | Command / URL | Expected |
|-------|---------------|----------|
| Compose status | `./deploy.sh status` | postgres, redis, app, nginx healthy |
| Health | `curl -fsS https://DOMAIN/api/v1/health` | `{"status":"ok"}` |
| Readiness | `curl -fsS https://DOMAIN/api/v1/ready` | database + redis ok |
| Landing | `https://DOMAIN/` | 200 HTML |
| Demo | `https://DOMAIN/demo` | Demo runs when `DEMO_ENABLED=true` |
| Dashboard | `https://DOMAIN/dashboard` | Login form loads |
| API docs | `https://DOMAIN/api/v1/docs` | OpenAPI UI |
| TLS | Browser padlock | Valid Let's Encrypt cert |
| Metrics auth | `curl /api/v1/metrics` without token | 401 in production |
| Manual QA | `python scripts/e2e_qa_manual.py` | 63/63 (set BASE in script) |
| Invite email | Dashboard → Settings → Invites, or `POST /orgs/{id}/invites` | With `EMAIL_PROVIDER=resend` or `smtp`, message arrives at the invitee inbox; with `log`, API/dashboard shows `accept_url` to copy |

## Optional profiles

| Profile | Trigger | Verify |
|---------|---------|--------|
| `knowledge` | `KNOWLEDGE_WORKER_ENABLED=true` | Upload doc → status `ready` |
| `livekit` | `LIVEKIT_URL` set | `POST /api/v1/livekit/sessions/{id}/token` → 200 |
| `monitoring` | `METRICS_BEARER_TOKEN` set | Grafana on `127.0.0.1:3000` via SSH tunnel |

## Local prod smoke (no TLS)

```bash
./scripts/validate-prod-smoke.sh
# or
./deploy.sh smoke
```

## Backup & restore

```bash
./deploy.sh backup
# Restore: see docs/deployment/operations.md
```

## Rollback

```bash
./deploy.sh down
git checkout <previous-tag>
./deploy.sh up
```
