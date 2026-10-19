# 04 — Model storage

**Goal:** the model weights sit on EFS, so a new GPU node loads them from
inside the VPC in seconds instead of downloading 5.6 GB from Hugging Face.

| Resource | Why |
|---|---|
| EFS file system `<name>-models` | Encrypted, **Bursting** throughput (no throughput charge; a new file system starts with burst credits), **backups off** (the weights can be re-downloaded) |
| Mount targets in both private subnets | One per AZ, so a GPU node in either AZ can mount it |
| Security group | NFS (TCP 2049) only from the EKS node security group |
| StorageClass `efs-models` | Dynamic provisioning: one EFS access point per claim under `/models`. `Retain`, so deleting the claim keeps the weights |
| PVC `model-weights` (ReadWriteMany) | Mounted by the download Job now, and every vLLM pod later |
| Job `model-download` | Runs `hf download Qwen/Qwen2.5-7B-Instruct-AWQ` onto the volume |

**Why this model:** the GPU node costs the same whichever model runs on it, so
pick the best one that fits a 16 GB T4 (the cheapest GPU). Qwen2.5-7B-Instruct
AWQ is 5.6 GB, Apache 2.0, and **ungated** — no Hugging Face token needed.

## Steps

**1. Create EFS and the rest of the AWS resources** (this is the final full
apply, 38 resources; it also installs module 05's charts and module 06's
Load Balancer Controller):

```bash
make addons
```

The plan must show **no changes** to resources from modules 01–03. If it
does, stop and check what changed.

**2. Create the namespace, StorageClass and PVC:**

```bash
make storage
```

which runs:

```bash
kubectl apply -f k8s/namespace.yaml
EFS_FILE_SYSTEM_ID=$(terraform -chdir=terraform/envs/dev output -raw efs_file_system_id) \
  envsubst < k8s/model-storage.yaml | kubectl apply -f -
```

`model-storage.yaml` holds `${EFS_FILE_SYSTEM_ID}` instead of an ID because
the ID changes every time you rebuild.

**3. Download the model:**

```bash
make model
```

## You should see

```bash
kubectl get pvc -n vllm
```

```
NAME            STATUS   VOLUME     CAPACITY   ACCESS MODES   STORAGECLASS
model-weights   Bound    pvc-...    20Gi       RWX            efs-models
```

(EFS doesn't enforce the 20Gi; Kubernetes just requires a size.)

The download itself takes ~1 minute. On a fresh build the pod may first sit
in `ContainerCreating` for up to ~6 minutes with `FailedMount ... Failed to
resolve "fs-....efs.us-east-1.amazonaws.com"`: the mount targets were created
moments ago and their DNS names haven't propagated yet. The kubelet retries on
its own; just wait. When it finishes, it lists the files:

```
✓ Downloaded
  path: /models/qwen2.5-7b-instruct-awq
total 5.2G
-rw-r--r--. 1 50000 50000 3.8G ... model-00001-of-00002.safetensors
-rw-r--r--. 1 50000 50000 1.5G ... model-00002-of-00002.safetensors
...
```

Owner `50000` is the access point's user; files are world-readable, so vLLM
can read them whatever user it runs as. Lines like `Still waiting to acquire
lock` and `You are sending unauthenticated requests` are normal.

## Undo

```bash
kubectl delete namespace vllm
kubectl delete storageclass efs-models
```

The EFS file system itself goes with `terraform destroy` ([08](08-teardown.md)).
