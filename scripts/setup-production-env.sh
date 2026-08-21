#!/usr/bin/env bash
# Generate secrets and create .env.production from the example template.
# Usage: ./scripts/setup-production-env.sh [your-domain.example]

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="$ROOT/.env.production"
EXAMPLE="$ROOT/.env.production.example"
DOMAIN="${1:-your-domain.example}"

if [[ -f "$ENV_FILE" ]]; then
  echo "ERROR: $ENV_FILE already exists. Remove it first or edit manually." >&2
  exit 1
fi

[[ -f "$EXAMPLE" ]] || { echo "Missing $EXAMPLE" >&2; exit 1; }

gen_secret() { openssl rand -hex 32; }

POSTGRES_PASSWORD="$(gen_secret)"
REDIS_PASSWORD="$(gen_secret)"
JWT_SECRET_KEY="$(gen_secret)"
API_KEY_HASH_PEPPER="$(gen_secret)"
METRICS_BEARER_TOKEN="$(gen_secret)"
HANDOFF_REPLAY_SIGNING_SECRET="$(gen_secret)"

cp "$EXAMPLE" "$ENV_FILE"

# Portable in-place replace (macOS + Linux)
replace() {
  local key="$1" val="$2"
  if [[ "$(uname)" == "Darwin" ]]; then
    sed -i '' "s|^${key}=.*|${key}=${val}|" "$ENV_FILE"
  else
    sed -i "s|^${key}=.*|${key}=${val}|" "$ENV_FILE"
  fi
}

replace POSTGRES_PASSWORD "$POSTGRES_PASSWORD"
replace REDIS_PASSWORD "$REDIS_PASSWORD"
replace JWT_SECRET_KEY "$JWT_SECRET_KEY"
replace API_KEY_HASH_PEPPER "$API_KEY_HASH_PEPPER"
replace DATABASE_URL "postgresql+asyncpg://voxforge:${POSTGRES_PASSWORD}@postgres:5432/voxforge"
replace REDIS_URL "redis://:${REDIS_PASSWORD}@redis:6379/0"
replace PUBLIC_BASE_URL "https://${DOMAIN}"
replace TRUSTED_HOSTS "$DOMAIN"
replace CORS_ORIGINS "https://${DOMAIN}"
replace CERTBOT_EMAIL "admin@${DOMAIN}"

# Append optional secrets if not in example yet
grep -q '^METRICS_BEARER_TOKEN=' "$ENV_FILE" \
  && replace METRICS_BEARER_TOKEN "$METRICS_BEARER_TOKEN" \
  || echo "METRICS_BEARER_TOKEN=$METRICS_BEARER_TOKEN" >> "$ENV_FILE"

grep -q '^HANDOFF_REPLAY_SIGNING_SECRET=' "$ENV_FILE" \
  && replace HANDOFF_REPLAY_SIGNING_SECRET "$HANDOFF_REPLAY_SIGNING_SECRET" \
  || echo "HANDOFF_REPLAY_SIGNING_SECRET=$HANDOFF_REPLAY_SIGNING_SECRET" >> "$ENV_FILE"

GRAFANA_ADMIN_PASSWORD="$(gen_secret)"
grep -q '^GRAFANA_ADMIN_PASSWORD=' "$ENV_FILE" \
  && replace GRAFANA_ADMIN_PASSWORD "$GRAFANA_ADMIN_PASSWORD" \
  || echo "GRAFANA_ADMIN_PASSWORD=$GRAFANA_ADMIN_PASSWORD" >> "$ENV_FILE"

chmod 600 "$ENV_FILE"
echo "Created $ENV_FILE with generated secrets."
echo "Edit LIVEKIT_* vars before deploy if using LiveKit Cloud."
