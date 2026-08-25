# Single-Stream Benchmark: Walkthrough

## What it does

Runs a fixed three-prompt suite `repeats` times against each live backend, then one deliberately long prompt (~120 lines of fake agent transcript). Reports TTFT p50/p95, ITL p50, and decode tokens/sec, and writes `results/single_stream.json`.

## Key insight

TTFT and ITL measure two different machines wearing one coat.

**Prefill** processes the entire prompt in one pass — compute-bound, scales with prompt length, and is essentially all of TTFT. **Decode** emits one token at a time, re-reading the model's weights from memory for each one — memory-bandwidth-bound, scales with model size, and is essentially all of ITL.

The long-prefill prompt makes this visible: TTFT jumps several-fold while ITL barely moves. Which one you should optimise depends entirely on your workload. An agent loop with a 20k-token context and a 50-token tool call is almost all prefill; a chat UI streaming a long answer is almost all decode.

What this example *cannot* tell you is which server is better. One stream measures what one user feels, not what the hardware can do. Capacity is [`03_load_sweep.py`](03_load_sweep.py).

## Run it

```bash
.venv/bin/python examples/07_inference/02_benchmark.py
```

Neither label has to be passed any more: hardware is fixed in `harness.HARDWARE`, and dtype is read off the server at probe time — Ollama reports its quantization in `/api/tags`, and for vLLM/mlx-lm it comes from the model name. `BENCH_DTYPE` overrides that when a name does not say (an fp16 checkpoint, say).

## Save and reuse

Writes `results/single_stream.json` by default; override with `BENCH_SAVE_AS=<name>.json`. `save_replacing()` drops any prior record for the same `(backend, model, hardware, kind)` before writing, so re-running against the same engine updates its row instead of duplicating it.

Each record also carries the serving parameters read off the engine at probe time (vLLM's cache config, Ollama's `/api/ps`) — see [`00_running_engines.md`](00_running_engines.md#what-was-used).

UI page: `ui/pages/p07_1_inference_bench.py` — merges every file in `results/` into one comparison.

## References

- Code: [`02_benchmark.py`](02_benchmark.py), [`harness.py`](harness.py)
- Concept: [`docs/inference_serving.md`](../../docs/inference_serving.md) — "Generation is two different workloads"
