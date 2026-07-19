import queue
import time
from concurrent.futures import ThreadPoolExecutor

import streamlit as st

from common import live_panel, page_tabs, selected_model

st.title("Mini Researcher")
st.caption(
    "query → plan sub-questions → parallel search/scrape/compress → cited report. "
    "Progress events stream from worker threads through a queue."
)
tab_demo = page_tabs(
    None,
    walkthrough_path="agents/mini-researcher/README.md",
    reference_paths=["agents/mini-researcher/docs/ARCHITECTURE.md"],
)

with tab_demo:
    try:
        from researcher.config import Config
        from researcher.pipeline import ResearchPipeline
    except ImportError:
        st.error(
            "mini-researcher is not installed in this environment. From the repo root run:\n\n"
            "`uv pip install --python .venv/bin/python -e agents/mini-researcher`"
        )
        st.stop()

    with st.container(border=True):
        max_sub_queries = st.slider("Max sub-queries", 2, 6, 4)
        results_per_query = st.slider("Search results per sub-query", 1, 5, 3)
        query = st.text_input("Research query", placeholder="e.g. What is the state of solid-state batteries in 2026?")
        run = st.button("Research", type="primary")

    if run and query:
        config = Config()
        config.max_sub_queries = max_sub_queries
        config.results_per_query = results_per_query
        config.model = selected_model()

        events: queue.Queue = queue.Queue()
        pipeline = ResearchPipeline(config, on_event=events.put)

        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(pipeline.run, query)

            plan_label, plan_body = live_panel("Planning sub-queries…")
            sq_panels: dict[str, object] = {}
            sq_lines: dict[str, list[str]] = {}
            synth_label = None

            while not (future.done() and events.empty()):
                try:
                    ev = events.get(timeout=0.1)
                except queue.Empty:
                    continue
                stage = ev["stage"]
                if stage == "planning_done":
                    plan_body.markdown("\n".join(f"- {sq}" for sq in ev["sub_queries"]))
                    plan_label.markdown(f"**Planned {len(ev['sub_queries'])} sub-queries**")
                    for sq in ev["sub_queries"]:
                        sq_panels[sq] = live_panel(f"🔍 {sq}")
                        sq_lines[sq] = []
                elif stage == "searched" and ev["sub_query"] in sq_panels:
                    sq_lines[ev["sub_query"]].append(f"Found {ev['n_results']} results")
                    sq_panels[ev["sub_query"]][1].markdown("\n\n".join(sq_lines[ev["sub_query"]]))
                elif stage == "scraped" and ev["sub_query"] in sq_panels:
                    sq_lines[ev["sub_query"]].append(f"Scraped {ev['url']}")
                    sq_panels[ev["sub_query"]][1].markdown("\n\n".join(sq_lines[ev["sub_query"]]))
                elif stage == "subquery_done" and ev["sub_query"] in sq_panels:
                    sq_panels[ev["sub_query"]][0].markdown(
                        f"**✅ {ev['sub_query']} ({ev['blocks']} context blocks)**")
                elif stage == "synthesizing":
                    synth_label, _ = live_panel("Synthesizing report…")
                elif stage == "done" and synth_label is not None:
                    synth_label.markdown("**Report ready**")

            report = future.result()

        st.divider()
        st.markdown(report.content)

        u = report.usage
        c1, c2, c3 = st.columns(3)
        c1.metric("Research time", f"{report.timing['research_seconds']:.1f}s")
        c2.metric("Tokens", getattr(u, "total_tokens", "—"))
        cost = getattr(u, "cost", None)
        c3.metric("Cost", f"${cost:.4f}" if cost else "—")
