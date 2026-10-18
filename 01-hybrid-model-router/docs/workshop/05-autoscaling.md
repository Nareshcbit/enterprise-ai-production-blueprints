# 05 — Autoscaling stack

**Goal:** the controllers that will scale vLLM are running: Karpenter (adds
and removes GPU nodes), KEDA (scales vLLM pods on queue depth), and Prometheus
(feeds KEDA the queue metric). No GPU node can launch yet; that's module 06.

| Piece | What it does here | Where |
|---|---|---|
| Karpenter 1.15.0 | Launches a node when a pod can't be scheduled, removes it when idle | Helm, `kube-system`, pinned to system nodes |
| Karpenter IAM + Pod Identity | Controller role (`<name>-karpenter-controller`), node role (`<name>-karpenter-node`) plus its access entry | Terraform `karpenter` submodule |
| SQS queue + 5 EventBridge rules | Delivers the 2-minute spot interruption notice, rebalance and health events, so Karpenter drains a node before AWS reclaims it | Same submodule |
| KEDA 2.21.0 | Will scale the vLLM Deployment on `vllm:num_requests_waiting` | Helm, `keda` |
| Prometheus (server only) | KEDA's Prometheus scaler runs PromQL, so it needs a server. No Alertmanager, exporters or disk; 2-hour retention | Helm, `monitoring` |

**Version pins:** Karpenter 1.15.x is the only line that supports Kubernetes
1.37. KEDA 2.21 is tested up to 1.36 and logs a warning on 1.37; the APIs it
uses are stable, and it works.

## Steps

Already applied by `make addons` in module 04. If you skipped that:

```bash
make addons
```

## You should see

```bash
kubectl get pods -n kube-system -l app.kubernetes.io/name=karpenter
kubectl get pods -n keda
kubectl get pods -n monitoring
kubectl get apiservice v1beta1.external.metrics.k8s.io
```

- 2 `karpenter` pods `Running`, one per system node. One logs
  `Attempting to acquire leader lease...` forever — that's the standby.
- 3 KEDA pods `Running` (operator, metrics API server, admission webhooks).
  The operator and the metrics API server may each show `RESTARTS 1`: at
  start-up the API server looks for `/certs/ca.crt` before the operator has
  written it. Harmless if the count stays at 1.
- 1 `prometheus-server` pod `Running`.
- The external metrics API `Available: True`.

Prometheus answers from inside the cluster:

```bash
kubectl run prom-test -n monitoring --rm -i --restart=Never \
  --image=public.ecr.aws/docker/library/busybox:1.37 -- \
  wget -qO- 'http://prometheus-server.monitoring.svc.cluster.local/api/v1/query?query=up'
```

returns `"status":"success"`.

Don't test Prometheus through `kubectl get --raw .../services/prometheus-server:80/proxy/...`:
that path goes from the EKS control plane to the pod on port 9090, which the
node security group doesn't open, so it hangs. KEDA queries from inside the
cluster and isn't affected.

## Undo

These charts come out with `terraform destroy` ([08](08-teardown.md)).
