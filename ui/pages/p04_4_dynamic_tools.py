import streamlit as st

from common import load_example, page_tabs, render_events, selected_model

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
            prompt = st.text_area("Prompt", value=mod.DEFAULT_SCOPED_PROMPT, height=100)
        else:
            prompt = st.text_area("Prompt", value=mod.DEFAULT_PLUGIN_PROMPT, height=100)
        run = st.button("Run", type="primary")

    if run:
        if pattern == "Capability-scoped":
            agent = mod.build_scoped_agent(caps, model=selected_model())
        else:
            agent = mod.build_plugin_agent(model=selected_model())
        names = [s["function"]["name"] for s in agent.registry.get_schemas()]
        st.write(f"Registered tools: `{names}`")
        final = render_events(agent.run_events(prompt))
        st.markdown(f"**Final answer:**\n\n{final}")
