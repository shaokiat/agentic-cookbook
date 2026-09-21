import time

import pandas as pd
import streamlit as st

from core.model import ModelProvider

from common import about_from, cost_metric, load_example, page_tabs, render_events, selected_model, tool_list_expander

st.title("Parallel Tool Calls")
st.caption(
    "When the model emits several tool calls in one turn, ParallelAgent dispatches "
    "the batch concurrently. Sequential first, then parallel, for comparison."
)

CORE_CONCEPT = """\
**What it is**

When a single model response contains several tool calls, `ParallelAgent` overrides the act
step to dispatch the whole batch through a thread pool instead of running them one at a time.
The model already groups independent calls into one response when it decides several actions
don't depend on each other — this pattern parallelizes *within that batch*, cutting latency
without changing the loop's protocol at all: every result is still gathered and added to memory
before the next model turn, so the transcript the model eventually sees is identical either way.

```mermaid
flowchart TD
    M["Model response: N tool calls in one turn"] --> D{Execution mode}
    D -->|Sequential| S1[Tool 1] --> S2[Tool 2] --> S3[Tool 3] --> R1[All results gathered]
    D -->|Parallel| P["ThreadPoolExecutor runs all N calls at once"] --> R2[All results gathered]
    R1 --> N1[Next model turn]
    R2 --> N2[Next model turn]
```

Only wall-clock time changes — the sequential and parallel runs produce the same observations
in the same order once collected, just faster in the parallel case.
"""


relpath = "examples/04_tool_use_patterns/02_parallel_tool_calls.py"
mod = load_example(relpath)
tab_demo = page_tabs(relpath, mod, about_extra=about_from(CORE_CONCEPT))

with tab_demo:
    tool_list_expander(mod.build_registry())
    prompt = st.text_area("Prompt", value=mod.DEFAULT_PROMPT, height=100)

    if st.button("Run comparison", type="primary"):
        model = selected_model()
        registry = mod.build_registry()
        seq_provider = ModelProvider(model)
        par_provider = ModelProvider(model)

        with st.spinner("Sequential run (tools executed one by one)…"):
            _, seq_time = mod._run_sequential(registry, prompt, model_provider=seq_provider)
        st.write(f"Sequential: **{seq_time:.2f}s**")

        st.subheader("Parallel run")
        agent = mod.build_parallel_agent(registry, verbose=False, model_provider=par_provider)
        t0 = time.perf_counter()
        final = render_events(agent.run_events(prompt))
        par_time = time.perf_counter() - t0

        st.dataframe(pd.DataFrame({
            "Mode": ["Sequential", "Parallel"],
            "Time (s)": [round(seq_time, 2), round(par_time, 2)],
            "Speedup": ["1.0×", f"{seq_time / par_time:.1f}×"],
            "Cost": [
                f"${seq_provider.get_cumulative_usage().cost:.4f}",
                f"${par_provider.get_cumulative_usage().cost:.4f}",
            ],
        }), hide_index=True)
        st.markdown(f"**Final answer:**\n\n{final}")
        cost_metric(seq_provider, par_provider)
