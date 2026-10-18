# 03 — EKS cluster

**Goal:** an EKS 1.37 cluster with two small on-demand system nodes, the core
add-ons, and access entries for the people who use it.

| Resource | Why |
|---|---|
| EKS control plane, public + private endpoint | Public for `kubectl` from your laptop (still IAM-authenticated); private so nodes reach the API inside the VPC |
| Managed node group `system`: 2 × `t3.medium`, on-demand | Runs CoreDNS, Karpenter, KEDA, Prometheus. On-demand on purpose: if a spot reclaim took out Karpenter, nothing could replace nodes |
| Add-ons | `vpc-cni`, `kube-proxy`, `coredns`, `eks-pod-identity-agent`, `aws-efs-csi-driver` |
| Access entries from `eks_access_entries` | `admin` → `AmazonEKSClusterAdminPolicy`, `view` → `AmazonEKSViewPolicy`, cluster-wide |
| KMS key | Envelope encryption of Kubernetes secrets (module default, ~$1/month) |

Kubernetes 1.37 was the newest standard-support version on 2026-10-18. Check
yours with `aws eks describe-cluster-versions --region us-east-1`. If you pick
another version, check Karpenter's compatibility matrix in module 05.

## Steps

```bash
make eks
```

which runs:

```bash
terraform -chdir=terraform/envs/dev apply -target=module.gpu_compute.module.eks
```

This also creates the EFS CSI driver's IAM role, because the add-on depends on
it. The control plane takes ~10 minutes, the node group another ~3.

Then point `kubectl` at the cluster:

```bash
make kubeconfig
```

## You should see

```bash
kubectl get nodes
kubectl get pods -n kube-system
```

```
NAME                         STATUS   ROLES    AGE   VERSION
ip-10-0-1-xxx.ec2.internal   Ready    <none>   3m    v1.37.0-eks-...
ip-10-0-2-xxx.ec2.internal   Ready    <none>   3m    v1.37.0-eks-...
```

and `aws-node`, `kube-proxy`, `eks-pod-identity-agent`, `efs-csi-node` (2 each),
`coredns` and `efs-csi-controller` (2 each) all `Running`.

In the EKS console, the cluster's **Resources** tab loads without
"Unauthorized" errors, as long as your console identity is in
`eks_access_entries`.

## Adding someone later

Add an entry to `eks_access_entries` and re-run `terraform apply`:

```hcl
eks_access_entries = {
  me = {
    principal_arn = "arn:aws:iam::<ACCOUNT_ID>:user/<you>"
    access        = "admin"
  }
  readonly-sso = {
    principal_arn = "arn:aws:iam::<ACCOUNT_ID>:role/aws-reserved/sso.amazonaws.com/AWSReservedSSO_AWSReadOnlyAccess_<suffix>"
    access        = "view"
  }
}
```

IAM role ARNs with a path (like SSO roles) are accepted as-is.

## Undo

```bash
terraform -chdir=terraform/envs/dev destroy -target=module.gpu_compute
```

Only before module 04's Kubernetes objects exist; otherwise use [08](08-teardown.md).
