#!/usr/bin/env bash
# Prove the private-access design works: Argo CD is ACTIVE, its hostname
# resolves to private IPs, it can't be reached from here, it can be reached
# from inside the VPC, and it has synced the sample app.
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TF="terraform -chdir=$PROJECT_DIR/terraform/envs/dev"
TFVARS="$PROJECT_DIR/terraform/envs/dev/terraform.tfvars"

tfvar() { sed -n "s/^$1[[:space:]]*=[[:space:]]*\"\(.*\)\"/\1/p" "$TFVARS"; }
REGION="$(tfvar region)"
NAME="$(tfvar name)"

step() { printf '\n==> %s\n' "$1"; }
fail() { echo "FAIL: $1" >&2; exit 1; }

SERVER_URL="$($TF output -raw argocd_server_url)"
HOST="${SERVER_URL#https://}"
ACCESS_HOST="$($TF output -raw access_host_id)"

step "1. Capability status"
status="$(aws eks describe-capability --region "$REGION" --cluster-name "$NAME" \
  --capability-name argocd --query 'capability.status' --output text)"
echo "$status"
[ "$status" = "ACTIVE" ] || fail "capability is $status, not ACTIVE"

step "2. DNS from this machine: $HOST"
ips="$(dig +short "$HOST" | grep -E '^[0-9.]+$' || true)"
echo "${ips:-<no answer>}"
[ -n "$ips" ] || fail "no A records for $HOST"
for ip in $ips; do
  [[ "$ip" =~ ^10\.|^172\.(1[6-9]|2[0-9]|3[01])\.|^192\.168\. ]] || fail "$ip is not a private address"
done
echo "All private addresses."

step "3. HTTPS from this machine (should NOT connect)"
if curl -sS -o /dev/null --connect-timeout 8 "$SERVER_URL/" 2>/dev/null; then
  fail "reached Argo CD from outside the VPC; public access is not blocked"
fi
echo "Not reachable from here, as intended."

step "4. HTTPS from the access host inside the VPC"
params="$(printf '{"commands":["getent hosts %s","curl -sS -o /dev/null -w '"'"'HTTP %%{http_code}'"'"' --connect-timeout 8 %s/; echo"]}' "$HOST" "$SERVER_URL")"
cmd_id="$(aws ssm send-command --region "$REGION" --instance-ids "$ACCESS_HOST" \
  --document-name AWS-RunShellScript --parameters "$params" \
  --query 'Command.CommandId' --output text)"
for _ in $(seq 1 20); do
  sleep 3
  state="$(aws ssm get-command-invocation --region "$REGION" --command-id "$cmd_id" \
    --instance-id "$ACCESS_HOST" --query Status --output text 2>/dev/null || echo Pending)"
  case "$state" in Success|Failed|Cancelled|TimedOut) break ;; esac
done
out="$(aws ssm get-command-invocation --region "$REGION" --command-id "$cmd_id" \
  --instance-id "$ACCESS_HOST" --query StandardOutputContent --output text)"
echo "$out"
# Any HTTP answer (the UI, or a redirect to sign in) proves the private path works.
echo "$out" | grep -qE "HTTP [23][0-9][0-9]" || fail "access host could not reach Argo CD"

step "5. Sample app synced by Argo CD"
aws eks update-kubeconfig --region "$REGION" --name "$NAME" >/dev/null
sync="$(kubectl get application guestbook -n argocd -o jsonpath='{.status.sync.status}/{.status.health.status}')"
echo "$sync"
[ "$sync" = "Synced/Healthy" ] || fail "guestbook is $sync (it can take a few minutes after argocd-config)"
kubectl get deploy,svc -n guestbook

printf '\nAll checks passed.\n'
