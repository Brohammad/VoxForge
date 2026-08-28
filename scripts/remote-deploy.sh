#!/usr/bin/env bash
# Bootstrap and deploy VoxForge on a fresh Droplet via SSH.
#
#   DROPLET_IP=1.2.3.4 ./scripts/remote-deploy.sh
#
# Prerequisites:
#   - SSH key added to DO (root@DROPLET_IP works)
#   - DNS A record voxforge.brohammad.tech → DROPLET_IP (grey cloud)
#   - Git pushed to origin (remote clones latest main)

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
if [[ -f "$ROOT/.env.deploy" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/.env.deploy"
  set +a
fi

DROPLET_IP="${DROPLET_IP:-}"
REPO_URL="${REPO_URL:-https://github.com/Brohammad/VoxForge.git}"
DOMAIN="${DOMAIN:-voxforge.brohammad.tech}"
SSH_USER="${SSH_USER:-root}"
REMOTE_DIR="${REMOTE_DIR:-/opt/VoxForge}"

[[ -n "$DROPLET_IP" ]] || { echo "Set DROPLET_IP" >&2; exit 1; }

log() { printf '==> %s\n' "$*"; }

ssh_cmd() {
  ssh -o StrictHostKeyChecking=accept-new -o ConnectTimeout=15 "${SSH_USER}@${DROPLET_IP}" "$@"
}

log "Waiting for SSH on $DROPLET_IP..."
for _ in $(seq 1 40); do
  if ssh_cmd "echo ok" >/dev/null 2>&1; then
    break
  fi
  sleep 10
done
ssh_cmd "echo ok" >/dev/null

log "Bootstrapping server..."
ssh_cmd "bash -s" <<'REMOTE_BOOT'
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq git ufw curl ca-certificates
if ! command -v docker >/dev/null 2>&1; then
  curl -fsSL https://get.docker.com | sh
fi
ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable
REMOTE_BOOT

log "Cloning repo and configuring..."
ssh_cmd "bash -s" <<REMOTE_SETUP
set -euo pipefail
rm -rf ${REMOTE_DIR}
git clone ${REPO_URL} ${REMOTE_DIR}
cd ${REMOTE_DIR}
chmod +x scripts/*.sh deploy.sh
./scripts/setup-production-env.sh ${DOMAIN}
# 2GB droplet: skip on-server Grafana/Prometheus (SSH tunnel later if needed).
# Keep the knowledge worker on — blobs persist in the knowledge_data volume.
sed -i 's/^METRICS_BEARER_TOKEN=.*/METRICS_BEARER_TOKEN=/' .env.production || true
REMOTE_SETUP

log "Deploying (this may take 10–15 min on first build)..."
ssh_cmd "bash -s" <<REMOTE_DEPLOY
set -euo pipefail
cd ${REMOTE_DIR}
./deploy.sh init
REMOTE_DEPLOY

log "Smoke test..."
sleep 5
BASE_URL="https://voxforge.brohammad.tech" "${ROOT}/scripts/smoke-test.sh" || {
  echo "Smoke test failed — DNS may still be propagating. Retry:"
  echo "  BASE_URL=https://voxforge.brohammad.tech ./scripts/smoke-test.sh"
}

log "Done. Open https://voxforge.brohammad.tech/"
echo "Add LIVEKIT_* to .env.production on server, then: ssh root@${DROPLET_IP} 'cd ${REMOTE_DIR} && ./deploy.sh up'"
