# Inference Backends: Walkthrough

## What it does

Probes the one local endpoint (`LOCAL_API_BASE`, default `http://localhost:8000/v1`) and identifies the engine behind it — `/api/tags` answers only on Ollama, `vllm:` Prometheus metrics only on vLLM, otherwise mlx-lm — reads the loaded model from `/models`, then streams one timed completion and reports TTFT, ITL, and decode rate. Only one engine runs at a time, so there is one endpoint rather than one per engine.

## Key insight

A "backend" is `(model string, base URL, api key)` — not a class hierarchy. Every self-hosted server in common use speaks the OpenAI chat-completions format, and litellm already resolves `hosted_vllm/*` and `ollama_chat/*` against those env vars. So `core/model.py` needs **zero changes** to run against a model you host yourself. This example exists to make that concrete, not to add an abstraction.

The second insight is a warning: at concurrency 1 the backends will look roughly the same. Both are memory-bandwidth-bound on the same hardware, and continuous batching does nothing when there is nothing to batch. Concluding "there is no difference" from this example is the single most common benchmarking mistake — see [`03_load_sweep.md`](03_load_sweep.md).

## Run it

```bash
./deploy/vllm/local/serve.sh          # in another shell
.venv/bin/python examples/07_inference/01_backends.py
```

UI page: `ui/pages/p07_1_inference_bench.py`

## References

- Code: [`01_backends.py`](01_backends.py), [`harness.py`](harness.py)
- Concept: [`docs/inference_serving.md`](../../docs/inference_serving.md)
- Serving: [`deploy/vllm/README.md`](../../deploy/vllm/README.md)
- Provider layer above this one: [`docs/llm_provider_strategies.md`](../../docs/llm_provider_strategies.md)
