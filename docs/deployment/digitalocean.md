# DigitalOcean deployment

> **Note:** GitHub Student Pack DigitalOcean credits are ending for many students (2025–2026). If you no longer have credits, use [oracle-cloud.md](./oracle-cloud.md) ($0 permanent) or [Azure for Students](https://azure.microsoft.com/en-us/free/students/) ($100 credit).

Use DigitalOcean credits (when available) to host VoxForge on a single Droplet with Cloudflare DNS.

## 1. Create Droplet

1. Sign in at [cloud.digitalocean.com](https://cloud.digitalocean.com) (redeem Student Pack credits if prompted).
2. **Create → Droplets**
3. Region: closest to you (e.g. `BLR1` for India, `NYC1` for US East)
4. Image: **Ubuntu 24.04 LTS**
5. Size: **Basic → Regular → $12/mo** (2 vCPU, 2 GB) or **$24/mo** (2 vCPU, 4 GB) — 4 GB recommended for monitoring + workers
6. Authentication: **SSH key** (paste contents of `~/.ssh/id_ed25519.pub`)
7. Hostname: `voxforge`
8. Create Droplet and note the **public IPv4**

## 2. Cloudflare DNS

If `brohammad.tech` is on Cloudflare:

| Type | Name | Content | Proxy |
|------|------|---------|-------|
| A | `voxforge` | `<DROPLET_IP>` | DNS only (grey cloud) |

**Important:** Disable Cloudflare proxy (orange cloud) during initial Let's Encrypt issuance, or use DNS challenge. Grey cloud = DNS only.

Verify:

```bash
dig +short voxforge.brohammad.tech
```

## 3. Bootstrap server

```bash
ssh root@<DROPLET_IP>
```

```bash
git clone https://github.com/Brohammad/VoxForge.git /opt/VoxForge
cd /opt/VoxForge
chmod +x scripts/bootstrap-server.sh scripts/setup-production-env.sh deploy.sh
./scripts/bootstrap-server.sh
```

## 4. Configure secrets

```bash
./scripts/setup-production-env.sh
nano .env.production   # add LIVEKIT_* from LiveKit Cloud
```

## 5. Deploy

```bash
make deploy-validate
./deploy.sh init
```

`deploy.sh init` automatically starts:

- `livekit-worker` when `LIVEKIT_URL` is set
- `knowledge-worker` when `KNOWLEDGE_WORKER_ENABLED=true`
- Prometheus + Grafana when `METRICS_BEARER_TOKEN` is set

## 6. Verify

```bash
./deploy.sh status
BASE_URL=https://voxforge.brohammad.tech ./scripts/smoke-test.sh
```

Grafana (SSH tunnel only — bound to localhost on the VPS):

```bash
ssh -L 3000:127.0.0.1:3000 root@<DROPLET_IP>
# Open http://localhost:3000 — login admin / <GRAFANA_ADMIN_PASSWORD from .env.production>
```

## 7. Backups

```bash
crontab -e
# 0 3 * * * cd /opt/VoxForge && ./deploy.sh backup >> /var/log/voxforge-backup.log 2>&1
```

## Cost estimate

| Resource | Monthly |
|----------|---------|
| 2 vCPU / 4 GB Droplet | ~$24 (covered by $200 credit ≈ 8 months) |
| Domain subdomain | $0 |
| LiveKit Cloud | Free tier |
| Cloudflare DNS | $0 |
