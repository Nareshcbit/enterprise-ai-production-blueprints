# 09 — Troubleshooting

Errors hit while building this workshop, and the fix for each.

## AWS access

**`AccessDeniedException` calling Bedrock, though the model shows "Available"**
The account hasn't completed Anthropic's first-use form, or that model isn't
offered in your Region yet. Submit the form, send one message from the
playground, then retry. Switching to an inference profile you can invoke
(this workshop uses Haiku 4.5's global profile) also fixes it.

**EKS console: "Your current IAM principal doesn't have access to Kubernetes
objects" / lots of `Unauthorized`**
Your console identity has no access entry. Add its ARN to
`eks_access_entries` and `terraform apply`. Signed in as the **root user**?
Its ARN is `arn:aws:iam::<ACCOUNT_ID>:root` — but prefer an admin role.

**Spot GPU node never launches; Karpenter logs `MaxSpotInstanceCountExceeded`
or `VcpuLimitExceeded`**
The G and VT spot quota is still 0. See [00](00-before-you-start.md), step 5.

## Terraform

**`Error locating chart ... exec: "docker-credential-desktop": executable file
not found in $PATH`**
Helm reads `~/.docker/config.json`, which names Docker Desktop's credential
helper, but its folder isn't on your `PATH`. The `Makefile` adds it. When
running Terraform by hand:

```bash
export PATH="/Applications/Docker.app/Contents/Resources/bin:$PATH"
```

**`make image`: `make: docker: No such file or directory`, though `docker
login` worked**
Docker Desktop's `docker` CLI isn't on your `PATH` (no `/usr/local/bin/docker`
link). macOS ships GNU Make 3.81, which looks up a simple command on the
*original* `PATH` even after the Makefile changes it; `docker login` worked
only because it's part of a pipe, which runs in a shell. The Makefile now calls
`docker` by full path when it isn't on `PATH`. To fix it for your shell too:
Docker Desktop → Settings → Advanced → *System (requires password)*.

**`Kubernetes cluster unreachable` or Helm `Unauthorized` during plan**
Either the cluster doesn't exist yet (run module 03 first — see *Why the
build is staged*), or the identity running Terraform is not in
`eks_access_entries`.

**`ResourceInUseException: NodeGroup already exists` (409) during `make eks`**
Terraform lost the connection while waiting (laptop slept, Wi-Fi dropped),
retried the create, and the retry found the node group the first call made.
The node group is fine; it just isn't in state. Import it, then re-run:

```bash
terraform -chdir=terraform/envs/dev import \
  'module.gpu_compute.module.eks.module.eks_managed_node_group["system"].aws_eks_node_group.this[0]' \
  '<name>:<node-group-name-from-the-error>'
make eks
```

The re-run creates only the add-ons that were waiting for the nodes. Keep the
laptop awake during long applies (`caffeinate -i make eks` on macOS).

**`ecr`: "policy is required"**
Fixed in the module (`attach_repository_policy = false`). Appears if you set
`create_repository_policy` without a policy.

**Destroy fails after ~20 minutes: `DependencyViolation` deleting a private subnet
and the EKS node security group**
A network interface is still in the subnet. Find it:

```bash
aws ec2 describe-network-interfaces --region us-east-1 \
  --filters Name=subnet-id,Values=<subnet-id> \
  --query 'NetworkInterfaces[].[NetworkInterfaceId,Status,Description]' --output text
```

If it is `available` (detached) and named `aws-K8S-i-<instance>`, the VPC CNI created it
for pod IPs on a node that has since terminated (here, the spot GPU node Karpenter
removed). Delete it with `aws ec2 delete-network-interface --network-interface-id <eni>`
and run `make destroy` again. The teardown script now does this before
`terraform destroy`. Anything *attached* (`in-use`) belongs to something still running:
find that first.

**Destroy fails: `RepositoryNotEmptyException`**
Delete the images first (`make destroy` does). Deleting by tag isn't enough:
Docker pushes an image index plus untagged child manifests (the amd64 image and
a build attestation), and ECR refuses to delete a child while an index in the
same call references it. Repeat `batch-delete-image` until `list-images` is
empty; the teardown script does up to 3 passes.

## Gateway

**Tasks keep restarting; logs say a master key is required**
LiteLLM refuses to start without `LITELLM_MASTER_KEY`. Check the ECS task
definition has the secret, and the execution role can read it.

**`curl` from CloudShell: `health=000`**
You're in the default CloudShell environment, not a VPC environment, or the
VPC environment didn't use the `cloudshell` security group. The ALB is
internal-only.

**Every request goes to `bedrock-claude`**
Expected until module 06: `vllm_api_base` points at `vllm.invalid`, so the
circuit breaker can't read the vLLM queue and fails safe to Bedrock.

## Kubernetes

**`kubectl get --raw .../proxy/...` to Prometheus hangs**
The control plane can't reach pod port 9090 (node security group). Query from
a pod inside the cluster instead — see [05](05-autoscaling.md).

**Pod stuck in `ContainerCreating`: `FailedMount ... Failed to resolve
"fs-xxxx.efs.<region>.amazonaws.com"`**
Right after `make addons` creates EFS, the mount targets' DNS names take a few
minutes to resolve. The kubelet retries; it cleared in ~6 minutes in testing.
If it lasts longer than 10, check that both mount targets are `available`
(`aws efs describe-mount-targets --file-system-id <id>`) and that the EFS
security group allows TCP 2049 from the node security group.

**Karpenter: `InvalidBlockDeviceMapping: Volume of size 4GB is smaller than
snapshot ..., expect size >= 6GB`; NodePool `READY False`**
The EC2NodeClass OS volume is smaller than Bottlerocket's current OS snapshot
(6 GB). `gpu-nodepool.yaml` uses 8 GiB; if a future AMI grows again, raise
`/dev/xvda`'s `volumeSize`.

**vLLM crashes at start-up: `ValueError: VLLM_PORT 'tcp://172.20.x.x:8000'
appears to be a URI`**
Kubernetes injects `<SERVICE>_PORT` variables for each Service in the
namespace; a Service named `vllm` produces `VLLM_PORT`, which vLLM reads as
its own setting. The Deployment sets `enableServiceLinks: false` to stop it.

**`InsufficientCapacityError ... insufficient capacity, with fleet error`, then
`nodepool requirements filtered out all available instance types` for ~3 min**
No spot capacity for the offerings Karpenter tried. It marks them unavailable
for about 3 minutes, then retries; in the rehearsal the retry succeeded. If it
keeps failing, widen the NodePool (more families, e.g. `g6e`, or more AZs) or
allow `on-demand` as a fallback (that needs the separate on-demand G and VT
quota, which also starts at 0).

**vLLM pod `Pending` with no NodeClaim**
Check `kubectl get nodepool gpu` is `READY True` and Karpenter's logs
(`kubectl logs -n kube-system -l app.kubernetes.io/name=karpenter`). A
quota of 0 shows as `MaxSpotInstanceCountExceeded`; no spot capacity in any
listed type shows as `InsufficientInstanceCapacity` — Karpenter keeps
retrying other types and AZs.

**KEDA operator: `Error updating webhook with certificate ... the object has
been modified`**
A race while the operator creates its certificates at start-up. It retries
and stops; ignore it unless it repeats after a minute.

**KEDA metrics server: `too_many_pings`**
Harmless gRPC keepalive chatter between KEDA's components.
