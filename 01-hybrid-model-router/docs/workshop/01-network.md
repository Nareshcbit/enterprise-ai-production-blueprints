# 01 — Network

**Goal:** a VPC with two public and two private subnets across two AZs, one
NAT gateway, and a security group for testing from CloudShell.

| Resource | Why |
|---|---|
| `10.0.0.0/16` VPC, private `10.0.1.0/24` + `10.0.2.0/24` | ALB, Fargate tasks, EKS nodes and EFS all live in private subnets |
| Public `10.0.101.0/24` + `10.0.102.0/24` | Only the NAT gateway sits here |
| One NAT gateway | Outbound internet for image pulls, Hugging Face and AWS APIs. One is enough for a lab; set `single_nat_gateway = false` for one per AZ |
| Private subnet tags | `kubernetes.io/role/internal-elb=1` (the vLLM NLB) and `karpenter.sh/discovery=<name>` (Karpenter finds subnets by tag) |
| `<name>-cloudshell` security group | Outbound only. Lets a CloudShell VPC environment call the internal ALB |
| S3 gateway endpoint | Free. Keeps ECR image-layer pulls (stored in S3) off the NAT gateway |

**Interface endpoints are off** (`enable_vpc_endpoints = false`). Endpoints for
Bedrock Runtime, ECR API and ECR Docker would keep that traffic inside AWS's
network, but each costs ~$0.01/hr per AZ — about $0.06/hr ($43/month) for
three across two AZs, more than the NAT data charges they'd save in a lab. Set
it to `true` for production, where traffic volume and "no internet path"
requirements change the math.

## Steps

```bash
make network
```

which runs:

```bash
terraform -chdir=terraform/envs/dev init
terraform -chdir=terraform/envs/dev apply -target=module.networking
```

Terraform warns that `-target` is for exceptional use. That's expected here —
see *Why the build is staged* in the [README](README.md).

## You should see

```
Apply complete! Resources: 22 added, 0 changed, 0 destroyed.
```

```bash
terraform -chdir=terraform/envs/dev output vpc_id
terraform -chdir=terraform/envs/dev output private_subnet_ids
```

prints a VPC ID and two private subnet IDs.

## Undo

```bash
terraform -chdir=terraform/envs/dev destroy -target=module.networking
```

Only before module 02 exists; later modules depend on this network.
