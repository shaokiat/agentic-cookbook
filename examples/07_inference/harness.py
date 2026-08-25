"""
Shared measurement primitives for the 07_inference examples.

Not a numbered lesson — this is the small amount of machinery that 01/02/03 and the
Streamlit page all need: which backends exist, how to time one streaming completion,
and the on-disk result schema.

Docs: docs/inference_serving.md
"""
import json
import os
import re
import statistics
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

import httpx
import litellm

RESULTS_DIR = Path(__file__).resolve().parent / "results"

# A fixed prompt suite. Short prompts isolate decode; the long one exercises prefill,
# which is where TTFT separates from ITL. See docs/inference_serving.md.
PROMPT_SUITE = [
    "In one sentence, what is a KV cache?",
    "List three tradeoffs of quantizing an LLM to 4 bits.",
    "Explain continuous batching to a backend engineer who knows nothing about GPUs.",
]

LONG_PREFILL_PROMPT = (
    "Here is a transcript of an agent run:\n\n"
    + ("Step 1: called read_file('a.py'). Observed 412 lines of Python.\n"
       "Step 2: called grep('def '). Observed 18 matches.\n") * 60
    + "\nSummarize what the agent did in two sentences."
)


@dataclass
class Backend:
    """One OpenAI-compatible inference endpoint."""
    name: str
    model: str          # litellm model string, e.g. hosted_vllm/Qwen3-8B-4bit
    api_base: str | None
    api_key: str | None
    available: bool = False
    detail: str = ""
    dtype: str = ""     # detected from the server; BENCH_DTYPE overrides
    params: dict = field(default_factory=dict)   # serving config the server reports


DEFAULT_API_BASE = "http://localhost:8000/v1"


def discover() -> list[Backend]:
    """Identify the engine serving the one local endpoint.

    Only one engine can hold the accelerator at a time (see 00_running_engines.md), so
    they all serve on the same port and the harness asks the server what it is rather
    than being told by config. One less thing to get out of sync with reality: a stale
    env var can't mislabel a saved result any more.
    """
    # Read at call time, not import time: the example scripts call load_dotenv() after
    # importing this module.
    base = os.getenv("LOCAL_API_BASE", DEFAULT_API_BASE).rstrip("/")
    return [_identify(base, os.getenv("LOCAL_API_KEY", "cookbook-local"))]


def _identify(base: str, api_key: str | None) -> Backend:
    """Probe the endpoint for engine, model, dtype and serving parameters.

    The engine is inferred from what else answers: only Ollama serves /api/tags, and only
    vLLM exports vllm: Prometheus metrics.

    Picking the model is not symmetric. vLLM and mlx-lm serve exactly one, so /models
    answers it. Ollama lists its whole store and loads on demand, so /models there is a
    menu, not an answer — /api/ps says what is actually resident, and LOCAL_MODEL settles
    it when neither does.
    """
    root = base.removesuffix("/v1")
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    try:
        r = httpx.get(f"{base}/models", headers=headers, timeout=3.0)
        r.raise_for_status()
        entries = r.json().get("data") or []
    except Exception as exc:
        return Backend("local", "", base, api_key, detail=f"{type(exc).__name__}: {exc}")

    ids = [e.get("id") for e in entries if e.get("id")]
    override = os.getenv("LOCAL_MODEL")

    if _body(f"{root}/api/tags") is not None:
        return _ollama_backend(root, api_key, ids, override)

    model_id = override or (ids[0] if ids else "local-model")
    entry = next((e for e in entries if e.get("id") == model_id), entries[0] if entries else {})
    params = {"max_model_len": entry["max_model_len"]} if "max_model_len" in entry else {}

    metrics = _body(f"{root}/metrics") or ""
    if "vllm:" in metrics:
        params.update(_vllm_params(metrics))
        # The scheduler's batch cap is not in any metric. Starred: declared in
        # engines.yaml, not confirmed by the server. `make bench` passes it through.
        if seqs := os.getenv("VLLM_MAX_NUM_SEQS"):
            params["max_num_seqs*"] = seqs
        engine, prefix = "vllm", "hosted_vllm"
    elif params:
        # vLLM without /metrics still reports the context length that mlx-lm's /models omits.
        engine, prefix = "vllm", "hosted_vllm"
    else:
        engine, prefix = "mlx-lm", "openai"

    return Backend(engine, f"{prefix}/{model_id}", base, api_key, available=True,
                   detail=f"{model_id} ({engine}, {base})",
                   dtype=_dtype_from_name(model_id), params=params)


def _ollama_backend(root: str, api_key: str | None, ids: list[str], override: str | None) -> Backend:
    resident = _json(f"{root}/api/ps").get("models") or []
    model_id = override or (resident[0]["name"] if resident else "") or (ids[0] if len(ids) == 1 else "")
    if not model_id:
        return Backend("local", "", root, api_key, detail=(
            f"Ollama has {len(ids)} models and none loaded — set LOCAL_MODEL to one of: "
            + ", ".join(ids)))

    loaded = next((m for m in resident if m.get("name") == model_id), {})
    details = loaded.get("details") or _ollama_details(root, model_id)
    quant, fmt = details.get("quantization_level"), (details.get("format") or "gguf").upper()

    params = {}
    if version := _json(f"{root}/api/version").get("version"):
        params["ollama"] = version
    # context_length is per slot, and only known once the model is resident.
    for key in ("context_length", "size_vram"):
        if key in loaded:
            params[key] = loaded[key]
    if size := details.get("parameter_size"):
        params["parameters"] = size
    # The knob that decides the whole throughput curve, and no endpoint reports it — it
    # lives in the server's environment. Starred because it is what we were told was set,
    # not what the server confirmed. `make bench` passes it through from engines.conf.
    if parallel := os.getenv("OLLAMA_NUM_PARALLEL"):
        params["num_parallel*"] = parallel

    return Backend("ollama", f"ollama_chat/{model_id}", root, api_key, available=True,
                   detail=f"{model_id} (Ollama, {root})",
                   dtype=f"{quant} ({fmt})" if quant else "", params=params)


def _ollama_details(root: str, model_id: str) -> dict:
    for m in _json(f"{root}/api/tags").get("models") or []:
        if m.get("name") in (model_id, f"{model_id}:latest"):
            return m.get("details") or {}
    return {}


# vllm:cache_config_info carries the scheduler/cache knobs as Prometheus labels — the
# settings that decide the shape of the throughput curve. Only these few are worth
# recording; the metric has thirty labels, most of them internal defaults.
_VLLM_PARAMS = ("block_size", "gpu_memory_utilization", "enable_prefix_caching",
                "kv_cache_size_tokens", "num_gpu_blocks", "kv_cache_max_concurrency",
                "cache_dtype")


def _vllm_params(metrics: str) -> dict:
    line = next((l for l in metrics.splitlines() if l.startswith("vllm:cache_config_info")), "")
    labels = dict(re.findall(r'(\w+)="([^"]*)"', line))
    return {k: labels[k] for k in _VLLM_PARAMS if labels.get(k) not in (None, "None")}


def _json(url: str) -> dict:
    try:
        return json.loads(_body(url) or "{}")
    except json.JSONDecodeError:
        return {}


def _body(url: str) -> str | None:
    try:
        r = httpx.get(url, timeout=2.0)
        return r.text if r.status_code == 200 else None
    except Exception:
        return None


# The OpenAI /models schema has no dtype field, so for vLLM and mlx-lm the model name is
# the only thing carrying it. Bit width is all a name can honestly support — "4bit" says
# nothing about whether those are MLX or bitsandbytes weights — so set BENCH_DTYPE when you
# want the record to be more specific than this. Unrecognised names stay blank.
_NAME_DTYPES = {
    "4bit": "4bit", "8bit": "8bit", "awq": "AWQ", "gptq": "GPTQ",
    "fp8": "FP8", "bf16": "bf16", "fp16": "fp16",
}


def _dtype_from_name(model_id: str) -> str:
    tokens = model_id.lower().replace("/", "-").replace("_", "-").split("-")
    return next((v for t in tokens for k, v in _NAME_DTYPES.items() if t == k), "")


@dataclass
class CallResult:
    """Timings for one streaming completion."""
    ok: bool
    ttft_ms: float = 0.0
    e2e_ms: float = 0.0
    output_tokens: int = 0
    itl_ms: float = 0.0          # mean inter-token latency during decode
    output_tps: float = 0.0      # decode-only tokens/sec for this request
    text: str = ""
    reasoning: str = ""
    error: str = ""


def timed_completion(b: Backend, prompt: str, max_tokens: int = 128) -> CallResult:
    """Stream one completion, measuring TTFT and decode rate separately.

    Reasoning tokens count toward throughput and toward TTFT — they are decoded the
    same way — but are kept out of `text` so the visible answer stays clean.

    Token count comes from the provider's usage block when it sends one; otherwise
    we fall back to counting chunks, which is close but not exact.
    """
    kwargs: dict[str, Any] = {
        "model": b.model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": True,
        "max_tokens": max_tokens,
        "temperature": 0,
        "stream_options": {"include_usage": True},
    }
    if b.api_base:
        kwargs["api_base"] = b.api_base
    if b.api_key:
        kwargs["api_key"] = b.api_key

    start = time.perf_counter()
    first_token_at = None
    chunks = 0
    reported_tokens = None
    parts = []
    reasoning_parts = []

    try:
        for chunk in litellm.completion(**kwargs):
            usage = getattr(chunk, "usage", None)
            if usage and getattr(usage, "completion_tokens", None):
                reported_tokens = usage.completion_tokens
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            content = getattr(delta, "content", None)
            reasoning = getattr(delta, "reasoning_content", None)
            if content or reasoning:
                if first_token_at is None:
                    first_token_at = time.perf_counter()
                chunks += 1
                (parts if content else reasoning_parts).append(content or reasoning)
        end = time.perf_counter()
    except Exception as exc:
        return CallResult(ok=False, error=f"{type(exc).__name__}: {exc}")

    if first_token_at is None:
        return CallResult(ok=False, error="stream produced no content")

    tokens = reported_tokens or chunks
    decode_s = end - first_token_at
    return CallResult(
        ok=True,
        ttft_ms=(first_token_at - start) * 1000,
        e2e_ms=(end - start) * 1000,
        output_tokens=tokens,
        itl_ms=(decode_s / max(tokens - 1, 1)) * 1000,
        output_tps=(tokens - 1) / decode_s if decode_s > 0 else 0.0,
        text="".join(parts),
        reasoning="".join(reasoning_parts),
    )


def run_concurrent(b: Backend, prompts: list[str], concurrency: int,
                   max_tokens: int = 128) -> tuple[list[CallResult], float]:
    """Fire `concurrency` requests at once; return results and wall-clock seconds.

    Wall clock is what matters here — aggregate throughput is total tokens produced
    divided by the time the whole batch took, not the sum of per-request rates.
    """
    picks = [prompts[i % len(prompts)] for i in range(concurrency)]
    start = time.perf_counter()
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        results = list(pool.map(lambda p: timed_completion(b, p, max_tokens), picks))
    return results, time.perf_counter() - start


def pct(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = min(int(round((p / 100) * (len(ordered) - 1))), len(ordered) - 1)
    return ordered[idx]


@dataclass
class Record:
    """One measurement at one concurrency level. This is the on-disk schema.

    The dtype/max_model_len/hardware fields are not decoration — a comparison that
    omits them is uninterpretable. See docs/inference_serving.md.
    """
    backend: str
    model: str
    hardware: str
    dtype: str
    max_model_len: int
    concurrency: int
    kind: str          # "sweep" (a concurrency curve) or "single" (one stream)
    requests: int
    errors: int
    ttft_ms: dict[str, float] = field(default_factory=dict)
    itl_ms: dict[str, float] = field(default_factory=dict)
    e2e_ms: dict[str, float] = field(default_factory=dict)
    output_tps_per_req: float = 0.0
    aggregate_output_tps: float = 0.0
    total_output_tokens: int = 0
    wall_s: float = 0.0
    synthetic: bool = False
    note: str = ""
    # Serving parameters as reported by the engine at probe time. A key ending in * was
    # declared (engines.conf) rather than confirmed by the server.
    server: dict[str, Any] = field(default_factory=dict)


def summarize(b: Backend, results: list[CallResult], wall_s: float, concurrency: int,
              hardware: str, dtype: str, max_model_len: int, kind: str = "sweep") -> Record:
    ok = [r for r in results if r.ok]
    dtype = dtype or b.dtype or "unspecified"
    total_tokens = sum(r.output_tokens for r in ok)
    return Record(
        backend=b.name,
        model=b.model,
        hardware=hardware,
        dtype=dtype,
        max_model_len=max_model_len,
        concurrency=concurrency,
        kind=kind,
        requests=len(results),
        errors=len(results) - len(ok),
        ttft_ms={"p50": pct([r.ttft_ms for r in ok], 50), "p95": pct([r.ttft_ms for r in ok], 95)},
        itl_ms={"p50": pct([r.itl_ms for r in ok], 50), "p95": pct([r.itl_ms for r in ok], 95)},
        e2e_ms={"p50": pct([r.e2e_ms for r in ok], 50), "p95": pct([r.e2e_ms for r in ok], 95)},
        output_tps_per_req=statistics.mean([r.output_tps for r in ok]) if ok else 0.0,
        aggregate_output_tps=total_tokens / wall_s if wall_s > 0 else 0.0,
        total_output_tokens=total_tokens,
        wall_s=wall_s,
        server=dict(b.params),
    )


def knee(records: list) -> Any:
    """The last concurrency level that still bought meaningful throughput.

    Plain argmax is misleading: throughput often creeps up another 1% at 4x the
    latency. The knee is the point past which you are paying latency for nothing.
    Accepts Records or plain dicts.
    """
    def agg(r):
        return r["aggregate_output_tps"] if isinstance(r, dict) else r.aggregate_output_tps

    def conc(r):
        return r["concurrency"] if isinstance(r, dict) else r.concurrency

    # Collapse repeated levels (e.g. a single-stream run merged with a sweep) — otherwise
    # two records at the same concurrency look like a level that bought no throughput.
    by_level = {}
    for r in records:
        if conc(r) not in by_level or agg(r) > agg(by_level[conc(r)]):
            by_level[conc(r)] = r
    ordered = [by_level[c] for c in sorted(by_level)]
    best = ordered[0]
    for prev, cur in zip(ordered, ordered[1:]):
        if agg(prev) <= 0 or (agg(cur) - agg(prev)) / agg(prev) < 0.05:
            break
        best = cur
    return best


def save(records: list[Record], filename: str) -> Path:
    RESULTS_DIR.mkdir(exist_ok=True)
    path = RESULTS_DIR / filename
    path.write_text(json.dumps([asdict(r) for r in records], indent=2))
    return path


def save_replacing(records: list[Record], filename: str) -> Path:
    """Write records, dropping only the on-disk records for the same backend/model/hardware/kind.

    Re-running one engine should replace that engine's numbers, not wipe a run of the
    same engine against a different model or on different hardware — those are separate
    measurements that happen to share a file.
    """
    RESULTS_DIR.mkdir(exist_ok=True)
    path = RESULTS_DIR / filename
    keys = {(r.backend, r.model, r.hardware, r.kind) for r in records}

    def key(rec: dict):
        return (rec.get("backend"), rec.get("model"), rec.get("hardware"), rec.get("kind", "sweep"))

    kept = []
    if path.exists():
        try:
            data = json.loads(path.read_text())
            kept = [rec for rec in data if key(rec) not in keys]
        except json.JSONDecodeError:
            kept = []
    path.write_text(json.dumps(kept + [asdict(r) for r in records], indent=2))
    return path


def load_all() -> list[dict]:
    """Every record on disk, flattened. The UI reads this so it works with no backend running."""
    out = []
    for path in sorted(RESULTS_DIR.glob("*.json")):
        try:
            data = json.loads(path.read_text())
        except json.JSONDecodeError:
            continue
        for rec in data if isinstance(data, list) else [data]:
            rec["_source"] = path.name
            out.append(rec)
    return out


# Every result in results/ came off this one machine, and it is the only machine these
# benchmarks run on. Hardcoded rather than configured: an env var that can go stale is a
# worse label than no choice at all. Change this line if you move to different hardware —
# and start a fresh results/ directory when you do, because the old numbers no longer
# compare to the new ones.
HARDWARE = "M-series Mac 16GB"


def env_context() -> tuple[str, str, int]:
    """Context labels for the result record.

    Hardware is fixed (see HARDWARE) and dtype is detected from the server, so the dtype
    returned here is only an override for the cases detection cannot cover — an fp16 model
    whose name does not say so, say.
    """
    return (
        HARDWARE,
        os.getenv("BENCH_DTYPE", ""),
        int(os.getenv("BENCH_MAX_MODEL_LEN", "8192")),
    )


# Quantization/format tags that say nothing about which model this is.
_QUANT_TAGS = {"4bit", "8bit", "q4", "q8", "q4_k_m", "q8_0", "fp16", "bf16", "gguf", "mlx",
               "awq", "gptq", "instruct"}


def model_family(model: str) -> str:
    """Collapse an engine-specific model string to the underlying model.

    `hosted_vllm/Qwen3-0.6B-4bit`, `ollama_chat/qwen3:0.6b` and
    `openai/mlx-community/Qwen3-0.6B-4bit` are one 0.6B model served three ways. Grouping
    results by the raw string would give every engine its own bucket and leave nothing to
    compare — which is the whole point of the charts.
    """
    name = model.split("/")[-1].lower().replace(":", "-")
    parts = [p for p in name.split("-") if p not in _QUANT_TAGS]
    return "-".join(parts) or name
