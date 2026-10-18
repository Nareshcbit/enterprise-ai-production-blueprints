# 06 — vLLM on spot GPUs

**Goal:** vLLM serves Qwen2.5-7B-Instruct-AWQ on a spot GPU node that
Karpenter launches on demand, behind an internal NLB, and the gateway routes
standard requests to it.

**Needs:** the G and VT spot quota from [00](00-before-you-start.md), step 5
(at least 4 vCPUs). Check it:

```bash
aws service-quotas get-service-quota --region us-east-1 \
  --service-code ec2 --quota-code L-3819A6DF --query Quota.Value
```

| Piece | What it does | File |
|---|---|---|
| AWS Load Balancer Controller 3.6.0 | Creates the NLB for the vLLM Service. EKS's built-in controller only gets critical fixes; AWS recommends this one | Terraform (`make addons`) |
| EC2NodeClass `gpu` | Bottlerocket (`bottlerocket@latest`; its NVIDIA variant ships the GPU driver and device plugin), 8 GiB OS + 80 GiB image volume | `k8s/gpu-nodepool.yaml` |
| NodePool `gpu` | Spot only; `g4dn`/`g5`/`g6` `.xlarge` (Karpenter picks the cheapest); `nvidia.com/gpu` taint; CPU limit 4 = the quota; removes the node 5 min after it's empty | `k8s/gpu-nodepool.yaml` |
| Deployment `vllm` | vLLM 0.32.0, the model from EFS (read-only), `--quantization=awq --dtype=half` (T4: no bf16, no Marlin), 8k context, chunked prefill | `k8s/vllm-deployment.yaml` |
| Service `vllm` | Internal NLB, IP targets, port 8000, open to the VPC CIDR only | `k8s/vllm-service.yaml` |
| ScaledObject `vllm` | KEDA scales on `sum(vllm:num_requests_waiting)`, 1 replica per 2 waiting. Min and max are 1 while the quota allows one GPU node | `k8s/keda-scaledobject.yaml` |

## Steps

**1. Install the Load Balancer Controller** (already done if you ran
`make addons` after pulling this version):

```bash
make addons
```

**2. Create the GPU NodePool.** No node launches yet; nothing needs a GPU.

```bash
make gpu
kubectl get ec2nodeclass gpu      # READY True within ~30 s
```

**3. Deploy vLLM, its NLB and the ScaledObject:**

```bash
make vllm
```

The vLLM pod is `Pending` — that's what makes Karpenter launch a GPU node.
Watch it happen:

```bash
kubectl get nodeclaims -w
```

```
NAME        TYPE          CAPACITY   ZONE         NODE                         READY
gpu-fqkn9   g4dn.xlarge   spot       us-east-1a   ip-10-0-1-155.ec2.internal   True
```

**4. Wait for vLLM** (`1/1 Running`). The first start on a fresh node took
~13 minutes in testing:

| Phase | Time |
|---|---|
| Karpenter launches the spot node → node `Ready` | ~1 min |
| Pull `vllm/vllm-openai:v0.32.0` (9.2 GB) through the NAT gateway | ~7 min |
| Load weights from EFS (21 s), compile, warm up, allocate KV cache | ~2.5 min |

```bash
kubectl rollout status -n vllm deploy/vllm --timeout=20m
kubectl logs -n vllm deploy/vllm | grep -E 'Loading weights took|GPU KV cache size|startup complete'
```

```
Loading weights took 20.75 seconds
GPU KV cache size: 113,744 tokens, Maximum concurrency for 8,192 tokens per request: 13.88x
INFO:     Application startup complete.
```

**5. Point the gateway at vLLM.** The NLB's name changes on every rebuild:

```bash
make vllm-url
```

Put the printed address into `terraform/envs/dev/terraform.tfvars`:

```hcl
vllm_api_base    = "http://k8s-vllm-vllm-xxxxxxxxxx-xxxxxxxxxxxxxxxx.elb.us-east-1.amazonaws.com:8000/v1"
vllm_metrics_url = "http://k8s-vllm-vllm-xxxxxxxxxx-xxxxxxxxxxxxxxxx.elb.us-east-1.amazonaws.com:8000/metrics"
```

then roll the gateway (a new task definition revision, no downtime):

```bash
make gateway
```

## You should see

```bash
kubectl get pods -n vllm -l app=vllm      # 1/1 Running
kubectl get scaledobject -n vllm vllm     # READY True
kubectl get hpa -n vllm                   # keda-hpa-vllm   0/2 (avg)   1   1   1
```

The NLB target is healthy:

```bash
LB=$(aws elbv2 describe-load-balancers --region us-east-1 \
  --query "LoadBalancers[?starts_with(DNSName,'k8s-vllm-vllm')].LoadBalancerArn|[0]" --output text)
TG=$(aws elbv2 describe-target-groups --region us-east-1 --load-balancer-arn $LB \
  --query 'TargetGroups[0].TargetGroupArn' --output text)
aws elbv2 describe-target-health --region us-east-1 --target-group-arn $TG \
  --query 'TargetHealthDescriptions[].TargetHealth.State'
```

```
[ "healthy" ]
```

## Call vLLM directly

vLLM speaks the OpenAI API. Its model name is `qwen2.5-7b-awq`.

**From your laptop**, with a port-forward (no VPC access needed):

```bash
kubectl port-forward -n vllm svc/vllm 8000:8000
```

and in another terminal:

```bash
curl -s localhost:8000/v1/chat/completions -H "Content-Type: application/json" -d '{
  "model": "qwen2.5-7b-awq",
  "max_tokens": 100,
  "messages": [{"role": "user", "content": "Extract the invoice number from: INV-4471, due 2026-11-01."}]
}' | jq -r '.choices[0].message.content'
```

```
The invoice number is INV-4471.
```

Other endpoints on the same port:

| Endpoint | Returns |
|---|---|
| `GET /v1/models` | `qwen2.5-7b-awq` |
| `GET /health` | `200` once the model is loaded |
| `GET /metrics` | Prometheus metrics, including `vllm:num_requests_waiting` (what KEDA and the circuit breaker read) |

**From inside the VPC** (a CloudShell VPC environment), through the NLB:

```bash
VLLM=<address printed by make vllm-url on your laptop>
curl -s $VLLM/v1/chat/completions -H "Content-Type: application/json" \
  -d '{"model":"qwen2.5-7b-awq","max_tokens":100,"messages":[{"role":"user","content":"Hello"}]}'
```

**Through the gateway** (the normal path): send `"model": "auto"` to the ALB
and the router decides ([07](07-end-to-end-test.md)); send
`"model": "vllm-local"` to force vLLM.

> **vLLM has no API key here.** The port-forward and the NLB reach it
> directly, and the NLB accepts any caller inside the VPC — fine for a lab.
> In production, let clients reach vLLM only through the gateway: limit the
> NLB's source range to the gateway's security group, or start vLLM with
> `--api-key`.

## Turning the GPU off between sessions

The GPU node is ~$0.30/hr. To stop paying for it without tearing down:

```bash
# KEDA owns the replica count (min 1), so pause it at 0 rather than kubectl scale.
kubectl annotate -n vllm scaledobject vllm autoscaling.keda.sh/paused-replicas=0 --overwrite
```

Karpenter removes the empty node after 5 minutes. The router's circuit breaker
can't reach vLLM and sends everything to Bedrock. To turn it back on:

```bash
kubectl annotate -n vllm scaledobject vllm autoscaling.keda.sh/paused-replicas-
```

Measured in the rehearsal:

| Step | Time |
|---|---|
| Pause → vLLM at 0 replicas | seconds |
| → Karpenter marks the node `Empty` and terminates it | 5 min 20 s (EC2 billing stops at `shutting-down`) |
| Un-pause → first spot launch | **failed: `InsufficientCapacityError`** |
| → Karpenter retries after its ~3-minute back-off | 3 min 20 s |
| → new `g4dn.xlarge` spot node `Ready`, image pulled (4 m 34 s), vLLM ready | 12 min 20 s in all |

Spot capacity isn't guaranteed: a launch can fail, and Karpenter waits about 3
minutes before retrying the offerings that failed. Listing three instance
families across two AZs gives it somewhere else to go.

## Undo

```bash
kubectl delete -f k8s/keda-scaledobject.yaml -f k8s/vllm-deployment.yaml
kubectl delete svc -n vllm vllm                  # deletes the NLB
kubectl delete nodepool gpu && kubectl delete ec2nodeclass gpu
```

Set `vllm_api_base`/`vllm_metrics_url` back to `http://vllm.invalid:8000/...`
and `make gateway`.
