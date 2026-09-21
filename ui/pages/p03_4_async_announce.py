import queue
import time

import pandas as pd
import streamlit as st

from core.model import ModelProvider

from common import about_from, cost_metric, live_panel, load_example, page_tabs, selected_model

st.title("Async Announce")
st.caption(
    "Workers run in daemon threads and announce results on a shared queue; the parent loop "
    "drains it without blocking — results arrive in completion order, not spawn order."
)

CORE_CONCEPT = """\
**What it is**

Workers run in daemon threads and push an `Announcement` onto a shared queue when they finish,
instead of the parent blocking on each one in turn. The parent polls that queue between ticks
without blocking, so results surface in completion order — not spawn order — and a slow worker
never holds up a fast one from being processed.

```mermaid
flowchart TD
    Spawn[Parent spawns daemon-thread workers] --> W1[Worker 1]
    Spawn --> W2[Worker 2]
    Spawn --> W3[Worker 3]
    W1 -->|announce when done| Q[(Shared queue)]
    W2 -->|announce when done| Q
    W3 -->|announce when done| Q
    Q --> Poll["Parent polls queue each tick — non-blocking"]
    Poll --> Synth[Synthesizer agent processes announcements as they arrive]
```

**Key insight — decoupled in time, not just in execution**

This differs from Parallel Subagents in *when* results are consumed. There, the parent thread
waits on `as_completed` until every worker is done. Here, the parent's own turn can advance —
and its state persist — before any sub-agent finishes; announcements are drained opportunistically
whenever the parent checks the queue. In a production system this queue becomes a real message
bus, and an announcement re-enters the parent's session as an ordinary inbound message rather
than a blocking return value — the same shape OpenClaw and Nanobot use to deliver sub-agent
results back to a parent session.
"""


relpath = "examples/03_multi_agent_systems/04_async_announce.py"
mod = load_example(relpath)
tab_demo = page_tabs(relpath, mod, about_extra=about_from(CORE_CONCEPT))

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
