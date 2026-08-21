# VoxForge Deployment Guide

Deploy VoxForge on a single VPS using Docker Compose, NGINX, and Let's Encrypt TLS.

## Target environment

| Requirement | Recommendation |
|-------------|----------------|
| Provider | Hetzner CX22 or DigitalOcean Droplet (1–2 vCPU, 2+ GB RAM) |
| OS | Ubuntu 24.04 LTS |
| Domain | A record pointing to VPS public IP |
| Ports | 80, 443 open inbound |

## Prerequisites

1. Docker Engine 24+ and Docker Compose v2
2. Domain DNS propagated to the server
3. Voice provider API keys (optional — mock providers work for the public demo)

## Quick deploy

```bash
# On the VPS
git clone https://github.com/Brohammad/VoxForge.git
cd VoxForge

./scripts/setup-production-env.sh your-domain.example.com
# Or manually: cp .env.production.example .env.production

chmod +x deploy.sh scripts/backup_postgres.sh
./deploy.sh init
```

`init` will:

1. Validate production environment variables
2. Render NGINX configuration for your domain
3. Start Postgres, Redis, and the API
4. Obtain a Let's Encrypt certificate via Certbot
5. Switch NGINX to HTTPS and start the renewal sidecar

## Environment configuration

Copy `.env.production.example` to `.env.production`. Or generate secrets automatically:

```bash
./scripts/setup-production-env.sh your-domain.example.com
```

Required values (if not using setup script):

| Variable | Description |
|----------|-------------|
| `PUBLIC_BASE_URL` | `https://your-domain.example` |
| `TRUSTED_HOSTS` | Same hostname (comma-separated if multiple) |
| `CORS_ORIGINS` | Same origin(s) as `PUBLIC_BASE_URL` |
| `POSTGRES_PASSWORD` | Strong database password |
| `JWT_SECRET_KEY` | `openssl rand -hex 32` |
| `API_KEY_HASH_PEPPER` | `openssl rand -hex 32` |
| `METRICS_BEARER_TOKEN` | Enables Prometheus + Grafana stack |
| `HANDOFF_REPLAY_SIGNING_SECRET` | Replay token signing (handoff) |

For the public demo without paid API keys, keep:

```env
DEMO_ENABLED=true
STT_PROVIDER=mock
LLM_PROVIDER=mock
TTS_PROVIDER=mock
```

Validate before deploy (runs automatically during `./deploy.sh init` inside the app container):

```bash
./deploy.sh init
```

Or validate manually after building the app image:

```bash
docker compose -f docker-compose.prod.yml --env-file .env.production build app
docker compose -f docker-compose.prod.yml --env-file .env.production run --rm --no-deps \
  -e APP_ENV=production --entrypoint python app /app/scripts/validate_production_env.py
```

## LiveKit (optional)

WebRTC transport requires an external LiveKit server (LiveKit Cloud recommended):

```env
LIVEKIT_URL=wss://your-project.livekit.cloud
LIVEKIT_API_KEY=...
LIVEKIT_API_SECRET=...
```

`./deploy.sh init` starts `livekit-worker` automatically when `LIVEKIT_URL` is set.

## Monitoring (optional)

Set `METRICS_BEARER_TOKEN` in `.env.production`. Deploy starts Prometheus (internal) and Grafana on `127.0.0.1:3000` (SSH tunnel). See [digitalocean.md](digitalocean.md).

## Server bootstrap

On a fresh Ubuntu 24.04 VPS:

```bash
./scripts/bootstrap-server.sh
```

**Student hosting:** [oracle-cloud.md](oracle-cloud.md) (free permanent) or [digitalocean.md](digitalocean.md) if credits remain. Azure ($100) works the same way with an Ubuntu VM.

## Operations

| Command | Purpose |
|---------|---------|
| `./deploy.sh up` | Rebuild and start |
| `./deploy.sh down` | Stop stack |
| `./deploy.sh logs` | Tail service logs |
| `./deploy.sh backup` | PostgreSQL dump to `deploy/backups/` |
| `./deploy.sh renew-cert` | Force TLS renewal |
| `./deploy.sh status` | Health check summary |

### Scheduled backups

```cron
0 3 * * * cd /opt/VoxForge && ./deploy.sh backup >> /var/log/voxforge-backup.log 2>&1
```

Backups older than 14 days are pruned automatically.

## Public surfaces

After deploy:

| URL | Purpose |
|-----|---------|
| `/` | Landing page |
| `/demo` | Interactive voice pipeline demo |
| `/dashboard` | Operator dashboard |
| `/api/v1/docs` | OpenAPI reference |
| `/api/v1/health` | Liveness probe |
| `/api/v1/ready` | Readiness (DB + Redis) |

Demo credentials: `demo@voxforge.io` / `VoxForgeDemo!` (synced on container start when `DEMO_ENABLED=true`).

## Resource limits

Production compose sets per-service CPU and memory limits with defaults suitable for **1-vCPU / 2GB** droplets. Override via `COMPOSE_CPU_*` and `COMPOSE_MEM_*` in `.env.production` (see `.env.production.example`). For larger hosts, raise `COMPOSE_CPU_APP` and `COMPOSE_MEM_APP` first.

## Related docs

- [Documentation index](../README.md)
- [Operations runbook](../operations/runbook.md)
- [Operations guide](operations.md)
- [Troubleshooting](troubleshooting.md)
- [Recovery guide](recovery-guide.md)
- [Architecture overview](architecture.md)
- [Security overview](security.md)
- [Verification checklist](verification-checklist.md)
