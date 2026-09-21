import queue
import time
from concurrent.futures import ThreadPoolExecutor

import streamlit as st

from common import about_from, live_panel, page_tabs, selected_model

st.title("Mini Researcher")
st.caption(
    "query → plan sub-questions → parallel search/scrape/compress → cited report. "
    "Progress events stream from worker threads through a queue."
)

CORE_CONCEPT = """\
**What it is**

A case study composing three patterns from elsewhere in this cookbook into one real pipeline:
Plan-and-Execute (a planner decomposes the query before any research happens), parallel
fan-out/fan-in (each sub-question is researched concurrently), and hybrid-search context
compression (scraped pages are filtered down to only the relevant chunks before synthesis).

```mermaid
flowchart TD
    Q[Query] --> P["Planner — one LLM call → 2-4 sub-questions"]
    P --> W1[Sub-question 1: search → scrape → compress]
    P --> W2[Sub-question 2: search → scrape → compress]
    P --> W3[Sub-question 3: search → scrape → compress]
    W1 --> Agg[Aggregated compressed context]
    W2 --> Agg
    W3 --> Agg
    Agg --> S["Synthesizer — one LLM call, abstains if no relevant context"]
    S --> R[Cited report]
```

**Why a fixed pipeline instead of a ReAct agent**

Unlike the ReAct examples, there's no per-step "decide what to do next" loop here — the shape of
the work (plan, then fan out, then compress, then synthesize) is fixed in code. That's a
deliberate trade against flexibility: research decomposes cleanly into the same four stages
every time, so there's no need to pay for a model call to re-derive the plan at each step. Each
sub-question's search/scrape/compress runs in its own thread (~3x speedup over sequential on a
3-query run), and per-URL/per-sub-query failures are isolated so one dead link never kills the
whole run.
"""


tab_demo = page_tabs(
    None,
    walkthrough_path="agents/mini-researcher/README.md",
    reference_paths=["agents/mini-researcher/docs/ARCHITECTURE.md"],
    blog_label="Researcher Agent (fixed pipeline design)",
    blog_url="https://shaokiat.github.io/shaokiat-blog/docs/genai-agents/use_cases/researcher-agent/",
    blog_note="Covers why this is a fixed Planner → Workers → Compression → Synthesizer "
              "pipeline instead of a ReAct loop, and when you'd reach for each shape.",
    about_extra=about_from(CORE_CONCEPT),
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
