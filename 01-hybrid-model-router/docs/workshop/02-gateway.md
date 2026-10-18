# 02 — Gateway

**Goal:** the LiteLLM gateway with the routing plugin runs as 2 Fargate tasks
behind an internal ALB, and answers chat completions from Claude on Bedrock.

| Resource | Why |
|---|---|
| ECR repository `<name>-gateway` | Immutable tags, keeps the last 10 images |
| Secrets Manager master key | Clients send `Authorization: Bearer <key>`; LiteLLM won't start without one |
| Internal ALB, port 80 → 4000 | Reachable only from inside the VPC. Health check `/health/liveliness` |
| ECS cluster + service, 2 tasks (1 vCPU, 2 GB) | Runs the router image. ECS Exec is on for debugging |
| Task role: `bedrock:InvokeModel*` | Scoped to the inference profile and the models it routes to |

Until vLLM exists (module 06), set `vllm_api_base` and `vllm_metrics_url` to
`http://vllm.invalid:8000/v1` and `.../metrics` (or leave a previous build's
NLB address — it no longer resolves either). The
circuit breaker can't reach it, so every request goes to Bedrock. That's the
intended safe state.

## Steps

The ECS service needs its image in ECR, and ECR is created by this module, so
it takes three commands.

**1. Create the ECR repository only** (2 resources: the repository and its
lifecycle policy):

```bash
make ecr
```

**2. Build and push the router image** (tag comes from `gateway_image_tag`):

```bash
make image
```

which runs:

```bash
REPO=$(terraform -chdir=terraform/envs/dev output -raw gateway_ecr_repository_url)
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin ${REPO%%/*}
docker build --platform linux/amd64 -t $REPO:0.2.2 app
docker push $REPO:0.2.2
```

`--platform linux/amd64` matters on Apple Silicon: Fargate tasks here run
x86_64. The build bakes the embedding model (`BAAI/bge-small-en-v1.5`) into
the image, so tasks never download it at start-up. Expect 3–5 minutes.

**3. Create the ALB, cluster, service and secret** (24 resources):

```bash
make gateway
```

## You should see

Both tasks healthy behind the ALB (allow ~2 minutes after apply):

```bash
LB=$(aws elbv2 describe-load-balancers --region us-east-1 --names ai-router-dev-gateway \
  --query 'LoadBalancers[0].LoadBalancerArn' --output text)
TG=$(aws elbv2 describe-target-groups --region us-east-1 --load-balancer-arn $LB \
  --query 'TargetGroups[0].TargetGroupArn' --output text)
aws elbv2 describe-target-health --region us-east-1 --target-group-arn $TG \
  --query 'TargetHealthDescriptions[].TargetHealth.State'
```

```
[ "healthy", "healthy" ]
```

## Test it from CloudShell

The ALB is internal, so call it from inside the VPC.

1. In the console, open **CloudShell** → **Actions** → **Create VPC
   environment**. Pick the VPC, one **private** subnet, and the security group
   from `terraform output cloudshell_security_group_id`.
2. In that environment, set up (copy the two values from `terraform output`):

```bash
ALB=http://<gateway_alb_dns_name>
KEY=$(aws secretsmanager get-secret-value --region us-east-1 \
  --secret-id <gateway_master_key_secret_arn> --query SecretString --output text)
curl -s -o /dev/null -w "health=%{http_code}\n" $ALB/health/liveliness
```

```
health=200
```

3. Send a request with `model: auto`, so the router decides:

```bash
curl -s $ALB/v1/chat/completions -D - -o /tmp/body \
  -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
  -d '{"model":"auto","max_tokens":60,"messages":[{"role":"user","content":"Extract the invoice number from: INV-4471, due 2026-11-01."}]}' \
  | grep -i x-litellm-model-group
cat /tmp/body
```

```
x-litellm-model-group: bedrock-claude
{"id":"...","choices":[{"message":{"content":"INV-4471", ...
```

4. See the routing decision in the logs:

```bash
aws logs tail /aws/ecs/<name>-gateway/litellm-gateway --region us-east-1 \
  --since 15m --format short --filter-pattern route
```

You'll see `route.decision ... cache=miss`, `route.chosen model=bedrock-claude`,
and a few seconds later `route.judged tier=...` from the background judge.

## Undo

```bash
aws ecr batch-delete-image --region us-east-1 --repository-name <name>-gateway \
  --image-ids imageTag=0.2.2
terraform -chdir=terraform/envs/dev destroy -target=module.gateway
```

The repository can't be deleted while it holds images, hence the first command.
