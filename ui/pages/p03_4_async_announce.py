import queue
import time

import pandas as pd
import streamlit as st

from core.model import ModelProvider

from common import cost_metric, live_panel, load_example, page_tabs, selected_model

st.title("Async Announce")
st.caption(
    "Workers run in daemon threads and announce results on a shared queue; the parent loop "
    "drains it without blocking — results arrive in completion order, not spawn order."
)

relpath = "examples/03_multi_agent_systems/04_async_announce.py"
mod = load_example(relpath)
tab_demo = page_tabs(relpath, mod)

tasks = mod.DEFAULT_TASKS

with tab_demo:
    st.table(pd.DataFrame(tasks, columns=["Worker", "Task"]))

    if st.button("Run", type="primary"):
        model = selected_model()
        provider = ModelProvider(model)  # shared across background workers + synthesizer
        announce_queue = queue.Queue()
        for worker_id, task in tasks:
            mod.spawn_background_worker(worker_id, task, announce_queue, model, provider)

        panels = {wid: live_panel(f"{wid} — running…") for wid, _ in tasks}
        ticker = st.empty()
        announcements = []
        tick = 0
        while len(announcements) < len(tasks):
            time.sleep(1.0)
            tick += 1
            arrived = []
            try:
                while True:
                    arrived.append(announce_queue.get_nowait())
            except queue.Empty:
                pass
            for ann in arrived:
                announcements.append(ann)
                label_slot, body_slot = panels[ann.worker_id]
                body_slot.write(ann.result)
                label_slot.markdown(f"**{ann.worker_id} — announced after {ann.elapsed:.1f}s**")
            ticker.caption(
                f"Tick {tick}: {len(announcements)}/{len(tasks)} announcements received "
                f"(parent loop stays free between ticks)")

        with st.spinner("Synthesizing…"):
            summary = mod.run_synthesizer(announcements, model_provider=provider)
        st.subheader("Synthesized Result")
        st.markdown(summary)
        cost_metric(provider)
