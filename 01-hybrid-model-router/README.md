# Project 1: The "Dual-Engine" FinOps & Resilient Model Router (vLLM on EKS + Amazon Bedrock)

## The Enterprise Problem It Solves

Customers want the high reasoning of frontier models (Claude 3.5/3.7) but cannot afford the linear token cost at enterprise scale, nor can they risk cloud API quota throttling (HTTP 429) during peak hours.

```
                          [ Ingress Gateway / ALB ]
                                      │
                                      ▼
                        [ Custom Router Microservice ]
                         - Token length estimation
                         - Complexity classifier
                         - Circuit breaker (checks queue depth)
                                      │
                 ┌────────────────────┴────────────────────┐
                 ▼ (High-Volume / Standard)                ▼ (Complex / Failover)
       [ Internal vLLM on EKS ]                   [ Amazon Bedrock ]
       - Qwen2.5-7B-Instruct-AWQ                  - Claude Haiku 4.5 (global profile)
       - Karpenter spot GPU NodePool (`xlarge`)   - Serverless on-demand
       - Scaled via KEDA on waiting queue         - VPC Endpoint / PrivateLink
```

## What You Build (The Deliverables)

### Infrastructure as Code (Terraform)
- VPC with private subnets, VPC Endpoints for Bedrock and ECR.
- EKS Cluster with Karpenter configured for spot GPU instances (`g4dn`, `g5` or `g6` `.xlarge`, one GPU each; Karpenter picks the cheapest available).
- Storage: Amazon EFS (via the EFS CSI driver) caching the model weights to prevent multi-minute cold starts.

### vLLM Serving Stack
- Containerized vLLM engine deployed via Kubernetes manifest.
- Serves `Qwen/Qwen2.5-7B-Instruct-AWQ` (Apache 2.0, ungated, 5.6 GB) as `qwen2.5-7b-awq`, sized to fit one 16 GB T4.
- Configured `/dev/shm` memory mounts, AWQ 4-bit quantization, and chunked prefill.
- KEDA ScaledObject scraping `vllm:num_requests_waiting` from the Prometheus `/metrics` endpoint to autoscale GPU nodes dynamically.

### The Intelligent Router Application (Python / FastAPI)
- Inspects incoming requests: routes high-volume/short context tasks (< 2,000 tokens) to the vLLM cluster.
- Routes complex legal/reasoning tasks (> 2,000 tokens or tagged reasoning) to Amazon Bedrock via the `converse()` API.
- Circuit Breaker: If vLLM's queue depth exceeds 5 or times out, the router automatically fails over to Amazon Bedrock.

### FinOps & Telemetry Dashboard
- OpenTelemetry instrumentation logging tokens per minute, TTFT, and a calculated "Dollar Saved vs. Pure Bedrock" metric.
