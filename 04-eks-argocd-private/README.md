# 04 · Private Argo CD on Amazon EKS

The enterprise access pattern for the **EKS Capability for Argo CD** (AWS-managed Argo CD), built in one account and Region: an EKS cluster, the managed Argo CD with its UI and API reachable **only** through an `eks-capabilities` interface VPC endpoint, IAM Identity Center sign-in, and least-privilege access to the cluster it deploys to.

Companion to the article *Reaching a managed Argo CD on Amazon EKS: endpoints, identity and hub-and-spoke* on nmadiraju.com. Direct Connect, VPN and Transit Gateway are out of scope here; an SSM-only access host inside the VPC stands in for "a network connected to the VPC".

## What it builds

| Component | Why it's here |
|---|---|
| VPC, 2 AZs, private + public subnets, one NAT gateway | Nodes and endpoints live in private subnets; the NAT gateway serves image pulls and SSM |
| Interface endpoint `com.amazonaws.<region>.eks-capabilities` | Listing its ID on the capability blocks public access; the Argo CD hostname then resolves to its private IPs. Security group: TCP 443 from the VPC only |
| EKS cluster (hub), 2× t3.medium | Hosts the capability's custom resources and the sample app. Public API limited to your IP for `kubectl`; nodes use the private API |
| Argo CD capability (`aws_eks_capability`) | Identity Center sign-in, one identity mapped to ADMIN, `network_access.vpce_ids` = the endpoint |
| Capability IAM role + access policies | Trusts `capabilities.eks.amazonaws.com`. Read: `AmazonEKSAdminViewPolicy`, cluster-wide (Argo CD reads every resource type for health and drift). Write: `AmazonEKSEditPolicy` on the `guestbook` namespace only |
| Access host (t4g.nano, no public IP, SSM only) | The only way to reach Argo CD in this lab: checks from inside the VPC, and a port forward for your browser |
| Sample app (`k8s/`) | The hub registered by ARN, a `guestbook` AppProject, and an Application syncing `argoproj/argocd-example-apps` |

```
laptop ──kubectl (your IP only)──► EKS public API
laptop ──SSM──► access host ──443──► eks-capabilities endpoint ──PrivateLink──► Argo CD (AWS-managed)
                                                                                 │ pulls GitHub from AWS-managed infra
internet ──✗──► Argo CD hostname (public access blocked)                         ▼
                                                                    EKS hub: guestbook namespace
```

## Cost (us-east-1 list prices)

About **$0.35 an hour** while it runs: EKS control plane $0.10, two t3.medium nodes ~$0.083, NAT gateway $0.045 plus data, the interface endpoint ~$0.02 (2 AZs), the access host ~$0.004, and the Argo CD capability **$0.03 per capability-hour + $0.0015 per Application-hour** (one Application here). Run `make destroy` when you're done.

## Prerequisites

- AWS CLI v2.12.3+, Terraform 1.5+, `kubectl`, `envsubst`, `dig`.
- An **IAM Identity Center** instance (`aws sso-admin list-instances`) with a user or group for the Argo CD admin (`aws identitystore list-users` / `list-groups`).
- An S3 bucket for Terraform state (versioning on).
- For `make ui` only: the [Session Manager plugin](https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager-working-with-install-plugin.html) for the AWS CLI.

## Steps

```bash
cd 04-eks-argocd-private
cp terraform/envs/dev/backend.hcl.example     terraform/envs/dev/backend.hcl      # fill in
cp terraform/envs/dev/terraform.tfvars.example terraform/envs/dev/terraform.tfvars # fill in

make check          # tools and AWS identity
make test           # plan-only Terraform tests, no AWS calls
make apply          # ~20-25 min: VPC + endpoint, EKS, Argo CD capability, access host
make argocd-config  # register the hub by ARN, guestbook project + app
make verify         # see below
```

`make verify` proves the design, in five checks:

1. The capability is `ACTIVE`.
2. The Argo CD hostname resolves, **from your laptop**, to private RFC 1918 addresses. AWS publishes these records itself; there is no private hosted zone.
3. HTTPS to Argo CD **from your laptop fails**: public access is blocked.
4. HTTPS to Argo CD **from the access host** inside the VPC succeeds.
5. Argo CD has synced the guestbook app: `Synced/Healthy`.

## Opening the UI

```bash
make ui
```

It prints a line to add to `/etc/hosts` (`127.0.0.1 <argocd-hostname>`), then forwards local port 443 through the access host to the endpoint. Open `https://<argocd-hostname>` and sign in with Identity Center. The hostname and certificate stay the same, so TLS and the sign-in redirect work unchanged. Remove the `/etc/hosts` line afterwards.

## Design notes

- **No load balancer, Ingress or certificate.** Argo CD runs outside the cluster; the only access surface is its AWS-hosted hostname.
- **`private_dns_enabled = false`** on the endpoint. AWS manages the capability hostname's records once `vpce_ids` is set, so no private DNS name is involved.
- **The endpoint security group is the only network filter.** AWS doesn't support VPC endpoint policies for `eks-capabilities`.
- **The hub is registered explicitly, by ARN.** The capability doesn't add the local cluster, and EKS creates its access entry with no permissions.
- **Read access is an EKS access policy, not custom RBAC.** The AWS docs bind a ClusterRole to the group `eks-access-entry:<role-ARN>`; on this build that binding never matched (Argo CD got `apiservices ... is forbidden`). A cluster-scoped `AmazonEKSAdminViewPolicy` association works.
- **`delete_propagation_policy = "RETAIN"`** is the only value AWS accepts, so `make destroy` removes the sample app before Terraform destroys the rest.
- **Git is reached from AWS-managed infrastructure**, not through the VPC endpoint (that carries traffic *to* Argo CD only). A Git server reachable only inside your network needs AWS CodeConnections or a mirror.

## Teardown

```bash
make destroy
```

Deletes the guestbook Application and namespace, runs `terraform destroy`, then deletes any detached VPC CNI network interfaces that would block the VPC deletion.
