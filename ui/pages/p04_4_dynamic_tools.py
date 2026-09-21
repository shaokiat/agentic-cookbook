import streamlit as st

from common import about_from, cost_metric, load_example, page_tabs, render_events, selected_model, tool_list_expander

st.title("Dynamic Tools")
st.caption("Registries built at runtime: capability-scoped loading and plugin discovery via marker attributes.")

CORE_CONCEPT = """\
**What it is**

`ToolRegistry` is just a dict — nothing stops you from building, swapping, or extending it at
any point, which means tool availability is a runtime decision, not a fixed startup one. This
example shows two ways to build a registry dynamically instead of hardcoding every tool up
front.

```mermaid
flowchart TD
    subgraph Capability-scoped
    Caps[Task declares needed capabilities] --> Filt["Filter the full tool set to just those"] --> R1[Scoped registry]
    end
    subgraph Plugin discovery
    NS[Scan a namespace] --> Mark["Find functions with an @agent_tool marker attribute"] --> R2[Auto-registered registry]
    end
    R1 --> M[Model sees only relevant schemas]
    R2 --> M
```

**Key insight**

Fewer irrelevant tool schemas isn't just tidier — it directly means fewer prompt tokens spent
per turn and fewer opportunities for the model to pick the wrong tool out of an oversized
options list. Capability-scoped loading builds a registry containing only what the current task
needs; plugin discovery instead scans a namespace and auto-registers anything carrying a marker
attribute, so adding a new tool is just writing the function — no registration call required.
"""


relpath = "examples/04_tool_use_patterns/04_dynamic_tools.py"
mod = load_example(relpath)
tab_demo = page_tabs(relpath, mod, about_extra=about_from(CORE_CONCEPT))

with tab_demo:
    with st.container(border=True):
        pattern = st.radio("Pattern", ["Capability-scoped", "Plugin discovery"], horizontal=True)
        if pattern == "Capability-scoped":
            caps = st.multiselect("Capabilities", list(mod.CAPABILITY_MAP), default=["research", "code"])
            preview_registry = mod.build_registry_for(caps)
            prompt = st.text_area("Prompt", value=mod.DEFAULT_SCOPED_PROMPT, height=100)
        else:
            preview_registry = mod.discover_plugins(vars(mod))
            prompt = st.text_area("Prompt", value=mod.DEFAULT_PLUGIN_PROMPT, height=100)
        tool_list_expander(preview_registry, note="Rebuilds live as you change pattern/capabilities above.")
        run = st.button("Run", type="primary")

    if run:
        if pattern == "Capability-scoped":
            agent = mod.build_scoped_agent(caps, model=selected_model())
        else:
            agent = mod.build_plugin_agent(model=selected_model())
        final = render_events(agent.run_events(prompt))
        st.markdown(f"**Final answer:**\n\n{final}")
        cost_metric(agent)
