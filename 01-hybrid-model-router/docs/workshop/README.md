# Workshop: Build a Hybrid LLM Router on AWS

Build, from an empty AWS account, a gateway that sends each LLM request to the
cheapest model that can handle it: a self-hosted model (vLLM on a spot GPU in
EKS) for routine work, Claude on Amazon Bedrock for hard requests and as the
fallback.

```
 client ──► internal ALB ──► LiteLLM gateway on ECS Fargate
                              │  rules → semantic cache → background LLM judge
                              │  circuit breaker on the vLLM queue
                ┌─────────────┴──────────────┐
                ▼ standard                   ▼ complex / fallback
     vLLM on EKS (spot GPU)            Amazon Bedrock
     Qwen2.5-7B-Instruct-AWQ           Claude Haiku 4.5
     weights on EFS                    (global inference profile)
     Karpenter + KEDA scaling
```

## Modules

| # | Module | You build | Time | Cost while running |
|---|---|---|---|---|
| 00 | [Before you start](00-before-you-start.md) | Tools, access, quotas | 20 min (+ quota wait) | $0 |
| 01 | [Network](01-network.md) | VPC, subnets, NAT gateway | 5 min | ~$0.05/hr |
| 02 | [Gateway](02-gateway.md) | LiteLLM router on Fargate behind an internal ALB | 15 min | ~$0.10/hr |
| 03 | [EKS cluster](03-eks.md) | Kubernetes 1.37, 2 system nodes, access entries | 20 min | ~$0.18/hr |
| 04 | [Model storage](04-model-storage.md) | EFS, the CSI driver, the model weights | 10 min | ~$2/month |
| 05 | [Autoscaling stack](05-autoscaling.md) | Karpenter, KEDA, Prometheus | 10 min | ~$0 |
| 06 | [vLLM on spot GPUs](06-vllm.md) | Karpenter GPU NodePool, vLLM, internal NLB, KEDA | 20 min | ~$0.32/hr (spot `g4dn.xlarge` + NLB) |
| 07 | [End-to-end test](07-end-to-end-test.md) | Every routing path, from CloudShell | 10 min | Bedrock tokens |
| 08 | [Teardown](08-teardown.md) | Delete everything, in order | 20 min | $0 after |
| 09 | [Troubleshooting](09-troubleshooting.md) | Errors you may hit, and fixes | | |

Running modules 01–05 costs about **$0.35/hr** (NAT gateway, ALB, 2 Fargate
tasks, EKS control plane, 2 `t3.medium` nodes); module 06 adds ~$0.32/hr for
the spot GPU and NLB, about **$0.70/hr** in all. Tear down when you stop for
the day: rebuilding takes about an hour and a half, and leaving it up costs
~$17/day.
Prices are us-east-1 list prices on 2026-10-18; check current pricing.

## How each module works

Every module has the same shape:

1. **Goal** — what exists when you're done.
2. **Steps** — copy-paste commands. Every Terraform step prints its plan and
   waits for you to type `yes`. Read the plan before you do.
3. **You should see** — the check that proves the step worked.
4. **Undo** — how to back out just this module.

All commands run from the **project folder**, `01-hybrid-model-router/`,
unless a step says otherwise. The `Makefile` there wraps each stage (`make network`, `make gateway`, …); each
module also shows the raw commands, so you can see what the target does.

## Why the build is staged

`terraform apply` can't build everything in one pass from an empty account:

- The Helm provider (Karpenter, KEDA, Prometheus) connects to the EKS API, so
  the cluster must exist before Terraform can plan those releases.
- The gateway's ECS service needs its container image in ECR, and the ECR
  repository is created by the same module.

So each module applies one slice with `-target`, and module 05 runs the final
full `terraform apply`, which must show no changes to earlier slices.
