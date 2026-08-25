# 07 Inference and Serving

The layer below `core/model.py`. Everything else in this cookbook treats "call a model" as a
primitive; this section opens it up — running open-weight models yourself, measuring what you
get, and deciding whether it is worth it.

Concepts live in [`docs/inference_serving.md`](../../docs/inference_serving.md).
Running a server lives in [`deploy/vllm/`](../../deploy/vllm/).

---

## Concept Ladder

| Level | Pattern | File |
| :---- | :------ | :--- |
| 0 | Install and run vLLM, mlx-lm, and Ollama — verified commands | `00_running_engines.md` |
| 1 | Discover configured backends and stream one completion through each | `01_backends.py` |
| 2 | Separate TTFT (prefill) from ITL (decode) on a single stream | `02_benchmark.py` |
| 3 | Sweep concurrency to find the throughput/latency knee | `03_load_sweep.py` |
| — | Shared measurement primitives and the on-disk result schema | `harness.py` |

---

## Setup

Full, verified instructions for all three engines are in
**[`00_running_engines.md`](00_running_engines.md)** — installing `vllm-metal` on Apple
Silicon, standing up `mlx_lm.server` as the control, and configuring Ollama so it batches.

Everything uses a **0.6B model**. This is a proof of concept: a small model loads in seconds,
leaves room for 64 concurrent requests on a 16GB laptop, and shows the throughput curve just
as clearly as a large one would.

The short version — one engine at a time, all on the same port:

```bash
make serve-vllm      # subject   — vllm-metal, PagedAttention + continuous batching
make serve-mlx       # control   — same weights, same backend, one request at a time
make serve-ollama    # baseline  — llama.cpp + GGUF, OLLAMA_NUM_PARALLEL=32

make stop            # between engines
make probe           # which one is live, what it loaded, one timed completion
make bench ENGINE=vllm
```

```bash
# .env
LOCAL_API_BASE=http://localhost:8000/v1
LOCAL_API_KEY=cookbook-local
```

`discover()` probes that one URL and identifies the engine behind it, so swapping engines
needs no config edit and cannot mislabel a saved result.

To use the local model *elsewhere* in the repo — the Streamlit sidebar picker, any other
example — also set the litellm provider var for the engine you are running
(`HOSTED_VLLM_API_BASE` for vLLM, `OLLAMA_API_BASE` for Ollama); litellm resolves
`hosted_vllm/*` and `ollama_chat/*` against those.

---

## Examples

### `01_backends.py` — Inference Backends

```
env vars ──▶ discover() ──▶ probe /models or /api/tags
                              ├── vllm    up   Qwen3-8B-4bit
                              └── ollama  up   qwen3:8b
                                    │
                                    ▼  one identical streaming completion each
                              TTFT / ITL / decode tok/s
```

**Usage**: `.venv/bin/python examples/07_inference/01_backends.py`

Expect the backends to look *similar* here. At concurrency 1 both are memory-bandwidth-bound
on the same hardware. That is the setup for level 3, not a null result.

### `02_benchmark.py` — Single-Stream Benchmark

Runs a fixed prompt suite, then one deliberately long prompt. TTFT jumps on the long prompt
while ITL barely moves — prefill and decode are different workloads.

**Usage**: `.venv/bin/python examples/07_inference/02_benchmark.py`

### `03_load_sweep.py` — Concurrency Load Sweep

```
concurrency  1 ──▶ 2 ──▶ 4 ──▶ 8 ──▶ 16 ──▶ 32
     │
     ▼  run_concurrent() + scrape vLLM /metrics
aggregate tok/s ▲ ── knee ── ▶ flat (KV cache full, queueing begins)
per-request p95 ▲ ── stable ── ▶ degrading
```

**Usage**: `.venv/bin/python examples/07_inference/03_load_sweep.py`

This is where continuous batching becomes visible. Writes `results/load_sweep.json`.

---

## Results

Runs write JSON to `results/`. The Streamlit page (**Inference & Serving → Benchmarks**) merges
every file there into one comparison, so charts render on any machine with no backend running.

Measured on an M-series Mac with 16GB unified memory, `Qwen3-0.6B` at 4-bit, 128 output tokens
per request, one engine running at a time.

### The controlled comparison

vLLM and mlx-lm serve the **same MLX weights** at the **same quantization** on the **same Metal
backend**. The only difference is the scheduler.

| Concurrency | vLLM tok/s | mlx-lm tok/s | vLLM p95 | mlx-lm p95 |
| ---: | ---: | ---: | ---: | ---: |
| 1 | 172.6 | 146.8 | 738ms | 872ms |
| 4 | 531.5 | 350.6 | 961ms | 1458ms |
| 8 | 600.7 | 397.0 | 1703ms | 2566ms |
| 16 | 732.2 | 458.6 | 2789ms | 4452ms |
| **32** | **1098.4** | **621.8** | **3709ms** | **6564ms** |
| 64 | 1129.8 | 581.9 | 7211ms | 14009ms |

Both knee at concurrency 32. There, vLLM sustains **1.8× the throughput at half the p95
latency** — it wins both axes at once, which is the thing continuous batching buys and the
reason the two are not a tradeoff here.

Note how the gap *widens* with load: 1.18× at concurrency 1, 1.77× at 32. That is the whole
argument of this section in one number. A reviewer who benchmarked only a single stream would
have reported a 1.18× difference and drawn the wrong conclusion about capacity.

Past the knee, mlx-lm actually goes backwards (622 → 582 tok/s from 32 to 64) while its p95
doubles. vLLM flattens instead of degrading, because queued requests wait in the scheduler
rather than contending.

### Single stream, all three engines

| Engine | Quantization | TTFT p50 | ITL p50 | decode tok/s |
| :--- | :--- | ---: | ---: | ---: |
| vLLM | 4bit (MLX) | 104ms | 5.6ms | 204.4 |
| mlx-lm | 4bit (MLX) | 92ms | 6.1ms | 163.0 |
| Ollama | Q4_K_M (GGUF) | 204ms | 10.4ms | 97.3 |

Ollama runs GGUF rather than MLX weights, so its row mixes quantization and runtime differences
with the scheduler — it is a real-world data point, not a controlled one.

### What is not here

**No Ollama concurrency sweep.** It was cut off mid-run: at `OLLAMA_NUM_PARALLEL=32`, the top
levels took long enough to saturate the test machine. To collect it:

```bash
OLLAMA_NUM_PARALLEL=32 ollama serve
BENCH_LEVELS=1,2,4,8,16 BENCH_SAVE_AS=ollama_sweep.json \
  .venv/bin/python examples/07_inference/03_load_sweep.py
```

**No NVIDIA numbers.** Everything here is Metal via `vllm-metal`. Absolute values will not
transfer to a CUDA box; the *shape* of the curves will.

**The KV cache never saturated.** vLLM reported 10% cache utilisation even at concurrency 64 —
a 0.6B model with 128-token outputs simply cannot fill an 86,704-token cache. So the knee here
is compute saturation, not cache pressure. On a larger model or with long contexts you would
hit the cache ceiling first and see `num_requests_waiting` climb, which is the case
`docs/inference_serving.md` describes.

Never commit a made-up record. The schema has a `synthetic` flag and the UI badges it, but the
honest default is an empty `results/`.

## Making a fair comparison

The most common way to get this wrong: Ollama defaults to a quantized GGUF and vLLM to fp16
safetensors, so comparing them as shipped measures quantization, not the serving engine. Hold
dtype, context length, prompt/output length, and concurrency constant — and record them, which
is why they are fields in the result schema rather than prose. Also set `OLLAMA_NUM_PARALLEL`
deliberately; leaving it at the default and concluding "vLLM batches better" measures config.

Full list of confounds: [`docs/inference_serving.md`](../../docs/inference_serving.md).
