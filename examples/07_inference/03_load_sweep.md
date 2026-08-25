# Concurrency Load Sweep: Walkthrough

## What it does

Fires 1, 2, 4, 8, 16, then 32 simultaneous requests at each backend, recording aggregate tokens/sec, per-request tokens/sec, TTFT p50, and e2e p95 at every level. Where the backend is vLLM, it also scrapes `/metrics` for `num_requests_running`, `num_requests_waiting`, and KV cache utilisation. Writes `results/load_sweep.json`.

## Key insight

This is the point of the section. Everything before it is setup.

Static batching runs a batch to completion, so the whole batch moves at the speed of its slowest member and finished sequences burn idle slots. **Continuous batching** schedules per decode *iteration*: finished sequences leave, queued ones join, the GPU stays saturated. PagedAttention is what makes that affordable — KV cache in fixed blocks with a per-request block table, so memory is allocated on demand instead of reserved at maximum length.

The result is a curve, not a number:

```
aggregate tok/s
     │                    ╭──────────  ← KV cache saturated, queueing begins
     │              ╭─────╯
     │        ╭─────╯                  ← the knee
     │   ╭────╯
     │╭──╯
     └──────────────────────────────── concurrency
```

Per-request latency worsens monotonically the whole way; aggregate throughput improves until the KV cache fills, then flattens. The knee is the only number that matters for capacity planning, and **"tokens per second" quoted without a concurrency level is not a measurement.**

Watching `num_requests_waiting` go from 0 to nonzero at exactly the concurrency where the throughput curve flattens is the moment the theory stops being theory.

## Run it

```bash
  .venv/bin/python examples/07_inference/03_load_sweep.py
```

Reduce `LEVELS` if you are on a small machine — concurrency 32 with an 8k context can exhaust a shared unified-memory pool, at which point you are measuring swapping rather than scheduling. `BENCH_LEVELS=1,2,4,8` overrides it without editing the file; the top level is the expensive one, since a serializing engine mostly turns it into queueing time.

## Save and reuse

Writes `results/load_sweep.json` by default; override with `BENCH_SAVE_AS=<name>.json`. `save_replacing()` drops any prior record for the same `(backend, model, hardware, concurrency)` before writing, so re-sweeping an engine updates its rows instead of duplicating them.

Where the backend is vLLM, each record's `note` also carries the peak scheduler state sampled mid-sweep (`num_requests_running`, `num_requests_waiting`, `kv_cache_usage_perc`) — that's what lets you watch the knee happen rather than just read a number after the fact.

UI page: `ui/pages/p07_1_inference_bench.py` — merges every file in `results/` into one comparison, with a "Serving parameters" panel next to the chart (see [`00_running_engines.md`](00_running_engines.md#what-was-used)).

## References

- Code: [`03_load_sweep.py`](03_load_sweep.py), [`harness.py`](harness.py)
- Concept: [`docs/inference_serving.md`](../../docs/inference_serving.md) — "Throughput and latency are the same dial"
- vLLM Prometheus metrics: scraped in `vllm_metrics()`
