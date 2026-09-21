import streamlit as st

from core.model import ModelProvider

from common import about_from, cost_metric, load_example, page_tabs, selected_model

st.title("Sequential Pipeline")
st.caption("Researcher → Writer → Editor: each specialist hands its output to the next.")

CORE_CONCEPT = """\
**What it is**

Three specialist agents chain together — Researcher → Writer → Editor — where each stage's
output becomes the next stage's input. Specialization via narrow, single-purpose system prompts
beats asking one generalist agent to research, draft, and polish all in one pass.

```mermaid
flowchart LR
    T[Topic] --> R["Researcher agent"]
    R -->|research notes| W["Writer agent"]
    W -->|draft| E["Editor agent"]
    E --> F[Final piece]
```

**Key insight**

The "pipeline" is nothing more than function composition over `agent.run()` return values — no
framework, no message schema, just a string passed forward from one agent to the next. Each
stage is exposed as a step in a generator, so a frontend can render intermediate results (the
research notes, then the draft, then the edit) as they complete, rather than waiting for the
whole chain to finish. It's the same chaining shape as Reflexion, but here each stage does a
*different* job (research, then write, then edit) instead of critiquing the same output.
"""


relpath = "examples/03_multi_agent_systems/03_sequential_pipeline.py"
mod = load_example(relpath)
tab_demo = page_tabs(relpath, mod, about_extra=about_from(CORE_CONCEPT))

with tab_demo:
    topic = st.text_area("Topic", value=mod.DEFAULT_TOPIC, height=80)

    if st.button("Run", type="primary"):
        provider = ModelProvider(selected_model())
        steps = list(mod.pipeline_steps(topic, model_provider=provider))
        for i, (title, text) in enumerate(steps):
            if i > 0:
                st.divider()
            st.markdown(f"**{title}**")
            st.markdown(text)
        cost_metric(provider)
