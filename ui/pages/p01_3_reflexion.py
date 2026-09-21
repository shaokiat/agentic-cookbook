import streamlit as st

from core.model import ModelProvider

from common import cost_metric, load_example, page_tabs, selected_model

st.title("Reflexion")
st.caption("Generate → Critique → Revise: the agent reviews its own output before finalizing it.")

relpath = "examples/01_agent_patterns/03_reflexion.py"
mod = load_example(relpath)
tab_demo = page_tabs(relpath, mod)

with tab_demo:
    task = st.text_area("Task", value=mod.DEFAULT_TASK, height=80)

    if st.button("Run", type="primary"):
        provider = ModelProvider(selected_model())
        steps = list(mod.reflexion_steps(task, model_provider=provider))
        for i, (title, text) in enumerate(steps):
            if i > 0:
                st.divider()
            st.markdown(f"**{title}**")
            st.markdown(text)
        cost_metric(provider)
