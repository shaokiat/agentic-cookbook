# vLLM args, measured

One model, one machine, one arg changed at a time. Everything here was produced by
[`local/serve.sh`](local/serve.sh) and
[`examples/07_inference/03_load_sweep.py`](../../examples/07_inference/03_load_sweep.py) —
no special harness. For what each arg *means*, see the table in [`README.md`](README.md);
this file is what actually happened when they were changed.

- **Model:** `mlx-community/Qwen3.5-4B-4bit` (~2.9GB on disk)
- **Hardware:** M-series Mac, 17.2GB unified memory (see the memory accounting below)
- **Sweep:** concurrency 1 → 32, 128 output tokens per request, 3-prompt rotating suite
- **Raw results:** `examples/07_inference/results/vllm4b_<config>_sweep.json`

Reproduce any row:

```bash
make stop && make serve-vllm VLLM_MAX_NUM_SEQS=4        # or whichever arg
BENCH_SAVE_AS=vllm4b_seqs4_sweep.json \
  .venv/bin/python examples/07_inference/03_load_sweep.py
```

---

## The configs

| Config | `max_num_seqs` | `max_model_len` | `max_num_batched_tokens` | prefix caching |
|:--|--:|--:|--:|:--|
| `baseline` | 32 | 8192 | 2048 | on |
| `seqs4` | **4** | 8192 | 2048 | on |
| `noprefix` | 32 | 8192 | 2048 | **off** |
| `len2048` | 32 | **2048** | 2048 | on |
| `batched512` | 32 | 8192 | **512** | on |
| `batched8192` | 32 | 8192 | **8192** | on |

---

## The two batching budgets

Continuous batching is governed by two independent caps, and confusing them is the usual
reason a tuning session goes nowhere:

- **`--max-num-seqs`** — how many *sequences* may be resident in the running batch. A
  concurrency cap.
- **`--max-num-batched-tokens`** — how many *tokens* the scheduler may put through in one
  forward pass. A work-per-step cap.

Each scheduler step fills that token budget from two sources competing for it: prefill
chunks from newly arrived prompts, and exactly one token per sequence already decoding. So
with 32 sequences streaming, 32 of the budget goes to decode and the rest is what remains
for admitting new work. A prompt longer than the budget is split across several steps —
that is chunked prefill, and on vllm-metal it is on by default.

The default here is **2048**, set by the Metal platform rather than by vLLM's generic
default:

```
INFO [platform.py:666] Metal: chunked prefill enabled (paged attention), max_num_batched_tokens=2048
```

Raising it lets a long prefill finish in fewer steps (better throughput) at the cost of
every decode sharing those steps waiting behind a bigger chunk (worse inter-token latency
for everyone already streaming). Lowering it does the reverse: smoother streaming, slower
prompt ingestion.

Neither budget can rescue the third constraint, which is the one that actually bound this
box.

---

## Where the memory actually went

`gpu_memory_utilization` is **0.92**, but it is not a fraction of the 17.2GB the machine has.
vllm-metal applies it to a Metal *limit* well below the physical total, and the server prints
the whole derivation:

```
Metal memory: 17.2GB total, 8.9GB available
Set Metal wired_limit to 11.8 GB
Paged attention: VLLM_METAL_MEMORY_FRACTION=auto, using --gpu-memory-utilization=0.92
Paged attention memory breakdown: metal_limit=12.71GB, fraction=0.92, usable_metal=11.70GB,
  model_memory=2.37GB, overhead=1.02GB, kv_budget=8.31GB,
  per_block_bytes=36618240, num_blocks=226, max_tokens_cached=119328
KV cache: 3910.1 MB (8 layers, 226 blocks, 528 tokens/block)
GPU KV cache size: 84,154 tokens
```

Read top to bottom, for the `baseline` run:

| Quantity | Value | Where it comes from |
|:--|--:|:--|
| Physical unified memory | 17.20 GB | the machine |
| Free at launch | 8.90 GB | whatever the OS and your apps left |
| `metal_limit` | 12.71 GB | Metal's working-set ceiling, **not** the 17.2GB total |
| × `gpu_memory_utilization` **0.92** | **11.70 GB** | `usable_metal` — the budget vLLM plays inside |
| − model weights | 2.37 GB | Qwen3.5-4B at 4-bit |
| − runtime overhead | 1.02 GB | activations, graphs, scratch |
| = **KV cache budget** | **8.31 GB** | what is left for the cache |
| Actually allocated | **3.91 GB** | 226 blocks × 528 tokens, 8 layers |
| Reported capacity | **84,154 tokens** | ~10.3 sequences at `max_model_len=8192` |

Two things worth noticing. The budget is **8.31GB but only 3.91GB gets allocated** — the
planner sizes blocks at 36.6MB each and the allocator uses 17.3MB, so the cache stops at 226
blocks and leaves over half the budget on the floor. And 0.92 is applied to 12.71GB, not
17.2GB, so the effective share of the machine is closer to **68%** than 92%.

### Overrides must be verified, not assumed

The first attempt at this comparison produced four different-looking result sets from four
**identical** servers. `deploy/engines.py --make` rendered `KEY=VALUE`, and a plain
assignment in an included makefile overrides the environment and is then re-exported to the
recipe — so `VLLM_MAX_NUM_SEQS=4 make serve-vllm` was silently discarded. The numbers looked
plausible and were pure run-to-run variance.

`engines.py` now renders `KEY ?= VALUE`, matching the `:=` the `--sh` path already used. The
lesson generalizes past this bug: **read back the config the server resolved before trusting
a benchmark.** `serve.sh` echoes it, and vLLM logs `non-default args` at startup. The driver
for these runs aborts if the two disagree.

In the verified rerun, `overhead` held at 1.02GB for every config that did not change the
token budget, so the comparisons below are sound. Still, check that the `GPU KV cache size`
line matches across any two runs before attributing a difference to a flag.

---

## The constraint nobody configures: KV cache

`serve.sh` asks for `max_num_seqs: 32`. The server never got close, and it said so at
startup before a single request arrived:

```
GPU KV cache size: 84,154 tokens
Maximum concurrency for 8,192 tokens per request: 10.27x
```

The weights take their share of a 17.2GB pool first; whatever `gpu_memory_utilization`
leaves becomes the KV cache, and the cache must hold `max_model_len` tokens for every
sequence in the batch. At 8192 tokens per sequence that is ~10 sequences, so
`max_num_seqs: 32` was never a setting — it was a wish. **Read that line on every start.
It is the ceiling all the other args negotiate under.**

---

## Results

### Peak aggregate throughput (tok/s)

| config | 1 | 2 | 4 | 8 | 16 | 32 | peak |
|:--|--:|--:|--:|--:|--:|--:|--:|
| `baseline` | 28 | 50 | 76 | 80 | 96 | 101 | **101** @ 32 |
| `seqs4` | 21 | 36 | 50 | 48 | 39 | 36 | **50** @ 4 |
| `noprefix` | 31 | 51 | 63 | 66 | 70 | 11 | **70** @ 16 |
| `len2048` | 21 | 34 | 48 | 54 | 67 | 69 | **69** @ 32 |
| `batched512` | 26 | 41 | 54 | 59 | 67 | 67 | **67** @ 32 |
| `batched8192` | 26 | 26 | 34 | 32 | 36 | 40 | **40** @ 32 |

### p95 end-to-end latency (ms)

| config | 1 | 2 | 4 | 8 | 16 | 32 |
|:--|--:|--:|--:|--:|--:|--:|
| `baseline` | 4,533 | 5,105 | 6,759 | 12,758 | 21,415 | 40,520 |
| `seqs4` | 6,036 | 7,197 | 10,278 | 21,311 | 52,282 | 114,361 |
| `noprefix` | 4,148 | 5,047 | 8,121 | 15,410 | 29,220 | 275,631 |
| `len2048` | 6,118 | 7,502 | 10,560 | 18,857 | 30,589 | 59,362 |
| `batched512` | 5,011 | 6,313 | 9,490 | 17,217 | 30,638 | 61,240 |
| `batched8192` | 4,831 | 9,853 | 15,261 | 31,963 | 56,734 | 90,877 |

### p95 time to first token (ms)

| config | 1 | 2 | 4 | 8 | 16 | 32 |
|:--|--:|--:|--:|--:|--:|--:|
| `baseline` | 169 | 322 | 571 | 1,001 | 1,806 | 3,698 |
| `seqs4` | 204 | 528 | 870 | 11,210 | 38,789 | 101,326 |
| `noprefix` | 210 | 466 | 737 | 1,056 | 1,845 | 32,556 |
| `len2048` | 404 | 639 | 926 | 1,266 | 2,218 | 5,714 |
| `batched512` | 188 | 439 | 769 | 1,261 | 2,268 | 7,850 |
| `batched8192` | 263 | 447 | 1,267 | 1,873 | 36,906 | 62,022 |

### What the server actually allocated

| config | KV cache (tokens) | max concurrency | errors |
|:--|--:|--:|--:|
| `baseline` | 84,154 | 10.3x | 0 |
| `seqs4` | 84,154 | 10.3x | 0 |
| `noprefix` | 203,075 | 24.8x | 0 |
| `len2048` | 46,284 | 22.6x | 0 |
| `batched512` | 87,505 | 10.7x | 0 |
| `batched8192` | 16,384 | 2.0x | 0 |


### Memory, per config

The same `gpu_memory_utilization=0.92` and the same 2.37GB of weights every time. What moved
was the runtime overhead — and only for the arg that actually drives it:

| Config | overhead | kv_budget | blocks | KV cache tokens | max concurrency |
|:--|--:|--:|--:|--:|--:|
| `baseline` | 1.02 GB | 8.31 GB | 226 | 84,154 | 10.3x |
| `seqs4` | 1.02 GB | 8.31 GB | 226 | 84,154 | 10.3x |
| `len2048` | 1.02 GB | 8.31 GB | 226 | 46,284 | 22.6x |
| `noprefix` | — | — | — | 203,075 | 24.8x |
| `batched512` | **0.70 GB** | 8.63 GB | 235 | 87,505 | 10.7x |
| `batched8192` | **7.71 GB** | **1.62 GB** | **44** | **16,384** | **2.0x** |

`noprefix` takes a different allocation path and does not print the breakdown line.

---

## What the numbers say

**`max_num_batched_tokens` is not free — it is charged to the KV cache.** This is the biggest
effect measured, and it is the opposite of what "bigger batch = faster" suggests. Raising the
token budget 2048 → 8192 grew runtime overhead from 1.02GB to **7.71GB**, which left only
1.62GB for the KV cache: 44 blocks instead of 226, a cache of 16,384 tokens, and a real
concurrency ceiling of **2.0x**. Throughput fell to 40 tok/s against the baseline's 101, and
p95 TTFT at concurrency 16 went from 1.8s to 37s. The scratch buffers for a step scale with
the tokens that step may process, and they come out of the same pool the cache lives in.

Lowering it to 512 is nearly free memory-wise (overhead 0.70GB, a *slightly* bigger cache) but
still costs throughput — 67 vs 101 — because prefill arrives in smaller chunks. **2048 was
already the right value on this box.** The default was not the thing to tune.

**`max_num_seqs` does exactly what it claims, and the curve shows it.** Capped at 4, throughput
peaks at concurrency 4 (50 tok/s) and then *declines* — 48, 39, 36 — as surplus requests queue
instead of batching. p95 TTFT at 32 is 101 seconds, because requests 5 through 32 are waiting,
not running. The KV cache was identical (84,154 tokens) in both runs, so this is the scheduler
and nothing else. Baseline reaches 101 tok/s and is still climbing at 32, meaning even the
"unreachable" `max_num_seqs: 32` was not the limit at these levels.

**Prefix caching earned ~44%** — 101 vs 70 tok/s peak — despite `noprefix` being handed a 2.4x
*larger* cache (203,075 tokens). Caveat: the sweep rotates only three prompts, so above
concurrency 3 the requests are exact duplicates and the cache hit rate is a best case. Treat
this as an upper bound, not a typical workload.

**Lowering `max_model_len` bought headroom the workload could not use.** Dropping 8192 → 2048
did more than double the concurrency ceiling (10.3x → 22.6x), exactly as intended — and
throughput went *down*, 69 vs 101. With short prompts and 128-token outputs, the KV cache was
never the binding constraint at these concurrencies; compute was. Lower `max_model_len` when
the server refuses to start or when requests genuinely queue on cache blocks, not as a
throughput knob.

### The short version

| Change | Peak tok/s | vs baseline |
|:--|--:|--:|
| *(baseline: 32 seqs / 8192 len / 2048 batched / prefix on)* | **101** | — |
| `max_num_seqs` 32 → 4 | 50 | **−50%** |
| `max_num_batched_tokens` 2048 → 8192 | 40 | **−60%** |
| `max_num_batched_tokens` 2048 → 512 | 67 | −34% |
| prefix caching off | 70 | −31% |
| `max_model_len` 8192 → 2048 | 69 | −32% |

Every deviation from the default lost throughput. On this machine the shipped config is
already at the local optimum, and the useful output of a tuning session like this is knowing
*which* wall you are against — here, compute at low concurrency and the KV cache above it.

### One suspect row

`noprefix` at concurrency 32 reported 10.7 tok/s and a 275-second wall clock, against 70 tok/s
at concurrency 16. All 32 requests were running with none queued and the cache only 27% full,
and it returned 2,952 output tokens where 4,096 were expected — so it is not a cache limit.
Memory pressure from the 2.4x larger cache and thermal throttling are both plausible; the logs
do not settle it. Re-run that row before quoting it.
