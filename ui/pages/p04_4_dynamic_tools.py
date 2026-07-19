import streamlit as st

from common import cost_metric, load_example, page_tabs, render_events, selected_model, tool_list_expander

st.title("Dynamic Tools")
st.caption("Registries built at runtime: capability-scoped loading and plugin discovery via marker attributes.")

relpath = "examples/04_tool_use_patterns/04_dynamic_tools.py"
mod = load_example(relpath)
tab_demo = page_tabs(relpath, mod)

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
