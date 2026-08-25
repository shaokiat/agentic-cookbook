# Deploying vLLM on GCP

Concept-first. Cloud Run is the first rung because it scales to zero; GKE is the second rung,
for when you need multi-replica routing, node-level control, or a GPU pool you already own.

Prerequisites everywhere: a GCP project with billing, `gcloud` authenticated, the
Compute/Artifact Registry/Cloud Run APIs enabled, and **an approved GPU quota** — quota is the
step that actually blocks people, and it is not instant.

---

## The shape of the problem

vLLM is an ordinary container that listens on a port. Three things make it different from a
normal web service, and every decision below follows from them:

1. **It needs a GPU.** That constrains region, machine type, and cost far more than anything else.
2. **Cold start is dominated by weight download, not process startup.** An 8B model is several
   GB pulled from Hugging Face before the server can answer anything. Expect minutes, not
   seconds, and set health-check timeouts accordingly.
3. **It is stateful in memory only.** The KV cache lives in GPU memory and dies with the pod.
   There is nothing to persist — but there is a lot to *cache*, namely the weights.

That third point is why the interesting choice is where weights come from:

| Approach | Cold start | Image size | Best for |
| :--- | :--- | :--- | :--- |
| Download from HF at boot | Slowest | Small | First deploy, experimenting |
| Bake weights into the image | Fast | Huge (multi-GB pushes) | Fixed model, frequent scaling |
| Mount from GCS (FUSE) or a PVC | Medium | Small | Several models, or shared across replicas |

Start with the first. Move to the third when cold starts annoy you.

---

## Rung 1: Cloud Run with GPU

Why here first: **scale-to-zero.** An always-on GPU node costs real money per month whether or
not it serves a request; Cloud Run bills for the time a request is being handled. For a
cookbook backend, a side project, or anything bursty, that is the difference between a rounding
error and a bill you notice. (Check current pricing before committing — GPU pricing moves.)

```bash
./deploy/vllm/gcp/cloudrun-deploy.sh
```

The tradeoffs you are accepting:

- **Cold starts are brutal** with weight download on the critical path. Set `--min-instances=1`
  when you care about latency, and accept that you have just given up scale-to-zero.
- **Request timeouts cap generation length.** A long completion can outlive the timeout.
- **One GPU per instance**, no tensor parallelism, so model size is capped by a single card.
- Concurrency is set per-instance (`--concurrency`) — exactly the dial that
  [`03_load_sweep.py`](../../../examples/07_inference/03_load_sweep.py) measures. Set it from
  your measured knee, not from a guess.

Point the cookbook at the result:

```bash
HOSTED_VLLM_API_BASE=https://<service-url>/v1
HOSTED_VLLM_API_KEY=<the key you set>
```

---

## Rung 2: GKE

Move here when you need more than one replica behind a load balancer, tensor parallelism across
cards, or GPU nodes shared with other workloads.

```bash
kubectl create secret generic hf-token --from-literal=token="$HF_TOKEN"
kubectl create secret generic vllm-api-key --from-literal=key="$VLLM_API_KEY"
kubectl apply -f deploy/vllm/gcp/gke/
```

What the manifests demonstrate, and why each part exists:

- **`nodeSelector` on `cloud.google.com/gke-accelerator`** — pins the pod to a GPU node pool.
  Without it the scheduler will happily place the pod on a CPU node where it will never start.
- **`nvidia.com/gpu: 1` in resource limits** — GPUs are not shareable by default; request and
  limit must match.
- **A long `startupProbe`, a short `readinessProbe`** — the weight-download problem expressed in
  Kubernetes. The startupProbe's generous `failureThreshold` gives the model time to load; the
  readinessProbe then keeps traffic away during transient stalls. Using only a readinessProbe
  with a long `initialDelaySeconds` is the common mistake: it makes *every* restart slow, not
  just the first.
- **`emptyDir: {medium: Memory}` at `/dev/shm`** — the default 64MB shm breaks NCCL as soon as
  you use tensor parallelism across more than one GPU, and it fails confusingly. Set it now.
- **HF token as a Secret**, never in the manifest.
- **HPA on `vllm:num_requests_waiting`**, not on CPU. CPU utilisation on a GPU inference server
  is close to meaningless; queue depth is the signal that tells you the KV cache is saturated.

Cost control on GKE, in order of impact: spot GPU nodes (with a `terminationGracePeriodSeconds`
long enough to drain), cluster autoscaler with `minNodes: 0` on the GPU pool, and node
auto-provisioning so the expensive pool only exists while something needs it.

---

## Why not local Kubernetes

kind/k3d/Docker Desktop on a Mac cannot GPU-accelerate this. Metal has no GPU passthrough into
containers, so a pod would fall back to vLLM's CPU backend and be unusably slow. You can still
`kubectl apply` these manifests locally to validate structure, probes, and secret wiring — just
don't expect inference. See [`../README.md`](../README.md).

---

## Not covered here, deliberately

Multi-model routing, LoRA hot-swapping, speculative decoding, and prefix-cache-aware load
balancing all matter at production scale, and none are worth configuring before you have
measured a knee. The manifests here are the skeleton to hang that on.
