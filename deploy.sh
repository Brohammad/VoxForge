#!/usr/bin/env bash
# VoxForge production deployment — Docker Compose on a single VPS.
#
# Usage:
#   ./deploy.sh init          # First-time: validate env, bootstrap TLS, start stack
#   ./deploy.sh up            # Build and start (after init)
#   ./deploy.sh down          # Stop stack
#   ./deploy.sh logs          # Tail logs
#   ./deploy.sh backup        # PostgreSQL backup to deploy/backups/
#   ./deploy.sh renew-cert    # Force certbot renewal
#   ./deploy.sh status        # Service health summary
#
# Prerequisites: Docker, Docker Compose v2, domain DNS → this host, ports 80/443 open.

set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
COMPOSE="docker compose -f $ROOT/docker-compose.prod.yml"
ENV_FILE="${ENV_FILE:-$ROOT/.env.production}"
NGINX_CONF_DIR="$ROOT/deploy/nginx/conf.d"
DOMAIN="${DOMAIN:-}"

log() { printf '==> %s\n' "$*"; }
die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

require_env_file() {
  if [[ ! -f "$ENV_FILE" ]]; then
    log "No $ENV_FILE found — generating from template..."
    "$ROOT/scripts/setup-production-env.sh"
  fi
  [[ -f "$ENV_FILE" ]] || die "Missing $ENV_FILE — copy .env.production.example and fill secrets."
}

load_env() {
  require_env_file
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
  DOMAIN="${DOMAIN:-${PUBLIC_BASE_URL#https://}}"
  DOMAIN="${DOMAIN#http://}"
  DOMAIN="${DOMAIN%%/*}"
  [[ -n "$DOMAIN" && "$DOMAIN" != "your-domain.example" ]] \
    || die "Set PUBLIC_BASE_URL or DOMAIN to your public hostname."
}

validate_env() {
  load_env
  log "Validating production environment (in app container)..."
  $COMPOSE --env-file "$ENV_FILE" build app
  $COMPOSE --env-file "$ENV_FILE" run --rm --no-deps \
    -e APP_ENV=production \
    --entrypoint python \
    app /app/scripts/validate_production_env.py
}

render_nginx_config() {
  load_env
  local http_tpl="$NGINX_CONF_DIR/voxforge-http.conf.template"
  local https_tpl="$NGINX_CONF_DIR/voxforge-https.conf.template"
  local out="$NGINX_CONF_DIR/voxforge.conf"
  local staged_dir="$ROOT/deploy/nginx/staged"

  log "Rendering NGINX config for $DOMAIN..."
  mkdir -p "$staged_dir"
  sed -e "s/\${DOMAIN}/$DOMAIN/g" "$http_tpl" > "$staged_dir/voxforge-http.conf"
  sed -e "s/\${DOMAIN}/$DOMAIN/g" "$https_tpl" > "$staged_dir/voxforge-https.conf"

  # NGINX loads every *.conf in conf.d — keep TLS snippets staged until certs exist.
  rm -f "$NGINX_CONF_DIR/voxforge-http.conf" "$NGINX_CONF_DIR/voxforge-https.conf"

  if [[ -f "$ROOT/deploy/nginx/certs-ready" ]]; then
    cat "$staged_dir/voxforge-http.conf" "$staged_dir/voxforge-https.conf" > "$out"
  else
    cp "$NGINX_CONF_DIR/voxforge-bootstrap.conf" "$out"
  fi
}

render_prometheus_config() {
  load_env
  local tpl="$ROOT/infra/prometheus/prometheus.prod.yml.template"
  local out="$ROOT/infra/prometheus/prometheus.prod.yml"
  [[ -f "$tpl" ]] || return 0
  [[ -n "${METRICS_BEARER_TOKEN:-}" ]] || return 0
  log "Rendering Prometheus config..."
  sed -e "s/\${METRICS_BEARER_TOKEN}/$METRICS_BEARER_TOKEN/g" "$tpl" > "$out"
}

start_optional_workers() {
  load_env
  local profiles=()

  if [[ -n "${LIVEKIT_URL:-}" ]]; then
    log "Starting LiveKit worker (LIVEKIT_URL set)..."
    profiles+=(--profile livekit)
    $COMPOSE --env-file "$ENV_FILE" "${profiles[@]}" up -d livekit-worker
    profiles=()
  fi

  if [[ "${KNOWLEDGE_ENABLED:-true}" != "false" ]]; then
    log "Starting knowledge worker..."
    $COMPOSE --env-file "$ENV_FILE" up -d knowledge-worker
  fi

  if [[ -n "${METRICS_BEARER_TOKEN:-}" ]]; then
    render_prometheus_config
    log "Starting monitoring stack (METRICS_BEARER_TOKEN set)..."
    $COMPOSE --env-file "$ENV_FILE" --profile monitoring up -d prometheus grafana
  fi
}

bootstrap_tls() {
  load_env
  render_nginx_config
  mkdir -p "$ROOT/deploy/backups"

  log "Starting bootstrap stack (HTTP only)..."
  $COMPOSE --env-file "$ENV_FILE" up -d postgres redis app nginx

  log "Waiting for API health..."
  for _ in $(seq 1 30); do
    if $COMPOSE --env-file "$ENV_FILE" exec -T app curl -fsS http://127.0.0.1:8000/api/v1/health >/dev/null 2>&1; then
      break
    fi
    sleep 2
  done

  log "Requesting Let's Encrypt certificate for $DOMAIN..."
  $COMPOSE --env-file "$ENV_FILE" --profile certbot run --rm --entrypoint certbot certbot certonly \
    --webroot -w /var/www/certbot \
    --email "${CERTBOT_EMAIL:-admin@$DOMAIN}" \
    --agree-tos --no-eff-email \
    -d "$DOMAIN"

  touch "$ROOT/deploy/nginx/certs-ready"
  render_nginx_config
  $COMPOSE --env-file "$ENV_FILE" up -d nginx
  $COMPOSE --env-file "$ENV_FILE" restart nginx
  $COMPOSE --env-file "$ENV_FILE" --profile certbot up -d certbot
  start_optional_workers
  log "TLS bootstrap complete."
}

cmd_init() {
  validate_env
  render_nginx_config
  mkdir -p "$ROOT/deploy/backups"

  if [[ ! -f "$ROOT/deploy/nginx/certs-ready" ]]; then
    bootstrap_tls
  else
    log "Certificates already provisioned — starting full stack..."
    $COMPOSE --env-file "$ENV_FILE" up -d --build
    $COMPOSE --env-file "$ENV_FILE" --profile certbot up -d certbot
  fi

  start_optional_workers
  cmd_status
}

cmd_up() {
  validate_env
  render_nginx_config
  mkdir -p "$ROOT/deploy/backups"
  $COMPOSE --env-file "$ENV_FILE" up -d --build
  start_optional_workers
  cmd_status
}

cmd_down() {
  $COMPOSE --env-file "$ENV_FILE" down
}

cmd_logs() {
  $COMPOSE --env-file "$ENV_FILE" logs -f --tail=100
}

cmd_backup() {
  ENV_FILE="$ENV_FILE" "$ROOT/scripts/backup_postgres.sh"
}

cmd_renew_cert() {
  load_env
  $COMPOSE --env-file "$ENV_FILE" --profile certbot run --rm --entrypoint certbot certbot renew --webroot -w /var/www/certbot
  $COMPOSE --env-file "$ENV_FILE" exec nginx nginx -s reload
}

cmd_smoke() {
  ENV_FILE="$ENV_FILE" "$ROOT/scripts/validate-prod-smoke.sh"
}

cmd_status() {
  load_env
  log "Compose services:"
  $COMPOSE --env-file "$ENV_FILE" ps
  echo
  log "Health endpoints (via app container):"
  $COMPOSE --env-file "$ENV_FILE" exec -T app curl -fsS http://127.0.0.1:8000/api/v1/health || echo "  /health: unavailable"
  $COMPOSE --env-file "$ENV_FILE" exec -T app curl -fsS http://127.0.0.1:8000/api/v1/ready || echo "  /ready: unavailable"
  echo
  log "Public URLs:"
  echo "  Landing:  https://$DOMAIN/"
  echo "  Demo:     https://$DOMAIN/demo"
  echo "  API docs: https://$DOMAIN/api/v1/docs"
}

case "${1:-}" in
  init)        cmd_init ;;
  up)          cmd_up ;;
  down)        cmd_down ;;
  logs)        cmd_logs ;;
  backup)      cmd_backup ;;
  renew-cert)  cmd_renew_cert ;;
  smoke)       cmd_smoke ;;
  status)      cmd_status ;;
  *)
    echo "Usage: $0 {init|up|down|logs|backup|renew-cert|smoke|status}"
    exit 1
    ;;
esac
