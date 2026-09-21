# deploy/vllm — Serving Your Own Model

Operational glue, not a lesson. This directory runs a vLLM server that the rest of the
cookbook (and any other project you own) can call over an OpenAI-compatible API.

For the *concepts* behind what the server is doing — KV cache, PagedAttention, continuous
batching, why throughput and latency trade against each other — read
[`docs/inference_serving.md`](../../docs/inference_serving.md).
For *measuring* it, see [`examples/07_inference/`](../../examples/07_inference/).

---

## Why this needs no code changes

`core/model.py` calls `litellm.completion()`. LiteLLM resolves a `hosted_vllm/*` model string
against the `HOSTED_VLLM_API_BASE` environment variable, and `ollama_chat/*` against
`OLLAMA_API_BASE`. So pointing the entire cookbook at a self-hosted model is configuration,
never code:

```bash
# .env
HOSTED_VLLM_API_BASE=http://localhost:8000/v1
HOSTED_VLLM_API_KEY=cookbook-local
VLLM_MODEL=Qwen3.5-4B-4bit

# The benchmarks in examples/07_inference use one endpoint instead, and detect the engine:
LOCAL_API_BASE=http://localhost:8000/v1
LOCAL_API_KEY=cookbook-local
```

The Streamlit sidebar model picker then offers `hosted_vllm/<VLLM_MODEL>` alongside the API
models, and every example — ReAct, Reflexion, orchestrator/worker, mini-researcher — runs
against it unchanged. That is the provider-agnosticism claim in `PROJECT_CONTEXT.md` being
cashed in rather than asserted.

**Expect degraded tool calling.** Small open models are materially worse at multi-turn
function calling than frontier models. The primitives and single-tool examples work well; the
multi-agent and Reflexion examples will loop or retry more. That is a finding worth observing,
not a bug in the wiring.

---

## Local (Apple Silicon)

```bash
make serve-vllm      # wraps ./deploy/vllm/local/serve.sh on port 8000
```

Apple Silicon has no CUDA. Three options, only one is worth using:

| Path | Works? | Usable? |
| :--- | :--- | :--- |
| vLLM CPU backend | Source build, no prebuilt arm64 wheels | **No** — ~20–30× slower than llama.cpp's Metal backend |
| [`vllm-metal`](https://github.com/vllm-project/vllm-metal) plugin | macOS 15+, native arm64 Python 3.12 | **Yes** — MLX backend, paged attention, continuous batching |
| vLLM CUDA | No | — |

`vllm-metal` installs into its own venv (`~/.venv-vllm-metal`) because it pins its own
vLLM/torch build — do not install it into the repo `.venv`.

It serves MLX-format models from `mlx-community` on Hugging Face, not the fp16 safetensors
you would use on an NVIDIA box. Model coverage is still growing; check the
[compatibility matrix](https://docs.vllm.ai/projects/vllm-metal/) before picking one.

**Sizing:** `serve.sh` defaults to `mlx-community/Qwen3.5-4B-4bit` — ~2.3GB of weights,
which on a 16GB laptop leaves enough unified memory for a real KV cache and a batch deep
enough to see the scheduler work. Unified memory is shared with the OS, so a 7–8B model at
4-bit needs ~32GB to batch meaningfully; going bigger starves the batch and destroys the
very behaviour you are trying to see. Full setup for all three engines:
[`examples/07_inference/00_running_engines.md`](../../examples/07_inference/00_running_engines.md).

---

## The args, and what each one actually does

Every value below lives in [`deploy/engines.yaml`](../engines.yaml) and is overridable for a
single run, because `engines.py --sh` renders them as `: "${KEY:=value}"` — an existing
environment variable always wins:

```bash
make serve-vllm VLLM_MAX_NUM_SEQS=8          # one run, file untouched
```

The three that matter fight over the same pool of unified memory. vLLM loads the weights
first, then gives whatever is left of `gpu_memory_utilization` to the KV cache, and the cache
has to hold `max_model_len x max_num_seqs` tokens for a full batch. Push any one up and the
other two have less to work with.

| Arg (`VLLM_*` env) | Default | What it controls | What you see when you change it |
| :--- | :--- | :--- | :--- |
| `MODEL` | `mlx-community/Qwen3.5-4B-4bit` | Weights and quantization | `-8bit`/`-bf16` roughly double/quadruple the weight footprint, stealing it from the KV cache. Quality up, batch depth down. |
| `MAX_MODEL_LEN` | `8192` | Context budget per sequence | The KV cache multiplier. Halving it roughly doubles how many sequences fit. Lower this first if vLLM refuses to start for lack of cache blocks. |
| `MAX_NUM_SEQS` | `32` | Sequences the scheduler runs in one batch | The batching knob. Set it *below* your sweep's top concurrency and the throughput curve flattens at exactly this number — you measured the config, not the engine. |
| `GPU_MEMORY_UTILIZATION` | `0.92` | Share of memory for weights + cache | Higher = bigger cache = deeper batches, until the OS starts swapping and the sweep reads that as a hardware knee. On a Mac the OS needs its share; above ~0.95 gets unstable. |
| `ENABLE_PREFIX_CACHING` | `1` | Reuse of a shared prompt prefix | Set `0` and re-run the sweep. The gap is what prefix caching is worth for *your* prompts — large with a long shared system prompt, near zero with unique prompts. |
| `MAX_NUM_BATCHED_TOKENS` | `2048` | Tokens per scheduler step | The *other* batching budget: `MAX_NUM_SEQS` caps sequences, this caps work per forward pass. Raise it and long prefills finish in fewer steps; lower it and streaming stays smoother. |
| `EXTRA_ARGS` | `""` | Anything else, word-split verbatim | The escape hatch: `VLLM_EXTRA_ARGS="--swap-space 2"`. |

### A sane way to experiment

Change **one** arg, re-run the sweep, compare. Two at a time and you cannot attribute the
difference:

```bash
make serve-vllm                                   # terminal 1
make bench ENGINE=vllm                            # terminal 2 -> results/

make stop && make serve-vllm VLLM_MAX_NUM_SEQS=4  # the batching cap, made visible
make bench ENGINE=vllm
```

Startup logs are the ground truth for whether an arg took effect — vLLM prints the number of
KV cache blocks and tokens it actually allocated, which is the real budget your `max_num_seqs`
is spending. If that number collapses after a change, that is your answer.

**Measured results for each of these args on Qwen3.5-4B are in
[`arg_sweeps.md`](arg_sweeps.md)** — one arg changed at a time, with the sweep numbers.

> The older numbers in [`examples/07_inference/`](../../examples/07_inference/) were taken
> with a 0.6B model. The shape holds, the absolute figures do not.

### mlx-lm, the control

```bash
make install-mlx     # once
make serve-mlx       # mlx_lm.server on the same port 8000 — run it INSTEAD of vLLM
```

This is the most useful comparison in the whole section, because it is the only one that
isolates a single variable. `mlx_lm.server` runs the **same MLX weights** at the **same
quantization** on the **same Metal backend** as `vllm-metal` — it just answers one request at a
time. Any gap under concurrency is the scheduler, and nothing else.

### Ollama, for comparison

```bash
make pull-ollama     # once
make serve-ollama    # OLLAMA_HOST=127.0.0.1:8000 OLLAMA_NUM_PARALLEL=32 ollama serve
```

`OLLAMA_NUM_PARALLEL` must be set **before** the server starts, and it is the whole ballgame:
at its conservative default Ollama queues past a handful of concurrent requests, so the
throughput curve flattens at exactly that number. Leaving it alone and concluding "vLLM
batches better" measures the config, not the engine.

---

## Cloud (GCP)

See [`gcp/README.md`](gcp/README.md). Short version: start with Cloud Run + GPU because it
scales to zero; graduate to GKE when you need multi-replica routing or node-level control.

---

## Security

vLLM's `/v1/chat/completions` is unauthenticated unless you pass `--api-key`. An open endpoint
on a GPU instance gets found and mined. Always set a key, and never expose the port publicly
without a proxy in front of it.
