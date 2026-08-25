# LLM Inference and Serving: What Happens Below the API Call

[`llm_provider_strategies.md`](llm_provider_strategies.md) asks *who owns the translation layer*
between your agent and a provider's wire format. This document asks the layer below it: **who
runs the weights, and why does the same model on the same GPU produce wildly different numbers
depending on how requests arrive?**

You need this to read the charts in [`examples/07_inference/`](../examples/07_inference/), and
to size anything you deploy from [`deploy/vllm/`](../deploy/vllm/).

---

## Generation is two different workloads wearing one coat

A single completion has two phases with opposite performance characteristics.

**Prefill** processes the whole prompt at once. Every token attends to every earlier token in
one big matrix multiply. This is *compute-bound* — the GPU's FLOPs are the limit, and the
hardware is well fed.

**Decode** emits one token at a time. Each step reads the entire model's weights out of memory
to produce a single token. This is *memory-bandwidth-bound*, and the arithmetic intensity is
terrible: you move gigabytes to compute a few thousand FLOPs.

That asymmetry explains the two metrics that matter:

- **TTFT** (time to first token) is dominated by prefill, so it scales with prompt length.
- **ITL** (inter-token latency, sometimes TPOT) is dominated by decode, so it scales with
  model size and memory bandwidth — and is nearly independent of prompt length.

An agent loop with a 20k-token context and a 50-token tool call is almost entirely prefill.
A chat UI streaming a long answer is almost entirely decode. Optimising the wrong one is the
most common mistake in this area.

---

## The KV cache is the thing you are actually managing

To avoid recomputing attention over the whole prefix at every decode step, the server caches
each token's key and value tensors. That cache is per-request, grows with every token
generated, and lives in GPU memory next to the weights.

```
GPU memory = model weights (fixed) + KV cache (grows with tokens × concurrent requests) + overhead
```

The cache is not small. Roughly:

```
bytes ≈ 2 (K and V) × layers × kv_heads × head_dim × dtype_bytes × tokens
```

For a 7–8B model at fp16 this lands in the low hundreds of KB per token — so a single 8k-token
conversation costs on the order of a gigabyte, and *the KV cache, not the weights, is what caps
your concurrency.* Grouped-query attention (GQA) exists largely to shrink the `kv_heads` term.

This reframes the whole problem. Serving throughput is a memory allocation problem wearing a
performance costume.

---

## What vLLM actually does

Two ideas, and they compose.

### PagedAttention

Naive servers allocate one contiguous KV buffer per request, sized to the *maximum* possible
length. A request that generates 100 tokens with an 8k limit wastes 98% of its reservation.
Across a batch, most of your GPU memory is holding nothing.

PagedAttention borrows virtual memory's answer: split the cache into fixed-size blocks, keep a
per-request block table, allocate blocks on demand. Fragmentation collapses, and the same GPU
holds several times more concurrent sequences. It also makes prefix sharing cheap — two
requests with an identical system prompt can point at the same blocks, which matters a great
deal for agents, where every request in a session repeats the same large preamble.

### Continuous batching

Static batching waits for a batch to fill, runs all of it to completion, then starts the next.
The whole batch runs at the speed of its longest member, and finished sequences sit idle
burning a slot.

Continuous batching schedules at the *iteration* level: after every decode step, finished
sequences leave and queued ones join. The GPU stays saturated. This is where the throughput
gap comes from — and why **it is invisible at concurrency 1.**

That last point is worth stating flatly, because it is the trap: at one request at a time,
vLLM and a llama.cpp-based server on the same hardware are both memory-bandwidth-bound and
will look similar. Benchmark with a single stream and you will conclude there is no
difference, and you will be wrong. The difference only appears when requests overlap.

---

## Throughput and latency are the same dial

Adding concurrency adds work to each decode iteration. Every request's per-token latency gets
slightly worse, while total tokens produced per second gets much better — until the KV cache
fills, at which point the scheduler starts queueing (or preempting), and latency degrades
sharply while throughput flattens.

```
aggregate tok/s
     │                    ╭──────────  ← KV cache saturated: queueing begins
     │              ╭─────╯
     │        ╭─────╯                  ← the knee: best throughput per unit of latency
     │   ╭────╯
     │╭──╯
     └──────────────────────────────── concurrency
```

The knee is the only number that matters for capacity planning, and it is what
[`examples/07_inference/03_load_sweep.py`](../examples/07_inference/03_load_sweep.py) plots.
"Tokens per second" quoted without a concurrency level is not a measurement.

vLLM exposes its internal state at `/metrics` in Prometheus format —
`vllm:num_requests_running`, `vllm:num_requests_waiting`, and the KV cache usage gauge. Watching
those three during a sweep turns the paragraph above into something you can see happening.

---

## Making a fair comparison

Most published vLLM-vs-Ollama comparisons are invalid, and in a predictable way: Ollama
defaults to a quantized GGUF, vLLM to fp16 safetensors. Comparing them as shipped measures
**quantization**, not the serving engine, and the direction of the error flatters whichever
side happened to be quantized more aggressively.

To compare engines, hold these constant and state them in the results:

| Variable | Why it corrupts the comparison |
| :--- | :--- |
| Quantization / dtype | 4-bit vs fp16 is a ~4× memory difference; dominates everything else |
| Max context length | Sets the KV cache reservation, so it sets max concurrency |
| Prompt and output length | TTFT tracks input, ITL tracks output; mixing them mixes the phases |
| Concurrency | The single most important axis, and the most often omitted |
| Hardware | Unified memory on Apple Silicon behaves unlike discrete VRAM |
| `OLLAMA_NUM_PARALLEL` | Left at the default, this measures config, not engine |

This is why the result records in `examples/07_inference/results/` carry `dtype`,
`max_model_len`, `hardware`, and `concurrency` as first-class fields rather than prose.

---

## Where this leaves Apple Silicon

There is no CUDA on a Mac. The `vllm-metal` plugin runs vLLM's scheduler over an MLX compute
backend, so PagedAttention and continuous batching are genuinely present and the knee is
genuinely observable — but the absolute numbers are not comparable to an NVIDIA box, and
Metal has no GPU passthrough into containers, which is why local Kubernetes cannot serve
accelerated inference on a Mac at all. See [`deploy/vllm/README.md`](../deploy/vllm/README.md).

---

## Cost

The reason to care. A frontier API model bills per token with zero idle cost. A GPU instance
bills per hour whether or not it is serving anything.

The crossover is entirely about **utilisation**, and self-hosting only wins on cost at
sustained high volume — which is why scale-to-zero (Cloud Run) beats an always-on cluster for
everything short of production traffic. The `$/1M tokens` column in the benchmark UI computes
this from your measured throughput and your actual instance price, rather than from a vendor's
best-case number.

Cost is also not the only axis: data residency, latency floors, fine-tuned weights, and
offline operation are all reasons to self-host a model that is, token for token, more
expensive than the API.
