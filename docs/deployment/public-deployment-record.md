# Public Deployment Record

**URL:** https://voxforge.brohammad.tech  
**Status:** Live (RC-1 baseline)  
**Last verified:** 2026-07-10 (v1.0.0-rc.1 redeploy)

## Infrastructure

| Component | Implementation |
|-----------|----------------|
| Host | Ubuntu 24.04 VPS (DigitalOcean) |
| TLS | Let's Encrypt via Certbot + NGINX |
| App | Docker Compose production stack |
| Database | PostgreSQL 16 + pgvector |
| Cache | Redis 7 |
| Reverse proxy | NGINX 1.27 (rate limits, HSTS, WS upgrade) |

## Health verification

```bash
curl -fsS https://voxforge.brohammad.tech/api/v1/health
# {"status":"ok"}

curl -fsS https://voxforge.brohammad.tech/api/v1/ready
# database + redis ok
```

## Surfaces

| URL | Purpose |
|-----|---------|
| `/` | Product landing page |
| `/demo` | Interactive pipeline demo (mock providers) |
| `/dashboard` | Operator console |
| `/api/v1/docs` | OpenAPI reference |

## Update procedure

```bash
ssh root@<DROPLET_IP>
cd /opt/VoxForge
git pull origin main
./deploy.sh up
```

Or from local machine:

```bash
DROPLET_IP=<ip> ./scripts/remote-deploy.sh
```

## Monitoring (optional profile)

Enable on larger VPS:

```bash
# Set METRICS_BEARER_TOKEN in .env.production
./deploy.sh up --profile monitoring
# Grafana: SSH tunnel to 127.0.0.1:3000
```

## Backups

```bash
./deploy.sh backup
# Cron: scripts/install-backup-cron.sh
```

## Related docs

- [Deployment guide](guide.md)
- [Verification checklist](verification-checklist.md)
- [Operations runbook](../operations/runbook.md)
