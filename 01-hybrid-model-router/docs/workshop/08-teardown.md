# 08 — Teardown

**Goal:** nothing from this workshop is left running or billing.

`terraform destroy` alone isn't enough. Some AWS resources are created by
controllers *inside* the cluster, not by Terraform, and they outlive it if the
cluster goes first:

| Created by | Resource | Removed by |
|---|---|---|
| Karpenter | GPU EC2 instances (module 06) | Deleting the NodePools while Karpenter still runs |
| AWS Load Balancer integration | vLLM NLB (module 06) | Deleting the `vllm` namespace (its Service) |
| EFS CSI driver | EFS access point | Deleted with the file system |
| You | Images in ECR | Deleting them first; the repository won't delete otherwise |
| VPC CNI | A detached `aws-K8S-<instance>` network interface left by a terminated node | Deleting it before `terraform destroy`; it blocks the subnet and node security group |

## Steps

```bash
make destroy
```

which runs `scripts/teardown.sh`:

1. Deletes Karpenter NodePools and EC2NodeClasses and waits for their
   instances to terminate (skipped if Karpenter isn't installed).
2. Deletes the `vllm` namespace (Deployment, Service/NLB, PVC, Job) and the
   `efs-models` StorageClass.
3. Deletes every image in the gateway ECR repository.
4. Deletes detached `aws-K8S-*` network interfaces the VPC CNI left behind in the
   stack's VPC (only detached ones; nothing attached is touched).
5. Runs `terraform destroy`. **Review the plan, then type `yes`.** Expect
   ~15–20 minutes, mostly the EKS cluster and NAT gateway.
6. Deletes the Container Insights log group, which ECS creates itself, so
   Terraform doesn't own it.
7. Reports any Karpenter instance or vLLM load balancer still alive.

## You should see

```
Destroy complete! Resources: 127 destroyed.

==> Checking for leftovers
No Karpenter instances.
```

and no load balancer names after it.

## What's left on purpose

| Item | Why it stays | Cost |
|---|---|---|
| Terraform state bucket | Created in module 00, outside this stack | Cents |
| Secrets Manager master key | Scheduled for deletion after a 30-day recovery window, not deleted at once. A rebuild gets a new name, so it doesn't clash | $0 while pending |
| GPU quota increase | Account setting | $0 |
| Local Docker images | On your laptop | $0 |

Check the bill's **Cost Explorer → Service** view the next day; EC2, EKS, ELB
and VPC (NAT) should drop to zero.
