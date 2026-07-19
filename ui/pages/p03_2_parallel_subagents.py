import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
import streamlit as st

from common import live_panel, load_example, page_tabs, selected_model

st.title("Parallel Subagents")
st.caption(
    "Fan-out: independent workers run concurrently in threads; the page updates as each "
    "future completes (worker threads never touch the UI)."
)

relpath = "examples/03_multi_agent_systems/02_parallel_subagents.py"
mod = load_example(relpath)
tab_demo = page_tabs(relpath, mod)

tasks = mod.DEFAULT_TASKS

with tab_demo:
    st.table(pd.DataFrame(tasks, columns=["Role", "Task"]))

    with st.container(border=True):
        run_sequential_too = st.checkbox("Also run sequentially (for timing comparison)", value=False)
        run = st.button("Run", type="primary")

    if run:
        model = selected_model()

        seq_time = None
        if run_sequential_too:
            with st.spinner("Sequential pass…"):
                _, seq_time = mod.run_sequential(tasks, model)
            st.write(f"Sequential: **{seq_time:.1f}s**")

        panels = {role: live_panel(f"{role} — running…") for role, _ in tasks}
        results = {}
        t0 = time.perf_counter()
        with ThreadPoolExecutor(max_workers=len(tasks)) as executor:
            futures = {executor.submit(mod.run_worker, role, task, model): role for role, task in tasks}
            for future in as_completed(futures):
                role, result = future.result()
                results[role] = result
                label_slot, body_slot = panels[role]
                body_slot.write(result)
                label_slot.markdown(f"**{role} — done**")
        par_time = time.perf_counter() - t0
        st.write(f"Parallel: **{par_time:.1f}s**" + (f" ({seq_time / par_time:.1f}× speedup)" if seq_time else ""))

        with st.spinner("Aggregating…"):
            summary = mod.run_aggregator(results, model)
        st.subheader("Aggregated Summary")
        st.markdown(summary)
