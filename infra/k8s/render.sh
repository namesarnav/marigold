#!/usr/bin/env bash
# Substitute deployment-specific values into the manifests and print them.
#
# The manifests in this directory are committed with PLACEHOLDER tokens rather
# than real values, because the domain, bucket and image registry all come from
# `terraform output` and differ per environment. This script is the single place
# that substitution happens, so CI and a human running it by hand produce byte
# identical output.
#
# Usage:
#   DOMAIN=marigold.example.com \
#   ACME_EMAIL=you@example.com \
#   AWS_REGION=us-east-1 \
#   ARTIFACTS_BUCKET=marigold-artifacts-abc123 \
#   SES_FROM_EMAIL=no-reply@marigold.example.com \
#   IMAGE_REPO=123456789012.dkr.ecr.us-east-1.amazonaws.com/marigold/app \
#   IMAGE_TAG=<git sha> \
#   ./render.sh | kubectl apply -f -
set -euo pipefail

: "${DOMAIN:?set DOMAIN (e.g. marigold.example.com)}"
: "${ACME_EMAIL:?set ACME_EMAIL — Let us Encrypt needs a contact address}"
: "${AWS_REGION:?set AWS_REGION}"
: "${ARTIFACTS_BUCKET:?set ARTIFACTS_BUCKET (terraform output artifacts_bucket)}"
: "${IMAGE_REPO:?set IMAGE_REPO (terraform output ecr_repository_urls)}"
: "${IMAGE_TAG:?set IMAGE_TAG — use the commit SHA, never the latest tag}"
SES_FROM_EMAIL="${SES_FROM_EMAIL:-no-reply@${DOMAIN}}"

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

cp "$HERE"/*.yaml "$WORK/"

# `kubectl kustomize` renders; the substitution happens on the copy so the
# committed files keep their placeholders.
for f in "$WORK"/*.yaml; do
  sed -i.bak \
    -e "s|DOMAIN_PLACEHOLDER|${DOMAIN}|g" \
    -e "s|ACME_EMAIL_PLACEHOLDER|${ACME_EMAIL}|g" \
    -e "s|AWS_REGION_PLACEHOLDER|${AWS_REGION}|g" \
    -e "s|ARTIFACTS_BUCKET_PLACEHOLDER|${ARTIFACTS_BUCKET}|g" \
    -e "s|SES_FROM_EMAIL_PLACEHOLDER|${SES_FROM_EMAIL}|g" \
    -e "s|IMAGE_REPO_PLACEHOLDER|${IMAGE_REPO}|g" \
    -e "s|IMAGE_TAG_PLACEHOLDER|${IMAGE_TAG}|g" \
    "$f"
  rm -f "$f.bak"
done

# Fail loudly rather than applying a manifest that still contains a placeholder.
# Matches the exact tokens, not the bare word, so prose in a comment cannot trip
# it and a genuinely missed substitution cannot slip through.
TOKENS='(DOMAIN|ACME_EMAIL|AWS_REGION|ARTIFACTS_BUCKET|SES_FROM_EMAIL|IMAGE_REPO|IMAGE_TAG)_PLACEHOLDER'
if grep -rEl "$TOKENS" "$WORK" >/dev/null 2>&1; then
  echo "ERROR: unsubstituted placeholders remain:" >&2
  grep -rEn "$TOKENS" "$WORK" >&2
  exit 1
fi

# The ClusterIssuer is emitted outside the kustomization: see the note in
# kustomization.yaml on why it must not pass through the namespace transformer.
cat "$WORK/issuer.yaml"
echo "---"
kubectl kustomize "$WORK"
