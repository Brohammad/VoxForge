# Oracle Cloud deployment (Always Free)

**Recommended if DigitalOcean Student Pack credits are unavailable.** Oracle's Always Free tier does not expire and is enough for the full VoxForge stack (FastAPI, Postgres, Redis, workers, Grafana).

| Spec | Always Free (ARM Ampere A1) |
|------|---------------------------|
| Compute | Up to 4 OCPU, 24 GB RAM (across VMs) |
| Cost | $0/month (permanent while account active) |
| OS | Ubuntu 24.04 **aarch64** |
| Fit | Same Docker Compose deploy as other VPS guides |

## 1. Create Oracle Cloud account

1. Sign up at [cloud.oracle.com](https://www.oracle.com/cloud/free/)
2. Complete identity verification (card may be required; Always Free resources are not charged if you stay within limits)
3. Pick a **home region** close to you (cannot change later)

## 2. Create the VM

1. **Compute → Instances → Create instance**
2. Name: `voxforge`
3. Image: **Ubuntu 24.04** (aarch64)
4. Shape: **Ampere** → `VM.Standard.A1.Flex` → **2 OCPU, 12 GB RAM** (leaves headroom in free quota; you can use 4/24 on a single VM if quota allows)
5. Networking: assign a **public IPv4** (create VCN if prompted — defaults are fine)
6. SSH keys: paste `~/.ssh/id_ed25519.pub`
7. Create

Note the **public IP** when the instance reaches `RUNNING`.

## 3. Open firewall ports

Oracle blocks inbound traffic by default.

### Security list (VCN)

**Networking → Virtual cloud networks → your VCN → Security Lists → Default Security List**

Add **Ingress** rules:

| Source | Protocol | Port |
|--------|----------|------|
| `0.0.0.0/0` | TCP | 22 |
| `0.0.0.0/0` | TCP | 80 |
| `0.0.0.0/0` | TCP | 443 |

### Instance firewall (if enabled)

On the VM after SSH:

```bash
# Ubuntu may use iptables/nftables; our bootstrap script configures ufw
ufw allow OpenSSH && ufw allow 80/tcp && ufw allow 443/tcp && ufw enable
```

## 4. Cloudflare DNS

| Type | Name | Content | Proxy |
|------|------|---------|-------|
| A | `voxforge` | `<ORACLE_VM_IP>` | DNS only (grey cloud) |

Grey cloud during Let's Encrypt bootstrap. Verify:

```bash
dig +short voxforge.brohammad.tech
```

## 5. Bootstrap and deploy

```bash
ssh ubuntu@<ORACLE_VM_IP>   # default user is often 'ubuntu' on Ubuntu images
```

```bash
sudo -i   # or use ubuntu with sudo below
git clone https://github.com/Brohammad/VoxForge.git /opt/VoxForge
cd /opt/VoxForge
chmod +x scripts/bootstrap-server.sh scripts/setup-production-env.sh deploy.sh
./scripts/bootstrap-server.sh
./scripts/setup-production-env.sh
nano .env.production   # add LIVEKIT_* from LiveKit Cloud
make deploy-validate
./deploy.sh init
```

First Docker build on ARM may take 10–20 minutes.

## 6. Verify

```bash
./deploy.sh status
BASE_URL=https://voxforge.brohammad.tech ./scripts/smoke-test.sh
```

Grafana via SSH tunnel:

```bash
ssh -L 3000:127.0.0.1:3000 ubuntu@<ORACLE_VM_IP>
```

## 7. Backups

```bash
./scripts/install-backup-cron.sh
```

## ARM notes

- All images in `docker-compose.prod.yml` support **linux/arm64** (official Postgres, Redis, NGINX, Prometheus, Grafana images)
- `Dockerfile.prod` builds natively on ARM — no extra flags needed
- If build fails on an older Docker version, upgrade: `apt install docker-ce docker-compose-plugin`

## Cost comparison

| Provider | Monthly cost | Student benefit |
|----------|--------------|-----------------|
| Oracle Always Free | **$0** | Permanent (not GitHub Pack) |
| Azure for Students | ~$0 until $100 credit used | GitHub Pack |
| DigitalOcean | ~$24 | Pack credits ending for many students |

## Troubleshooting

| Issue | Fix |
|-------|-----|
| `Out of host capacity` for A1 | Try another availability domain or region at signup |
| Let's Encrypt fails | Confirm Cloudflare proxy is **off** (grey cloud) |
| SSH timeout | Check Oracle security list + instance public IP |
| Slow first deploy | Normal on ARM; subsequent deploys use Docker cache |
