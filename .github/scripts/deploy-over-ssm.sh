#!/usr/bin/env bash
# Ship a rendered manifest bundle to the k3s node and roll it out.
#
# Why SSM rather than kubectl-from-CI: infra/security.tf restricts the
# Kubernetes API (6443) to a single known address. GitHub's runners have
# dynamic IPs across very large shared ranges, so allowing them would mean
# exposing cluster admin to a wide net. SSM needs no inbound port at all and
# reuses the instance profile the node already has.
#
# Secrets are deliberately NOT passed through here. SendCommand parameters are
# recorded in command history and readable by anyone with ssm:ListCommands, so
# the node reads them from Parameter Store itself (see refresh_secret below).
#
# Usage: deploy-over-ssm.sh <rendered-manifests.yaml>
set -euo pipefail

MANIFESTS="${1:?usage: deploy-over-ssm.sh <manifests.yaml>}"
: "${INSTANCE_ID:?set INSTANCE_ID (terraform output node_instance_id)}"
: "${AWS_REGION:?set AWS_REGION}"
PROJECT="${PROJECT:-marigold}"
NAMESPACE="${NAMESPACE:-marigold}"

# Base64 so the YAML survives being embedded in a shell command as one token,
# with no quoting or newline handling to get wrong.
B64="$(base64 < "$MANIFESTS" | tr -d '\n')"
echo "Manifest bundle: $(wc -c < "$MANIFESTS") bytes, $(printf %s "$B64" | wc -c) base64."

# SendCommand caps total parameter size at 100KB.
if [ "$(printf %s "$B64" | wc -c)" -gt 90000 ]; then
  echo "ERROR: manifest bundle too large to send over SSM. Stage it in S3 instead." >&2
  exit 1
fi

# POSIX sh, not bash. SSM's AWS-RunShellScript does not guarantee which shell
# runs this, and Ubuntu's /bin/sh is dash — which has no `set -o pipefail`, no
# process substitution and no $'\t'. Using any of those produces a deploy that
# works on one AMI and fails on the next.
read -r -d '' REMOTE <<REMOTE_SCRIPT || true
set -eu
export KUBECONFIG=/etc/rancher/k3s/k3s.yaml

echo "== refreshing application secret from Parameter Store =="
# Every SecureString under /<project>/ becomes a key in the Kubernetes secret,
# so adding a setting is a Parameter Store write rather than a change here.
#
# The value is piped straight into kubectl as an env-file and never touches
# disk. Building it in a variable (rather than a while-read loop over a pipe) is
# also what keeps it working in dash, where a pipeline's last stage runs in a
# subshell and any variable it sets is lost.
PARAMS="\$(
  aws ssm get-parameters-by-path \
    --path "/${PROJECT}/" --recursive --with-decryption \
    --region "${AWS_REGION}" \
    --query 'Parameters[].[Name,Value]' --output text \
    | sed -e 's|^/${PROJECT}/||' -e 's|	|=|'
)"

if [ -z "\$PARAMS" ]; then
  echo "ERROR: no parameters found under /${PROJECT}/ — the app cannot start without them." >&2
  echo "Seed them with infra/scripts/put-secrets.sh" >&2
  exit 1
fi

printf '%s\\n' "\$PARAMS" \
  | kubectl -n "${NAMESPACE}" create secret generic marigold-secrets \
      --from-env-file=/dev/stdin --dry-run=client -o yaml \
  | kubectl apply -f -

echo "== applying manifests =="
echo "${B64}" | base64 -d > /tmp/marigold-manifests.yaml
kubectl apply -f /tmp/marigold-manifests.yaml
rm -f /tmp/marigold-manifests.yaml

echo "== waiting for rollout =="
# The app Deployment uses Recreate and an init container that runs migrations,
# so this is also where a failed migration shows up as a failed deploy.
kubectl -n "${NAMESPACE}" rollout status statefulset/postgres --timeout=300s
kubectl -n "${NAMESPACE}" rollout status deployment/redis --timeout=180s
kubectl -n "${NAMESPACE}" rollout status deployment/app --timeout=420s

echo "== deployed =="
kubectl -n "${NAMESPACE}" get pods -o wide
REMOTE_SCRIPT

echo "Sending command to ${INSTANCE_ID}..."
CMD_ID="$(aws ssm send-command \
  --instance-ids "$INSTANCE_ID" \
  --document-name AWS-RunShellScript \
  --comment "deploy ${GITHUB_SHA:-manual}" \
  --region "$AWS_REGION" \
  --parameters commands="$(printf '%s' "$REMOTE" | python3 -c 'import json,sys; print(json.dumps([sys.stdin.read()]))')" \
  --query 'Command.CommandId' --output text)"

echo "Command id: $CMD_ID"

# send-command returns immediately; poll until the invocation reaches a terminal
# state, then surface the node's own output so a failure is readable here rather
# than only in the SSM console.
STATUS="Pending"
for _ in $(seq 1 120); do
  sleep 10
  STATUS="$(aws ssm get-command-invocation \
    --command-id "$CMD_ID" --instance-id "$INSTANCE_ID" \
    --region "$AWS_REGION" --query 'Status' --output text 2>/dev/null || echo Pending)"
  case "$STATUS" in
    Success|Failed|Cancelled|TimedOut) break ;;
  esac
  echo "  ...$STATUS"
done

echo "--- node stdout ---"
aws ssm get-command-invocation --command-id "$CMD_ID" --instance-id "$INSTANCE_ID" \
  --region "$AWS_REGION" --query 'StandardOutputContent' --output text || true
echo "--- node stderr ---"
aws ssm get-command-invocation --command-id "$CMD_ID" --instance-id "$INSTANCE_ID" \
  --region "$AWS_REGION" --query 'StandardErrorContent' --output text || true

if [ "$STATUS" != "Success" ]; then
  echo "::error::Deploy failed on the node with status: $STATUS"
  echo "Roll back with: kubectl -n ${NAMESPACE} rollout undo deployment/app"
  exit 1
fi
echo "Deploy succeeded."
