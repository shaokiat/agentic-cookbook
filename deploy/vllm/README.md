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
VLLM_MODEL=Qwen3-0.6B-4bit

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

**Sizing:** start small. `serve.sh` defaults to `mlx-community/Qwen3-0.6B-4bit` because the
point is to observe scheduling, and a 0.6B model leaves room for 64 concurrent requests on a
16GB laptop. Unified memory is shared with the OS, so a 7–8B model at 4-bit needs ~32GB to
batch meaningfully — going bigger starves the batch and destroys the very behaviour you are
trying to see. Full setup for all three engines:
[`examples/07_inference/00_running_engines.md`](../../examples/07_inference/00_running_engines.md).

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
