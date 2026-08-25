# Running the Inference Engines

Before you can compare engines you have to run them. This page is the setup half of the
section — every command here was executed on an Apple Silicon Mac with 16GB of unified memory
to produce the numbers in `results/`.

**Everything uses a 0.6B model on purpose.** This is a proof of concept: the goal is to make
scheduler behaviour visible, not to serve a useful assistant. A 0.6B model loads in seconds,
leaves room for 64 concurrent requests on a laptop, and shows the throughput/latency curve just
as clearly as a 70B model would. Scale up only once the shape makes sense to you.

| Engine | Role in the comparison | Start it |
| :--- | :--- | :--- |
| **vLLM** (`vllm-metal`) | The subject — PagedAttention + continuous batching | `make serve-vllm` |
| **mlx-lm** | The control — same weights, same backend, simpler scheduler | `make serve-mlx` |
| **Ollama** | The familiar baseline — llama.cpp + GGUF | `make serve-ollama` |

All three expose an OpenAI-compatible `/v1/chat/completions`, which is why one harness can
drive them all — and all three serve on **the same port**, because only one of them runs at
a time anyway:

```bash
# .env — the single local endpoint, whichever engine currently owns it
LOCAL_API_BASE=http://localhost:8000/v1
LOCAL_API_KEY=cookbook-local
```

Which model each engine serves, and how it is tuned, lives in
[`deploy/engines.yaml`](../../deploy/engines.yaml) — one file for all three, read by the
Makefile and by `serve.sh`. `make config` prints what is currently set, and any value can
be overridden for a single run: `make serve-vllm VLLM_MODEL=mlx-community/Qwen3-4B-4bit`.

`discover()` probes that URL and works out which engine answered (`/api/tags` means Ollama,
`vllm:` Prometheus metrics mean vLLM, otherwise mlx-lm) and which model it has loaded. So
swapping engines is `make stop` followed by the next `make serve-*` — there is no config to
edit in between, and a stale env var cannot mislabel a saved result.

---

## 1. vLLM (Apple Silicon)

There is no CUDA on a Mac, and vLLM's CPU backend is ~20–30× slower than Metal — useless for
benchmarking. The `vllm-metal` plugin runs vLLM's scheduler over an MLX compute backend, so
PagedAttention and continuous batching are genuinely present.

```bash
# Installs vLLM + the Metal plugin into its own venv (~/.venv-vllm-metal).
# It pins its own vLLM/torch build — do NOT install it into the repo .venv.
curl -fsSL https://raw.githubusercontent.com/vllm-project/vllm-metal/main/install.sh | bash
```

Requires macOS 15 (Sequoia)+ and a **native arm64 Python 3.12**. A Rosetta/x86_64 Python fails.
If you have `uv`, the installer uses it and no system Python 3.12 is needed.

```bash
make serve-vllm                          # VLLM_MODEL=… to override the model
```

First start downloads weights and compiles Metal kernels — allow a couple of minutes. You know
it worked when the log shows paged attention coming up:

```
Paged attention enabled: 28 layers patched, 5419 blocks allocated (block_size=16)
GPU KV cache size: 86,704 tokens
Maximum concurrency for 8,192 tokens per request: 10.58x
```

That last line is the KV-cache ceiling from `docs/inference_serving.md`, printed by the server.

> On Linux with an NVIDIA GPU, skip all of the above: `pip install vllm` then
> `vllm serve Qwen/Qwen3-0.6B --port 8000 --api-key cookbook-local` — same port, so the
> harness needs no changes.

---

## 2. mlx-lm — the control

This is the most informative comparison in the section, because it isolates exactly one
variable. `mlx_lm.server` runs the **same MLX weights** at the **same quantization** on the
**same Metal backend** as `vllm-metal`. Only the scheduler differs.

```bash
make install-mlx     # once: a venv at ~/.venv-mlx-lm with mlx-lm in it
make serve-mlx
```

---

## 3. Ollama — the familiar baseline

```bash
make pull-ollama     # once
make serve-ollama    # OLLAMA_HOST=127.0.0.1:8000 OLLAMA_NUM_PARALLEL=32 ollama serve
```

`make serve-ollama` moves Ollama off its default 11434 onto the shared port with
`OLLAMA_HOST`. If the Ollama desktop app is already running, quit it first — it holds the
default port and the model store. `make pull-ollama` talks to that server, so start it first.

Ollama is the one engine whose `/v1/models` is a *menu* rather than an answer: it lists
everything you have ever pulled and loads on demand. The harness asks `/api/ps` which model
is actually resident, which covers the normal case; if several are pulled and none is loaded
yet, name one:

```bash
make probe LOCAL_MODEL=qwen3:0.6b        # or LOCAL_MODEL=… in .env
```

**`OLLAMA_NUM_PARALLEL` is the whole ballgame** and it must be set before the server starts.
At its conservative default, Ollama queues past a handful of concurrent requests and the
throughput curve flattens at exactly that number — you would be measuring a config value and
calling it an engine limitation. Set it at or above your highest sweep level so Ollama gets a
fair run.

Ollama serves GGUF (`Q4_K_M` here), not MLX 4-bit. That is a **different quantization**, so
Ollama-vs-vLLM mixes scheduler and quantization effects. It is a useful real-world data point;
mlx-lm is the controlled one.

---

## Run one engine at a time

**This is not optional on a laptop.** vLLM reserves ~10GB for its KV cache by default; mlx-lm
and Ollama each hold their own copy of the weights plus their own caches. Leaving two servers
up means your sweep measures memory pressure and swap, not scheduling — and on a 16GB machine
it will bring the desktop to a crawl.

The workflow that produced `results/`: serve in one terminal, benchmark from another.
`make bench` writes `<engine>_single.json` and `<engine>_sweep.json` into `results/`.

| terminal 1 | terminal 2 |
| :--- | :--- |
| `make serve-vllm` | `make bench ENGINE=vllm` |
| `make stop` | |
| `make serve-mlx` | `make bench ENGINE=mlx` |
| `make stop` | |
| `make serve-ollama` | `make bench ENGINE=ollama` |
| `make stop` | |

Nothing changes in `.env` between those steps: the endpoint is the same and the harness
identifies the engine each time. `ENGINE=` only names the output files — the `backend` field
inside each record comes from what was actually detected, so a mismatched filename is
cosmetic rather than a wrong number.

The Streamlit page merges every file in `results/` into one comparison, so collecting them
separately costs nothing.

### What was used

Every saved record carries the serving parameters read off the engine at probe time —
vLLM's `cache_config_info` metric (block size, KV cache tokens, prefix caching,
`gpu_memory_utilization`), Ollama's `/api/ps` (context length, resident size,
quantization). The Streamlit page shows them next to the charts, because a throughput
curve is not interpretable without them.

Two knobs are not reported by any endpoint — vLLM's `max_num_seqs` and Ollama's
`OLLAMA_NUM_PARALLEL` — and both cap concurrency, so a curve that flattens at exactly
that number is measuring the config. `make bench` passes them from `engines.yaml` into
the record, starred (`max_num_seqs*`) to mark them as declared rather than confirmed.

### Budget

| Knob | Effect |
| :--- | :--- |
| `BENCH_LEVELS=1,2,4,8` | Skips the expensive top levels. Default is `1,2,4,8,16,32`. |
| `MAX_TOKENS` in the script | 128 by default; halving it roughly halves total runtime. |
| `repeats` in `02_benchmark.py` | 3 by default. |

The top concurrency level dominates the runtime, and against a serializing engine it mostly
measures queueing. If the machine is busy, cut it — `BENCH_LEVELS=1,2,4,8` still shows the
shape of the curve.

## Verifying before you benchmark

```bash
make probe
```

Prints which engine is serving the local endpoint, what model it has loaded, and one timed
completion. If nothing is up, this says so before a sweep wastes minutes on it.
