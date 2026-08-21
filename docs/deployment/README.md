# Deployment Documentation

Deploy VoxForge on Ubuntu 24.04 with Docker Compose, NGINX, and automatic HTTPS.

**Reference deployment:** https://voxforge.brohammad.tech · [public record](public-deployment-record.md)

---

## Start here

| Document | Description |
|----------|-------------|
| [uptime.md](uptime.md) | External health checks, `/status` page, alerting |
| [guide.md](guide.md) | **Primary** — step-by-step VPS deployment |
| [verification-checklist.md](verification-checklist.md) | Post-deploy QA checklist |
| [setup-production-env.sh](../../scripts/setup-production-env.sh) | Auto-generate `.env.production` |

## Hosting providers

| Document | Cost | Notes |
|----------|------|-------|
| [oracle-cloud.md](oracle-cloud.md) | $0 (Always Free) | Recommended for students |
| [digitalocean.md](digitalocean.md) | ~$12–24/mo | Simple droplet setup |

## Architecture & security

| Document | Description |
|----------|-------------|
| [architecture.md](architecture.md) | Production topology |
| [architecture-overview.md](architecture-overview.md) | Component diagram |
| [security.md](security.md) | Security controls |

## Operations

| Document | Description |
|----------|-------------|
| [operations.md](operations.md) | Day-2 ops, scaling, secret rotation |
| [../operations/runbook.md](../operations/runbook.md) | Quick reference |
| [troubleshooting.md](troubleshooting.md) | Common failures |
| [recovery-guide.md](recovery-guide.md) | Recovery procedures |
| [rollback-guide.md](rollback-guide.md) | Roll back code or config |
| [production-checklist.md](production-checklist.md) | Pre-flight checklist |

## Quick deploy

```bash
git clone https://github.com/Brohammad/VoxForge.git
cd VoxForge
./scripts/setup-production-env.sh your-domain.example.com
./deploy.sh init
```

## Commands

| Command | Purpose |
|---------|---------|
| `./deploy.sh init` | First-time deploy with TLS |
| `./deploy.sh up` | Rebuild and start |
| `./deploy.sh status` | Health summary |
| `./deploy.sh backup` | PostgreSQL backup |
| `./deploy.sh smoke` | Local prod validation (no TLS) |

## Related

- [../CONFIGURATION.md](../CONFIGURATION.md) — environment variables
- [../ONBOARDING.md](../ONBOARDING.md) — local development setup
