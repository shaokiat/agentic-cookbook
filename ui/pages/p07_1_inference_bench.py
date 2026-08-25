import os

import pandas as pd
import streamlit as st

from common import load_example, page_tabs

st.title("Inference Benchmarks")
st.caption(
    "Self-hosted vLLM, Ollama and mlx-lm: TTFT, decode rate, and the throughput/latency "
    "knee that only appears once requests overlap. One engine is benchmarked per run — "
    "the comparison is assembled from saved results, not measured side by side."
)

relpath = "examples/07_inference/03_load_sweep.py"
sweep_mod = load_example(relpath)
harness = load_example("examples/07_inference/harness.py")

ENGINES = [
    (
        "vLLM",
        "The contender. A scheduler, not just a runtime.",
        """make serve-vllm      # vllm-metal on Apple Silicon (MLX backend, own venv)

# the flags it passes, all set in deploy/engines.yaml
vllm serve mlx-community/Qwen3-0.6B-4bit --port 8000 \\
  --max-model-len 8192 --max-num-seqs 64 \\
  --gpu-memory-utilization 0.92 --enable-prefix-caching""",
        [
            "**Continuous batching** — finished sequences leave the batch at every decode "
            "iteration and queued ones join immediately, so the accelerator never idles "
            "waiting for the longest request in a fixed batch. This is the one feature the "
            "throughput curve above is actually measuring.",
            "**PagedAttention** — KV cache stored in fixed-size blocks instead of one "
            "contiguous per-request reservation, so concurrency scales until the cache is "
            "genuinely full rather than until it is fragmented.",
            "**Prefix caching** — a shared system prompt is prefilled once and reused across "
            "requests, which is most of the win for agent workloads that resend a long tool "
            "preamble every turn.",
            "**Prometheus `/metrics`** — `num_requests_running`, `num_requests_waiting`, "
            "`kv_cache_usage_perc`. The sweep scrapes these while the batch is in flight, "
            "which is how the knee becomes something you watch rather than infer.",
            "**Cost:** heaviest install of the three, and it pins its own torch build — hence "
            "the separate `~/.venv-vllm-metal`.",
        ],
    ),
    (
        "Ollama",
        "The convenient one. Fixed parallel slots, not a dynamic scheduler.",
        """make pull-ollama     # once
make serve-ollama

# under the hood — NUM_PARALLEL must be set BEFORE the server starts
OLLAMA_HOST=127.0.0.1:8000 OLLAMA_NUM_PARALLEL=32 \\
  OLLAMA_CONTEXT_LENGTH=8192 ollama serve""",
        [
            "**llama.cpp / GGUF underneath** — one binary, model pull built in, no venv "
            "surgery. The lowest-friction way to have a local model at all.",
            "**Parallelism is a slot count, not a scheduler** — `OLLAMA_NUM_PARALLEL` fixes "
            "how many requests run at once; past that they queue. The throughput curve "
            "flattens at exactly that number, and the shape of the flattening is the config.",
            "**The default is conservative.** Benchmarking Ollama without raising it measures "
            "the default setting and not the engine — the single most common way this "
            "comparison is run wrong.",
            "**Automatic model load/unload** — good when you switch between many models, and "
            "a source of surprise cold-start TTFT if a swap happens mid-benchmark.",
            "**No scheduler metrics endpoint**, so there is nothing to scrape while a batch "
            "is in flight.",
        ],
    ),
    (
        "mlx-lm",
        "The control. Same weights, same backend, no batching.",
        """make install-mlx     # once
make serve-mlx

# under the hood
~/.venv-mlx-lm/bin/mlx_lm.server --model mlx-community/Qwen3-0.6B-4bit --port 8000""",
        [
            "**Not a contender — a control.** It serves the *same* MLX weights at the *same* "
            "quantization on the *same* Metal backend as vllm-metal. Quantization and hardware "
            "are held constant, so any gap under load is the scheduler and nothing else.",
            "**One request at a time** — aggregate throughput is essentially flat from "
            "concurrency 1 upward; extra load turns into queueing, visible first as TTFT.",
            "**Strong single-stream decode** — at concurrency 1 it is competitive with, and "
            "often faster than, the batching engines. That is exactly why a single-stream "
            "benchmark cannot rank serving engines.",
            "**Trivial install** — a pip package and a port, no plugin and no compatibility "
            "matrix to check.",
        ],
    ),
]


def engine_notes() -> None:
    st.markdown(
        "Three OpenAI-compatible engines, run one at a time because they each want the whole "
        "accelerator. They all serve on the same port (`LOCAL_API_BASE`, default "
        "`http://localhost:8000/v1`) and the probe identifies which one answered, so swapping "
        "engines is `make stop` then the next `make serve-*` — no config to keep in sync. "
        "What separates them is not the model: it is what the server does when requests "
        "overlap. Models and tuning parameters for all three live in `deploy/engines.yaml`; "
        "the settings each run actually used are recorded with its results."
    )
    for name, tagline, snippet, features in ENGINES:
        st.divider()
        st.markdown(f"#### {name}")
        st.caption(tagline)
        st.code(snippet, language="bash")
        for line in features:
            st.markdown(f"- {line}")


tab_demo = page_tabs(
    relpath,
    sweep_mod,
    about_extra=engine_notes,
    reference_paths=[
        "examples/07_inference/01_backends.py",
        "examples/07_inference/02_benchmark.py",
        "docs/inference_serving.md",
        "deploy/vllm/README.md",
    ],
)

# Presets rather than a free-text box: two runs sampled at different concurrency levels
# produce curves that do not line up, and the levels are the x-axis of the experiment.
# Quick already shows the shape; the rest is spent on the expensive top of the curve.
LEVEL_PRESETS = {
    "Quick (1–8)": [1, 2, 4, 8],
    "Full (1–32)": [1, 2, 4, 8, 16, 32],
    "Deep (1–64)": [1, 2, 4, 8, 16, 32, 64],
}

# Fixed slot per backend so a filter that drops a series never repaints the survivors.
SERIES_COLORS = {"vllm": "#2a78d6", "ollama": "#eb6834", "tgi": "#1baf7a", "mlx-lm": "#eda100"}
FALLBACK = ["#e87ba4", "#008300", "#4a3aa7", "#e34948"]


def colors_for(names: list[str]) -> list[str]:
    spare = iter(FALLBACK)
    return [SERIES_COLORS.get(n) or next(spare, "#4a3aa7") for n in names]


def wide(df: pd.DataFrame, value: str) -> pd.DataFrame:
    return df.pivot_table(index="concurrency", columns="backend", values=value, aggfunc="mean")


def results_file(backend: str) -> str:
    """Write back into whatever file already holds this backend's sweep, so a re-run
    replaces those records instead of accumulating a parallel copy."""
    for rec in harness.load_all():
        if rec["backend"] == backend and rec.get("kind", "sweep") == "sweep":
            return rec["_source"]
    return f"{backend.replace('-', '_')}_sweep.json"


with tab_demo:
    # One engine holds the accelerator at a time, so nothing here is measured side by side.
    # Each run benchmarks the engine that is live right now and replaces that engine's
    # records; the charts below are the accumulation of those separate runs.
    st.subheader("Run a benchmark")

    if st.button("Probe endpoint"):
        st.session_state["inf_backends"] = harness.discover()

    found = st.session_state.get("inf_backends")
    if found is None:
        st.info(f"Probe `{os.getenv('LOCAL_API_BASE', harness.DEFAULT_API_BASE)}` "
                "to see which engine is serving it.")
    elif not found:
        st.warning("No local endpoint configured. See `deploy/vllm/README.md`.")
    else:
        for b in found:
            icon = "🟢" if b.available else "🔴"
            st.markdown(f"{icon} **{b.name}** — `{b.model}` @ `{b.api_base}`")
            st.caption(b.detail)

    if found and not any(b.available for b in found):
        st.caption("Nothing is serving. Start an engine: `make serve-vllm`, `make serve-mlx` "
                   "or `make serve-ollama`.")

    live = [b for b in (found or []) if b.available]
    if live:
        # Exactly one, by construction — one endpoint, whichever engine currently owns it.
        target = live[0]
        preset = st.radio(
            "Concurrency levels", list(LEVEL_PRESETS), horizontal=True,
            help="Where to sample the curve. The top level dominates the runtime, so this "
                 "is the cost knob — the shape of the curve is already visible from Quick.",
        )
        levels = LEVEL_PRESETS[preset]

        hardware, dtype_override, max_len = harness.env_context()
        dtype = dtype_override or target.dtype or "unspecified"
        st.caption(
            f"{levels} concurrent requests · {sweep_mod.MAX_TOKENS} output tokens each · "
            f"recorded as hardware=`{hardware}` dtype=`{dtype}` max_model_len=`{max_len}`"
        )
        if dtype == "unspecified":
            st.caption("The model name does not say how it is quantized — set `BENCH_DTYPE` "
                       "in `.env` if you want the record to say.")

        run_col, check_col = st.columns(2)
        if check_col.button("Sanity check", width="stretch",
                            help="One completion, so you can see the endpoint actually answers."):
            r = harness.timed_completion(target, harness.PROMPT_SUITE[0], 128)
            if not r.ok:
                st.error(r.error)
            else:
                st.caption(f"TTFT {r.ttft_ms:.0f}ms · ITL {r.itl_ms:.1f}ms · "
                           f"{r.output_tps:.1f} decode tok/s · {r.output_tokens} tokens")
                st.markdown((r.text or r.reasoning).strip()[:600] or "_empty response_")

        if run_col.button(f"Run sweep on {target.name}", type="primary", width="stretch"):
            progress = st.empty()
            with st.spinner(f"Sweeping {target.name} at {levels}…"):
                records = sweep_mod.sweep_backend(
                    target, levels, sweep_mod.MAX_TOKENS,
                    on_level=lambda rec: progress.caption(
                        f"c={rec.concurrency}: {rec.aggregate_output_tps:.1f} aggregate tok/s · "
                        f"e2e p95 {rec.e2e_ms['p95']:.0f}ms · {rec.errors} errors"
                    ),
                )
            path = harness.save_replacing(records, results_file(target.name))
            st.session_state["inf_last_run"] = (
                f"Recorded {len(records)} levels for **{target.name}** "
                f"(`{target.model}` on {hardware}) → `{path.name}`. Any earlier run of the "
                "same engine on the same model and hardware was replaced."
            )
            st.rerun()

    if st.session_state.get("inf_last_run"):
        st.success(st.session_state.pop("inf_last_run"))

    st.divider()
    st.subheader("Results")

    records = harness.load_all()
    if not records:
        st.info("No results yet. See `examples/07_inference/00_running_engines.md`.")
        st.stop()

    df = pd.DataFrame(records)
    df["ttft_p50"] = df["ttft_ms"].apply(lambda d: d.get("p50", 0))
    df["itl_p50"] = df["itl_ms"].apply(lambda d: d.get("p50", 0))
    df["e2e_p95"] = df["e2e_ms"].apply(lambda d: d.get("p95", 0))
    df["kind"] = df["kind"].fillna("sweep") if "kind" in df else "sweep"

    # Grouped by model, not by hardware — hardware is fixed (harness.HARDWARE), and each
    # engine names the same weights differently, so the raw model string cannot group them.
    df["family"] = df["model"].apply(harness.model_family)
    families = sorted(df["family"].unique())
    chosen = st.selectbox("Model", families, help="Results for different models are not "
                          "comparable — pick one to compare engines on.")
    df = df[df["family"] == chosen]

    served = df.drop_duplicates("backend").sort_values("backend")
    st.caption(f"On {harness.HARDWARE} · served as " + " · ".join(
        f"**{r.backend}** `{r.model}` ({r.dtype})" for r in served.itertuples()))

    with st.expander("Serving parameters these results were produced with"):
        st.caption(
            "Read off each server at probe time, not assumed — a curve is only interpretable "
            "next to the settings that shaped it. Set them in `deploy/engines.conf`."
        )
        rows = [{"backend": r.backend, **{k: str(v) for k, v in (r.server or {}).items()}}
                for r in served.itertuples() if getattr(r, "server", None)]
        bare = [r.backend for r in served.itertuples() if not getattr(r, "server", None)]
        if not rows:
            st.caption("These records predate parameter capture — re-run to record them.")
        else:
            st.dataframe(pd.DataFrame(rows).set_index("backend").T.fillna("—"),
                         width="stretch")
            st.caption(
                "`—` means the engine has no such setting. A `*` means the value was "
                "declared in `deploy/engines.yaml` rather than confirmed by the server: "
                "`max_num_seqs` and `OLLAMA_NUM_PARALLEL` are the two knobs no endpoint "
                "reports."
            )
        if bare:
            st.caption(
                f"**{', '.join(bare)}** reports no serving parameters — mlx-lm has none to "
                "report. It answers one request at a time and has no scheduler to tune, "
                "which is exactly why it is the control."
            )

    if "synthetic" in df and df["synthetic"].any():
        st.warning("⚠️ Some records are marked synthetic — those numbers were not measured.")

    sweeps = df[df["kind"] == "sweep"]
    singles = df[df["kind"] == "single"]

    if sweeps.empty:
        st.info(f"No concurrency sweeps for `{chosen}` yet.")
        st.stop()

    backends = sorted(sweeps["backend"].unique())

    st.subheader("Aggregate throughput vs concurrency")
    st.caption("The headline. Continuous batching keeps climbing; a simpler scheduler flattens.")
    st.line_chart(wide(sweeps, "aggregate_output_tps"), color=colors_for(backends),
                  x_label="Concurrent requests", y_label="Aggregate output tok/s")

    cols = st.columns(len(backends))
    knees = {}
    for col, name in zip(cols, backends):
        sub = sweeps[sweeps["backend"] == name]
        # The knee, not the argmax — throughput often creeps up another 1% at 2x latency.
        k = harness.knee(sub.to_dict("records"))
        knees[name] = k
        col.metric(
            f"{name} — knee",
            f"{k['aggregate_output_tps']:.0f} tok/s",
            help=f"e2e p95 {k['e2e_p95']:.0f}ms at concurrency {int(k['concurrency'])}",
        )
        col.caption(f"at concurrency **{int(k['concurrency'])}**")

    if "vllm" in knees and len(knees) > 1:
        gaps = ", ".join(
            f"**{knees['vllm']['aggregate_output_tps'] / k['aggregate_output_tps']:.1f}×** {n}"
            for n, k in knees.items() if n != "vllm" and k["aggregate_output_tps"]
        )
        st.success(f"At its knee, vLLM sustains {gaps}.")

    # Deliberately a second chart, not a second y-axis on the one above.
    st.subheader("Per-request latency vs concurrency")
    st.caption("The price of that throughput. Latency degrades the whole way up.")
    st.line_chart(wide(sweeps, "e2e_p95"), color=colors_for(backends),
                  x_label="Concurrent requests", y_label="End-to-end p95 (ms)")

    st.subheader("Time to first token")
    st.caption("Queueing shows up here first — TTFT climbs long before throughput stops rising.")
    st.bar_chart(wide(sweeps, "ttft_p50"), color=colors_for(backends),
                 x_label="Concurrent requests", y_label="TTFT p50 (ms)")

    if not singles.empty:
        st.subheader("Single stream (concurrency 1)")
        st.caption(
            "What one user feels, with nothing to batch. The engines are much closer here — "
            "which is exactly why a single-stream benchmark cannot rank serving engines."
        )
        st.dataframe(
            singles[["backend", "dtype", "ttft_p50", "itl_p50", "output_tps_per_req"]]
            .rename(columns={"ttft_p50": "TTFT p50 (ms)", "itl_p50": "ITL p50 (ms)",
                             "output_tps_per_req": "decode tok/s"})
            .round(1),
            hide_index=True, width="stretch",
        )

    st.subheader("Cost")
    st.caption(
        "Self-hosting only beats a per-token API at sustained utilisation. This computes "
        "$/1M output tokens from the measured knee and the real instance price."
    )
    hourly = st.number_input("Instance cost ($/hour)", min_value=0.0, value=0.70, step=0.05)
    util = st.slider("Utilisation (% of the hour actually generating)", 1, 100, 100)
    rows = []
    for name in backends:
        tokens_per_hour = knees[name]["aggregate_output_tps"] * 3600 * (util / 100)
        rows.append({
            "backend": name,
            "knee tok/s": round(knees[name]["aggregate_output_tps"], 1),
            "$/1M output tokens": round(hourly / tokens_per_hour * 1e6, 2) if tokens_per_hour else None,
        })
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")

    with st.expander("Raw records"):
        st.dataframe(
            df[["backend", "kind", "model", "dtype", "concurrency", "requests", "errors",
                "ttft_p50", "e2e_p95", "output_tps_per_req", "aggregate_output_tps",
                "note", "_source"]],
            hide_index=True, width="stretch",
        )
