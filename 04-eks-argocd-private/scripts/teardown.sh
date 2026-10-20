#!/usr/bin/env bash
# Tear down Project 4 in the order that leaves nothing behind.
# The capability's delete policy is RETAIN (the only value AWS accepts), so the
# sample app is removed first; then terraform destroys the rest.
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TF_DIR="$PROJECT_DIR/terraform/envs/dev"
TFVARS="$TF_DIR/terraform.tfvars"

tfvar() { sed -n "s/^$1[[:space:]]*=[[:space:]]*\"\(.*\)\"/\1/p" "$TFVARS"; }
REGION="$(tfvar region)"
NAME="$(tfvar name)"

step() { printf '\n==> %s\n' "$1"; }

remove_sample_app() {
  aws eks describe-cluster --region "$REGION" --name "$NAME" >/dev/null 2>&1 || return 0
  step "Kubernetes: removing the sample app and Argo CD objects"
  aws eks update-kubeconfig --region "$REGION" --name "$NAME" >/dev/null
  kubectl delete application guestbook -n argocd --ignore-not-found --wait=true --timeout=5m
  kubectl delete namespace guestbook --ignore-not-found --wait=true --timeout=5m
}

delete_orphaned_cni_interfaces() {
  # The VPC CNI can leave detached "aws-K8S-<instance>" interfaces behind when a
  # node goes away; terraform destroy then fails with DependencyViolation on the
  # subnet and node security group. Delete only detached ones in this VPC.
  local vpc enis eni
  vpc="$(aws ec2 describe-vpcs --region "$REGION" --filters "Name=tag:Name,Values=$NAME" \
    --query 'Vpcs[0].VpcId' --output text)"
  [ "$vpc" = "None" ] && return 0
  step "VPC: deleting detached VPC CNI interfaces"
  enis="$(aws ec2 describe-network-interfaces --region "$REGION" \
    --filters "Name=vpc-id,Values=$vpc" "Name=status,Values=available" "Name=description,Values=aws-K8S-*" \
    --query 'NetworkInterfaces[].NetworkInterfaceId' --output text)"
  [ -z "$enis" ] && { echo "None found."; return 0; }
  for eni in $enis; do
    aws ec2 delete-network-interface --region "$REGION" --network-interface-id "$eni"
    echo "Deleted $eni"
  done
}

remove_sample_app
step "Terraform: destroying everything else"
terraform -chdir="$TF_DIR" destroy
delete_orphaned_cni_interfaces
