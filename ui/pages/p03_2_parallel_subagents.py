import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
import streamlit as st

from core.model import ModelProvider

from common import about_from, cost_metric, live_panel, load_example, page_tabs, selected_model

st.title("Parallel Subagents")
st.caption(
    "Fan-out: independent workers run concurrently in threads; the page updates as each "
    "future completes (worker threads never touch the UI)."
)

CORE_CONCEPT = """\
**What it is**

Several independent worker agents run concurrently instead of one after another, then a fourth
aggregator agent synthesizes their results into one summary. Unlike the orchestrator pattern —
where delegation happens through the model's own tool-call loop, one call at a time — fan-out
here is plain Python: all workers are submitted to a thread pool at once, and results are
collected as they complete.

```mermaid
flowchart TD
    Tasks[Independent tasks] --> P["ThreadPoolExecutor — one thread per task"]
    P --> W1[Worker 1]
    P --> W2[Worker 2]
    P --> W3[Worker 3]
    W1 --> AC[as_completed — arrival order, not spawn order]
    W2 --> AC
    W3 --> AC
    AC --> Agg["Aggregator agent — no tools, synthesizes all results"]
    Agg --> F[Unified summary]
```

**Why threads, not `asyncio`**

`Agent.run()` calls a synchronous, blocking model client under the hood. Wrapping a blocking
call in `async def` doesn't make it non-blocking — it just hides the problem, and coroutines
that never hit a real `await` still run one at a time. `ThreadPoolExecutor` sidesteps this
entirely: each worker blocks independently on its own network call, on its own OS thread, and
Python releases the GIL during I/O so the threads genuinely overlap. The rule of thumb is to
match the concurrency primitive to the call stack — async code reaches for `asyncio.gather`,
synchronous blocking code reaches for `ThreadPoolExecutor`.

**Why the speedup approaches the worker count**

Each worker spends nearly all its time waiting on the model API, not on CPU work — so wall-clock
time for the parallel run is bounded by the *slowest* individual worker, not the sum of all of
them. Three workers that would take ~8s sequentially finish in ~2s together, because their wait
times overlap almost completely.

**Isolation and aggregation stay separate concerns**

Like the orchestrator pattern, every worker gets an empty `Memory()` — none can see another's
output, so each produces an uncontaminated, independent answer. But here coordination (the
fan-out itself) lives in ordinary Python code, while synthesis is delegated to a dedicated
aggregator agent — splitting "who runs what" from "what does it mean," rather than one agent
doing both jobs.
"""


relpath = "examples/03_multi_agent_systems/02_parallel_subagents.py"
mod = load_example(relpath)
tab_demo = page_tabs(relpath, mod, about_extra=about_from(CORE_CONCEPT))

tasks = mod.DEFAULT_TASKS

with tab_demo:
    st.table(pd.DataFrame(tasks, columns=["Role", "Task"]))

    with st.container(border=True):
        run_sequential_too = st.checkbox("Also run sequentially (for timing comparison)", value=False)
        run = st.button("Run", type="primary")

    if run:
        model = selected_model()
        provider = ModelProvider(model)  # shared across the parallel workers + aggregator, so cost sums them all

        seq_time = None
        if run_sequential_too:
            seq_provider = ModelProvider(model)  # separate — this pass is only for timing, kept out of the main cost
            with st.spinner("Sequential pass…"):
                _, seq_time = mod.run_sequential(tasks, model_provider=seq_provider)
            st.write(f"Sequential: **{seq_time:.1f}s**")
            st.caption(f"Sequential comparison pass cost: ${seq_provider.get_cumulative_usage().cost:.4f}")

        panels = {role: live_panel(f"{role} — running…") for role, _ in tasks}
        results = {}
        t0 = time.perf_counter()
        with ThreadPoolExecutor(max_workers=len(tasks)) as executor:
            futures = {
                executor.submit(mod.run_worker, role, task, model, provider): role
                for role, task in tasks
            }
            for future in as_completed(futures):
                role, result = future.result()
                results[role] = result
                label_slot, body_slot = panels[role]
                body_slot.write(result)
                label_slot.markdown(f"**{role} — done**")
        par_time = time.perf_counter() - t0
        st.write(f"Parallel: **{par_time:.1f}s**" + (f" ({seq_time / par_time:.1f}× speedup)" if seq_time else ""))

        with st.spinner("Aggregating…"):
            summary = mod.run_aggregator(results, model_provider=provider)
        st.subheader("Aggregated Summary")
        st.markdown(summary)
        cost_metric(provider)
