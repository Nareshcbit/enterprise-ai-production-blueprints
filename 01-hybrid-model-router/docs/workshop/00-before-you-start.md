# 00 — Before you start

**Goal:** your laptop has the tools, your AWS identity can build everything,
Bedrock can serve Claude, and a GPU quota request is in flight.

## Get the code

```bash
git clone https://github.com/Nareshcbit/enterprise-ai-production-blueprints.git
cd enterprise-ai-production-blueprints/01-hybrid-model-router
```

Every command in this workshop runs from that folder.

## 1. Install the tools (macOS)

```bash
brew install awscli terraform kubectl helm gettext   # gettext provides envsubst
brew install --cask docker                           # Docker Desktop, for image builds
```

Start Docker Desktop once so its daemon is running.

| Tool | Version used in this workshop |
|---|---|
| Terraform | ≥ 1.5 (AWS provider ~> 6.28, Helm provider ~> 3.3) |
| kubectl | 1.37 |
| Helm | 4.x |
| AWS CLI | v2 |

## 2. Configure AWS credentials

Use an IAM principal with administrator access in the target account (an IAM
Identity Center role is best; long-lived IAM user keys work for a lab).

```bash
aws configure            # or: aws sso login --profile <profile>
aws sts get-caller-identity
```

Note the `Arn` it prints. You need it in step 5.

## 3. Create the Terraform state bucket

State lives in S3 with native locking (`use_lockfile`, no DynamoDB table). Use
an existing bucket or create one, with versioning on:

```bash
BUCKET=<your-state-bucket>
aws s3api create-bucket --bucket $BUCKET --region us-east-1
aws s3api put-bucket-versioning --bucket $BUCKET --versioning-configuration Status=Enabled
```

Then point Terraform at it. `backend.hcl` is gitignored, so your bucket name
stays out of the repo:

```bash
cd terraform/envs/dev
cp backend.hcl.example backend.hcl     # set bucket and region (the bucket's Region)
cd -
```

`make init` (run by every Terraform target) passes it with
`-backend-config=backend.hcl`.

## 4. Enable Claude Haiku 4.5 on Bedrock

The gateway calls `global.anthropic.claude-haiku-4-5-20251001-v1:0`, a global
cross-Region inference profile.

1. Open the Bedrock console in **us-east-1** → **Model catalog** →
   **Claude Haiku 4.5**.
2. Anthropic models need a one-time use-case form per account. Submit it if
   the console asks.
3. Open the model in the **playground** and send one message. If it answers,
   the gateway's IAM role will be able to call it too.

## 5. Request GPU spot quota (do this now — it can take days)

New accounts have a GPU quota of **0 vCPUs**. The quota counts vCPUs, not GPUs:
one `g4dn.xlarge` / `g5.xlarge` / `g6.xlarge` is 4 vCPUs and 1 GPU.

```bash
aws service-quotas request-service-quota-increase --region us-east-1 \
  --service-code ec2 --quota-code L-3819A6DF --desired-value 4
```

`L-3819A6DF` is **All G and VT Spot Instance Requests**. Track it in the
console: Service Quotas → Amazon EC2 → that quota → *Recent quota increase
requests*. Small requests are sometimes approved in minutes; when a support
case opens, expect 24–48 hours. Modules 01–05 don't need it.

## 6. Create `terraform.tfvars`

```bash
cp terraform/envs/dev/terraform.tfvars.example terraform/envs/dev/terraform.tfvars
```

It's gitignored: it holds your account ID and ARNs. Set:

| Variable | Set it to |
|---|---|
| `region` | `us-east-1` (keep it unless you also move the Bedrock profile and quota) |
| `name` | A short prefix, e.g. `ai-router-dev`. It names the VPC, cluster, roles |
| `eks_access_entries` | Your ARN from step 2 as `admin`, **plus** anyone who uses the EKS console |
| `gateway_image_tag` | The tag you'll build in module 02, e.g. `0.2.2` |

`eks_access_entries` matters more than it looks: the cluster grants nobody
access by default (`enable_cluster_creator_admin_permissions = false`), and
Terraform itself installs Helm charts with your credentials. If your ARN is
missing, module 05 fails with `Unauthorized`.

## You should see

```bash
make check
```

```
AWS identity: arn:aws:iam::<ACCOUNT_ID>:user/<you>
Region: us-east-1  Name: ai-router-dev  Gateway image: 0.2.2
```

No `missing:` lines, and no `Docker is not running`.
