import streamlit as st

from common import load_example, page_tabs, selected_model

st.title("Reflexion")
st.caption("Generate → Critique → Revise: the agent reviews its own output before finalizing it.")

relpath = "examples/01_agent_patterns/03_reflexion.py"
mod = load_example(relpath)
tab_demo = page_tabs(relpath, mod)

with tab_demo:
    task = st.text_area("Task", value=mod.DEFAULT_TASK, height=80)

    if st.button("Run", type="primary"):
        steps = list(mod.reflexion_steps(task, selected_model()))
        for i, (title, text) in enumerate(steps):
            if i > 0:
                st.divider()
            st.markdown(f"**{title}**")
            st.markdown(text)
