#!/usr/bin/env bash
# Tear down Project 1 in the order that leaves nothing behind.
# Kubernetes-created AWS resources (Karpenter nodes, NLBs) are removed while
# their controllers still run; then terraform destroys the rest.
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TF_DIR="$PROJECT_DIR/terraform/envs/dev"
TFVARS="$TF_DIR/terraform.tfvars"

tfvar() { sed -n "s/^$1[[:space:]]*=[[:space:]]*\"\(.*\)\"/\1/p" "$TFVARS"; }
REGION="$(tfvar region)"
NAME="$(tfvar name)"

step() { printf '\n==> %s\n' "$1"; }

cluster_exists() {
  aws eks describe-cluster --region "$REGION" --name "$NAME" >/dev/null 2>&1
}

remove_kubernetes_resources() {
  step "Kubernetes: removing workloads that own AWS resources"
  aws eks update-kubeconfig --region "$REGION" --name "$NAME" >/dev/null

  # Karpenter terminates its own EC2 instances when its NodePools are deleted.
  if kubectl get crd nodepools.karpenter.sh >/dev/null 2>&1; then
    kubectl delete nodepools.karpenter.sh --all --wait=true --timeout=10m
    kubectl delete ec2nodeclasses.karpenter.k8s.aws --all --wait=true --timeout=5m
  fi

  # Deleting the namespace removes the vLLM NLB Service, Deployment, PVC and Job.
  kubectl delete namespace vllm --ignore-not-found --wait=true --timeout=10m
  kubectl delete storageclass efs-models --ignore-not-found
}

empty_ecr_repository() {
  local repo="$NAME-gateway"
  step "ECR: deleting images in $repo"
  # Docker pushes an image index plus child manifests. ECR won't delete a child
  # while an index in the same call still references it, so repeat until empty.
  local ids pass
  for pass in 1 2 3; do
    ids="$(aws ecr list-images --region "$REGION" --repository-name "$repo" \
      --query 'imageIds[*]' --output json 2>/dev/null || echo '[]')"
    [ "$ids" = "[]" ] && return 0
    aws ecr batch-delete-image --region "$REGION" --repository-name "$repo" \
      --image-ids "$ids" >/dev/null
  done
  echo "ECR repository $repo is still not empty after $pass passes" >&2
  exit 1
}

delete_unmanaged_log_groups() {
  # ECS creates this Container Insights log group itself; Terraform doesn't own it.
  local group="/aws/ecs/containerinsights/$NAME-gateway/performance"
  step "CloudWatch: deleting $group"
  aws logs delete-log-group --region "$REGION" --log-group-name "$group" 2>/dev/null \
    || echo "Not found; nothing to delete."
}

report_leftovers() {
  step "Checking for leftovers"
  local instances
  instances="$(aws ec2 describe-instances --region "$REGION" \
    --filters "Name=tag:karpenter.sh/discovery,Values=$NAME" \
              "Name=instance-state-name,Values=pending,running,stopping" \
    --query 'Reservations[].Instances[].InstanceId' --output text)"
  [ -z "$instances" ] && echo "No Karpenter instances." || echo "STILL RUNNING: $instances"
  aws elbv2 describe-load-balancers --region "$REGION" \
    --query "LoadBalancers[?contains(LoadBalancerName, 'vllm')].LoadBalancerName" --output text
}

if cluster_exists; then
  remove_kubernetes_resources
else
  echo "EKS cluster $NAME not found; skipping Kubernetes cleanup."
fi
empty_ecr_repository

step "Terraform: destroying everything (review the plan, then type yes)"
export PATH="/Applications/Docker.app/Contents/Resources/bin:$PATH"
terraform -chdir="$TF_DIR" destroy

delete_unmanaged_log_groups
report_leftovers
