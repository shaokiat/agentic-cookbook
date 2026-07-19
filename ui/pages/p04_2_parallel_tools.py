import time

import pandas as pd
import streamlit as st

from common import load_example, page_tabs, render_events, selected_model

st.title("Parallel Tool Calls")
st.caption(
    "When the model emits several tool calls in one turn, ParallelAgent dispatches "
    "the batch concurrently. Sequential first, then parallel, for comparison."
)

relpath = "examples/04_tool_use_patterns/02_parallel_tool_calls.py"
mod = load_example(relpath)
tab_demo = page_tabs(relpath, mod)

with tab_demo:
    prompt = st.text_area("Prompt", value=mod.DEFAULT_PROMPT, height=100)

    if st.button("Run comparison", type="primary"):
        model = selected_model()
        registry = mod.build_registry()

        with st.spinner("Sequential run (tools executed one by one)…"):
            _, seq_time = mod._run_sequential(registry, prompt, model)
        st.write(f"Sequential: **{seq_time:.2f}s**")

        st.subheader("Parallel run")
        agent = mod.build_parallel_agent(registry, model, verbose=False)
        t0 = time.perf_counter()
        final = render_events(agent.run_events(prompt))
        par_time = time.perf_counter() - t0

        st.dataframe(pd.DataFrame({
            "Mode": ["Sequential", "Parallel"],
            "Time (s)": [round(seq_time, 2), round(par_time, 2)],
            "Speedup": ["1.0×", f"{seq_time / par_time:.1f}×"],
        }), hide_index=True)
        st.markdown(f"**Final answer:**\n\n{final}")
