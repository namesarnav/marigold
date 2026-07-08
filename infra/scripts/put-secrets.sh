#!/usr/bin/env bash
# Seed the application's secrets into SSM Parameter Store as SecureStrings.
#
# Run this once by hand before the first deploy, and again whenever a secret
# changes. It is deliberately not part of CI: the deploy pipeline has no access
# to these values at all, which is what keeps them out of GitHub, out of the
# container image, and out of SSM command history.
#
# Every SecureString under /<project>/ becomes a key in the `marigold-secrets`
# Kubernetes secret, so adding a new setting is a call to this script rather
# than a change to a manifest.
#
# Usage:
#   AWS_REGION=us-east-1 ./put-secrets.sh
#
# It prompts for anything not already in the environment, and never echoes a
# value back to the terminal.
set -euo pipefail

PROJECT="${PROJECT:-marigold}"
: "${AWS_REGION:?set AWS_REGION, e.g. us-east-1}"

put() {
  local key="$1" value="$2"
  aws ssm put-parameter \
    --name "/${PROJECT}/${key}" \
    --value "$value" \
    --type SecureString \
    --overwrite \
    --region "$AWS_REGION" >/dev/null
  echo "  set /${PROJECT}/${key}"
}

prompt_secret() {
  local varname="$1" prompt="$2" existing="${!1:-}"
  if [ -n "$existing" ]; then
    printf '%s' "$existing"
    return
  fi
  local value
  read -r -s -p "$prompt: " value >&2
  echo >&2
  printf '%s' "$value"
}

echo "Seeding secrets under /${PROJECT}/ in ${AWS_REGION}."
echo

POSTGRES_USER="${POSTGRES_USER:-marigold}"
POSTGRES_DB="${POSTGRES_DB:-marigold}"

# Generated rather than prompted: a database password nobody types is a
# database password nobody reuses.
if [ -z "${POSTGRES_PASSWORD:-}" ]; then
  POSTGRES_PASSWORD="$(LC_ALL=C tr -dc 'A-Za-z0-9' < /dev/urandom | head -c 40)"
  echo "Generated a 40-character POSTGRES_PASSWORD."
fi
if [ -z "${SECRET_KEY:-}" ]; then
  SECRET_KEY="$(LC_ALL=C tr -dc 'A-Za-z0-9' < /dev/urandom | head -c 64)"
  echo "Generated a 64-character SECRET_KEY (signs JWTs and session cookies)."
fi

GEMINI_API_KEY="$(prompt_secret GEMINI_API_KEY 'GEMINI_API_KEY')"
GOOGLE_CLIENT_ID="${GOOGLE_CLIENT_ID:-}"
GOOGLE_CLIENT_SECRET="${GOOGLE_CLIENT_SECRET:-}"
GITHUB_CLIENT_ID="${GITHUB_CLIENT_ID:-}"
GITHUB_CLIENT_SECRET="${GITHUB_CLIENT_SECRET:-}"

put POSTGRES_USER     "$POSTGRES_USER"
put POSTGRES_PASSWORD "$POSTGRES_PASSWORD"
put POSTGRES_DB       "$POSTGRES_DB"

# Assembled here so the app never has to build it, and so rotating the password
# updates exactly one place that matters. `postgres` is the in-cluster Service.
put DATABASE_URL "postgresql+psycopg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@postgres:5432/${POSTGRES_DB}"

put SECRET_KEY     "$SECRET_KEY"
put GEMINI_API_KEY "$GEMINI_API_KEY"

# OAuth is optional: backend/oauth.py only registers a provider when both of its
# values are present, so empty means "password login only" rather than broken.
[ -n "$GOOGLE_CLIENT_ID" ]     && put GOOGLE_CLIENT_ID     "$GOOGLE_CLIENT_ID"
[ -n "$GOOGLE_CLIENT_SECRET" ] && put GOOGLE_CLIENT_SECRET "$GOOGLE_CLIENT_SECRET"
[ -n "$GITHUB_CLIENT_ID" ]     && put GITHUB_CLIENT_ID     "$GITHUB_CLIENT_ID"
[ -n "$GITHUB_CLIENT_SECRET" ] && put GITHUB_CLIENT_SECRET "$GITHUB_CLIENT_SECRET"

echo
echo "Done. The next deploy will pick these up."
echo "Note: changing POSTGRES_PASSWORD here does NOT change it in an existing"
echo "database — Postgres only reads POSTGRES_PASSWORD when it initialises an"
echo "empty data directory. Rotate it with ALTER ROLE inside the cluster too."
