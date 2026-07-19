import streamlit as st

from common import load_example, page_tabs, selected_model

st.title("Sequential Pipeline")
st.caption("Researcher → Writer → Editor: each specialist hands its output to the next.")

relpath = "examples/03_multi_agent_systems/03_sequential_pipeline.py"
mod = load_example(relpath)
tab_demo = page_tabs(relpath, mod)

with tab_demo:
    topic = st.text_area("Topic", value=mod.DEFAULT_TOPIC, height=80)

    if st.button("Run", type="primary"):
        steps = list(mod.pipeline_steps(topic, selected_model()))
        for i, (title, text) in enumerate(steps):
            if i > 0:
                st.divider()
            st.markdown(f"**{title}**")
            st.markdown(text)
